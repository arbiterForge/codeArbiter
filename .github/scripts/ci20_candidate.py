#!/usr/bin/env python3
"""Build or verify an explicitly UNQUALIFIED native CI test input.

This is a test-harness input, not a release manifest, installed payload,
qualification record, authority receipt, or permission to mutate production.
No consumer or publisher may treat a successful verification here as evidence
that native tests or complete CI have passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from _contextverificationlib import hash_go_module

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "core/artifacts"
FORMAT = "codearbiter.ci-test-input/1"
STATE = "unqualified"
WORKFLOW = ".github/workflows/ci.yml"
REPOSITORY = "arbiterForge/codeArbiter"
PRODUCER_JOB = "artifact-ci-build"
# Explicit future jobs only: production/qualification/packaging are absent.
TEST_CONSUMERS = frozenset({
    # No installed-client/authority/conformance suites until separately
    # reviewed test admission exists. They currently need native-tested input.
    "artifact-ci-direct-tests",
})
PLATFORMS = frozenset({
    "linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
    "darwin/amd64", "darwin/arm64",
})
GO_VERSION = "go1.27.1"
BUILD_FLAGS = ("build", "-trimpath", "-buildvcs=false", "-ldflags=-s -w")
GO_ENV = {
    "GOTOOLCHAIN": "local", "GOENV": "off", "GOWORK": "off",
    "GOFLAGS": "", "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0",
}
MAX_MANIFEST = 65_536
MAX_BINARY = 128 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
POSITIVE = re.compile(r"[1-9][0-9]*\Z")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate CI input metadata field: " + key)
        result[key] = value
    return result


def _regular(path: Path, maximum: int) -> bytes:
    """Reject symlinks/reparse points, nonfiles and oversize source artifacts."""
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_size > maximum):
        raise ValueError("CI input is not a bounded ordinary file: " + path.name)
    data = path.read_bytes()
    if len(data) > maximum:
        raise ValueError("CI input exceeds its bound")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _filename(platform: str) -> str:
    if platform not in PLATFORMS:
        raise ValueError("unsupported native platform")
    return "ca-artifact-" + platform.replace("/", "-") + (
        ".exe" if platform.startswith("windows/") else "")


def _environment(ambient: Mapping[str, str]) -> dict[str, str]:
    return {**ambient, **GO_ENV}


def ci_identity(role: str, *, ambient: Mapping[str, str] | None = None) -> dict[str, str]:
    """Bind CI workflow, checkout, same-run attempt, native target and Go bytes."""
    env = dict(os.environ if ambient is None else ambient)
    allowed = {PRODUCER_JOB} if role == "build" else TEST_CONSUMERS if role == "verify" else set()
    sha, run, attempt = (
        env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_ID", ""),
        env.get("GITHUB_RUN_ATTEMPT", ""),
    )
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    if (env.get("GITHUB_ACTIONS") != "true"
            or env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_JOB") not in allowed
            or not COMMIT.fullmatch(sha)
            or not POSITIVE.fullmatch(run)
            or not POSITIVE.fullmatch(attempt)
            or not workflow_ref.startswith(REPOSITORY + "/" + WORKFLOW + "@refs/")):
        raise ValueError("operation requires the exact authorized CI test job")
    checked = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8",
    ).strip()
    if checked != sha:
        raise ValueError("checked-out source is not the CI revision")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "core/artifacts"],
                   cwd=REPO, stdout=subprocess.DEVNULL, check=True)
    go = shutil.which("go")
    if go is None:
        raise ValueError("native Go executable unavailable")
    executable = Path(go).resolve(strict=True)
    values = json.loads(subprocess.check_output(
        ["go", "env", "-json", "GOOS", "GOARCH", "GOHOSTOS",
         "GOHOSTARCH", "GOVERSION", "CGO_ENABLED"],
        cwd=MODULE, env=_environment(env), encoding="utf-8", text=True,
    ), object_pairs_hook=_unique)
    platform = values["GOOS"] + "/" + values["GOARCH"]
    if (platform not in PLATFORMS
            or platform != values["GOHOSTOS"] + "/" + values["GOHOSTARCH"]
            or values["GOVERSION"] != GO_VERSION
            or values["CGO_ENABLED"] != "0"):
        raise ValueError("CI test input requires the pinned native Go toolchain")
    return {
        "source_commit": sha, "run_id": run, "run_attempt": attempt,
        "workflow_ref": workflow_ref, "platform": platform,
        "go_version": values["GOVERSION"],
        "go_sha256": _sha256(_regular(executable, MAX_BINARY)),
        "module_sha256": hash_go_module(MODULE),
    }


def _output_directory(output: Path, ambient: Mapping[str, str]) -> Path:
    """Allow a newly created output only below the GitHub runner's own temp root."""
    if not output.is_absolute() or output.is_symlink() or output.exists():
        raise ValueError("CI test output must be a new absolute directory")
    temp = ambient.get("RUNNER_TEMP", "")
    if not temp:
        raise ValueError("runner temporary directory is required")
    root = Path(temp).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("runner temporary root is invalid")
    try:
        parent = output.parent.resolve(strict=True)
    except OSError as error:
        raise ValueError("CI output parent must already exist") from error
    if parent != root:
        raise ValueError("CI test input must be an immediate child of runner temp")
    return parent


