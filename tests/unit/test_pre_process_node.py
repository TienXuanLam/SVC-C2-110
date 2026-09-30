# SVC-C2-110 — Unit Tests: Pre-Process Node (Step 1: controlled intake and normalization)

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import PreProcessNode


def _valid_raw_claim() -> dict:
    return {
        "claim_id": " clm-0001 ",
        "policy_id": "pol-100",
        "policy_version": "2026.1",
        "asset_serial": "asset-0001",
        "service_order_id": "so-1000",
        "service_date": "2026-03-15",
        "coverage_start_date": "2026-01-01",
        "coverage_end_date": "2026-12-31",
        "fault_codes": ["f-100"],
        "part_references": ["pn-200"],
        "prior_claim_ids": [],
        "exception_policy_ref": None,
    }


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success_path_normalizes_claim(self):
        state = {
            "user_input": json.dumps(_valid_raw_claim()),
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        claim_references = json.loads(result["claim_references"])
        assert claim_references["claim_id"] == "CLM-0001"
        assert json.loads(result["intake_rejections"]) == []
        assert result["caller_authorized"] is True

    def test_missing_required_field_is_a_rejection_not_a_hard_error(self):
        raw = _valid_raw_claim()
        del raw["service_order_id"]
        state = {"user_input": json.dumps(raw), "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        rejections = json.loads(result["intake_rejections"])
        assert any(r["field"] == "service_order_id" for r in rejections)

    def test_malformed_json_returns_error(self):
        state = {"user_input": "{not valid json", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_empty_input_returns_error(self):
        state = {"user_input": "", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_required_trust_level_declared_explicitly(self):
        assert PreProcessNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_extra_security_gate_input_rejects_unauthorized_caller(self):
        state = {
            "user_input": json.dumps(_valid_raw_claim()),
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "node_history": [],
            "error_log": [],
        }
        gated_state = self.node._extra_security_gate_input(state)
        assert gated_state["status"] == AgentStatus.ERROR.value

    def test_extra_security_gate_input_does_not_raise(self):
        """S-2 contract: _extra_security_gate_input() must never raise."""
        state = {"caller_trust_level": "not-a-real-trust-level"}
        result = self.node._extra_security_gate_input(state)
        assert isinstance(result, dict)

    def test_extra_security_gate_input_allows_verified_external(self):
        state = {
            "user_input": json.dumps(_valid_raw_claim()),
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "caller_id": "svc-tenant-unit",
            "node_history": [],
            "error_log": [],
        }
        gated_state = self.node._extra_security_gate_input(state)
        assert gated_state.get("status") != AgentStatus.ERROR.value

    def test_extra_security_gate_input_rejects_missing_caller_id(self):
        """T2-1 (S-5): authorized trust without caller identity is rejected
        fail-closed — tenant attribution is mandatory."""
        state = {
            "user_input": json.dumps(_valid_raw_claim()),
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "caller_id": "",
            "node_history": [],
            "error_log": [],
        }
        gated_state = self.node._extra_security_gate_input(state)
        assert gated_state["status"] == AgentStatus.ERROR.value

    def test_extra_security_gate_input_rejects_malformed_json(self):
        """T1-4: structural payload validation genuinely runs in the S-2
        hook, not only later in execute()."""
        state = {
            "user_input": "{not valid json",
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "caller_id": "svc-tenant-unit",
            "node_history": [],
            "error_log": [],
        }
        gated_state = self.node._extra_security_gate_input(state)
        assert gated_state["status"] == AgentStatus.ERROR.value

    def test_extra_security_gate_input_rejects_non_object_json(self):
        state = {
            "user_input": json.dumps(["a", "list"]),
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "caller_id": "svc-tenant-unit",
            "node_history": [],
            "error_log": [],
        }
        gated_state = self.node._extra_security_gate_input(state)
        assert gated_state["status"] == AgentStatus.ERROR.value
