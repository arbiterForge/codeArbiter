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
  `execute_branch_deletion` REQUIRES a `ProofResult`: an unproven target is
  refused outright, and the force/atomic-delete path is unlocked only by
  `proof.method == "pr_delivery"` -- never a caller-supplied flag.
- The T-02 slice below: the shared decision and interaction vocabulary
  (Scope, Target, Decision, make_decision, scope_covers,
  required_confirmation_count) that T-06's live routing will consume.
  ProofResult above already serves as the "proof outcome" type this layer
  wraps; T-02 adds no second proof representation.
- The T-03 slice below: an authoritative, bounded branch/worktree inventory
  (parse_branch_ref_inventory / parse_worktree_inventory /
  parse_worktree_inventory_nul / bind_branch_occupancy /
  classify_worktree_loss_surface / validate_resource_path). Pure parsers and
  classifiers only, same discipline as the rest of this module -- discovery
  facts in, structured records out, no eligibility or authorization claim
  made anywhere in this slice (AC-07: a gone upstream is a raw fact here,
  never proof of merged eligibility). `validate_resource_path` takes the
  caller's own exact allowlist of authorized targets, not a "nested under
  a root" rule -- worktrees are conventionally siblings of the repo root,
  not descendants of it.

Independent-review status (2026-09-17): an adversarial review of T-04/T-05
as merged (T-03, the authoritative inventory, did not exist yet at review
time -- it was skipped over in the original delivery order and is built
separately, below) found 27 concrete gaps (6 blocking) against ADR-0036's
gate for superseding safety-core.md #6, and returned NO-GO. The blocking
findings are fixed here: force eligibility now derives from proof.method
rather than a caller flag; the executor requires and journals a ProofResult
instead of trusting a bare oid; the ancestry proof path is repository-
qualified (it previously was not -- only the PR-delivery path was);
worktree occupancy is revalidated fresh at every mutation attempt via a
callable, not a static snapshot; and a claimed-successful delete is
reverified before being recorded "applied". Still true, unchanged by this
pass, and NOT claimed otherwise: nothing in this repository calls this
module in production -- `delete_fn` is entirely caller-injected with no
real git-calling implementation anywhere, the three vendored plugin copies
are unused, and worktree-removal guarding and filesystem-operation safety
do not exist. Wiring any of this into a live route is T-06's job, not this
module's, and this module being correct is a precondition for that work,
not a substitute for the review T-06 will still need before it lands.

