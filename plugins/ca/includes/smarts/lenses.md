# SMARTS — lens reference (lazy)

Per-lens detail behind the one-line summaries in [`core.md`](core.md). `core.md` owns the role,
verdicts, cell rules and strength; this file only deepens what each lens asks. Load it only under
the condition `core.md` states — never for a routine scan the summaries already settle.

Each lens lists the question it answers, the considerations that usually decide it, the traps
that produce a wrong verdict, and the observation that settles an `Unknown` on it (the
`missing_observation` an Unknown cell names).

## Scalable

**Question:** does the option support growth in users, data, throughput or geography without an
architectural rewrite?

**Considerations:**
- User scale across the stated horizon — prototype, pilot, production.
- Data volume and its growth rate, including retained history and logs.
- Throughput shape: bursty versus steady, and the peak the design must absorb.
- Geographic spread: single region now, multi-region on the roadmap or not.

**Traps:** over-engineering for scale that never arrives; under-engineering for scale that is on
the roadmap; confusing performance (one request is fast) with scalability (many requests stay fast).

**Settles an Unknown:** the expected load or data volume at the stated horizon, or a measurement
of the option at that load.

## Maintainable

**Question:** can the system be understood, modified and extended later — including by agents —
without prohibitive effort?

**Considerations:**
- Comprehensibility for the next contributor, human or agent, without reading internals.
- Standard patterns versus bespoke abstractions.
- Documentation the option obliges someone to keep current.
- Refactoring blast radius when the option changes.
- Onboarding and hand-off cost to whoever owns the code next.

**Traps:** treating maintainability as one engineer's concern; underestimating the cost of a
bespoke pattern when agents write most of the code; ignoring the eventual hand-off.

**Settles an Unknown:** who maintains the code at the stated horizon, and whether the pattern
already exists in the codebase.

## Available

**Question:** is the system reachable and functional when needed, including under partial failure?

**Considerations:**
- Single points of failure the option introduces or removes.
- Failure of a bundled or external dependency, and what keeps working.
- Disconnected or degraded operation requirements.
- Time to recover from the common failure modes.
- The downtime the caller can actually accept.

**Traps:** conflating availability with high availability; designing for high availability the
project does not require; ignoring partial-availability states.

**Settles an Unknown:** the stated downtime tolerance, or how the option behaves when its
dependency is unreachable.

## Reliable

**Question:** does the option produce correct, predictable, durable outcomes?

**Considerations:**
- Atomicity and durability where they matter — the decision log, audit events, receipts.
- Idempotency of retried operations.
- State consistency across components.
- Recovery from failure without corruption.
- Reproducibility of builds, deployments and recorded evidence.

**Traps:** assuming the database or framework handles it without checking; underestimating the
reliability cost of distribution; ignoring long-tail durability.

**Settles an Unknown:** the failure the option must survive, and evidence of its behavior under it.

## Testable

**Question:** can the option be validated by deterministic, fast tests that cover meaningful
failure modes?

**Considerations:**
- Unit testability of the parts the option introduces.
- Integration and contract testing between components.
- Test data generation and isolation.
- Whether the real failure modes can be reproduced in a test, not just the happy path.
- The boundary between a throwaway spike and a test that must hold.

**Traps:** patterns that resist mocking or isolation; ignoring the cost of test infrastructure;
"tests later" for foundational components.

**Settles an Unknown:** whether a deterministic test can reproduce the failure mode the option
must handle.

## Securable

**Question:** does the option enable the project's security posture — as defined in
`${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — without retrofit?

**Considerations:**
- Authentication boundary: who the actor is.
- Authorization boundary: what the actor may do.
- Audit boundary: what is recorded, and whether it can be trusted.
- Secret handling.
- Attack surface: every bundled component and exposed input.
- Default-deny versus default-allow stance.
- Supply-chain integrity: provenance, licenses, signatures.

**Traps:** bolting security on after the architecture is set; confusing compliance with security;
underestimating the hardening burden of bundled components.

**Settles an Unknown:** the trust boundary the option crosses, and the control
`security-controls.md` requires there.
