#!/usr/bin/env python3
"""codeArbiter: repository-qualified integration-proof evaluator (T-04).

Decides whether a candidate branch tip's content has genuinely landed on an
authorized integration target -- the one fact routine branch/worktree cleanup
may act on. Deliberately narrow: this module answers ONE question (is this
candidate proven-delivered?) and takes already-resolved git/PR facts as input
rather than querying Git or GitHub itself, so it stays a pure, unit-testable
decision function. Discovery (which branches exist, what their upstream state
is, resolving a PR record by number) is the caller's job and never substitutes
for the proof performed here:

- AC-07: ancestry is checked against the caller-supplied authorized
  integration target only -- never inferred from upstream state (gone,
  absent, still-existing), and it needs no PR/gh input to succeed.
- AC-08: a non-ancestry (typically squash) landing is proven only from an
  already-resolved, repository-qualified PR record naming an exact head SHA,
  base repository and a landing commit shown to be retained in the fetched
  target. Tree-equality is accepted only as corroboration alongside a real
  proof; it can never establish eligibility by itself.
- AC-10: the result records whether the original branch commits' identity
  survives (true only for an ancestry landing) so a squash/PR-delivery proof
  is never represented as preserving them.

Public API:
- evaluate_merge_proof(...) -> ProofResult  (T-04, the integration proof)
- The T-05 slice below: a repository-bound operation journal
  (load_journal / append_pending_operation / update_operation_outcome /
  reconcile_pending_operations) and a guarded, revalidating branch-deletion
  executor (guard_branch_deletion / execute_branch_deletion). Scope: branch
  deletion only -- worktree-removal guarding is a distinct, not-yet-built
  increment sharing this same journal/executor pattern.
"""

import json
import os
import uuid
from collections import namedtuple
from datetime import datetime, timezone

from _hooklib import acquire_lock, release_lock, write_text_atomic

ProofResult = namedtuple(
    "ProofResult",
    [
        "proven",
        "method",  # "ancestry" | "pr_delivery" | None
        "target_ref",
        "target_sha",
        "candidate_sha",
        "pr_number",
        "pr_merge_commit",
        "preserves_original_identity",
        "corroboration",  # tree-equality note, or None; never load-bearing
        "reason",  # always populated when proven is False
    ],
)

_PR_REQUIRED_FIELDS = ("number", "state", "head_sha", "base_repo", "merge_commit_sha")


