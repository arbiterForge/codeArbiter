---
title: SMARTS
description: "The structured, multi-lens scoring rubric codeArbiter uses when weighing options during autonomous runs, with every verdict recorded in an append-only sprint log."
---

When codeArbiter must weigh options, and especially when `/ca:sprint` decides "as the user"
during an autonomous run, it doesn't pick on vibes. It runs a structured, multi-lens scoring
rubric called **SMARTS** and records the verdict: the options weighed, the lens scores, the
chosen option, and a confidence flag. Low-confidence calls are exactly what the user reviews
afterward. Nothing hides behind autonomy. Every auto-decision lands in an append-only sprint
log.

## The Six Lenses

SMARTS is an acronym. Every option is scored evenhandedly against the same six lenses, and the
analysis travels with the recommendation:

- **Scalable.** Supports growth in users, data, and throughput without an architectural rewrite. The trap is over-engineering for scale that never arrives, or under-engineering for scale that's already on the roadmap.
- **Maintainable.** Can be understood, modified, and extended later (including by agents) without prohibitive effort. Standard patterns over bespoke abstractions; mind the refactoring blast radius.
- **Available.** Reachable and functional when needed, including under partial failure. Watch for single points of failure, bundled-dependency failure, and recovery time.
- **Reliable.** Correct, predictable, durable outcomes: ACID where it matters (the decision log, audit events), idempotency, state consistency, and recovery without corruption.
- **Testable.** Validated by deterministic, fast tests that cover real failure modes. "Tests later" is a weak verdict.
- **Securable.** Enables the project's security posture (per `security-controls.md`) without a retrofit: authentication, authorization, audit, secret management, and a default-deny stance.

## Verdicts and Strength

Each lens gets one verdict word: **Strong**, **Adequate**, **Weak**, or **Indifferent** (the lens
does not differentiate the options at the current scale). A short, evidence-specific justification
follows. Vague appeals like "industry standard" or "best practice" are not evidence; a cell must
cite a concrete property of the option, a specific project constraint, or a named failure mode.

The recommendation itself carries one strength label: **strong** when multiple dominant lenses align
cleanly, **moderate** when they align with caveats or a single lens dominates, and **tied** when no
preferred option emerges. A tie is a legitimate result, surfaced as a genuine call for the user
rather than a forced pick.

SMARTS deliberately does not score cost, time-to-market, team-skill fit, or vendor lock-in. When
those matter, they are surfaced as non-SMARTS considerations alongside the table; they supplement the
analysis, never replace it.