T-03's own independent review (2026-09-17, against this module as first
merged) returned NO-GO: 3 blocking, 5 high. Both blocking defects it shares
a class with the T-04/T-05 review above -- a read failure folded into
"confirmed absent" -- are fixed here (B-3: unknown worktree-list readability
no longer defaults branch occupancy to unoccupied; H-1: a for-each-ref line
without exactly the documented 4 tab-separated fields is now a fully
unreadable record, never a partially-trusted one). `is_main` no longer
string-compares against a caller-supplied repo root -- a linked worktree's
`show-toplevel` almost never equals it, silently flagging every worktree
`is_main=False` including no ambiguity signal (B-2) -- it now trusts Git's
own documented ordering guarantee (the main worktree is always first in
`git worktree list`) instead of guessing from a path string. `validate_
resource_path` no longer treats "nested under the repo root" as the safe
shape: git worktrees are conventionally SIBLINGS of the repo root, not
descendants, so that rule refused every real worktree this module exists to
let a caller remove (H-2). It is now an exact-match allowlist guard --
`(True, resolved_path)` only when the resolved path equals one of the
caller's own authorized targets exactly -- which also fixes H-3 (the
resolved path is now returned so a caller can act on what was actually
validated, not the original unresolved string) and H-4 (no more prefix/
separator heuristics to get wrong on a volume or UNC root).
`classify_worktree_loss_surface` now accepts a `record_read_error` flag and
folds any UNREADABLE input into retain=True (H-5, M-3) rather than silently
being unreachable from the inventory's own error channel. Still true and
not claimed otherwise: this module still has no live caller -- wiring it
into a route is T-06's job -- and this remediation pass has not itself been
re-reviewed yet.
"""

import json
import ntpath
import os
import re
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
        "target_repo",  # the AUTHORIZED integration_repo this proof was
        # evaluated against (never the caller's unverified target_repo
        # assertion) -- CodeRabbit review, 2026-09-17: lets a downstream
        # consumer (execute_branch_deletion) bind a proof to the exact
        # repository_id it is operating on, rather than re-trusting that
        # the caller derived the same repository correctly a second time.
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


_PrDeliveryOutcome = namedtuple("_PrDeliveryOutcome", ["landing_sha", "pr_number", "reason"])
# M-3: replaces an earlier (landing_or_none, detail) return where the SAME
# slot meant "the landing sha" on success and "the failure reason" on
# failure -- correct only because merge_commit_sha is proven truthy before
# that slot is ever populated with a real value; a named, three-field
# outcome makes success/failure unambiguous regardless of what future
# fields carry.


def _evaluate_pr_delivery(pr_record, candidate_sha, integration_repo, is_ancestor, target_sha):
    """Return a _PrDeliveryOutcome. `.reason` is set whenever `.landing_sha`
    is None (failure); exactly one of the two is ever populated."""
    if pr_record is None:
        return _PrDeliveryOutcome(None, None, "no PR delivery record supplied")
    if not isinstance(pr_record, dict):
        return _PrDeliveryOutcome(
            None, None, "PR delivery record must be a resolved record, not a name search result",
        )

    missing = [field for field in _PR_REQUIRED_FIELDS if not pr_record.get(field)]
    if missing:
        return _PrDeliveryOutcome(
            None, None, "PR record missing required field(s): %s" % ", ".join(missing),
        )

    number = pr_record["number"]

    if pr_record["state"] != "MERGED":
        return _PrDeliveryOutcome(
            None, None, "PR #%s is not MERGED (state=%s)" % (number, pr_record["state"]),
        )

    if pr_record["head_sha"] != candidate_sha:
        return _PrDeliveryOutcome(None, None, (
            "PR #%s head %s does not match candidate tip %s (stale or wrong PR)"
            % (number, pr_record["head_sha"], candidate_sha)
        ))

    if pr_record["base_repo"] != integration_repo:
        return _PrDeliveryOutcome(None, None, (
            "PR #%s base repository %s is not the authorized integration repository %s"
            % (number, pr_record["base_repo"], integration_repo)
        ))

    landing = pr_record["merge_commit_sha"]
    if not is_ancestor(landing, target_sha):
        return _PrDeliveryOutcome(None, None, (
            "PR #%s landing commit %s is not retained in the fetched integration target"
            % (number, landing)
        ))

    return _PrDeliveryOutcome(landing, number, None)


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
    target_repo,
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
        target_repo: the "owner/repo" the caller asserts target_ref/target_sha
            were actually fetched from. Checked against `integration_repo`
            unconditionally, before EITHER proof path runs (independent
            review, 2026-09-17): without this, is_ancestor(candidate_sha,
            target_sha) returning True "proved" ancestry no matter which
            repository target_sha actually came from -- a caller bug, a
              stale remote, or a fork could all forge a passing ancestry
            check. Ancestry is not exempt from repository qualification
            just because it needs no PR record.
        integration_repo: the "owner/repo" the target must actually belong
            to. Also used to reject a PR whose base repository does not
            match (fork-name collision / ambiguous fork identity).
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
    if not isinstance(target_repo, str) or not target_repo.strip():
        raise ValueError("target_repo must be a non-empty repository identity string")

    corroboration = _evaluate_tree_corroboration(candidate_sha, target_sha, tree_equal_fn)

    if target_repo != integration_repo:
        return ProofResult(
            proven=False,
            method=None,
            target_ref=target_ref,
            target_sha=target_sha,
            target_repo=integration_repo,
            candidate_sha=candidate_sha,
            pr_number=None,
            pr_merge_commit=None,
            preserves_original_identity=False,
            corroboration=corroboration,
            reason=(
                "fetched target repository %s is not the authorized integration repository %s"
                % (target_repo, integration_repo)
            ),
        )

    if is_ancestor(candidate_sha, target_sha):
        return ProofResult(
            proven=True,
            method="ancestry",
            target_ref=target_ref,
            target_sha=target_sha,
            target_repo=integration_repo,
            candidate_sha=candidate_sha,
            pr_number=None,
            pr_merge_commit=None,
            preserves_original_identity=True,
            corroboration=corroboration,
            reason=None,
        )

    pr_outcome = _evaluate_pr_delivery(
        pr_record, candidate_sha, integration_repo, is_ancestor, target_sha,
    )
    if pr_outcome.landing_sha is not None:
        return ProofResult(
            proven=True,
            method="pr_delivery",
            target_ref=target_ref,
            target_sha=target_sha,
            target_repo=integration_repo,
            candidate_sha=candidate_sha,
            pr_number=pr_outcome.pr_number,
            pr_merge_commit=pr_outcome.landing_sha,
            preserves_original_identity=False,
            corroboration=corroboration,
            reason=None,
        )

    reason = "not an ancestor of %s, and %s" % (target_ref, pr_outcome.reason)
    if corroboration:
        reason += "; %s, but that is corroboration only, not proof" % corroboration

    return ProofResult(
        proven=False,
        method=None,
        target_ref=target_ref,
        target_sha=target_sha,
        target_repo=integration_repo,
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
_JOURNAL_RELPATH = os.path.join(".codearbiter", ".cleanup-journal.json")
_COMPLETED_STATUSES = frozenset({"applied", "skipped", "failed"})
# H-2: the proposal's own named example is a 40-branch bulk delete. The bound
# must comfortably exceed that so the audit trail for the exact authorized
# batch is never truncated mid-operation.
_MAX_COMPLETED_RECORDS = 50

_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _require_full_oid(value, label):
    """M-4: an abbreviated or malformed OID is rejected up front with a
    specific error, rather than silently causing every downstream
    comparison to "skip" as stale with no diagnosis."""
    if not isinstance(value, str) or not _FULL_SHA_RE.match(value):
        raise ValueError("%s must be a full 40-character hex SHA, got %r" % (label, value))


def _require_branch_collection(value, label):
    """M-2: a bare string is iterable and would silently match by
    SUBSTRING (`"ai" in "main"` is True) rather than by membership in a
    branch-name collection. Reject it outright instead of guessing intent."""
    if isinstance(value, str):
        raise TypeError(
            "%s must be a collection of branch names, not a bare string %r" % (label, value)
        )


def _require_repository_id(value, label):
    """CodeRabbit review (2026-09-17): a missing or empty repository_id can
    never be cross-checked against anything, which is exactly the "unbound
    journal record" gap the review named. Reject it up front rather than
    silently accepting an identity that binds to nothing."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty repository identity string" % label)


_OID_UNREADABLE = object()

UNREADABLE = _OID_UNREADABLE
# Public alias: the T-03 inventory below (branch/worktree records, worktree
# loss-surface classification) reuses this exact sentinel for "this could
# not be determined," rather than minting a second "unreadable" concept.
# One canonical marker for "read failed" across the whole module means a
# caller can never accidentally treat T-03's UNREADABLE and T-05's internal
# _OID_UNREADABLE as somehow different states -- they are the same object.


def _read_oid(current_oid_fn, branch):
    """Distinguish confirmed-absent (None, a positive answer from a
    successful read) from unreadable (the read itself failed) -- H-1's
    fix. Never fold the two together: `current_oid_fn` raising means "I
    could not tell," which is a materially different fact from "I checked
    and it is gone." Callers must never treat _OID_UNREADABLE as None."""
    try:
        return current_oid_fn(branch)
    except Exception as exc:  # noqa: BLE001 -- any read failure is "unreadable"
        return _OID_UNREADABLE


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
    if (
        not isinstance(data, dict)
        or data.get("schema") != _JOURNAL_SCHEMA
        or not isinstance(data.get("operations"), list)
    ):
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


def _check_repository_identity(journal, repository_id):
    """H-3 (partial): AC-05's "invalid repository identity blocks the whole
    operation" applies to the journal itself, not just Scope (T-02). If the
    journal already holds records for a DIFFERENT repository_id than the one
    supplied now, something is wrong -- the wrong root was passed, or one
    journal path is serving two different repositories -- and we refuse
    rather than silently mixing records from two repositories together.

    `repository_id` is required non-empty by every caller (enforced in
    `_append_operation_record` via `_require_repository_id`) before this
    runs, so every record this ever compares against is itself non-empty --
    there is no "either side is None" leniency left to exploit (CodeRabbit
    review, 2026-09-17: the old skip-on-None behavior permitted unbound
    records to coexist silently with bound ones).

    This does not solve cross-worktree mutual exclusion for one shared
    repository (a deeper structural question -- the journal path is still
    resolved relative to the caller's `root`, so two worktrees of the SAME
    repository currently get separate journals and separate locks). That
    remains an explicitly open gap, not silently claimed as fixed here."""
    for op in journal.get("operations", []):
        existing = op.get("repository_id")
        if existing != repository_id:
            raise ValueError(
                "cleanup journal at this path already holds records for repository %r, "
                "not %r -- refusing to mix operations across repositories"
                % (existing, repository_id)
            )


