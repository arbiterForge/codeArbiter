# Spec: docs-site product redesign

**Status:** APPROVED 2026-06-27 by brennonhuff@gmail.com (brainstorming Phase 4) — as-is, both load-bearing calls (no-harness gate, Concepts 9-way split) confirmed.
**Lane:** `/ca:sprint` (autonomous), preceded by this content/IA audit
**Slug:** `docs-site-product-redesign`
**Governs:** `site/**`

## Problem

The codeArbiter docs site (`site/`, Astro + Starlight) has strong *content* but weak
*presentation and coverage*. A first-time visitor — the adoption funnel's primary caller
(repo-as-onboarding; "show a gate catching a real mistake") — lands on an overloaded splash,
a low-separation sidebar lopsided by a 74-item generated Reference under a 4-item curated top,
empty gutters that read as unfinished, and — most damning — **no way to learn how to install
or use the product**. Measured against the Diátaxis framework, the site has built the two hard
quadrants (Reference, Explanation) and skipped the two visitors hit first (Tutorial, How-to).

"Done" looks like documentation you'd expect from an expensive enterprise product: a real
Getting-Started on-ramp, task-oriented Guides, balanced and legible navigation, and a landing
that earns the fold — in the gold/slate brand, reading in *feel* like docs.astro.build.

## Audit findings (Diátaxis coverage, current)

| Quadrant | codeArbiter today | Action |
|---|---|---|
| Tutorial (learning) | absent | author Quickstart |
| How-to (tasks) | absent | author a Guides section (~9) |
| Reference (information) | strong (74 generated + hooks.md) | keep; restyle + collapse |
| Explanation (understanding) | strong (overview/concepts/enforcement) | keep; split overloaded Concepts |

Critical gap: **no install page exists** — the funnel has no on-ramp.

## Scope

### In
- **Design system**: retune `theme.css`/`landing.css`/`callouts.css` (or successors) to an
  enterprise-grade gold/slate system; fix the splash gutters and oversized hero glow; full
  light + dark parity.
- **Landing recompose**: above the fold = hero + the gate-catch terminal only; demote the
  command block, lane-flow diagram, and Forge showcase below it.
- **Sidebar/IA restructure** (target IA below): 4 balanced curated groups above a
  collapsed-by-default generated Reference.
- **Content — full Diátaxis fill**:
  - **Getting started**: Install (NEW), Quickstart (NEW), What is codeArbiter (from `overview`).
  - **Guides (NEW section)**: opt a repo in · the feature lane end-to-end · autonomous sprints
    (+`--farm`) · overriding a gate safely · recording ADRs · adding a dependency · releasing a
    version · the statusline · troubleshooting (`/ca:doctor`).
  - **Concepts split**: break the single `concepts.md` into per-concept pages (gated lanes,
    Feature Forge, SMARTS, ADRs, checkpoints, provenance/drift, JIT injection,
    persona/context-minimization, auditability).
  - **Security**: keep Enforcement + Hooks reference, surfaced as their own group.
- **Quality**: ALL docs-site work routed through the `anti-slop-design` bundle per medium
  (web / diagram / documents leaves), with `design-quality-reviewer` dispatched as the gate.

### Out / constraints
- **Build ON Starlight; keep `gen.ts`.** Not a rebuild off the framework. The reference
  generator (74 pages from plugin frontmatter) is the spine of maintainable reference docs and
  is preserved. ("Nothing must be conserved" applies to the *presentation and hand-authored
  content*, not the framework or the generator.)
- **No new test harness.** No pixel/visual snapshot tests, no axe/playwright standing suite.
  Quality is gated by `astro build`, built-page checks, and the anti-slop reviewer (see
  Testing posture). Stated here for the approval-gate record; not a silent reconciliation of
  the brainstorming single-test rule — every AC below is verifiable by one concrete check.
- **Reference *content* is generator-owned** — its *presentation* is in scope, its text is not.
- Not changing the plugin itself, hooks, or `.codearbiter/` framework docs.

## Target IA

```
Getting started   Install · Quickstart (first gate catch) · What is codeArbiter
Guides            opt-in · feature lane · sprints (+farm) · override · ADRs ·
                  add-dep · release · statusline · troubleshooting
Concepts          gated lanes · Feature Forge · SMARTS · ADRs · checkpoints ·
                  provenance/drift · JIT injection · persona & context · auditability
Security          Enforcement · Hooks reference
Reference         Commands(38) · Skills(21) · Agents(15)   [collapsed by default]
```

## Testing posture (resolves the single-test rule without a harness)

Each AC is verifiable by exactly one of: (a) `astro build` exit status; (b) a one-shot
existence/content check against built output (no standing harness); (c) a
`design-quality-reviewer` verdict against the `anti-slop-design` bundle. Visual taste,
gutters, and a11y/contrast are covered by the reviewer's layout/color/core leaves, not by
pixel assertions.

## Acceptance criteria

Build & integrity
1. `npm run build` in `site/` (which runs `gen` first) exits 0.
2. The build produces the full generated Reference (38 commands + 21 skills + 15 agents pages);
   the generator pipeline is unchanged in contract (page count preserved).
3. No broken internal links in the built site (build-time link check passes / Starlight
   reports none).

Getting started (content)
4. An **Install** page exists at a stable slug and contains the concrete install path
   (marketplace add + `/ca:init` + the `arbiter: enabled` opt-in).
5. A **Quickstart** page exists and walks: opt a repo in → run a first command → observe a
   gate catching a real mistake (the conversion mechanic, as a tutorial).

Information architecture
6. The built sidebar renders exactly four curated top groups (Getting started, Guides,
   Concepts, Security) above the generated Reference group.
7. The Reference subgroups (Commands, Skills, Agents) render collapsed by default.
8. `concepts.md` is split: each of the nine concepts exists as its own page at its own slug
   under a Concepts group.
9. The Guides group contains each of the nine named guides as a real (non-stub) page — each
   has a task-oriented title and at least one concrete step/command.

Landing
10. In built `index.html`, the first two content blocks in DOM order are the hero and the
    gate-catch terminal; the command block, lane-flow diagram, and Forge showcase all appear
    after them.
11. The hero renders without the oversized glow dead-space and without empty side gutters at
    desktop width (verified by `design-quality-reviewer` layout-leaf verdict).

Design quality (the load-bearing gate)
12. `design-quality-reviewer`, run against the landing (`medium-web` leaves), a representative
    doc page (`medium-documents`), and the diagrams (`medium-diagram`), returns no CRITICAL or
    HIGH findings.
13. The theme defines complete light AND dark token sets; both render with brand identity and
    contrast intact (reviewer core/color verdict).

MVP slice (ship-able floor if scope must be cut): AC 1–7, 10–13 + Install + Quickstart.
The nine Guides (AC 9) and the full Concepts split (AC 8) are the bulk and the first
de-scope candidates if the sprint must land partial.

## Open questions

- No new blocking `[CONFIRM-NN]` raised by this spec.
- Related (non-blocking): `[CONFIRM-08]` (site build-time deps `LGPL-3.0`/`0BSD`) is pre-existing
  and concerns dependencies already in `site/package-lock.json`; this work introduces no new
  runtime deps and does not depend on its resolution. If the redesign adds any build dep, it
  must clear the same license bar — flag at that point.

## Handoff

On approval: `/ca:sprint` against this spec. Each acceptance criterion becomes a sprint
obligation; the anti-slop bundle is the standing quality gate; hard gates (security, secrets,
merge-to-default) remain true stops. Recommended first batch = the MVP slice.
