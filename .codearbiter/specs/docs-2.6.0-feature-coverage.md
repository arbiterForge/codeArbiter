# Spec — 2.6.0 docs push: narrative coverage for the release feature tracks

**Slug:** `docs-2.6.0-feature-coverage` · **Lane:** full (docs, no TDD) · **Status:** approved (2026-06-27)
**Governs:** site/src/content/docs/concepts.md, site/src/content/docs/enforcement.md, site/src/content/docs/hooks.md, README.md

> Gates the `v2.6.0` tag. The release is paused on branch `release/v2.6.0` (nothing tagged).
> This is prose/asset work: there is no TDD. The quality gates are the docs-site CI
> (`typecheck` + `vitest` + `build` + `link-audit`), `anti-slop-design`, and the
> `design-quality-reviewer`, in place of unit tests.

---

## Problem

ca 2.6.0 bundles four user-facing capability tracks, but their narrative coverage lags the code.
Three (context-drift provenance #145, commit-gate board transitions #144, file-scoped context
injection #146) appear only as command-catalog rows or not at all; #146 is absent from every
narrative surface. A consumer reading the README or the docs site cannot learn what these features
do or how to use them. Releasing now tags a payload whose marquee features are unexplained.

**Caller who feels it:** a consumer or evaluator reading `README.md` and the docs site to adopt or
understand codeArbiter; and the maintainer who wants 2.6.0 to ship documented.

**Done looks like:** each 2.6.0 track has a narrative home (a docs-site concept section, a hooks
entry, or a README table row), registered and rendering, supported by a diagram where it clarifies,
anti-slop-clean, with every docs-site CI gate green.

---

## Scope

**In scope**
- **Docs site (primary narrative home), `site/src/content/docs/`:**
  - `concepts.md` — a new **Provenance & context drift** section (#145): drift detection, the
    SessionStart drift line, `.codearbiter/code-map.md`, `/ca:context-check`, and commit-gate
    auto-heal.
  - `concepts.md` — a new **Just-in-time context injection** section (#146): the `PreToolUse:Read`
    hook, the four-tier file-to-knowledge map (security-controls > decisions > specs > provenance),
    the `**Governs:**` spec-header line, and the budget/dedup/fail-open properties.
  - `enforcement.md` — a new **Board transitions land with the work** section (#144): `/ca:task`,
    the commit-gate board-sync chokepoint, and ADR-0008 (flips ride the work commit).
  - `hooks.md` — a new entry for the `PreToolUse:Read` injection hook.
- **Two new SVG diagrams** in the docs-site diagram asset dir, matching the existing diagram style:
  the four-tier file-to-knowledge map, and the provenance drift-to-auto-heal flow. Each carries an
  accessible `<title>`/`<desc>`, a base-path-correct href, and is referenced from its section.
- **README (light touch):**
  - A brief mention of provenance, JIT injection, and board transitions in **How it works**, each
    linking to its docs-site section (no full duplicate narrative).
  - **Feature Forge → Pluggable execution farm**: add `FARM_SAMPLES` and `FARM_TEMPERATURE` rows to
    the env-var table plus a one-line best-of-N note (#137), inside the existing preview subsection.

**Out of scope**
- Editing the auto-generated `reference/` pages (regenerated from `plugins/ca/**` at build).
- New features, and any `forge-status.ts` `PREVIEW_COMMANDS` change — the three stable tracks are
  on-by-default, NOT Feature Forge previews; only the farm sampling extends the existing farm preview
  and needs no new allowlist entry.
- Wholesale rewrite of existing pages; a docs-site redesign; new top-level pages or sidebar groups
  (coverage lands as sections in already-registered pages).
- `plugins/ca/README.md` deep changes (it intentionally defers to the repo README).
- The CHANGELOG reconciliation and the tag itself — those are the paused `/ca:release` flow, resumed
  after this ships.

---

## Acceptance criteria

Each is verifiable by a single structural check or a named reviewer.

- **AC-1** — `concepts.md` contains a "Provenance & context drift" section naming drift detection,
  `code-map.md`, `/ca:context-check`, and commit-gate auto-heal (grep headings + terms).
- **AC-2** — `concepts.md` contains a "Just-in-time context injection" section naming the
  `PreToolUse:Read` hook, the four tiers in priority order, and the `**Governs:**` line (grep).
- **AC-3** — `enforcement.md` contains a board-transitions section naming `/ca:task` and ADR-0008
  commit-coupled flips (grep).
- **AC-4** — `hooks.md` contains a `PreToolUse:Read` injection-hook entry (grep).
- **AC-5** — the README farm var table contains `FARM_SAMPLES` and `FARM_TEMPERATURE` rows and a
  best-of-N note, within the Feature Forge preview subsection (grep).
- **AC-6** — README **How it works** mentions each of the three stable tracks with a link resolving
  to its docs-site section (grep links; link-audit confirms resolution).
- **AC-7** — two new SVG diagram files exist in the diagram asset dir, each with a non-empty
  `<title>`, referenced by a base-path-correct href from its concept section (file exists + grep
  `<title>` + grep the reference).
- **AC-8** — every hand-authored content page is reachable from the `astro.config.mjs` sidebar; no
  orphaned new page (build + sidebar check).
- **AC-9** — the docs-site CI gates pass: `npm run typecheck`, `npm test`, `npm run build`, and
  `npm run link-audit` each exit 0 in `site/`.
- **AC-10** — `design-quality-reviewer` clears the new prose and diagrams against `anti-slop-design`
  §3.A (no em-dash prose separators) and §3.B (copy self-audit); zero unresolved findings.
- **AC-11** — `python .github/scripts/check_badge_consistency.py` stays green (docs changes do not
  touch command/skill/agent counts).

---

## Open questions

None blocking. Two scope choices resolved during brainstorming, recorded here:
- README depth: docs-site is the primary narrative home; README gets brief linking mentions only,
  not duplicate sections (avoids two-place drift).
- Diagrams: in scope (two new SVGs), matching the existing diagram style.

## Notes

- Execution is prose/asset work: tasks route to `frontend-author` (the docs site is Astro/Starlight
  frontend) with `design-quality-reviewer`, and each task's verification maps to a docs-site CI gate
  or a grep assertion, NOT a `tdd` obligation.
- On approval and completion, resume `/ca:release` for 2.6.0 (CHANGELOG reconciliation already
  scoped: roll in #138/#139/#143/#145/#146, broaden the intro, date 2026-06-27), then tag.