def _append_operation_record(root, record):
    _require_repository_id(record.get("repository_id"), "repository_id")

    def _mutate(journal):
        _check_repository_identity(journal, record.get("repository_id"))
        journal["operations"].append(record)
        return journal

    _with_locked_journal(root, _mutate)
    return record["operation_id"]


def append_pending_operation(root, kind, target, repository_id):
    """Write-ahead intent (AC-19): record a pending operation BEFORE any
    mutation is attempted. Returns the new operation_id. `repository_id`
    identifies the repository this operation belongs to (AC-05); it must be
    a non-empty string (CodeRabbit review, 2026-09-17 -- an absent or empty
    identity can never be cross-checked against anything) and is validated
    for consistency against any existing records in this journal -- see
    _check_repository_identity."""
    record = {
        "operation_id": uuid.uuid4().hex,
        "kind": kind,
        "target": target,
        "repository_id": repository_id,
        "status": "pending",
        "created_at": _now_iso(),
    }
    return _append_operation_record(root, record)


def update_operation_outcome(root, operation_id, status, result):
    """Record the final outcome of a journaled operation. Raises KeyError if
    `operation_id` is not present -- an outcome for an operation that was
    never journaled indicates a caller bug, not a state to paper over.

    H-5: the membership check happens INSIDE the locked mutation, and
    raising there means _with_locked_journal never reaches its write --
    an outcome update for an unknown operation_id never rewrites the
    journal file at all, rather than writing an unchanged copy first and
    only then discovering the id was never found."""

    def _mutate(journal):
        for op in journal["operations"]:
            if op["operation_id"] == operation_id:
                op["status"] = status
                op["result"] = result
                op["completed_at"] = _now_iso()
                return journal
        raise KeyError("no operation %r in the cleanup journal" % operation_id)

    _with_locked_journal(root, _mutate)


def reconcile_pending_operations(root, current_oid_fn, repository_id):
    """Crash-time reconciliation (AC-19): resolve every still-pending
    branch_delete record from ACTUAL current state, never by blind retry.

    - branch no longer exists (a successful read confirms absence) -> the
      deletion evidently completed: "applied".
    - the read itself fails (H-1) -> "unknown", NEVER "applied". A read
      failure is not evidence of absence; folding the two together would
      let a transient git error masquerade as a confirmed deletion.
    - branch exists with the SAME expected tip -> still genuinely pending;
      left untouched for a fresh attempt.
    - branch exists with a DIFFERENT tip -> ambiguous (a fresh commit, or a
      partial/racing mutation); marked "unknown" for explicit review, never
      auto-resolved to "applied" and never silently retried.

    Only "branch_delete" records are touched (H-6) -- a pending record of
    any other kind (e.g. a future worktree_remove) is left completely
    alone; this function has no basis for judging a different kind's state.

    `repository_id` (CodeRabbit review, 2026-09-17) identifies the
    repository actually being reconciled RIGHT NOW; it must be a non-empty
    string. A pending record belonging to a DIFFERENT repository_id is left
    completely untouched -- reconciliation must never resolve another
    repository's operation from this repository's git state, even though
    both currently share one journal path per `root`.

    Already-resolved (applied/skipped/failed) records are never touched."""
    _require_repository_id(repository_id, "repository_id")

    def _mutate(journal):
        for op in journal["operations"]:
            if op.get("status") != "pending" or op.get("kind") != "branch_delete":
                continue
            if op.get("repository_id") != repository_id:
                continue
            target = op.get("target") or {}
            branch = target.get("branch")
            expected_oid = target.get("expected_oid")
            actual = _read_oid(current_oid_fn, branch)
            if actual is _OID_UNREADABLE:
                op["status"] = "unknown"
                op["result"] = {"detail": "reconciled: could not determine current state (read failed)"}
                op["completed_at"] = _now_iso()
            elif actual is None:
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
                           protected_branches, worktree_branches_fn, current_oid_fn):
    """Pure guard (AC-09, AC-06): raises GuardRefusal if `branch` must not be
    deleted right now. Performs no mutation itself -- see
    execute_branch_deletion for the full journaled apply path.

    `worktree_branches_fn` is a zero-argument callable invoked HERE, fresh,
    every time the guard runs (B-6) -- never a snapshot bound earlier. A
    worktree created after inspection but before this call must still be
    caught.

    Refuses, in order: the current branch, the default branch, an explicitly
    protected branch, a branch occupied by any worktree (occupancy read
    fresh via `worktree_branches_fn`), a branch that no longer exists, and
    -- the AC-06 case -- a branch whose ACTUAL current tip (read here,
    immediately before mutation, via `current_oid_fn`) no longer equals
    `expected_oid` bound at inspection time. A candidate that passed
    inspection and then moved is never swept in on a stale proof.

    A read failure (either callable raising) is fail-safe: refuse, never
    crash, and never treat "could not tell" as "safe to proceed" (H-1)."""
    _require_full_oid(expected_oid, "expected_oid")
    _require_branch_collection(protected_branches, "protected_branches")
    if branch == current_branch:
        raise GuardRefusal("%r is the current branch" % branch)
    if branch == default_branch:
        raise GuardRefusal("%r is the protected default branch" % branch)
    if branch in (protected_branches or ()):
        raise GuardRefusal("%r is an explicitly protected branch" % branch)
    try:
        worktree_branches = worktree_branches_fn()
    except Exception as exc:  # noqa: BLE001 -- any read failure is fail-safe refusal
        raise GuardRefusal(
            "could not determine worktree occupancy for %r: %s" % (branch, exc)
        ) from exc
    _require_branch_collection(worktree_branches, "worktree_branches_fn() result")
    if branch in (worktree_branches or ()):
        raise GuardRefusal("%r is checked out in a worktree" % branch)
    actual_oid = _read_oid(current_oid_fn, branch)
    if actual_oid is _OID_UNREADABLE:
        raise GuardRefusal("could not determine %r's current state" % branch)
    if actual_oid is None:
        raise GuardRefusal("%r no longer exists (already deleted or renamed)" % branch)
    if actual_oid != expected_oid:
        raise GuardRefusal(
            "%r tip moved from expected %s to %s since inspection -- stale target"
            % (branch, expected_oid, actual_oid)
        )


