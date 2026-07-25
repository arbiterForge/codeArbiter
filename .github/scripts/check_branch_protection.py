#!/usr/bin/env python3
"""Read-only audit of main's merge-readiness enforcement (issue #383 AC-3).

Run:  python .github/scripts/check_branch_protection.py --repo owner/name
Local: GH_TOKEN=$(gh auth token) python .github/scripts/check_branch_protection.py

WHAT IT GUARDS.  main's only required status context is ci.yml's
`[GATE ] | [REPO] | Merge readiness` aggregate.  On 2026-07-25 that context sat
behind `required_status_checks.strict=false` and no merge queue, so a pull
request could merge on a required check computed against an OLDER base - two
individually green pull requests could interact after one landed while the
second kept a valid check from its stale merge base.  #383's ruling was a merge
queue, which synthesises and tests the exact prospective merge commit.  Both
answers are accepted here: `strict` OR a queue.  Demanding both would fail the
moment the ruled-on fix landed, because a queue makes `strict` redundant and it
is expected to stay false.

WHY IT SKIPS RATHER THAN FAILS.  `GET /repos/{owner}/{repo}/branches/{branch}
/protection` requires Administration:read.  A workflow `permissions:` block has
no key that grants it - `administration` is not among GITHUB_TOKEN's permission
scopes - so in ordinary CI this audit CANNOT see the protection document, and a
check that failed on that would jam every merge for a permission that cannot be
granted.  Every field is therefore three-valued: True, False, or None for "this
run could not see it".  A definite False is a violation; a None is a skip that
prints what it could not check and how to check it.  Only a settings change is
ever reported, never a transport or permission problem.

READ-ONLY.  Two calls, both queries: a REST GET for the protection document and
a GraphQL query for `repository.mergeQueue`.  The GraphQL call is an HTTP POST
because that is the protocol's only verb; it mutates nothing.  The merge-queue
answer needs plain repository read, so a run without admin rights can still
prove the queue is on even when the protection document is invisible.
"""
import argparse
import dataclasses
import json
import os
import sys
import urllib.error
import urllib.request


# The single stable context #383 requires to REMAIN main's required check.
# Un-requiring it makes every other guarantee vacuous: there would be nothing
# whose passing SHA the base has to be current with.
MERGE_READINESS_CONTEXT = "[GATE ] | [REPO] | Merge readiness"

_API = "https://api.github.com"
_API_VERSION = "2022-11-28"
_TIMEOUT_SECONDS = 30

# `mergeQueue` is null until a queue is configured for the branch, and is
# readable with ordinary repository read - unlike the protection document.
_MERGE_QUEUE_QUERY = """
query($owner: String!, $name: String!, $branch: String!) {
  repository(owner: $owner, name: $name) {
    mergeQueue(branch: $branch) { id }
  }
}
"""


@dataclasses.dataclass(frozen=True)
class Enforcement:
    """What this run could actually READ about a branch's merge enforcement.

    Every field is three-valued.  `None` means unreadable - no token, a token
    without Administration:read, or a transport failure - and never means
    "switched off".  Conflating the two is what would turn a read-only audit
    into a merge jam.
    """

    protected: bool | None
    strict: bool | None
    merge_queue: bool | None
    contexts: tuple[str, ...] | None


def audit(enforcement: Enforcement) -> list[str]:
    """Every DEFINITE weakening of merge-readiness enforcement, as findings.

    Silent on anything it could not read.  An empty list means "nothing
    observed is wrong", which is not the same as "everything was checked" -
    `unreadable()` reports that half.
    """
    if enforcement.protected is False:
        # GitHub answers 404 for an unprotected branch and 403 when the token
        # merely lacks rights, so this is a real absence and not a blind spot.
        # It short-circuits: naming a missing context on an unprotected branch
        # is noise piled on the one finding that matters.
        return [
            "main has no branch protection at all, so nothing requires "
            f"{MERGE_READINESS_CONTEXT} before a merge (issue #383)."
        ]

    findings: list[str] = []
    if enforcement.strict is False and enforcement.merge_queue is False:
        findings.append(
            "main can merge a stale-base result: required_status_checks.strict "
            "is false and no merge queue is enabled, so a green "
            f"{MERGE_READINESS_CONTEXT} computed against an OLDER base still "
            "satisfies the gate. Re-enable the merge queue for main, or turn on "
            '"Require branches to be up to date before merging" (issue #383).'
        )
    if enforcement.contexts is not None and MERGE_READINESS_CONTEXT not in enforcement.contexts:
        # Requiring MORE contexts is a hardening, not a weakening, so only the
        # absence of the stable one is reported.
        findings.append(
            f"main no longer requires the {MERGE_READINESS_CONTEXT} context "
            f"(required contexts: {list(enforcement.contexts) or 'none'}). "
            "It is the single stable context every other guarantee hangs off "
            "(issue #383)."
        )
    return findings


