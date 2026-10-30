---
name: ca-standup
description: Daily repo hygiene — review the day's repo state, then perform selected cleanups. Fast-forward only, never destructive without a yes.
argument-hint: (none)
---

# $ca-standup — daily hygiene

The checklist you run when you sit down to code. The SessionStart briefing
*reports* hygiene state read-only; this command performs the cleanups you select.
Arbiter gathers and proposes; you decide each action's scope.

## Flow

The orchestrator reads the current repo state (reusing the briefing's read-only
computation — branch, ahead/behind, dirty tree, stashes, prune-candidate branches,
stale worktrees) and presents it, then offers each applicable action in turn. Skip
an action that has no candidates. Branch deletions stay per-item; worktree
removal and work archival may use one explicitly named selection. Never infer
that a yes to one action authorizes another.

1. **Fetch + fast-forward pull** — kick `git fetch`, then offer a **`--ff-only`**
   pull of the current branch. Eligibility is the briefing summary's
   `ff_pull_eligible` flag (SH-6: clean working tree AND behind upstream) — the same
   pure helper the SessionStart briefing computes, not a condition re-derived here.
   On a dirty tree the pull is withheld and the dirty state is reported instead. A
   diverged branch (would need a merge) is refused with a diverged-branch message —
   never a merge commit.
2. **Prune merged local branches** — list local branches already merged on remote
   (the `: gone]` upstream set), excluding the current branch and the default
   (`main`). Delete a listed branch only after an explicit per-branch confirmation;
   declining leaves it in place.

   A `: gone]` branch that was squash-merged will typically **refuse** plain
   `git branch -d` — its upstream is already pruned, so `-d` has nothing to test
   reachability against. Before reporting that as a stop, check for a merged PR
   record: `gh pr list --head <branch> --state merged --json headRefOid`. When a
   `MERGED` PR's `headRefOid` equals that branch's local tip, containment is
   proven and `git branch -D` is permitted — with the proof stated and the
   branch named in the confirmation — mirroring the `post-merge-cleanup` Phase 5
   contract. Without that proof, a refusal stays a report-and-stop; never guess.
3. **Remove stale worktrees** — list stale/merged worktrees (branch gone-or-merged,
   or path missing on disk), never the main worktree. Present the full stale list
   together with each item's evidence, then offer removal as an explicitly
   **enumerated group** — one confirmation that names every member — as well as
   per-item confirmation for anyone who wants to keep some. Declining the group
   falls back to per-item confirmation, and declining any item leaves it intact.
4. **Surface stashes / dirty / un-pushed** — list stashes, uncommitted changes, and
   un-pushed commits, each with a suggested next step (`$ca-commit`, `git push`,
   `git stash show`). Report-and-route only: never discard a stash, reset, or push.
