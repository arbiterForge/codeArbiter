---
name: post-merge-cleanup
description: Finish an already-merged branch. Proves the branch is contained in the fetched default, classifies leftover artifacts as unique / redundant / superseded, returns to a clean --ff-only default checkout, and deletes the merged local branch — every discard confirmed per item. Routed to by /ca-cleanup.
---

# post-merge-cleanup

The walk back from a merged PR. Routed to by `/ca-cleanup`.

The work has landed on the default branch. What is left is local: the branch you
are standing on, and whatever the run left in the tree. This skill returns you to
a clean, fast-forwarded default checkout without losing anything you have not
explicitly agreed to lose.

**It is ordinary lifecycle work and never needs `/ca-override`.** When it
cannot proceed, it names the gate that stopped it. Issue #308 recorded the
alternative: with no owner for this transition, the routing loop reached for
`/ca-chore`, then for `/ca-override` — a bypass manufactured to cover a
coverage hole.

## Pre-flight

Read this, or STOP and surface the gap — never guess the default-branch name:

- `<project-root>/.codearbiter/CONTEXT.md` — the default-branch name.

If HEAD is already the default branch, there is no transition to make. Report the
dirty state read-only and exit; branch pruning across *other* branches belongs to
`/ca-standup`.

## Phase 1 — Prove the merge · gate: BLOCK

A branch that looks merged is not merged. Establish it against the network, not
against a stale local ref. This repo squash-merges by default, so SHA-ancestry
alone is the wrong instrument for most landings: it holds for a fast-forward or
a merge-commit landing, but a squash merge writes a new commit with no SHA
lineage back to the branch, and `--is-ancestor` will report non-zero for a
branch that landed cleanly. The gate is **content-containment**, proven by
whichever instrument fits the landing, always reported as a fact:

1. `git fetch` the remote holding the default branch. A fetch that fails STOPs —
   an unfetched comparison proves nothing.
2. Prove containment with two primary instruments plus a fallback, tried in
   order:
   1. **Ancestry** — `git merge-base --is-ancestor HEAD origin/<default>`. Holds
      for a fast-forward or merge-commit landing. If it holds, that is the
      proof: report it and move on.
   2. **Squash-merge proof via the PR record** — if ancestry fails, run
      `gh pr list --head "$(git branch --show-current)" --state merged --json number,state,headRefOid,mergeCommit`.
      A `MERGED` PR whose `headRefOid` equals local `git rev-parse HEAD` proves
      every commit on this branch rode that PR's squash into the default
      branch. Report the PR number, that `headRefOid == HEAD`, the merge
      commit (`mergeCommit.oid` in that JSON), **and** the ancestry check's
      negative result — all as facts, not as a failure. Corroborate with
      `git diff --quiet origin/<default> HEAD` when it happens to hold; a
      **non-empty** diff alongside a valid PR proof is normal (the default
      branch advanced since the merge landed) and is reported as a fact, never
      treated as a failure. The PR-record identity — `MERGED` plus
      `headRefOid == HEAD` — is the load-bearing proof; the diff is
      corroboration only when it happens to be fresh, never a requirement.
   3. **Fallback when `gh` is unavailable or no PR record exists** —
      `git diff --quiet origin/<default> HEAD` (the tree is byte-identical to
      the fetched default) is an acceptable fallback proof. Report it as such.
3. Report whichever instrument held as a fact — the default branch, the fetched
   SHA, and which of the three proofs established containment.

If none of the three hold, STOP exactly as today. Name the un-landed commits
and route to `/ca-pr`; nothing is deleted here.

> Deliberate deviation from issue #586's suggested contract: that suggestion
> required the squash-merge proof's diff to be empty. That requirement
> re-breaks this gate the moment any later PR merges to the default branch —
> the common state, not an edge case. The PR-record identity is what proves
> containment; the diff is corroboration, demoted from requirement to fact.

