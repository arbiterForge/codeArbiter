# Deep review — codeArbiter — run `2026-06-24-root`

Scope: repository root · Concurrency: 3 · Mode: **report-only** (no issues filed) ·
Lenses: 10 launched, 2 mappers skipped (mapped inline).

**45 findings → 42 kept/combined · 2 decision-required · 1 deferred.**
Calibrated severity (kept): **2 high · 18 medium · 22 low**. Every severity here is
the orchestrator's calibrated value (the lens self-scores are provisional and were
overridden at triage — 3 self-scored "high"s were downgraded; see counter-arguments
in `triage.jsonl`).

Source of truth = the append-only logs (`findings/<lens>.jsonl`, `triage.jsonl`).
This report is a projection. Fix roadmaps: `plans/phase-1.md` (Wave 1),
`plans/phase-2.md` (Wave 2), `plans/phase-3.md` (Wave 3).

This audit ran against the dev tree. Per the project's own note, the hand-built
`.codearbiter/` state can mask consumer-facing behavior — the hook findings below
were grounded by reading the hook source directly and the guard test-suite, not by
observing live hook behavior.

---

## The one-paragraph read

The hardest surfaces held. The appsec lens **cleared** the sandbox isolation core
(`validateRepoUrl`, `buildMountArgs`, the `--with-claude` token co-mount guard,
`assertSecureBaseUrl` — no parser-differential), and the coverage lens confirmed
the highest-risk guards (H-01/02/03/05/11, the CRYPTO_RE branches, the H-14 backstop,
the docker isolation invariants) are genuinely well-tested. tests-fidelity found
**zero** fixture drift. The real findings cluster in two places: the **commit-time
backstops** in `pre-bash.py` (a `git commit <pathspec>` spelling slips crypto/secret
*and* migration changes past the gate — the only HIGH), and **detection-spec drift**
(the `_hooklib` regexes miss RC2/Blowfish and compound key-names; the farm redactor
and the hook gate are two hand-synced copies of "what a secret looks like"). The
rest is solid, mechanical hardening: atomic state writes, subprocess timeouts,
hot-path caching, and a batch of cheap test/diagnosability gaps.

---

## HIGH (2)

- **[appsec-001]** `plugins/ca/hooks/pre-bash.py:312-341` — `git commit <pathspec>`
  bypasses the H-09b/H-10b crypto/secret commit gate (the backstop scans only the
  *index*; a pathspec-commit ships worktree content). → Union the worktree diff for
  pathspec tokens. *Decision: combine (g1, lead). → `plans/phase-1.md`.*
- **[coverage-001]** `.github/scripts/test_hook_guards.py` vs `pre-bash.py:316-341` —
  the **H-10b secret** commit gate has no end-to-end test (only `SECRET_RE` unit
  coverage); its H-09b crypto twin is fully exercised. → Add integration cases
  (block + TOCTOU re-block) mirroring H-09b. *Decision: combine (g11). → `plans/phase-3.md`.*

> The two HIGHs are the same story from two angles: the secret/crypto commit lane has
> both a real bypass (appsec-001) and the missing test that would have caught it
> (coverage-001). Fix them in one pass — land the g1 code change with the g11 tests.

## MEDIUM (18) — by type

### Commit-gate & detection (security)
- **[appsec-002]** `pre-bash.py:355-377` — same pathspec gap defeats the H-14
  migration gate. *combine (g1).*
- **[secrets-001]** `_hooklib.py:41-51` — CRYPTO_RE omits `rc2`/`blowfish` (both
  forbidden by `security-controls.md`). *combine (g2).*
- **[secrets-002]** `_hooklib.py:56-63` — SECRET_RE leading `\b` won't fire inside
  `FARM_API_KEY`; project key prefix matches no anchor. *combine (g2).*
- **[architecture-001]** `farm.ts:264-267` vs `_hooklib.py:56-64` — secret-detection
  regex forked across languages, drifted, "kept in step" comment false. → one shared
  CI fixture asserted against both. *keep (pairs with g2).*
- **[coverage-002]** `pre-bash.py:313-315` — `git commit -a/-am` worktree branch
  untested for crypto/secret. *combine (g11).*
- **[coverage-003]** `create.test.ts` — `validateRepoUrl` scp-like `host::address`
  rejection has no pinning test (git-arg-injection boundary). *keep.*

### Reliability & data integrity
- **[reliability-001]** `farm.ts` — gate/setup/mutation subprocesses have no timeout;
  a hung command wedges a worker and the run never finalizes. *keep (g3).*
