# Plan: session-hygiene

**Spec:** `specs/session-hygiene.md` (sprint) over `specs/standup-hygiene.md` +
`specs/pr-babysitter.md`.
**Status:** APPROVED — 2026-06-13 (executing)
**Backend:** premium. **Posture:** balanced. **Order:** Feature 1 → Feature 2.

The `Status` column is the resume ledger: `TODO` → `ACCEPTED` (recorded by
`subagent-driven-development` as each task passes its gates). An interrupted sprint
re-enters at the first non-`ACCEPTED` task.

Maps to acceptance criteria: SH-n = `standup-hygiene.md` criterion n; PB-n =
`pr-babysitter.md` criterion n.

## Slice A — standup briefing in the SessionStart hook (Feature 1)

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 1 | Pure-logic helpers for briefing/standup — parse `git status --porcelain`, ahead/behind, remote-merged branches (excl. current/default), `git worktree list` stale set, stash count | `plugins/ca/hooks/_standuplib.py` (new) | unittest: each parser returns expected struct on fixture strings; merged-branch parser excludes current + `main` | — | auto | ACCEPTED |
| 2 | RED: first-of-day marker gating — no marker for local date → full briefing + marker written; marker present → no full briefing | `plugins/ca/hooks/tests/test_standup.py` (new) | Test red before impl | 1 | auto | ACCEPTED |
| 3 | Impl first-of-day briefing in SessionStart: full briefing once per local date, marker at `.codearbiter/.markers/standup-<YYYY-MM-DD>` | `plugins/ca/hooks/session-start.py`, `_standuplib.py` | Task 2 green (SH-1) | 2 | auto | ACCEPTED |
| 4 | RED+impl: later-session offer line — marker present + ≥1 actionable condition → exactly one offer line; marker present + none → silent | `test_standup.py`, `session-start.py` | Tests green (SH-2) | 3 | auto | ACCEPTED |
| 5 | RED+impl: dormancy — no `arbiter: enabled` → neither briefing nor offer line | `test_standup.py`, `session-start.py` | Test green (SH-3) | 3 | auto | ACCEPTED |
| 6 | RED+impl: non-blocking background fetch — detached `git fetch` with timeout; fetch-hangs stub → hook returns within budget, briefing renders from last-completed fetch marked stale | `plugins/ca/hooks/session-start.py`, `_standuplib.py`, `test_standup.py` | Test green (SH-4); hook never awaits network | 3 | auto | ACCEPTED |
| 7 | RED+impl: read-only guarantee — git state (porcelain, branches, stashes, worktrees) byte-identical before/after session start | `test_standup.py`, `session-start.py` | Test green (SH-5) | 6 | auto | ACCEPTED |
| 8 | Briefing content assembly — reuse `arbiter_state` (overrides-since-checkpoint, aging CONFIRM/tasks) + `head_branch`/`git_dirty`; display-only, no action | `plugins/ca/hooks/session-start.py`, `_standuplib.py` (factor shared logic) | unittest on assembled briefing struct; no duplication of `statusline.py` logic beyond shared helper | 1,7 | auto | ACCEPTED (stale-worktree classification carried to task 10) |
| 9 | `py_compile` + cold-install/SessionStart-injection regression still green | `plugins/ca/hooks/*` | `python -m py_compile session-start.py _standuplib.py`; existing `test_session_start.py` + cold-install matrix pass | 3-8 | auto | ACCEPTED |