OperationResult = namedtuple("OperationResult", ["operation_id", "status", "detail"])


def execute_branch_deletion(root, branch, proof, current_branch, default_branch,
                             protected_branches, worktree_branches_fn, current_oid_fn,
                             delete_fn, repository_id):
    """Journal-then-mutate, per-item outcome (AC-14, AC-19). This is the ONE
    guarded path branch deletion may go through; it verifies evidence itself
    (via `proof` and `guard_branch_deletion`) rather than trusting a
    caller-supplied safe/owned flag.

    `proof` is a `ProofResult` (from `evaluate_merge_proof`) for `branch`,
    whose `candidate_sha` is used as the branch's expected tip. "Proven-
    merged" is never caller honor (B-3): if `proof.proven` is not True, the
    operation is skipped outright, before the guard even runs.

    Force/atomic-delete (the `-D`-equivalent path) is permitted ONLY when
    `proof.method == "pr_delivery"` -- NEVER a caller-supplied boolean
    (B-1). An ancestry-proven branch has no legitimate reason to need a
    forced delete; if its plain attempt fails, that is itself suspicious
    and returns "failed" for investigation rather than escalating.

    `delete_fn(branch, force, expected_oid) -> (ok: bool, detail: str)`
    performs the actual deletion. `expected_oid` is passed through so a real
    implementation can make the git-level operation ITSELF atomic with
    respect to the tip -- e.g. `git update-ref -d refs/heads/<branch>
    <expected_oid>`, which the project's own Git-behavior probes (GIT-07)
    confirm refuses a stale value -- rather than a plain `git branch -d`/`-D`,
    which performs its own unrelated lookup and could still delete a branch
    whose tip moved between our guard's check and git's own call.

    If the plain attempt fails and a forced retry is permitted, BOTH the
    branch's actual tip AND its worktree occupancy are revalidated AGAIN,
    fresh, immediately before the retry (B-6) -- a plain-attempt refusal is
    not itself proof either fact is still what was expected, and a ref move
    or new worktree injected exactly at this seam must still refuse (AC-06),
    never fall through to a forced delete of a now-different branch.

    After ANY claimed-successful delete, the branch's state is reverified
    (H-4) -- `delete_fn` returning `ok=True` is never trusted absolutely.
    If the branch still resolves, that is a contradiction and is recorded
    "failed"; if the post-delete state cannot even be read, that is
    honestly "unknown," never silently folded into "applied."
    """
    expected_oid = proof.candidate_sha
    _require_full_oid(expected_oid, "proof.candidate_sha")
    _require_repository_id(repository_id, "repository_id")
    operation_id = uuid.uuid4().hex
    _append_operation_record(root, {
        "operation_id": operation_id,
        "kind": "branch_delete",
        "target": {"branch": branch, "expected_oid": expected_oid},
        "proof": {
            "method": proof.method,
            "target_ref": proof.target_ref,
            "target_sha": proof.target_sha,
            "target_repo": proof.target_repo,
            "pr_number": proof.pr_number,
            "pr_merge_commit": proof.pr_merge_commit,
        },
        "repository_id": repository_id,
        "status": "pending",
        "created_at": _now_iso(),
    })

    def _finish(status, detail):
        update_operation_outcome(root, operation_id, status, {"detail": detail})
        return OperationResult(operation_id, status, detail)

    if not proof.proven:
        return _finish("skipped", "not proven delivered: %s" % proof.reason)

    if proof.target_repo != repository_id:
        # CodeRabbit review (2026-09-17): a proof validated for one
        # repository must never authorize a deletion journaled/executed
        # under a different repository_id -- ProofResult.target_repo and
        # the operation's repository_id are two independently-derived
        # facts and must agree before anything is deleted.
        return _finish(
            "skipped",
            "proof was validated for repository %r, not this operation's repository %r"
            % (proof.target_repo, repository_id),
        )

    allow_force = proof.method == "pr_delivery"

    try:
        guard_branch_deletion(
            branch, expected_oid, current_branch, default_branch,
            protected_branches, worktree_branches_fn, current_oid_fn,
        )
    except GuardRefusal as exc:
        return _finish("skipped", exc.reason)

    ok, detail = delete_fn(branch, False, expected_oid)
    if not ok and allow_force:
        actual_oid = _read_oid(current_oid_fn, branch)
        if actual_oid is _OID_UNREADABLE or actual_oid != expected_oid:
            return _finish(
                "skipped",
                "tip changed (or became unreadable) before the forced retry -- refusing",
            )
        try:
            worktree_branches = worktree_branches_fn()
        except Exception as exc:  # noqa: BLE001
            return _finish(
                "skipped",
                "could not confirm worktree occupancy before the forced retry -- refusing: %s" % exc,
            )
        _require_branch_collection(worktree_branches, "worktree_branches_fn() result")
        if branch in (worktree_branches or ()):
            return _finish(
                "skipped",
                "%r became worktree-occupied before the forced retry -- refusing" % branch,
            )
        ok, detail = delete_fn(branch, True, expected_oid)

    if ok:
        verify_oid = _read_oid(current_oid_fn, branch)
        if verify_oid is _OID_UNREADABLE:
            return _finish(
                "unknown",
                "delete_fn reported success but %r's post-delete state could not be reverified" % branch,
            )
        if verify_oid is not None:
            return _finish(
                "failed",
                "delete_fn reported success but %r still resolves to %s" % (branch, verify_oid),
            )

    return _finish("applied" if ok else "failed", detail)


# ---------------------------------------------------------------------------
# T-02: shared decision and interaction typed objects.
#
# Pure policy-decision vocabulary: how many confirmations an operation needs
# (authorization), whether a scope covers a given target (eligibility-of-
# scope, not eligibility-of-content -- that's ProofResult/guard_branch_
# deletion's job), and one typed outcome per target. Consumed by T-06's live
# routing and by shared/host orchestration tests alike; this module makes no
# orchestration decisions and calls no git/gh itself.
# ---------------------------------------------------------------------------

