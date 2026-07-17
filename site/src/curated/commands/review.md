---
entity: commands/review
related: [skills/dispatching-parallel-agents, pr, preview]
gates:
  - gate: severity block
    when: any CRITICAL or HIGH finding surfaces
    effect: must be resolved before /ca:pr — the aggregated verdict is not advisory at that severity
---

## What it does

A read-only review of the current change, dispatched by path against a reviewer-to-path matrix:
`security-reviewer` for auth/middleware/secrets/deploy paths, `auth-crypto-reviewer` for
authn/crypto/key handling, `dependency-reviewer` for manifest/lockfile changes,
`migration-reviewer` for DB migrations, `coverage-auditor` for any source change, and
`architecture-drift-reviewer` for code that may diverge from an accepted ADR. Each matched
reviewer runs as one read-only unit through `dispatching-parallel-agents`; the results are
deduped, then funneled through `finding-triage` (severity plus an inline `[NEEDS-TRIAGE]` marker
on anything out of scope) and `checkpoint-aggregator` down to a single verdict. No file is
modified by a run. A finding that turns on a genuinely-unresolved unknown surfaces as a numbered
[`CONFIRM-NN`](/glossary/#confirm-nn) rather than being resolved by guessing.

Findings are surfaced by severity (CRITICAL/HIGH/MEDIUM/LOW), file:line, remediation, and — for
security findings — the specific control in `.codearbiter/security-controls.md` they map to. Raw
per-reviewer output is never consumed directly; only the triaged, aggregated verdict is.

## Usage

```
/ca:review [path]
```

Defaults to the current uncommitted diff when no path is given.

## Example

```text
> /ca:review

Dispatched: security-reviewer, auth-crypto-reviewer (src/auth/session.ts)
            coverage-auditor (src/auth/session.ts, src/auth/login.test.ts)

HIGH   src/auth/session.ts:41  Session token generated with Math.random(),
       not a CSPRNG. Control: security-controls.md §Randomness.
LOW    src/auth/login.test.ts  No test for expired-token rejection path.

Verdict: 1 HIGH, 1 LOW — HIGH must be resolved before /ca:pr.
```

## When to reach for it

`/ca:pr` already dispatches this automatically when opening a PR, so a manual run is for checking
before that point; a periodic full-codebase sweep is `/ca:checkpoint`'s job, and a
pre-implementation threat model is `/ca:threat-model`'s. A read-only look before onboarding at all
is `/ca:preview`.
