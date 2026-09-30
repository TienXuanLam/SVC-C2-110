# PB-02: Deterministic-vs-LLM authority boundary (docs/02_design.md Design
# Decision Record). Every domain decision function (evidence mapping,
# consistency validation, route decision) must be inspectable as taking no
# `llm` parameter — this template introduces no LLM dependency at all.

from __future__ import annotations

import inspect

from src.nodes.consistency_validation_node import ConsistencyValidationNode
from src.nodes.evidence_mapping_node import EvidenceMappingNode
from src.nodes.evidence_validation_graph_node import EvidenceValidationGraphNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.services import (
    consistency_validation_service,
    evidence_mapping_service,
    intake_normalization_service,
    report_composition_service,
)

DOMAIN_DECISION_CALLABLES = (
    intake_normalization_service.normalize_claim_package,
    evidence_mapping_service.map_evidence,
    consistency_validation_service.validate_consistency,
    report_composition_service.decide_review_route,
    report_composition_service.compose_evidence_gap_report,
    report_composition_service.compose_human_confirmation_checklist,
)


def test_no_domain_decision_function_accepts_llm_parameter():
    violations = []
    for fn in DOMAIN_DECISION_CALLABLES:
        params = inspect.signature(fn).parameters
        if "llm" in params:
            violations.append(f"{fn.__module__}.{fn.__qualname__} accepts an 'llm' parameter")
    assert violations == [], "\n".join(violations)


def test_no_node_constructor_accepts_llm_parameter():
    for node_cls in (
        PreProcessNode,
        EvidenceValidationGraphNode,
        EvidenceMappingNode,
        ConsistencyValidationNode,
        PostProcessNode,
    ):
        params = inspect.signature(node_cls.__init__).parameters
        assert "llm" not in params, f"{node_cls.__name__}.__init__ accepts an 'llm' parameter"


def test_no_llm_import_anywhere_in_src():
    """This template has no narrative-generation requirement in the
    proposal — no module should import an LLM client at all."""
    import pathlib

    src_root = pathlib.Path(__file__).parents[2] / "src"
    llm_import_markers = ("langchain_anthropic", "anthropic", "openai", "ChatAnthropic", "ChatOpenAI")
    violations = []
    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text()
        for marker in llm_import_markers:
            if marker in text:
                violations.append(f"{py_file}: found LLM-related marker '{marker}'")
    assert violations == [], "\n".join(violations)
