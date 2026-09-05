#!/usr/bin/env python3
# codeArbiter — prepare a reviewed, append-only tag provenance candidate.
# OFFLINE CANDIDATE ONLY: this neither authenticates receipt provenance nor edits
# the source manifest. Before invoking it, the caller MUST authenticate the
# downloaded artifact and its repository, workflow, run and attempt independently,
# then supply those expected values from that trusted evidence. JSON claims are
# not authority. A hosted observation does not establish original tag history.
#
# reconcile(manifest, receipt, expected, legacy_tags=...) -> dict | None: pure append or no-op.
# main(argv=None) -> int: bounded input verification and exclusive candidate write.

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from tag_publication_receipt import REPO_RE, _Parser, _output_path, _positive_integer, _sha, _tag
from check_tag_immutability import load_legacy_manifest, load_original_manifest, validate_disjoint


RECEIPT_LIMIT = 16 * 1024
MANIFEST_LIMIT = 2 * 1024 * 1024
IDENTITY_KEYS = {"object_sha", "object_type", "commit_sha"}
EXPECTED_KEYS = {"repo", "tag", "commit", "run_id", "run_attempt", "workflow_sha"}


def _keys(value, wanted):
    if not isinstance(value, dict) or set(value) != wanted:
        raise ValueError("invalid object schema")


def _identity(value, *, exact=False):
    if not isinstance(value, dict) or not IDENTITY_KEYS.issubset(value):
        raise ValueError("invalid tag identity")
    if exact:
        _keys(value, IDENTITY_KEYS)
    _sha(value["object_sha"])
    _sha(value["commit_sha"])
    if value["object_type"] not in ("tag", "commit"):
        raise ValueError("invalid object type")
    if value["object_type"] == "commit" and value["object_sha"] != value["commit_sha"]:
        raise ValueError("inconsistent direct commit identity")
    return {key: value[key] for key in IDENTITY_KEYS}


def _bindings(value):
    _keys(value, EXPECTED_KEYS)
    repo = value["repo"]
    if (not isinstance(repo, str) or not REPO_RE.fullmatch(repo)
            or repo.split("/")[1] in (".", "..") or repo.split("/")[0].endswith("-")):
        raise ValueError("invalid repository identity")
    _tag(value["tag"])
    _sha(value["commit"])
    _sha(value["workflow_sha"])
    for key in ("run_id", "run_attempt"):
        if type(value[key]) is not int or not 0 < value[key] < 10 ** 20:
            raise ValueError("invalid hosted run identity")


def reconcile(manifest, receipt, expected, *, legacy_tags):
    """Validate all history, then produce one append without mutating inputs."""
    _bindings(expected)
    _keys(receipt, {"schema_version", "repo", "tag", "identity", "source"})
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1:
        raise ValueError("unsupported receipt schema")
    source = receipt["source"]
    _keys(source, {"kind", "run_id", "run_attempt", "workflow_sha"})
    if source["kind"] != "hosted-tag-observation":
        raise ValueError("unsupported evidence kind")
    identity = _identity(receipt["identity"], exact=True)
    actual = {"repo": receipt["repo"], "tag": receipt["tag"], "commit": identity["commit_sha"],
              "run_id": source["run_id"], "run_attempt": source["run_attempt"],
              "workflow_sha": source["workflow_sha"]}
    _bindings(actual)
    if actual != expected:
        raise ValueError("receipt does not match independently supplied bindings")
    original = load_original_manifest(manifest)
    if set(original) & set(legacy_tags):
        raise ValueError("original and legacy tag ledgers overlap")
    tag = expected["tag"]
    if tag in legacy_tags:
        raise ValueError("closed legacy tag cannot be admitted as a publication receipt")
    if tag in manifest["tags"]:
        if _identity(manifest["tags"][tag]) != identity:
            raise ValueError("existing tag identity conflicts; history cannot be replaced")
        return None
    result = copy.deepcopy(manifest)
    result["tags"][tag] = identity
    return result