5. **Selected-owner drift sweep** — load the installed
   `../../includes/helper-invocation.md`
   card relative to this loaded standup resource. Resolve
   its literal `hooks/work.py` leaf and a compatible Python once; use the card's
   PowerShell or POSIX invocation for the current shell and never retry a failed
   helper under another interpreter (#577). Call `work.py list --limit 1` to
   select the owner:
   `owner: legacy` means the board, and a `project_id` field means native work.
   Stop if the command fails or returns neither shape.
   For the **legacy owner**, run `git log` over the recent merge window (since
   the last `ca`-scoped tag, or a rolling 30-day window when no tag exists) and
   pipe it to the installed `boardsync.py reconcile` helper resolved from the
   same loaded standup resource. Display
   DRIFTED tasks and informational UNKNOWN ids as advisory only. Resolve a
   drifted task through `$ca-task done <id>`; do not auto-flip the board.
   For the **native owner**, do not run `boardsync.py`: its dotted board IDs
   cannot establish native work state. Report that commit-to-work drift is not
   assessed by this sweep. A failed owner read is a stop for work hygiene, not
   permission to fall back to a second writer.

6. **Archival sweep — one named subset** (B-24, WS-03). For the **native owner**,
   page the resolved `work.py list --limit 64 --budget 65536`,
   passing the returned `--membership-sha256` on every later page. Inspect at
   most 256 entries in this sweep; state the omitted count if more remain.
   Select only `complete` entries with `completed_at` strictly more than 14
   calendar days old. `content_snapshot: false` means the preview is advisory;
   verify each selected item again on the archive branch before writing.

   For the **legacy owner**, retain the existing board classifier's dated done
   list and its exact dotted IDs or titles for ID-less rows. The work list can
   omit originless old rows; report its `unkeyed_count` and inspect those rows
   through the legacy board owner. A title may target an ID-less row only after
   proving it uniquely identifies the selected current done row; refuse an
   ambiguous title. An undated item has
   unknown age and is excluded unless the user explicitly asks to include its
   exact ID with `--allow-undated`.

   Present the eligible IDs or unique legacy titles and dates, then ask once for a **named subset** to
   archive. The user may select all, some, or none. Do not infer inclusion from
   silence; preserve declined items. One selection authorizes only these IDs.

   **If at least one ID was selected:** an archive is calendar-driven hygiene,
   not a consequence of any in-flight work, so it never rides another commit.
   Keep the current working tree and index, including its local
   `.codearbiter/.artifacts/` journal, intact. Fetch the configured default
   branch and verify its fetched tip. Stop on fetch or ref failure. Choose a new
   sibling path outside the current repository and a unique branch name such as
   `chore/work-archive-<YYYY-MM-DD>-<HHMMSSZ>`. This is a dedicated branch for
   the sweep. Require that the target path does not exist and the branch name
   is unused. Run `git worktree add -b <branch> <fresh-path> <fetched-default-tip>`;
   fail closed if the branch name already exists, and
   never reuse or overwrite the path.
   Verify the new worktree's HEAD is the fetched default tip and its working
   tree and index are clean before the first archive helper call. Run all
   subsequent reads and writes with the fresh worktree as the project cwd.
   Initialize its own local store through the installed helper as needed;
   preserve both worktrees' journals and do not copy or switch one between them.

   This worktree isolation is what makes the sweep committable at all: writing
   straight to disk on whatever branch happens to be current would either land
   on `main` (refused outright) or mix into an unrelated feature branch's staged
   work (a type split under commit-gate Phase 3) — see #573. One fresh branch per
   sweep, never reused across sessions.

   In that fresh worktree, repeat `work.py list --limit 1` and require the same
   owner (and native `project_id`) selected in step 5; stop if it changed.
   Re-read every selected ID or unique legacy title and
   its state/date. If it is
   missing, no longer complete, or no longer eligible, stop that item and report
   the changed scope. Do not substitute a same-title item. For the native owner,
   use the resolved `work.py get <work_id>` to obtain the current
   revision and model hash. Archive each still-eligible item through
   `work.py archive <work_id> --operation-id <stable-id>
   --expected-revision <revision> --expected-model-sha256 <hash>`.
   Reuse that operation ID and expected pair if the response is lost; report a
   conflict without overwriting a later edit. For the legacy owner, re-read the
   exact board row and use the resolved `taskwrite.py archive <exact-dotted-id>`
   for an ID-carrying row, whether or not it has a work origin. For an ID-less
   row, use `taskwrite.py archive <unique-title>` only after rechecking that
   the title still identifies exactly one completed row with the selected date.
   Pass `--allow-undated` only for an explicitly selected undated row. Stop if
   the row or its eligibility changed; never select the first same-title row.

   A selected set is one user choice, not one atomic write. Process IDs one at a
   time; on refusal, report completed and remaining IDs and retain the branch
   for recovery. The legacy helper's append to `done-tasks.md` before removing
   from `open-tasks.md` remains its interrupted-sweep recovery order.

   Stage only the selected owner's changed paths: native
   `.codearbiter/work/<work_id>.html` files, or legacy
   `.codearbiter/open-tasks.md` and `.codearbiter/done-tasks.md` (including the
   first-created archive file). Route legacy board prose through
   `$ca-chore docs`; route native canonical work-state changes directly
   through `commit-gate` with a homogeneous `chore` classification. Both use a
   dedicated archive commit and the normal PR path.
   Do not stage journals, generated compatibility views, or unrelated work.

Present a one-line summary of what was done and what was declined.

## When NOT to use

- A read-only state snapshot without acting → `$ca-status`.
- Install health (interpreter, payload, hooks) → `$ca-doctor`.
- Committing staged work → `$ca-commit`.

## Hard gate

- MUST pull with `--ff-only` and ONLY on a clean working tree — never a merge
  commit, never on a dirty tree, never a rebase.
- MUST exclude the current branch and the default branch from branch pruning, and
  the main worktree from worktree cleanup.
- MUST confirm branch deletions individually — no batched or implied yes.
  Worktree removals MAY be confirmed as one explicitly enumerated group (naming
  every member) or individually; either way there is no implied yes, and
  declining the group falls back to per-item confirmation rather than removing
  anything.
- MUST treat stash / dirty / un-pushed state as report-and-route only — never
  discard, reset, force, or push on the user's behalf.
- MUST NOT write to or force-push the default branch.
- MUST NOT auto-flip any board entry during the drift sweep — the sweep is advisory
  and read-only; resolving a drifted task is the user's decision and routes
  exclusively through `$ca-task done <id>`.
