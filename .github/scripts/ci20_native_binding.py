#!/usr/bin/env python3
"""Bind a genuinely module-tested candidate to its exact GitHub Actions run.

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
import sys
from typing import Any, Mapping

from _contextverificationlib import hash_go_module

REPO = Path(__file__).resolve().parents[2]
FORMAT = "codearbiter.ci-native-candidate/1"
WORKFLOW = ".github/workflows/ci.yml"
PRODUCER = "artifact-native-build"
PLATFORMS = frozenset({
    "linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
    "darwin/amd64", "darwin/arm64",
})
REQUIRED_STAGES = frozenset({
    "changes",
    "artifact-native-build", "artifact-native-default",
    "artifact-native-coverage",
    "artifact-native-bridges", "artifact-authority",
    "artifact-coverage",
})
CONSUMERS = frozenset({"artifact-native-bridges", "artifact-authority", "artifact-engine"})
# The single receipt issuer runs on Linux and checks each native stamp without
# that platform's host; see docs/plans/ci20-02-candidate-admission.md, CI20-04b.
ISSUER = "artifact-engine"
TOOLCHAIN = "go1.27.1"
RUNNERS = {
    "ubuntu-24.04": "linux/amd64", "ubuntu-24.04-arm": "linux/arm64",
    "windows-2025": "windows/amd64", "windows-11-arm": "windows/arm64",
    "macos-15-intel": "darwin/amd64", "macos-26": "darwin/arm64",
}
RECORD_FIELDS = frozenset({
    "format", "source_commit", "run_id", "run_attempt", "workflow", "producer_job",
    "platform", "toolchain", "module_sha256", "go_sha256", "manifest_sha256",
    "binary_sha256",
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
    if {entry.name for entry in candidate.iterdir()} != {"release.json", filename}:
        raise ValueError("tested candidate has additional or missing files")
    return {"manifest_sha256": digest(raw), "binary_sha256": actual}


def run_identity(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Bind this exact workflow run and its clean checkout; no host claim."""
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
            or not env.get("GITHUB_WORKFLOW_REF", "").startswith(repository + "/" + WORKFLOW + "@refs/")):
        raise ValueError("missing exact native CI run identity")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8",
    ).strip()
    if actual != source:
        raise ValueError("CI source differs from checked-out commit")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=REPO,
                   stdout=subprocess.DEVNULL, check=True)
    return {"source_commit": source, "run_id": run_id, "run_attempt": attempt}


