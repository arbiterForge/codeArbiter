---
entity: commands/tribunal
related: [checkpoint, audit, skills/tribunal]
gates:
  - gate: cost acknowledgement
    when: before Phase 0 finishes, every run
    effect: the selected evidence and review settings are sized, an estimated token-cost band is shown, and reviewers start only after you acknowledge the estimate and confirm the settings
  - gate: approval before filing
    when: after the report is generated
    effect: findings become GitHub issues only on your explicit selection, silence or "looks good" files nothing
---

## What it does

Tribunal is codeArbiter's deepest review, for a deliberate audit of a repository or subtree.
Thirteen specialist lenses look for concrete defects and incomplete changes. Findings and leads
are saved under `.codearbiter/reports/<run-id>/` as the review proceeds, so an interruption does
not erase the work. Tribunal recommends fixes; it never becomes a required commit or merge gate.

Before reviewers start, Tribunal collects a deterministic inventory without running project code,
selects applicable lenses, and estimates the work from their evidence packets and supported model
settings. You see the inputs and uncertainty band and approve the cost and settings. Narrowing
the scope or evidence reduces review work; lowering concurrency mainly changes peak resource use
and elapsed time.

## The thirteen lenses

Each lens judges one concern, in priority waves capped at five in flight. A lens is skipped
when its concern is absent from scope: a repo with no migrations drops the migration lens. Every
lens run is the same generic [`tribunal-lens-reviewer`](/reference/agents/tribunal-lens-reviewer/)
agent, dispatched once per lens with that lens's card as its mandate.

| Lens | What it checks |
| --- | --- |
| [appsec](/reference/tribunal-lenses/appsec/) | Reachable security failures across trust and authorization boundaries. |
| [architecture](/reference/tribunal-lenses/architecture/) | Unsafe coupling, policy drift, dead paths, and violated architectural contracts with concrete consequences. |
| [change-closure](/reference/tribunal-lenses/change-closure/) | Changes that fail to reach callers, generated files, hosts, packages, or release surfaces. |
| [coverage](/reference/tribunal-lenses/coverage/) | Missing behavioral checks and assertions too weak to distinguish a plausible wrong implementation. |
| [infra](/reference/tribunal-lenses/infra/) | CI/CD, containers, deployment configuration, and release automation. |
| [migration](/reference/tribunal-lenses/migration/) | Data and schema changes against the project's actual rollout and recovery model. |
| [observability](/reference/tribunal-lenses/observability/) | Missing diagnostics or audit evidence needed to operate and recover the product. |
| [performance](/reference/tribunal-lenses/performance/) | Resource or latency problems supported by a measured, documented, or demonstrable scale premise. |
| [reliability](/reference/tribunal-lenses/reliability/) | Error ownership, cancellation, retries, races, partial failure, and resource lifecycle. |
| [secrets-supply](/reference/tribunal-lenses/secrets-supply/) | Secret flows, unsafe dependency use, package identity, and provenance. |
| [semantic-contract](/reference/tribunal-lenses/semantic-contract/) | Plausible code that violates an established requirement, compatibility promise, or forbidden behavior. |
| [test-fidelity](/reference/tribunal-lenses/test-fidelity/) | Mocks, fixtures, or expected results that disagree with the real producer or contract. |
| [typesafety](/reference/tribunal-lenses/typesafety/) | Unvalidated data, unchecked narrowing, schema mismatch, and other unsound boundaries. |

Coverage and test-fidelity share verification-quality guidance with complementary responsibilities.
Test doubles, large files, local error propagation, or machine-looking code are not defects by
themselves. Severity follows impact and likelihood.

## Evidence and verification

Each reviewer starts with a bounded set of paths, contracts, tests, and inventory facts. A subtree
finding can use declared evidence from a caller or schema outside that subtree without widening
where findings may be filed. Repository text and tool output are evidence; instructions embedded
in them cannot change the review or authorize commands.

Critical and high claims, later promotions, and expensive recommendations based mainly on
inference require a separate attempt to disprove them. The report distinguishes confirmed or
narrowed defects from refuted claims, items needing verification, and genuine design decisions.
If the host cannot provide a fresh reviewer context, the report records limited independence and
serious claims remain verification-required. Corroborating lenses are grouped by root cause.

## Resume and follow-up

Every fresh run has a unique timestamp-and-suffix directory and records the exact reviewed source,
including selected untracked inputs. Resume checks that binding again. Changed source or scope
requires a fresh run; the age of a run is only advisory. Older runs without a binding remain
readable as historical evidence.

Writing the report completes the audit stage. Filing and optional telemetry are separate choices;
an interruption can resume those follow-ups after the source check without rerunning the lenses.
The run finishes when each follow-up has been completed or explicitly skipped. Silence leaves a
choice pending. Findings become issues only on your explicit selection and authorization.

Telemetry is off by default. You see the full aggregate payload before any per-run approval to
post publicly. It excludes source fingerprints, code, paths, commit hashes, and finding text;
repository identity is never filled in automatically. The optional user-entered `--tag` remains
visible in that preview and never grants permission to send it.

## Usage

```
/ca:tribunal "[scope-path] [--tag <label>]"
```

An optional `scope-path` narrows the subtree. The full roster is considered, but only
applicable lenses run; launched and skipped lenses are recorded. `--tag <label>` supplies
a freeform label, not permission to send telemetry. Requesting the deep audit in ordinary
language selects the same procedure; cost acknowledgment still precedes dispatch.

## When to reach for it

Rare, deliberate, whole-codebase depth, not the routine sweep (`/ca:checkpoint`), not a diff review
(`/ca:review`), and never wired into a hot loop or schedule.