Gate: the remote is fetched and HEAD is proven contained in the fetched default
branch — by ancestry, by the PR-record squash proof, or by the byte-identical
fallback — or the skill has stopped.

## Phase 2 — Classify the residue · gate: BLOCK

List every dirty tracked change, every untracked file, and every stash reachable
from this branch. Classify each into exactly one of three, and say *why* for each:

- **Redundant** — byte-identical to content already on the default branch, or a
  regenerated build artifact whose generator is committed and rerunnable. Safe to
  remove because removing it loses no information.
- **Superseded** — an earlier form of something the merged PR already landed in a
  better shape. Name what supersedes it.
- **Unique** — anything else. This is the default: an artifact that cannot be
  proven redundant or superseded IS unique. Uncertainty classifies as unique, not
  as redundant.

Present the classification before touching anything. A file whose class you
cannot establish is reported as unique with the reason you could not classify it.

Gate: every dirty, untracked, and stashed artifact carries a class and a stated
reason, with unclassifiable items counted as unique.

## Phase 3 — Resolve the residue · gate: STOP

Per item, in the order Phase 2 listed them. Never batch:

- **Unique** — offer to keep it: `/ca-commit` it on this branch before the
  transition, move it aside, or leave it in place and stop the cleanup. It is
  discarded only if the user explicitly confirms *that item by name*, with the
  Phase 2 reasoning in view.
- **Redundant / superseded** — offer removal, one confirmation each, stating what
  it is and why it is safe. Declining leaves it exactly where it is.

A stash is never dropped here. Stashes are reported with `git stash show` as the
suggested next step, the same report-and-route contract `/ca-standup` holds.

If anything the user chose to keep would block the checkout, STOP and say so
rather than removing it anyway — but distinguish the two causes before naming
the artifact as the blocker:

- **The kept artifact genuinely conflicts** — its content collides with what
  checking out the default branch would need to change or remove. This is the
  user's to resolve, as today.
- **The local default ref lags the fetched one** — git refuses a checkout when
  a locally-modified tracked file differs between HEAD and the target ref, and
  a stale local `<default>` makes that difference larger than reality: content
  the kept artifact never actually touches can still collide with what a
  *current* default branch would carry. That gap is not the user's problem and
  not the kept artifact's fault. It is resolved by Phase 4's fast-forward-first
  step, not by discarding anything here. Issue #586 recorded the observed
  failure mode: a stale local `main` — 513 lines behind on
  `.codearbiter/gate-events.log` alone — made this STOP name a correctly-kept
  38-line artifact as the blocker, which invites exactly the silent discard
  this phase exists to prevent.

Gate: every item is resolved by an explicit per-item decision, and the working
tree is clean enough to check out the default branch — or the skill has stopped
with the blocker named, correctly attributed to a genuine conflict or a stale
local ref.

## Phase 4 — Transition · gate: BLOCK

Only after Phase 3 leaves the tree safe:

1. **Fast-forward the local default ref BEFORE checking it out:**
   `git fetch origin <default>:<default>`. Git refuses a non-fast-forward
   update of a ref that is not currently checked out, so the `--ff-only`
   guarantee is preserved by the instrument itself — this cannot silently
   rewrite the local default ref, only advance it or refuse. This is what
   keeps a stale local default from blocking (or worse, misattributing) the
   checkout below. This step can itself be refused for the same reason a
   checkout can be — `<default>` checked out in another worktree — in which
   case report that as the (correctly attributed) blocker, per Phase 3, and
   stop; do not treat the refusal as license to skip ahead.
2. Check out the default branch, then **verify the checkout actually happened**
   (`git branch --show-current`). A checkout silently fails when another worktree
   holds the branch, and every step after this one would otherwise run against
   the wrong branch.
3. Fast-forward with `--ff-only` (belt over the braces of step 1 — a no-op when
   the pre-checkout fetch already brought the local ref current). A divergence
   means the default branch moved in a way this skill will not reconcile:
   report it and stop. Never a merge commit, never a rebase, never a reset.

