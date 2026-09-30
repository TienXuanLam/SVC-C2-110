"""AgentCore Platform v1.0"""

# Outer-graph `main` slot — Cat 2 GraphNode wrapping the inner domain
# workflow (src/graph/domain_workflow_graph.py). See graph.py and
# docs/02_design.md "Architecture" for the outer/inner split rationale
# (Agent1000 review finding T1-1, 2026-07-28).

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel

from src.services.evidence_mapping_service import PolicyKnowledgeBase
from src.services.consistency_validation_service import ClaimHistoryLookup

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import EvidenceValidationWorkflowGraph


class EvidenceValidationGraphNode(GraphNode):
    """Wraps EvidenceValidationWorkflowGraph (evidence mapping ->
    consistency validation) in the outer graph's `main` slot."""

    # S-1: consistent with every other node in this template — claim data
    # requires an authorized caller. The same trust level propagates into
    # the inner graph automatically via GraphNode.execute().
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        policy_kb: PolicyKnowledgeBase | None = None,
        claim_history: ClaimHistoryLookup | None = None,
    ) -> None:
        super().__init__()
        self._policy_kb = policy_kb
        self._claim_history = claim_history
        self._subgraph: EvidenceValidationWorkflowGraph | None = None

    def get_subgraph(self) -> EvidenceValidationWorkflowGraph:
        from src.graph.domain_workflow_graph import EvidenceValidationWorkflowGraph

        if self._subgraph is None:
            self._subgraph = EvidenceValidationWorkflowGraph(
                config={
                    "policy_kb": self._policy_kb,
                    "claim_history": self._claim_history,
                }
            )
            self._subgraph.compile()
        return self._subgraph

    def extract_input(self, state: AgentState) -> str:
        # GraphNode.execute() calls subgraph.invoke(user_input, ...) with no
        # input_context channel (framework contract — see
        # framework/nodes/graph_node.py execute()), so the JSON-encoded
        # normalized claim manifest must travel as the plain user_input
        # string. The inner graph's EvidenceMappingNode reads it back out of
        # state["user_input"] (BaseGraph.invoke()'s own initial_state field).
        return state.get("claim_references") or "{}"

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        """Map inner graph sub_result fields into the outer state delta.

        Explicit field-by-field mapping only — no raw pass-through
        (CoE criterion #9).
        """
        return {
            "evidence_map": sub_result.get("evidence_map"),
            "missing_evidence": sub_result.get("missing_evidence"),
            "consistency_findings": sub_result.get("consistency_findings"),
            "exception_evidence_present": sub_result.get("exception_evidence_present", False),
            "validation_confidence": sub_result.get("validation_confidence", "needs_human_confirmation"),
            "status": sub_result.get("status"),
        }
