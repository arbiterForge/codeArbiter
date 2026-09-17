#!/usr/bin/env python3
"""Build this standalone module offline. No host payload is enabled by a build."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

QUALIFICATION_FORMAT = "codearbiter.artifact-qualification/0.1.0"
QUALIFICATION_WORKFLOW = ".github/workflows/ci.yml"
QUALIFICATION_JOB = "artifact-engine"
NATIVE_TESTS = [
    "artifact-bridge", "artifact-conformance", "artifact-native", "artifact-package",
    "go-test", "go-vet",
]


def write_qualification(candidate: Path, destination: Path) -> None:
    """Emit the exact-host receipt only inside the protected CI matrix job."""
    source_commit = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_JOB") != QUALIFICATION_JOB
            or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
            or not re.fullmatch(r"[1-9][0-9]*", run_id)
            or f"/{QUALIFICATION_WORKFLOW}@" not in workflow_ref):
        raise SystemExit("native qualification receipts are emitted only by the protected exact-host CI job")
    repo = Path(__file__).resolve().parents[1]
    actual_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, encoding="utf-8"
    ).strip()
    if actual_commit != source_commit:
        raise SystemExit("qualification source commit does not match the checked-out tree")
    manifest_path = candidate / "release.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("format") != QUALIFICATION_FORMAT.replace(
            "qualification", "release") or manifest.get("version") != "0.1.0"
            or manifest.get("protocol") != "codearbiter.artifact-api/0.1.0"
            or manifest.get("schema_version") != "0.3.1"):
        raise SystemExit("candidate identity is not eligible for native qualification")
    entries = manifest.get("binaries")
    if not isinstance(entries, dict) or len(entries) != 1:
        raise SystemExit("qualification requires exactly one native candidate")
    platform_name, entry = next(iter(entries.items()))
    goos = subprocess.check_output(["go", "env", "GOOS"], text=True).strip()
    goarch = subprocess.check_output(["go", "env", "GOARCH"], text=True).strip()
    if platform_name != f"{goos}/{goarch}" or entry.get("native_tested") is not True:
        raise SystemExit("candidate platform does not match the exact host")
    binary = candidate / entry["file"]
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != entry.get("sha256"):
        raise SystemExit("candidate digest changed before qualification")
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise SystemExit("qualification output must be a new file in an existing directory")
    receipt = {
        "format": QUALIFICATION_FORMAT,
        "source_commit": source_commit,
        "workflow": QUALIFICATION_WORKFLOW,
        "run_id": run_id,
        "job": QUALIFICATION_JOB,
        "platform": platform_name,
        "binary_sha256": digest,
        "version": manifest["version"],
        "protocol": manifest["protocol"],
        "schema_version": manifest["schema_version"],
        "native_tests": NATIVE_TESTS,
    }
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-tests", action="store_true", help="development only; marks binary unqualified")
    parser.add_argument("--qualify-existing", type=Path)
    parser.add_argument("--qualification-output", type=Path)
    args = parser.parse_args()
    if args.qualify_existing is not None or args.qualification_output is not None:
        if args.output is not None or args.skip_tests or args.qualify_existing is None or args.qualification_output is None:
            parser.error("qualification mode requires --qualify-existing and --qualification-output only")
        write_qualification(args.qualify_existing.resolve(strict=True),
                            args.qualification_output.absolute())
        print(json.dumps({"qualification": str(args.qualification_output.absolute())}, indent=2))
        return
    if args.output is None:
        parser.error("--output is required when building a candidate")
    repo = Path(__file__).resolve().parents[1]
    module = repo / "core/artifacts"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", CGO_ENABLED="0")
    goos = subprocess.check_output(["go", "env", "GOOS"], env=env, text=True).strip()
    goarch = subprocess.check_output(["go", "env", "GOARCH"], env=env, text=True).strip()
    if goos not in {"linux", "darwin", "windows"}:
        raise SystemExit("No qualified native repository backend exists for this platform.")
    native_os = platform.system().lower()
    native_arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if not args.skip_tests and (goos, goarch) != (native_os, native_arch):
        raise SystemExit("Native qualification requires the actual host target; unset cross-build GOOS/GOARCH or use --skip-tests.")
    if not args.skip_tests:
        subprocess.run(["go", "test", "./...", "-count=1"], cwd=module, env=env, check=True)
        subprocess.run(["go", "vet", "./..."], cwd=module, env=env, check=True)
    name = f"ca-artifact-{goos}-{goarch}" + (".exe" if goos == "windows" else "")
    subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-ldflags=-s -w", "-o", str(output/name), "./cmd/ca-artifact"], cwd=module, env=env, check=True)
    executable = output/name
    if goos != "windows":
        executable.chmod(0o755)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    manifest = {"format":"codearbiter.artifact-release/0.1.0", "version":"0.1.0", "protocol":"codearbiter.artifact-api/0.1.0", "schema_version":"0.3.1", "binaries":{f"{goos}/{goarch}":{"file":name,"sha256":digest,"native_tested":not args.skip_tests}}}
    (output/"release.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"binary":str(executable),"sha256":digest,"toolchain":subprocess.check_output(["go","version"],text=True).strip(),"platform":platform.platform(),"module_tests_passed":not args.skip_tests,"upstream_host_qualified":False},indent=2))

if __name__ == "__main__":
    main()
