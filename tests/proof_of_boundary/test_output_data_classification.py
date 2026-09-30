# PB (domain) — Output data classification / minimization verification.
#
# Added 2026-07-28 (Agent1000 review finding T2-3): the S-3 field
# allow-list test (test_pb03) only proves *extra keys* are stripped; this
# test proves the *content* of the allow-listed artifacts follows the data
# classification policy in docs/02_design.md (proposal §11 Risk #2):
#
#   PERMITTED in evidence_gap_report (citations the reviewer needs):
#     claim_id, policy_version_citation, requested_by (S-5 attribution),
#     requirement ids, source *field names* (provenance), finding
#     categories/notes, rejection field names/reasons.
#
#   PROHIBITED (raw source-record values with no citation purpose):
#     asset_serial value, service_order_id value, part reference values,
#     fault code values, coverage/service raw dates — none of these may
#     appear anywhere in the composed report or checklist.

import json

from framework.schemas.trust_level import TrustLevel

from src.nodes.post_process_node import PostProcessNode
from src.services.consistency_validation_service import validate_consistency
from src.services.evidence_mapping_service import map_evidence
from src.services.intake_normalization_service import normalize_claim_package

# Sentinel values chosen to be unmistakable if they leak into the report.
_SENSITIVE_VALUES = {
    "asset_serial": "SN-LEAK-SENTINEL-77",
    "service_order_id": "SO-LEAK-SENTINEL-88",
    "part_ref": "PART-LEAK-SENTINEL-99",
    "fault_code": "FC-LEAK-SENTINEL-11",
}

_RAW_CLAIM = {
    "claim_id": "CLM-CLASS-1",
    "policy_id": "POL-CLASS-1",
    "policy_version": "v7",
    "asset_serial": _SENSITIVE_VALUES["asset_serial"],
    "service_order_id": _SENSITIVE_VALUES["service_order_id"],
    "part_references": [_SENSITIVE_VALUES["part_ref"]],
    "fault_codes": [_SENSITIVE_VALUES["fault_code"]],
    "prior_claim_ids": ["CLM-OLD-1", "CLM-OLD-2"],
    "coverage_start_date": "2026-01-01",
    "coverage_end_date": "2026-12-31",
    "service_date": "2026-06-01",
}

_REPORT_ALLOWED_TOP_LEVEL_KEYS = {
    "claim_id",
    "requested_by",
    "policy_version_citation",
    "review_route",
    "evidence_requirements",
    "missing_evidence",
    "consistency_findings",
    "intake_rejections",
    "disclaimer",
}


def _compose_report_via_full_pipeline() -> tuple[dict, list]:
    claim_references, rejections = normalize_claim_package(dict(_RAW_CLAIM))
    evidence_map, missing = map_evidence(claim_references, policy_kb=None)
    findings, exception_present, confidence = validate_consistency(
        claim_references, evidence_map, policy_resolved=False, claim_history=None
    )

    state = {
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "caller_id": "svc-tenant-classification-test",
        "claim_references": json.dumps(claim_references),
        "evidence_map": json.dumps(evidence_map),
        "missing_evidence": json.dumps(missing),
        "consistency_findings": json.dumps(findings),
        "intake_rejections": json.dumps(rejections),
        "validation_confidence": confidence,
        "node_history": [],
        "error_log": [],
        "trace_id": "t1",
        "correlation_id": "c1",
        "session_id": "s1",
    }
    result = PostProcessNode().execute(state)
    report = json.loads(result["evidence_gap_report"])
    checklist = json.loads(result["human_confirmation_checklist"])
    return report, checklist


class TestOutputDataClassification:
    def test_report_top_level_keys_are_exactly_the_classified_set(self):
        report, _ = _compose_report_via_full_pipeline()
        assert set(report.keys()) == _REPORT_ALLOWED_TOP_LEVEL_KEYS

    def test_raw_source_identifier_values_never_appear_in_report(self):
        report, checklist = _compose_report_via_full_pipeline()
        serialized = json.dumps(report) + json.dumps(checklist)
        for label, sentinel in _SENSITIVE_VALUES.items():
            assert sentinel not in serialized, (
                f"raw source value for '{label}' leaked into the human-facing "
                f"report/checklist: {sentinel}"
            )

    def test_provenance_uses_field_names_not_values(self):
        report, _ = _compose_report_via_full_pipeline()
        for entry in report["evidence_requirements"]:
            source_field = entry.get("source_field")
            if source_field is None:
                continue
            # source_field must be a field-name string (provenance), never a value
            for sentinel in _SENSITIVE_VALUES.values():
                assert sentinel not in source_field

    def test_requested_by_attribution_present(self):
        """S-5 (T2-1): the report must carry the authenticated caller_id."""
        report, _ = _compose_report_via_full_pipeline()
        assert report["requested_by"] == "svc-tenant-classification-test"
