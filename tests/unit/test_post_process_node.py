# SVC-C2-110 — Unit Tests: Post-Process Node (Step 4: result composition and human handoff)

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.post_process_node import PostProcessNode


def _clean_state() -> dict:
    return {
        "claim_references": json.dumps({"claim_id": "CLM-0001", "policy_version": "2026.1"}),
        "evidence_map": json.dumps(
            {"asset_coverage": {"present": True, "source_field": "asset_serial"}}
        ),
        "missing_evidence": json.dumps([]),
        "consistency_findings": json.dumps([]),
        "intake_rejections": json.dumps([]),
        "validation_confidence": "pass",
        "node_history": [],
        "error_log": [],
    }


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_clean_claim_routes_ready_for_review(self):
        result = self.node.execute(_clean_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["review_route"] == "ready_for_human_warranty_review"

    def test_gap_confidence_routes_manual_exception_review(self):
        state = _clean_state()
        state["validation_confidence"] = "gap"
        result = self.node.execute(state)
        assert result["review_route"] == "manual_exception_review"

    def test_intake_rejections_force_manual_exception_review(self):
        state = _clean_state()
        state["intake_rejections"] = json.dumps([{"field": "service_order_id", "reason": "missing"}])
        result = self.node.execute(state)
        assert result["review_route"] == "manual_exception_review"

    def test_review_route_is_never_a_decisional_value(self):
        for state in (
            _clean_state(),
            {**_clean_state(), "validation_confidence": "gap"},
            {**_clean_state(), "validation_confidence": "needs_human_confirmation"},
        ):
            result = self.node.execute(state)
            assert result["review_route"] in (
                "ready_for_human_warranty_review",
                "manual_exception_review",
            )

    def test_evidence_gap_report_contains_disclaimer_and_no_decisional_language(self):
        result = self.node.execute(_clean_state())
        report = json.loads(result["evidence_gap_report"])
        assert "disclaimer" in report
        report_text = json.dumps(report).lower()
        for forbidden in ("approved", "rejected", "denied", "\"paid\"", "ruling"):
            assert forbidden not in report_text

    def test_human_confirmation_checklist_present(self):
        result = self.node.execute(_clean_state())
        checklist = json.loads(result["human_confirmation_checklist"])
        assert len(checklist) > 0
        assert any("has not approved" in item.lower() for item in checklist)

    def test_extra_security_gate_output_strips_unlisted_fields(self):
        result = self.node.execute(_clean_state())
        result["leaked_raw_source_payload"] = "should never survive the S-3 allow-list"
        gated = self.node._extra_security_gate_output(result)
        assert "leaked_raw_source_payload" not in gated
        assert "review_route" in gated

    def test_malformed_upstream_state_returns_error(self):
        state = _clean_state()
        state["evidence_map"] = "not json"
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_required_trust_level_declared_explicitly(self):
        assert PostProcessNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL
