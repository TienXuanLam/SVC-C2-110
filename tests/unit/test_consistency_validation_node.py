# SVC-C2-110 — Unit Tests: ConsistencyValidationNode (inner graph, Step 3)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.consistency_validation_node import ConsistencyValidationNode


class _RaisingClaimHistory:
    def has_open_or_recent_claim(self, asset_serial, exclude_claim_id):
        raise ConnectionError("claim-history connector down")


class _PositiveClaimHistory:
    def has_open_or_recent_claim(self, asset_serial, exclude_claim_id):
        return True


def _valid_claim_references() -> dict:
    return {
        "claim_id": "CLM-0001",
        "policy_id": "POL-100",
        "policy_version": "2026.1",
        "asset_serial": "ASSET-0001",
        "service_order_id": "SO-1000",
        "service_date": "2026-03-15",
        "coverage_start_date": "2026-01-01",
        "coverage_end_date": "2026-12-31",
        "fault_codes": ["F-100"],
        "part_references": ["PN-200"],
        "prior_claim_ids": [],
        "exception_policy_ref": None,
    }


def _complete_evidence_map() -> dict:
    return {
        "asset_coverage": {"present": True, "source_field": "asset_serial+coverage_start_date+coverage_end_date"},
        "service_evidence": {"present": True, "source_field": "service_order_id+service_date"},
        "parts_reference": {"present": True, "source_field": "part_references"},
        "fault_code_evidence": {"present": True, "source_field": "fault_codes"},
        "exception_evidence": {"present": False, "source_field": None},
    }


def _state(claim=None, evidence_map=None, policy_resolved=True) -> dict:
    return {
        "claim_references": json.dumps(claim or _valid_claim_references()),
        "evidence_map": json.dumps(evidence_map or _complete_evidence_map()),
        "policy_resolved": policy_resolved,
        "node_history": [],
        "error_log": [],
    }


class TestConsistencyValidationNode:
    def test_success_path_with_resolved_policy(self):
        node = ConsistencyValidationNode()
        result = node.execute(_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["validation_confidence"] == "pass"
        assert json.loads(result["consistency_findings"]) == []

    def test_unresolved_policy_routes_needs_human_confirmation(self):
        """T1-2: policy_resolved=False (including the no-KB case) must
        surface as an unresolved-policy finding and needs_human_confirmation."""
        node = ConsistencyValidationNode()
        result = node.execute(_state(policy_resolved=False))
        findings = json.loads(result["consistency_findings"])
        assert any(f["category"] == "policy_version_unresolved" for f in findings)
        assert result["validation_confidence"] == "needs_human_confirmation"

    def test_coverage_period_misalignment_is_a_finding_not_a_ruling(self):
        claim = _valid_claim_references()
        claim["service_date"] = "2027-01-01"  # outside coverage period
        node = ConsistencyValidationNode()
        result = node.execute(_state(claim=claim))
        findings = json.loads(result["consistency_findings"])
        assert any(f["category"] == "coverage_period_gap" for f in findings)
        assert result["validation_confidence"] == "gap"

    def test_duplicate_claim_indicator_is_review_signal_only(self):
        claim = _valid_claim_references()
        claim["prior_claim_ids"] = ["CLM-0000"]
        node = ConsistencyValidationNode()
        result = node.execute(_state(claim=claim))
        findings = json.loads(result["consistency_findings"])
        duplicate_findings = [f for f in findings if f["category"] == "duplicate_claim_indicator"]
        assert len(duplicate_findings) == 1
        assert "not a fraud finding" in duplicate_findings[0]["note"]

    def test_duplicate_note_does_not_embed_raw_asset_serial(self):
        """T2-3: finding notes must not leak raw source identifiers."""
        claim = _valid_claim_references()
        claim["prior_claim_ids"] = ["CLM-0000"]
        node = ConsistencyValidationNode(claim_history=_PositiveClaimHistory())
        result = node.execute(_state(claim=claim))
        assert claim["asset_serial"] not in result["consistency_findings"]

    def test_claim_history_adapter_failure_degrades_safely(self):
        """T1-3 (Agent1000 R1 HIGH): a connector outage must degrade to an
        unresolved finding + needs_human_confirmation, never raise."""
        node = ConsistencyValidationNode(claim_history=_RaisingClaimHistory())
        result = node.execute(_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        findings = json.loads(result["consistency_findings"])
        assert any(f["category"] == "duplicate_claim_check_unavailable" for f in findings)
        assert result["validation_confidence"] == "needs_human_confirmation"

    def test_malformed_upstream_state_returns_error(self):
        node = ConsistencyValidationNode()
        result = node.execute({"claim_references": "not json", "evidence_map": "{}", "node_history": [], "error_log": []})
        assert result["status"] == AgentStatus.ERROR.value

    def test_required_trust_level_declared_explicitly(self):
        assert ConsistencyValidationNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_no_llm_parameter_anywhere(self):
        from src.services import consistency_validation_service

        assert "llm" not in inspect.signature(consistency_validation_service.validate_consistency).parameters
        assert "llm" not in inspect.signature(ConsistencyValidationNode.__init__).parameters
