"""AgentCore Platform v1.0"""

# Service layer: domain queries, external API wrappers, data aggregation.
# Must NOT contain business logic that depends on framework/agenticstar
# imports, routing, or credentials. Pure Python only.
#
# Step 1 (Controlled intake and normalization) support for
# WarrantyClaimEvidenceValidatorAgent.
#
# All decisions here (which fields are required, what counts as malformed,
# duplicate-key ambiguity) are deterministic — never depend on an `llm`
# parameter (see docs/02_design.md Design Decision Record: "Deterministic
# vs LLM authority").

from __future__ import annotations

from typing import Any

# Requirement fields a claim package must present to be processable at all.
# Missing/blank -> a rejection notice, not a raised exception (fail-closed,
# but the pipeline continues to a manual_exception_review route rather than
# a hard error, per proposal Risk #4).
REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "policy_id",
    "policy_version",
    "asset_serial",
    "service_order_id",
)

# Hard ceiling on claim-package size to bound latency (proposal Risk #5).
MAX_CLAIM_PAYLOAD_FIELDS = 200


def normalize_claim_package(raw_claim: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Normalize identifiers in a raw claim package; report rejections.

    Never raises. Returns (claim_references, rejections) where rejections is
    a list of audit-safe {"field": ..., "reason": ...} notices for
    malformed, missing, or unsupported records. Deterministic — string
    normalization only (trim + uppercase for identifiers), no lookups.
    """
    rejections: list[dict[str, str]] = []

    if not isinstance(raw_claim, dict):
        return {}, [{"field": "claim_package", "reason": "payload is not a JSON object"}]

    if len(raw_claim) > MAX_CLAIM_PAYLOAD_FIELDS:
        return {}, [
            {
                "field": "claim_package",
                "reason": f"payload exceeds max field ceiling ({MAX_CLAIM_PAYLOAD_FIELDS})",
            }
        ]

    claim_references: dict[str, Any] = {}

    for field in REQUIRED_CLAIM_FIELDS:
        value = raw_claim.get(field)
        normalized = _normalize_identifier(value)
        if normalized is None:
            rejections.append({"field": field, "reason": "missing or malformed identifier"})
            continue
        claim_references[field] = normalized

    # Optional multi-valued evidence references — normalized if present,
    # never required (their absence is a mapping-time missing-evidence
    # finding in Step 2, not an intake rejection).
    for list_field in ("fault_codes", "part_references", "prior_claim_ids"):
        raw_values = raw_claim.get(list_field)
        if raw_values is None:
            claim_references[list_field] = []
            continue
        if not isinstance(raw_values, list):
            rejections.append({"field": list_field, "reason": "expected a list"})
            claim_references[list_field] = []
            continue
        normalized_list = [_normalize_identifier(v) for v in raw_values]
        claim_references[list_field] = [v for v in normalized_list if v is not None]

    exception_ref = raw_claim.get("exception_policy_ref")
    claim_references["exception_policy_ref"] = _normalize_identifier(exception_ref)

    coverage_start = raw_claim.get("coverage_start_date")
    coverage_end = raw_claim.get("coverage_end_date")
    service_date = raw_claim.get("service_date")
    claim_references["coverage_start_date"] = coverage_start if isinstance(coverage_start, str) else None
    claim_references["coverage_end_date"] = coverage_end if isinstance(coverage_end, str) else None
    claim_references["service_date"] = service_date if isinstance(service_date, str) else None

    if claim_references["coverage_start_date"] is None:
        rejections.append({"field": "coverage_start_date", "reason": "missing or malformed date"})
    if claim_references["coverage_end_date"] is None:
        rejections.append({"field": "coverage_end_date", "reason": "missing or malformed date"})
    if claim_references["service_date"] is None:
        rejections.append({"field": "service_date", "reason": "missing or malformed date"})

    return claim_references, rejections


def _normalize_identifier(value: Any) -> str | None:
    """Trim + uppercase a scalar identifier. Returns None if not usable."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed.upper()
