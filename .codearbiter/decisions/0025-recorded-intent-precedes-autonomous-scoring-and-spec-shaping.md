---
status: accepted
date: 2026-08-07
title: Recorded intent precedes autonomous scoring and spec shaping
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/includes/smarts/core.md, core/surface/SPRINT.md, core/surface/agents/grader.md, core/surface/skills/brainstorming/SKILL.md, core/surface/skills/decision-variance/SKILL.md, core/surface/agents/decision-challenger.md, plugins/*/includes/smarts/core.md, plugins/*/SPRINT.md, plugins/*/agents/grader.md, plugins/*/skills/brainstorming/SKILL.md, plugins/*/routines/brainstorming/SKILL.md
---

# ADR-0025 — Recorded intent precedes autonomous scoring and spec shaping

## Status
Accepted — explicitly ratified by SUaDtL@users.noreply.github.com on 2026-08-07 ("accept both").
Decision content approved the same day in the `recorded-intent-kernel-campaign` sprint spec
(rev 2, adversarially reviewed).

## Context

SMARTS scores option quality; it does not check conformance to the project's own recorded intent.
Two surfaces decide without consulting the record: `/sprint` autonomous scoring (a sprint can
contradict a Layer-4 forced trade-off overnight, and no lens catches it) and `brainstorming`'s
Phase 2 approach choice (specs are checked against `CONTEXT.md` only — never against accepted
ADRs, `plans/01–03`, or recorded deferrals). The arbitration surfaces — `decision-variance`, the
`grader`, the `decision-challenger` — are NOT gaps: there the variance IS the recorded-intent
check, and the decision-variance Phase 4 authority order already ranks the record.

## Decision

A **Step 0 — recorded-intent check** precedes SMARTS scoring, scoped as follows:

- **Applies to:** `/sprint` autonomous scoring and `brainstorming` (spec shaping).
- **Exempt by name:** `decision-variance`, the `grader`, and the `decision-challenger` —
  arbitration ranks the record via the Phase 4 authority order; a "conform" rule there would
  invert that order and install the grader's own anti-pattern #2 as required procedure.
- **Intent sources, ranked by the decision-variance Phase 4 authority order:** an explicit user
  decision this session (including the approved sprint spec) > a recorded, unsuperseded
  `decision-log.md` entry > an accepted ADR > `plans/01–03`; plus `CONTEXT.md` and
  `open-questions.md` (including Deferred-decisions sections). The raw `.decompose-draft/`
  interview layers are NOT a source (pre-review positions; deleted at decompose Phase 6 by
  design).
- **Three outcomes:** *answered* — conform to the highest-ranked source; in interactive lanes a
  wanted contradiction routes to `/ca:reconcile` or ADR supersession; under `/sprint` an
  answered-but-contradicting outcome IS the contradiction hard gate (never a mid-sprint
  reconcile dispatch, per SPRINT.md's Rule-1 override). *Constrains* — the citation feeds the
  SMARTS cells per the existing evidence-specificity rule. *Silent* — proceed and state
  `intent: silent`.
- **Sprint hard gate with stale-record valve:** an auto-decision contradicting an accepted ADR
  or a recorded deferral is never auto-decided. Valve: the sprint-start intent read runs before
  Phase 1 spec approval and surfaces plausibly-touched records at the interactive gate (a
  pre-ruling there is a user decision); a deferral whose recorded re-evaluation trigger has
  occurred is reopened, not treated as a contradiction; one stop per record per sprint.
- **Cost bounds are normative:** index-first loading (ADR index / plan section headings; bodies
  only after the index names them relevant; never bulk-read `plans/` or `decisions/`, per
  ORCHESTRATOR §3), and fail-soft on all surfaces (absent `plans/` or `decisions/` records
  `intent: silent — no decomposition record` and never STOPs — brownfield repos are the dominant
  consumer path and never gain a new block).
- **Log field:** sprint-log entries carry `intent:` positioned after the `confidence:` token (or
  on a body line) — never before it, which would pollute harvested board titles through the
  positional parser. An answered decision logs `confidence: high` with the citation in the
  SMARTS-verdict slot.

## Alternatives considered

- **Step 0 in shared `smarts/core.md` for all four consumers** — rejected (adversarial review,
  CRITICAL): it pre-empts arbitration, lets a rank-4 artifact defeat a rank-1 user steer, and
  contradicts the challenger's charter through its own required reading.
- **Also archive the raw `.decompose-draft/` layers as an intent source** — rejected by user
  ruling 2026-08-07: pre-review positions create a second, lower-fidelity source of truth that
  the authority order would then have to rank.
- **Auto-decide contradictions with a low-confidence log entry instead of a hard gate** —
  rejected by user ruling 2026-08-07: a night of work built on an overruled ADR is the exact
  failure the check exists to prevent.
- **Extend the check to `writing-plans`** — rejected: the chain is record→spec→plan→code, each
  stage checking exactly one level up; the plan lane already proves spec conformance via the
  AC ledger, and re-checking is double ceremony.

## Consequences

`/sprint` and `brainstorming` consult the record before deciding; contradictions surface at the
cheapest point (spec shaping) or stop autonomy (sprint) instead of shipping. `brainstorming`
gains a bounded per-feature read cost (index-first, pinned by structural test). The
`decision-variance` exemption is normative text: that skill's authority order remains the sole
ranking of the record on arbitration surfaces.

## Risks

A stale record stops sprints more often (mitigated by the valve; a repeatedly-tripping ADR is
routed to supersession in the sprint summary, and SPRINT.md's diagnostic names stale-record as a
cause). Index-first loading depends on index quality — a decision-log that drifts from the ADR
directory weakens the check. Proven wrong if: the intent check blocks a brownfield repo, the
sprint gate stops repeatedly on records whose triggers had occurred, or measured brainstorming
token cost grows materially despite the index-first rule.
