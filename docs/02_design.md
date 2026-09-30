# Template Design Specification — SVC-C2-110

## Position in AgentCore Architecture

- **Agent Class**: `WarrantyClaimEvidenceValidatorAgent`
- **L1 Base**: AgentBaseGraph (direct; no L2 inheritance — per proposal §1
  "Inherits from AgentBaseGraph (L1 direct only; no L2 inheritance)")
- **Pattern**: Cat 2 multi-step domain workflow — outer `AgentBaseGraph`
  backbone with the `main` slot wrapping an inner domain workflow graph via
  `GraphNode` composition, per the framework's Cat 2 composition contract.
  **Corrected 2026-07-28** (review finding T1-1): the prior implementation registered a
  flat `FunctionNode` directly in `main`, which is the Cat 1 pipeline shape,
  not the required Cat 2 outer/inner split. See "Architecture Overview"
  below.
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

### ASCII Diagram

```
[Authorized caller: claim package + policy/version ref
 + asset/serial + coverage-period + service/fault-code evidence
 + parts record + prior-claim refs + exception policy ref]
    |
    v
OUTER: START → initialize → pre_process → main → route() → post_process → finalize → END
                                 |            |                  |
                                 |            |                  └─ Step 4: Result composition
                                 |            |                     + human handoff package
                                 |            |
                                 |            └─ GraphNode (EvidenceValidationGraphNode)
                                 |               wraps INNER graph:
                                 |
                                 |               INNER: START → evidence_mapping
                                 |                             → consistency_validation → END
                                 |                 (src/graph/domain_workflow_graph.py,
                                 |                  EvidenceValidationWorkflowGraph : BaseGraph)
                                 |
                                 └─ Step 1: Controlled intake & normalization
                                                       ↑ (RETRY, up to max_retry)
                                                     pre_process
    |
    v
[Output: review_route ∈ {ready_for_human_warranty_review, manual_exception_review}
 + evidence_gap_report + human_confirmation_checklist]
    |
    ├─► Warranty operations / commercial reviewer (external, out-of-agent decision)
    └─► Service administrator (correction loop, external)
```

### Cat 2 outer/inner split (corrected 2026-07-28 — review finding T1-1)

Per the framework's Cat 2 composition contract, a Cat 2 template's `main` slot must wrap a `GraphNode`
around an inner domain workflow graph — a flat `FunctionNode` in `main` is
the Cat 1 shape and does not satisfy the composition-consistency review
criterion. This template's Steps 2+3 (Evidence Mapping, Consistency
Validation) are the domain workflow:

- **Outer graph** (`src/graph/graph.py`, `WarrantyClaimEvidenceValidatorAgent : AgentBaseGraph`):
  fixed 5-node backbone. `main` = `EvidenceValidationGraphNode` (`GraphNode`
  subclass) — implements `get_subgraph()`, `extract_input()`,
  `merge_output()` per the mandatory `GraphNode` contract.
- **Inner graph** (`src/graph/domain_workflow_graph.py`,
  `EvidenceValidationWorkflowGraph : BaseGraph`): fully custom 2-node linear
  topology — `evidence_mapping` → `consistency_validation`. Inherits
  `BaseGraph` directly (not `AgentBaseGraph`) because it has no
  pre_process/post_process concerns of its own; those belong to the outer
  graph only.