def _record(identity: dict[str, str], binary: bytes) -> dict[str, Any]:
    """Encode a distinct provisional type with no native-tested or PASS field."""
    filename = _filename(identity["platform"])
    return {
        "format": FORMAT,
        "state": STATE,
        "source_commit": identity["source_commit"],
        "run_id": identity["run_id"],
        "producer_attempt": identity["run_attempt"],
        "workflow_ref": identity["workflow_ref"],
        "platform": identity["platform"],
        "go_version": identity["go_version"],
        "go_sha256": identity["go_sha256"],
        "module_sha256": identity["module_sha256"],
        "build_flags": list(BUILD_FLAGS) + ["-o", filename, "./cmd/ca-artifact"],
        "build_environment": dict(GO_ENV),
        "binary": {"file": filename, "size": len(binary), "sha256": _sha256(binary)},
    }


def build(output: Path, identity: dict[str, str], *, ambient: Mapping[str, str]) -> dict[str, Any]:
    """Compile but never test, mark native-tested, or create release.json."""
    _output_directory(output, ambient)
    filename = _filename(identity["platform"])
    with tempfile.TemporaryDirectory(prefix="ci20-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        argv = ["go", *BUILD_FLAGS, "-o", str(stage / filename), "./cmd/ca-artifact"]
        subprocess.run(argv, cwd=MODULE, env=_environment(ambient), timeout=300, check=True)
        binary = _regular(stage / filename, MAX_BINARY)
        if not binary:
            raise ValueError("CI compiler produced an empty executable")
        record = _record(identity, binary)
        with (stage / "ci-input.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        # No other contents and no release.json, including after the build.
        if {item.name for item in stage.iterdir()} != {filename, "ci-input.json"}:
            raise ValueError("CI compiler created unexpected files")
        if output.exists() or output.is_symlink():
            raise ValueError("CI test output appeared during compilation")
        # os.rename on the same runner temp volume cannot publish half a record.
        stage.rename(output)
        return record


def verify(candidate: Path, identity: dict[str, str]) -> Path:
    """Return direct binary path for an allowed test; never make an installation."""
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ValueError("CI input must be an independent absolute directory")
    info = candidate.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("CI test candidate is not an ordinary directory")
    filename = _filename(identity["platform"])
    if {item.name for item in candidate.iterdir()} != {"ci-input.json", filename}:
        raise ValueError("CI test input must not contain release or extra files")
    record = json.loads(_regular(candidate / "ci-input.json", MAX_MANIFEST),
                        object_pairs_hook=_unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    binary_path = candidate / filename
    binary = _regular(binary_path, MAX_BINARY)
    if not binary:
        raise ValueError("CI test binary is empty")
    producer_attempt = record.get("producer_attempt") if isinstance(record, dict) else None
    if (not isinstance(producer_attempt, str) or not POSITIVE.fullmatch(producer_attempt)
            or int(producer_attempt) > int(identity["run_attempt"])):
        raise ValueError("CI producer attempt is not valid for this consumer")
    expected = _record({**identity, "run_attempt": producer_attempt}, binary)
    if record != expected:
        raise ValueError("CI test input source, tool, run, flags or bytes mismatch")
    if not identity["platform"].startswith("windows/"):
        binary_path.chmod(0o755)
    return binary_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()
    try:
        identity = ci_identity(args.operation)
        if args.operation == "build":
            print(json.dumps(build(args.candidate, identity, ambient=os.environ),
                             indent=2, sort_keys=True))
        else:
            print("UNQUALIFIED_TEST_BINARY=" + str(verify(args.candidate, identity)))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise SystemExit("CI test input refused: " + str(exc)) from exc


if __name__ == "__main__":
    main()
