# RA-11 Catalog Rationalization Implementation Plan

> **Execution:** use the codeArbiter subagent-driven-development routine task by task. Every behavior
> task follows red, green, refactor; generated files are never hand-edited.

**Goal:** make 18 core lanes discoverable without removing any of the 38 compatibility-bearing
command routes, and project one validated taxonomy across Claude, Codex, Pi, README, and the site.

**Architecture:** `core/surface/command-routes.json` owns visibility, workflow, canonical target,
replacement, reverse legacy routes, modes, and compatibility policy. The stdlib surface generator parses
and validates that graph while leaving executable host frontmatter unchanged, then renders host-native catalogs and
per-host JSON sidecars. The site generator joins the Claude sidecar to shipped command bodies to
build grouped reference discovery and source-derived landing statistics. Legacy wrappers remain
installed and keep executing their existing contracts; additive canonical modes route independently
to the same underlying workflows.

**Tech stack:** Python 3 stdlib surface generator and unittest; Markdown command templates; Astro 7,
TypeScript, and Vitest site generator; Pi TypeScript/Vitest package. No dependency changes.

**Spec:** `.codearbiter/specs/reaudit-ra11-catalog-rationalization.md`

## Global constraints

- Work only in `C:\Users\brenn\projects\codeArbiter-worktrees\reaudit-ra11-catalog-rationalization`
  on `codex/reaudit-ra11-catalog-rationalization`, based on exact `4561dc219818032369f0985c787f7fccd8030770`.
- Never edit `campaign.html`, the imported ledger, the dirty controller checkout, or unrelated RA
  scope.
- Edit canonical `core/surface/` inputs, run generators, and commit inputs plus projections together.
- Preserve all existing route files and host exclusions. Do not add a top-level command.
- Use `apply_patch` for authored file edits and explicit-path staging through `/ca:commit`.
- Stop after governed local commit(s). Do not push or open a PR.

## AC ledger

| ID | Acceptance criterion |
|---|---|
| AC-01 | Strict route-registry schema and closed alias graph fail path-specifically on invalid input. |
| AC-02 | Exact taxonomy is 18 core, 13 advanced, 5 aliases, 1 internal, 1 deprecated. |
| AC-03 | Five legacy aliases stay installed, preserve arguments/workflows, and emit one host-native notice. |
| AC-04 | Five canonical replacement modes are executable wrapper contracts with old gates/skills. |
| AC-05 | `add-dep` stays canonical; no new dependency/evidence/config/extend/help top-level route. |
| AC-06 | Three human host catalogs agree with installed files, visibility counts, and workflow groups. |
| AC-07 | Per-host JSON sidecars carry metadata while executable frontmatter retains its prior schema. |
| AC-08 | README shows grouped core lanes, not the raw full table/count-first marketing. |
| AC-09 | Site reference groups by visibility/workflow exactly once and preserves host availability. |
| AC-10 | Landing has no stale hard-coded route count and derives 18 core lanes from the registry. |
| AC-11 | Compatibility policy fixes retention floors/removal windows; no release operation occurs. |
| AC-12 | Focused and whole-surface tests pass; projections are idempotent; branch ends clean. |
| AC-13 | Architecture, compatibility, final diff, secrets, provenance, docs, and anti-slop reviews clear. |

## Tasks

### Task 1: Specify the catalog graph in failing surface-generator tests

**Files:**
- Modify: `.github/scripts/test_build_surface.py`
- Modify: `.github/scripts/test_host_descriptors.py`

**Breaks caught:** a missing/invalid classification is accepted; an alias points to an absent,
aliased, or host-excluded target; a reverse alias list drifts; host output drops metadata or groups
by raw filename only.

- [ ] Add literal synthetic fixtures for valid core/advanced/internal/alias/deprecated entries.
- [ ] Add table-driven invalid fixtures for every schema and graph violation named by AC-01.
- [ ] Assert literal grouped catalog sections/counts and Pi JSON metadata for a small known fixture.
- [ ] Run `python .github/scripts/test_build_surface.py` and observe failures for missing production
  parsing/validation/projection behavior.
- [ ] Run the host-descriptor suite and retain the independent oracle obligation.

**Verification:** `python .github/scripts/test_build_surface.py`; `python .github/scripts/test_host_descriptors.py`
**Maps to:** AC-01, AC-02, AC-06, AC-07
**Depends on:** none
**Status:** PENDING

### Task 2: Implement the strict metadata parser and host projections

**Files:**
- Modify: `tools/build-surface.py`
- Modify: `.github/scripts/test_build_surface.py`
- Modify: `.github/scripts/test_host_descriptors.py`