AUTHORIZATION_SOURCES = frozenset({
    # AC-01: an explicit instruction that already names a bounded operation.
    "direct_instruction",
    # The interaction model's snapshot-bind row: a reply that accepts (all
    # or a subset of) an already-displayed enumerated proposal.
    "snapshot_reply",
    # AC-04: an accepted work lifecycle's own disposable housekeeping.
    "accepted_lifecycle",
})

RESOURCE_KINDS = frozenset({"branch", "worktree", "file", "directory"})

DECISION_OUTCOMES = frozenset({
    "eligible",      # proven and unblocked; may proceed
    "excluded",      # protected, occupied, or outside the scope's kinds -- never a loss
    "unique_loss",   # eligible for removal, but discards unique work (AC-12)
    "unknown",       # cannot be determined; blocks only itself and dependants (AC-05)
    "error",         # invalid identity or corrupt state; blocks the whole operation (AC-05)
})

Scope = namedtuple("Scope", ["source", "resource_kinds", "members", "repository_id"])
# source: one of AUTHORIZATION_SOURCES, or None for a not-yet-authorized
#   proposal (nothing is covered until the user responds).
# resource_kinds: frozenset naming EVERY resource kind this scope covers
#   (AC-03: composite scopes name their resource kinds and members --
#   there is no implicit "and anything else that looks related").
# members: frozenset of exact target locators bound at authorization time,
#   or None when offered but not yet enumerated/accepted. A later-
#   discovered target is never silently added to an existing operation.
# repository_id: the exact repository identity this authorization applies
#   to (AC-05: an invalid repository identity blocks the whole operation).

Target = namedtuple("Target", ["kind", "locator", "expected_identity"])
# kind: a RESOURCE_KINDS member, or an out-of-band kind (e.g. "task_archive")
#   that a scope may legitimately never cover.
# locator: the exact name/path identifying this target.
# expected_identity: an oid/fingerprint bound at inspection time, or None
#   when identity is not yet resolved.

Decision = namedtuple("Decision", ["target", "outcome", "reason", "blocks_operation"])


def make_decision(target, outcome, reason):
    """One typed outcome for one target (AC-05, AC-12). `reason` is always a
    specific, human-readable string -- callers never see a bare outcome
    without why. `blocks_operation` is True only for "error": an unknown,
    excluded, or unique-loss decision blocks only its own target and
    dependants, never the whole operation."""
    if outcome not in DECISION_OUTCOMES:
        raise ValueError("unrecognized decision outcome %r" % outcome)
    return Decision(
        target=target, outcome=outcome, reason=reason,
        blocks_operation=(outcome == "error"),
    )


def scope_covers(scope, target, repository_id):
    """AC-03 (keep the scope closed): a target is covered only when its
    resource kind is one the scope explicitly names AND its locator is in
    the scope's exact bound member set. Kind is checked before membership,
    so a same-named resource of the wrong kind (a task-archive candidate
    sharing a branch's name) is never covered by a branch-only scope. A
    scope with no bound members yet (an unaccepted proposal) covers
    nothing, and neither does no scope at all. A Scope with an unknown
    authorization source covers nothing either, even if members happens
    to already be populated (e.g. a displayed-but-not-yet-accepted
    snapshot). The caller also supplies the active repository identity;
    authorization bound in one repository never transfers to another."""
    if (
        scope is None
        or scope.source not in AUTHORIZATION_SOURCES
        or scope.members is None
    ):
        return False
    if not repository_id or scope.repository_id != repository_id:
        return False
    if target.kind not in scope.resource_kinds:
        return False
    return target.locator in scope.members


def required_confirmation_count(scope, has_unresolved_unique_loss=False):
    """Pure prompt-budget classifier (AC-01, AC-02, AC-04, AC-12, AC-26):
    how many NEW confirmation questions this scope's operation needs, based
    only on its authorization source -- never per-target, never per-branch.

    - scope=None (a proposal not yet authorized, e.g. a generic standup
      sweep) needs exactly one batch offer (AC-02): "at most 1 per
      proposed scope," not zero and not one per candidate.
    - Each AUTHORIZATION_SOURCES member is already self-authorizing for
      the members it binds (AC-01's direct instruction, the snapshot-bind
      reply, AC-04's accepted lifecycle): zero further questions.
    - A declined proposal is represented the same way as one never made
      (scope stays None) -- there is no per-item prompt primitive here for
      a decline to fall into; re-offering the same declined proposal is an
      orchestration decision, not this function's job to inflate.
    - An unresolved unique loss (AC-12) always adds exactly one further
      question on top of any authorization source, because routine
      cleanup authorization never covers a unique loss by itself. The
      flag is boolean, not a count: multiple named losses still share one
      explicit decision, never one prompt each.
    """
    if scope is None or scope.source is None:
        base = 1
    elif scope.source in AUTHORIZATION_SOURCES:
        base = 0
    else:
        raise ValueError("unrecognized authorization source %r" % scope.source)
    return base + (1 if has_unresolved_unique_loss else 0)


# ---------------------------------------------------------------------------
# T-03: authoritative, bounded branch/worktree inventory.
#
# Pure parsers only (same discipline as T-02/T-04/T-05 above): every function
# here takes an already-captured Git command output string (or an
# already-resolved filesystem fact via an injectable callable) and returns a
# structured record -- no subprocess call, no os.environ read, no network
# call happens in this module. Discovery output is reported AS-IS; nothing
# here decides eligibility (AC-07: gone/absent/still-existing upstream state
# never implies merged -- that is evaluate_merge_proof's job) or authorizes a
# mutation (that is Scope/guard_branch_deletion's job). A read failure or a
# malformed line is always its own explicit state, never silently folded
# into "absent" or "clean" (AC-05, AC-09, AC-11): an inventory that hides a
# read failure behind a default value is worse than no inventory at all.
#
# Branch OIDs come from `git for-each-ref refs/heads --format='%(refname:
# short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)'` -- full
# hex SHAs (40 characters for SHA-1, 64 for a SHA-256 repository), never the
# abbreviated form `git branch -vv` prints by default. That format ALWAYS
# emits exactly 4 tab-separated fields (empty ones for an unset upstream);
# anything else means a truncated read, a format-string drift, or a
# different git version, so a line with any other field count is rejected
# as a whole, not partially trusted. Branch occupancy is bound by
# cross-referencing the REAL worktree list (`git worktree list
# --porcelain[|-z]`), never guessed from a display-only "+"/"*" prefix: a
# marker alone would say a branch is occupied without ever saying by which
# worktree, and the actual path is exactly what a caller needs to make a
# real decision. The MAIN worktree is identified by Git's own documented
# ordering guarantee -- it is always the first record `git worktree list`
# prints -- never by string-comparing a path against a caller-supplied repo
# root: a linked worktree's own `show-toplevel` is almost never equal to
# that root, and Windows path separators never equal Git's forward slashes,
# so a string-equality rule flags EVERY worktree "not main" with no
# ambiguity signal at all.
# ---------------------------------------------------------------------------

