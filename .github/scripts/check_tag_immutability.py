#!/usr/bin/env python3
"""Read-only audit of published-tag immutability (issue #386 AC-3).

Run:  python .github/scripts/check_tag_immutability.py --repo owner/name
Local: GH_TOKEN=$(gh auth token) python .github/scripts/check_tag_immutability.py

WHAT IT GUARDS.  This repository publishes four installable tag series - `v*`
(ca), `ca-sandbox-v*`, `ca-codex-v*`, and `ca-pi-v*` - and the README tells Pi
consumers to PIN `ca-pi-v<version>`.  A git tag is a mutable ref: anything
holding contents:write can retarget or delete one.  A moved tag means a pinned
install fetches different code under a version that prior review, prior
verification, and published release notes all still vouch for.  On 2026-07-25
the live repository had no rulesets at all and every GitHub Release reported
`immutable: false`, so nothing whatsoever prevented that move.

HOW IT KNOWS.  The originally-published commit is not recoverable from the API:
a moved tag looks exactly like a tag that was always there, and a Release's
`target_commitish` is mutable and usually just "main".  The provenance has to be
written down at publication time, which is what `.github/published-tags.json`
is - a committed manifest of tag -> (object sha, commit sha).  Its integrity
comes from git history and branch protection on main: changing a recorded sha
requires a reviewed pull request, whereas moving a tag requires nothing.  The
audit compares the manifest against a live listing of the refs and reports any
disagreement.  Comparing the REF OBJECT sha (not just the commit) is the
stronger test: an annotated tag object is content-addressed over its target,
message, and tagger, so re-annotating the same commit still changes it.

WHY IT SKIPS RATHER THAN FAILS.  Every observation is three-valued - present,
definitely different, or None for "this run could not see it".  A definite
mismatch is a security finding; an unreadable run prints a loud SKIP and passes.
Unlike the branch-protection audit beside it, this one needs only `contents:
read`, which GITHUB_TOKEN does grant, so it runs LIVE in ordinary CI rather than
skipping by default.  The skip path exists for transport failures, rate limits,
and local runs without a token - never as the normal case.

RELEASE PREFLIGHT. --require-recorded is deliberately stricter: it refuses
missing credentials, unreadable inventory, or any unrecorded governed tag.
Ordinary observation policy is unchanged. A new tag is recorded afterward from
its trusted run receipt through a reviewed PR, before another release is allowed.

READ-ONLY.  One GET against `/git/matching-refs/tags/`. Nothing is written, and
an invalid response is discarded rather than audited, because an incomplete
inventory would otherwise read as deletions.
"""
import argparse
import dataclasses
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


# The four installable series #386 names. Every published tag belongs to one;
# anything else in refs/tags is a working tag this audit has no opinion about.
NAMESPACES = ("v*", "ca-sandbox-v*", "ca-codex-v*", "ca-pi-v*")

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "published-tags.json"

_API = "https://api.github.com"
_API_VERSION = "2022-11-28"
_TIMEOUT_SECONDS = 30

# A published tag is a namespace prefix followed by a SemVer core, optionally
# with a pre-release or build suffix (`v2.1.0-beta.2` is a real published tag).
# Requiring the version shape is what stops `v*` from swallowing `versioned-*`.
_VERSION = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
_GOVERNED = re.compile(
    "^(?:%s)$" % "|".join(re.escape(ns[:-1]) + _VERSION for ns in NAMESPACES)
)


@dataclasses.dataclass(frozen=True)
class Provenance:
    """Where a tag pointed when it was PUBLISHED, as recorded in the manifest."""

    object_sha: str
    object_type: str
    commit_sha: str


def is_governed(name: str) -> bool:
    """True for a published release tag in one of the four series."""
    return bool(_GOVERNED.match(name))


def load_recorded(mapping: dict) -> dict[str, Provenance]:
    """Read the manifest's `tags` object into `Provenance` records."""
    return {
        name: Provenance(
            object_sha=entry["object_sha"],
            object_type=entry["object_type"],
            commit_sha=entry["commit_sha"],
        )
        for name, entry in mapping.items()
    }


def audit(recorded: dict[str, Provenance], live: dict[str, str] | None) -> list[str]:
    """Every DEFINITE break in tag immutability, as findings.

    Silent when `live` is None - that is an unreadable run, not a repository in
    which every published tag was simultaneously deleted.
    """
    if live is None:
        return []

    findings: list[str] = []
    for name in sorted(recorded):
        provenance = recorded[name]
        if name not in live:
            findings.append(
                f"published tag {name} no longer exists on the remote. It was "
                f"published at commit {provenance.commit_sha}. Deleting a "
                "published tag breaks every install pinned to it; a bad release "
                "is corrected by publishing a NEW version (issue #386)."
            )
        elif live[name] != provenance.object_sha:
            findings.append(
                f"published tag {name} has MOVED: it was published as "
                f"{provenance.object_sha} (commit {provenance.commit_sha}) and "
                f"now resolves to {live[name]}. Anything pinned to {name} now "
                "fetches code that the review and verification behind that "
                "version never covered (issue #386)."
            )
    return findings


