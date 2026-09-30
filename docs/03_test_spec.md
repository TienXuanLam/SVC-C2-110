# Test Specification — SVC-C2-110

## Test Strategy
- Coverage target: framework-compliance + domain-logic + PB tests all passing; every
  node has ≥1 success-path and ≥1 error/edge-path unit test (per
  `EngineerGuide/sdk/how-to/write-tests.md` coverage requirements).
- Test types: Unit (nodes + services) / Integration (full graph compile+invoke) / PB

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | `src/schemas/state.py` — flat `TypedDict(AgentState)`, all dict/list fields `Optional[str]` JSON-str per ADR-005 | Pass |
| TC-02 | Fail-closed input rejection | `PreProcessNode._extra_security_gate_input()` sets `status=ERROR` for unauthorized/malformed input, never raises | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | Pass (CI) |
| TC-04 | InvocationContext via `configurable`/`from_state()` only | `MainNode`/`PostProcessNode` never construct `InvocationContext(...)` directly; only `src/api/server.py` does (entry-point exception) | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from all `execute()` bodies | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | 0 overrides |
| TC-08 | `required_trust_level` enforced | All 3 domain nodes declare `VERIFIED_EXTERNAL` explicitly; ANONYMOUS caller blocked before `execute()` | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial | `PreProcessNode` rejects unauthorized `caller_trust_level` | Pass |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial | `PostProcessNode` strips any field outside the explicit output allow-list | Pass |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per `execute()` invocation path | `MainNode` emits `evidence_validation_completed` on every successful path | ≥1 per relevant node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires in `MainNode.execute()` | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only (`test_state_safety.py`) | No Pydantic/dataclass, no credential-like field names | Pass |
| PB-3 | Level 2 → External service | N/A — this template has no live external service integration in-scope for implementation (proposal §12 Dependency #2 unresolved: authorized non-production data sources not yet provided); `policy_kb`/`claim_history` are injectable read-only adapters, exercised via fakes in unit/integration tests | Auto-waived — no external service wired at implementation time |
| PB-4 | Import isolation | No Level 0 (`agenticstar`) imports (`test_import_isolation.py`) | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint (`test_state_safety.py`) | Inspection pass | Pass |
| PB-6 | Invoke execution order | `__call__()`: S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` (`test_pb_invoke_order.py`, all 3 domain nodes) | Order verified for `PreProcessNode`, `MainNode`, `PostProcessNode` | Pass |
| PB-7 | HITL interrupt propagation *(conditional)* | `config/config.yaml` does not set `hitl.enabled: true` (see docs/02_design.md Design Decision Record: human review is external, not an in-graph checkpoint) | **Auto-waived — non-HITL** | Skipped (by design) |
| PB-01 (domain) | No claim-action language | Static AST scan of all string literals under `src/` for approval/rejection/payment/entitlement language (`test_pb01_no_claim_action_language.py`) | 0 violations; `review_route` module exposes exactly the 2 proposal-mandated outcomes | Pass |
| PB-02 (domain) | Deterministic-vs-LLM authority | Every domain decision function inspected via `inspect.signature()` for absence of an `llm` parameter; no LLM import anywhere in `src/` (`test_pb02_deterministic_domain_logic.py`) | 0 violations | Pass |
| PB-03 (domain) | S-3 output field minimization | `PostProcessNode._extra_security_gate_output()` strips any field outside the explicit allow-list (`test_pb03_output_field_minimization.py`) | Simulated leak fields never survive the gate | Pass |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory. PB-7 is
> auto-waived (non-HITL, per design). PB-01–PB-03 are the domain-specific
> boundary proofs required for this template's Risk #1/#2/#3 mitigations.

## Domain Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Intake normalization — happy path | Well-formed claim package JSON | `claim_references` normalized, uppercased, no rejections | Pass |
| BL-02 | Intake normalization — missing required field | Claim package missing `service_order_id` | Rejection notice recorded, pipeline continues (no hard error) | Pass |
| BL-03 | Evidence mapping — complete evidence | All requirement fields present | All requirements `present: true` except unresolved exception evidence | Pass |
| BL-04 | Evidence mapping — missing parts/fault-code | Empty `part_references`/`fault_codes` | Both requirements reported in `missing_evidence` | Pass |
| BL-05 | Consistency — coverage-period misalignment | `service_date` outside `[coverage_start_date, coverage_end_date]` | `coverage_period_gap` finding; `validation_confidence="gap"` | Pass |
| BL-06 | Consistency — unresolved policy version | `policy_resolved=False` | `policy_version_unresolved` finding; `validation_confidence="needs_human_confirmation"` | Pass |
| BL-07 | Consistency — duplicate-claim indicator | Non-empty `prior_claim_ids` | `duplicate_claim_indicator` finding labeled as review signal, never a fraud finding | Pass |
| BL-08 | Route decision — clean claim | No findings, no rejections, `validation_confidence="pass"` | `review_route="ready_for_human_warranty_review"` | Pass |
| BL-09 | Route decision — any gap/rejection | Any finding, rejection, or non-`pass` confidence | `review_route="manual_exception_review"` | Pass |
| BL-10 | Report composition | Any valid state | `evidence_gap_report` includes disclaimer; `human_confirmation_checklist` non-empty | Pass |
| BL-11 | Full pipeline — unauthorized caller | `caller_trust_level=ANONYMOUS` | `status=error`, no domain processing occurs | Pass |
| BL-12 | Full pipeline — incomplete claim | Minimal/incomplete claim JSON | `review_route="manual_exception_review"` end-to-end | Pass |

## Negative / Source-Failure / Stale-Data Cases

| TC-ID | Test | Scenario | Expected Result |
|-------|------|----------|----------------|
| NEG-01 | Malformed JSON input | `user_input` is not valid JSON | `PreProcessNode` returns `status=error` |
| NEG-02 | Non-dict claim payload | JSON payload is a list/scalar, not an object | `intake_normalization_service` returns empty references + rejection, no crash |
| NEG-03 | Oversized claim payload | >200 top-level fields | Rejected at intake with a size-ceiling reason |
| NEG-04 | Malformed upstream JSON state field | `evidence_map`/`consistency_findings` corrupted between nodes | `MainNode`/`PostProcessNode` return `status=error` instead of raising |
| NEG-05 | Unresolvable policy KB adapter | `policy_kb.resolve_policy_version()` returns `None` | Falls back to baseline requirement set; `validation_confidence="needs_human_confirmation"` |
| NEG-06 | Non-list evidence-reference field | `fault_codes` supplied as a string, not a list | Rejected safely, treated as empty list, no crash |

## Test Execution Summary
- Execution date: 2026-07-28
- Total tests: see CI `run-tests` job output for `tests/` (unit + integration + proof_of_boundary)
- Pass / Fail / Skip: PB-7 is the only expected `SKIPPED` result (non-HITL, by design)
- Coverage: framework/security gates (TC-01–TC-11) + domain logic (BL-01–BL-12) +
  negative cases (NEG-01–NEG-06) + proof-of-boundary (PB-1–PB-6, PB-01–PB-03) all pass