def unreadable(enforcement: Enforcement) -> list[str]:
    """The parts of the contract this run could not see, in plain words."""
    blind: list[str] = []
    if enforcement.protected is None:
        blind.append("whether main is protected at all")
    if enforcement.merge_queue is None:
        blind.append("whether a merge queue is enabled for main")
    if enforcement.strict is None and enforcement.merge_queue is not True:
        # An enabled queue already settles the base-currency question, so the
        # unreadable `strict` flag is not a gap worth reporting.
        blind.append("required_status_checks.strict")
    if enforcement.contexts is None:
        blind.append("the required status-check contexts")
    return blind


def enforcement_from_protection(
    document: dict, merge_queue: bool | None = None
) -> Enforcement:
    """Read a branch-protection response into an `Enforcement`."""
    checks = document.get("required_status_checks") or {}
    contexts = checks.get("contexts")
    if contexts is None:
        # `contexts` is deprecated in favour of `checks`; a response carrying
        # only the newer array must not read as "the context was dropped".
        contexts = [
            entry.get("context")
            for entry in (checks.get("checks") or [])
            if isinstance(entry, dict) and entry.get("context")
        ]
    return Enforcement(
        protected=True,
        strict=bool(checks.get("strict", False)),
        merge_queue=merge_queue,
        contexts=tuple(contexts),
    )


def read_enforcement(repo: str, branch: str, *, rest, graphql) -> Enforcement:
    """Gather what the given transports can see. Never raises on an API error."""
    owner, _, name = repo.partition("/")

    merge_queue: bool | None = None
    status, payload = graphql(
        _MERGE_QUEUE_QUERY, {"owner": owner, "name": name, "branch": branch}
    )
    if status == 200 and not payload.get("errors"):
        repository = (payload.get("data") or {}).get("repository")
        if isinstance(repository, dict) and "mergeQueue" in repository:
            merge_queue = repository["mergeQueue"] is not None

    status, payload = rest(f"/repos/{repo}/branches/{branch}/protection")
    if status == 200:
        return enforcement_from_protection(payload, merge_queue=merge_queue)
    if status == 404:
        return Enforcement(protected=False, strict=None, merge_queue=merge_queue, contexts=None)
    # 401/403 (no Administration:read), 5xx, or a transport failure reported as
    # status 0 - all unreadable, none of them a finding.
    return Enforcement(protected=None, strict=None, merge_queue=merge_queue, contexts=None)


def _send(request: urllib.request.Request) -> tuple[int, dict]:
    """One request, reduced to (status, decoded body). Never raises."""
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8")
            payload = json.loads(body) if body.strip() else {}
        except (ValueError, OSError):
            payload = {}
        return error.code, payload
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return 0, {"message": str(error)}


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": "codearbiter-branch-protection-audit",
    }


def _rest_reader(token: str):
    def rest(path: str) -> tuple[int, dict]:
        return _send(urllib.request.Request(_API + path, method="GET", headers=_headers(token)))

    return rest


def _graphql_reader(token: str):
    def graphql(query: str, variables: dict) -> tuple[int, dict]:
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        headers = _headers(token) | {"Content-Type": "application/json"}
        return _send(
            urllib.request.Request(_API + "/graphql", data=body, method="POST", headers=headers)
        )

    return graphql


_SKIP_NOTE = """SKIP: no token, so main's branch protection was NOT audited.

This is expected in ordinary CI. Reading a branch-protection document requires
Administration:read, and a workflow `permissions:` block has no key that grants
it, so the default GITHUB_TOKEN can never satisfy this check. It skips instead
of failing because a merge gate must not depend on a permission that cannot be
granted.

To actually run the audit, set GH_TOKEN to a token with admin rights on the
repository - as a repository secret wired into this step, or locally with:

    GH_TOKEN=$(gh auth token) python .github/scripts/check_branch_protection.py
"""


def main(argv=None, *, token=None, rest=None, graphql=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default="main")
    arguments = parser.parse_args(argv)

    if token is None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not arguments.repo:
        print("SKIP: no --repo and no GITHUB_REPOSITORY; nothing to audit.")
        return 0
    if not token and (rest is None or graphql is None):
        print(_SKIP_NOTE)
        print(f"::notice title=Branch protection audit::skipped for {arguments.repo} - no GH_TOKEN")
        return 0

    enforcement = read_enforcement(
        arguments.repo,
        arguments.branch,
        rest=rest if rest is not None else _rest_reader(token),
        graphql=graphql if graphql is not None else _graphql_reader(token),
    )
    findings = audit(enforcement)
    blind = unreadable(enforcement)

    for finding in findings:
        print(f"::error title=Branch protection::{finding}")
    if blind:
        print(
            "SKIP (partial): could not read "
            + "; ".join(blind)
            + " - see the note above on Administration:read."
        )
    if findings:
        return 1
    print(
        f"OK: {arguments.repo}@{arguments.branch} still enforces merge readiness "
        f"against the current base (strict={enforcement.strict}, "
        f"merge_queue={enforcement.merge_queue})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
