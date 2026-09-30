"""AgentCore Platform v1.0"""

# Inner graph for the Cat 2 evidence-validation domain workflow.
# Wrapped by EvidenceValidationGraphNode.get_subgraph() in src/graph/graph.py.
#
# Pipeline: START -> evidence_mapping -> consistency_validation -> END
#
# Inherits BaseGraph (fully custom 2-node topology — not the fixed
# pre_process/main/post_process backbone) per
# src/examples/domain_workflow_graph_sample.py.

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.consistency_validation_node import ConsistencyValidationNode
from src.nodes.evidence_mapping_node import EvidenceMappingNode
from src.schemas.state import State


class EvidenceValidationWorkflowGraph(BaseGraph):
    """Inner Cat 2 domain workflow: evidence mapping -> consistency validation.

    Called by EvidenceValidationGraphNode.get_subgraph() in graph.py.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._policy_kb = self.config.get("policy_kb")
        self._claim_history = self.config.get("claim_history")

    @property
    def name(self) -> str:
        return "evidence_validation_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # policy_kb / claim_history are optional read-only adapters — their
        # absence is a valid (fail-closed-routed) configuration, not an error.
        pass

    def register_nodes(self) -> None:
        # No super() call — BaseGraph.register_nodes() is abstract.
        self._nodes["evidence_mapping"] = EvidenceMappingNode(policy_kb=self._policy_kb)
        self._nodes["consistency_validation"] = ConsistencyValidationNode(claim_history=self._claim_history)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "evidence_mapping")
        self._sg.add_edge("evidence_mapping", "consistency_validation")
        self._sg.add_edge("consistency_validation", END)

    def route(self, state: AgentState) -> str:
        """Required by BaseGraph ABC. Linear topology — never actually called
        (no add_conditional_edges() in add_edges())."""
        return END if state.get("status") == AgentStatus.ERROR.value else "consistency_validation"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        """Shape sub_result for EvidenceValidationGraphNode.merge_output()."""
        return {
            "status": state.get("status"),
            "evidence_map": state.get("evidence_map"),
            "missing_evidence": state.get("missing_evidence"),
            "consistency_findings": state.get("consistency_findings"),
            "exception_evidence_present": state.get("exception_evidence_present"),
            "validation_confidence": state.get("validation_confidence"),
            "error_log": state.get("error_log", []),
        }
