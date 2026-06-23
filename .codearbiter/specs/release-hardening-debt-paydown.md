# Sprint spec — Release-skill hardening + test-debt paydown

**Slug:** `release-hardening-debt-paydown`
**Mode:** `/ca:sprint` (premium backend, no `--farm`)
**Drafted:** 2026-06-23
**Status:** DRAFT — awaiting user approval at the Phase 1 STOP gate.

## Origin

`/ca:sprint` seeded with three threads:
1. The README version badge didn't get bumped to match the 2.5.0 release.
2. The `release` skill probably needs an adversarial pass to confirm it does everything it should.
3. Plan as many `open-tasks.md` items as reasonable.

Recon (three parallel passes) turned each thread into concrete, evidenced findings. The badge bug
is the visible symptom of a deeper one: the `release` skill never touches the README badges **and**
was written for a single-plugin repo, so the `ca-sandbox` sibling plugin silently broke its tag
resolution, release window, `--latest` flag, and artifact-freshness check.

## Goal

Make the release path correct and self-checking for this two-plugin repo, eliminate badge/count
drift at the root, and pay down the bounded test/chore/docs-site debt — landing as **one PR**
(sprint never merges; merge stays the user's call).

## Scope decisions (set by the user at the scoping gate)

- **Full scope:** release-hygiene + the 3 bounded backfills + the 4 docs-site items.
- **Drift guard:** BOTH a release-skill update step AND a CI guard that fails on drift.
- **Release pass depth:** full red-team; fix every BLOCK/HIGH finding this sprint, log MEDIUM/LOW.

## Out of scope (deferred, with reason)

- `v2.security.0003` (farm `assertSecureBaseUrl` re-review record) — security re-review is a hard-gate
  surface; belongs with the user, not autonomous execution.
- `mkt.review.0004` (live macOS session + fixture-payload decision) — needs a physical macOS session
  this environment can't provide, plus an owner decision.
- `v2.release.0001` (marketplace publication) — publication is an authorization gate, not autonomous.
- Release findings **MEDIUM 8–LOW 12** — logged as `open-tasks.md` items per the "fix BLOCK/HIGH" choice.
- Docs-site **Task 4 decision-log reconciliation** form — semantically tied to the still-open
  `CONFIRM-05`; only the unblocked self-consistency check ships this sprint.

---

## Workstream A — Release-skill hardening

Target: `plugins/ca/skills/release/SKILL.md` (a procedure in prose; edits go through the docs/prose
review path + anti-slop self-audit, not TDD red-green) plus one new CI guard (real code → test-first).

### Acceptance criteria

- **AC-A1 (BLOCK 1 — tag resolution).** Pre-flight resolves `LAST_TAG` from ca's SemVer tags only,
  excluding pre-releases and the `ca-sandbox-v*` tags — e.g. `git tag -l 'v[0-9]*' --sort=-v:refname`
  filtered of `*-beta*`/`*-rc*`, never bare `git describe --tags`. The skill states the rationale
  (two-plugin repo). *Verify:* from current `HEAD`, the documented command yields `v2.5.0`, not
  `ca-sandbox-v0.1.0`.
- **AC-A2 (BLOCK 2 — release window).** The commit window AND bump derivation are scoped to the
  plugin payload path (`git log LAST_TAG..HEAD -- plugins/ca/`); `feat(ca-sandbox)` commits cannot
  influence ca's bump or changelog. The skill documents which plugin `/release` targets. *Verify:*
  the documented window command excludes the `#111`/`#115` ca-sandbox commits.
- **AC-A3 (BLOCK 3 — manifest sync).** Pre-flight asserts the derived version equals
  `plugins/ca/.claude-plugin/plugin.json` `version`, and STOPs on mismatch (bump-the-manifest is a
  precondition of tagging).
- **AC-A4 (HIGH 4 — catalog drift).** Pre-flight asserts the command-file set matches the
  `COMMANDS.md` catalog (both copies) and the README counts; STOP on drift.
- **AC-A5 (HIGH 5 — `--latest`).** `gh release create` no longer hard-codes `--latest`; the skill
  computes whether this tag is the newest release across *both* plugins and asserts `--latest` only
  then, else `--latest=false`.
- **AC-A6 (HIGH 6 — publish read-back).** After `gh release create`, the skill runs
  `gh release view vX.Y.Z --json url,isDraft,tagName` and STOPs unless a non-draft Release exists on
  the correct tag. The Phase-3 gate no longer treats a failed publish as passing.
- **AC-A7 (HIGH 7 — footer enforcement).** A `feat`/`fix` commit missing its `CHANGELOG:` footer is a
  Phase-1 **BLOCK**, not a soft `[NEEDS-TRIAGE]`.
- **AC-A8 (badge/count update step — root cause of Thread 1).** The skill gains a step that, as part
  of a release, updates the README version badge, the command/skill/agent count badges, and the prose
  counts that echo them, plus `plugin.json` — all derived mechanically from the repo, never typed.
- **AC-A9 (immediate drift fix).** The current README is corrected: `version-2.4.6`→`2.5.0`;
  `commands-36`→`37`; the prose "36 commands" (README:246) and `commands/ (36)` (README:323) updated;
  every count re-derived from the repo (skills 20 / agents 15 re-confirmed). COMMANDS.md reconciled if
  it drifted.
- **AC-A10 (CI drift guard — test-first).** A committed check (script + unit test) fails when the
  README badges/prose counts disagree with the real command/skill/agent counts or the `plugin.json`
  version disagrees with the latest `v*` tag; wired into CI. *Verify:* mutate a count, check goes red;
  restore, green.
- **AC-A11 (log the rest).** Release findings MEDIUM 8–LOW 12 are appended to `open-tasks.md` via
  `/ca:task`, each one task, with the finding text and "done when".

### Release findings logged (not fixed this sprint)

- MEDIUM 8 — `farm.js` freshness check is conditional; should rebuild-and-assert-no-diff
  unconditionally, and cover `ca-sandbox` `sandbox.js`.
- MEDIUM 9 — half-finished-publish recovery: Phase-2 "tag exists → STOP" dead-ends a pushed-but-
  unpublished tag; branch on version/SHA match → resume Phase 3.
- MEDIUM 10 — date stamping uses an unspecified clock; derive once and reuse across header,
  `Released-at:`, and the Release.
- LOW 11 — assert the notes-file `## vX.Y.Z` heading matches the tag before `gh release create`.
- LOW 12 — exclude pre-release tags from baseline resolution explicitly (subsumed by AC-A1; close if so).

---

## Workstream B — Test-debt paydown

The task board is stale: A/B are partly done. Reflect reality and close the residual gaps; ensure the
new tests are actually enforced by CI (today neither hook suite runs in CI).

### Acceptance criteria

- **AC-B1 (`v2.test.0001` — `_sloplib`).** `test_sloplib.py` (already 16 tests) gains direct coverage
  for the uncovered exemptions: `~~~` tilde fence, HTML-tag/autolink and markdown-link-target branches
  of `_URL_RE`, leading `./` path normalization, empty/falsy `rel_path`, and multi-line multi-finding
  output. *Verify:* `cd plugins/ca/hooks && python -m pytest tests/test_sloplib.py` green.
- **AC-B2 (`v2.test.0002` — CRYPTO_RE).** `test_hooklib.py`'s `CryptoReTest` gains a direct positive
  assertion for each currently-undirected branch: `createCipher`, `createHmac`, `\bsha1\b`, `\brc4\b`,
  `3des`, `\bRSA\b`, and the `crypto.*` group (`subtle`, `sign`, `verify`, `createSign`, `createVerify`,
  `generateKey`, `publicEncrypt`, `privateDecrypt`, `pbkdf2`, `scrypt`, `randomBytes`,
  `createDiffieHellman`). Test-only; no change to `CRYPTO_RE` or any security control. *Verify:*
  `python .github/scripts/test_hooklib.py` (or pytest) green.
- **AC-B3 (CI enforcement).** `test_hooklib.py` and the `plugins/ca/hooks/tests/` suite are invoked by
  CI so B1/B2 are load-bearing. *Verify:* a deliberately-broken assertion fails the CI job locally
  (`act`/manual run of the step).
- **AC-B4 (`v2.chore.0001` — sharp).** `sharp` moves from `dependencies` to `optionalDependencies` in
  `site/package.json`; `site/package-lock.json` regenerated with `npm install --package-lock-only`;
  LF preserved (no CRLF drift). *Verify:* `cd site && npm ci && npm run build` succeeds.

---

## Workstream C — Docs-site cluster

Prerequisite: site vitest + typecheck run **nowhere** in CI today (AC-21 unmet), so new site tests are
unguarded until wired in.

### Acceptance criteria

- **AC-C0 (CI prerequisite).** `npm test` (vitest) and `npm run typecheck` for `site/` run in CI on
  `site/**` changes (added to `docs.yml`'s build job or a new site job). *Verify:* a failing site test
  fails the job.
- **AC-C1 (`Task 1` — link-audit; AC-2/AC-4).** A committed post-build script walks every internal
  `href`/`src` in `site/dist/**/*.html`, asserts each resolves under the `/codeArbiter` base, and
  asserts `dist/favicon.svg` + a `dist/_astro/logo.*.svg` emit; non-zero on any dangling link; wired
  into CI. *Verify:* `cd site && npm run build && npm run link-audit` exits 0; a broken slug exits non-zero.
- **AC-C2 (`Task 2` — assertions; AC-9/AC-13 + forge edges).** New `forge-status.test.ts` covers the
  `/ca:` prefix-strip and case-normalization paths (`/ca:prune`, `PRUNE`, `/ca:Sprint`, `commit`→null);
  a content test asserts the 3 diagram SVGs exist, each carries an in-SVG `<title>`, each is referenced
  by ≥1 page, and `concepts.md` contains the `## The Feature Forge` section with evidence-promotion
  language. *Verify:* `cd site && npm test` green.
- **AC-C3 (`Task 3` — base-path convention).** One base-safe diagram/image-href convention is chosen
  (SMARTS during execution: shared `<Diagram>` `.astro` component vs. root-absolute `/codeArbiter/…`)
  and applied to all 5 references across `index.mdx`, `overview.md`, `concepts.md`,
  `ForgeShowcase.astro`; a committed check greps `site/src/**` and fails on a stray off-convention
  diagram href. *Verify:* build + the convention check pass; all 5 diagrams still render in `dist`.
- **AC-C4 (`Task 4` — allowlist drift, unblocked form).** A self-consistency check asserts every slug
  in `PREVIEW_COMMANDS` (`forge-status.ts`) maps to a real command file under `plugins/ca/**`; fails on
  a stale/typo'd slug; wired into the site CI step. The stronger decision-log reconciliation form is
  logged as a `CONFIRM-05`-dependent task. *Verify:* add a bogus allowlist slug → check fails.

---

## Risks & hard-gate watch

- **CRYPTO_RE tests (B2)** touch crypto-detection territory but add *tests for existing branches* —
  no change to `CRYPTO_RE` or `security-controls.md`. Not a hard gate; the crypto-compliance reviewer
  may still inspect — expected, not a stop.
- **CI edits (A10, B3, C0, C1, C4)** are scope-touch. Adding test/lint steps to `ci.yml`/`docs.yml`
  does not touch deploy permissions, secrets, or auth → not a hard gate, but gets review scrutiny.
- **Task 3 design fork (C3)** and **Task 4 truth-source (C4)** are the thin-spec points most likely to
  produce low-confidence SMARTS calls — both are pre-bounded here to keep autonomy from stalling.
- **Sprint size:** ~19 tasks across plugin-prose, Python tests, and Astro/TS+CI. Large but legitimate
  given full-scope opt-in. MVP slicing below lets the user stop after any slice.

## MVP slicing (value-ordered; each slice is independently shippable)

1. **Slice 1 — Release BLOCKs + badge fix + guards (MVP).** AC-A1, A2, A3, A8, A9, A10. Fixes the
   reported bug *and* the dangerous multi-plugin breakage. Highest value; ship even if nothing else does.
2. **Slice 2 — Release HIGH findings + logging.** AC-A4, A5, A6, A7, A11.
3. **Slice 3 — Test-debt paydown.** AC-B1, B2, B3, B4.
4. **Slice 4 — Docs-site cluster.** AC-C0, C1, C2, C3, C4. Largest and least urgent; the natural
   fold-to-next-sprint if the user wants to keep this one tight.

## Done when

Every in-scope AC met, suite green, MEDIUM/LOW release findings and the CONFIRM-05-dependent docs check
logged to `open-tasks.md`, branch through `commit-gate`, PR opened (not merged), sprint Receipt emitted.
