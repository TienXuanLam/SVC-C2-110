# SVC-C2-110 — Unit Tests: consistency_validation_service (pure Python, no framework import)
#
# Most important test module in this template — see docs/02_design.md
# Security Design (Risk #1 and #3 mitigation).

import inspect
from datetime import date

from src.services.consistency_validation_service import (
    CATEGORY_COVERAGE_GAP,
    CATEGORY_DUPLICATE_INDICATOR,
    CATEGORY_FAULT_PART_MISMATCH,
    CATEGORY_POLICY_UNRESOLVED,
    validate_consistency,
)


def _claim_references() -> dict:
    return {
        "asset_serial": "ASSET-0001",
        "claim_id": "CLM-0001",
        "coverage_start_date": "2026-01-01",
        "coverage_end_date": "2026-12-31",
        "service_date": "2026-03-15",
        "fault_codes": ["F-100"],
        "part_references": ["PN-200"],
        "prior_claim_ids": [],
        "exception_policy_ref": None,
    }


def _complete_evidence_map() -> dict:
    return {
        "asset_coverage": {"present": True},
        "service_evidence": {"present": True},
        "parts_reference": {"present": True},
        "fault_code_evidence": {"present": True},
        "exception_evidence": {"present": False},
    }


def test_pass_confidence_when_all_consistent():
    findings, exception_present, confidence = validate_consistency(
        _claim_references(),
        _complete_evidence_map(),
        policy_resolved=True,
        claim_history=None,
        today=date(2026, 6, 1),
    )
    assert findings == []
    assert exception_present is False
    assert confidence == "pass"


def test_coverage_period_misalignment_flagged_not_ruled():
    claim = _claim_references()
    claim["service_date"] = "2027-06-01"  # outside coverage
    findings, _, confidence = validate_consistency(
        claim, _complete_evidence_map(), policy_resolved=True, claim_history=None
    )
    categories = [f["category"] for f in findings]
    assert CATEGORY_COVERAGE_GAP in categories
    assert confidence == "gap"
    # Never a coverage/entitlement conclusion — only a category + note.
    for f in findings:
        assert set(f.keys()) == {"category", "note"}


def test_unresolved_policy_forces_needs_human_confirmation():
    findings, _, confidence = validate_consistency(
        _claim_references(), _complete_evidence_map(), policy_resolved=False, claim_history=None
    )
    assert any(f["category"] == CATEGORY_POLICY_UNRESOLVED for f in findings)
    assert confidence == "needs_human_confirmation"


def test_fault_code_part_mismatch_detected():
    claim = _claim_references()
    claim["fault_codes"] = []
    findings, _, _ = validate_consistency(
        claim, _complete_evidence_map(), policy_resolved=True, claim_history=None
    )
    assert any(f["category"] == CATEGORY_FAULT_PART_MISMATCH for f in findings)


def test_prior_claim_ids_produce_duplicate_indicator_review_signal():
    claim = _claim_references()
    claim["prior_claim_ids"] = ["CLM-0000", "CLM-9999"]
    findings, _, _ = validate_consistency(
        claim, _complete_evidence_map(), policy_resolved=True, claim_history=None
    )
    duplicate_findings = [f for f in findings if f["category"] == CATEGORY_DUPLICATE_INDICATOR]
    assert len(duplicate_findings) == 1
    assert "fraud" not in duplicate_findings[0]["note"].lower().split("review signal")[0]


def test_claim_history_lookup_adds_duplicate_indicator():
    class FakeHistory:
        def has_open_or_recent_claim(self, asset_serial, exclude_claim_id):
            return True

    findings, _, _ = validate_consistency(
        _claim_references(),
        _complete_evidence_map(),
        policy_resolved=True,
        claim_history=FakeHistory(),
    )
    assert any(f["category"] == CATEGORY_DUPLICATE_INDICATOR for f in findings)


def test_never_infers_exception_grant_or_coverage_entitlement():
    """Static assertion that no finding note contains decisional language."""
    claim = _claim_references()
    claim["exception_policy_ref"] = "EXC-001"
    findings, exception_present, _ = validate_consistency(
        claim, _complete_evidence_map(), policy_resolved=True, claim_history=None
    )
    assert exception_present is True  # presence only, never "granted"
    forbidden_terms = ("approved", "granted", "entitled", "covered", "denied")
    for f in findings:
        note_lower = f["note"].lower()
        for term in forbidden_terms:
            assert term not in note_lower


def test_deterministic_no_llm_parameter():
    assert "llm" not in inspect.signature(validate_consistency).parameters
