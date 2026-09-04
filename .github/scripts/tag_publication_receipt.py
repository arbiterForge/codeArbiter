#!/usr/bin/env python3
# codeArbiter — capture an exact hosted tag observation.
# This is a current observation, NOT proof of original publication. The caller
# owns the trusted checkout/origin, hosted metadata, and private output directory.
# No tag is created, moved, or deleted. Diagnostics never include transport data.
#
# parse_remote_refs(text, tag, expected_commit) -> dict: strict identity parser.
# main(argv=None, *, run=None) -> int: capture CLI, injectable Git boundary.

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


SHA_RE = re.compile(r"[0-9a-f]{40}")
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")
NUMBER = r"(?:0|[1-9][0-9]*)"
PRERELEASE = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
TAG_RE = re.compile(
    rf"(?:ca-(?:sandbox|codex|pi)-)?v{NUMBER}\.{NUMBER}\.{NUMBER}"
    rf"(?:-{PRERELEASE}(?:\.{PRERELEASE})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
MAX_REF_OUTPUT = 4096


def _sha(value):
    if not isinstance(value, str) or not SHA_RE.fullmatch(value) or value == "0" * 40:
        raise ValueError("invalid commit or object identity")
    return value


def _tag(value):
    if not isinstance(value, str) or len(value) > 256 or not TAG_RE.fullmatch(value):
        raise ValueError("invalid governed version tag")
    return value


def _positive_integer(value):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("invalid hosted run metadata")
    return int(value)

def parse_remote_refs(text, tag, expected_commit):
    """Reject any observation other than one exact ref and optional peeled ref."""
    _tag(tag)
    _sha(expected_commit)
    if not isinstance(text, str) or not text or len(text) > MAX_REF_OUTPUT:
        raise ValueError("missing or oversized remote observation")
    ref = "refs/tags/" + tag
    records = text.removesuffix("\n").split("\n")
    if len(records) not in (1, 2):
        raise ValueError("ambiguous remote observation")
    observed = {}
    for record in records:
        fields = record.split("\t")
        if len(fields) != 2:
            raise ValueError("malformed remote observation")
        object_sha, name = fields
        _sha(object_sha)
        if name not in (ref, ref + "^{}") or name in observed:
            raise ValueError("unexpected or duplicate remote ref")
        observed[name] = object_sha
    if ref not in observed:
        raise ValueError("missing exact remote ref")
    commit_sha = observed.get(ref + "^{}", observed[ref])
    if commit_sha != expected_commit:
        raise ValueError("remote commit does not match expected commit")
    return {"object_sha": observed[ref],
            "object_type": "tag" if ref + "^{}" in observed else "commit",
            "commit_sha": commit_sha}


def _output_path(value):
    if not value or len(value) > 4096 or any(ord(char) < 32 for char in value):
        raise ValueError("invalid output path")
    path = Path(os.path.abspath(value))
    # Inspect lexical ancestors without resolving links. The hosted output root
    # must be private: these checks do not defend against same-user rename races.
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("unsafe output parent")
    if os.path.lexists(path):
        raise ValueError("output already exists")
    return path


def _write_exclusive(path, payload):
    # Linking a fully-written file provides no-replace publication on Windows and
    # POSIX. Unsupported filesystems fail closed; never downgrade to overwrite.
    descriptor, temporary = tempfile.mkstemp(prefix=".tag-receipt-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            # A complete, exclusively published receipt remains valid even if
            # its temporary hardlink cannot be removed. Never call that failure.
            print("tag receipt: temporary file cleanup failed", file=sys.stderr)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error message can repeat caller-supplied values.
        raise ValueError("invalid capture arguments")


def _arguments(argv):
    parser = _Parser(description="Capture a hosted tag observation (not original publication proof)",
                     allow_abbrev=False)
    parser.add_argument("command", choices=("capture",))
    flags = ("repo", "tag", "expected-commit", "run-id", "run-attempt", "workflow-sha", "output")
    for flag in flags:
        parser.add_argument("--" + flag, required=True)
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) > 15 or any(len(value) > 4096 for value in values):
        raise ValueError("invalid capture arguments")
    # Exactly one of each required flag; repeated metadata must not be last-wins.
    for flag in flags:
        if sum(value == "--" + flag or value.startswith("--" + flag + "=")
               for value in values) > 1:
            raise ValueError("duplicate capture argument")
    return parser.parse_args(values)


def main(argv=None, *, run=None):
    """Capture immutable local evidence only after all claims and refs validate."""
    try:
        args = _arguments(argv)
    except ValueError:
        print("tag receipt: invalid capture arguments", file=sys.stderr)
        return 2
    try:
        if (not REPO_RE.fullmatch(args.repo) or args.repo.split("/")[1] in (".", "..")
                or args.repo.split("/")[0].endswith("-")):
            raise ValueError("invalid repository identity")
        _tag(args.tag)
        _sha(args.expected_commit)
        _sha(args.workflow_sha)
        run_id = _positive_integer(args.run_id)
        run_attempt = _positive_integer(args.run_attempt)
        output = _output_path(args.output)
        ref = "refs/tags/" + args.tag
        runner = subprocess.run if run is None else run
        result = runner(["git", "ls-remote", "--tags", "origin", ref, ref + "^{}"],
                        stdin=subprocess.DEVNULL, capture_output=True, text=True,
                        encoding="ascii", errors="strict", timeout=30, check=False, shell=False)
        if result.returncode != 0:
            raise ValueError("remote observation failed")
        identity = parse_remote_refs(result.stdout, args.tag, args.expected_commit)
        document = {"schema_version": 1, "repo": args.repo, "tag": args.tag, "identity": identity,
                    "source": {"kind": "hosted-tag-observation", "run_id": run_id,
                               "run_attempt": run_attempt, "workflow_sha": args.workflow_sha}}
        payload = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
        _write_exclusive(output, payload)
    except (ValueError, OSError, subprocess.SubprocessError):
        print("tag receipt: capture failed; no new observation accepted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
