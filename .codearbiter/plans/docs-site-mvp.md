# Plan — docs-site-mvp

slug: docs-site-mvp
spec: `.codearbiter/specs/docs-site-mvp.md` (PROPOSED — awaiting approval)
created: 2026-06-17
mode: `/ca:sprint --farm` — Slice 1 (generator) dispatched to the farm; Slice 2 (Astro + prose) Claude-authored

> Pre-flight: `FARM_API_KEY` present (farm preflight OK). `plugins/ca/**` is READ-ONLY (generator reads it).
> Canonical site commands (authored this sprint, in `site/`): `npm test` (vitest), `npm run typecheck`
> (`tsc --noEmit`), `npm run build` (astro build), `npm run dev` (astro dev). The generator runs via
> `npm run gen` (`tsx scripts/generate.ts`) and is wired into `predev`/`prebuild`.

## Slice strategy (one MVP slice at a time, per SPRINT.md)

- **Slice 0 — harness (Claude, pre-farm):** `site/` npm project with Vitest + TypeScript + tsx; tsconfig;
  test fixtures; **all 15 failing tests** (authored by Claude); **all 15 typed impl stubs** (signature +
  `throw new Error('not implemented')`) so the project typechecks and each test is genuinely red. This is
  the `writing-plans --farm` test-authoring step. Co-emits `plans/docs-site-mvp.plan.json`.
- **Slice 1 — generator (FARM):** the 15 `F-*` tasks below. Each worker fills exactly one impl-file body;
  the worker may not touch the test. Gate per task = narrow test first (mutation-guard target) + typecheck.
  Full-suite green is NOT a per-task gate (siblings stay red until merged); it is Claude's Phase-5
  verification after all tasks merge.
- **Slice 2 — site (Claude, post-farm):** the `C-*` tasks — Astro Starlight scaffold, generator wiring,
  Overview + Concepts prose, run generator to emit reference pages, README, `.gitignore`, local serve.

## Module / file layout

- Impl: `site/scripts/generator/<module>.ts` (one module per farm task)
- Orchestrator entry: `site/scripts/generate.ts`
- Tests: `site/test/generator/<module>.test.ts` (Claude-authored, worker-protected)
- Fixtures: `site/test/fixtures/{commands,skills,agents,edge,empty-dir}/...` (Claude-authored test data)
- Generated output: `site/src/content/docs/reference/{commands,skills,agents}/*.md` + `site/src/generated/sidebar.json`

## Acceptance-criterion ledger

AC-01..AC-17 per the spec. Mapping in the `covers` column below.

## Slice 1 tasks (FARM) — each = one failing test → one impl file