BranchRefRecord = namedtuple("BranchRefRecord", [
    "name", "oid", "upstream", "upstream_gone", "occupied_by", "read_error",
])
# oid: full-length hex SHA (40 or 64 characters), or UNREADABLE if the line
#   did not carry exactly 4 tab-separated fields or the OID field was
#   anything short of a full-length hex object name (an abbreviated SHA is
#   refused, not silently accepted, since T-03's whole point is a FULL,
#   authoritative ref ID).
# upstream: the upstream ref's short name, or None for a real, confirmed
#   "no upstream configured" -- or UNREADABLE if the line itself could not
#   be parsed at all (never conflated with a confirmed-absent upstream).
# upstream_gone: True/False only when Git's own %(upstream:track) explicitly
#   said so from a fully-parsed line; UNREADABLE if the line could not be
#   parsed. AC-07: this is a raw discovery FACT, never proof of merged
#   eligibility -- a gone-but-unmerged branch stays exactly that, unproven,
#   through this entire module.
# occupied_by: the worktree path currently holding this branch checked out,
#   UNREADABLE if occupancy could not be determined, or None if it is
#   affirmatively known to be unoccupied. Populated ONLY by
#   bind_branch_occupancy from a real list of WorktreeInventoryRecord --
#   never inferred here.
# read_error: True if the source line did not carry exactly the 4
#   tab-separated fields the --format string always emits, or carried an
#   unparseable OID. A malformed line still produces its own record (AC-05:
#   an unknown item blocks only itself) with whatever name text could be
#   salvaged, rather than vanishing from the inventory -- a silently
#   shrunken inventory is a worse failure than a visibly broken record.

_FULL_HEX_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def parse_branch_ref_inventory(for_each_ref_text):
    """Parse tab-delimited `git for-each-ref refs/heads` output (see module
    docstring for the exact --format) into a list of BranchRefRecord, one
    per non-blank line, in the order Git printed them. The format string
    always emits exactly 4 tab-separated fields; any other count is a fully
    unreadable record (H-1) -- not a partially-trusted one with a
    confirmed-absent upstream fabricated from a truncated read."""
    out = []
    for raw in (for_each_ref_text or "").splitlines():
        if not raw.strip():
            continue
        fields = raw.split("\t")
        name = fields[0] if fields and fields[0] else raw.strip()
        if len(fields) != 4:
            out.append(BranchRefRecord(
                name=name, oid=UNREADABLE, upstream=UNREADABLE,
                upstream_gone=UNREADABLE, occupied_by=None, read_error=True,
            ))
            continue
        _, oid_field, upstream_field, track_field = fields
        oid_field = oid_field.strip()
        oid = oid_field if _FULL_HEX_RE.match(oid_field) else UNREADABLE
        upstream = upstream_field.strip() or None
        upstream_gone = "gone" in track_field.strip()
        out.append(BranchRefRecord(
            name=name, oid=oid, upstream=upstream, upstream_gone=upstream_gone,
            occupied_by=None, read_error=(oid is UNREADABLE),
        ))
    return out


WorktreeInventoryRecord = namedtuple("WorktreeInventoryRecord", [
    "path", "oid", "branch", "is_main", "detached", "locked", "locked_reason",
    "bare", "prunable", "prunable_reason", "path_exists", "read_error",
])
# oid: full-length hex from the record's HEAD line, or UNREADABLE if that
#   line was missing or malformed -- a worktree whose HEAD cannot be read is
#   never silently treated as "no branch" or otherwise safe (AC-09, AC-11).
#   Always UNREADABLE for a `bare` record (a bare worktree has no single
#   checked-out commit and carries no HEAD line at all -- that absence is
#   expected, not a read error).
# is_main: True for exactly the first record a parse call produces -- Git's
#   `worktree list` always lists the main worktree first (B-2) -- never
#   derived by comparing `path` against a caller-supplied root.
# bare: True for a bare-repository worktree record (a `bare` porcelain
#   line, no HEAD/branch of its own). Never flagged as a read error merely
#   for lacking a HEAD line.
# prunable / prunable_reason: True and Git's stated reason when Git itself
#   marked this record `prunable <reason>` -- an inventory that silently
#   drops this fact would hide exactly the "this worktree's gitdir points
#   nowhere real" signal an authoritative inventory exists to surface.
# path_exists: computed via the injected path_exists_fn (production default
#   os.path.exists). AC-11: a missing path is surfaced as its own fact,
#   never auto-abandoned -- the caller decides what a missing path means.
# read_error: True only when the HEAD line itself was missing/malformed for
#   a non-bare record; a missing path is NOT a read error (the record
#   parsed fine; the path just isn't there right now).


def _strip_trailing_sep(path):
    """Strip ALL trailing separators (M-9: a single-strip left a
    double-separated path like "/repo//" not fully normalized, which could
    under- or over-match in a caller's own comparison), while never
    stripping a bare root down to nothing -- "/" stays "/"."""
    if not path:
        return path
    stripped = path.rstrip("/\\")
    return stripped or path[0]


