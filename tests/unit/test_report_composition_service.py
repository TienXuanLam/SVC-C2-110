# SVC-C2-110 — Unit Tests: report_composition_service (pure Python, no framework import)

import inspect

from src.services.report_composition_service import (
    ROUTE_MANUAL_EXCEPTION_REVIEW,
    ROUTE_READY_FOR_REVIEW,
    compose_evidence_gap_report,
    compose_human_confirmation_checklist,
    decide_review_route,
)


def test_decide_review_route_only_two_possible_values():
    cases = [
        ("pass", [], []),
        ("gap", [], []),
        ("needs_human_confirmation", [], []),
        ("pass", [{"category": "x", "note": "y"}], []),
        ("pass", [], [{"field": "a", "reason": "b"}]),
    ]
    for confidence, findings, rejections in cases:
        route = decide_review_route(confidence, findings, rejections)
        assert route in (ROUTE_READY_FOR_REVIEW, ROUTE_MANUAL_EXCEPTION_REVIEW)


def test_pass_confidence_no_findings_no_rejections_routes_ready():
    assert decide_review_route("pass", [], []) == ROUTE_READY_FOR_REVIEW


def test_gap_confidence_routes_manual_exception_review():
    assert decide_review_route("gap", [], []) == ROUTE_MANUAL_EXCEPTION_REVIEW


def test_intake_rejections_always_force_manual_exception_review():
    assert (
        decide_review_route("pass", [], [{"field": "x", "reason": "y"}])
        == ROUTE_MANUAL_EXCEPTION_REVIEW
    )


def test_evidence_gap_report_has_disclaimer_and_no_decisional_language():
    report = compose_evidence_gap_report(
        claim_id="CLM-0001",
        policy_version="2026.1",
        evidence_map={},
        missing_evidence=[],
        consistency_findings=[],
        intake_rejections=[],
        review_route=ROUTE_READY_FOR_REVIEW,
    )
    assert "disclaimer" in report
    disclaimer_lower = report["disclaimer"].lower()
    for forbidden in ("approve", "reject", "pay", "submit"):
        assert f"does not {forbidden}" in disclaimer_lower or forbidden not in disclaimer_lower.replace(
            "does not approve, reject, pay, submit", ""
        )


def test_human_confirmation_checklist_non_empty_and_mentions_human_authority():
    checklist = compose_human_confirmation_checklist(ROUTE_READY_FOR_REVIEW)
    assert len(checklist) >= 3
    assert any("has not approved" in item.lower() for item in checklist)


def test_manual_exception_review_checklist_has_extra_item():
    ready_checklist = compose_human_confirmation_checklist(ROUTE_READY_FOR_REVIEW)
    exception_checklist = compose_human_confirmation_checklist(ROUTE_MANUAL_EXCEPTION_REVIEW)
    assert len(exception_checklist) > len(ready_checklist)


def test_deterministic_no_llm_parameter():
    assert "llm" not in inspect.signature(decide_review_route).parameters
    assert "llm" not in inspect.signature(compose_evidence_gap_report).parameters
    assert "llm" not in inspect.signature(compose_human_confirmation_checklist).parameters