def unrecorded(recorded: dict[str, Provenance], live: dict[str, str]) -> list[str]:
    """Governed tags on the remote that the manifest does not yet record.

    This is expected immediately after a release. Ordinary CI warns; strict
    release preflight refuses to authorize another release until it is recorded.
    """
    return sorted(
        name for name in live if is_governed(name) and name not in recorded
    )


def unreadable(live: dict[str, str] | None) -> list[str]:
    """The part of the contract this run could not see, in plain words."""
    if live is None:
        return ["the repository's live tag refs, so no tag was verified at all"]
    return []


def read_live_tags(repo: str, *, rest) -> dict[str, str] | None:
    """Every tag ref as name -> object sha, or None if it could not be read.

    GitHub's matching-refs endpoint returns the complete matching array in one
    response. All-or-nothing validation prevents malformed or partial data from
    becoming fabricated deletion findings.
    """
    status, payload = rest(f"/repos/{repo}/git/matching-refs/tags/")
    if status != 200 or not isinstance(payload, list):
        return None

    tags: dict[str, str] = {}
    for ref in payload:
        if not isinstance(ref, dict):
            return None
        full_name = ref.get("ref")
        obj = ref.get("object")
        if not isinstance(full_name, str) or not full_name.startswith("refs/tags/"):
            return None
        if not isinstance(obj, dict):
            return None
        name = full_name.removeprefix("refs/tags/")
        sha = obj.get("sha")
        if (
            not name or name in tags or not isinstance(sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", sha) is None
            # Working tags may legally label blobs or trees. Their presence
            # must not turn a definite release-tag drift into a skipped audit.
            or obj.get("type") not in ("tag", "commit", "blob", "tree")
        ):
            return None
        tags[name] = sha
    return tags


def _send(request: urllib.request.Request) -> tuple[int, object]:
    """One request, reduced to (status, decoded body). Never raises."""
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return 0, {"message": str(error)}


def _rest_reader(token: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": "codearbiter-tag-immutability-audit",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def rest(path: str) -> tuple[int, object]:
        return _send(urllib.request.Request(_API + path, method="GET", headers=headers))

    return rest


_SKIP_NOTE = """SKIP: no token, so published-tag immutability was NOT audited.

This check reads `/repos/{owner}/{repo}/git/matching-refs/tags/`, which needs only
contents:read - a permission the default GITHUB_TOKEN DOES grant - so in ordinary
CI it runs live and this skip should not appear. It exists for local runs and for
transport failures, because a merge gate must report a settings or history
regression, never a network problem.

To run the audit by hand:

    GH_TOKEN=$(gh auth token) python .github/scripts/check_tag_immutability.py \\
        --repo arbiterForge/codeArbiter
"""


def main(argv=None, *, token=None, rest=None, recorded=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument(
        "--require-recorded", action="store_true",
        help="Refuse release when prior tag records are incomplete or cannot be verified.",
    )
    arguments = parser.parse_args(argv)

    if token is None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not arguments.repo:
        if arguments.require_recorded:
            print("::error title=Tag provenance::release requires a repository to verify")
            return 1
        print("SKIP: no --repo and no GITHUB_REPOSITORY; nothing to audit.")
        return 0
    if not token and rest is None:
        if arguments.require_recorded:
            print("::error title=Tag provenance::release requires authenticated tag evidence")
            return 1
        print(_SKIP_NOTE)
        print(f"::notice title=Tag immutability::skipped for {arguments.repo} - no GH_TOKEN")
        return 0

    if recorded is None:
        recorded = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))["tags"]
    provenance = load_recorded(recorded)

    live = read_live_tags(
        arguments.repo, rest=rest if rest is not None else _rest_reader(token)
    )
    findings = audit(provenance, live)

    for finding in findings:
        print(f"::error title=Published tag immutability::{finding}")
    for blind in unreadable(live):
        print(f"SKIP (partial): could not read {blind} - see the note in this script.")
    if findings:
        return 1
    if live is None:
        if arguments.require_recorded:
            print("::error title=Tag provenance::release requires a complete live tag inventory")
            return 1
        return 0

    missing = unrecorded(provenance, live)
    for name in missing:
        level = "error" if arguments.require_recorded else "warning"
        print(
            f"::{level} title=Unrecorded published tag::{name} is published but "
            f"absent from {MANIFEST_PATH.name}, so its target is not being "
            "verified. Add it in the release that published it (issue #386)."
        )
    if missing and arguments.require_recorded:
        return 1
    print(
        f"OK: {len(provenance)} published tags in {arguments.repo} still resolve "
        "to the commits they were published at."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
