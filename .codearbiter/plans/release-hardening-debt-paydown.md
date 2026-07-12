# Plan — Release-skill hardening + test-debt paydown

**Spec:** `.codearbiter/specs/release-hardening-debt-paydown.md`
**Slug:** `release-hardening-debt-paydown`
**Backend:** premium subagent (no `--farm`)
**Branch:** `sprint/release-hardening-debt-paydown` (created at execution start; sprint opens a PR, never merges)

**Status:** COMPLETE — reconciled 2026-07-12 against PR #125 and subsequent release-hardening PRs #138, #150, and #151.

Lanes: **prose** = skill/README markdown, reviewed + anti-slop self-audit (no TDD); **test** = test-first
code; **chore** = non-behavioral (deps/lockfile); **ci** = workflow edit (scope-touch, reviewed).
`status` column is the ledger: `QUEUED` → `IN-PROGRESS` → `ACCEPTED`.

## Slice 1 — Release BLOCKs + badge fix + guards (MVP)

| # | Task | Path(s) | Lane | Verification | Status |
|---|---|---|---|---|---|
| 1 | Fix `LAST_TAG` resolution to ca `v*` SemVer tags, exclude pre-releases + `ca-sandbox-v*`; document two-plugin rationale (AC-A1) | `plugins/ca/skills/release/SKILL.md` (Pre-flight) | prose | Documented command run from HEAD yields `v2.5.0`, not `ca-sandbox-v0.1.0` | ACCEPTED |
| 2 | Scope release window + bump derivation to `plugins/ca/`; state which plugin `/release` targets (AC-A2) | `plugins/ca/skills/release/SKILL.md` (Phase 1) | prose | Documented `git log LAST_TAG..HEAD -- plugins/ca/` excludes `#111`/`#115` | ACCEPTED |
| 3 | Add pre-flight assertion: derived version == `plugin.json` version, STOP on mismatch (AC-A3) | `plugins/ca/skills/release/SKILL.md` (Pre-flight) | prose | Skill text STOPs when `plugin.json` lags the derived bump | ACCEPTED |
| 4 | Add badge/count update step: README version+count badges, prose counts, `plugin.json`, all mechanically derived (AC-A8) | `plugins/ca/skills/release/SKILL.md` (Phase 1/2) | prose | Skill text enumerates the four README sites + plugin.json and derives counts from the repo | ACCEPTED |
| 5 | Correct current README drift: `2.4.6`→`2.5.0`, `36`→`37` (badge + README:246 + README:323); re-confirm skills 20 / agents 15; reconcile COMMANDS.md if drifted (AC-A9) | `README.md`, `plugins/ca/COMMANDS.md` (if drifted) | prose | `grep -n 'version-2\|commands-3\|36 command\|(36)' README.md` shows only correct values; counts match repo | ACCEPTED |
| 6 | Write failing test for the badge/count CI guard: counts + plugin.json-vs-tag (AC-A10 red) | `.github/scripts/test_badge_consistency.py` (or site/test) | test | Test runs red against an injected wrong count | ACCEPTED |
| 7 | Implement the badge/count guard script to green (AC-A10 green) | `.github/scripts/check_badge_consistency.py` | test | Guard passes on correct repo; red on a mutated count | ACCEPTED |
| 8 | Wire the badge/count guard into CI (AC-A10) | `.github/workflows/ci.yml` | ci | The guard step runs in CI; a mutated count fails the job | ACCEPTED |

## Slice 2 — Release HIGH findings + logging

| # | Task | Path(s) | Lane | Verification | Status |
|---|---|---|---|---|---|
| 9 | COMMANDS.md catalog-drift pre-flight check (both copies + README counts), STOP on drift (AC-A4) | `plugins/ca/skills/release/SKILL.md` (Pre-flight) | prose | Skill text asserts command-file set == catalog == counts | ACCEPTED |
| 10 | Replace hard-coded `--latest`: compute newest-across-both-plugins, else `--latest=false` (AC-A5) | `plugins/ca/skills/release/SKILL.md` (Phase 3) | prose | Skill text conditions `--latest` on cross-plugin newest check | ACCEPTED |
| 11 | Post-publish read-back: `gh release view … --json url,isDraft,tagName`, STOP unless non-draft on tag; fix Phase-3 gate language (AC-A6) | `plugins/ca/skills/release/SKILL.md` (Phase 3) | prose | Gate no longer accepts a failed publish; read-back step present | ACCEPTED |
| 12 | Make a missing `CHANGELOG:` footer a Phase-1 BLOCK, not a soft finding (AC-A7) | `plugins/ca/skills/release/SKILL.md` (Phase 1 gate) | prose | Phase-1 gate BLOCKs on an unresolved footer `[NEEDS-TRIAGE]` | ACCEPTED |
| 13 | Log release findings MEDIUM 8–LOW 12 to the task board via `/ca:task` (AC-A11) | `.codearbiter/open-tasks.md` | chore | 5 tasks added, each with finding text + "done when" | ACCEPTED |

