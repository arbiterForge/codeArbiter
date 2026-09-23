# Spec — hook registry cross-host path resolution (#684, #686, #683)

Source: `/ca:debug` session, 2026-09-20. No code changed during investigation.
Branch: `fix/hooks-wsl-path-races` (worktree off `origin/main` @ `a3e7cbf8`).

## Symptom (Phase 1)

**Observed:** In a repo whose `.git` is shared between a WSL-hosted process (Codex
running through `/mnt/c/...` Python/paths) and Git for Windows (native `C:\...`
paths, hooks run through its bundled Git-Bash/MSYS POSIX shell), the generated
`pre-commit`/`pre-push` shims fail closed with `no registered git-enforce.py could
be resolved from "..." -- failing CLOSED (#161/#265 git backstop, ADR-0014)`, even
though the named enforcer file exists (from the writing host's own point of view)
and `doctor.py` / its live-fire probe reported the registry healthy. Separately
(#686), in one repo the `pre-commit` and `pre-push` shims ended up embedding
**different, mutually incompatible** spellings of the drop-in directory
(`D=`) after repeated installs — one Windows-native, one WSL — so one phase
worked and the sibling phase failed closed.

**Expected:** Either a registered enforcer resolves correctly regardless of which
host's Git/shell runs the shim, or the failure is caught and reported clearly by
`doctor` *before* a governed commit/push is attempted, and it never happens to a
git operation that reads back a previously-clean install.

**Minimal repro (shared, all three issues):**
1. Open the same physical checkout (or a same-runtime linked worktree of it) from
   both a WSL session and a Windows (Git for Windows / Git-Bash) session, each
   running a codeArbiter host's `install()` (SessionStart).
2. From WSL: `git commit` / `git push` — hooks resolve fine (WSL wrote its own
   registry entry/shim last).
3. From Windows: `git.exe commit` / `git push` in the same repo — the shim
   (embedded `D=` and/or the `.path` entries) may contain WSL-spelled paths
   (`/mnt/c/...`) that Git-Bash/MSYS cannot resolve → fails closed.
4. `doctor.py`'s live-fire probe (`git hook run pre-push`) only ever invokes
   **the current process's own** Git — it never proves the *other* host's Git
   can resolve the same registry, so it reports healthy in exactly the state
   that (3) fails.

**Evidence in hand:** issue bodies #684, #686, #683 (verbatim repro/error text,
cited above); `core/pysrc/_githooks.py` and `core/pysrc/doctor.py` read in full
this session (paths cited per-hypothesis below); `.codearbiter/tech-stack.md`
lines 76-79 ("WSL is not a separately verified named cell... unsupported...
Git Bash is the Windows hook shell and is not equivalent to WSL"); no ADR
mentions WSL (`grep -rl -i wsl .codearbiter/decisions/` → no matches — this is a
descriptive tech-stack note, not an ADR-backed decision, so narrowing it is a
doc update alongside the fix, not an ADR reversal).

## Hypotheses (Phase 2)

- **H1 — no cross-host path-form translation (primary).** `_shell_path()`
  (`core/pysrc/_githooks.py:261-270`) only replaces `\` with `/`; it never
  translates between the three spellings of the same file that exist on a
  Windows-drive-hosted repo: Windows-native (`C:/Users/...`), Git-Bash/MSYS
  (`/c/Users/...`), and WSL drvfs (`/mnt/c/Users/...`). `_enforcer_path()` and
  `_git_common_dir()` (lines 165-166, 202-244) resolve in whichever spelling the
  *calling* interpreter's OS uses, and that literal string is what's written into
  the shared `.git/codearbiter-hooksd/*.path` registry and baked into the shim's
  `D=` value (`_shim()`, line 586) — a value every worktree and host is required
  to share (ADR-0014, by design). **Verified asymmetry (Opus review):** Git-Bash's
  `test`/`[ -f ]` resolves BOTH `/c/...` and `C:/...`, but NOT `/mnt/c/...`; WSL
  bash resolves ONLY `/mnt/c/...`. No single spelling satisfies both hosts.
- **H2 — installer race / non-resilient two-phase shim write (#686).**
  `install()`'s full probe (`core/pysrc/_githooks.py:859-892`) writes
  `pre-commit` and `pre-push` as two independently-atomic `os.replace` calls
  with no cross-file transaction, **and** the `try/except` at lines 877-889 is
  *inside* the `for phase in PHASES:` loop — one phase's write throwing (AV
  scan, drvfs lock, anything) leaves the other phase already rewritten, a
  permanent split with **zero concurrency required**. Concurrent `install()`
  calls from different host environments (both missing the on-disk hooks-dir
  cache, which never "hits" across hosts — `_cached_hooks_dir`/`install()`
  lines 730-853 compare host-local path strings) make the same split far more
  likely, but the single-process partial-write case is a distinct, simpler
  mechanism and needs its own coverage.
- **H3 — install()/doctor's "already current" check never accounts for a
  sibling host, so the shim churns and flaps on every alternating
  SessionStart; a "healthy" doctor run is invalidated by the very next
  session on the other host.** (Revised — see "Corrected from initial spec"
  below.) `check_git_hook_freshness` (`core/pysrc/doctor.py:317-391`) actually
  DOES fail today when run on the host whose Git/shell can't resolve a
  foreign-spelled entry (`_hooks_current` line 349 string-compares a
  regenerated `_shim(dropin_dir, phase)` against the on-disk shim and fails at
  350-352 on any spelling mismatch; `live_registered_plugins`
  (`_githooks.py:481`) filters on `os.path.isfile`, which is False for a
  foreign-hosted spelling, driving `fail(...)` at doctor.py:360-364 — both fire
  before the live-fire probe at 365-368 is ever reached). The real defect is
  upstream of doctor: because the cache/"already current" checks are computed
  in the caller's own path spelling, EVERY SessionStart on either host treats
  the shared shim as stale and rewrites it to that host's own spelling —
  literally the pre-ADR-0014 "shim rewritten to whichever host ran last"
  problem, recurring one layer up for the `D=` drop-in-dir string instead of
  the enforcer path ADR-0014 already fixed. A doctor run is only ever a
  snapshot of whichever host wrote last; it gives no assurance past the
  sibling's next SessionStart.
- **H5 — NEW, found by Opus review: `trusted-executables.identity` silently
  hard-locks with no diagnostic.** `_refresh_trusted_identity` writes
  `PY`/`git` executable paths through the same backslash-only `_shell_path`
  (`_githooks.py:519`); a Pi/WSL session writes WSL-spelled paths, and a
  Windows host with neither trust env var set returns early (lines 511-517)
  and never rewrites it. The shim's identity branch then dies at line 596
  (`[ -n "$IDENTITY_OWNER" ] && [ -f "$PY" ] && [ -f "$G" ] || exit 1`) with
  **no stderr message at all** — unlike the `.path`-registry fail-closed path,
  this one is invisible and does not self-heal from a `.path` entry's normal
  refresh cycle.
- **H4 — boring/environmental: local mount misconfiguration, not a general
  defect.** Considered and refuted: the failure mechanism (H1) is structural —
  it reproduces for any Windows-drive repo shared between WSL's default `/mnt/`
  automount and Git for Windows' bundled Git-Bash, not a peculiarity of this
  machine's WSL/mount settings. REFUTED as the primary cause.

### Corrected from initial spec (post Opus-review)

The first draft of this spec mis-stated H3 as "doctor reports healthy in the
broken state" and proposed a regression test that would already pass today —
that would have violated `/ca:fix`'s must-fail-before-fix rule. The Opus
reviewer verified doctor already fails correctly on direct inspection
(`_hooks_current`/`live_registered_plugins`, cited above); the real, still-open
defect is the churn/flapping described in H3 above, not a false-healthy report.

## Evidence ledger (Phase 3)

| H | Verdict | Cited evidence |
|---|---|---|
| H1 | CONFIRMED | `_githooks.py:261-270` (`_shell_path`, backslash-only); `:165-166`, `:202-244` (host-local resolution); verified Git-Bash resolves `/c/...`+`C:/...` but not `/mnt/c/...`, WSL resolves only `/mnt/c/...` — no shared spelling exists. |
| H2 | CONFIRMED | `_githooks.py:859-892` loop, `try/except` at 877-889 scoped inside the per-phase loop (single-process partial-write hazard); `_cached_hooks_dir`/`_confirmed_no_local_hooks_path` (730-753, 654-696) host-local, so concurrent cross-host installs both fall through to the full loop and can interleave at file granularity too. |
| H3 | CONFIRMED (revised) | `doctor.py:349-352` (`_hooks_current` string-compare fails on spelling mismatch), `:360-364` (`live_registered_plugins`/`isfile` fails on foreign spelling) — doctor already fails correctly today; the defect is that `install()`'s cache/staleness check (same functions) has no concept of "a sibling host wrote a validly-different spelling," so it rewrites every session, and a green doctor run proves nothing about the next session on the other host. |
| H5 | CONFIRMED (new) | `_githooks.py:519` (`_shell_path` on trust identity), `:511-517` (asymmetric refresh — a host with no env vars never rewrites a stale/foreign identity), `:587-598` and specifically `:596` (bare `exit 1`, no message) in the generated shim's identity branch. |
| H4 | REFUTED | Mechanism is structural per H1, not configuration-dependent. |

## Root-cause decision (Phase 4) — SPLIT disposition

The cluster resolves into two dispositions, not one — collapsing them into a
single exit would either force a design change through as a "pure fix" or
stall genuine bugs behind a design debate they don't need.

### Exit (a) — confirmed code bugs → `/ca:fix` (no ADR needed)

B1 (H2), B2 (H5), and B3 (H3) are bounded robustness/observability defects in
`core/pysrc/_githooks.py` / `doctor.py` with no design ambiguity:

- **B1 — partial/interleaved two-phase shim write.** Make the `pre-commit`/
  `pre-push` write-pair fail atomically as a set (both succeed or neither is
  applied; a mid-loop exception must not leave one phase rewritten and its
  sibling stale) — this closes the single-process partial-write hazard
  regardless of concurrency, and narrows (but does not by itself eliminate —
  see Exit (b)) the cross-host race window.
- **B2 — silent identity lockout.** At minimum, add a diagnostic message to
  the shim's identity-branch `exit 1` (line 596) so this failure is at least
  as debuggable as the "no registered git-enforce.py" case; apply the same
  spelling-robustness fix chosen for the `.path` registry (once decided, see
  Exit (b)) to `trusted-executables.identity` too, so the two mechanisms don't
  diverge.
- **B3 — churn/flapping across alternating SessionStarts.** Teach the
  cache/"already current" checks that a differently-spelled-but-otherwise-valid
  sibling entry is not automatically "stale" just because it doesn't
  string-match this host's own rendering, so a stable cross-host pair doesn't
  perpetually rewrite itself every session; and make doctor's freshness report
  explicit that a green result reflects only the last SessionStart's host,
  not a durable cross-host guarantee.

**Regression test obligations (must fail before fix code):**
1. A single-process `install()` call whose second phase write throws must
   leave the drop-in dir/shim pair in its PRIOR consistent state, never a
   split pair (covers B1 without needing concurrency).
2. Two interleaved `install()` calls (two host-spelling contexts) must not
   leave `pre-commit`/`pre-push` on mutually inconsistent `D=` values (covers
   B1's concurrent case).
3. A `trusted-executables.identity` entry written in a foreign spelling, read
   by a host with no trust env vars set, must produce a non-empty diagnostic
   before the shim exits non-zero (covers B2's silence).
4. Alternating simulated SessionStarts from two host-spelling contexts must
   converge to a stable state (no unbounded rewrite churn), and a doctor
   "healthy" result must be correctly scoped/labeled as host-specific rather
   than implying cross-host durability (covers B3).

### Exit (b) — design ambiguity → `/ca:adr`, user attribution required

**H1, the cross-host path-form translator, does NOT get exit (a).** ADR-0014's
own "Alternatives considered" section already rejected "multiple-candidate
path embedding / runtime cache glob" for the enforcer-path problem, citing
"an unverified, host-layout-guessing filesystem search on every commit under
Windows Git-Bash — a fragile git-level backstop is worse than the accepted
trade." A translator that tries multiple candidate spellings at shim-exec
time (the only mechanism that can work, since no single spelling resolves on
both Git-Bash and WSL) is the same shape of fix, one layer over. Whether that
previously-rejected tradeoff still holds — or whether the now-demonstrated
real-world blast radius (three filed issues, commits blocked, a "safe" false
block that still stops releases) changes the calculus — is a decision only
the user can make, not something this investigation or `/ca:fix` should
decide unilaterally. `.codearbiter/tech-stack.md`'s "WSL... unsupported" line
is a *descriptive* note with no backing ADR, but ADR-0014 itself is exactly
the backing decision whose rationale a translator fix would need to revisit.

The question for the user: **do we (i) revisit ADR-0014's rejection and build
the bounded 3-way translator (accepting its previously-named risk: an
unverified, host-layout-guessing candidate search on every commit), or (ii)
keep WSL+Git-for-Windows mixed use formally unsupported and stop at the
Exit (a) hardening above (B1-B3), which makes the failure fast, non-flapping,
and — via B2/B3 — loudly diagnosed instead of silently or confusingly
fail-closed?**

## Handoff (Phase 5)

- Exit (a): route B1/B2/B3 (with their 4 regression test obligations) to
  `/ca:fix`. This alone fixes #686 outright and substantially improves #684's
  and #683's failure mode (loud, stable, diagnosable) even without the
  translator.
- Exit (b): surface the ADR question above to the user before any translator
  code is written; author via `/ca:adr` only with explicit user attribution
  once decided.
