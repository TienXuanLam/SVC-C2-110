# PB-2 + PB-5: State Safety Verification
# Verifies that State contains only msgpack-safe types (no Pydantic, dataclass, JWT)

import ast
import json
import os
import re



CREDENTIAL_FIELD_PATTERNS = re.compile(
    r"(jwt|token|api_key|secret|password|credential|connection_string)", re.IGNORECASE
)

PROHIBITED_TYPE_ANNOTATIONS = [
    "BaseModel",
    "InvocationContext",
]


def _scan_state_file(filepath: str) -> list[str]:
    """Scan a state definition file for safety violations."""
    with open(filepath, "r") as f:
        source = f.read()
        tree = ast.parse(source, filename=filepath)

    violations = []

    for node in ast.walk(tree):
        # Check class definitions that look like State
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id

                    # Check for credential-like field names
                    if CREDENTIAL_FIELD_PATTERNS.search(field_name):
                        violations.append(
                            f"{filepath}:{item.lineno} — Credential-like field name: {field_name}"
                        )

                    # Check for prohibited type annotations
                    if item.annotation:
                        annotation_str = ast.dump(item.annotation)
                        for prohibited in PROHIBITED_TYPE_ANNOTATIONS:
                            if prohibited in annotation_str:
                                violations.append(
                                    f"{filepath}:{item.lineno} — Prohibited type in State: {prohibited}"
                                )

    return violations


class TestStateSafety:
    """PB-2/PB-5: State must be msgpack-safe with no credentials."""

    def test_state_file_safety(self):
        """State definition must not contain credential fields or prohibited types."""
        state_file = os.path.join(os.path.dirname(__file__), "..", "..", "src", "schemas", "state.py")
        # Fixed 2026-07-28 (T2-2): a missing state.py is a hard repository
        # defect for this template, not a reason to silently pass PB-5 —
        # the prior pytest.skip() let a broken/missing scaffold path go
        # unnoticed instead of failing the gate.
        assert os.path.exists(state_file), f"required state file missing: {state_file}"

        violations = _scan_state_file(state_file)

        assert violations == [], (
            "State safety violations found:\n" + "\n".join(violations)
        )

    def test_runtime_checkpoint_state_is_msgpack_serializable(self):
        """PB-5: a real post-invoke State dict must actually pack with the
        framework's checkpoint serializer (ormsgpack — the real dependency
        LangGraph checkpointing uses; verified installed, not the generic
        'msgpack' package name), not just pass a static AST scan.

        Fixed 2026-07-28 (T2-2): the prior test only performed a static
        field-name/type-annotation scan and never attempted to actually
        serialize a runtime state dict.
        """
        import ormsgpack

        from src.nodes.consistency_validation_node import ConsistencyValidationNode
        from src.nodes.evidence_mapping_node import EvidenceMappingNode
        from src.nodes.post_process_node import PostProcessNode
        from src.nodes.pre_process_node import PreProcessNode
        from framework.schemas.trust_level import TrustLevel

        claim = {
            "claim_id": "CLM-1",
            "policy_id": "POL-1",
            "policy_version": "v1",
            "asset_serial": "SN-1",
            "service_order_id": "SO-1",
            "coverage_start_date": "2026-01-01",
            "coverage_end_date": "2026-12-31",
            "service_date": "2026-06-01",
        }
        state = {
            "user_input": json.dumps(claim),
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "caller_id": "svc-tenant-001",
            "node_history": [],
            "error_log": [],
            "trace_id": "t1",
            "correlation_id": "c1",
            "session_id": "s1",
        }

        pre_result = PreProcessNode().execute(state)
        state.update(pre_result)

        mapping_result = EvidenceMappingNode().execute(state)
        state.update(mapping_result)

        consistency_result = ConsistencyValidationNode().execute(state)
        state.update(consistency_result)

        post_result = PostProcessNode().execute(state)
        state.update(post_result)

        # The actual PB-5 assertion: the accumulated runtime state (what a
        # real LangGraph checkpoint would persist) must pack without error.
        packed = ormsgpack.packb(state)
        assert isinstance(packed, bytes)
        assert len(packed) > 0