- **Data channel**: `GraphNode.execute()` calls
  `subgraph.invoke(user_input, session_id=ctx.session_id, ctx=ctx)` with no
  `input_context` parameter (framework contract, verified against
  `framework/nodes/graph_node.py`), so `EvidenceValidationGraphNode
  .extract_input()` serializes the normalized `claim_references` JSON
  string as the inner graph's `user_input`. `EvidenceMappingNode` (inner)
  reads it back via `state.get("user_input")`, re-derives `claim_references`
  for the second inner node, and both inner nodes' outputs are shaped by
  `EvidenceValidationWorkflowGraph.get_output()` into `sub_result`, which
  `EvidenceValidationGraphNode.merge_output()` maps field-by-field into the
  outer state (no raw pass-through, per CoE criterion #9).

### Node Configuration

| Node | Graph | Responsibility | Input State | Output State | Inherits/Overrides |
|------|-------|---------------|-------------|--------------|-------------------|
| initialize | outer | Sets schema_version, session_id, trust_level | `user_input`, `input_context` | `session_id`, `trace_id`, `correlation_id` | InitializeNode (default) |
| pre_process | outer | Step 1 — Controlled intake & normalization | `user_input` (claim package JSON string) | `claim_references`, `intake_rejections`, `caller_authorized`, `status` | `FunctionNode` |
| main (`EvidenceValidationGraphNode`) | outer | Wraps the inner domain workflow graph | `claim_references` | `evidence_map`, `missing_evidence`, `consistency_findings`, `exception_evidence_present`, `validation_confidence`, `status` | `GraphNode` |
| ↳ evidence_mapping | inner | Step 2 — Checklist-to-evidence mapping | `user_input` (= outer's `claim_references`) | `claim_references`, `evidence_map`, `missing_evidence`, `policy_resolved`, `status` | `FunctionNode` |
| ↳ consistency_validation | inner | Step 3 — Consistency and exception validation | `claim_references`, `evidence_map`, `policy_resolved` | `consistency_findings`, `exception_evidence_present`, `validation_confidence`, `status` | `FunctionNode` |
| post_process | outer | Step 4 — Result composition & human handoff | `evidence_map`, `missing_evidence`, `consistency_findings`, `validation_confidence`, `intake_rejections` | `review_route`, `evidence_gap_report`, `human_confirmation_checklist`, `formatted_output`, `status` | `FunctionNode` |
| finalize | outer | Builds response_metadata, total_time_ms | all | `formatted_output`, `response_metadata` | FinalizeNode (default) |

### Step Detail

| Step | Node | Core Logic | Output |
|---|---|---|---|
| 1. Controlled intake and normalization | `pre_process` (outer) | S-2 hook validates caller authorization plus JSON structural well-formedness (valid JSON, is an object) — fail-closed, sets `status=ERROR` without raising. `execute()` then normalizes claim/asset/serial/service-order/part/fault-code/policy identifiers (case/whitespace/format normalization only — no lookups) and produces a rejection list for missing/malformed individual fields (business-rule rejection, not a security block — see T1-4 note in Security Design). | `claim_references` (JSON-str), `intake_rejections` (JSON-str), `caller_authorized` |
| 2. Checklist-to-evidence mapping | `evidence_mapping` (inner) via `evidence_mapping_service.py` | Select the applicable policy/checklist version from `claim_references.policy_version`; map each requirement (asset, service, parts, fault-code, exception) to evidence present in the normalized claim references, with provenance (source field). Uses an injected read-only `policy_kb` adapter. `policy_resolved` is derived strictly from whether the KB actually resolved the version — a missing/unconfigured `policy_kb` is `policy_resolved=False` (fail-closed; fixed 2026-07-28, T1-2). | `claim_references` (re-exposed), `evidence_map` (JSON-str), `missing_evidence` (JSON-str), `policy_resolved` |
| 3. Consistency and exception validation | `consistency_validation` (inner) via `consistency_validation_service.py` | Deterministic checks only: serial/coverage-period alignment, service-evidence completeness, fault-code/part-reference consistency, duplicate-claim indicators (via `prior_claim_ids` overlap and the injected `claim_history` adapter), and presence (not validity/entitlement) of exception evidence. Never infers an exception grant or coverage entitlement. The `claim_history` adapter call is wrapped — an adapter/connector failure degrades to an unresolved-duplicate-check finding and `needs_human_confirmation`, never an unhandled exception (fixed 2026-07-28, T1-3). | `consistency_findings` (JSON-str), `exception_evidence_present`, `validation_confidence` |
| 4. Result composition and human handoff | `post_process` (outer) | Deterministic route decision: `validation_confidence in {"gap", "needs_human_confirmation"}` OR any exception-related finding → `manual_exception_review`; otherwise → `ready_for_human_warranty_review`. Composes the structured Markdown/JSON evidence-gap report with citations (policy/rule version ids) and a human confirmation checklist. Applies S-3 output minimization (drops any raw source payload fields, keeps only the derived findings). | `review_route`, `evidence_gap_report` (JSON-str), `human_confirmation_checklist` (JSON-str), `formatted_output` |

### Data Flow

```
OUTER:
START
  → initialize             (session_id, trust_level set)
  → pre_process             [S-1 gate: required_trust_level=VERIFIED_EXTERNAL]
       execute(): parse+normalize claim package
       → claim_references, intake_rejections, caller_authorized, status
  → main (EvidenceValidationGraphNode)
       extract_input(state) -> claim_references JSON string
       subgraph.invoke(user_input=claim_references, ctx=ctx)
         INNER:
         → evidence_mapping           [S-1 gate: required_trust_level=VERIFIED_EXTERNAL]
              execute(): evidence_mapping_service.map_evidence(claim_references)
              → claim_references, evidence_map, missing_evidence, policy_resolved, status
         → consistency_validation     [S-1 gate: required_trust_level=VERIFIED_EXTERNAL]
              execute(): consistency_validation_service.validate_consistency(...)
              → consistency_findings, exception_evidence_present, validation_confidence, status
       merge_output(state, sub_result) -> outer state delta (explicit field mapping)
       → evidence_map, missing_evidence, consistency_findings,
         exception_evidence_present, validation_confidence, status
  → route()                 (status == "success" → post_process; "retry" → pre_process; else → finalize)
  → post_process             [S-1 gate: required_trust_level=VERIFIED_EXTERNAL]
       execute(): deterministic route decision + report composition
       → review_route, evidence_gap_report, human_confirmation_checklist,
         formatted_output, status
  → finalize                 (response_metadata, total_time_ms)
END
```

### State Definition

| Field | Type | Producer | Consumer | ADR-005 note |
|-------|------|----------|----------|--------------|
| `claim_references` | `Optional[str]` (JSON) | pre_process | main | dict of normalized identifiers — stored as JSON string |
| `intake_rejections` | `Optional[str]` (JSON) | pre_process | main, post_process | list of rejection notices — stored as JSON string |
| `caller_authorized` | `bool` | pre_process | main | primitive, no ADR-005 concern |
| `evidence_map` | `Optional[str]` (JSON) | main | post_process | dict of requirement→evidence+provenance — stored as JSON string |
| `missing_evidence` | `Optional[str]` (JSON) | main | post_process | list of requirement ids — stored as JSON string |
| `policy_resolved` | `bool` | main (inner: evidence_mapping) | main (inner: consistency_validation) | primitive; fail-closed — False when no policy_kb is configured, never treated as resolved |
| `consistency_findings` | `Optional[str]` (JSON) | main | post_process | list of structured findings — stored as JSON string |
| `exception_evidence_present` | `bool` | main | post_process | primitive |
| `validation_confidence` | `str` | main | post_process | enum-like string: `pass`\|`gap`\|`needs_human_confirmation` |
| `review_route` | `str` | post_process | caller (external) | enum-like string: `ready_for_human_warranty_review`\|`manual_exception_review` |
| `evidence_gap_report` | `Optional[str]` (JSON) | post_process | caller, human reviewer | structured report — stored as JSON string |
| `human_confirmation_checklist` | `Optional[str]` (JSON) | post_process | caller, human reviewer | list of checklist items — stored as JSON string |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Security Design (S-1 → S-5)

| Layer | Applies at | Design |
|---|---|---|
| S-1 Trust Gate | pre_process, main (outer + both inner nodes), post_process | Every domain node (outer `pre_process`/`post_process`, inner `evidence_mapping`/`consistency_validation`) declares `required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL` explicitly (proposal: "Authorize and normalize refs" requires an authorized caller — no ANONYMOUS access to claim/policy/service data). The inner graph receives the outer `InvocationContext` automatically via `GraphNode.execute()` (framework contract) — trust level is not re-derived or weakened at the inner boundary. |
| S-2 PII Input Gate | pre_process | `_extra_security_gate_input()` fail-closed rejects (sets `status=ERROR`, does not raise) in order: (1) unauthorized/insufficient `caller_trust_level`, (2) missing `caller_id` (S-5 — see below), (3) empty/malformed/non-object JSON payload. Fixed 2026-07-28 (T1-4): JSON structural validation now genuinely runs in this hook, not later in `execute()` — reconciled with docs/03_test_spec.md. Field-level business rejections (which named claim fields are present) remain a rejection-list outcome in `execute()`, not a security block, per proposal Risk #4. |
| S-3 Output Credential Scan | post_process | `_extra_security_gate_output()` strips any field not in the allow-list (`review_route`, `evidence_gap_report`, `human_confirmation_checklist`, `formatted_output`) before it can leave the node — belt-and-suspenders field minimization on top of the framework's default credential scan, addressing Risk #2 (data exposure through outputs). |
| S-4 Audit Logging | pre_process, main (both inner nodes), post_process | Every node emits at least one domain event via `emit_trace_event()`: `claim_intake_normalized` (pre_process), `evidence_mapping_completed` (inner evidence_mapping), `consistency_validation_completed` (inner consistency_validation; `claim_history_lookup_failed` on adapter failure — T1-3), `evidence_gap_report_composed` (post_process). All events carry `caller_id` for S-5 attribution, never raw source-record payload. |
| S-5 Tenant Isolation / Retention | pre_process, post_process | Fixed 2026-07-28 (review T2-1). The proposal identifies unresolved privacy/retention/tenant-isolation dependencies (see proposal §10 row 5, §12 Dependency 3) that remain genuinely unresolved as external policy — this design's scope is the traceability half only: (1) `pre_process._extra_security_gate_input()` fail-closed rejects any authorized-trust request with an empty `caller_id`, so no claim can be processed with an unattributable identity; (2) every audit event and the `evidence_gap_report`'s new `requested_by` field carry `caller_id`, so no output artifact can be mistaken for or merged with another tenant's data downstream. This agent holds no state beyond a single synchronous invocation (no persistence/cache of claim data across requests) and is read-only/advisory, so it does not itself implement data-retention *duration* controls — retention policy for the evidence-gap report once it leaves this agent is an explicit unresolved dependency for the platform/warranty-ops owner, not something this template can unilaterally decide. See `docs/01_proposal.md` §12 Dependency 3. |

### Risk mitigation mapping (proposal §11)

| Proposal Risk | Mitigation in this design |
|---|---|
| #1 Agent presents incomplete/misread evidence as coverage or a claim recommendation | `review_route` is restricted to exactly 2 enum values, both non-decisional; `post_process` never emits approval/rejection/payment language — enforced by PB test (static scan, see `docs/03_test_spec.md`). |
| #2 Customer/asset/technician/service/commercial data exposed via inputs, prompts, outputs, or logs | S-3 output allow-list in `post_process`; `pre_process` normalizes identifiers only (no raw record echo into `evidence_gap_report`); `emit_trace_event()` payloads carry only derived flags, never raw source fields. |
| #3 Users treat duplicate indicators as fraud findings or act on output without a reviewer | `consistency_findings` duplicate-indicator entries are labeled `"category": "duplicate_claim_indicator"` (review signal only); `human_confirmation_checklist` explicitly requires reviewer sign-off before any downstream claim action; PB test asserts rejection of forged "approve"/"pay"/"submit" input intents. |
| #4 Outdated policy/version or incomplete service history produces false gaps or misleading status | `evidence_mapping_service` requires `policy_version` to be present and resolvable via the injected `policy_kb`; unresolvable/stale version → `validation_confidence="needs_human_confirmation"` → fails safe to `manual_exception_review`. |
| #5 Large claim packages or ambiguous identifiers cause latency or incorrect linkage | `pre_process` enforces an input-size ceiling on the claim payload and rejects ambiguous (duplicate-key) identifiers into `intake_rejections` rather than guessing a linkage. |

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller_id, trust level) — propagated automatically into the inner graph by `GraphNode.execute()` (framework contract); never constructed directly in a node.
- [x] GraphNode (`framework.nodes.graph_node`) — Cat 2 composition; `EvidenceValidationGraphNode` implements all 3 mandatory abstract methods.
- [x] S-2: `_extra_security_gate_input()` in `pre_process` — authorization + caller_id presence (S-5) + JSON structural validation.
- [x] S-3: `_extra_security_gate_output()` in `post_process` — output field allow-list.
- [x] S-4: `emit_trace_event()` — one domain event per node: `claim_intake_normalized`, `evidence_mapping_completed`, `consistency_validation_completed` (+ `claim_history_lookup_failed` on adapter failure), `evidence_gap_report_composed`; all carrying `caller_id`.

> **S-2/S-3 gate behaviour by node type (ADR-017):** all three domain nodes
> are `FunctionNode` subclasses — the framework `@final` gate always runs
> automatically; extended only via `_extra_security_gate_input()` /
> `_extra_security_gate_output()`.

### Composition Pattern

- **Pattern**: Cat 2 GraphNode composition — the outer graph's `main` slot
  is `EvidenceValidationGraphNode` (`GraphNode` subclass) wrapping the
  inner `EvidenceValidationWorkflowGraph`
  (`src/graph/domain_workflow_graph.py`). This template is not itself
  embedded as a subgraph of another agent.
- **Composition target**: inner graph `EvidenceValidationWorkflowGraph :
  BaseGraph` (2-node linear domain topology). Mandatory `GraphNode`
  contract implemented in full: `get_subgraph()` (cached instance +
  compile), `extract_input()` (claim_references JSON string →
  inner user_input), `merge_output()` (explicit field-by-field mapping —
  no raw pass-through, CoE criterion #9).
- **Error propagation strategy**: `error_strategy = "propagate"` (explicit
  ClassVar) — an inner-graph error raises `SubgraphError` to the outer
  pipeline; `status=ERROR` routes to `finalize` without silently
  downgrading to a review route.
- **HITL propagation**: `propagate_hitl = False` (this template has no
  in-graph HITL — see Design Decision Record).

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)

## Class Name Consistency

| Location | Value |
|---|---|
| `config/agent.yaml` → `agent.class` | `WarrantyClaimEvidenceValidatorAgent` |
| `src/graph/graph.py` → class name | `WarrantyClaimEvidenceValidatorAgent` |
| `docs/02_design.md` → Agent Class | `WarrantyClaimEvidenceValidatorAgent` |

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Proposal §1 mandates L1-direct `AgentBaseGraph`; workflow is a fixed, bounded pipeline with no autonomous think→act loop or self-directed termination. |
| Node-count reconciliation | Flat merge of Steps 2+3 into one `main` FunctionNode | Cat 2 GraphNode wrapping an inner 2-node domain workflow graph | **Cat 2 composition (Option B)** — revised 2026-07-28 | The original design chose the flat merge (Option A), which is the Cat 1 pipeline shape and fails CoE criterion #9 for a Cat 2 template (Agent1000 review finding T1-1). Steps 2+3 are now two real `FunctionNode`s (`evidence_mapping`, `consistency_validation`) inside `EvidenceValidationWorkflowGraph`, each with its own S-1/S-4 boundary; `src/services/` still keeps the domain logic in separate, independently unit-testable pure functions. |
| HITL scope | In-graph `interrupt()` checkpoint | External human review (no `interrupt()`) | **External (Option B)** | Proposal describes the accountable reviewer receiving the evidence-gap report and independently deciding — there is no described suspend/resume checkpoint inside the agent's own execution (contrast with e.g. physician sign-off patterns). Per `EngineerGuide/IMPLEMENTATION_LOG.md` §A5, `interrupt()` is reserved for a *described technical* suspend/resume checkpoint; a "requires downstream accountable review" requirement without an in-agent pause point uses the advisory/human-handoff pattern instead — here realized as the mandatory `human_confirmation_checklist` field plus the strict 2-value `review_route` enum, never a bypass-able "approved" state written by the agent itself. |
| Deterministic vs LLM authority | LLM classifies validation_confidence/review_route | Deterministic rules only | **Deterministic only** | Per `EngineerGuide/IMPLEMENTATION_LOG.md` §A4, decisions with legal/financial/technical weight (coverage/consistency findings, route classification) must be deterministic; this template currently has no narrative-generation requirement in the proposal, so no LLM dependency is introduced at all — `evidence_gap_report` text is templated from structured findings, not LLM-authored. This keeps `docs/03_test_spec.md` PB tests able to assert via `inspect.signature()` that no domain decision function accepts an `llm` parameter. |
| Output field minimization | Return full internal findings dict | Explicit allow-list in `_extra_security_gate_output()` | **Explicit allow-list** | Directly addresses proposal Risk #2 (data exposure) — belt-and-suspenders on top of the framework's default S-3 credential scan, which does not by itself prevent an over-broad but credential-free field from leaking. |
