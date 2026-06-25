# Phase 3 plan — Wave 3 (observability · dx-typesafety · tests-coverage · tests-fidelity)

Roadmap level: groups + sequences kept findings by type. Covers `keep`/`combine`.
tests-fidelity returned 0 (clean). Wave-3 kept tally after calibration:
1 high · 4 medium · 11 low. `observability-002` → decision-required (below).

New groups g10–g11; several findings extend earlier groups (g3, g4, g5).

---

## Group g11 — Commit-gate integration test coverage (tests-coverage)

**Findings:** coverage-001 (high), coverage-002 (medium) ·
**File:** `.github/scripts/test_hook_guards.py` (add cases) · **Effort:** S

The H-09b crypto commit gate is tested end-to-end (cases 6a–6e); its **H-10b
secret twin has no integration test** (only `SECRET_RE` unit coverage), and the
**`git commit -a/-am` worktree-diff branch** is untested for crypto/secret. →
Add: (a) stage a `SECRET_RE` literal, assert `[H-10b]` block + a TOCTOU re-block;
(b) a `git commit -am` worktree-only crypto change asserts `[H-09b]`. **Sequence
this WITH the g1 pathspec-bypass fix** — add the pathspec-commit case in the same
pass, so the g1 code change ships with the tests that prove all three commit
spellings (staged / `-a` / pathspec) are gated. **Acceptance:** the secret lane
and both worktree-inclusion spellings have blocking integration tests.

## Standalone — validateRepoUrl scp-like pinning test (tests-coverage)

**Finding:** coverage-003 (medium) · **File:**
`plugins/ca-sandbox/tools/create.test.ts` · **Effort:** S — add negative tests
pinning that `git@github.com::evil` (double-colon transport-helper) is rejected
and single-colon scp forms are accepted. Cheap insurance on the git-arg-injection
boundary; pairs with the architecture-006 mount-chokepoint work on create.ts.

## Standalone — advisory-scope coverage (tests-coverage, low)

**Findings:** coverage-004 (low), coverage-005 (low) · **Effort:** S each —
test the `is_ci_path`/`is_deploy_path` custom extend/exclude grammar (mirror the
migration OB-02/03 cases) and the post-write-edit **H-12** governed-path reminder
integration path. Both advisory gates; broken parsing silently drops the warning.

---

## Group g3 (extends) — farm.ts robustness + diagnosability

**Findings (Wave 3):** dx-001 (medium), observability-003 (low), dx-002 (low),
dx-003 (low) · **File:** `plugins/ca/tools/farm.ts` · **Effort:** S each

Folds into the Phase-1/2 g3 farm.ts group (reliability-001 timeout,
reliability-004 finally-guard, migration-004 validate guards). Add:
- **dx-001** — runtime outer-shape guard in `parseChatCompletion` (no `choices`
  array → `ok:false` actionable error, not silent empty content).
- **observability-003** — mint a run-id at `main()`; include it in every
  `farm-results.jsonl` line + report header; add truncated `err.stack` to the
  crash note.
- **dx-002 / dx-003** — `typeof`-object guard before reading `parsed.score` in
  `mutationCheck`; replace the `originals.get(c.file)!` non-null assertion with an
  explicit guard that preserves the file on a Map miss.

## Group g4 (extends) — ca-sandbox build/clone failure surfacing

**Finding (Wave 3):** observability-004 (low) · **File:**
`plugins/ca-sandbox/tools/create.ts` · **Effort:** S

Joins reliability-002 (unchecked `docker create`/`cp`). `defaultCloneRepo`'s
`spawnAsync` uses `stdio:'ignore'`, so a failed clone surfaces only an exit code.
→ Capture a bounded slice of git stderr and thread it into the thrown error.
Fix alongside reliability-002 — one create.ts failure-surfacing pass.

## Group g5 (extends) — H-05 audit-log guard hardening + doc accuracy

**Finding (Wave 3):** observability-005 (low) · **File:**
`.codearbiter/security-controls.md` · **Effort:** S

Joins appsec-003 + migration-003 in g5. Pure doc fix: `security-controls.md`
§Audit trail claims H-05 enforces "at every tool-call boundary" but the
`pre-bash.py` comment documents accepted gaps (`exec N>`, `>>>`, process
substitution). → Mirror the accepted-residual-risk scope into the policy doc so
it doesn't overstate coverage.

## Standalone — `_hooklib`/`_sloplib` public-API headers (dx, low)

**Finding:** dx-007 (low) · **Files:** `plugins/ca/hooks/_hooklib.py`,
`_sloplib.py` · **Effort:** S — add the `name(args) -> type` header block the
coding standard requires (and `_taskboardlib`/`_metricslib` already have).
`_hooklib` is the surface every untrusted-payload hook routes through.

## Standalone — DEV:exit audit completeness (observability)

**Finding:** observability-001 (medium) · **File:**
`plugins/ca/hooks/session-start.py` · **Effort:** S — when SessionStart clears a
live `dev-active` marker, append a synthetic `DEV:exit BY: session-cleanup` line
to `overrides.log` first, so a mid-session dev exit isn't an orphaned `DEV:enter`.
Replaces a prose-only "repair at next opportunity" instruction with enforcement.

---

## Group g10 — `_taskboardlib` input-contract guards (dx-typesafety)

**Findings:** dx-004 (low), dx-005 (low) · **File:**
`plugins/ca/hooks/_taskboardlib.py` · **Effort:** S

Two undocumented-value-contract gaps: `set_state` raises `KeyError` on an
out-of-set `state`; `promote` silently auto-applies (mutating persistent state)
on any non-`"interactive"` `mode`. → Guard both (degrade or raise-with-message)
and document the valid value sets in the docstrings + header.

## Standalone — NetPolicy safe-default typo (dx-typesafety, low)

**Finding:** dx-006 (low) · **File:** `plugins/ca-sandbox/tools/run.ts` (58, 125)
· **Effort:** S — `buildRunArgs` emits `--network none` only for exact
`"offline"` against an open string type, so a typo of `"offline"` silently drops
the airgap at the T-06 layer. → Narrow the handled-policy compare (closed union /
normalized check) so a typo can't lose isolation. *(The T-10 `network.ts`
closed-union exhaustiveness is correct and unaffected.)*

---

## Not planned (recorded in triage.jsonl)

- **observability-002 → decision-required:** the "compel a log write" gap — no
  hook forces an `/override`, `/sprint` auto-decision, or `/dev`-entry append; H-05
  only protects logs once written. This is the enforcement-strategy choice the user
  already deferred (open-questions.md L19); the response is ADR-grade, not a fix. →
  Promote to a tracked `CONFIRM-NN`. No-regrets sub-action (independent of the
  decision): document the integrity-vs-completeness distinction in
  `security-controls.md` §Audit trail.
