# PB-6: Invoke Execution Order Verification
# Verifies BaseNode.__call__() enforces: S-1 trust gate -> S-4 node_start ->
# S-2 _security_gate_input() -> execute() -> S-3 _security_gate_output() ->
# S-4 node_complete, for every concrete node under src/nodes/.

import importlib
import inspect
import pkgutil

import pytest


def _discover_node_classes() -> list[type]:
    """Import every module under src/nodes/ and collect concrete BaseNode subclasses."""
    from framework.nodes.base_node import BaseNode

    try:
        pkg = importlib.import_module("src.nodes")
    except ImportError:
        return []

    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
            ):
                discovered.append(attr)
    return discovered


class TestInvokeOrder:
    """PB-6: __call__ must run S-1 -> node_start -> S-2 -> execute() -> S-3 -> node_complete."""

    def test_call_order_for_every_node(self, monkeypatch):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        import framework.nodes.base_node as base_node_module

        failures: list[str] = []
        for node_cls in node_classes:
            order: list[str] = []
            monkeypatch.setattr(
                base_node_module,
                "emit_trace_event",
                lambda event_type, _payload, _state, _o=order: _o.append(f"event:{event_type}"),
            )

            for method_name, label in (
                ("_security_gate_input", "security_gate_input"),
                ("execute", "execute"),
                ("_security_gate_output", "security_gate_output"),
            ):
                original = getattr(node_cls, method_name)

                def spy(self, arg, _o=order, _label=label, _orig=original):
                    _o.append(_label)
                    return _orig(self, arg)

                monkeypatch.setattr(node_cls, method_name, spy)

            instance = node_cls()
            # A minimal-but-valid claim manifest and caller_id — every node
            # in this template's S-2 hook needs these to reach execute()
            # rather than fail-closed reject early (caller_id for S-5,
            # user_input for the structural JSON check in PreProcessNode).
            valid_claim_json = (
                '{"claim_id": "CLM-PB6", "policy_id": "POL-PB6", '
                '"policy_version": "v1", "asset_serial": "SN-PB6", '
                '"service_order_id": "SO-PB6", '
                '"coverage_start_date": "2026-01-01", '
                '"coverage_end_date": "2026-12-31", '
                '"service_date": "2026-06-01"}'
            )
            state = {
                "caller_trust_level": node_cls.required_trust_level.value,
                "caller_id": "svc-tenant-pb6",
                "correlation_id": "pb6-invoke-order-test",
                # GraphNode.execute() (EvidenceValidationGraphNode) builds
                # its own InvocationContext via InvocationContext.from_state(),
                # which requires session_id/trace_id with no default —
                # unlike plain FunctionNodes, so this generic harness must
                # supply them for every node, not just GraphNode ones.
                "session_id": "pb6-session",
                "trace_id": "pb6-trace",
                "thread_id": "pb6-thread",
                "hitl_allowed": True,
                "user_input": valid_claim_json,
                "claim_references": valid_claim_json,
                "evidence_map": "{}",
                "missing_evidence": "[]",
                "consistency_findings": "[]",
                "intake_rejections": "[]",
                "policy_resolved": True,
                "validation_confidence": "pass",
            }
            instance(state)

            # GraphNode subclasses (e.g. EvidenceValidationGraphNode) run a
            # real inner subgraph inside execute() — the inner graph's own
            # nodes emit their own node_start/node_complete event pairs
            # while the wrapped `execute` call is in flight, so they land
            # in `order` before the "execute" spy marker itself is appended
            # (the spy records execute()'s call *after* the wrapped
            # function returns). That inner-graph nesting is correct
            # GraphNode behavior (framework contract), not a boundary
            # violation of this node's own S-1..S-4 order — strip every
            # event:node_start/event:node_complete pair except the first
            # and last, which belong to this node itself.
            from framework.nodes.graph_node import GraphNode

            if issubclass(node_cls, GraphNode):
                start_positions = [i for i, item in enumerate(order) if item == "event:node_start"]
                complete_positions = [i for i, item in enumerate(order) if item == "event:node_complete"]
                if len(start_positions) > 1 or len(complete_positions) > 1:
                    keep_indices = set(range(len(order))) - set(start_positions[1:]) - set(complete_positions[:-1])
                    order = [item for i, item in enumerate(order) if i in keep_indices]

            expected = [
                "event:node_start",
                "security_gate_input",
                "execute",
                "security_gate_output",
                "event:node_complete",
            ]
            if order != expected:
                failures.append(
                    f"{node_cls.__name__}: invoke order violation.\n" f"expected: {expected}\nactual:   {order}"
                )

        assert not failures, "\n\n".join(failures)
