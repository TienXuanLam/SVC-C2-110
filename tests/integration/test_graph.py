# SVC-C2-110 — Integration Test: full graph (compile + invoke)
# Covers the Cat 2 outer/inner composition end-to-end (outer AgentBaseGraph
# backbone + EvidenceValidationGraphNode wrapping the inner
# EvidenceValidationWorkflowGraph).

import json

import pytest
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.graph.graph import WarrantyClaimEvidenceValidatorAgent


class _ResolvingPolicyKB:
    """Injected KB that resolves every version — the 'approved policy
    configured' deployment shape."""

    def resolve_policy_version(self, policy_version):
        return {
            "requirements": [
                "asset_coverage",
                "service_evidence",
                "parts_reference",
                "fault_code_evidence",
            ]
        }


def _valid_claim_payload() -> str:
    return json.dumps(
        {
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
    )


def _ctx(trust=TrustLevel.VERIFIED_EXTERNAL, caller_id="svc-tenant-itest"):
    return InvocationContext(caller_trust_level=trust, caller_id=caller_id)


@pytest.fixture
def agent():
    a = WarrantyClaimEvidenceValidatorAgent(
        config={"max_retry": 1, "policy_kb": _ResolvingPolicyKB()}
    )
    a.compile()
    return a


@pytest.fixture
def agent_without_policy_kb():
    a = WarrantyClaimEvidenceValidatorAgent(config={"max_retry": 1})
    a.compile()
    return a


@pytest.fixture
def secrets():
    return InMemoryProvider({})


def test_full_pipeline_clean_claim_routes_ready_for_review(agent, secrets):
    with bound_secrets(secrets):
        result = agent.invoke(_valid_claim_payload(), ctx=_ctx())

    assert result["status"] == "success"
    assert result["output"] is not None
    assert "PreProcessNode" in result["node_history"]
    assert "EvidenceValidationGraphNode" in result["node_history"]
    assert "PostProcessNode" in result["node_history"]
    assert result["output"]["review_route"] == "ready_for_human_warranty_review"


def test_full_pipeline_without_policy_kb_fails_closed(agent_without_policy_kb, secrets):
    """T1-2 (Agent1000 R1 BLOCKER): with no approved policy KB configured,
    even a complete claim must NOT reach ready_for_human_warranty_review —
    the unresolved policy dependency routes to manual_exception_review."""
    with bound_secrets(secrets):
        result = agent_without_policy_kb.invoke(_valid_claim_payload(), ctx=_ctx())

    assert result["status"] == "success"
    assert result["output"]["review_route"] == "manual_exception_review"


def test_full_pipeline_unauthorized_caller_is_blocked(agent, secrets):
    with bound_secrets(secrets):
        result = agent.invoke(
            _valid_claim_payload(), ctx=_ctx(trust=TrustLevel.ANONYMOUS)
        )

    assert result["status"] == "error"


def test_full_pipeline_missing_caller_id_is_blocked(agent, secrets):
    """T2-1 (S-5): an authorized-trust request with no caller identity is
    rejected fail-closed — tenant attribution is mandatory."""
    with bound_secrets(secrets):
        result = agent.invoke(_valid_claim_payload(), ctx=_ctx(caller_id=""))

    assert result["status"] == "error"


def test_full_pipeline_incomplete_claim_routes_manual_exception_review(agent, secrets):
    incomplete_payload = json.dumps({"claim_id": "CLM-0002"})
    with bound_secrets(secrets):
        result = agent.invoke(incomplete_payload, ctx=_ctx())

    assert result["status"] == "success"
    output = result["output"]
    assert output["review_route"] == "manual_exception_review"


def test_full_pipeline_report_carries_caller_attribution(agent, secrets):
    """T2-1 (S-5): the evidence-gap report is stamped with the caller_id."""
    with bound_secrets(secrets):
        result = agent.invoke(_valid_claim_payload(), ctx=_ctx())

    # AgentBaseGraph.get_output() surfaces state["formatted_output"] as
    # "output" — PostProcessNode sets formatted_output = evidence_gap_report
    # (the dict itself, not a further-nested JSON string).
    assert result["output"]["requested_by"] == "svc-tenant-itest"


def test_full_pipeline_never_produces_claim_action_language(agent, secrets):
    with bound_secrets(secrets):
        result = agent.invoke(_valid_claim_payload(), ctx=_ctx())

    output_text = json.dumps(result["output"]).lower()
    for forbidden in ("\"approved\"", "\"rejected\"", "\"paid\"", "ruling"):
        assert forbidden not in output_text
