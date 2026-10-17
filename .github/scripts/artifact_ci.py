#!/usr/bin/env python3
"""Bind CI consumers to one module-tested native candidate from this run.

These unkeyed records detect accidental cross-run, source, tool or byte swaps;
GitHub's same-run artifact transport and required jobs supply the execution
boundary. They are not release qualification or live-host authority. Only the
existing artifact-engine job may issue the final qualification receipt.
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
from typing import Any, Mapping

from _contextverificationlib import hash_go_module

REPO = Path(__file__).resolve().parents[2]
FORMAT = "codearbiter.ci-native-candidate/1"
WORKFLOW = ".github/workflows/ci.yml"
PRODUCER = "artifact-candidate"
PLATFORMS = frozenset({
    "linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
    "darwin/amd64", "darwin/arm64",
})
REQUIRED_STAGES = frozenset({
    "changes", "artifact-candidate", "artifact-native-default",
    "artifact-native-coverage", "artifact-context", "artifact-bridges",
    "artifact-authority", "artifact-coverage",
})


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Refuse ambiguous duplicate JSON fields instead of taking the last one."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def read_regular(path: Path, limit: int) -> bytes:
    """Read a bounded ordinary file, rejecting links and Windows reparse points."""
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_size > limit):
        raise ValueError(f"not a bounded regular file: {path.name}")
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError(f"file exceeds its bound: {path.name}")
    return data


def digest(data: bytes) -> str:
    """Return the SHA-256 identity of the actual bytes supplied."""
    return hashlib.sha256(data).hexdigest()


def candidate_identity(candidate: Path, platform: str) -> dict[str, str]:
    """Require one genuinely module-tested native manifest and its exact binary."""
    if platform not in PLATFORMS:
        raise ValueError("unsupported native platform")
    info = candidate.lstat()
    if (not stat.S_ISDIR(info.st_mode) or candidate.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("candidate directory must not be a link")
    raw = read_regular(candidate / "release.json", 65536)
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"format", "version", "protocol", "schema_version", "binaries"}
            or manifest["format"] != "codearbiter.artifact-release/0.1.0"
            or manifest["version"] != "0.1.0"
            or manifest["protocol"] != "codearbiter.artifact-api/0.1.0"
            or manifest["schema_version"] != "0.3.2"
            or not isinstance(manifest["binaries"], dict)
            or set(manifest["binaries"]) != {platform}):
        raise ValueError("candidate manifest has unexpected identity")
    entry = manifest["binaries"][platform]
    filename = "ca-artifact-" + platform.replace("/", "-")
    if platform.startswith("windows/"):
        filename += ".exe"
    if (not isinstance(entry, dict) or set(entry) != {"file", "sha256", "native_tested"}
            or entry["file"] != filename or entry["native_tested"] is not True):
        raise ValueError("candidate must be native and module-tested, not a skip-tests build")
    actual = digest(read_regular(candidate / filename, 128 * 1024 * 1024))
    if actual != entry["sha256"]:
        raise ValueError("candidate binary digest mismatch")
    return {"manifest_sha256": digest(raw), "binary_sha256": actual}


def ci_identity(platform: str, environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Bind the checkout, native Go executable and run attempt before consumption."""
    env = os.environ if environment is None else environment
    source = env.get("GITHUB_SHA", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    repository = env.get("GITHUB_REPOSITORY", "")
    if (env.get("GITHUB_ACTIONS") != "true"
            or repository != "arbiterForge/codeArbiter"
            or not re.fullmatch(r"[0-9a-f]{40}", source)
            or not re.fullmatch(r"[1-9][0-9]*", run_id)
            or not re.fullmatch(r"[1-9][0-9]*", attempt)
            or not env.get("GITHUB_WORKFLOW_REF", "").startswith(repository + "/" + WORKFLOW + "@")
            or platform not in PLATFORMS):
        raise ValueError("missing exact native CI run identity")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8",
    ).strip()
    if actual != source:
        raise ValueError("CI source differs from checked-out commit")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=REPO,
                   stdout=subprocess.DEVNULL, check=True)
    tool_env = dict(env, GOTOOLCHAIN="local", GOENV="off", GOWORK="off", GOFLAGS="")
    go = json.loads(subprocess.check_output(
        ["go", "env", "-json", "GOOS", "GOARCH", "GOHOSTOS", "GOHOSTARCH", "GOVERSION"],
        cwd=REPO / "core/artifacts", env=tool_env, text=True, encoding="utf-8",
    ))
    if (go["GOOS"] + "/" + go["GOARCH"] != platform
            or go["GOHOSTOS"] + "/" + go["GOHOSTARCH"] != platform
            or go["GOVERSION"] != "go1.27.1"):
        raise ValueError("candidate requires the exact pinned native Go toolchain")
    executable = shutil.which("go")
    if executable is None:
        raise ValueError("Go executable is unavailable")
    return {
        "format": FORMAT, "source_commit": source, "run_id": run_id,
        "run_attempt": attempt, "workflow": WORKFLOW, "producer_job": PRODUCER,
        "platform": platform, "toolchain": go["GOVERSION"],
        "module_sha256": hash_go_module(REPO / "core/artifacts"),
        "go_sha256": digest(read_regular(Path(executable).resolve(strict=True), 128 * 1024 * 1024)),
    }