def ci_identity(platform: str, environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Bind the checkout, native Go executable and run attempt before consumption."""
    env = os.environ if environment is None else environment
    if platform not in PLATFORMS:
        raise ValueError("missing exact native CI run identity")
    run = run_identity(env)
    source, run_id, attempt = run["source_commit"], run["run_id"], run["run_attempt"]
    tool_env = dict(env, GOTOOLCHAIN="local", GOENV="off", GOWORK="off", GOFLAGS="")
    go = json.loads(subprocess.check_output(
        ["go", "env", "-json", "GOOS", "GOARCH", "GOHOSTOS", "GOHOSTARCH", "GOVERSION"],
        cwd=REPO / "core/artifacts", env=tool_env, text=True, encoding="utf-8",
    ))
    if (go["GOOS"] + "/" + go["GOARCH"] != platform
            or go["GOHOSTOS"] + "/" + go["GOHOSTARCH"] != platform
            or go["GOVERSION"] != TOOLCHAIN):
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
        raise ValueError("only the tested native builder may create its source binding")
    identity = {**ci_identity(platform), **candidate_identity(candidate, platform)}
    if metadata.is_symlink() or not metadata.parent.is_dir():
        raise ValueError("CI binding needs a new file in an existing directory")
    with metadata.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(identity, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return identity


def verify(candidate: Path, metadata: Path, platform: str) -> dict[str, str]:
    """Reject substituted inputs and restore only the verified binary's execute bit."""
    if os.environ.get("GITHUB_JOB") not in CONSUMERS:
        raise ValueError("only declared native CI consumers may verify a tested input")
    record = json.loads(read_regular(metadata, 65536), object_pairs_hook=unique_object)
    expected = {**ci_identity(platform), **candidate_identity(candidate, platform)}
    # A failed consumer may reuse a successful producer from an earlier attempt
    # of this same immutable-source run. Never accept another run or a future attempt.
    expected["run_attempt"] = _attempt_not_later(record, expected["run_attempt"])
    if record != expected:
        raise ValueError("CI candidate source, run, platform, tool or bytes changed")
    if not platform.startswith("windows/"):
        (candidate / ("ca-artifact-" + platform.replace("/", "-"))).chmod(0o755)
    return expected


def _attempt_not_later(record: Any, current: str) -> str:
    """A retry may reuse an earlier successful producer, never a future one."""
    attempt = record.get("run_attempt") if isinstance(record, dict) else None
    if (not isinstance(attempt, str) or not re.fullmatch(r"[1-9][0-9]*", attempt)
            or int(attempt) > int(current)):
        raise ValueError("CI candidate run attempt is invalid")
    return attempt


def recorded(candidate: Path, metadata: Path, platform: str,
             environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Check a native builder's stamp off-host, for the single receipt issuer.

    The native consumers already verified this stamp against their own host,
    Go executable and checkout. The issuer re-binds everything that does not
    need that host: run, source, module, platform, toolchain and bytes."""
    env = os.environ if environment is None else environment
    if env.get("GITHUB_JOB") != ISSUER:
        raise ValueError("only the final issuer may check a recorded native binding")
    run = run_identity(env)
    record = json.loads(read_regular(metadata, 65536), object_pairs_hook=unique_object)
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
        raise ValueError("recorded native binding has unexpected fields")
    _attempt_not_later(record, run["run_attempt"])
    expected = {
        "format": FORMAT, "source_commit": run["source_commit"], "run_id": run["run_id"],
        "workflow": WORKFLOW, "producer_job": PRODUCER, "platform": platform,
        "toolchain": TOOLCHAIN, "module_sha256": hash_go_module(REPO / "core/artifacts"),
        **candidate_identity(candidate, platform),
    }
    changed = sorted(field for field, value in expected.items() if record[field] != value)
    if changed:
        raise ValueError("recorded native binding differs: " + ", ".join(changed))
    if not isinstance(record["go_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["go_sha256"]):
        raise ValueError("recorded native binding lacks the native Go executable digest")
    return record


def qualify_recorded(root: Path, environment: Mapping[str, str] | None = None) -> list[Path]:
    """Issue all six receipts from exactly one tested and one context record per runner."""
    env = dict(os.environ if environment is None else environment)
    if env.get("GITHUB_JOB") != ISSUER:
        raise ValueError("only the final issuer may qualify recorded native results")
    expected = {f"ci20-native-{kind}-{runner}" for runner in RUNNERS for kind in ("tested", "context")}
    present = {entry.name for entry in root.iterdir()}
    if present != expected:
        raise ValueError("native records are missing or unexpected: "
                         + ", ".join(sorted(present ^ expected)))
    receipts = []
    for runner, platform in sorted(RUNNERS.items()):
        tested = root / f"ci20-native-tested-{runner}"
        receipt = tested / "artifact-qualification.json"
        subprocess.run([
            sys.executable, str(REPO / "tools/build-artifacts.py"),
            "--qualify-existing", str(tested / "artifact-candidate"),
            "--native-binding", str(tested / "ci20-native-tested.json"),
            "--qualification-output", str(receipt),
            "--context-native-observation",
            str(root / f"ci20-native-context-{runner}" / "context-native-observation.json"),
        ], cwd=REPO, env={**env, "EXPECTED_ARTIFACT_PLATFORM": platform}, check=True)
        receipts.append(receipt)
    return receipts


def require_stages(raw: str) -> None:
    """Reject missing, cancelled, skipped, pending and failed required groups."""
    if len(raw) > 65536:
        raise ValueError("native result closure exceeds its bound")
    needs = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(needs, dict) or set(needs) != REQUIRED_STAGES:
        raise ValueError("native qualification needs every required stage exactly once")
    failed = [name for name, status in needs.items()
              if not isinstance(status, dict) or status.get("result") != "success"]
    if failed:
        raise ValueError("native qualification requires successful stages: " + ", ".join(sorted(failed)))
    if needs["changes"].get("outputs", {}).get("artifacts") != "true":
        raise ValueError("native artifact verification was not selected")


def main() -> None:
    """Execute a binding operation or the strict final-stage join."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stamp", "verify", "gate", "qualify-recorded"))
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
        elif args.operation == "qualify-recorded":
            if any((args.candidate, args.metadata, args.platform)):
                parser.error("qualify-recorded reads its records only from NATIVE_ROOT")
            root = os.environ.get("NATIVE_ROOT", "")
            if not root:
                raise ValueError("NATIVE_ROOT is unset")
            for receipt in qualify_recorded(Path(root).absolute()):
                print(f"qualified {receipt.parent.name}: {receipt}")
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
