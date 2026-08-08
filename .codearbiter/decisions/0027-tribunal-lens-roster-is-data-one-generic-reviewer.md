---
status: proposed
date: 2026-08-08
title: Tribunal lens roster is data; one generic lens-reviewer executes it
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/agents/tribunal-lens-reviewer.md, core/surface/skills/tribunal/*, plugins/*/agents/tribunal-lens-reviewer.md, plugins/*/skills/tribunal/*, plugins/*/routines/tribunal/*
---

# ADR-0027 — Tribunal lens roster is data; one generic lens-reviewer executes it

## Status
Proposed — decision content approved by SUaDtL@users.noreply.github.com on 2026-08-08 (plan
"tranquil-crunching-fog" v2 approved post-adversarial-review; explicit rulings "Tribunal-only
collapse" and "publish lens cards + redirects" the same day). Awaiting explicit ratification to
Accepted.

## Context

The tribunal lane shipped eleven `tribunal-<lens>-reviewer` agents whose bodies were ~73%
identical template (identical H2 skeleton, identical dispatch and write contracts) around the
14–18-line lens cards under `skills/tribunal/references/lenses/` — the cards already carried the
real mandate. Each agent description cost always-loaded registry context (~589 tokens on the
Claude host), and every contract change had to be replicated eleven times. The repo already
proved the generic-body + injected-assignment pattern (`scout`, `grader`). Adversarial review
(2026-08-08, three independent reviewers) confirmed the consolidation loses nothing structural:
per-lens model tiers are dispatch-time aliases, the wave partition and run/triage/telemetry
schemas key on `lens` (never an agent name), `scout` already dispatches six concurrent instances
of one agent type, and `build-surface.py` removes orphaned rendered agents on all managed
surfaces. The same review found the two real hazards — nine of eleven lenses would silently
lose their project-doc pre-reads unless the cards absorb them, and a uniform assignment opener
would blind the statusline's per-lens subagent labels — both addressed in the decision below.

## Decision

One generic agent, `tribunal-lens-reviewer`, replaces the eleven per-lens tribunal agents.

- The tribunal skill dispatches it once per active lens with an assignment block whose FIRST
  line is the title `Tribunal lens: <lens-slug> — <scope summary>` (the statusline derives
  subagent labels from the first non-role line).
- **The roster IS the set of cards** under `skills/tribunal/references/lenses/`. Adding a lens
  = one card + one cost-table row + one site lens page; no new agent.
- Lens cards absorb what only the agent bodies carried: a `## Scope emphasis` section and a
  `## Required reading` section naming that lens's project docs. The generic body reads
  whatever the card names; the card, not the body, is the mandate, and an assignment naming a
  lens with no card is a STOP, never an improvised mandate.
- Shared reviewer/author contracts are extracted per the lazy-load placement rule (2+ consumers
  → `includes/`): `includes/reviewer-contract.md` (findings format, review output template,
  gate-status rule, out-of-scope rule; the five gate reviewers point at it) and
  `includes/author-tdd-workflow.md` (backend/frontend authors point at it).
- The eleven public site URLs `/reference/agents/tribunal-<lens>-reviewer/` redirect to a new
  generated per-lens collection `/reference/tribunal-lenses/<lens>/` sourced from the cards, so
  per-lens public documentation survives the consolidation.

## Alternatives considered

- **Keep the eleven bodies, dedupe via a shared template include** — rejected: leaves eleven
  registry descriptions loaded and eleven files to update per contract change; the bodies held
  no unique content beyond what the cards now carry.
- **Collapse the checkpoint reviewers and authors too** — rejected (user ruling): only ~30%
  shared, genuinely distinct jobs, and proactive auto-dispatch selects on their distinct
  descriptions.
- **Merge `map-deps`/`map-structure` into one extractor** — rejected: different extraction
  targets; merging touches five surfaces for approximately zero context gain.
- **Move the two-line out-of-scope closer into the include for all carriers** — rejected for
  the six non-gate agents: forcing a file read to learn two lines inverts lazy-load economics;
  `includes/reviewer-contract.md` is canonical and those inline copies are deliberate.

## Consequences

- Agent count 28 → 18: README badge, `agents/INDEX.md`, ca-pi `generated/roles.json`, three CI
  tests re-pinned from 28 to 18, site landing agent floor lowered.
- Context saving is per-host (~589 tokens on the Claude host registry); ca and ca-pi are never
  co-installed, so per-host is the honest figure.
- A contract change lands once in the generic body or the shared include instead of eleven
  times; a new lens is data, not a new agent.
- `references/cost-and-models.md` is keyed by lens; the agent name is constant.

## Risks

- A lens card that under-specifies its mandate now has no agent body to fall back on — the
  card review burden rises. Mitigated by the absorbed Scope-emphasis/Required-reading sections
  and the malformed-assignment STOP.
- Old external links to the eleven agent pages depend on the redirect map staying in place.
- If a future host keys subagent telemetry by agent name rather than dispatch prompt, per-lens
  attribution would need the assignment title; today every schema keys on `lens`.