def stamp(candidate: Path, metadata: Path, platform: str) -> dict[str, str]:
    """Record only the successful builder's candidate; never promote a manifest."""
    if os.environ.get("GITHUB_JOB") != PRODUCER:
        raise ValueError("only the native candidate job may write a CI build binding")
    identity = {**ci_identity(platform), **candidate_identity(candidate, platform)}
    if metadata.is_symlink() or not metadata.parent.is_dir():
        raise ValueError("CI binding needs a new file in an existing directory")
    with metadata.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(identity, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return identity


def verify(candidate: Path, metadata: Path, platform: str) -> dict[str, str]:
    """Reject substituted inputs and restore only the verified binary's execute bit."""
    record = json.loads(read_regular(metadata, 65536), object_pairs_hook=unique_object)
    expected = {**ci_identity(platform), **candidate_identity(candidate, platform)}
    # A failed consumer may reuse a successful producer from an earlier attempt
    # of this same immutable-source run. Never accept another run or a future attempt.
    attempt = record.get("run_attempt") if isinstance(record, dict) else None
    if (not isinstance(attempt, str) or not re.fullmatch(r"[1-9][0-9]*", attempt)
            or int(attempt) > int(expected["run_attempt"])):
        raise ValueError("CI candidate run attempt is invalid")
    expected["run_attempt"] = attempt
    if record != expected:
        raise ValueError("CI candidate source, run, platform, tool or bytes changed")
    if not platform.startswith("windows/"):
        (candidate / ("ca-artifact-" + platform.replace("/", "-"))).chmod(0o755)
    return expected


def require_stages(raw: str) -> None:
    """Fail the final join on missing, skipped, cancelled, failed or pending stages."""
    if len(raw) > 65536:
        raise ValueError("native stage results exceed their bound")
    needs = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(needs, dict) or set(needs) != REQUIRED_STAGES:
        raise ValueError("native qualification needs every declared stage exactly once")
    failures = [key for key, value in needs.items()
                if not isinstance(value, dict) or value.get("result") != "success"]
    if failures:
        raise ValueError("native qualification lacks successful stages: " + ", ".join(sorted(failures)))
    if needs["changes"].get("outputs", {}).get("artifacts") != "true":
        raise ValueError("native qualification was not selected by the impact planner")


def main() -> None:
    """Execute a binding operation or the strict final-stage join."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stamp", "verify", "gate"))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--platform", choices=sorted(PLATFORMS))
    args = parser.parse_args()
    try:
        if args.operation == "gate":
            if any((args.candidate, args.metadata, args.platform)):
                parser.error("gate takes its required results only from NATIVE_RESULTS")
            require_stages(os.environ.get("NATIVE_RESULTS", ""))
            print("All native verification stages passed; final qualification may proceed.")
        else:
            if args.candidate is None or args.metadata is None or args.platform is None:
                parser.error("candidate operations require --candidate, --metadata and --platform")
            result = (stamp if args.operation == "stamp" else verify)(
                args.candidate.absolute(), args.metadata.absolute(), args.platform,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"native CI input refused: {error}") from error


if __name__ == "__main__":
    main()
