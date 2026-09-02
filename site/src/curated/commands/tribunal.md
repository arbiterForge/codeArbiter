---
entity: commands/tribunal
related: [checkpoint, audit, skills/tribunal]
gates:
  - gate: cost acknowledgement
    when: before Phase 0 finishes, every run
    effect: the job is sized, a token-cost band and model recommendation are printed, and nothing dispatches until you explicitly acknowledge the estimate and confirm the model
  - gate: approval before filing
    when: after the report is generated
    effect: findings become GitHub issues only on your explicit selection, silence or "looks good" files nothing
---

## What it does

codeArbiter's deepest, most expensive review, convened rarely and never as a required gate. Eleven
specialist lenses judge the whole codebase in priority waves; each finding is written to its own
file under `.codearbiter/reports/<run-id>/`, so an interrupted run resumes from disk instead of
losing progress. Because this lane routinely costs millions of tokens on a large repo, Phase 0
always stops first: it sizes the codebase, prints the cost band, recommends the highest-reasoning
model, and waits for you to say go. Critical and high findings are blocking-severity in the report:
they are work that should block shipping the affected code. The tribunal run itself never halts a
merge or commit.

## The eleven lenses

Each lens judges one concern, in priority waves capped at five in flight. A lens is skipped
when its concern is absent from scope: a repo with no migrations drops the migration lens. Every
lens run is the same generic [`tribunal-lens-reviewer`](/reference/agents/tribunal-lens-reviewer/)
agent, dispatched once per lens with that lens's card as its mandate.

1. [appsec](/reference/tribunal-lenses/appsec/): injection, resource-level authz/IDOR, input validation, JWT, CORS, SSRF.
2. [architecture](/reference/tribunal-lenses/architecture/): dead/orphan modules, pattern drift, cosmetic abstractions, god modules, monolith accretion. Distinct from `architecture-drift-reviewer`, which checks conformance to accepted ADRs; this lens judges structural health on its own terms.
3. [coverage](/reference/tribunal-lenses/coverage/): risk-path coverage gaps, edge/property gaps, implementation-coupled tests.
4. [infra](/reference/tribunal-lenses/infra/): CI/CD correctness and security, container posture, IaC/deploy manifests, release automation.
5. [migration](/reference/tribunal-lenses/migration/): migration safety, data-classification tagging, immutability, schema-to-code drift.
6. [observability](/reference/tribunal-lenses/observability/): structured logging, tracing/correlation IDs, metrics on critical paths, audit gaps.
7. [performance](/reference/tribunal-lenses/performance/): N+1 queries, redundant hot-path work, query/index shape, caching, blocking IO.
8. [reliability](/reference/tribunal-lenses/reliability/): async correctness, error propagation, races, resource lifecycle, boundary conditions, orphan state.
9. [secrets-supply](/reference/tribunal-lenses/secrets-supply/): hardcoded secrets, weak crypto, cleartext, secrets in logs, supply-chain hygiene.
10. [test-fidelity](/reference/tribunal-lenses/test-fidelity/): tests validating fiction, meaning mocks, stubs, or fixtures that drifted from a producer that's since become real.
11. [typesafety](/reference/tribunal-lenses/typesafety/): footgun interfaces, weak typing, escape hatches, unhelpful errors, undocumented invariants.

On a large repo, two optional read-only mappers ([`map-structure`](/reference/agents/map-structure/)
and [`map-deps`](/reference/agents/map-deps/)) build the codebase inventory ahead of the lenses, so
that mapping work stays off the orchestrator's own context.

Published releases from 0.7.5 include each packaged lens resource charter for Codex host-provided
agent threads. Exact static-package and route-closure checks gate release. Until exact-release
thread dispatch is durably proven, the bounded inline fallback applies only where the canonical
workflow explicitly permits it and isolation is not mandatory. See
[Claude Code + Codex → Intentional host
differences](/getting-started/claude-code-and-codex/#intentional-host-differences).

A triage pass independently recalibrates every lens's own severity call rather than trusting it
as final; every critical or high finding must carry a counter-argument. `report.md` is always a
projection of the append-only `run.jsonl` and `triage.jsonl` logs, never hand-authored.

Resuming an interrupted run is time-boxed: a run older than seven days STOPs and asks whether to
resume anyway or start fresh, since the codebase may have drifted under the recorded findings.

## Usage

```
/ca:tribunal "[scope-path] [--tag <label>]"
```

An optional `scope-path` narrows which subtree gets scrutiny (the full eleven-lens roster still
runs); `--tag <label>` records a freeform label if you opt in to KPI telemetry at the end.

## Example

```text
> /ca:tribunal

Sizing codebase... 340 files, ~2.1M tokens estimated.
Recommended model: highest-reasoning available, high effort.
Estimated cost band: $180-$260.

Proceed with this model and cost? (y/n)
> y

RUN_ID: 2026-07-02-full
Phase 1: mapping... inventory.md written, 11 lenses active.
Phase 2: dispatching lenses (wave 1/3, ≤5 in flight)...
...
Phase 4: report.md regenerated — 3 CRITICAL, 9 HIGH, 21 MEDIUM findings.

Phase 5: file findings as GitHub issues? Select which, or "none".
```

## When to reach for it

Rare, deliberate, whole-codebase depth, not the routine sweep (`/ca:checkpoint`), not a diff review
(`/ca:review`), and never wired into a hot loop or schedule.
