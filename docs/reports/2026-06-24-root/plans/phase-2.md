# Phase 2 plan — Wave 2 (performance · architecture · migration-data-integrity)

Roadmap level: groups + sequences kept findings by type. Covers `keep`/`combine`
only. All 17 Wave-2 findings were kept (after calibration: 0 critical/high,
8 medium, 9 low). No `decision-required`/`defer` this wave.

Some groups extend Phase-1 groups (g1–g5); new groups are g6–g9.

---

## Group g6 — `_hooklib.py` per-call hot-path: precompute at module load (performance)

**Findings:** performance-001 (medium), performance-002 (low) ·
**File:** `plugins/ca/hooks/_hooklib.py` (242–304) · **Effort:** S

Two per-call costs on the hook hot path: `_read_controls` re-reads
`security-controls.md` on every `is_ci/deploy/migration_path` call, and
`_glob_to_re` rebuilds glob→regex objects per `path_in_globs`. → Cache controls
text mtime-keyed at module level; pre-compile the constant default glob sets
(`MIGRATION/CI/DEPLOY_DEFAULT_GLOBS`) at import. **Acceptance:** no redundant
controls read or glob recompile within a hook process; glob-match correctness
tests unchanged. *(Calibrated down from the lens's "high" — OS page-cache and
`re._cache` already blunt most of the cost; still a clean win.)*

## Group g7 — `statusline.py` per-render redundant file IO (performance)

**Findings:** performance-004 (medium), performance-005 (medium) ·
**File:** `plugins/ca/hooks/statusline.py` (372–402, 666–693) · **Effort:** S

The statusline renders on every tool-call completion. Each render does an O(N)
scan+parse of session JSON files (`session_start`) and 5 uncached `.codearbiter/`
reads (`arbiter_state`). → PID-fast-path the session lookup (or cache the resolved
start in the ledger); mtime-key or per-render-memoize `arbiter_state`.
**Acceptance:** typical re-renders hit no full session scan and re-read the 5 state
files only when one changed.

## Standalone — `project_root()` git subprocess per hook (performance, highest-value)

**Finding:** performance-003 (medium) · **File:** `plugins/ca/hooks/_hooklib.py`
(139–150), called by all four enforcement hooks · **Effort:** S

Every enforcement hook spawns `git rev-parse --show-toplevel` as its first action
— a process fork on every Bash/Write/Edit, ~15–30ms on Windows. → Reuse the
`.git`-directory upward walk `statusline.py` already implements; fall back to the
subprocess for worktrees/bare repos. **Acceptance:** no subprocess spawn for the
common local-repo case; worktree/bare-repo parity preserved.

## Standalone — detached-HEAD triple git spawn (performance, low)

**Finding:** performance-006 (low) · **File:** `plugins/ca/hooks/pre-bash.py`
(131–138) · **Effort:** S — collapse 3 sequential `git rev-parse` into one
`git rev-parse HEAD main master`. Rare path; trivial fix.

---

## Group g2-ext — Secret-detection consistency (architecture + Phase-1 g2)

**Finding:** architecture-001 (medium) · **Files:** `plugins/ca/tools/farm.ts`
(264–267), `plugins/ca/hooks/_hooklib.py` (56–64) · **Effort:** M

farm.ts `SECRET_LINE` (outbound redactor) and `_hooklib.SECRET_RE` (commit gate)
are a hand-synced fork that has already drifted, with a *false* "kept in step"
comment. → Add one shared must-match/must-not-match fixture asserted against BOTH
(CI fails on divergence), or derive both from one source; correct the comment.
**Do alongside Phase-1 g2** (the `_hooklib` regex gaps) — same secret-spec surface.
**Acceptance:** CI fails if the two classifiers disagree on any fixture string.

## Standalone — Container hardening flags duplicated (architecture, security-load-bearing)

**Finding:** architecture-002 (medium) · **Files:**
`plugins/ca-sandbox/tools/run.ts` (127–159), `claude-inside.ts` (262–303) ·
**Effort:** S

