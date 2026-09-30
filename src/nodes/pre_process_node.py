"""AgentCore Platform v1.0"""

# Node contract (agents_layer_design.md §1):
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes (never full state)
#  - Return AgentStatus.<X>.value strings for status assignments [A1]
#  - Read input_context via state.get("input_context", {}) — read-only [C1]
#  - Never import from mediator/, api/, or other agents
#
# Step 1 — Controlled intake and normalization (docs/02_design.md).

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.intake_normalization_service import normalize_claim_package


class PreProcessNode(FunctionNode):
    """Verify caller authorization and normalize the claim package."""

    # S-1 (framework trust-gate contract): claim/policy/service data requires
    # an authorized caller — explicit by design, not inherited implicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        """S-2: fail-closed authorization + minimal schema validation.
        Must not raise — reject via status=ERROR only (framework contract).

        T1-4 fix (Agent1000 review, 2026-07-28): docs/02_design.md and
        docs/03_test_spec.md both document this hook as performing "minimal
        schema validation" (structural: is the payload valid JSON, and is it
        a JSON object at all), but the prior implementation only checked
        caller trust here — JSON parsing ran later in execute(). That let
        the S-2 contract and the actual gate diverge. The structural check
        now runs here; field-level business validation (which named claim
        fields are present/well-formed) intentionally stays a rejection-list
        pattern in execute() via normalize_claim_package() — an incomplete
        claim is not a security violation, it is a valid business outcome
        that routes to manual_exception_review (proposal Risk #4), so it
        must not hard-block at the security gate.
        """
        trust_level = state.get("caller_trust_level")
        authorized = trust_level in (
            TrustLevel.VERIFIED_EXTERNAL.value,
            TrustLevel.INTERNAL.value,
            TrustLevel.VERIFIED_EXTERNAL,
            TrustLevel.INTERNAL,
        )
        if not authorized:
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = state.get("error_log", []) + [
                "PreProcessNode: caller is not authorized for warranty claim/policy/service data"
            ]
            return state

        # T2-1 fix (S-5 tenant isolation, review 2026-07-28): the
        # proposal identifies unresolved privacy/tenant-isolation
        # requirements (see proposal §10 row 5 / §12 Dependency 3). Every
        # request MUST carry a resolvable caller identity (`caller_id`,
        # set by the framework's InvocationContext -> initial_state, see
        # framework/graph/base_graph.py) so that every audit event and every
        # human-facing output artifact can be attributed to exactly one
        # authenticated tenant/reviewer scope. A VERIFIED_EXTERNAL/INTERNAL
        # caller with no caller_id is a configuration failure (an upstream
        # auth layer that authenticated trust but not identity) — fail
        # closed rather than process a claim with no attributable owner.
        if not str(state.get("caller_id", "")).strip():
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = state.get("error_log", []) + [
                "PreProcessNode: caller_id is required for tenant-scoped claim processing (S-5)"
            ]
            return state

        user_input = state.get("user_input", "")
        if not user_input or not str(user_input).strip():
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = state.get("error_log", []) + ["PreProcessNode: user_input is empty or missing"]
            return state

        try:
            parsed = json.loads(user_input)
        except (TypeError, ValueError):
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = state.get("error_log", []) + ["PreProcessNode: user_input is not valid JSON"]
            return state

        if not isinstance(parsed, dict):
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = state.get("error_log", []) + ["PreProcessNode: user_input JSON must be an object"]
            return state

        return state

    def execute(self, state: AgentState) -> dict[str, Any]:
        # If S-2 already rejected (auth failure, empty/malformed/non-object
        # JSON), __call__() short-circuits before execute() runs, so
        # reaching here implies an authorized caller with a structurally
        # valid claim-package object. Re-parse defensively — the S-2 hook
        # validates but does not persist the parsed value into state.
        user_input = state.get("user_input", "")
        try:
            raw_claim = json.loads(user_input)
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: user_input is not valid JSON"],
                "caller_authorized": True,
            }

        claim_references, rejections = normalize_claim_package(raw_claim)

        emit_trace_event(
            "claim_intake_normalized",
            {
                "caller_id": state.get("caller_id", ""),
                "rejection_count": len(rejections),
                "evidence_reference_count": len(claim_references),
            },
            state,
        )

        return {
            "claim_references": json.dumps(claim_references),
            "intake_rejections": json.dumps(rejections),
            "caller_authorized": True,
            "status": AgentStatus.SUCCESS.value,
        }