## Slice 3 — Test-debt paydown

| # | Task | Path(s) | Lane | Verification | Status |
|---|---|---|---|---|---|
| 14 | Close residual `_sloplib` exemption gaps: `~~~` fence, HTML/autolink + link-target `_URL_RE` branches, leading `./`, empty `rel_path`, multi-line findings (AC-B1) | `plugins/ca/hooks/tests/test_sloplib.py` | test | `cd plugins/ca/hooks && python -m pytest tests/test_sloplib.py` green; each new case red first against a stubbed bug | ACCEPTED |
| 15 | Add direct CRYPTO_RE branch assertions: createCipher, createHmac, sha1, rc4, 3des, RSA, full `crypto.*` group (AC-B2) | `.github/scripts/test_hooklib.py` | test | `python .github/scripts/test_hooklib.py` green; each branch asserted positively | ACCEPTED |
| 16 | Wire `test_hooklib.py` + `plugins/ca/hooks/tests/` into CI (AC-B3) | `.github/workflows/ci.yml` | ci | A broken assertion fails the CI step (manual/act run) | ACCEPTED |
| 17 | Move `sharp` to `optionalDependencies`; regenerate lockfile; preserve LF (AC-B4) | `site/package.json`, `site/package-lock.json` | chore | `cd site && npm ci && npm run build` succeeds; lockfile LF | ACCEPTED |

## Slice 4 — Docs-site cluster

| # | Task | Path(s) | Lane | Verification | Status |
|---|---|---|---|---|---|
| 18 | Wire `site` vitest + typecheck into CI (AC-C0 — prerequisite for 19–22) | `.github/workflows/docs.yml` (or new site job) | ci | A failing site test fails the job | ACCEPTED |
| 19 | Link-audit script (internal dist links resolve under base; favicon/logo emit) + CI wiring (AC-C1) | `site/scripts/link-audit.ts`, `site/package.json`, CI | test | `npm run build && npm run link-audit` exits 0; broken slug → non-zero | ACCEPTED |
| 20 | `forge-status.test.ts` (prefix-strip + case-norm) + diagram/content assertions (AC-9/AC-13) | `site/test/generator/forge-status.test.ts`, `site/test/generator/diagrams.test.ts` | test | `cd site && npm test` green; each red first against a stub | ACCEPTED |
| 21 | Choose + apply one base-safe diagram-href convention across the 5 refs; add a convention-guard check (AC-C3) | `index.mdx`, `overview.md`, `concepts.md`, `ForgeShowcase.astro` (+ optional `<Diagram>` component), guard script | test | SMARTS-logged choice; build + guard pass; all 5 diagrams render in `dist` | ACCEPTED |
| 22 | Forge allowlist self-consistency check (slug→real command file) + CI; log decision-log form as CONFIRM-05-dependent task (AC-C4) | `site/test/generator/forge-allowlist.test.ts` or check script, `.codearbiter/open-tasks.md` | test | Bogus allowlist slug → check fails; CONFIRM-05 task logged | ACCEPTED |

## Dependencies & ordering

- Slice 1 first (MVP, highest value). Task 5 (README fix) can reuse the count derivation written for Task 4.
- Tasks 6→7→8 ordered (red → green → CI).
- Slice 4: Task 18 (CI wiring) before 19/20/22's CI assertions are meaningful; Task 21 is the SMARTS fork.
- Tasks 16 and 18 both edit CI workflows — sequence to avoid collision; not parallel.

## Auto-decision watch (likely SMARTS points during autonomy)

- Task 21 — diagram-href convention (shared `.astro` component vs root-absolute). Break ties toward
  Maintainable + the spec's base-safety priority.
- Task 22 — self-consistency check shape. Bounded to the unblocked form by the spec.
- Task 10 — exact cross-plugin "newest release" computation. Toward Reliable (correct badge ownership).
- Where the badge/count guard lives (ci.yml step vs standalone) — toward the existing `.github/scripts` convention.

All non-hard-gate auto-decisions log to `.codearbiter/sprint-log.md` with a confidence flag.
