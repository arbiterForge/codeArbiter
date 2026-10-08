# SMARTS — design-quality rubric

SMARTS is codeArbiter's six-lens design-quality rubric for material engineering solution choices.
Workflow owners decide when a choice needs a scan, a full comparison, or delegated autonomous
handling; SMARTS itself does not grant authority. Architectural variance (decision-variance, the
grader, the decision-challenger) is one consumer of the rubric, not the definition of the framework.
Apply the six lenses evenhandedly to every option; this is the project's framework, do not substitute
another. This `core` file is everything a routine evaluation needs; the per-lens detail in [`lenses.md`](lenses.md)
is loaded only when a case named under the lenses below arises. The append-only **decision-log entry
format** lives separately in [`decision-log-format.md`](decision-log-format.md) — load it only when
writing a log line.

## Evaluation depths

1. **Scan** — a lightweight six-lens fitness pass for ordinary solution shaping: name the material strengths, weaknesses, unknowns and decisive lenses; no full table is required in user-visible output.
2. **Comparison** — the full option-by-option table, when two or more materially plausible approaches exist, when the user explicitly asks for a full SMARTS read, or when reconciliation or arbitration requires it.
3. **Delegated decision** — the authority-bearing path an approved `/sprint` uses for in-scope method decisions, recorded through the typed `smarts-apply` boundary where it applies.