Gate: the local default ref was fast-forwarded before the checkout — or the
fast-forward's refusal was itself reported as a fact and the skill stopped —
HEAD is confirmed on the default branch by re-read, and the belt-and-braces
`--ff-only` pull either succeeded (typically a no-op) or was reported as a
refused divergence.

## Phase 5 — Delete the merged local branch · gate: STOP

Offer deletion of the now-merged local branch, with the Phase 1 containment
proof restated. One confirmation, naming the branch.

- `git branch -d` first, always. Never reach for `-D` on the assumption that a
  refusal means `-d` can't handle a squash merge — it often can. `git branch
  -d`'s safety check accepts a branch merged into its **upstream**, not only
  into HEAD: with an upstream still configured and equal to the tip, `-d`
  succeeds (with a warning) even for a squash merge that `--is-ancestor` alone
  would call unmerged. Do not conclude a refusal here means `-D` is required —
  check the reason first.
- **The sanctioned `-D` path.** `-d` typically refuses once the remote branch
  has been auto-deleted and pruned, because there is then no upstream left for
  `-d` to test reachability against. When that happens, `git branch -D` is
  permitted, but ONLY when both hold:
  1. Phase 1's proof, established this run, was the PR-record squash proof
     (`MERGED` and `headRefOid == HEAD`) — not a bare ancestry pass, not a
     stale or assumed proof.
  2. The confirmation restates that Phase-1 proof and explicitly names the
     branch.
  Frame this precisely: `-d`'s safety check tests SHA-reachability, and the
  squash proof has already shown that instrument is the wrong one for this
  repo's merge mode. The PR-record proof plus a named confirmation **replaces**
  the check that `-d` can no longer run — it does not bypass it. Everywhere
  else, `-D` stays forbidden exactly as before: if `-d` refuses and Phase 1's
  proof was anything other than the PR-record squash proof, report both and
  stop.
- The **remote** branch is never touched. If the user wants it gone, that is
  theirs to do or the platform's auto-delete-on-merge to do.

Declining leaves the branch in place. That is a normal outcome, not a failure.

Gate: the branch is deleted only after an explicit confirmation naming it, via
`-d`, or via `-D` restricted to the sanctioned path above with the proof
restated, with the remote untouched.

## Phase 6 — Receipt

One short summary: what landed, what was removed, what was kept, and where HEAD
is now. State declines as declines — a cleanup the user stopped halfway is a
correct outcome reported plainly, not an error.

## Hard rules

- MUST fetch and prove `HEAD` is **contained** in the fetched default branch
  before any deletion — via ancestry, via the PR-record squash proof (`MERGED`
  and `headRefOid == HEAD`), or, without `gh`, via a byte-identical tree diff.
  MUST NOT infer merge state from a `: gone]` upstream alone.
- MUST classify every artifact, and MUST treat anything not provably redundant or
  superseded as unique.
- MUST NOT discard a unique or unclassifiable artifact without an explicit
  confirmation naming that item.
- MUST confirm every removal and the branch deletion individually — no batched or
  implied yes.
- MUST fast-forward the local default ref (`git fetch origin <default>:<default>`)
  before checking it out, or report the fast-forward's own refusal (e.g.
  `<default>` checked out in another worktree) as the blocker and stop. MUST
  re-read the current branch after checkout before acting on it.
- MUST use `--ff-only`, and MUST NOT merge, rebase, or reset to reach the default
  branch.
- MUST use `git branch -d`, and MAY use `-D` ONLY when the Phase-1 squash-merge
  proof held this run and `-d` refused, with that proof restated and the branch
  named in the confirmation. Everywhere else `-D` is forbidden. MUST NOT delete a
  remote branch, force-push, or write to the default branch.
- MUST NOT drop a stash — report and route, as `/ca-standup` does.
- MUST NOT route to `/ca-override` when blocked. Name the gate instead.
