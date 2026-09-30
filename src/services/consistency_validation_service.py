"""AgentCore Platform v1.0"""

# Service layer — Step 3 (Consistency and exception validation) support for
# WarrantyClaimEvidenceValidatorAgent. Pure Python; no framework imports.
#
# **Most important module in this template.** Every function here is
# deterministic (no `llm` parameter in any signature — enforced by a PB
# test via inspect.signature()). This module NEVER infers a coverage or
# exception entitlement — it only reports machine-checkable consistency
# findings and duplicate-claim *indicators* (review signals, never fraud
# determinations — proposal Risk #3).

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

# Finding categories — used by post_process to decide the human review
# route and by PB tests to assert no "ruling"/"approved"/"denied" language
# ever appears in a finding category or note.
CATEGORY_COVERAGE_GAP = "coverage_period_gap"
CATEGORY_SERVICE_INCOMPLETE = "service_evidence_incomplete"
CATEGORY_FAULT_PART_MISMATCH = "fault_code_part_reference_inconsistent"
CATEGORY_DUPLICATE_INDICATOR = "duplicate_claim_indicator"
CATEGORY_EXCEPTION_UNRESOLVED = "exception_policy_unresolved"
CATEGORY_POLICY_UNRESOLVED = "policy_version_unresolved"


class ClaimHistoryLookup(Protocol):
    """Read-only prior-claim lookup adapter — injected, never constructed
    inside a node."""

    def has_open_or_recent_claim(self, asset_serial: str, exclude_claim_id: str) -> bool: ...


def validate_consistency(
    claim_references: dict[str, Any],
    evidence_map: dict[str, Any],
    policy_resolved: bool,
    claim_history: ClaimHistoryLookup | None,
    *,
    today: date | None = None,
) -> tuple[list[dict[str, str]], bool, str]:
    """Run all deterministic consistency checks.

    Returns (findings, exception_evidence_present, validation_confidence).
    validation_confidence is one of "pass" | "gap" | "needs_human_confirmation".
    Never raises for a business-data reason — a check that cannot be
    completed produces a finding, not an exception.
    """
    findings: list[dict[str, str]] = []
    today = today or date.today()

    if not policy_resolved:
        findings.append(
            {
                "category": CATEGORY_POLICY_UNRESOLVED,
                "note": "policy_version could not be resolved against the policy knowledge base",
            }
        )

    # Serial and coverage-period alignment.
    coverage_start = _parse_date(claim_references.get("coverage_start_date"))
    coverage_end = _parse_date(claim_references.get("coverage_end_date"))
    service_date = _parse_date(claim_references.get("service_date"))
    if coverage_start and coverage_end and service_date:
        if not (coverage_start <= service_date <= coverage_end):
            findings.append(
                {
                    "category": CATEGORY_COVERAGE_GAP,
                    "note": "service_date falls outside the claimed coverage period",
                }
            )
    else:
        findings.append(
            {
                "category": CATEGORY_COVERAGE_GAP,
                "note": "coverage period or service date could not be parsed for alignment check",
            }
        )

    # Service-evidence completeness.
    if not evidence_map.get("service_evidence", {}).get("present"):
        findings.append(
            {
                "category": CATEGORY_SERVICE_INCOMPLETE,
                "note": "service_order_id/service_date evidence is missing",
            }
        )

    # Fault-code / part-reference consistency: a part reference without any
    # fault code (or vice versa) is a structural inconsistency, never a
    # parts-fit determination (out of scope per proposal §5).
    has_fault_codes = bool(claim_references.get("fault_codes"))
    has_parts = bool(claim_references.get("part_references"))
    if has_parts and not has_fault_codes:
        findings.append(
            {
                "category": CATEGORY_FAULT_PART_MISMATCH,
                "note": "part_references present without any linked fault_codes",
            }
        )

    # Duplicate-claim indicator — review signal only, never a fraud finding.
    exception_evidence_present = bool(claim_references.get("exception_policy_ref"))
    asset_serial = claim_references.get("asset_serial")
    claim_id = claim_references.get("claim_id", "")
    prior_claim_ids = claim_references.get("prior_claim_ids") or []
    # Data minimization (T2-3, Agent1000 review 2026-07-28): finding notes
    # must not embed raw source identifiers (asset serial) — the reviewer
    # already has the claim context via the report's claim_id citation, so
    # the note only needs the signal, not the identifier value.
    if asset_serial and prior_claim_ids:
        findings.append(
            {
                "category": CATEGORY_DUPLICATE_INDICATOR,
                "note": (
                    f"the claimed asset has {len(prior_claim_ids)} prior claim "
                    "reference(s) on record — review signal only, not a fraud finding"
                ),
            }
        )
    if (
        asset_serial
        and claim_history is not None
        and claim_history.has_open_or_recent_claim(asset_serial, exclude_claim_id=claim_id)
    ):
        findings.append(
            {
                "category": CATEGORY_DUPLICATE_INDICATOR,
                "note": "the claimed asset has an open or recent claim on record",
            }
        )

    if exception_evidence_present and not evidence_map.get("exception_evidence", {}).get("present"):
        findings.append(
            {
                "category": CATEGORY_EXCEPTION_UNRESOLVED,
                "note": "exception_policy_ref present but evidence mapping could not confirm it",
            }
        )

    validation_confidence = _confidence_from_findings(findings)
    return findings, exception_evidence_present, validation_confidence


def _confidence_from_findings(findings: list[dict[str, str]]) -> str:
    if not findings:
        return "pass"
    unresolved_categories = {CATEGORY_POLICY_UNRESOLVED, CATEGORY_EXCEPTION_UNRESOLVED}
    if any(f["category"] in unresolved_categories for f in findings):
        return "needs_human_confirmation"
    return "gap"


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
