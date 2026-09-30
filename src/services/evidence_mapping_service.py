"""AgentCore Platform v1.0"""

# Service layer — Step 2 (Checklist-to-evidence mapping) support for
# WarrantyClaimEvidenceValidatorAgent. Pure Python; no framework imports.
#
# Deterministic only (docs/02_design.md Design Decision Record) — signature
# never takes an `llm` parameter. A PB test asserts this via
# inspect.signature().

from __future__ import annotations

from typing import Any, Protocol

# The fixed policy-checklist requirement categories this template validates,
# per proposal §4 Step 2. A real deployment's policy_kb resolves the
# requirement set for a given policy_version; this default set is the
# minimum baseline used when the KB does not narrow it further.
BASELINE_REQUIREMENTS = (
    "asset_coverage",
    "service_evidence",
    "parts_reference",
    "fault_code_evidence",
    "exception_evidence",
)


class PolicyKnowledgeBase(Protocol):
    """Read-only policy/checklist lookup adapter — injected, never constructed
    inside a node. A real implementation resolves a policy_version to its
    requirement set and citation metadata; unresolvable/stale versions must
    return None (fail-closed, see consistency_validation_service).
    """

    def resolve_policy_version(self, policy_version: str) -> dict[str, Any] | None: ...


def map_evidence(
    claim_references: dict[str, Any], policy_kb: PolicyKnowledgeBase | None
) -> tuple[dict[str, Any], list[str]]:
    """Map each policy/checklist requirement to available evidence.

    Returns (evidence_map, missing_evidence) where evidence_map is
    {requirement: {"present": bool, "source_field": str | None}} with
    provenance, and missing_evidence is the list of requirement ids with no
    matching evidence found. Never mutates a source system (read-only).
    """
    policy_record = None
    if policy_kb is not None:
        policy_version = claim_references.get("policy_version")
        if policy_version:
            policy_record = policy_kb.resolve_policy_version(policy_version)

    requirements = (
        policy_record["requirements"] if policy_record and policy_record.get("requirements") else BASELINE_REQUIREMENTS
    )

    evidence_map: dict[str, Any] = {}
    missing: list[str] = []

    checks = {
        "asset_coverage": bool(claim_references.get("asset_serial"))
        and bool(claim_references.get("coverage_start_date"))
        and bool(claim_references.get("coverage_end_date")),
        "service_evidence": bool(claim_references.get("service_order_id"))
        and bool(claim_references.get("service_date")),
        "parts_reference": bool(claim_references.get("part_references")),
        "fault_code_evidence": bool(claim_references.get("fault_codes")),
        "exception_evidence": bool(claim_references.get("exception_policy_ref")),
    }

    for requirement in requirements:
        present = checks.get(requirement, False)
        evidence_map[requirement] = {
            "present": present,
            "source_field": _source_field_for(requirement) if present else None,
            "policy_version": claim_references.get("policy_version"),
            "policy_resolved": policy_record is not None,
        }
        if not present:
            missing.append(requirement)

    return evidence_map, missing


def _source_field_for(requirement: str) -> str:
    return {
        "asset_coverage": "asset_serial+coverage_start_date+coverage_end_date",
        "service_evidence": "service_order_id+service_date",
        "parts_reference": "part_references",
        "fault_code_evidence": "fault_codes",
        "exception_evidence": "exception_policy_ref",
    }.get(requirement, "unknown")