## Slice B — `/ca:standup` gated command (Feature 1)

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 10 | RED+impl: standup action candidate logic — ff-eligible only on clean tree; prune list excludes current/default; stale-worktree set | `plugins/ca/hooks/_standuplib.py`, `test_standup.py` | Tests green (SH-6 clean-tree gate, SH-8 exclusions) | 1 | auto | ACCEPTED |
| 11 | Author `/ca:standup` command — per-action confirm; ff-only pull (refuse on divergence/dirty); branch & worktree prune behind explicit per-item confirm; stash/dirty/un-pushed report-and-route only | `plugins/ca/commands/standup.md` (new) | Body specifies `--ff-only`, clean-tree gate, current/`main` exclusion, per-item confirm, report-only surfacing (SH-6,7,8,9,10) | 10 | auto | ACCEPTED |
| 12 | Catalog + routing wiring | `plugins/ca/COMMANDS.md`, `plugins/ca/README.md`, `${CLAUDE_PLUGIN_ROOT}/includes/routing-table.md` | `check-plugin-refs.py` green; `/ca:standup` row present | 11 | auto | ACCEPTED |

## Slice C — PR babysitter command + flag (Feature 2)

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 13 | RED+impl: babysitter flag reader mirroring `CODEARBITER_PRUNE` — `CODEARBITER_BABYSIT` default off; on-red depth `CODEARBITER_BABYSIT_ONRED` default `propose`; two-layer gate vs `arbiter_active` | `plugins/ca/hooks/_babysitlib.py` (new) or `_hooklib.py`, `plugins/ca/hooks/tests/test_babysit.py` (new) | Tests green via `env=` injection (PB-5 default propose, PB-8 default off, PB-10 dormant) | — | auto | ACCEPTED |
| 14 | Author `/ca:watch <PR>` command — detached `gh pr checks <PR> --watch` (no poll loop); `gh` precondition failure surfaced; on-red diagnose at depth `propose`\|`branch` (branch = unmergeable `spike/fix-*`, no tracked-file edit at `propose`); on-green notify + merge **offer**, never `gh pr merge`; default-branch merge routes through hard gate | `plugins/ca/commands/watch.md` (new) | Body satisfies PB-1,2,3,4,6,7; explicitly no interval/model-wake loop | 13 | auto | ACCEPTED |
| 15 | Wire global flag into PR flow — flag on → `/ca:pr` auto-attaches watcher; off → not (ad-hoc `/ca:watch` still works); never auto-set the flag | `plugins/ca/commands/pr.md` | Body satisfies PB-8,9; mirrors prune.md "MUST NOT auto-enable" clause | 13,14 | auto | ACCEPTED |
| 16 | Catalog + routing wiring | `plugins/ca/COMMANDS.md`, `plugins/ca/README.md`, `${CLAUDE_PLUGIN_ROOT}/includes/routing-table.md` | `check-plugin-refs.py` green; `/ca:watch` row + flag doc present | 14,15 | auto | ACCEPTED |

## Slice D — release hygiene (carried into Phase 3 landing)

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 17 | Version bump `2.1.0-beta.3` → `2.1.0-beta.4`, synced 3 places + CHANGELOG entry | `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca/README.md` (badge), `CHANGELOG.md` | Three version strings agree; dated CHANGELOG section; `version-bump` CI guard passes | 1-16 | auto | ACCEPTED |
| 18 | Full CI-parity sweep green before landing | repo | `test_hook_guards.py`, `test_hooks_cold_install.py`, `check-plugin-refs.py`, JSON manifest parse, `py_compile` on touched hooks all green | 17 | auto | ACCEPTED |
| 19 | Land via `commit-gate` → `finishing-a-development-branch` (auto open-PR; merge deferred to user) | branch / PR | Suite green; PR opened; NOT merged | 18 | **HARD: merge-to-default → user** | ACCEPTED (PR #46; merge → user) |

## Notes

- No `plugins/ca/tools/**` change planned → vitest/typecheck leg not triggered;
  confirm at task 18.
- SH/PB criteria that are command-prose behaviors (SH-6..10 wording, PB-1..4,6,7)
  are verified by the authoring/ref gates, with the testable sub-logic pushed into
  `_standuplib.py` / `_babysitlib.py` for unit coverage (tasks 1, 10, 13).
- Auto-decisions during execution log to `.codearbiter/sprint-log.md` (append-only)
  with confidence flags; `low`-confidence calls are surfaced in the Phase 3 summary.
