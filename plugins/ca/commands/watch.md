---
description: Watch a PR's CI to completion — diagnose on red, notify and offer the merge on green. Never auto-merges.
argument-hint: "<PR number | url | branch>"
---

# /ca:watch — PR CI babysitter

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `/ca:pr --watch` for new usage. This installed route remains
> functional under the command-route compatibility policy at ${CLAUDE_PLUGIN_ROOT}/includes/command-compatibility.md;
> continue with the unchanged watcher workflow below.
<!-- catalog-compatibility-notice:end -->

Watch a pull request's checks to completion without babysitting them by hand. One
detached `gh` process waits; the GitHub CLI itself re-reads the checks on its refresh
interval, but the model is not called while CI runs — arbiter wakes once, on the
verdict — diagnoses a red, or offers you the merge on a green. Arbiter never
pulls the merge trigger.

## Precondition

Requires the GitHub CLI authenticated (`gh auth status`). If `gh` is absent or
unauthenticated, report the precondition failure naming `gh` and STOP — do not start
a phantom watcher.

## Flow

1. **Resolve the PR** from `$ARGUMENTS` (number, URL, or branch; default to the
   current branch's PR).
2. **Watch to completion** — run the watch as ONE **detached background task**:
   ```
   gh pr checks <PR> --watch
   ```
   The `gh` process blocks until every check finishes and then exits non-zero on
   failure. While it waits, `gh` itself refreshes the check status on its own
   interval (`gh pr checks --help`: `-i, --interval` "Refresh interval in seconds in
   watch mode", default 10 in gh 2.93.0) — those are CLI-side API requests, not model
   calls. There is no agent polling loop and no interval-based model wake-up: arbiter
   is re-invoked once, when the watch process exits.
3. **On red** — retrieve the failing job's logs (`gh run view --log-failed` /
   `gh pr checks`) and act at the configured depth. Resolve that depth with the
   canonical resolver rather than reading the env var by hand (so the accepted
   values can't drift). Resolve the interpreter once by presence —
   `PY=python3; { command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; } || PY=python`
   — never `python3 X || python X`, which reruns X on any nonzero exit (#577):
   ```
   "$PY" "${CLAUDE_PLUGIN_ROOT}/hooks/babysit.py" --root "${CLAUDE_PROJECT_DIR}"
   ```
   It prints one JSON line; act at its `on_red` value (`CODEARBITER_BABYSIT_ONRED`,
   default `propose`):
   - **`propose`** — name the likely cause and propose a concrete fix. Do NOT edit
     any tracked file; applying the fix routes through `/ca:fix` or `/ca:feature`.
   - **`branch`** — additionally open a `spike/fix-*` branch carrying the proposed
     change for review. That branch is a spike: it can never PR or merge. The default
     branch is left untouched.
4. **On green** — notify the user and present a merge **offer** (the `gh pr merge`
   command, ready to run). The watcher itself NEVER merges. If the PR targets the
   default branch, the merge routes through the merge-to-default hard gate — the offer
   cannot bypass it.

## On/off

A global flag, `CODEARBITER_BABYSIT` (default **off**, mirrors `CODEARBITER_PRUNE`),
governs auto-attachment: when on, `/ca:pr` auto-attaches a watcher to the PR it
opens. `/ca:watch <PR>` works ad-hoc regardless of the flag. The flag is never set on
the user's behalf — enabling it is the user's explicit choice. Both the command and
the flag are dormant in a repo without `arbiter: enabled`.

## When NOT to use

- Open the PR first → `/ca:pr`.
- Apply a fix for a diagnosed red → `/ca:fix` (or `/ca:feature`).
- Review a diff without watching CI → `/ca:review`.

## Hard gate

- MUST NOT auto-merge. Green → notify + offer only; the watcher never invokes
  `gh pr merge`.
- A merge into the default branch MUST route through the merge-to-default hard gate —
  the green offer cannot and does not bypass it.
- MUST NOT implement a polling loop that re-invokes the model on a timer — the watch
  is one detached `gh pr checks --watch` process (which refreshes checks itself).
- MUST surface a missing/unauthenticated `gh` as a precondition failure, not a silent
  no-op.
- At depth `propose` MUST NOT edit any tracked file; at depth `branch` the proposed
  change lands only on an unmergeable `spike/fix-*` branch.
