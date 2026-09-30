"""AgentCore Platform v1.0"""

# Inner-graph node — Step 2 (Checklist-to-evidence mapping), domain_workflow_graph.py.
# Part of the Cat 2 inner workflow wrapped by EvidenceValidationGraphNode in
# the outer src/graph/graph.py — see docs/02_design.md.

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.evidence_mapping_service import PolicyKnowledgeBase, map_evidence


class EvidenceMappingNode(FunctionNode):
    """Map claim evidence to policy/checklist requirements."""

    # S-1: inner-graph nodes still declare trust level explicitly — the
    # inner graph receives the outer InvocationContext automatically via
    # GraphNode.execute() (framework contract), so this stays consistent
    # with the outer pre_process/post_process declaration.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, policy_kb: PolicyKnowledgeBase | None = None) -> None:
        super().__init__()
        self._policy_kb = policy_kb

    def execute(self, state: AgentState) -> dict[str, Any]:
        # This inner-graph node receives the normalized claim manifest via
        # user_input (BaseGraph.invoke()'s initial_state field), not
        # claim_references — GraphNode.execute() has no input_context
        # channel into the inner graph (see EvidenceValidationGraphNode
        # .extract_input()). Also fall back to claim_references for direct
        # unit-test construction of this node in isolation.
        claim_references_raw = state.get("user_input") or state.get("claim_references")
        try:
            claim_references = json.loads(claim_references_raw) if claim_references_raw else {}
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["EvidenceMappingNode: claim manifest is not valid JSON"],
            }

        evidence_map, missing_evidence = map_evidence(claim_references, self._policy_kb)

        # T1-2 fix: policy_resolved must reflect whether the policy/checklist
        # version was actually resolved against a configured knowledge base.
        # A missing policy_kb (fail-closed, per proposal §12 Dependency 1 and
        # docs/02_design.md) must NEVER be treated as "resolved" — that was
        # the prior bug (`or self._policy_kb is None`), which let claims
        # reach "ready_for_human_warranty_review" without an approved policy
        # version at all. Absence of a configured KB is exactly the
        # unresolved case, so it must produce policy_resolved=False and
        # route to needs_human_confirmation via consistency_validation.
        policy_resolved = any(detail.get("policy_resolved") for detail in evidence_map.values())

        emit_trace_event(
            "evidence_mapping_completed",
            {
                "missing_evidence_count": len(missing_evidence),
                "policy_resolved": policy_resolved,
            },
            state,
        )

        return {
            # Re-expose the parsed claim manifest under claim_references so
            # the next inner-graph node (ConsistencyValidationNode) can read
            # it without redoing the user_input/claim_references fallback.
            "claim_references": json.dumps(claim_references),
            "evidence_map": json.dumps(evidence_map),
            "missing_evidence": json.dumps(missing_evidence),
            "policy_resolved": policy_resolved,
            "status": AgentStatus.SUCCESS.value,
        }
