# Plan — pre-release-hardening

Spec: `.codearbiter/specs/pre-release-hardening.md`
Branch: `feat/pre-release-hardening` (worktree @ `.claude/worktrees/pre-release-hardening`)
Base: `origin/main` @ 32b116b

## Conventions (every task)

1. Edit **`core/pysrc/`** only — never a vendored `plugins/*/hooks/` copy.
2. Run `python tools/sync-core.py` after the edit (tests import the vendored copy).
3. Test-first (`tdd` Phase 1): the failing test exists before the implementation.
4. Stdlib `unittest` only (ADR-0004).
5. All git writes use `git -C <worktree>`.

## File-conflict map (drives the ordering)

- `core/pysrc/pre-bash.py` — Lane A **and** Lane B → **sequential**, A before B.
- `core/pysrc/session-start.py` — Lane C **and** Lane D → **sequential**, C before D.
- `core/pysrc/_hooklib.py` — Lane A (root helper) **and** Lane C (lock hoist) → **sequential**.
- Lane E touches `_colorlib.py` / `statusline.py` / `test_ledgerlib.py` / docs only → **disjoint**, may
  run parallel with Lane A.

## Slice 1 — Lane A: #223 (MVP; the enabler)

Unblocks correct guard behavior in this very worktree, and removes the incentive that caused #237.

| # | Task | Files | Verification |
|---|---|---|---|
| A-1 | Failing test: worktree false-positive + false-negative. Extend `TestGitCwdEndToEnd` — build a repo with a linked worktree; assert H-01 BLOCKS a commit from a worktree sitting on `main` while the main checkout is on a feature branch (the false negative), and does NOT block a worktree on `feat/*` while main checkout is on `main` (the false positive). | `plugins/ca/hooks/tests/test_repo_resolution.py` | Test **fails** (both cases) against current code |
| A-2 | Failing test: heredoc prose. `gh pr create --body "$(cat <<'EOF' … git commit -m x … EOF)"` must NOT trip H-01. `bash <<'EOF' … git commit … EOF` must still BLOCK. | `plugins/ca/hooks/tests/test_repo_resolution.py` | Test **fails** on case 1, passes case 2 |
| A-3 | Add cwd-aware repo resolution. Introduce an effective-cwd resolver: derive the git root from the command's effective cwd (process cwd / payload `cwd`), preferring it over `CLAUDE_PROJECT_DIR` when the two resolve to different git roots. Reuse the linked-worktree-aware precedent in `_gitlib.head_branch` / `_gitlib.project_root` (parses the `gitdir:` pointer file). Keep gate **markers** resolving to the pinned project root per spec D-2, and comment that split as intentional. | `core/pysrc/_hooklib.py`, `core/pysrc/pre-bash.py`, `core/pysrc/hostapi.py` | A-1 passes; `sync-core.py`; full `test_repo_resolution.py` + `test_h01_failclosed.py` green |
| A-4 | Narrow the raw-`cmd` fallback (spec D-3). Keep `X_RE.search(cmd)` fallback only when the heredoc's **consuming command is a shell** (`bash`/`sh`/`zsh`/`python -c`/…); drop it for non-shell consumers (`gh`, `curl`, …). Do not delete the fallback. | `core/pysrc/pre-bash.py` (~576-599, `_strip_heredoc_bodies` ~504-517) | A-2 passes; `test_pre_bash_no_verify.py`, `test_hook_guards.py` green (no regression) |
| A-5 | Sync + full-suite regression. | `tools/sync-core.py` | `unittest discover -s plugins/ca/hooks/tests`; every `.github/scripts/test_*.py`; `sync-core.py --check` |

**Exit:** AC-1, AC-2. From here on, `git -C` is no longer required for correctness (keep using it anyway until merged).

## Slice 2 — Lane B (#237) + Lane E (harvest), parallel-safe with each other

### Lane B — #237

