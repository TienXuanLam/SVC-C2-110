# SVC-C2-110 — Unit Tests: intake_normalization_service (pure Python, no framework import)

from src.services.intake_normalization_service import (
    MAX_CLAIM_PAYLOAD_FIELDS,
    normalize_claim_package,
)


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
        "fault_codes": ["f-100", " f-200 "],
        "part_references": ["pn-200"],
        "prior_claim_ids": [],
        "exception_policy_ref": None,
    }


def test_normalizes_and_uppercases_identifiers():
    claim_references, rejections = normalize_claim_package(_valid_raw_claim())
    assert claim_references["claim_id"] == "CLM-0001"
    assert claim_references["fault_codes"] == ["F-100", "F-200"]
    assert rejections == []


def test_missing_required_field_produces_rejection():
    raw = _valid_raw_claim()
    del raw["asset_serial"]
    claim_references, rejections = normalize_claim_package(raw)
    assert any(r["field"] == "asset_serial" for r in rejections)
    assert "asset_serial" not in claim_references


def test_non_dict_payload_is_rejected_safely():
    claim_references, rejections = normalize_claim_package("not a dict")  # type: ignore[arg-type]
    assert claim_references == {}
    assert len(rejections) == 1
    assert rejections[0]["field"] == "claim_package"


def test_oversized_payload_is_rejected():
    huge = {f"field_{i}": "x" for i in range(MAX_CLAIM_PAYLOAD_FIELDS + 1)}
    claim_references, rejections = normalize_claim_package(huge)
    assert claim_references == {}
    assert "ceiling" in rejections[0]["reason"]


def test_non_list_evidence_field_is_rejected_but_does_not_crash():
    raw = _valid_raw_claim()
    raw["fault_codes"] = "not-a-list"
    claim_references, rejections = normalize_claim_package(raw)
    assert claim_references["fault_codes"] == []
    assert any(r["field"] == "fault_codes" for r in rejections)


def test_never_raises_for_business_data_issues():
    """Deterministic fail-closed behaviour — malformed input never raises."""
    for bad_input in (None, 123, [], {}, {"claim_id": ""}):
        claim_references, rejections = normalize_claim_package(bad_input)  # type: ignore[arg-type]
        assert isinstance(claim_references, dict)
        assert isinstance(rejections, list)
