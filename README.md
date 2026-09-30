# SVC-C2-110 — Field-Service Warranty Claim Evidence Validator Agent

> **Category**: Cat 2 (multi-step domain workflow — job-to-be-done)
> **Industry**: SVC (field service)

## Overview

Read-only/advisory Cat 2 workflow that validates a field-service warranty
claim's evidence against organization-approved policy, coverage, service,
parts, and fault-code requirements. It normalizes an authorized claim
package, maps each policy requirement to the evidence supplied (with
provenance back to the source field), checks cross-field consistency and
duplicate-claim indicators, and produces a structured evidence-gap report
plus a human confirmation checklist routed to warranty review. It never
approves, rejects, pays, submits, or negotiates a claim, and never
determines coverage or entitlement — every output is confirmed by an
external, accountable human reviewer. See `docs/01_proposal.md` and
`docs/02_design.md` for full detail.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

This agent is written against the `agenticstar-agentcore` framework and is
runnable standalone via `src/api/server.py` — it does not require the wider
AgentCore platform (registry, gateway, orchestrator) to function. Outside the
platform: request authentication falls back to an optional bearer token read
from an environment variable (unset means every caller is treated as
unauthenticated), and there is no persistent checkpointer unless you wire one
yourself, so in-flight state does not survive a process restart.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
deploy/       deployment manifests and invocation payload samples
```

See `docs/` for the design spec and test specification.

## Customising

1. Replace the injected `policy_kb` and `claim_history` adapters under `src/services/` with connectors to your own warranty policy catalog and claim history store.
2. Adjust the evidence-requirement checklist (asset, service, parts, fault-code, exception) in `evidence_mapping_service.py` to match your own coverage policy structure.
3. Tune the consistency and duplicate-claim checks in `consistency_validation_service.py` for your own field-service data model.
4. Re-run the test suite and review `docs/03_test_spec.md` for the proof-of-boundary assertions this template relies on.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
