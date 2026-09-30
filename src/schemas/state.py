"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.
#
# SVC-C2-110 — Field-Service Warranty Claim Evidence Validator.
# Read-only/advisory Cat 2 workflow: normalizes an authorized warranty-claim
# package, maps it to a policy/checklist requirement set, checks coverage /
# service / parts / fault-code / duplicate-claim consistency, and produces a
# structured evidence-gap report routed to human warranty review. It never
# approves, rejects, pays, or submits a claim — see docs/02_design.md.
#
# Dict/list-shaped domain fields follow ADR-005: stored as JSON strings
# (Optional[str]) rather than nested objects, to keep the state flat and
# msgpack-safe.

from typing import Optional

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for the Warranty Claim Evidence Validator.

    Add only fields specific to this agent below. All shared fields
    (user_input, status, session_id, node_history, error_log, hitl_*, etc.)
    are inherited from AgentState. This agent does not use hitl_* — human
    review happens downstream of the agent's advisory output, not as an
    in-graph interrupt/resume checkpoint (see docs/02_design.md, Design
    Decision Record).

    # ── Step 1 (pre_process): Controlled intake and normalization ──
    claim_references: Optional[str]
        JSON-str dict of normalized identifiers extracted/validated from the
        caller's authorized claim package: claim_id, policy_id,
        policy_version, asset_serial, service_order_id, fault_code(s),
        part_reference(s), prior_claim_ids. Producer: pre_process.
        Consumer: main.
    intake_rejections: Optional[str]
        JSON-str list of audit-safe rejection notices for malformed/
        unauthorized/unsupported references found during intake (does not
        halt the pipeline — feeds into the evidence-gap report).
        Producer: pre_process. Consumer: main, post_process.
    caller_authorized: bool
        Whether the caller's authorization for claim/policy/service data was
        verified during intake. Producer: pre_process. Consumer: main.

    # ── Step 2+3 (main): Evidence mapping + consistency validation ──
    evidence_map: Optional[str]
        JSON-str dict mapping each policy/checklist requirement to the
        source evidence found (asset, service, parts, fault-code, exception)
        with provenance (source id + field). Producer: main. Consumer:
        post_process.
    missing_evidence: Optional[str]
        JSON-str list of requirement ids with no matching evidence found.
        Producer: main. Consumer: post_process.
    consistency_findings: Optional[str]
        JSON-str list of structured findings from serial/coverage-period
        alignment, service-evidence completeness, fault-code/part-reference
        consistency, and duplicate-claim indicator checks. Each finding
        carries a machine-checkable category, never a coverage/entitlement
        conclusion. Producer: main. Consumer: post_process.
    policy_resolved: bool
        Whether the policy/checklist version was actually resolved against a
        configured policy knowledge base (Cat 2 inner-graph field). False
        (including when no policy_kb is configured at all — fail-closed) is
        propagated into consistency_validation as an unresolved-policy
        finding, never silently treated as resolved. Producer: main
        (evidence_mapping inner node). Consumer: main (consistency_validation
        inner node).
    exception_evidence_present: bool
        Whether the claim references an approved exception-policy record.
        Never used to infer an exception was granted. Producer: main.
        Consumer: post_process.
    validation_confidence: str
        One of "pass" | "gap" | "needs_human_confirmation" — deterministic
        machine-checkable outcome of Step 3, distinct from the final human
        review route decided in post_process. Producer: main. Consumer:
        post_process.

    # ── Step 4 (post_process): Result composition and human handoff ──
    review_route: str
        One of "ready_for_human_warranty_review" | "manual_exception_review".
        The only two outcomes this agent may ever produce; never an
        approval/rejection/payment decision. Producer: post_process.
        Consumer: caller (external).
    evidence_gap_report: Optional[str]
        JSON-str structured report: requirement-level evidence map, missing
        items, inconsistency list, exception references, and citations
        (rule/policy version ids) — the human-handoff artifact. Producer:
        post_process. Consumer: caller (external), human reviewer.
    human_confirmation_checklist: Optional[str]
        JSON-str list of discrete confirmation items the accountable human
        reviewer must check off before any claim action is taken elsewhere.
        Producer: post_process. Consumer: caller (external), human reviewer.
    """

    claim_references: Optional[str]
    intake_rejections: Optional[str]
    caller_authorized: bool

    evidence_map: Optional[str]
    missing_evidence: Optional[str]
    policy_resolved: bool
    consistency_findings: Optional[str]
    exception_evidence_present: bool
    validation_confidence: str

    review_route: str
    evidence_gap_report: Optional[str]
    human_confirmation_checklist: Optional[str]
