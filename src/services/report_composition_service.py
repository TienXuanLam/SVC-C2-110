"""AgentCore Platform v1.0"""

# Service layer — Step 4 (Result composition and human handoff) support for
# WarrantyClaimEvidenceValidatorAgent. Pure Python; no framework imports.
#
# Deterministic only — the route decision and report text are templated
# from structured findings, never LLM-generated (docs/02_design.md Design
# Decision Record: "Deterministic vs LLM authority"). No signature here
# takes an `llm` parameter.
#
# The two possible outcomes are the ONLY values `decide_review_route()` may
# return — this is asserted by a PB test. Report text is checked by a PB
# test for forbidden decisional language ("approved", "rejected", "denied",
# "paid", "ruling").

from __future__ import annotations

from typing import Any

ROUTE_READY_FOR_REVIEW = "ready_for_human_warranty_review"
ROUTE_MANUAL_EXCEPTION_REVIEW = "manual_exception_review"

_GAP_CONFIDENCE_VALUES = {"gap", "needs_human_confirmation"}


def decide_review_route(
    validation_confidence: str,
    consistency_findings: list[dict[str, str]],
    intake_rejections: list[dict[str, str]],
) -> str:
    """Deterministic route decision. The ONLY two possible return values."""
    if intake_rejections:
        return ROUTE_MANUAL_EXCEPTION_REVIEW
    if validation_confidence in _GAP_CONFIDENCE_VALUES:
        return ROUTE_MANUAL_EXCEPTION_REVIEW
    if consistency_findings:
        return ROUTE_MANUAL_EXCEPTION_REVIEW
    return ROUTE_READY_FOR_REVIEW


def compose_evidence_gap_report(
    claim_id: str | None,
    policy_version: str | None,
    evidence_map: dict[str, Any],
    missing_evidence: list[str],
    consistency_findings: list[dict[str, str]],
    intake_rejections: list[dict[str, str]],
    review_route: str,
    caller_id: str = "",
) -> dict[str, Any]:
    """Build the structured, citation-backed evidence-gap report.

    This is the only human-facing artifact produced by this agent. It is
    strictly descriptive (evidence present/missing, findings, route) and
    never contains an approval/rejection/payment/coverage decision.

    T2-1 (S-5 tenant isolation, Agent1000 review 2026-07-28): every report
    is stamped with the authenticated caller_id that submitted the request,
    so downstream consumers/audit tooling can attribute and scope each
    report to exactly one tenant/reviewer context — this is not
    tenant-*enforcement* by itself (that is InvocationContext/S-1's job),
    it is the traceability half of S-5: no report can be mistaken for
    another tenant's data because the owning identity travels with it.
    """
    return {
        "claim_id": claim_id,
        "requested_by": caller_id,
        "policy_version_citation": policy_version,
        "review_route": review_route,
        "evidence_requirements": [
            {
                "requirement": requirement,
                "present": detail.get("present", False),
                "source_field": detail.get("source_field"),
            }
            for requirement, detail in evidence_map.items()
        ],
        "missing_evidence": list(missing_evidence),
        "consistency_findings": list(consistency_findings),
        "intake_rejections": list(intake_rejections),
        "disclaimer": (
            "This report is advisory and read-only. It identifies evidence "
            "gaps only. It does not approve, reject, pay, submit, or "
            "determine coverage or entitlement for this claim. All claim "
            "actions require an accountable human warranty reviewer."
        ),
    }


def compose_human_confirmation_checklist(review_route: str) -> list[str]:
    """Discrete confirmation items the accountable reviewer must check off
    before any claim action is taken elsewhere (outside this agent)."""
    checklist = [
        "Confirm the policy/checklist version cited matches the currently approved version.",
        "Confirm evidence gaps and consistency findings listed above are accurate against source records.",
        "This agent has not approved, rejected, paid, or submitted this claim — that decision remains with you.",
    ]
    if review_route == ROUTE_MANUAL_EXCEPTION_REVIEW:
        checklist.append(
            "This claim requires manual exception review — evaluate any exception-policy "
            "evidence and duplicate-claim indicators independently before proceeding."
        )
    return checklist