- [ ] Parse the versioned JSON route registry with Python stdlib only.
- [ ] Validate enum values, filename/canonical invariants, alias targets, host availability, exact
  forward/reverse closure, and replacement-mode declarations.
- [ ] Prove executable Claude/Codex/Pi frontmatter remains on its prior loader-facing schema.
- [ ] Render grouped Codex/Pi human catalogs with separate installed visibility counts.
- [ ] Generate `generated/command-catalog.json` for all three hosts with `visibility`, `workflow`,
  `canonical`, `replacement`, and `aliases` where applicable.
- [ ] Run Task 1 tests to green, then mutation-check wrong visibility, dropped alias, and missing
  target handling.

**Verification:** Task 1 commands plus `python tools/build-surface.py --check` after generation
**Maps to:** AC-01, AC-06, AC-07
**Depends on:** Task 1
**Status:** PENDING

### Task 3: Classify all routes and preserve compatibility through canonical modes

**Files:**
- Add: `core/surface/command-routes.json`
- Modify bodies: `pr.md`, `init.md`, `status.md`
- Modify alias bodies: `watch.md`, `cleanup.md`, `decompose.md`, `create-context.md`,
  `context-check.md`
- Modify deprecated body: `btw.md`
- Add: `core/surface/includes/command-compatibility.md`

**Breaks caught:** a legacy route loses its body, arguments, output, or owning skill/gate; a
replacement is merely metadata and not an executable canonical wrapper mode; a compatibility route
cross-invokes a host command; `add-dep` is falsely redirected.

- [ ] Add one exact registry entry for each of the 38 templates with the verified taxonomy,
  reverse aliases, declared modes, and compatibility policy.
- [ ] First add focused assertions that each canonical replacement body declares its literal mode,
  each legacy body retains its pre-change workflow markers and argument contract, and its single
  migration notice names the canonical form without host-command cross-invocation.
- [ ] Observe the focused failures before changing command bodies.
- [ ] Add minimal mode dispatch sections to the three canonical wrappers and one concise migration
  notice to each of the five otherwise-intact compatibility bodies.
- [ ] Keep `btw` functional and read-only while marking direct questions as its replacement.
- [ ] Add the shared retention/removal policy include and reference it from every alias/deprecated
  wrapper without duplicating version policy; publication, not source presence, starts each window.
- [ ] Prove the registry keeps `add-dep` at `visibility: core`, `canonical: add-dep`.

**Verification:** `python .github/scripts/test_build_surface.py`; `python .github/scripts/check-plugin-refs.py`; `python .github/scripts/check_command_catalog.py`
**Maps to:** AC-02, AC-03, AC-04, AC-05, AC-11
**Depends on:** Task 2
**Status:** PENDING

### Task 4: Generate and test all host surfaces

**Files:**
- Generated: `plugins/ca/**` direct projections of changed canonical surfaces
- Generated: `plugins/ca-codex/**` direct projections and manifest count/description
- Generated: all three host projections and their command JSON sidecars
- Modify: `plugins/ca-pi/tools/test/commands.test.ts` if its runtime catalog boundary needs new
  assertions
- Modify: `.github/scripts/check_routing_index_parity.py` stale fixed-count prose

- [ ] Run `python tools/build-surface.py` once; never hand-edit generated policy files.
- [ ] Add/extend Pi runtime-catalog assertions before any runtime consumer change and observe the
  metadata expectation fail if the consumer surface lacks it.
- [ ] Update only generated-count manifest prose that is proven stale by current source.
- [ ] Run generation again and assert `0 file(s) changed`.
- [ ] Verify exact core and package parity.

**Verification:** `python tools/build-surface.py --check`; `python tools/sync-core.py --check`; `python tools/build-host-packages.py --check`; `npm --prefix plugins/ca-pi/tools test -- commands.test.ts`
**Maps to:** AC-03, AC-06, AC-07, AC-12
**Depends on:** Task 3
**Status:** PENDING

### Task 5: Drive grouped site discovery from the generated command registry

**Files:**
- Modify: `site/scripts/generator/types.ts`
- Modify: `site/scripts/generator/build-index.ts`
- Modify: `site/scripts/generator/generate.ts`
- Modify: `site/scripts/generator/landing-stats.ts`
- Modify: `site/scripts/generator/render-command-page.ts`
- Modify/add focused tests under `site/test/generator/` and `site/test/landing/`

**Breaks caught:** a command appears in no group or multiple groups; aliases are counted as core;
replacement guidance disappears; host badges regress; malformed source metadata is silently
accepted; the landing count returns to raw `.md` files.

- [ ] Add failing generator fixtures with literal expected visibility/workflow groups and one alias.
- [ ] Add failing landing-stat fixtures requiring source-derived core/alias counts and strict
  malformed-metadata rejection.