All three depths use the semantics in this file; they differ in presentation, persistence and
decision authority, not in what the acronym means.

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
(arbiter.md §3's no-bulk-reads rule).

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

## Context envelope

Before judging a material choice, establish only the context that makes the lenses meaningful:

- **decision** — the actual choice being made, stated when the request leaves it implicit.
- **scope/horizon** — the bounded system and planning horizon, when they change a verdict.
- **scale expectation** — only when scale could differentiate the options.
- **failure/availability expectation** — only when failure behavior could differentiate the options.
- **security/trust boundary** — only when it bears on Securable.
- **non-SMARTS constraints** — cost, schedule, team skill, vendor or stakeholder constraints, only when they materially affect the recommendation.

The envelope is scope-sized and fail-soft. No dimension is required for every choice, and it creates
no new project or configuration file: existing project context, the active spec, explicit user
steering and relevant recorded decisions supply the evidence when available.

## The six lenses

The summaries below settle most verdicts. Load the per-lens reference
[`lenses.md`](lenses.md) only when a verdict turns on a consideration these summaries do not
settle, or when the user asks for a full SMARTS read — never for a routine scan.

- **Scalable** — supports growth in users, data, throughput, geography without an architectural rewrite. Trap: over-engineering for scale that never arrives, or under-engineering for scale that's on the roadmap.
- **Maintainable** — can be understood, modified, and extended later (including by agents) without prohibitive effort. Standard patterns over bespoke abstractions; mind the refactoring blast radius and eventual hand-off.
- **Available** — reachable and functional when needed, including under partial failure. Watch single points of failure, bundled-dependency failure, recovery time. Do not conflate availability with high availability.
- **Reliable** — correct, predictable, durable outcomes. ACID where it matters (the decision log, audit events), idempotency, state consistency, recovery without corruption.
- **Testable** — validated by deterministic, fast tests that cover real failure modes. Unit + integration + contract; mind mockability and test-data isolation. "Tests later" is a Weak verdict.
- **Securable** — enables the project's security posture (per `{{PROJECT_DIR}}/.codearbiter/security-controls.md`) without retrofit. Authentication, authorization, audit, secret management, attack surface, default-deny stance, supply-chain integrity.

## Verdicts

Every evaluated lens takes exactly one verdict:

- **Strong** — performs well for the stated context.
- **Adequate** — acceptable for the stated context.
- **Weak** — materially poor for the stated context.
- **Indifferent** — evidence shows the lens does not materially differentiate the options at the stated context and horizon. If any option marks a lens `Indifferent`, every option marks it `Indifferent`. In a single-option scan there is nothing to differentiate, so Indifferent means the lens is not material to this choice at the stated context; a lens that matters but lacks evidence is `Unknown`, never `Indifferent`.
- **Unknown** — the evidence needed to judge the lens is missing, contradictory or not yet established. Every Unknown names its missing observation (`missing_observation`) and states whether it is decision-critical (`decision_critical`: true when that observation could change the selected option); no other verdict carries those fields.

`Unknown` is not neutral: never treat it as `Indifferent`, `Adequate` or a pass, and never map it to
one. A recommendation may stand with a non-critical Unknown only when the output names the missing
observation and why it does not control the decision. A decision-critical Unknown blocks a `strong`
recommendation, blocks selecting the option that carries it, and is surfaced before any irreversible
or authority-bearing choice. A non-critical Unknown never shields a dominated option: on the selected
option it is no better than the other option's verdict on that lens, and strictly worse than a compared
`Strong`.

## Cell rules (hard)

Each SMARTS cell is a constraint, not a guideline. A non-conformant cell is rejected.

1. **Length cap** — at most 25 words per cell.
2. **Verdict-first** — every cell opens with one verdict word: `Strong`, `Adequate`, `Weak`, `Indifferent` or `Unknown`.
3. **Justification follows** — at most 20 words after the verdict; an `Unknown` justification names the missing observation and whether it is decision-critical.
4. **No hedging adverbs** — forbidden: potentially, might, arguably, perhaps, generally, tends to, could be, may. If genuinely uncertain, the verdict is `Unknown` with its missing observation.
5. **Evidence specificity** — "industry standard," "best practice," "widely adopted" are not evidence. Cite a specific property of the option, a specific project constraint, or a specific failure mode.

## Conflicting lenses and priority

SMARTS stays qualitative: never count `Strong` cells, assign weights, sum or compute percentages to pick a winner.
Per-lens dominance — one option no worse on every lens and better on at least one — is an ordinal
comparison, not a score. When lenses conflict, apply preference evidence in this order:

1. explicit current user or approved-spec priority;
2. explicit project priority already recorded in project context or an accepted decision;
3. relevant prior-decision precedent, labelled as precedent, not authority;
4. no assumed priority.

Absent explicit priority evidence, a tied comparison stays tied.

## Strength of recommendation

Every recommendation carries exactly one strength label:

- **strong** — dominant lenses align cleanly on one option, non-SMARTS factors confirm, and no option carries a decision-critical Unknown.
- **moderate** — dominant lenses align with caveats, or a single lens dominates.
- **tied** — no preferred option emerges. A legitimate output: "This is a coin flip under SMARTS — your call."

There is no `weak` level — a slight edge is `moderate`. The `Precedent:` line under each table
(decision-variance Phase 3) surfaces step 3 of the priority order: 1–3 most-similar prior decisions by
ID plus the observed lens pattern, or `Precedent: none on record` when history is thin — never an
invented pattern, and never authority on its own.

SMARTS does not cover cost, time-to-market, team-skill fit, vendor lock-in, or political
acceptability. When these matter, surface them as **non-SMARTS considerations** alongside the
analysis; they supplement, never replace it, and never become a seventh lens.

## Design rationale record

An approved full-lane spec keeps a concise SMARTS design rationale; it is design evidence, not a
source of execution authority. For a typed HTML spec, write it through the existing mutation
operations with this convention, with no spec-schema change:

- the chosen approach and its trade-off live in the existing `approach` record (`choice`, `tradeoff`);
- a `decisions` record carries each material decision the SMARTS pass settled, and `approach.binding_decision_refs` cites it;
- one `sections` record with the fixed id `SEC-SMARTS` (title "SMARTS design rationale") holds one block each for: alternatives considered or the single-option statement; decisive lenses; material Weak and Unknown observations, each Unknown with its missing observation and whether it is decision-critical; load-bearing assumptions; non-SMARTS considerations; and priority evidence when one influenced the recommendation.

Read the rationale back with the existing read operations; never hand-edit or parse rendered HTML.
A legacy Markdown spec keeps the rationale in one stable `## SMARTS design rationale` section that
carries the same parts in the same order.

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