| id | impl file (filesInScope) | narrow test (gate[0], worker-protected) | behavior | covers | deps | status |
|---|---|---|---|---|---|---|
| F-01 | `scripts/generator/split-frontmatter.ts` | `test/generator/split-frontmatter.test.ts` | `splitFrontmatter(raw)→{frontmatter:string\|null, body}`; null block when no leading `---`; no throw on empty | AC-02 | — | PENDING |
| F-02 | `scripts/generator/parse-fields.ts` | `test/generator/parse-fields.test.ts` | `parseFields(text)→Record<string,string>`; missing→absent; extra preserved; malformed line skipped (no throw); empty→{} | AC-03,04,05 | — | PENDING |
| F-03 | `scripts/generator/parse-doc.ts` | `test/generator/parse-doc.test.ts` | `parseDoc(raw)→{fields,body}` composing F-01+F-02; never throws on empty/body-only | AC-06 | F-01,F-02 | PENDING |
| F-04 | `scripts/generator/slugify.ts` | `test/generator/slugify.test.ts` | `slugify(s)→string` stable kebab; lowercases, strips/space→`-`, idempotent | AC-07 | — | PENDING |
| F-05 | `scripts/generator/assign-slugs.ts` | `test/generator/assign-slugs.test.ts` | `assignSlugs(names[])→string[]` dedupes collisions deterministically (`-2`,`-3`), stable order | AC-07 | F-04 | PENDING |
| F-06 | `scripts/generator/classify-source.ts` | `test/generator/classify-source.test.ts` | `classifySource(path)→'command'\|'skill'\|'agent'` from the three path shapes | AC-08 | — | PENDING |
| F-07 | `scripts/generator/derive-name.ts` | `test/generator/derive-name.test.ts` | `deriveName(path,fields)→string`; skills/agents use `fields.name`; commands derive from filename | AC-09 | — | PENDING |
| F-08 | `scripts/generator/model-tier.ts` | `test/generator/model-tier.test.ts` | `modelTier(model?)→string` label; missing→`default` | AC-10 | — | PENDING |
| F-09 | `scripts/generator/format-tools-list.ts` | `test/generator/format-tools-list.test.ts` | `formatToolsList(tools?)→string` md list from comma string; empty/missing→`—` | AC-10 | — | PENDING |
| F-10 | `scripts/generator/render-agent-page.ts` | `test/generator/render-agent-page.test.ts` | `renderAgentPage(doc)→md` with name+description+model tier+tools; missing model handled | AC-10 | F-08,F-09 | PENDING |
| F-11 | `scripts/generator/render-command-page.ts` | `test/generator/render-command-page.test.ts` | `renderCommandPage(doc)→md` name+description; no model/tools section | AC-11 | — | PENDING |
| F-12 | `scripts/generator/render-skill-page.ts` | `test/generator/render-skill-page.test.ts` | `renderSkillPage(doc)→md` name+description | AC-12 | — | PENDING |
| F-13 | `scripts/generator/collect-sources.ts` | `test/generator/collect-sources.test.ts` | `collectSources(rootDir)→{path,raw,type}[]`; empty dir→[]; no throw on missing dir | AC-13 | F-06 | PENDING |
| F-14 | `scripts/generator/build-index.ts` | `test/generator/build-index.test.ts` | `buildIndex(pages[])→{markdown,sidebar}` lists every page grouped by type, stable order | AC-14 | — | PENDING |
| F-15 | `scripts/generator/generate.ts` | `test/generator/generate.test.ts` | `generate(srcDir,outDir)` collect→parse→render→write pages+`sidebar.json`; one page/source; **idempotent** | AC-15 | F-03,F-05,F-06,F-07,F-10,F-11,F-12,F-13,F-14 | PENDING |

Leaves (F-01,02,04,06,07,08,09,11,12,14) run fully parallel; F-03,05,10,13 depend on 1–2 leaves; F-15 integrates.

## Slice 2 tasks (Claude, post-farm)

| id | path(s) | verification | covers | status |
|---|---|---|---|---|
| C-01 | `site/package.json`, `site/astro.config.mjs`, `site/src/content.config.ts` | Astro Starlight scaffold; `npm run build` produces `dist/` | AC-16 | PENDING |
| C-02 | `site/astro.config.mjs`, `site/package.json` | generator wired into `predev`/`prebuild`; astro.config consumes `src/generated/sidebar.json` | AC-16 | PENDING |
| C-03 | `site/src/content/docs/index.mdx`, `.../overview.md` | Overview prose (orchestration, gates, "you hold the gates; the user holds the decisions") from ORCHESTRATOR.md + docs/architecture.md | spec §MVP-1 | PENDING |
| C-04 | `site/src/content/docs/concepts.md` | Concepts prose (gated-lane, SMARTS, ADR/decision log, checkpoints, persona-register split) | spec §MVP-2 | PENDING |
| C-05 | (run `npm run gen`) | reference pages emitted under `src/content/docs/reference/`; `npm run build` + `npm run dev` green; shown to owner | AC-16 | PENDING |
| C-06 | `site/README.md`, root `.gitignore` | README (run/test/generator); `.gitignore` adds `site/node_modules`,`site/dist`,`site/.astro`; deploy-readiness note | AC-17 | PENDING |

## Verification (Claude Phase 5, after farm merge)

- `cd site && npm test` — **full** Vitest suite green (all 15 modules integrated).
- `cd site && npm run typecheck` — clean.
- `cd site && npm run gen && git diff --exit-code site/src/content/docs/reference` after a second run — idempotent.
- `cd site && npm run build` — site builds; `npm run dev` serves locally (shown to owner).

## Measurement (Step 6, after merge)

`python tools/farm-first-pass.py` over `.farm/farm-report.json`: first-pass vs. escalation per F-task;
flag any `FARM_ABORT_ESCALATION_RATE` circuit-breaker trip.
