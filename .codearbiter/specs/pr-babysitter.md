# Spec: pr-babysitter

**Status:** APPROVED — 2026-06-13 (into sprint session-hygiene); executing
**Feature 2 of 2** in the "session hygiene" brainstorm (the other: `standup-hygiene`).

## Problem

After opening a PR you babysit CI by hand — refreshing checks, digging into a red
job, remembering to merge once green. That attention-tax pulls you out of flow.
Arbiter should watch the PR, diagnose failures, and offer the merge — without ever
merging on its own.

## Scope

**In:**
- A **`/ca:watch <PR>`** command that watches a PR's CI to completion using
  `gh pr checks <PR> --watch` run as a **detached background task** — the server
  blocks until checks finish, so the model spends ~zero tokens while CI runs and is
  woken exactly once, on completion.
- **On red:** pull the failing job's logs and act at the configured depth:
  - `propose` (default): identify the likely cause and propose a concrete fix,
    stopping there — applying it routes through `/ca:fix` / `tdd`.
  - `branch` (opt-in): additionally open a `spike/fix-*` branch carrying the
    proposed change for review (never merges; the spike branch can never PR/merge).
- **On green:** notify the user and **offer** a one-keystroke merge. The user
  always pulls the trigger.
- A **global persistent on/off flag** (modeled on the prune flag): when on,
  `/ca:pr` auto-attaches a watcher to the PR it opens. `/ca:watch <PR>` works
  ad-hoc regardless of the flag. The flag can fully disable the feature.

**Out of scope (the boundary that keeps this honest):**
- **NEVER auto-merges.** Green → notify + offer only. Merge-to-default remains the
  §3 hard gate and a true manual stop — no exception, not even behind the flag.
- Never force-pushes, never merges (only the user's explicit merge), never closes
  or reopens PRs, never pushes to the PR branch on its own.
- Does not *fix* red autonomously — at most it proposes a change or stages it on an
  unmergeable spike branch; real implementation flows through `/ca:fix` / `tdd`.
- Not a poll loop — no interval-based model wake-ups (the token-inefficient path is
  explicitly rejected).

## Behavior detail

- **Mechanism:** the watch is `gh pr checks --watch` (server-side block) in a
  detached background task; on exit the model is invoked once with pass/fail.
  Requires `gh` to be installed and authenticated — a missing/unauthenticated `gh`
  is reported as a precondition failure, not a silent no-op.
- **On-red depth** is read from a setting (`propose` | `branch`), default
  `propose`.
- **Flag:** a global persistent setting (the prune-flag pattern). Default **off**.
  When on, `/ca:pr` starts a watcher for the PR it just opened. When off, only the
  explicit `/ca:watch <PR>` starts one.
- **Green offer:** arbiter surfaces the merge as an explicit offer; the merge
  itself is the user's action and, for the default branch, is a hard-gate stop that
  the offer cannot bypass.
- **Activation:** command and flag are live only in an `arbiter: enabled` repo.

## Acceptance criteria

1. `/ca:watch <PR>` launches the watch as a detached background task built on
   `gh pr checks <PR> --watch`; the implementation contains no interval/poll loop
   that re-invokes the model on a timer.
2. With `gh` absent or unauthenticated, `/ca:watch <PR>` reports a precondition
   failure naming `gh` and does not start a phantom watcher.
3. On CI completion **red**, arbiter retrieves the failing job's log and, at depth
   `propose`, emits a named likely-cause and a concrete proposed fix WITHOUT
   editing any tracked file.
4. At depth `branch`, on red arbiter additionally creates a `spike/fix-*` branch
   with the proposed change; that branch is marked unmergeable (cannot PR/merge),
   and the working `main`/default is untouched.
5. The on-red depth is governed by a setting whose default is `propose`: with no
   setting present, behavior is `propose` (no branch created).
6. On CI completion **green**, arbiter notifies and presents a merge **offer**; it
   performs no merge as part of the watch — `gh pr merge`/equivalent is never
   invoked by the watcher itself.
7. A green offer for a PR targeting the **default** branch routes the merge through
   the existing merge-to-default hard gate; the offer cannot and does not bypass
   that stop.
8. The global flag defaults **off**: in a fresh config, opening a PR via `/ca:pr`
   does NOT auto-attach a watcher.
9. With the global flag **on**, `/ca:pr` auto-attaches a watcher to the PR it
   opens; with the flag off, it does not (but `/ca:watch <PR>` still works).
10. Command and flag are dormant in a repo without `arbiter: enabled`.

## Open questions

None blocking. The `gh`-CLI dependency is an accepted precondition (consistent with
the repo already using `gh` for PR flows); on-red depth and the global flag default
(`off`) are sane defaults, revisable. No `[CONFIRM-NN]` raised.