| # | Task | Files | Verification |
|---|---|---|---|
| B-1 | Failing test: interpreter forgery. `python -c "...write security-gate-passed..."`, `python3 -c`, `node -e`, `perl -e`, `ruby -e`, `sh -c` naming a `.markers/` gate-marker path must all BLOCK (H-19). | `.github/scripts/test_hook_guards.py` (H-19 block) | Test **fails** — the verb list omits interpreters |
| B-2 | Extend `GATE_MARKER_WRITE_RE`'s verb set with the interpreters. Watch the `[^\|;&]*` segment bound — an interpreter one-liner's payload is a quoted string, so confirm the marker path is still reachable by the pattern within the same segment. | `core/pysrc/pre-bash.py:244-260` | B-1 passes; existing H-19 cases (`mv`/`cp`/`tee`/redirect) still block; no false positive on a benign `python -c` |
| B-3 | Correct the docs claim (AC-4). Find and rewrite the `.codearbiter` directory reference asserting a hand-written marker "can't satisfy a gate anyway". Replace with the truth: the Write/Edit/Bash flanks add friction and an audit trail on the cooperative path (ADR-0010); a determined same-user process can still mint one. | docs (locate via grep), possibly `site/` | Claim gone; `npm test` + build if `site/` is touched (per repo rule: site changes run the vitest suite, not just build) |

**Exit:** AC-3, AC-4.

### Lane E — harvest (disjoint files; may also start during Slice 1)

| # | Task | Files | Verification |
|---|---|---|---|
| E-1 | `_read_custom`: add `RecursionError` to the except tuple (deeply nested custom theme JSON). Test-first. | `core/pysrc/_colorlib.py` | New test in `plugins/ca/hooks/tests/test_colorlib.py` |
| E-2 | Invalid-hex boundary cases (`#01020`, `#0102030`, `#0102GG`) assert the violet fallback. | `plugins/ca/hooks/tests/test_colorlib.py` | Tests pass |
| E-3 | Strip C0/OSC control chars from `display_model` and `sub_label` before render. Test-first. | `core/pysrc/statusline.py` (+ `_colorlib.py` if the helper lands there) | New test; injected `\x1b]0;…\x07` / C0 bytes do not reach the rendered line |
| E-4 | Restore the time-bounded negative wait (~0.2s) on `second_acquired` after `second_attempted` in the contention harness. | `plugins/ca/hooks/tests/test_ledgerlib.py` (`_serialize_transactions`, ~192-231) | Serialization is actually asserted, not assumed |
| E-5 | Codex py2-Windows host: document out-of-support, **or** extend the PY2 cold-install scenario to assert the codex Windows entry never exits 0. | `.github/scripts/test_hooks_cold_install.py` or docs | Test or doc lands |

**Exit:** AC-9.

## Slice 3 — Lane C: #271

