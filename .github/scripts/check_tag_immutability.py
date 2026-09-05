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
audit compares that ledger plus ADR-0034's separate closed legacy observation
ledger against a live listing of the refs and reports any
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
missing credentials, unreadable inventory, or any governed tag absent from the
disjoint union. A new, non-legacy tag must be recorded afterward from its
trusted run receipt through a reviewed PR before another release is allowed.
The receipt writer has no legacy-ledger mutation path and there is no
break-glass path.

READ-ONLY.  One GET against `/git/matching-refs/tags/`. Nothing is written.
Transport unavailability remains a loud ordinary-CI skip; a successful but
malformed or incomplete response fails because it cannot be trusted as the
complete inventory.
"""
import argparse
import dataclasses
import hashlib
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
LEGACY_MANIFEST_PATH = REPO_ROOT / ".github" / "legacy-published-tags.json"

LEGACY_SCHEMA = "legacy-published-tags/v1"
LEGACY_ADR = "0034-establish-closed-legacy-published-tag-provenance-epoch"
LEGACY_OBSERVED_AT = "2026-09-04T20:45:43Z"
LEGACY_RECORD_COUNT = 44
LEGACY_SET_SHA256 = "26f2d1b06b494dbcc721367e09af52f32ca1a50a71dddb457557af2a48cd8c48"
LEGACY_MATRIX_SHA256 = "cfb3f66e933edb6b1f075f3e089103115c95837b944d56e2c7338d0d3519e8a6"
LEGACY_GRADES = {
    "publisher-log-corroborated": 15,
    "associated-run-metadata-only": 28,
    "current-release-metadata-only": 1,
}

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


@dataclasses.dataclass(frozen=True)
class LegacyProvenance(Provenance):
    """A later observation baseline; never original-publication evidence."""

    observed_at: str
    source_id: str
    evidence_grade: str


class InvalidInventory(ValueError):
    """A successful response that cannot be a complete trustworthy inventory."""


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


def _exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {label} schema")
    return value


def _identity(entry: object, *, label: str) -> Provenance:
    data = _exact_keys(entry, {"object_sha", "object_type", "commit_sha"}, label)
    object_sha = data["object_sha"]
    commit_sha = data["commit_sha"]
    object_type = data["object_type"]
    if (not isinstance(object_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", object_sha)
            or object_sha == "0" * 40
            or not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha)
            or commit_sha == "0" * 40
            or object_type not in ("tag", "commit")
            or (object_type == "commit" and object_sha != commit_sha)):
        raise ValueError(f"invalid {label} identity")
    return Provenance(object_sha, object_type, commit_sha)


def load_original_manifest(document: object) -> dict[str, Provenance]:
    """Validate the original-publication ledger without changing its proof meaning."""
    data = _exact_keys(document, {"$comment", "namespaces", "verified_at", "tags"},
                       "original-publication ledger")
    if (not isinstance(data["$comment"], list)
            or not all(isinstance(line, str) for line in data["$comment"])
            or data["namespaces"] != list(NAMESPACES)
            or not isinstance(data["verified_at"], str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["verified_at"]) is None
            or not isinstance(data["tags"], dict)):
        raise ValueError("invalid original-publication ledger metadata")
    result = {}
    for name, entry in data["tags"].items():
        if not isinstance(name, str) or not is_governed(name) or name in result:
            raise ValueError("invalid original-publication tag")
        result[name] = _identity(entry, label="original-publication record")
    return result


def load_legacy_manifest(document: object) -> dict[str, LegacyProvenance]:
    """Validate the immutable, exact ADR-0034 historical observation set."""
    keys = {"schema", "adr", "observed_at", "record_count", "canonical_set_sha256",
            "source_matrix_sha256", "records"}
    data = _exact_keys(document, keys, "legacy ledger")
    if (data["schema"] != LEGACY_SCHEMA or data["adr"] != LEGACY_ADR
            or data["observed_at"] != LEGACY_OBSERVED_AT
            or type(data["record_count"]) is not int
            or data["record_count"] != LEGACY_RECORD_COUNT
            or data["canonical_set_sha256"] != LEGACY_SET_SHA256
            or data["source_matrix_sha256"] != LEGACY_MATRIX_SHA256
            or not isinstance(data["records"], list)
            or len(data["records"]) != LEGACY_RECORD_COUNT):
        raise ValueError("legacy ledger does not match accepted ADR-0034 metadata")

    canonical = []
    result = {}
    grades = {grade: 0 for grade in LEGACY_GRADES}
    record_keys = {"tag", "object_sha", "object_type", "commit_sha", "observed_at",
                   "source_id", "evidence_grade"}
    for item in data["records"]:
        row = _exact_keys(item, record_keys, "legacy record")
        name = row["tag"]
        grade = row["evidence_grade"]
        source_id = row["source_id"]
        if (not isinstance(name, str) or not is_governed(name) or name in result
                or row["observed_at"] != LEGACY_OBSERVED_AT
                or grade not in LEGACY_GRADES
                or not isinstance(source_id, str)
                or re.fullmatch(r"[1-9][0-9]{0,19}", source_id) is None):
            raise ValueError("invalid legacy record metadata")
        identity = _identity(
            {key: row[key] for key in ("object_sha", "object_type", "commit_sha")},
            label="legacy record",
        )
        result[name] = LegacyProvenance(
            identity.object_sha, identity.object_type, identity.commit_sha,
            row["observed_at"], source_id, grade,
        )
        grades[grade] += 1
        canonical.append({key: row[key] for key in (
            "tag", "evidence_grade", "source_id", "object_sha", "object_type", "commit_sha"
        )})
    if [row["tag"] for row in data["records"]] != sorted(result) or grades != LEGACY_GRADES:
        raise ValueError("legacy ledger closed set or evidence grades changed")
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != LEGACY_SET_SHA256:
        raise ValueError("legacy ledger approved identity set changed")
    return result


def validate_disjoint(original: dict[str, Provenance],
                      legacy: dict[str, LegacyProvenance]) -> None:
    overlap = set(original) & set(legacy)
    if overlap:
        raise ValueError("original-publication and legacy ledgers overlap")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


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


def audit_legacy(recorded: dict[str, LegacyProvenance],
                 live: dict[str, str] | None) -> list[str]:
    """Report only movement after observation, never original-publication history."""
    if live is None:
        return []
    findings = []
    for name in sorted(recorded):
        baseline = recorded[name]
        prefix = (f"legacy baseline {name} ({baseline.evidence_grade}) moved after its "
                  f"{baseline.observed_at} observation")
        if name not in live:
            findings.append(
                f"{prefix}: the ref no longer exists. This baseline is not "
                "original-publication evidence; correct a release with a NEW version (issue #386)."
            )
        elif live[name] != baseline.object_sha:
            findings.append(
                f"{prefix}: observed object {baseline.object_sha}, now {live[name]}. "
                "This baseline is not original-publication evidence; correct a release with a "
                "NEW version (issue #386)."
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
    if status != 200:
        return None
    if not isinstance(payload, list):
        raise InvalidInventory("matching-refs response is not a list")

    tags: dict[str, str] = {}
    for ref in payload:
        if not isinstance(ref, dict):
            raise InvalidInventory("malformed matching-refs entry")
        full_name = ref.get("ref")
        obj = ref.get("object")
        if not isinstance(full_name, str) or not full_name.startswith("refs/tags/"):
            raise InvalidInventory("malformed tag ref")
        if not isinstance(obj, dict):
            raise InvalidInventory("malformed tag identity")
        name = full_name.removeprefix("refs/tags/")
        sha = obj.get("sha")
        if (
            not name or name in tags or not isinstance(sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", sha) is None
            # Working tags may legally label blobs or trees. Their presence
            # must not turn a definite release-tag drift into a skipped audit.
            or obj.get("type") not in ("tag", "commit", "blob", "tree")
        ):
            raise InvalidInventory("duplicate or invalid tag ref")
        tags[name] = sha
    return tags


def _send(request: urllib.request.Request) -> tuple[int, object]:
    """Return one decoded response; reject an invalid successful JSON body."""
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            status = response.status
            raw_body = response.read()
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, {"message": str(error)}

    try:
        body = raw_body.decode("utf-8")
        payload = (json.loads(body, object_pairs_hook=_unique_object)
                   if body.strip() else {})
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidInventory("successful response contains invalid JSON") from error
    return status, payload


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


def main(argv=None, *, token=None, rest=None, recorded=None, legacy=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--legacy-manifest", default=str(LEGACY_MANIFEST_PATH))
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

    # Ledger integrity is locally knowable and must never be hidden by missing
    # network credentials. Only the remote observation itself may skip.
    injected_original = recorded is not None
    try:
        provenance = (load_recorded(recorded) if injected_original
                      else load_original_manifest(_read_json(arguments.manifest)))
        legacy = ({} if injected_original and legacy is None else legacy)
        legacy_provenance = (load_legacy_manifest(_read_json(arguments.legacy_manifest))
                             if legacy is None else legacy)
        validate_disjoint(provenance, legacy_provenance)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        print("::error title=Tag provenance::invalid publication or legacy provenance ledger")
        return 1

    if not token and rest is None:
        if arguments.require_recorded:
            print("::error title=Tag provenance::release requires authenticated tag evidence")
            return 1
        print(_SKIP_NOTE)
        print(f"::notice title=Tag immutability::skipped for {arguments.repo} - no GH_TOKEN")
        return 0

    try:
        live = read_live_tags(
            arguments.repo, rest=rest if rest is not None else _rest_reader(token)
        )
    except InvalidInventory:
        print("::error title=Tag provenance::invalid live tag inventory; release requires a complete live tag inventory")
        return 1
    findings = audit(provenance, live)
    legacy_findings = audit_legacy(legacy_provenance, live)

    for finding in findings + legacy_findings:
        print(f"::error title=Published tag immutability::{finding}")
    for blind in unreadable(live):
        print(f"SKIP (partial): could not read {blind} - see the note in this script.")
    if findings or legacy_findings:
        return 1
    if live is None:
        if arguments.require_recorded:
            print("::error title=Tag provenance::release requires a complete live tag inventory")
            return 1
        return 0

    coverage = {**provenance, **legacy_provenance}
    missing = unrecorded(coverage, live)
    for name in missing:
        level = "error" if arguments.require_recorded else "warning"
        print(
            f"::{level} title=Unrecorded published tag::{name} is published but "
            f"absent from the disjoint provenance ledgers, so its target is not being "
            "verified. Add its original-publication receipt through the reviewed "
            "publication reconciliation path (issue #386)."
        )
    if missing and arguments.require_recorded:
        return 1
    print(
        f"OK: {len(provenance)} original-publication receipts and "
        f"{len(legacy_provenance)} legacy baselines in {arguments.repo} still resolve "
        "to their separately recorded identities."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