def _read_bytes(path, limit):
    # Inputs and output live in caller-controlled private directories. Reject
    # static link/reparse aliases; hostile same-user filesystem races are outside
    # this cooperative offline tool's boundary, not claimed atomic protection.
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("unsafe input path")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("input is not a regular file")
    with path.open("rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("input is not a regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds size limit")
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("nonfinite JSON number")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _decode(data):
    document = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_nonfinite, parse_float=_finite_float)
    if not isinstance(document, dict):
        raise ValueError("JSON root must be an object")
    return document


def _write_candidate(output, payload, verify_current):
    # No partial candidate or overwrite, even when a collision appears after
    # validation. Recheck the source after writing/fsync and immediately before
    # exclusive publication. This detects drift, not adversarial lock-free races.
    descriptor, temporary = tempfile.mkstemp(prefix=".tag-candidate-", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        verify_current()
        os.link(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            print("tag candidate: temporary file cleanup failed", file=sys.stderr)


def _arguments(argv):
    parser = _Parser(description="Prepare an offline candidate from independently authenticated evidence",
                     allow_abbrev=False)
    flags = ("receipt", "manifest", "legacy-manifest", "output", "expected-manifest-sha256",
             "expected-legacy-sha256", "expected-repo",
             "expected-tag", "expected-commit", "expected-run-id", "expected-run-attempt",
             "expected-workflow-sha")
    for flag in flags:
        parser.add_argument("--" + flag, required=True)
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) > 24 or any(len(value) > 4096 for value in values):
        raise ValueError("invalid candidate arguments")
    for flag in flags:
        if sum(value == "--" + flag or value.startswith("--" + flag + "=")
               for value in values) > 1:
            raise ValueError("duplicate candidate arguments")
    return parser.parse_args(values)


def main(argv=None):
    """Create a review candidate, never an authenticated or installed baseline."""
    try:
        args = _arguments(argv)
    except ValueError:
        print("tag candidate: invalid arguments", file=sys.stderr)
        return 2
    try:
        if (not re.fullmatch(r"[0-9a-f]{64}", args.expected_manifest_sha256)
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_legacy_sha256)):
            raise ValueError("invalid expected manifest digest")
        expected = {"repo": args.expected_repo, "tag": args.expected_tag,
                    "commit": args.expected_commit,
                    "run_id": _positive_integer(args.expected_run_id),
                    "run_attempt": _positive_integer(args.expected_run_attempt),
                    "workflow_sha": args.expected_workflow_sha}
        _bindings(expected)
        output = _output_path(args.output)
        manifest_bytes = _read_bytes(args.manifest, MANIFEST_LIMIT)
        if hashlib.sha256(manifest_bytes).hexdigest() != args.expected_manifest_sha256:
            raise ValueError("stale manifest digest")
        legacy_bytes = _read_bytes(args.legacy_manifest, MANIFEST_LIMIT)
        if hashlib.sha256(legacy_bytes).hexdigest() != args.expected_legacy_sha256:
            raise ValueError("stale legacy ledger digest")
        receipt = _decode(_read_bytes(args.receipt, RECEIPT_LIMIT))
        manifest = _decode(manifest_bytes)
        legacy = load_legacy_manifest(_decode(legacy_bytes))
        validate_disjoint(load_original_manifest(manifest), legacy)
        result = reconcile(manifest, receipt, expected, legacy_tags=set(legacy))

        def verify_current():
            if _read_bytes(args.manifest, MANIFEST_LIMIT) != manifest_bytes:
                raise ValueError("manifest changed during reconciliation")
            if _read_bytes(args.legacy_manifest, MANIFEST_LIMIT) != legacy_bytes:
                raise ValueError("legacy ledger changed during reconciliation")

        if result is None:
            verify_current()
            return 0
        payload = (json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > MANIFEST_LIMIT:
            raise ValueError("candidate exceeds manifest size limit")
        _write_candidate(output, payload, verify_current)
    except (ValueError, OSError, RecursionError):
        print("tag candidate: validation failed; no new candidate accepted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