- [ ] Thread catalog fields through `RenderedPage`/sidebar items and group command discovery by
  visibility then workflow while leaving skill/agent grouping unchanged.
- [ ] Render replacement guidance on alias/deprecated command pages.
- [ ] Preserve all pages, search indexing, and host availability.
- [ ] Run focused Vitest tests to green and mutation-check a duplicated/missing assignment.

**Verification:** `npm --prefix site exec vitest run test/generator test/landing/trust-row.test.ts`
**Maps to:** AC-02, AC-09, AC-10
**Depends on:** Task 3
**Status:** PENDING

### Task 6: Rationalize README, canonical catalog, and landing copy

**Files:**
- Modify: `core/surface/COMMANDS.md`
- Modify: `README.md`
- Modify: `site/src/content/docs/index.mdx`
- Modify: directly affected content tests

- [ ] Replace technical flat grouping with core workflow groups plus collapsed advanced,
  compatibility, and internal/deprecated sections in the canonical catalog.
- [ ] Replace README command-count badge and full 38-row table with the 18-lane workflow chooser,
  host-difference statement, and complete-reference link.
- [ ] Replace homepage `40 commands` with source-derived/copy-stable route language; keep the six
  high-signal lane cards and link complete discovery to the grouped reference.
- [ ] Correct the stale TrustRow fixture comment and any directly affected canonical-route prose.
- [ ] Run content, badge, site-voice, link, and reference generation tests.

**Verification:** `python .github/scripts/check_badge_consistency.py`; `python .github/scripts/check_command_catalog.py`; `npm --prefix site run gen`; `npm --prefix site run test`; `npm --prefix site run typecheck`; `npm --prefix site run build`; `npm --prefix site run link-audit`
**Maps to:** AC-06, AC-08, AC-09, AC-10, AC-12
**Depends on:** Tasks 4 and 5
**Status:** PENDING

### Task 7: Whole-surface validation and independent review

**Files:** all changed paths; no new scope

- [ ] Run focused generator, host, Pi, site, and catalog suites with recorded counts.
- [ ] Run repository-applicable whole-surface commands from `.codearbiter/tech-stack.md` and record
  exact pass/skip/failure counts without claiming unavailable live-host proof.
- [ ] Run secrets scan, provenance/reference checks, anti-slop docs review, and generated-tree
  idempotence checks.
- [ ] Dispatch an independent architecture/compatibility review at gpt-5.6-sol/xhigh over the final
  diff and acceptance ledger; remediate every CRITICAL/HIGH finding.
- [ ] Dispatch a separate final diff reviewer; re-run affected tests after remediation.
- [ ] Verify no campaign/controller checkout mutation and no release/push/PR side effect.

**Verification:** commands recorded in final evidence; `git diff --check`; `git status --short`; generated checks above
**Maps to:** AC-12, AC-13
**Depends on:** Tasks 1-6
**Status:** PENDING

### Task 8: Governed local commit and clean handoff

**Files:** only the reviewed RA-11 diff

- [ ] Run the complete `/ca:commit` gate, including explicit secret scan and entire applicable suite.
- [ ] Stage every changed path explicitly; never use `git add .` or `git add -A`.
- [ ] Commit with a conventional subject/body and required `CHANGELOG:` footer.
- [ ] Re-run `git status --short --branch`, capture exact commit SHA, and prove clean state.
- [ ] Stop without push, PR, merge, release, tag, publication, deployment, or live install.

**Verification:** `/ca:commit` evidence plus exact `git rev-parse HEAD` and clean status
**Maps to:** AC-11, AC-12, AC-13
**Depends on:** Task 7
**Status:** PENDING

## Order and MVP

Dependency order: T1 -> T2 -> T3 -> T4; T3 -> T5; T4 + T5 -> T6 -> T7 -> T8.

**Minimum shippable compatibility slice:** Tasks 1-4. It provides strict metadata, real canonical
modes, preserved aliases, and all three host projections. It is not the completed RA-11 leg until
Tasks 5-8 make discovery truthful, clear reviews, and land the governed local commit.

## Coverage proof

Every AC maps to at least one task and every task maps to at least one AC. AC-01 -> T1,T2;
AC-02 -> T1,T3,T5; AC-03 -> T3,T4; AC-04 -> T3; AC-05 -> T3; AC-06 -> T2,T4,T6;
AC-07 -> T2,T4; AC-08 -> T6; AC-09 -> T5,T6; AC-10 -> T5,T6; AC-11 -> T3,T8;
AC-12 -> T4,T6,T7,T8; AC-13 -> T7,T8.

Plan self-review: no task assumes a missing top-level replacement, no generated policy file is an
authored input, behavior tasks name their red observation, host exclusions stay descriptor-owned,
and no step authorizes release or remote mutation.
