# Spec: docs-site overhaul (audit remediation)

**Status:** APPROVED 2026-07-02 by brennonhuff@gmail.com (plan-mode approval; babysat lane campaign)
**Lane:** sequenced babysat PRs (tribunal-remediation pattern) — Fable specs/reviews, Sonnet-medium authors
**Slug:** `docs-site-overhaul`
**Governs:** `site/**` (+ read-only build-time reads of `plugins/ca/**`; zero plugin file changes)
**Continues:** `docs-site-product-redesign` (2026-06-27, shipped)

## Problem

An outside-in audit of the live site (2026-07-02, written without codebase knowledge) surfaced
four concentrated failures behind an otherwise sound Diátaxis structure:

1. **~89 generated reference pages are one-sentence stubs** — the single biggest credibility
   drain for the adoption funnel.
2. **Every root-absolute content link 404s in production.** 74 links across 18 files render
   without the `/codeArbiter/` base. Root cause is ours, not the authors': the convention
   comment at `site/astro.config.mjs:33-39` claims Starlight base-maps `](/slug)` links — it
   does not — and `site/scripts/link-audit.ts:76/81` silently skips exactly that class
   (resolves against `dist/` where files exist regardless of base), so CI stays green while
   production is broken.
3. **Three voices fight** — persona-spec register addressing the model as "you"
   (`overview.md:11`), negation-triad aphorisms repeated past the landing page, and
   internal-spec fossils (a version-headed `## 2.5.2 Hardening` section in `enforcement.md`).
4. **Missing table-stakes pages** — `.codearbiter/` configuration reference, glossary, FAQ,
   uninstall/disable, compatibility matrix, on-site changelog.

Audit claims verified against the codebase and **dropped where stale**: sidebar groups are
already `collapsed: true`; the reference generator already exists (22 vitest suites,
build-time, gitignored output) — this campaign extends it rather than building one.

## Governing principle (from the audit, adopted)

**Source-visible documentation.** codeArbiter's product is its prompts, gates, and hooks; for
a compliance-minded adopter, reading exactly what an agent is told to do is a trust
prerequisite. Docs never *summarize* a source artifact where they can *show* it:

- Every command/agent/skill page = **curated framing layer** (hand-written, voice-guided) +
  **verbatim source layer** (embedded at build time from `plugins/ca/`, collapsible, with a
  tag-pinned view-in-repo link). Paraphrased prompt text is banned and lint-enforced.
- Hooks are code, not prose — their verbatim layer is generated metadata (gate ID, event,
  blocking/advisory, user-visible message strings) plus line-pinned source permalinks, never
  pasted Python.

## Design decisions

- **(a) Links:** new `site/scripts/rehype-base-links.ts` prefixes the base onto any
  root-absolute `href`/`src` not already prefixed — the documented convention becomes true,
  zero content rewrites. `link-audit.ts` refactored to `link-audit/lib.ts` + CLI and hardened:
  base-less internal root-absolute targets are **failures**, not skips.
- **(b) Curated content:** companion files `site/src/curated/{commands,agents,skills}/<basename>.md`
  keyed by plugin source basename (the `forge-status.ts` key discipline), parsed with the
  generator's own `parse-doc.ts`. Frontmatter `entity` / `related` / `gates`; body sections
  What it does / Usage / Example. Merged in `generate.ts`. Divergence check: orphan curated
  file → generator throws; uncurated source → valid generated-only page. Curated content lives
  in `site/`, never plugin frontmatter (version-bump gate).
- **(c) Source embed:** `render-source-embed.ts` — `<details class="ca-source">` wrapping a
  dynamically-fenced code block (fence = longest backtick run + 1, min 4), version pinned to
  `v<version>` from `plugins/ca/.claude-plugin/plugin.json`.
- **(d) Hooks reference:** `extract-hook-gates.ts` scans `plugins/ca/hooks/*.py` at gen time
  for `block(`/`remind(` literal-tag call sites (depth-tracked scan, adjacent-literal
  concatenation, f-string placeholders rendered as code); events from `hooks.json`;
  `git-enforce.py` labeled "git backstop". Emits generated `reference/hooks-gates.md`
  (H-00…H-20). Count-floor snapshot test guards silent under-collection. Hand-authored
  `hooks.md` narrative is kept and links to the catalog.
- **(e) Slugs:** per-collection `assignSlugs` in `generate.ts`; six skill `-2` URLs get Astro
  `redirects`. Command slugs unchanged (path sort verified) → forge-status keys safe.
- **(f) Changelog:** `render-changelog.ts` renders repo-root `CHANGELOG.md` to a gitignored
  `site/src/content/docs/changelog.md` at gen time.
- **Scope:** FULL curated coverage — all 39 commands (with example transcripts), all 28
  agents, all 22 skills — authored in batches.

## PR ladder

```
PR-S    this spec
Phase 0 0.1 rehype links + hardened audit ‖ 0.2 drop dup H1 + meta descriptions ‖ 0.3 per-collection slugs + redirects
Phase 1 1.1 VOICE.md + overview rewrite ‖ 1.2 MD5 example → TypeScript ‖ 1.3 enforcement split + aphorism cap
Phase 2 2.1 generator: curated merge + source embed + anatomy (blocks the rest)
        → 2.2 hooks generator ‖ 2.3a-c curated commands ×39 ‖ 2.4 curated agents ×28 + rosters ‖ 2.5 curated skills ×22
Phase 3 3.1 .codearbiter/ reference + glossary + FAQ ‖ 3.2 uninstall + compat + changelog → 3.3 IA restructure
Phase 4 4.1 landing blocks (why-gates, who-for, trust row, three doors) → 4.2 terminal frames + accents (time-boxed)
```

Every PR verifies with `cd site && npm run typecheck && npm test && npm run build && npm run link-audit`;
CI (`docs.yml`) re-runs all four. User approval at phase boundaries.

## Acceptance criteria

- **AC-1 (Phase 0):** hardened link-audit fails on the pre-fix build and passes after the
  rehype plugin lands (both states demonstrated); one `<h1>` per built reference page; populated
  per-page `<meta name="description">`; no `-2` reference URL; old `-2` URLs redirect.
- **AC-2 (Phase 1):** no docs page addresses the model as "you"; negation-triad register
  confined to the landing page and section intros; one MD5 worked example, one language (TS);
  `enforcement.md` carries no version-headed section.
- **AC-3 (Phase 2):** every command/agent/skill page renders the anatomy with a collapsible
  verbatim source embed and tag-pinned repo link; `npm run gen` fails on an orphan curated
  file; paraphrase-lint green; hooks-gates page lists every literal-tag call site (count-floor
  test); all 89 entities carry curated framing.
- **AC-4 (Phase 3):** every `.codearbiter/` file and CONTEXT.md frontmatter key documented;
  glossary linked from ≥3 pages; uninstall/disable documented per-repo and global; changelog
  renders on-site with the latest version at top.
- **AC-5 (Phase 4):** from the landing page alone a skeptical visitor can answer: what is
  this, why tolerate it, how do I try it in 5 minutes, how do I turn it off.

## Out / constraints

- No changes to `plugins/ca/**` (hooks are read at build time only). No docs versioning
  system. No new standing visual-test harness (per the prior spec's posture).
- Keep: hero demo format, Diátaxis top structure, audit-grade enforcement specificity
  (layered, not diluted), hook IDs in user-facing docs, per-entity reference URLs, the nine
  guide topics.
- Generation is for fidelity to source, not for producing prose: authored layers (landing,
  guides, concepts, curated framing) remain hand-written under `site/VOICE.md`.
