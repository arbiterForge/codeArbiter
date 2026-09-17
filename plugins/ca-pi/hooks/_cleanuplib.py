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

Public API: evaluate_merge_proof(...) -> ProofResult.
"""

from collections import namedtuple

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