def _c_unquote(s):
    """Undo Git's C-style quoting of a value that contains a raw newline or
    other special byte -- Git wraps such a value in double quotes with
    backslash/octal escapes when NOT using a NUL-delimited (`-z`) format
    (M-6). Only ever applied on the newline-delimited porcelain parser; the
    NUL-delimited parser already returns the raw bytes verbatim and must
    never go through this. A value not shaped like a quoted string is
    returned unchanged."""
    if s is None or len(s) < 2 or not (s.startswith('"') and s.endswith('"')):
        return s
    inner = s[1:-1]
    out = []
    i = 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            octal = inner[i + 1:i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(chr(int(octal, 8)))
                i += 4
                continue
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _new_worktree_record(path):
    return {
        "path": path, "head": None, "branch": None, "detached": False,
        "locked": False, "locked_reason": None, "head_seen": False,
        "bare": False, "prunable": False, "prunable_reason": None,
    }


def _apply_worktree_line(cur, line, unquote=False):
    """Mutate `cur` (the dict form of an in-progress record) with one
    porcelain line's worth of fact. Shared between the newline-delimited
    and NUL-delimited parsers so the two formats can never silently drift
    apart in what they recognize -- `unquote` is the one deliberate,
    format-level difference (M-6): the newline-delimited format C-quotes a
    lock reason containing special bytes onto one line; the NUL-delimited
    format never does."""
    if line.startswith("HEAD "):
        cur["head"] = line[len("HEAD "):].strip() or None
        cur["head_seen"] = True
    elif line == "detached":
        cur["detached"] = True
    elif line.startswith("branch "):
        ref = line[len("branch "):].strip()
        cur["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    elif line == "locked":
        cur["locked"] = True
    elif line.startswith("locked "):
        cur["locked"] = True
        reason = line[len("locked "):].strip() or None
        cur["locked_reason"] = _c_unquote(reason) if (unquote and reason) else reason
    elif line == "bare":
        cur["bare"] = True
    elif line == "prunable" or line.startswith("prunable "):
        cur["prunable"] = True
        cur["prunable_reason"] = line[len("prunable"):].strip() or None


def _finish_worktree_record(cur, path_exists_fn):
    head = cur["head"]
    bare = cur["bare"]
    if bare:
        # A bare worktree record carries no HEAD line at all -- that is
        # Git's normal shape for it, never a read error (M-4).
        read_error = False
        oid = UNREADABLE
    else:
        read_error = not cur["head_seen"] or head is None or not _FULL_HEX_RE.match(head or "")
        oid = head if (head and _FULL_HEX_RE.match(head)) else UNREADABLE
    return WorktreeInventoryRecord(
        path=cur["path"], oid=oid, branch=cur["branch"], is_main=False,
        detached=cur["detached"], locked=cur["locked"], locked_reason=cur["locked_reason"],
        bare=bare, prunable=cur["prunable"], prunable_reason=cur["prunable_reason"],
        path_exists=path_exists_fn(cur["path"]), read_error=read_error,
    )


def _flush_worktree_record(out, cur, path_exists_fn):
    """Append the finished record for `cur`, marking it `is_main=True` iff
    it is the FIRST record either porcelain parser has produced so far
    (B-2) -- Git's own documented guarantee, shared here so the two parsers
    can never disagree about which record is main."""
    record = _finish_worktree_record(cur, path_exists_fn)
    if not out:
        record = record._replace(is_main=True)
    out.append(record)


def parse_worktree_inventory(porcelain_text, path_exists_fn=None):
    """Parse newline/blank-line-delimited `git worktree list --porcelain`
    output into a list of WorktreeInventoryRecord. See
    parse_worktree_inventory_nul for the `-z` (NUL-terminated) variant
    needed for a path that could itself contain a newline."""
    path_exists_fn = path_exists_fn or os.path.exists
    out = []
    cur = None
    for raw in (porcelain_text or "").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            if cur is not None:
                _flush_worktree_record(out, cur, path_exists_fn)
                cur = None
            continue
        if line.startswith("worktree "):
            if cur is not None:
                _flush_worktree_record(out, cur, path_exists_fn)
            cur = _new_worktree_record(line[len("worktree "):].strip())
            continue
        if cur is None:
            continue
        _apply_worktree_line(cur, line, unquote=True)
    if cur is not None:
        _flush_worktree_record(out, cur, path_exists_fn)
    return out


def parse_worktree_inventory_nul(porcelain_z_text, path_exists_fn=None):
    """Parse `git worktree list --porcelain -z` output: each LINE is
    NUL-terminated instead of newline-terminated, and a record ends at an
    EMPTY field (i.e. two consecutive NULs) instead of a blank line. This is
    the format that survives a worktree path containing a raw newline or
    unusual/non-ASCII bytes -- the ordinary newline-delimited porcelain
    format cannot represent that path unambiguously at all."""
    path_exists_fn = path_exists_fn or os.path.exists
    out = []
    cur = None
    if not porcelain_z_text:
        return out
    for field in porcelain_z_text.split("\0"):
        if field == "":
            if cur is not None:
                _flush_worktree_record(out, cur, path_exists_fn)
                cur = None
            continue
        if field.startswith("worktree "):
            if cur is not None:
                _flush_worktree_record(out, cur, path_exists_fn)
            cur = _new_worktree_record(field[len("worktree "):])
            continue
        if cur is None:
            continue
        _apply_worktree_line(cur, field, unquote=False)
    if cur is not None:
        _flush_worktree_record(out, cur, path_exists_fn)
    return out


def bind_branch_occupancy(branch_records, worktree_records):
    """AC-09: return a new list of BranchRefRecord with `occupied_by` filled
    in from the REAL worktree list -- a branch is occupied iff some
    non-detached, readable worktree record's `branch` field names it
    exactly. Never mutates upstream_gone or any other field (AC-07:
    occupancy is a separate fact from delivery-proof eligibility).

    `worktree_records` being `None` or `UNREADABLE` means the worktree list
    itself could not be obtained -- every branch's occupancy is then
    UNREADABLE (unknown), never silently defaulted to unoccupied (B-3): a
    guard keyed on "confirmed not checked out anywhere" must never receive
    that answer from a read that never actually happened. An explicit empty
    list is trusted as a genuinely complete (if unusual) worktree list.

    A branch bound here as occupied by a worktree whose OWN `path_exists`
    is False is still reported occupied -- the fact is true (some record
    still names this branch) even though the path is currently missing; a
    caller that wants to treat "worktree gone from disk" differently from
    "worktree present and checked out" can cross-reference `path_exists` on
    the same worktree record this occupancy came from."""
    if worktree_records is None or worktree_records is UNREADABLE:
        return [b._replace(occupied_by=UNREADABLE) for b in (branch_records or [])]
    occupants = {}
    for wt in worktree_records:
        if wt.branch and not wt.detached and not wt.read_error:
            occupants.setdefault(wt.branch, wt.path)
    out = []
    for b in branch_records or []:
        out.append(b._replace(occupied_by=occupants.get(b.name)))
    return out


WorktreeLossSurface = namedtuple("WorktreeLossSurface", [
    "dirty", "untracked", "ignored_only", "locked", "is_current",
    "nested_repo", "read_error", "retain",
])


def classify_worktree_loss_surface(status_text, is_locked, is_current_worktree,
                                    has_nested_repo, record_read_error=False):
    """AC-11/AC-12: classify what a worktree actually holds BEFORE any
    directory removal is even proposed.

    `status_text` is `git status --porcelain=v1 --ignored --untracked-
    files=all` run INSIDE the worktree, or `None`/`UNREADABLE` if that read
    failed. A failed read is NEVER folded into "no output means clean"
    (AC-05, AC-11) -- it retains the worktree and sets `read_error=True`.
    The same applies if `is_locked`, `is_current_worktree`, or
    `has_nested_repo` is itself `UNREADABLE` (M-3: "unknown" must never
    silently coerce to "confirmed absent" in a boolean `or` chain), or if
    the caller passes `record_read_error=True` -- the inventory record this
    worktree came from was itself unreadable (H-5: a caller MUST be able to
    fold that fact in here, since this function is the only one that
    produces the retention verdict).

    `retain` is True -- i.e. this worktree is NOT a disposal candidate
    without a separate, explicit named-loss decision (AC-12) -- if it is
    dirty, has ANY untracked content (ignored or not), is locked, is the
    currently executing worktree, contains a nested repository/unsupported
    submodule boundary, or any input above could not be determined at all.
    `retain` is False only when every one of those signals is affirmatively
    absent, and is always a real bool (M-3), never a sentinel."""
    unknown_input = record_read_error or any(
        v is UNREADABLE for v in (is_locked, is_current_worktree, has_nested_repo)
    )
    if status_text is None or status_text is UNREADABLE or unknown_input:
        return WorktreeLossSurface(
            dirty=False, untracked=False, ignored_only=False, locked=is_locked,
            is_current=is_current_worktree, nested_repo=has_nested_repo,
            read_error=True, retain=True,
        )
    dirty = False
    untracked = False
    has_ignored = False
    for raw in status_text.splitlines():
        if not raw.strip():
            continue
        code = raw[:2]
        if code == "!!":
            has_ignored = True
        elif code == "??":
            untracked = True
        else:
            dirty = True
    # M-1: "ignored_only" means what it says -- ignored content coexisting
    # with dirty/untracked content is not "only" ignored content.
    ignored_only = has_ignored and not dirty and not untracked
    # No bool() coercion needed here: the unknown_input check above already
    # refused every UNREADABLE input via an early return with a literal
    # True, so every operand below is a real bool by construction -- an
    # `or` chain over real bools is already a real bool.
    retain = dirty or untracked or has_ignored or is_locked or is_current_worktree or has_nested_repo
    return WorktreeLossSurface(
        dirty=dirty, untracked=untracked, ignored_only=ignored_only, locked=is_locked,
        is_current=is_current_worktree, nested_repo=has_nested_repo,
        read_error=False, retain=retain,
    )


def _is_filesystem_root(path):
    """True iff `path` (already realpath-resolved and separator-stripped)
    IS a bare volume, filesystem, or UNC-share root -- "/", "C:",
    "\\\\server\\share" -- with no further path component. Guards
    validate_resource_path's allowlist against ever admitting "everything
    on this volume/share" as an authorized target (H-4).

    Uses `ntpath` explicitly rather than `os.path`: a Windows drive letter
    or UNC prefix must be recognized the same way on every platform this
    module's tests run on (Linux, macOS, Windows) -- `os.path.splitdrive`
    is platform-native and never recognizes a Windows-shaped root at all on
    POSIX, which silently admitted "C:\\" and "\\\\server\\share" as valid
    (non-root) allowlist entries whenever this ran on a POSIX CI runner."""
    if not path:
        return False
    if path in ("/", "\\"):
        return True
    drive, tail = ntpath.splitdrive(path)
    return bool(drive) and tail.rstrip("/\\") == ""


def validate_resource_path(path, allowed_paths, real_path_fn=None):
    """AC-13: pure guard against an unsafe filesystem target -- BEFORE any
    directory removal is even proposed. `allowed_paths` is the CALLER'S own
    authorized target set -- e.g. the exact worktree paths a fresh
    inventory just reported -- never a "nested under some root" rule (H-2):
    Git worktrees are conventionally SIBLINGS of the repository root, not
    descendants of it, so a nesting rule refuses every real worktree this
    guard exists to let a caller remove.

    Returns `(True, resolved_path)` only when `path` resolves (via
    `real_path_fn`, production default os.path.realpath) to EXACTLY one
    entry of `allowed_paths` (also resolved, and compared with
    OS-appropriate case-folding via os.path.normcase) -- and that entry is
    not itself a bare volume/filesystem/UNC-share root (H-4). Returns
    `(False, reason)` for an empty/blank path, a resolution that raises, or
    a resolution matching no authorized target -- a resolution failure is
    refused, never defaulted to safe.

    The RESOLVED path is returned specifically so a caller acts on what
    this guard actually validated (H-3) -- but this function proves nothing
    about what a symlink or junction resolves to a moment later. A caller
    MUST revalidate at the actual mutation seam (the same discipline
    execute_branch_deletion already applies to worktree occupancy), not
    cache this result across a delay."""
    real_path_fn = real_path_fn or os.path.realpath
    if not path or not path.strip():
        return (False, "path is empty")
    try:
        resolved = real_path_fn(path)
    except Exception as exc:  # noqa: BLE001 -- any resolution failure is fail-safe refusal
        return (False, "path could not be resolved: %s" % exc)
    if not resolved:
        return (False, "path could not be resolved")
    resolved = _strip_trailing_sep(resolved)
    resolved_key = os.path.normcase(resolved)
    for allowed in (allowed_paths or []):
        if not allowed or not allowed.strip():
            continue
        try:
            resolved_allowed = real_path_fn(allowed)
        except Exception:  # noqa: BLE001 -- an unresolvable allowlist entry is skipped, not fatal
            continue
        if not resolved_allowed:
            continue
        resolved_allowed = _strip_trailing_sep(resolved_allowed)
        if _is_filesystem_root(resolved_allowed):
            continue
        if os.path.normcase(resolved_allowed) == resolved_key:
            return (True, resolved)
    return (False, "path does not exactly match an authorized target")
