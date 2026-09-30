# SVC-C2-110 — Unit Tests: evidence_mapping_service (pure Python, no framework import)

import inspect

from src.services.evidence_mapping_service import BASELINE_REQUIREMENTS, map_evidence


def _complete_claim_references() -> dict:
    return {
        "asset_serial": "ASSET-0001",
        "coverage_start_date": "2026-01-01",
        "coverage_end_date": "2026-12-31",
        "service_order_id": "SO-1000",
        "service_date": "2026-03-15",
        "part_references": ["PN-200"],
        "fault_codes": ["F-100"],
        "exception_policy_ref": None,
        "policy_version": "2026.1",
    }


def test_all_requirements_present_when_evidence_complete():
    evidence_map, missing = map_evidence(_complete_claim_references(), policy_kb=None)
    assert missing == ["exception_evidence"]  # exception_policy_ref is None
    assert evidence_map["asset_coverage"]["present"] is True
    assert evidence_map["service_evidence"]["present"] is True


def test_missing_parts_and_fault_codes_reported():
    claim = _complete_claim_references()
    claim["part_references"] = []
    claim["fault_codes"] = []
    evidence_map, missing = map_evidence(claim, policy_kb=None)
    assert "parts_reference" in missing
    assert "fault_code_evidence" in missing


def test_uses_baseline_requirements_when_no_policy_kb():
    evidence_map, _ = map_evidence(_complete_claim_references(), policy_kb=None)
    assert set(evidence_map.keys()) == set(BASELINE_REQUIREMENTS)


def test_policy_kb_narrows_requirement_set():
    class FakePolicyKb:
        def resolve_policy_version(self, policy_version):
            return {"requirements": ["asset_coverage", "service_evidence"]}

    evidence_map, missing = map_evidence(_complete_claim_references(), policy_kb=FakePolicyKb())
    assert set(evidence_map.keys()) == {"asset_coverage", "service_evidence"}
    assert missing == []


def test_unresolvable_policy_version_falls_back_to_baseline():
    class UnresolvingPolicyKb:
        def resolve_policy_version(self, policy_version):
            return None

    evidence_map, _ = map_evidence(_complete_claim_references(), policy_kb=UnresolvingPolicyKb())
    assert set(evidence_map.keys()) == set(BASELINE_REQUIREMENTS)
    assert all(detail["policy_resolved"] is False for detail in evidence_map.values())


def test_never_mutates_input_claim_references():
    claim = _complete_claim_references()
    original = dict(claim)
    map_evidence(claim, policy_kb=None)
    assert claim == original


def test_deterministic_no_llm_parameter():
    assert "llm" not in inspect.signature(map_evidence).parameters