The isolation argv is re-emitted verbatim in both builders; the token-bearing
`--with-claude` box silently weakens if a future flag lands in `run.ts` only. →
Extract one exported `hardeningFlags()` both splice; share `SANDBOX_LABEL`; add a
test asserting the `--with-claude` argv contains every hardening flag the ordinary
sandbox argv does. **Acceptance:** isolation flag block defined once; parity test green.

## Group g4 (Phase-1) extends — Centralize audit-log / ADR path sets (architecture)

**Finding:** architecture-004 (medium) · **Files:** `pre-write.py` (30,37),
`pre-edit.py` (35,53), `pre-bash.py` (72,83) · **Effort:** S

The append-only-log and ADR-decisions path patterns are triplicated inline — the
exact drift `_hooklib` centralization exists to prevent. → Lift to
`_hooklib.AUDIT_LOG_RE`/`is_audit_log` + `DECISIONS_PATH_RE`; import in all three
pre-* hooks. **This is the natural home for the g5 H-05 hardening** (below).
**Acceptance:** each path set defined once; adding an artifact touches one file.

## Standalone — create.ts mount-chokepoint bypass (architecture, low)

**Finding:** architecture-006 (low) · **File:**
`plugins/ca-sandbox/tools/create.ts` (174–188, 205–218) · **Effort:** S — route
the clone/build-helper mounts through `buildMountArgs` so the "single chokepoint"
invariant mounts.ts advertises is actually true, or document the exception. Safe
today (internal volume names), but the isolation audit story is currently false.

## Group g8 — statusline.py structural cleanup (architecture, behavior-preserving)

**Findings:** architecture-005 (low), architecture-007 (low) ·
**File:** `plugins/ca/hooks/statusline.py` · **Effort:** S–M

(1) Drop the local `frontmatter()`/arbiter-enabled reimplementation; reuse
`_hooklib.frontmatter_enabled`/`arbiter_active` (guarded import, as `_taskboardlib`
already is). (2) Extract the ~290-LOC cost-ledger subsystem into `_ledgerlib.py`
with its own test (mirrors `_metricslib`/`_taskboardlib`), per the thin-entry-point
standard. → Route via `/ca:refactor`; statusline renders identically. **Acceptance:**
activation state derives from `_hooklib`; ledger lives in a tested lib.

## Standalone — farm.ts god-module split (architecture, low-priority L refactor)

**Finding:** architecture-003 (medium) · **File:** `plugins/ca/tools/farm.ts` ·
**Effort:** L — extract the secret redactor (213–413) and mutation engine (767–948)
into focused modules with their own tests; route via `/ca:refactor` (vitest = parity
proof). depends_on architecture-001 (redactor extraction carries the shared fixture).
Lower priority than the mediums above.

---

## Group g9 — Atomic state writes (migration-data-integrity)

**Findings:** migration-001 (medium), migration-002 (low) · **Files:**
`taskwrite.py` (105–106), `migration-pass.py` (91–92), `security-pass.py` (84–85) ·
**Effort:** S

All three do truncate-then-write read-modify-write of state. `open-tasks.md` loss
is real data loss (board → empty, no auto-recovery); the markers only force a
spurious gate re-run (fail-closed preserved). → Write `.tmp` then `os.replace()`
everywhere. **Acceptance:** a simulated crash leaves the original file intact;
backstop markers never half-written.

## Group g5 (Phase-1) extends — H-05 guard hardening (migration + appsec)

**Finding:** migration-003 (low) · **File:** `plugins/ca/hooks/pre-edit.py`
(43–45) · **Effort:** S

`new.startswith(old)` is always True when `old_string==''`, so an empty-old_string
Edit on an audit log isn't blocked. Distinct from appsec-003 (pre-bash variable
indirection); both belong to the **g5 H-05 audit-log guard hardening** group. →
Block empty `old_string` on audit logs outright (an empty old can't be a verifiable
append). Pairs with g4's centralized `is_audit_log`.

## Standalone — farm.ts validate() null guards (migration/DX, low)

**Finding:** migration-004 (low) · **File:** `plugins/ca/tools/farm.ts`
(1292–1297) · **Effort:** S — add named-field guards before dereferencing required
plan fields so a malformed plan.json yields a readable error, not a TypeError.
Belongs with the **g3 farm.ts robustness** group.
