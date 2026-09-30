# SVC-C2-110 — Unit Tests: EvidenceMappingNode (inner graph, Step 2)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.evidence_mapping_node import EvidenceMappingNode


class _ResolvingPolicyKB:
    def resolve_policy_version(self, policy_version):
        return {"requirements": ["asset_coverage", "service_evidence"]}


class _UnresolvingPolicyKB:
    def resolve_policy_version(self, policy_version):
        return None


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


def _state_with(claim: dict) -> dict:
    # Inner-graph channel: the outer GraphNode serializes claim_references
    # as the inner graph's user_input (see EvidenceValidationGraphNode).
    return {"user_input": json.dumps(claim), "node_history": [], "error_log": []}


class TestEvidenceMappingNode:
    def test_success_path_maps_complete_evidence(self):
        node = EvidenceMappingNode(policy_kb=_ResolvingPolicyKB())
        result = node.execute(_state_with(_valid_claim_references()))
        assert result["status"] == AgentStatus.SUCCESS.value
        evidence_map = json.loads(result["evidence_map"])
        assert evidence_map["asset_coverage"]["present"] is True
        assert result["policy_resolved"] is True

    def test_no_policy_kb_is_fail_closed_not_resolved(self):
        """T1-2 (Agent1000 R1 BLOCKER): a missing/unconfigured policy_kb
        must produce policy_resolved=False — never be treated as resolved."""
        node = EvidenceMappingNode(policy_kb=None)
        result = node.execute(_state_with(_valid_claim_references()))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["policy_resolved"] is False

    def test_unresolvable_policy_version_is_not_resolved(self):
        node = EvidenceMappingNode(policy_kb=_UnresolvingPolicyKB())
        result = node.execute(_state_with(_valid_claim_references()))
        assert result["policy_resolved"] is False

    def test_missing_evidence_reported(self):
        claim = _valid_claim_references()
        claim["part_references"] = []
        claim["fault_codes"] = []
        node = EvidenceMappingNode()
        result = node.execute(_state_with(claim))
        missing = json.loads(result["missing_evidence"])
        assert "parts_reference" in missing
        assert "fault_code_evidence" in missing

    def test_claim_references_reexposed_for_next_inner_node(self):
        node = EvidenceMappingNode()
        claim = _valid_claim_references()
        result = node.execute(_state_with(claim))
        assert json.loads(result["claim_references"])["claim_id"] == claim["claim_id"]

    def test_malformed_manifest_returns_error(self):
        node = EvidenceMappingNode()
        result = node.execute({"user_input": "not json", "node_history": [], "error_log": []})
        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_required_trust_level_declared_explicitly(self):
        assert EvidenceMappingNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_no_llm_parameter_anywhere(self):
        from src.services import evidence_mapping_service

        assert "llm" not in inspect.signature(evidence_mapping_service.map_evidence).parameters
        assert "llm" not in inspect.signature(EvidenceMappingNode.__init__).parameters
