# SMARTS — lenses, cell rules, strength

The standardized evaluation for architectural variances. Apply the six lenses evenhandedly to every
option. This is the project's framework; do not substitute another. This `core` file is everything the
scoring path needs (decision-variance, the grader, the decision-challenger, and `/sprint` autonomous
scoring). The append-only **decision-log entry format** lives separately in
[`decision-log-format.md`](decision-log-format.md) — load it only when writing a log line.

## Step 0 — recorded-intent check (before any lens is scored; ADR-0025)

*Applies to `/sprint` autonomous scoring and `brainstorming` (spec shaping) ONLY. Exempt by name:
`decision-variance`, the `grader`, and the `decision-challenger` — on arbitration surfaces the
variance IS the recorded-intent check, and the decision-variance Phase 4 authority order, not this
step, ranks the record.*

Before scoring, check whether the project's record already answers or constrains the decision.
Sources, ranked by the Phase 4 authority order: an explicit user decision this session (including
the approved sprint spec) > a recorded, unsuperseded `decision-log.md` entry > an accepted ADR >
the three `plans/` artifacts; `CONTEXT.md` and `open-questions.md` (including its
Deferred-decisions sections) constrain at their recorded level. Load index-first: consult the ADR
index (`decision-log.md` or the `decisions/` filename listing) and plan section headings only;
load a body only after the index names it relevant; never bulk-read `plans/` or `decisions/`
(ORCHESTRATOR §3's no-bulk-reads rule).

Three outcomes:

- **Answered** — a source already decides it. Conform to the highest-ranked source and cite it.
  A wanted contradiction routes to `/reconcile` or ADR supersession in interactive lanes; under
  `/sprint`, an answered-but-contradicting outcome IS the contradiction hard gate — stop and
  surface, never a mid-sprint reconcile dispatch. A lower-ranked record answering against a
  higher-ranked steer follows the steer and logs the divergence with both citations — never
  silently conform downward.
- **Constrains** — the record narrows but does not decide. Feed the citation into the affected
  cells; it satisfies the evidence-specificity rule below.
- **Silent** — no record speaks. Proceed to the lenses and state `intent: silent`.

Fail-soft: an absent `plans/` or `decisions/` directory is not a gap to surface and never a STOP —
record `intent: silent — no decomposition record` and proceed.

## The six lenses

- **Scalable** — supports growth in users, data, throughput, geography without an architectural rewrite. Trap: over-engineering for scale that never arrives, or under-engineering for scale that's on the roadmap.
- **Maintainable** — can be understood, modified, and extended later (including by agents) without prohibitive effort. Standard patterns over bespoke abstractions; mind the refactoring blast radius and eventual hand-off.
- **Available** — reachable and functional when needed, including under partial failure. Watch single points of failure, bundled-dependency failure, recovery time. Do not conflate availability with high availability.
- **Reliable** — correct, predictable, durable outcomes. ACID where it matters (the decision log, audit events), idempotency, state consistency, recovery without corruption.
- **Testable** — validated by deterministic, fast tests that cover real failure modes. Unit + integration + contract; mind mockability and test-data isolation. "Tests later" is a Weak verdict.
- **Securable** — enables the project's security posture (per `<project-root>/.codearbiter/security-controls.md`) without retrofit. Authentication, authorization, audit, secret management, attack surface, default-deny stance, supply-chain integrity.

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
