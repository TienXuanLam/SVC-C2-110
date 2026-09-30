"""AgentCore Platform v1.0"""

# Inner-graph node — Step 3 (Consistency and exception validation),
# domain_workflow_graph.py. Part of the Cat 2 inner workflow wrapped by
# EvidenceValidationGraphNode in the outer src/graph/graph.py.

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.consistency_validation_service import (
    ClaimHistoryLookup,
    validate_consistency,
)


class ConsistencyValidationNode(FunctionNode):
    """Run deterministic consistency/exception checks against evidence."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, claim_history: ClaimHistoryLookup | None = None) -> None:
        super().__init__()
        self._claim_history = claim_history

    def execute(self, state: AgentState) -> dict[str, Any]:
        claim_references_raw = state.get("claim_references")
        evidence_map_raw = state.get("evidence_map")
        try:
            claim_references = json.loads(claim_references_raw) if claim_references_raw else {}
            evidence_map = json.loads(evidence_map_raw) if evidence_map_raw else {}
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ConsistencyValidationNode: upstream JSON state field could not be parsed"],
            }

        policy_resolved = bool(state.get("policy_resolved", False))

        # T1-3 fix: validate_consistency() calls into the injected
        # ClaimHistoryLookup adapter, which is an external/connector call
        # (docs/02_design.md). An adapter/data-source outage must not
        # propagate as an unhandled exception through this node's execute()
        # — the module's own docstring promises business-data checks "never
        # raise," but the prior implementation did not actually guard the
        # one call that can (has_open_or_recent_claim()). On failure, treat
        # the duplicate-claim check as unresolved and route to
        # needs_human_confirmation rather than crashing the request.
        try:
            findings, exception_evidence_present, validation_confidence = validate_consistency(
                claim_references,
                evidence_map,
                policy_resolved=policy_resolved,
                claim_history=self._claim_history,
            )
        except Exception as exc:  # noqa: BLE001 — deliberate safe-degrade boundary
            emit_trace_event(
                "claim_history_lookup_failed",
                {"error": str(exc)},
                state,
            )
            findings, exception_evidence_present, validation_confidence = validate_consistency(
                claim_references,
                evidence_map,
                policy_resolved=policy_resolved,
                claim_history=None,
            )
            findings.append(
                {
                    "category": "duplicate_claim_check_unavailable",
                    "note": "duplicate-claim history lookup failed; treat as unresolved and confirm manually",
                }
            )
            validation_confidence = "needs_human_confirmation"

        emit_trace_event(
            "consistency_validation_completed",
            {
                "validation_confidence": validation_confidence,
                "finding_count": len(findings),
                "exception_evidence_present": exception_evidence_present,
            },
            state,
        )

        return {
            "consistency_findings": json.dumps(findings),
            "exception_evidence_present": exception_evidence_present,
            "validation_confidence": validation_confidence,
            "status": AgentStatus.SUCCESS.value,
        }
