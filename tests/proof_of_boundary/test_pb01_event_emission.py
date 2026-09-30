# PB-1: BaseNode -> AuditLogger boundary verification
# Verifies emit_trace_event() actually fires from every node's execute()
# path, with no silent failures — the proof-of-boundary PB-1 contract.
#
# Added 2026-07-28 (review finding T2-2): docs/03_test_spec.md
# declared PB-1 as passing but no test file existed for it.

import json

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.consistency_validation_node import ConsistencyValidationNode
from src.nodes.evidence_mapping_node import EvidenceMappingNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode

_VALID_CLAIM = {
    "claim_id": "CLM-1",
    "policy_id": "POL-1",
    "policy_version": "v1",
    "asset_serial": "SN-1",
    "service_order_id": "SO-1",
    "coverage_start_date": "2026-01-01",
    "coverage_end_date": "2026-12-31",
    "service_date": "2026-06-01",
}


def _base_state(**overrides) -> dict:
    state = {
        "user_input": json.dumps(_VALID_CLAIM),
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "caller_id": "svc-tenant-001",
        "node_history": [],
        "error_log": [],
        "trace_id": "t1",
        "correlation_id": "c1",
        "session_id": "s1",
    }
    state.update(overrides)
    return state


@pytest.fixture
def spy_emit(monkeypatch):
    calls = []

    def _spy(event_type, payload, state):
        calls.append((event_type, payload))

    for module in (
        "src.nodes.pre_process_node",
        "src.nodes.evidence_mapping_node",
        "src.nodes.consistency_validation_node",
        "src.nodes.post_process_node",
    ):
        monkeypatch.setattr(f"{module}.emit_trace_event", _spy)
    return calls


class TestPB01EventEmission:
    def test_pre_process_emits_domain_event(self, spy_emit):
        node = PreProcessNode()
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert any(event == "claim_intake_normalized" for event, _ in spy_emit)

    def test_evidence_mapping_emits_domain_event(self, spy_emit):
        node = EvidenceMappingNode()
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert any(event == "evidence_mapping_completed" for event, _ in spy_emit)

    def test_consistency_validation_emits_domain_event(self, spy_emit):
        node = ConsistencyValidationNode()
        state = _base_state(
            claim_references=json.dumps(_VALID_CLAIM),
            evidence_map=json.dumps({}),
            policy_resolved=True,
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert any(event == "consistency_validation_completed" for event, _ in spy_emit)

    def test_post_process_emits_domain_event(self, spy_emit):
        node = PostProcessNode()
        state = _base_state(
            claim_references=json.dumps(_VALID_CLAIM),
            evidence_map=json.dumps({}),
            missing_evidence=json.dumps([]),
            consistency_findings=json.dumps([]),
            intake_rejections=json.dumps([]),
            validation_confidence="pass",
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert any(event == "evidence_gap_report_composed" for event, _ in spy_emit)

    def test_no_silent_failure_when_audit_logger_raises(self, monkeypatch):
        """A raising emit_trace_event must propagate, not be swallowed —
        'no silent failures' per the proof-of-boundary PB-1 contract."""

        def _raise(*args, **kwargs):
            raise RuntimeError("audit sink unavailable")

        monkeypatch.setattr("src.nodes.pre_process_node.emit_trace_event", _raise)
        node = PreProcessNode()
        with pytest.raises(RuntimeError):
            node.execute(_base_state())