- **[reliability-002]** `create.ts:198-228` — `defaultBuildImage` ignores
  `docker create`/`cp` exit codes → silent empty checkout → wrong dephash cache key.
  *keep (g4).*
- **[migration-001]** `taskwrite.py:105-106` — non-atomic overwrite of
  `open-tasks.md`; a crash empties the board (no auto-recovery). *combine (g9).*

### Performance (hot path: every tool call / render)
- **[performance-003]** `_hooklib.py:139-150` — `project_root()` spawns
  `git rev-parse` on every hook (~15-30ms/call on Windows). → `.git`-walk. *keep.*
- **[performance-001]** `_hooklib.py:267-292` — `security-controls.md` re-read per
  path-check. *combine (g6).*
- **[performance-004]** `statusline.py:666-693` — O(N) session-file scan per render.
  *combine (g7).*
- **[performance-005]** `statusline.py:372-402` — 5 uncached `.codearbiter/` reads
  per render. *combine (g7).*

### Structure (architecture)
- **[architecture-002]** `run.ts:127-159` / `claude-inside.ts:262-303` — container
  hardening argv duplicated verbatim; the token-bearing box silently weakens if a
  future flag lands in one. → extract `hardeningFlags()` + parity test. *keep.*
- **[architecture-003]** `farm.ts` — 1690-LOC god-module (5 subsystems incl. the
  security redactor). → extract redactor + mutation engine via `/ca:refactor`. *keep (L).*
- **[architecture-004]** `pre-write/pre-edit/pre-bash` — audit-log & ADR path sets
  triplicated inline. → centralize in `_hooklib`. *keep (extends g4-plan/g5).*

### Observability / DX
- **[observability-001]** `session-start.py:417-422` — clears the `dev-active` marker
  with no `DEV:exit` audit line → orphaned `DEV:enter`. *keep.*
- **[dx-001]** `farm.ts:536-546` — `parseChatCompletion` parses the Zen API response
  with no shape guard → silent empty content exhausts retries. *keep (g3).*

## LOW (22) — by type (terse; full records in `findings/`)

### Audit-log guard hardening (g5)
- **[appsec-003]** `pre-bash.py:72-90,289-293` — H-05 log guard lexical-only;
  `$f=overrides.log; rm $f` evades. *keep.*
- **[migration-003]** `pre-edit.py:43-45` — H-05 bypassed when `old_string==""`
  (`startswith("")` always True). *keep.*
- **[observability-005]** `security-controls.md:148-155` — doc overstates H-05
  coverage vs the code's documented gaps. *keep (doc-only).*

### Atomic writes / state integrity (g9)
- **[migration-002]** `migration-pass.py:91-92`, `security-pass.py:84-85` — non-atomic
  marker writes (fail-closed, but spurious re-run). *combine (g9).*

### farm.ts robustness/diagnosability (g3)
- **[reliability-004]** `farm.ts:1618-1621` — `finally` passes undefined worktree to
  spawn → TypeError masks the real error. *keep.*
- **[migration-004]** `farm.ts:1292-1297` — `validate()` null-derefs required plan
  fields → opaque TypeError. *keep.*
- **[observability-003]** `farm.ts:1592-1598` — crash note has no run-id correlation /
  no stack. *keep.*
- **[dx-002]** `farm.ts:903-909` — `mutationCheck` JSON.parse no object guard →
  silently disables mutation scoring. *keep.*
- **[dx-003]** `farm.ts:937` — `originals.get(c.file)!` could write `"undefined"` to
  the worktree on a future Map miss. *keep.*

### Performance (low)
- **[performance-002]** `_hooklib.py:242-304` — glob→regex rebuilt per call (largely
  `re._cache`-mitigated). *combine (g6).*
- **[performance-006]** `pre-bash.py:131-138` — 3 git spawns where 1 suffices
  (rare detached-HEAD path). *keep.*

### Structure (low)
- **[architecture-005]** `statusline.py:339-376` — reimplements `_hooklib`
  frontmatter/arbiter-enabled parsing. *combine (g8).*
- **[architecture-006]** `create.ts:174-188,205-218` — raw `--mount` argv bypasses the
  `buildMountArgs` "single chokepoint" (invariant currently false; safe today). *keep.*
- **[architecture-007]** `statusline.py:405-693` — ~290-LOC cost-ledger embedded in
  the render entry-point vs the thin-entry-point standard. *combine (g8).*

### ca-sandbox failure surfacing (g4)
- **[observability-004]** `create.ts:146-163` — `spawnAsync stdio:'ignore'` swallows
  git clone stderr; error has only an exit code. *combine (g4).*

