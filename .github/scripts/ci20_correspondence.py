#!/usr/bin/env python3
"""Cross-check all six early CI test binaries against fully native-tested bytes.

This is a read-only correspondence observation, NOT native qualification.
Existing strict native/host package verification remains authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

import ci20_candidate
from _contextverificationlib import hash_go_module

REPO = Path(__file__).resolve().parents[2]
FORMAT = "codearbiter.ci20-byte-correspondence/1"
PLATFORM_RUNNERS = {
    "ubuntu-24.04": "linux/amd64",
    "ubuntu-24.04-arm": "linux/arm64",
    "windows-2025": "windows/amd64",
    "windows-11-arm": "windows/arm64",
    "macos-15-intel": "darwin/amd64",
    "macos-26": "darwin/arm64",
}
RELEASE_FORMAT = "codearbiter.artifact-release/0.1.0"
RECEIPT_FORMAT = "codearbiter.artifact-qualification/0.1.0"
PROTOCOL = "codearbiter.artifact-api/0.1.0"
SCHEMA = "0.3.2"
VERSION = "0.1.0"
EXPECTED_JOB = "artifact-engine"
EXPECTED_NATIVE_TESTS = [
    "artifact-bridge", "artifact-conformance", "artifact-native",
    "artifact-package", "go-test", "go-vet",
]


def _read(path: Path, max_bytes: int) -> bytes:
    """Read only bounded, ordinary files, rejecting symlinks and reparse points."""
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_size > max_bytes):
        raise ValueError("correspondence input must be a bounded ordinary file")
    result = path.read_bytes()
    if len(result) > max_bytes:
        raise ValueError("correspondence input exceeds its byte budget")
    return result


def _directory(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("correspondence input directory cannot be a link")


def _json(path: Path) -> dict:
    record = json.loads(_read(path, 65_536), object_pairs_hook=ci20_candidate._unique,
                        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    if not isinstance(record, dict):
        raise ValueError("correspondence record must be an object")
    return record


def identity(ambient: Mapping[str, str]) -> dict[str, str]:
    """Require exactly the package assembly job from this GitHub run."""
    sha = ambient.get("GITHUB_SHA", "")
    run = ambient.get("GITHUB_RUN_ID", "")
    attempt = ambient.get("GITHUB_RUN_ATTEMPT", "")
    workflow_ref = ambient.get("GITHUB_WORKFLOW_REF", "")
    if (ambient.get("GITHUB_ACTIONS") != "true"
            or ambient.get("GITHUB_REPOSITORY") != ci20_candidate.REPOSITORY
            or ambient.get("GITHUB_JOB") != "artifact-package-assembly"
            or not ci20_candidate.COMMIT.fullmatch(sha)
            or not ci20_candidate.POSITIVE.fullmatch(run)
            or not ci20_candidate.POSITIVE.fullmatch(attempt)
            or not workflow_ref.startswith(
                ci20_candidate.REPOSITORY + "/" + ci20_candidate.WORKFLOW + "@refs/")):
        raise ValueError("correspondence requires this run's authorized package assembly job")
    checkout = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8",
    ).strip()
    if checkout != sha:
        raise ValueError("correspondence checkout/source mismatch")
    return {"source_commit": sha, "run_id": run, "run_attempt": attempt,
            "workflow_ref": workflow_ref}


def compare(early_root: Path, qualified_root: Path, binding: dict[str, str],
            module_sha256: str) -> dict[str, Any]:
    """Refuse any missing, extra, mismatched, cross-run, or untested native bytes."""
    if (not early_root.is_absolute() or not qualified_root.is_absolute()
            or early_root == qualified_root):
        raise ValueError("candidate cohorts must be separate absolute directories")
    _directory(early_root)
    _directory(qualified_root)
    expected_early = {"ci20-test-input-" + name for name in PLATFORM_RUNNERS}
    expected_qualified = {"artifact-native-" + name for name in PLATFORM_RUNNERS}
    if ({p.name for p in early_root.iterdir()} != expected_early
            or {p.name for p in qualified_root.iterdir()} != expected_qualified):
        raise ValueError("correspondence requires all six and only six native platforms")
    records = []
    for runner, platform in PLATFORM_RUNNERS.items():
        early = early_root / ("ci20-test-input-" + runner)
        qualified = qualified_root / ("artifact-native-" + runner)
        _directory(early)
        _directory(qualified)
        candidate = qualified / "artifact-candidate"
        _directory(candidate)
        filename = ci20_candidate._filename(platform)
        if ({p.name for p in early.iterdir()} != {filename, "ci-input.json"}
                or {p.name for p in candidate.iterdir()} != {filename, "release.json"}
                or {p.name for p in qualified.iterdir()} != {
                    "artifact-candidate", "artifact-qualification.json"}):
            raise ValueError("correspondence cohort contains missing or unexpected files")
        early_bytes = _read(early / filename, ci20_candidate.MAX_BINARY)
        native_bytes = _read(candidate / filename, ci20_candidate.MAX_BINARY)
        if not early_bytes or not native_bytes or early_bytes != native_bytes:
            raise ValueError("unqualified CI test binary differs from fully tested candidate")
        early_metadata = _json(early / "ci-input.json")
        attempt = early_metadata.get("producer_attempt")
        go_sha = early_metadata.get("go_sha256")
        if (not isinstance(attempt, str)
                or not ci20_candidate.POSITIVE.fullmatch(attempt)
                or int(attempt) > int(binding["run_attempt"])
                or not isinstance(go_sha, str)
                or not ci20_candidate.HEX.fullmatch(go_sha)):
            raise ValueError("provisional producer/tool identity is invalid")
        expected_identity = {
            "source_commit": binding["source_commit"],
            "run_id": binding["run_id"],
            "run_attempt": attempt,
            "workflow_ref": binding["workflow_ref"],
            "platform": platform,
            "go_version": ci20_candidate.GO_VERSION,
            "go_sha256": go_sha,
            "module_sha256": module_sha256,
        }
        if early_metadata != ci20_candidate._record(expected_identity, early_bytes):
            raise ValueError("provisional CI input has wrong source, flags or digest")
        manifest = _json(candidate / "release.json")
        expected_release = {
            "format": RELEASE_FORMAT, "version": VERSION,
            "protocol": PROTOCOL, "schema_version": SCHEMA,
            "binaries": {platform: {
                "file": filename,
                "sha256": hashlib.sha256(native_bytes).hexdigest(),
                "native_tested": True,
            }},
        }
        if manifest != expected_release:
            raise ValueError("fully tested native manifest disagrees with candidate")
        receipt = _json(qualified / "artifact-qualification.json")
        receipt_identity = {
            "format": RECEIPT_FORMAT,
            "source_commit": binding["source_commit"],
            "workflow": ci20_candidate.WORKFLOW,
            "run_id": binding["run_id"],
            "job": EXPECTED_JOB,
            "platform": platform,
            "binary_sha256": hashlib.sha256(native_bytes).hexdigest(),
            "version": VERSION, "protocol": PROTOCOL, "schema_version": SCHEMA,
            "native_tests": EXPECTED_NATIVE_TESTS,
        }
        context = receipt.get("context_native")
        if (not isinstance(context, dict) or set(context) != {
                "format", "module_sha256", "go_sha256", "cases"}
                or context["format"] != "codearbiter.context-native-observation/0.1.0"
                or context["module_sha256"] != module_sha256
                or context["go_sha256"] != go_sha
                or not isinstance(context["cases"], list) or len(context["cases"]) != 6):
            raise ValueError("native context evidence/source/tool differs from early build")
        if receipt != {**receipt_identity, "context_native": context}:
            raise ValueError("native-tested qualification receipt changed identity")
        records.append({
            "platform": platform, "runner": runner,
            "binary_sha256": hashlib.sha256(native_bytes).hexdigest(),
            "early_manifest_sha256": hashlib.sha256(
                _read(early / "ci-input.json", 65_536)).hexdigest(),
            "release_manifest_sha256": hashlib.sha256(
                _read(candidate / "release.json", 65_536)).hexdigest(),
            "qualification_receipt_sha256": hashlib.sha256(
                _read(qualified / "artifact-qualification.json", 65_536)).hexdigest(),
            "producer_attempt": attempt,
        })
    return {
        "format": FORMAT,
        "state": "ci-only-byte-equivalence-observation",
        "source_commit": binding["source_commit"],
        "run_id": binding["run_id"],
        "run_attempt": binding["run_attempt"],
        "module_sha256": module_sha256,
        "native_platforms": records,
        "qualified_by_this_check": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--early-root", required=True, type=Path)
    parser.add_argument("--qualified-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        binding = identity(os.environ)
        module = hash_go_module(REPO / "core/artifacts")
        result = compare(args.early_root.absolute(), args.qualified_root.absolute(),
                         binding, module)
        if not args.report.is_absolute() or not args.report.parent.is_dir():
            raise ValueError("correspondence report parent is not an absolute directory")
        with args.report.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(result, target, indent=2, sort_keys=True)
            target.write("\n")
        print("CI20_CORRESPONDENCE_6_OF_6", module,
              "observation only; existing package verification remains required")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit("CI20 correspondence refused: " + str(exc)) from exc


if __name__ == "__main__":
    main()
