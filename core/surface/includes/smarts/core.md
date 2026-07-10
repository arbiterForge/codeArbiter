# SMARTS — lenses, cell rules, strength

The standardized evaluation for architectural variances. Apply the six lenses evenhandedly to every
option. This is the project's framework; do not substitute another. This `core` file is everything the
scoring path needs (decision-variance, the grader, the decision-challenger, and `/sprint` autonomous
scoring). The append-only **decision-log entry format** lives separately in
[`decision-log-format.md`](decision-log-format.md) — load it only when writing a log line.

## The six lenses

- **Scalable** — supports growth in users, data, throughput, geography without an architectural rewrite. Trap: over-engineering for scale that never arrives, or under-engineering for scale that's on the roadmap.
- **Maintainable** — can be understood, modified, and extended later (including by agents) without prohibitive effort. Standard patterns over bespoke abstractions; mind the refactoring blast radius and eventual hand-off.
- **Available** — reachable and functional when needed, including under partial failure. Watch single points of failure, bundled-dependency failure, recovery time. Do not conflate availability with high availability.
- **Reliable** — correct, predictable, durable outcomes. ACID where it matters (the decision log, audit events), idempotency, state consistency, recovery without corruption.
- **Testable** — validated by deterministic, fast tests that cover real failure modes. Unit + integration + contract; mind mockability and test-data isolation. "Tests later" is a Weak verdict.
- **Securable** — enables the project's security posture (per `{{PROJECT_DIR}}/.codearbiter/security-controls.md`) without retrofit. Authentication, authorization, audit, secret management, attack surface, default-deny stance, supply-chain integrity.

## Cell rules (hard)

Each SMARTS cell is a constraint, not a guideline. A non-conformant cell is rejected.

1. **Length cap** — at most 25 words per cell.
2. **Verdict-first** — every cell opens with one verdict word: `Strong` (performs well), `Adequate` (acceptable), `Weak` (poor), `Indifferent` (this lens does not differentiate the options at the current scale).
3. **Justification follows** — at most 20 words after the verdict.
4. **No hedging adverbs** — forbidden: potentially, might, arguably, perhaps, generally, tends to, could be, may. If genuinely uncertain, the verdict is `Indifferent`.
5. **Evidence specificity** — "industry standard," "best practice," "widely adopted" are not evidence. Cite a specific property of the option, a specific project constraint, or a specific failure mode.

## Strength of recommendation

Every recommendation carries exactly one strength label:

- **strong** — multiple dominant lenses align cleanly on one option; non-SMARTS factors confirm.
- **moderate** — dominant lenses align with caveats, or a single lens dominates.
- **tied** — no preferred option emerges. A legitimate output: "This is a coin flip under SMARTS — your call."

There is no `weak` level — a slight edge is `moderate`. When lenses conflict with no winner, state it
plainly, surface which lens the user has emphasized in prior decisions as input, and mark `tied`.
The `Precedent:` line under each table (decision-variance Phase 3) is how that emphasis is surfaced
systematically: 1–3 most-similar prior decisions by ID plus the observed lens pattern, or
`Precedent: none on record` when history is thin — never an invented pattern.

SMARTS does not cover cost, time-to-market, team-skill fit, vendor lock-in, or political
acceptability. When these matter, surface them as **non-SMARTS considerations** alongside the table;
they supplement, never replace, the analysis.

## Worked example

**Variance:** authorization engine bundled in the deployment package vs. customer-provided.

| Lens | Bundled | External |
|---|---|---|
| Scalable | Adequate. Sub-ms decisions sufficient at 50-user scale. | Adequate. Same ceiling, adds a network hop. |
| Maintainable | Strong. One package owns versioning and integration. | Weak. Two release cycles must coordinate. |
| Available | Strong. Available whenever the system is. | Weak. Depends on customer infrastructure. |
| Reliable | Strong. Failure contained in the deployment boundary. | Weak. Failure surface includes customer network. |
| Testable | Strong. Local test env is one package install. | Weak. Requires standing up two services. |
| Securable | Strong. Self-contained mandate satisfied. | Weak. Cross-service auditing is harder. |

**Recommendation:** Bundle the engine. Strength: **strong** — Securable and Available dominate cleanly; no lens favors external enough to override.