def _require_sha(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty sha string" % label)


def _evaluate_pr_delivery(pr_record, candidate_sha, integration_repo, is_ancestor, target_sha):
    """Return (ProofResult-or-None, reason). reason is set whenever proof is None."""
    if pr_record is None:
        return None, "no PR delivery record supplied"
    if not isinstance(pr_record, dict):
        return None, "PR delivery record must be a resolved record, not a name search result"

    missing = [field for field in _PR_REQUIRED_FIELDS if not pr_record.get(field)]
    if missing:
        return None, "PR record missing required field(s): %s" % ", ".join(missing)

    number = pr_record["number"]

    if pr_record["state"] != "MERGED":
        return None, "PR #%s is not MERGED (state=%s)" % (number, pr_record["state"])

    if pr_record["head_sha"] != candidate_sha:
        return None, (
            "PR #%s head %s does not match candidate tip %s (stale or wrong PR)"
            % (number, pr_record["head_sha"], candidate_sha)
        )

    if pr_record["base_repo"] != integration_repo:
        return None, (
            "PR #%s base repository %s is not the authorized integration repository %s"
            % (number, pr_record["base_repo"], integration_repo)
        )

    landing = pr_record["merge_commit_sha"]
    if not is_ancestor(landing, target_sha):
        return None, (
            "PR #%s landing commit %s is not retained in the fetched integration target"
            % (number, landing)
        )

    return landing, number


def _evaluate_tree_corroboration(candidate_sha, target_sha, tree_equal_fn):
    if tree_equal_fn is None:
        return None
    if tree_equal_fn(candidate_sha, target_sha):
        return "tree contents are byte-identical to the fetched integration target"
    return None


def evaluate_merge_proof(
    candidate_sha,
    target_ref,
    target_sha,
    integration_repo,
    is_ancestor,
    pr_record=None,
    tree_equal_fn=None,
):
    """Evaluate whether candidate_sha's content is proven delivered to target_ref/target_sha.

    Args:
        candidate_sha: full SHA of the branch tip under consideration.
        target_ref: display name of the authorized, fetched integration target
            (e.g. "origin/main"), carried through into the result only.
        target_sha: full SHA the authorized integration target was fetched at.
        integration_repo: the "owner/repo" the target belongs to, used to
            reject a PR whose base repository does not match (fork-name
            collision / ambiguous fork identity).
        is_ancestor: callable(a, b) -> bool, true when commit a is an
            ancestor of commit b. No git process is spawned here.
        pr_record: an already-resolved (by exact PR number/ID, never by a
            branch-name search) dict describing one specific PR, or None.
            Required keys when supplied: number, state, head_sha, base_repo,
            merge_commit_sha.
        tree_equal_fn: optional callable(a, b) -> bool for exact-tree
            comparison. Recorded as corroboration only; never sufficient
            alone (AC-08).

    Returns:
        ProofResult. `.proven` is True only when ancestry or a qualified PR
        delivery proof held; otherwise False with a specific, non-generic
        `.reason` -- never a bare boolean.
    """
    _require_sha(candidate_sha, "candidate_sha")
    _require_sha(target_sha, "target_sha")

    corroboration = _evaluate_tree_corroboration(candidate_sha, target_sha, tree_equal_fn)

    if is_ancestor(candidate_sha, target_sha):
        return ProofResult(
            proven=True,
            method="ancestry",
            target_ref=target_ref,
            target_sha=target_sha,
            candidate_sha=candidate_sha,
            pr_number=None,
            pr_merge_commit=None,
            preserves_original_identity=True,
            corroboration=corroboration,
            reason=None,
        )

    landing_or_none, pr_detail = _evaluate_pr_delivery(
        pr_record, candidate_sha, integration_repo, is_ancestor, target_sha,
    )
    if landing_or_none is not None:
        return ProofResult(
            proven=True,
            method="pr_delivery",
            target_ref=target_ref,
            target_sha=target_sha,
            candidate_sha=candidate_sha,
            pr_number=pr_detail,
            pr_merge_commit=landing_or_none,
            preserves_original_identity=False,
            corroboration=corroboration,
            reason=None,
        )

    reason = "not an ancestor of %s, and %s" % (target_ref, pr_detail)
    if corroboration:
        reason += "; %s, but that is corroboration only, not proof" % corroboration

    return ProofResult(
        proven=False,
        method=None,
        target_ref=target_ref,
        target_sha=target_sha,
        candidate_sha=candidate_sha,
        pr_number=None,
        pr_merge_commit=None,
        preserves_original_identity=False,
        corroboration=corroboration,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# T-05: operation journal + guarded, revalidating branch-deletion executor.
#
# Scope: branch deletion only. Worktree-removal guarding is a distinct,
# not-yet-built increment sharing this same journal/executor pattern -- it is
# not implemented here and nothing below claims otherwise.
# ---------------------------------------------------------------------------

_JOURNAL_SCHEMA = "cleanup-journal/v1"
_JOURNAL_RELPATH = os.path.join(".codearbiter", ".resources.json")
_COMPLETED_STATUSES = frozenset({"applied", "skipped", "failed"})
_MAX_COMPLETED_RECORDS = 20


class JournalCorruptError(Exception):
    """Raised when the operation journal exists but cannot be trusted --
    unreadable, unparseable, or the wrong shape. Never silently treated as an
    empty journal: a corrupt journal is a stop condition (spec: "Stop the
    whole operation on ... corrupt/unwritable operation journal"), not a
    reason to proceed as if no prior operation was ever recorded."""


def _journal_path(root):
    return os.path.join(root, _JOURNAL_RELPATH)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_journal(root):
    """The operation journal at `root`, or a fresh empty envelope when no
    journal file exists yet. Raises JournalCorruptError -- never returns a
    silently-reset empty envelope -- when the file exists but is unreadable,
    unparseable, or not shaped like a journal."""
    path = _journal_path(root)
    if not os.path.exists(path):
        return {"schema": _JOURNAL_SCHEMA, "operations": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise JournalCorruptError(
            "cleanup operation journal at %s is unreadable: %s" % (path, exc)
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("operations"), list):
        raise JournalCorruptError(
            "cleanup operation journal at %s has an unrecognized shape" % path
        )
    return data


def _compact(journal):
    """Bound completed (applied/skipped/failed) records to the most recent
    _MAX_COMPLETED_RECORDS; every unresolved record (pending, or unknown from
    a reconciliation that could not be resolved) is retained regardless of
    count -- compaction never drops something still needing attention.

    Preserves the list's existing relative order and drops only the OLDEST
    excess completed entries (by their position in the current list) rather
    than partitioning into "unresolved first, then completed": a partition-
    and-concatenate approach reorders every record each time a record
    transitions from pending to completed, which destroys the very
    chronological ordering "most recent" depends on -- a record's position
    would then reflect when it was LAST re-sorted, not when it was created."""
    operations = journal.get("operations", [])
    completed_indices = [i for i, op in enumerate(operations) if op.get("status") in _COMPLETED_STATUSES]
    if len(completed_indices) > _MAX_COMPLETED_RECORDS:
        drop = set(completed_indices[: len(completed_indices) - _MAX_COMPLETED_RECORDS])
        operations = [op for i, op in enumerate(operations) if i not in drop]
    journal["operations"] = operations
    return journal


def _with_locked_journal(root, mutate_fn):
    """Acquire the cross-process journal lock, load-mutate-compact-save,
    release. `mutate_fn(journal) -> journal`.

    A failed lock acquisition is a HARD error here, not the fail-soft None
    `_hooklib.acquire_lock` itself returns for disposable callers (a
    statusline render) -- this journal is load-bearing operational state for
    a mutation about to happen, the same treatment `taskwrite.py` gives its
    board lock."""
    path = _journal_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = acquire_lock(path)
    if handle is None:
        raise RuntimeError(
            "could not acquire the cleanup operation journal lock at %s" % path
        )
    try:
        journal = load_journal(root)
        journal = mutate_fn(journal)
        journal = _compact(journal)
        write_text_atomic(path, json.dumps(journal, indent=2, sort_keys=True) + "\n", newline="\n")
        return journal
    finally:
        release_lock(handle)


def _append_operation_record(root, record):
    def _mutate(journal):
        journal["operations"].append(record)
        return journal

    _with_locked_journal(root, _mutate)
    return record["operation_id"]


def append_pending_operation(root, kind, target):
    """Write-ahead intent (AC-19): record a pending operation BEFORE any
    mutation is attempted. Returns the new operation_id."""
    record = {
        "operation_id": uuid.uuid4().hex,
        "kind": kind,
        "target": target,
        "status": "pending",
        "created_at": _now_iso(),
    }
    return _append_operation_record(root, record)


def update_operation_outcome(root, operation_id, status, result):
    """Record the final outcome of a journaled operation. Raises KeyError if
    `operation_id` is not present -- an outcome for an operation that was
    never journaled indicates a caller bug, not a state to paper over."""
    found = {"ok": False}

    def _mutate(journal):
        for op in journal["operations"]:
            if op["operation_id"] == operation_id:
                op["status"] = status
                op["result"] = result
                op["completed_at"] = _now_iso()
                found["ok"] = True
                break
        return journal

    _with_locked_journal(root, _mutate)
    if not found["ok"]:
        raise KeyError("no operation %r in the cleanup journal" % operation_id)


def reconcile_pending_operations(root, current_oid_fn):
    """Crash-time reconciliation (AC-19): resolve every still-pending
    branch_delete record from ACTUAL current state, never by blind retry.

    - branch no longer exists -> the deletion evidently completed: "applied".
    - branch exists with the SAME expected tip -> still genuinely pending;
      left untouched for a fresh attempt.
    - branch exists with a DIFFERENT tip -> ambiguous (a fresh commit, or a
      partial/racing mutation); marked "unknown" for explicit review, never
      auto-resolved to "applied" and never silently retried.

    Already-resolved (applied/skipped/failed) records are never touched."""

    def _mutate(journal):
        for op in journal["operations"]:
            if op.get("status") != "pending" or op.get("kind") != "branch_delete":
                continue
            target = op.get("target") or {}
            branch = target.get("branch")
            expected_oid = target.get("expected_oid")
            actual = current_oid_fn(branch)
            if actual is None:
                op["status"] = "applied"
                op["result"] = {"detail": "reconciled: branch no longer exists"}
                op["completed_at"] = _now_iso()
            elif actual != expected_oid:
                op["status"] = "unknown"
                op["result"] = {
                    "detail": (
                        "reconciled: tip is %s, neither deleted nor the expected %s"
                        % (actual, expected_oid)
                    ),
                }
                op["completed_at"] = _now_iso()
            # else: still genuinely pending -- left untouched, not retried here.
        return journal

    _with_locked_journal(root, _mutate)


class GuardRefusal(Exception):
    """Raised by guard_branch_deletion when a branch must not be deleted.
    `.reason` is a specific, human-readable explanation -- callers never see
    a bare boolean refusal."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def guard_branch_deletion(branch, expected_oid, current_branch, default_branch,
                           protected_branches, worktree_branches, current_oid_fn):
    """Pure guard (AC-09, AC-06): raises GuardRefusal if `branch` must not be
    deleted right now. Performs no mutation itself -- see
    execute_branch_deletion for the full journaled apply path.

    Refuses, in order: the current branch, the default branch, an explicitly
    protected branch, a branch occupied by any worktree, a branch that no
    longer exists, and -- the AC-06 case -- a branch whose ACTUAL current tip
    (read here, immediately before mutation, via `current_oid_fn`) no longer
    equals `expected_oid` bound at inspection time. A candidate that passed
    inspection and then moved is never swept in on a stale proof."""
    if branch == current_branch:
        raise GuardRefusal("%r is the current branch" % branch)
    if branch == default_branch:
        raise GuardRefusal("%r is the protected default branch" % branch)
    if branch in (protected_branches or ()):
        raise GuardRefusal("%r is an explicitly protected branch" % branch)
    if branch in (worktree_branches or ()):
        raise GuardRefusal("%r is checked out in a worktree" % branch)
    actual_oid = current_oid_fn(branch)
    if actual_oid is None:
        raise GuardRefusal("%r no longer exists (already deleted or renamed)" % branch)
    if actual_oid != expected_oid:
        raise GuardRefusal(
            "%r tip moved from expected %s to %s since inspection -- stale target"
            % (branch, expected_oid, actual_oid)
        )


OperationResult = namedtuple("OperationResult", ["operation_id", "status", "detail"])


def execute_branch_deletion(root, branch, expected_oid, current_branch, default_branch,
                             protected_branches, worktree_branches, current_oid_fn,
                             delete_fn, allow_force, operation_id=None):
    """Journal-then-mutate, per-item outcome (AC-14, AC-19). This is the ONE
    guarded path branch deletion may go through; it verifies evidence itself
    (via guard_branch_deletion) rather than trusting a caller-supplied
    safe/owned flag.

    `delete_fn(branch, force) -> (ok: bool, detail: str)` performs the actual
    `git branch -d` (force=False) or `-D` (force=True). `allow_force` gates
    whether `-D` may ever be attempted at all -- the caller passes True only
    under the sanctioned squash-proof-restated path; this function does not
    itself decide when `-D` is legitimate, and never substitutes a blanket
    allowlist for that judgment.

    If the plain `-d` attempt fails and `allow_force` permits a retry, the
    branch's actual tip is revalidated AGAIN immediately before the `-D`
    attempt -- a `-d` refusal is not itself proof the tip is still what was
    expected, and a ref move injected exactly at this seam must still refuse
    (AC-06), never fall through to a forced delete of a now-different branch.
    """
    operation_id = operation_id or uuid.uuid4().hex
    _append_operation_record(root, {
        "operation_id": operation_id,
        "kind": "branch_delete",
        "target": {"branch": branch, "expected_oid": expected_oid},
        "status": "pending",
        "created_at": _now_iso(),
    })

    def _finish(status, detail):
        update_operation_outcome(root, operation_id, status, {"detail": detail})
        return OperationResult(operation_id, status, detail)

    try:
        guard_branch_deletion(
            branch, expected_oid, current_branch, default_branch,
            protected_branches, worktree_branches, current_oid_fn,
        )
    except GuardRefusal as exc:
        return _finish("skipped", exc.reason)

    ok, detail = delete_fn(branch, False)
    if not ok and allow_force:
        actual_oid = current_oid_fn(branch)
        if actual_oid != expected_oid:
            return _finish(
                "skipped",
                "tip changed to %s before the -D retry -- refusing" % actual_oid,
            )
        ok, detail = delete_fn(branch, True)

    return _finish("applied" if ok else "failed", detail)