| # | Task | Files | Verification |
|---|---|---|---|
| C-1 | Failing test: board lost-update + duplicate dotted ID under contention. Pattern-match `_serialize_transactions` (`test_ledgerlib.py:192-231`) — specifically the `while_first_holds` shape used by `test_same_session_concurrent_updates_do_not_regress_accounting`. **New file** (`taskwrite.py` has no test today). | `plugins/ca/hooks/tests/test_taskwrite.py` (new) | Test **fails**: an edit is lost and/or IDs collide |
| C-2 | Hoist the lock. Move `_acquire_lock`/`_release_lock` (+`LOCK_WAIT`) from `_ledgerlib.py:153-201` into `_hooklib.py` as a shared `acquire_lock`/`release_lock`. Repoint `_ledgerlib`'s two call sites (`:427`, `:504`). **Import-cycle check:** `_ledgerlib` currently imports nothing from `_hooklib`; `_hooklib` imports only `hostapi`. Verify no cycle. | `core/pysrc/_hooklib.py`, `core/pysrc/_ledgerlib.py` | `test_ledgerlib.py` fully green (all lock tests, incl. fail-soft latency bound ≤0.35s) |
| C-3 | Lock + **re-read-under-lock CAS** in `taskwrite` (spec D-4). Take the lock, **then** read the board, re-run the pure transform on the fresh text, `os.replace`, release. This is what fixes the duplicate-ID mint — `next_seq` must run on fresh text. Fail-soft on `None` lock handle: match `_ledgerlib`'s convention, but **do not silently drop a board write** — surface it. | `core/pysrc/taskwrite.py:73-120` | C-1 passes; `.github/scripts/test_taskwriter.py` green |
| C-4 | Failing test: dev-marker clobber. Session B's `clear_dev_marker` must not remove session A's live marker nor append a synthetic `DEV: exit`. Extend `TestDevExitAudit`. | `plugins/ca/hooks/tests/test_session_start.py:383-440` | Test **fails** — the clear is unconditional (`session-start.py:487-490`) |
| C-5 | Session-scope the dev marker. `session-start.py` must start **reading its stdin payload** (it does not today) to obtain `session_id` — precedent: `pre-read.py:51`, `statusline.py:545`, and the session-keyed marker hash in `_readinjectlib.marker_path` (`:786-812`). Carry the session id in the marker; clear only your own. **Degrade safely** when no `session_id` is available (Codex parity is unverified — fall back to today's behavior rather than never clearing). Update the three readers: `_arbiterstatelib.dev_active` (`:202`), `_hooklib._STALE_FLOWS` (`:878-882`), and the `/ca:dev` + `/ca:arbiter` prose entry/exit paths. | `core/pysrc/session-start.py:450-490`, `core/pysrc/_arbiterstatelib.py`, `core/pysrc/_hooklib.py`, `core/surface/commands/dev.md`, `core/surface/commands/arbiter.md` | C-4 passes; `test_session_start.py` green |

**Exit:** AC-5, AC-6. **Note:** C-5 touches `session-start.py` — Lane D must follow, not overlap.

## Slice 4 — Lane D: #265 + ADR-0014

**This lane reverses a documented ACCEPT-RISK** recorded in `_githooks.py`'s own header (lines 25-46),
which explicitly considered and rejected both multiple-candidate embedding and a runtime cache glob.
The drop-in dir is admissible precisely because it satisfies that header's *own stated exit condition*
("a shared, non-versioned shim target") — it reads a directory **we own** inside `.git/`, not an
unknown host cache layout. The ADR must say so.

| # | Task | Files | Verification |
|---|---|---|---|
| D-1 | **[HARD GATE]** Author **ADR-0014** — reversing the git-hook shim fail-open. User-attributed via `/ca:adr`. Must state: the accepted-risk being reversed, why the drop-in dir is not the rejected glob, the new fail-**closed** blast radius, and the residual (a stale entry from an uninstalled plugin). **Halt for user attribution.** | `.codearbiter/decisions/0014-*.md` | ADR exists, user-attributed. (0013 is taken by ca-pi.) |
| D-2 | Failing test: two plugins registered, remove one → the backstop still resolves to the survivor. Zero resolvable enforcers → shim **blocks** (non-zero), not exit 0. | `plugins/ca/hooks/tests/test_git_hooks.py` (real throwaway git repo, `_GitFixture`) | Test **fails** — today's shim exits 0 |
| D-3 | Implement the drop-in dir. `install()` registers this plugin's enforcer at `.git/codearbiter-hooksd/<plugin>.path`; `_shim()` iterates `"$D"/*.path`, execs the first that resolves, and **fails closed** with a message if none do. `uninstall()` drops only its own `.path`. Rewrite the header block (25-46) — it is the ADR-of-record today and must now point at ADR-0014. | `core/pysrc/_githooks.py:102-160, 316-414`, `core/pysrc/session-start.py:593-602` | D-2 passes; `test_git_hooks.py`, `.github/scripts/test_hooks_cold_install.py` green |
| D-4 | Sync + validate the codex plugin manifest if hook wiring changed. | `tools/sync-core.py`, `.github/scripts/validate_codex_plugin.py` | `sync-core.py --check`; validator green |

**Exit:** AC-7, AC-8.

## Slice 5 — Land

| # | Task | Verification |
|---|---|---|
| L-1 | Full fresh-run suite: `unittest discover -s plugins/ca/hooks/tests`; every `.github/scripts/test_*.py`; `tools/sync-core.py --check`. | AC-10 green |
| L-2 | `commit-gate` → `finishing-a-development-branch` (auto-selects open-PR). Board done-flips ride **with** this PR, not a lagging chore commit. | PR open; merge decision is the user's |
| L-3 | PR body closes #223, #237, #271, #265. Notes #270 deferred with its rationale. | — |

## Ordering summary

```
Slice 1 (A: #223)  ──┬──> Slice 2 (B: #237)  ──> Slice 3 (C: #271) ──> Slice 4 (D: #265) ──> Slice 5
                     └──> Lane E (harvest, disjoint — may start immediately)
```

MVP slice = **Slice 1**. It alone fixes the guard bug that (a) blocks correct worktree enforcement,
(b) created the #237 incident, and (c) is currently forcing every git write in this sprint through a
`-C` workaround.
