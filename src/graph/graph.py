"""AgentCore Platform v1.0"""

# ─────────────────────────────────────────────────────────────────────────────
# Template Category (Cat) — choose ONE based on your Cat judgment:
#
# Cat 1 — Single technical capability (use-case-agnostic)
#   Purpose : Delivers one reusable, domain-independent capability.
#             The same template can be dropped into any project unchanged.
#   Examples: TextSummarizer, EmbeddingGenerator, LanguageDetector,
#             SentimentAnalyzer, KeywordExtractor
#   Parent  : AgentBaseGraph
#   Pipeline: START → initialize → pre_process → main → {route} → post_process → finalize → END
#                                             ↓ (RETRY, max 3)
#                                          pre_process
#   See src/examples/graph_cat1_sample.py for a full example.
#
# Cat 2 — Multi-step domain workflow (job-to-be-done)
#   Purpose : Orchestrates multiple steps to accomplish a specific business
#             outcome. The template name describes the outcome, not the
#             individual capabilities it uses.
#   Examples: InvoiceTriageAgent, ContractGapDetectionAgent,
#             ResumeScreeningAgent, SupportTicketResolutionAgent
#   Parent  : AgentBaseGraph (outer graph) + GraphNode in the `main` slot
#             wrapping an inner BaseGraph/AgentBaseGraph (domain workflow)
#   Pipeline: Same fixed 5-node backbone as Cat 1; domain complexity is
#             encapsulated inside DomainWorkflowGraphNode.get_subgraph().
#   Layout  : src/graph/graph.py                 ← outer graph (this file)
#             src/graph/domain_workflow_graph.py ← inner graph
#   See src/examples/graph_cat2_sample.py and src/examples/domain_workflow_graph_sample.py for examples.
#
# Cat 3 — Autonomous think→act→observe loop (self-directed)
#   Purpose : Runs an LLM-driven loop that decides its own next action,
#             executes tools, observes results, and terminates when the task
#             is complete or a budget/iteration ceiling is hit.
#   Examples: ResearchAgent, AutonomousCodeReviewAgent,
#             DataExplorationAgent, MultiStepPlannerAgent
#   Parent  : AutonomousBaseGraph
#   Pipeline: START → initialize → think ⇄ act → finalize → END
#   Config  : budget_usd and llm are required in config.yaml.
#   See src/examples/graph_cat3_sample.py for a full example.
#
# ── How to choose ─────────────────────────────────────────────────────────────
#
#   Ask: "Does this template solve a specific business problem end-to-end?"
#     No  → Cat 1 (generic capability)
#     Yes → "Does it need an autonomous reasoning loop to decide its steps?"
#       No  → Cat 2 (fixed multi-step workflow)
#       Yes → Cat 3 (LLM-driven loop)
#
# framework.* imports are unchanged; agent-local imports use the src. prefix.
# ─────────────────────────────────────────────────────────────────────────────

from framework.graph.agent_base_graph import AgentBaseGraph
from src.nodes.pre_process_node import PreProcessNode
from src.nodes.evidence_validation_graph_node import EvidenceValidationGraphNode
from src.nodes.post_process_node import PostProcessNode
from src.schemas.state import State


class WarrantyClaimEvidenceValidatorAgent(AgentBaseGraph):
    """Field-Service Warranty Claim Evidence Validator (SVC-C2-110).

    Cat 2 multi-step domain workflow — outer AgentBaseGraph backbone
    (pre_process/main/post_process/finalize) with the `main` slot wrapping
    the inner evidence-mapping -> consistency-validation domain workflow
    (src/graph/domain_workflow_graph.py) via EvidenceValidationGraphNode,
    per the framework's Cat 2 composition contract. See docs/02_design.md
    "Architecture" (fixed 2026-07-28 per Agent1000 review finding T1-1 —
    the prior implementation registered a flat FunctionNode directly in the
    `main` slot instead of the required outer/inner GraphNode split).
    """

    @property
    def name(self) -> str:
        return "WarrantyClaimEvidenceValidatorAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        # super() injects "initialize" and "finalize" slots automatically.
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        # Domain pipeline slots. EvidenceValidationGraphNode takes the
        # read-only policy_kb / claim_history adapters from self.config and
        # threads them into the inner graph's config — see graph.py
        # constructor wiring checklist (EngineerGuide/IMPLEMENTATION_LOG.md
        # §A6): both dependencies must be threaded here, not just "the
        # obvious node".
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = EvidenceValidationGraphNode(
            policy_kb=self.config.get("policy_kb"),
            claim_history=self.config.get("claim_history"),
        )
        self._nodes["post_process"] = PostProcessNode()
