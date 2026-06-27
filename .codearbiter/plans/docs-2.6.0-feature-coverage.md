# Plan — 2.6.0 docs push: narrative coverage for the release feature tracks

**Spec:** `.codearbiter/specs/docs-2.6.0-feature-coverage.md` (approved 2026-06-27, Lane: full, docs/no-TDD)
**Branch:** `docs/2.6.0-feature-coverage` · gates the `v2.6.0` tag alongside the relicense (PR #147).

Prose/asset work: there is **no `tdd`**. Each task's `maps-to` is the docs-site CI gate or grep that
proves it, in place of a tdd obligation. Execution authoring agent = `frontend-author` (Astro/Starlight
is frontend) with `design-quality-reviewer`.

---

## AC ledger (from the spec)

- **AC-1** — `concepts.md` "Provenance & context drift" section: drift detection, `code-map.md`, `/ca:context-check`, commit-gate auto-heal.
- **AC-2** — `concepts.md` "Just-in-time context injection" section: the `PreToolUse:Read` hook, the four tiers in priority order, the `**Governs:**` line.
- **AC-3** — `enforcement.md` board-transitions section: `/ca:task`, ADR-0008 commit-coupled flips.
- **AC-4** — `hooks.md` `PreToolUse:Read` injection-hook entry.
- **AC-5** — README farm var table gains `FARM_SAMPLES` + `FARM_TEMPERATURE` rows and a best-of-N note, inside the Feature Forge preview subsection.
- **AC-6** — README **How it works** mentions each of the three stable tracks with a link resolving to its docs-site section.
- **AC-7** — two new SVG diagrams (four-tier map; provenance drift→auto-heal flow), each with a non-empty `<title>`, referenced by a base-path-correct href from its concept section.
- **AC-8** — every hand-authored content page is reachable from the `astro.config.mjs` sidebar; no orphaned new page.
- **AC-9** — docs-site CI green: `npm run typecheck`, `npm run test`, `npm run build`, `npm run link-audit` each exit 0 in `site/`.
- **AC-10** — `design-quality-reviewer` clears the new prose and diagrams against `anti-slop-design` §3.A + §3.B; zero unresolved findings.
- **AC-11** — `python .github/scripts/check_badge_consistency.py` stays green.

---

## Task table

Docs-site content lives in `site/src/content/docs/`. Diagrams: match the **committed source location**
of the existing diagrams (verify `site/public/diagrams/` vs `site/src/assets/diagrams/` — whichever is
git-tracked, not a build artifact), referenced as `/codeArbiter/diagrams/<name>.svg`. "→ exit 0" means
the cited command passes.

| id | path(s) | verification (maps-to) | covers | depends-on |
|----|---------|------------------------|--------|------------|
| **T-01** | `site/<diagram-src>/four-tier-map.svg`, `…/provenance-drift-flow.svg` | both SVGs exist at the tracked diagram source path, each with a non-empty `<title>`; `grep '<title>'` matches; style matches an existing diagram (gate-model.svg) | AC-7 | — |
| **T-02** | `site/src/content/docs/concepts.md` | a "Provenance & context drift" heading exists naming drift detection, `code-map.md`, `/ca:context-check`, and auto-heal; references `/codeArbiter/diagrams/provenance-drift-flow.svg` (grep heading + terms + img ref) | AC-1 | T-01 |
| **T-03** | `site/src/content/docs/concepts.md` | a "Just-in-time context injection" heading naming the `PreToolUse:Read` hook, the four tiers in order, and the `**Governs:**` line; references `/codeArbiter/diagrams/four-tier-map.svg` (grep) | AC-2 | T-01, T-02 (same file) |
| **T-04** | `site/src/content/docs/enforcement.md` | a board-transitions section naming `/ca:task` and ADR-0008 commit-coupled flips (grep heading + terms) | AC-3 | — |
| **T-05** | `site/src/content/docs/hooks.md` | a `PreToolUse:Read` injection-hook entry describing the at-read context injection (grep) | AC-4 | — |
| **T-06** | `README.md` (Feature Forge → farm subsection) | the farm env-var table contains `FARM_SAMPLES` and `FARM_TEMPERATURE` rows plus a best-of-N note (grep) | AC-5 | — |
| **T-07** | `README.md` (How it works) | brief mentions of provenance, JIT injection, and board transitions, each with a link to its docs-site section anchor (grep mentions + links; link-audit confirms resolution) | AC-6 | T-02, T-03, T-04, T-06 (same file) |
| **T-08** | `site/` (+ `site/astro.config.mjs` only if an orphan is found) | `cd site && npm run typecheck && npm run test && npm run build && npm run link-audit` → all exit 0 (build catches orphan pages; link-audit catches dangling diagram/section links — covers AC-8 too) | AC-8, AC-9 | T-01..T-07 |
| **T-09** | new prose + diagrams (review) | `design-quality-reviewer` clears §3.A (no em-dash prose separators) + §3.B copy self-audit; zero unresolved findings | AC-10 | T-01..T-07 |
| **T-10** | (verification) | `python .github/scripts/check_badge_consistency.py` → exit 0 (docs changes do not touch command/skill/agent counts) | AC-11 | T-06, T-07 |

---

## Order & MVP slice

Dependency order: T-01 → T-02 → T-03; T-04, T-05, T-06 independent; T-07 (after T-02/03/04/06) →
T-08, T-09 (after all authoring) → T-10.

**MVP slice = the whole push** (T-01–T-10). This is one cohesive docs deliverable: the four tracks
documented, diagrams integral (the concept sections reference them, so link-audit fails if they are
missing), gates green. There is no smaller shippable slice that satisfies the spec's "each track has a
narrative home" core without leaving a dangling reference or an ungated change. No incremental tail.

---

## Coverage proof

AC-1→T-02 · AC-2→T-03 · AC-3→T-04 · AC-4→T-05 · AC-5→T-06 · AC-6→T-07 · AC-7→T-01 · AC-8→T-08 · AC-9→T-08 · AC-10→T-09 · AC-11→T-10.

Every AC has ≥1 task; every task covers ≥1 AC. Bijective.

---

## Status ledger

| task | status |
|------|--------|
| T-01 | ACCEPTED |
| T-02 | ACCEPTED |
| T-03 | ACCEPTED |
| T-04 | ACCEPTED |
| T-05 | ACCEPTED |
| T-06 | ACCEPTED |
| T-07 | ACCEPTED |
| T-08 | ACCEPTED |
| T-09 | ACCEPTED |
| T-10 | ACCEPTED |

---

## Notes (no `[NEEDS-TRIAGE]` raised)

- No `forge-status.ts` change: the three stable tracks (provenance, JIT injection, board transitions) are on-by-default, not Feature Forge previews; only the farm sampling (T-06) extends the existing farm preview and needs no allowlist entry.
- Do NOT edit auto-generated `reference/` pages.
- README edits are scoped to the How-it-works + Feature-Forge sections to avoid conflict with the relicense PR's license-section edits (both target `main`).
