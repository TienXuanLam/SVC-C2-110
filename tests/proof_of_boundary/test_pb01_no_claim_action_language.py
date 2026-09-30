# PB-01: No claim-action / decisional language anywhere in src/
#
# SVC-C2-110 must never approve, reject, pay, submit, or negotiate a claim,
# or determine coverage/entitlement (proposal §3, §4 Notes, Risk #1/#3).
# Static AST/text scan of every string literal under src/ — a runtime test
# alone would only catch the code paths actually exercised; this catches
# accidental decisional language anywhere in the source, including strings
# that no test happens to reach.

from __future__ import annotations

import ast
import pathlib

FORBIDDEN_PHRASES = (
    "claim approved",
    "claim rejected",
    "claim denied",
    "payment approved",
    "payment authorized",
    "coverage confirmed",
    "coverage entitled",
    "entitlement granted",
    "exception granted",
    "exception approved",
)

# A small allow-list of substrings that legitimately mention these forbidden
# ideas only to explicitly disclaim them (e.g. "does not approve, reject,
# pay, submit"). Lines containing an allow-listed disclaimer phrase are
# exempt.
DISCLAIMER_MARKERS = (
    "does not",
    "never",
    "not a fraud",
    "not a ruling",
    "not approve",
)

SRC_ROOT = pathlib.Path(__file__).parents[2] / "src"


def _iter_string_literals():
    for py_file in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield py_file, node.lineno, node.value


def test_no_claim_action_language_in_source():
    violations = []
    for path, lineno, text in _iter_string_literals():
        lowered = text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                if any(marker in lowered for marker in DISCLAIMER_MARKERS):
                    continue
                violations.append(f"{path}:{lineno} — forbidden phrase '{phrase}': {text!r}")
    assert violations == [], "\n".join(violations)


def test_review_route_module_only_defines_two_outcomes():
    """Static confirmation that report_composition_service exposes exactly
    the two proposal-mandated route constants — no third "approved" branch
    can be silently added without this test failing."""
    from src.services import report_composition_service as svc

    route_constants = {
        name: value
        for name, value in vars(svc).items()
        if name.startswith("ROUTE_") and isinstance(value, str)
    }
    assert set(route_constants.values()) == {
        "ready_for_human_warranty_review",
        "manual_exception_review",
    }
