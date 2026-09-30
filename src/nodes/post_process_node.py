"""AgentCore Platform v1.0"""

# Step 4 — Result composition and human handoff (docs/02_design.md).

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.report_composition_service import (
    compose_evidence_gap_report,
    compose_human_confirmation_checklist,
    decide_review_route,
)

# S-3 output allow-list — only these fields may leave this node. Belt-and-
# suspenders field minimization addressing proposal Risk #2, on top of the
# framework's default credential scan (docs/02_design.md Security Design).
_OUTPUT_ALLOWLIST = {
    "review_route",
    "evidence_gap_report",
    "human_confirmation_checklist",
    "formatted_output",
    "status",
    "error_log",
}


class PostProcessNode(FunctionNode):
    """Compose the evidence-gap report and decide the human review route."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3: strip any field not on the explicit allow-list before it can
        leave this node. May raise — but here we minimize instead of
        blocking, since over-broad (non-credential) fields are the risk,
        not a hard security violation requiring a raised error."""
        return {k: v for k, v in result.items() if k in _OUTPUT_ALLOWLIST}

    def execute(self, state: AgentState) -> dict[str, Any]:
        try:
            claim_references = json.loads(state.get("claim_references") or "{}")
            evidence_map = json.loads(state.get("evidence_map") or "{}")
            missing_evidence = json.loads(state.get("missing_evidence") or "[]")
            consistency_findings = json.loads(state.get("consistency_findings") or "[]")
            intake_rejections = json.loads(state.get("intake_rejections") or "[]")
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PostProcessNode: upstream JSON state field could not be parsed"],
            }

        validation_confidence = state.get("validation_confidence", "needs_human_confirmation")

        review_route = decide_review_route(validation_confidence, consistency_findings, intake_rejections)

        evidence_gap_report = compose_evidence_gap_report(
            claim_id=claim_references.get("claim_id"),
            policy_version=claim_references.get("policy_version"),
            evidence_map=evidence_map,
            missing_evidence=missing_evidence,
            consistency_findings=consistency_findings,
            intake_rejections=intake_rejections,
            review_route=review_route,
            caller_id=state.get("caller_id", ""),
        )
        human_confirmation_checklist = compose_human_confirmation_checklist(review_route)

        emit_trace_event(
            "evidence_gap_report_composed",
            {
                "caller_id": state.get("caller_id", ""),
                "review_route": review_route,
                "missing_evidence_count": len(missing_evidence),
                "consistency_finding_count": len(consistency_findings),
            },
            state,
        )

        return {
            "review_route": review_route,
            "evidence_gap_report": json.dumps(evidence_gap_report),
            "human_confirmation_checklist": json.dumps(human_confirmation_checklist),
            "formatted_output": evidence_gap_report,
            "status": AgentStatus.SUCCESS.value,
        }