### DX input-contracts / type-safety
- **[dx-004]** `_taskboardlib.py:406-434` — `set_state` KeyError on unknown state;
  contract undocumented. *combine (g10).*
- **[dx-005]** `_taskboardlib.py:514-541` — `promote` silently auto-applies (mutates
  state) on any non-`interactive` mode. *combine (g10).*
- **[dx-006]** `run.ts:58,125` — `buildRunArgs` airgaps only exact `"offline"` vs an
  open string type; a typo of `"offline"` drops `--network none` at T-06. *keep.*
- **[dx-007]** `_hooklib.py`, `_sloplib.py` — missing the required `name(args)->type`
  public-API header. *keep.*

### Test coverage (low)
- **[coverage-004]** `_hooklib.py:277-304` — custom CI/deploy path extend/exclude
  grammar untested. *keep.*
- **[coverage-005]** `post-write-edit.py:106-113` — H-12 governed-path reminder has no
  integration test. *keep.*

---

## DECISION-REQUIRED (2) — these need you, not a fix

- **[secrets-003]** `site/package-lock.json:811-984` — 18 `@img/sharp-libvips-*`
  (**LGPL-3.0-or-later**) + `tslib` (**0BSD**) are outside the approved-license list.
  Build-time / docs-site only (not the shipped payload). **The call:** approve
  LGPL-3.0/0BSD for build-time deps (same SMARTS-arbitration path as the prior
  BlueOak/CC0 decision) and add to `security-controls.md`, *or* record `overrides.log`
  entries. ADR-stub candidate.
- **[observability-002]** the "compel a log write" gap — no hook forces an `/override`,
  `/sprint` auto-decision, or `/dev`-entry append; H-05 only protects logs *once
  written*. Already deferred as a design call (`open-questions.md` L19). **The call:**
  promote to a tracked `CONFIRM-NN` and decide the enforcement strategy (staleness
  check vs. per-action PreToolUse vs. accept prose-enforced). No-regrets regardless:
  document the integrity-vs-completeness distinction in `security-controls.md`.

## DEFERRED (1)

- **[secrets-004]** `run.ts:119`, `claude-inside.ts:257` — `Math.random()` for
  container-name suffixes. Not an isolation identifier here (resolution is by label),
  so below the issue bar; preserved, not filed.

---

## Lens roster

| Lens | Model | Findings | Notable |
|---|---|---|---|
| appsec | Opus | 3 | 1 HIGH (pathspec bypass); cleared the isolation core |
| secrets-crypto-supply | Sonnet | 4 | RC2/Blowfish + word-boundary regex gaps |
| reliability | Opus | 4 | farm timeout; docker-create swallow |
| performance | Sonnet | 6 | hot-path hook latency (3 self-"high"s calibrated down) |
| architecture | Opus | 7 | secret-regex fork; hardening-flag dup; cleared the suspected forks |
| migration-data-integrity | Sonnet | 4 | non-atomic `open-tasks.md` write |
| observability | Sonnet | 5 | DEV:exit gap; compel-log-write (→ decision) |
| dx-typesafety | Sonnet | 7 | API-boundary parse casts; NetPolicy typo |
| tests-coverage | Sonnet | 5 | 1 HIGH (H-10b untested); confirmed risk paths covered |
| tests-fidelity | Sonnet | **0** | clean — stubs match real signatures; no drift |
| map-structure / map-deps | — | skipped | repo bounded; mapped inline |

## Investigate appendix

None. Every finding resolved to a terminal decision (keep / combine / decision-required
/ defer). The one finding that risked a confidence-gate drop (dx-006, a suspected
conflict with `network.ts`/`security-controls.md`) was resolved by direct verification
rather than routed to investigate — see its `counter_argument` in `triage.jsonl`.

## Suggested sequencing (if you act on this)

1. **g1 + g11 together** — the pathspec/`-a` commit-gate bypass *and* its tests (the
   one HIGH + its coverage). Highest value; small.
2. **g2 + architecture-001** — close the `_hooklib` regex gaps and make the
   farm-redactor / hook-gate secret-spec a single CI-checked fixture.
3. **g9** — atomic state writes (`open-tasks.md` data-loss is the sharpest reliability edge).
4. **g3 / g4** — farm.ts + ca-sandbox robustness and failure surfacing (bundle the
   reliability/dx/observability findings per file).
5. **g6 / g7** — hot-path caching (felt on every tool call).
6. The two **decision-required** items — license approval + the audit-write enforcement strategy.
7. Low-priority structural refactors (architecture-003 god-module, g8 statusline) last.
