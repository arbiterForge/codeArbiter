#!/usr/bin/env python3
"""Apply an exact reviewed patch; verify it; store Git objects, never refs."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

REPOSITORY = "arbiterForge/codeArbiter"
BASE = "75b4d442ea42bdd19241608647419a390e1ee360"
BASE_TREE = "337d35be047c5ac699e8ab6d7c05cf7ccd561865"
ALLOWED = {
    "core/surface/skills/release/SKILL.md",
    "plugins/ca/skills/release/SKILL.md",
    "plugins/ca-codex/routines/release/SKILL.md",
    "plugins/ca-pi/routines/release/SKILL.md",
    "plugins/ca/hooks/tests/test_release_workflow_followup.py",
}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def verify_files(root, transfer):
    actual = set(git(root, "diff", "--name-only").splitlines())
    actual.update(git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    if actual != ALLOWED:
        raise RuntimeError(f"Unexpected candidate paths: {sorted(actual ^ ALLOWED)}")
    for entry in transfer["changes"]:
        path = root / entry["path"]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Not a regular file: {entry['path']}")
        data = path.read_bytes()
        if blob(data) != entry["after"] or len(data) != entry["size"]:
            raise RuntimeError(f"Candidate byte mismatch: {entry['path']}")
        if b"\r" in data:
            raise RuntimeError(f"Non-LF candidate: {entry['path']}")


def request(endpoint, payload):
    if endpoint not in ("blobs", "trees"):
        raise RuntimeError("Only unreferenced Git blobs and trees may be written")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/git/{endpoint}",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main():
    mode, root_arg, transfer_arg, output_arg = sys.argv[1:]
    root, transfer_path, output = map(Path, (root_arg, transfer_arg, output_arg))
    output.mkdir(parents=True, exist_ok=True)
    raw = transfer_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != os.environ["TRANSFER_SHA256"]:
        raise RuntimeError("Transfer identity mismatch")
    transfer = json.loads(raw)
    if (transfer["repository"], transfer["base_commit"], transfer["base_tree"]) != (REPOSITORY, BASE, BASE_TREE):
        raise RuntimeError("Repository or base mismatch")
    if {e["path"] for e in transfer["changes"]} != ALLOWED:
        raise RuntimeError("Transfer scope mismatch")
    if git(root, "rev-parse", "HEAD") != BASE or git(root, "rev-parse", "HEAD^{tree}") != BASE_TREE:
        raise RuntimeError("Checkout is not the inspected base")
    if mode == "verify":
        if git(root, "status", "--porcelain"):
            raise RuntimeError("Baseline is not clean")
        for entry in transfer["changes"]:
            path = root / entry["path"]
            if entry["before"] is None:
                if path.exists():
                    raise RuntimeError("New path already exists")
            elif blob(path.read_bytes()) != entry["before"]:
                raise RuntimeError(f"Baseline blob mismatch: {entry['path']}")
        patch = gzip.decompress(base64.b64decode(transfer["patch_gzip_base64"], validate=True))
        if len(patch) > 1000000 or hashlib.sha256(patch).hexdigest() != transfer["patch_sha256"]:
            raise RuntimeError("Patch identity mismatch")
        patch_path = output / "candidate.patch"
        patch_path.write_bytes(patch)
        subprocess.run(["git", "apply", "--check", str(patch_path)], cwd=root, check=True)
        subprocess.run(["git", "apply", str(patch_path)], cwd=root, check=True)
        subprocess.run([sys.executable, "tools/build-surface.py"], cwd=root, check=True)
        verify_files(root, transfer)
        commands = [
            [sys.executable, "-m", "unittest", "discover", "-s", "plugins/ca/hooks/tests", "-p", "test_release_workflow_followup.py", "-v"],
            [sys.executable, ".github/scripts/test_release_lib.py"],
            [sys.executable, ".github/scripts/test_consumer_smoke.py"],
            [sys.executable, ".github/scripts/test_release_workflow.py"],
            [sys.executable, ".github/scripts/test_payload_version_gate.py"],
            [sys.executable, ".github/scripts/test_release_trace.py"],
            [sys.executable, "tools/sync-core.py", "--check"],
            [sys.executable, "tools/build-surface.py", "--check"],
            [sys.executable, "tools/build-host-packages.py", "--check"],
            ["git", "diff", "--check"],
        ]
        results = []
        for index, command in enumerate(commands):
            with (output / f"check-{index:02d}.log").open("w") as log:
                run = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            results.append({"command": command, "exit_code": run.returncode, "log": f"check-{index:02d}.log"})
            print(json.dumps(results[-1]), flush=True)
        # Inspection only: stale independent proof is reported, never rewritten.
        with (output / "skill-proof.log").open("w") as log:
            proof = subprocess.run([sys.executable, ".github/scripts/check_skill_proof_fresh.py"], cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        result = {"base": BASE, "changes": transfer["changes"], "checks": results,
                  "independent_skill_proof_exit": proof.returncode,
                  "qualification": "Source checks only; no merge, publication, or independent agent exercise"}
        (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
        verify_files(root, transfer)
        if any(r["exit_code"] for r in results):
            raise RuntimeError("A required candidate check failed; no Git objects may be uploaded")
    elif mode == "store":
        result = json.loads((output / "results.json").read_text())
        if result["base"] != BASE or any(r["exit_code"] for r in result["checks"]):
            raise RuntimeError("Candidate has no passing source-check record")
        verify_files(root, transfer)
        elements = []
        for entry in transfer["changes"]:
            data = (root / entry["path"]).read_text()
            remote = request("blobs", {"content": data, "encoding": "utf-8"})
            if remote["sha"] != entry["after"]:
                raise RuntimeError("Uploaded blob identity mismatch")
            elements.append({"path": entry["path"], "mode": entry["mode"], "type": "blob", "sha": remote["sha"]})
        subprocess.run(["git", "add", "--", *sorted(ALLOWED)], cwd=root, check=True)
        expected_tree = git(root, "write-tree")
        remote_tree = request("trees", {"base_tree": BASE_TREE, "tree": elements})
        if remote_tree["sha"] != expected_tree:
            raise RuntimeError("Remote preserving tree differs from verified local index")
        result["tree_sha"] = expected_tree
        result["git_refs_modified"] = False
        (output / "objects.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"VERIFIED_UNREFERENCED_TREE={expected_tree}", flush=True)
    else:
        raise RuntimeError("Unknown operation")


if __name__ == "__main__":
    main()
