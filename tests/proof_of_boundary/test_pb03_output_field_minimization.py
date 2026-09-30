# PB-03: S-3 output field minimization on PostProcessNode
#
# Addresses proposal Risk #2 (customer/asset/technician/service/commercial
# data exposed through outputs). PostProcessNode._extra_security_gate_output
# must strip any field not on the explicit allow-list — this is
# belt-and-suspenders on top of the framework's default credential scan,
# which does not by itself prevent an over-broad but credential-free field
# from leaking (e.g. an accidental raw source-record echo).

from __future__ import annotations

from src.nodes.post_process_node import PostProcessNode


def test_unlisted_fields_are_stripped_from_output():
    node = PostProcessNode()
    result = {
        "review_route": "ready_for_human_warranty_review",
        "evidence_gap_report": "{}",
        "human_confirmation_checklist": "[]",
        "formatted_output": {},
        "status": "success",
        # Simulated leak candidates — must never survive the gate.
        "raw_claim_payload": {"customer_name": "should not leak"},
        "internal_debug_trace": "should not leak",
        "asset_owner_pii": "should not leak",
    }
    gated = node._extra_security_gate_output(result)
    assert "raw_claim_payload" not in gated
    assert "internal_debug_trace" not in gated
    assert "asset_owner_pii" not in gated


def test_allowed_fields_survive_the_gate():
    node = PostProcessNode()
    result = {
        "review_route": "manual_exception_review",
        "evidence_gap_report": "{}",
        "human_confirmation_checklist": "[]",
        "formatted_output": {},
        "status": "success",
        "error_log": [],
    }
    gated = node._extra_security_gate_output(result)
    assert gated == result


def test_gate_never_raises_on_arbitrary_extra_fields():
    node = PostProcessNode()
    result = {"status": "success", "anything": object()}
    gated = node._extra_security_gate_output(result)
    assert "anything" not in gated
    assert gated["status"] == "success"
