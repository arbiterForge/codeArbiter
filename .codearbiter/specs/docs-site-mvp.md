# Spec — docs-site-mvp: codeArbiter documentation site (MVP)

status: APPROVED — 2026-06-17, by repo owner (Phase 1 STOP gate cleared)
slug: docs-site-mvp
created: 2026-06-17
lane: full
backend: `--farm` (Feature Forge preview) for the generator slice
relates-to: [CONFIRM-05] (Feature Forge promotion bar for `--farm`) — this sprint *produces evidence*
toward that bar (real-run first-pass vs. escalation rates on a JS-heavy, test-dense slice). It does
**not** resolve it; promotion stays a separate owner decision. This is Step 6 of the token-efficiency
investigation (`docs/investigations/token-efficiency.md`).

## Problem

codeArbiter has no published documentation site. Equally, `--farm` has never been validated on a real,
non-trivial run — its escalation behavior on genuine multi-task labor is unmeasured (CONFIRM-05). A
documentation site whose reference section is **auto-generated from the plugin's own frontmatter** is a
good first artifact: low-sensitivity, JS/TS-native, and decomposable into many small TDD units — exactly
the shape that gives the farm real, samplable labor.

## Goals (this sprint)

1. **A buildable MVP docs site** under `site/` using Astro Starlight (JS/TS only — no Python toolchain),
   serving locally, with hand-written narrative for Overview and Concepts.
2. **A living, auto-generated reference** — a TypeScript generator that reads frontmatter
   (`name`, `description`, `tools`, `model`) from `plugins/ca/commands/*.md`,
   `plugins/ca/skills/*/SKILL.md`, and `plugins/ca/agents/*.md` and emits one reference page per source
   file plus a sidebar/index. The reference regenerates from the plugin and cannot drift.
3. **A measurement** — exercise `--farm` over ≥12 granular, independent failing-test→pass units (the
   generator), and report first-pass vs. escalation broken down by task, flagging any circuit-breaker trip.

## Hard tech constraints (from the owner, non-negotiable)

- Site generator: **Astro Starlight**. No MkDocs, no Python-based generator.
- Generator + tests in **TypeScript**. Test runner: **Vitest**. Package manager: **npm**, Node LTS.
- `plugins/ca/**` is **READ-ONLY** source. The generator reads it; nothing in the sprint modifies it.
- Site lives in `site/`. `site/node_modules`, `site/dist`, `site/.astro` are gitignored.
- Minimal deps beyond Astro/Starlight/Vitest/TS.
- **Do NOT deploy/publish** without explicit owner OK. Build + serve locally only.

## Design decisions (decided here; owner approves at the gate)

- **Frontmatter parsing: hand-rolled, dep-free line parser** (not the `yaml` package). Rationale:
  (a) frontmatter is flat `key: value`; (b) "minimal deps"; (c) the explicit "malformed YAML must not
  throw" requirement is cleaner to specify against our own parser; (d) more small testable units = better
  farm signal. SMARTS: strong (Simplicity + Maintainability + project fit).
- **Field heterogeneity is the core test surface.** Verified against source: commands carry only
  `description` + `argument-hint` (no `name`/`model`/`tools`); skills carry `name` + `description`;
  agents carry all four. The parser must treat missing fields as absent (not errors), preserve/ignore
  extra fields, and derive a display name for commands from the filename. This *is* the
  missing/extra/edge-field test matrix the owner asked for.
- **Generator = pure functions + a thin filesystem orchestrator.** Each behavior is its own module/file
  with its own test, so farm tasks are worktree-isolated and parallel (one impl file in scope per task;
  the failing test is authored by Claude and never touched by the worker).
- **Output target:** generator emits Markdown reference pages into
  `site/src/content/docs/reference/{commands,skills,agents}/` plus a generated sidebar data file
  (`site/src/generated/sidebar.json`) that `astro.config.mjs` consumes, plus a reference index page.
- **Farm scope boundary (the measurement boundary):** the **generator + its unit tests** are the farm
  slice (Claude authors each failing test; the worker authors each impl). The Astro scaffold,
  `astro.config`, narrative prose (Overview, Concepts), README, and `.gitignore` are **Claude-authored**
  setup/prose — not farm-testable units, so they are not dispatched to the farm.

## Acceptance criteria

- **AC-01** — `site/` is an npm project (Node LTS) with Vitest + TypeScript wired; `npm test` runs.
- **AC-02** — frontmatter splitter separates a `---`-delimited block from the body; returns a null block
  for files with no frontmatter; never throws on empty input.
- **AC-03** — field parser turns a flat `key: value` block into a record; missing keys are simply absent.
- **AC-04** — field parser preserves/ignores extra fields (e.g. `argument-hint`) without error.
- **AC-05** — field parser does not throw on malformed lines (no colon, blank lines); returns a partial.
- **AC-06** — a doc parser composes split+fields and never throws on edge inputs (empty file, body-only).
- **AC-07** — slugger produces stable kebab-case slugs; slug assignment de-duplicates collisions deterministically.
- **AC-08** — source classifier maps a path to `command` | `skill` | `agent`.
- **AC-09** — display-name derivation: skills/agents use the `name` field; commands derive from filename.
- **AC-10** — agent page renders model tier + tools list + name + description; missing `model` is handled.
- **AC-11** — command page renders name + description (no model/tools section).
- **AC-12** — skill page renders name + description.
- **AC-13** — source collector reads the three globs from a directory; empty dir → empty list; no throw.
- **AC-14** — index/sidebar builder lists every generated page, grouped by type, stable order.
- **AC-15** — full generator run emits exactly one page per source file (no collisions) and is **idempotent**
  (run twice → byte-identical output).
- **AC-16** — site builds (`npm run build`) and serves (`npm run dev`); reference pages are present and
  regenerated from the plugin; the generator is wired into a pre-build/pre-dev npm script.
- **AC-17** — `site/README.md` explains how to run the site, run the tests, and how the generator works;
  the sprint summary states what deploying would take (GH Pages workflow + versioning against releases).

## Non-goals / deferred

- Deployment / GH Pages publish (owner OK required; documented as a follow-up, not built).
- Polished visual design, search tuning, versioned docs, i18n.
- Any change to `plugins/ca/**` (read-only).
- Resolving CONFIRM-05 (this run only adds evidence).

## Measurement read-out (Step 6)

After the farm slice merges, report first-pass vs. escalation from `.farm/farm-report.json`
(`python tools/farm-first-pass.py`), broken down across the generator's tasks, and flag any
`FARM_ABORT_ESCALATION_RATE` circuit-breaker trip (cheap-model labor falling back to the Max pool).
