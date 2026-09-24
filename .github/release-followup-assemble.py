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
FINAL_CHANGES = [{'path': 'core/surface/skills/release/SKILL.md', 'before': '71a89c2f78b427bc46e85356a7077bbecc36ccce', 'after': '18df7c539108ab108bd90db9d4969c0af6f817f6', 'size': 133479, 'mode': '100644'}, {'path': '.github/scripts/test_release_lib.py', 'before': '2c481bb0ac1257a3a668101ff40b62ab9f04a7b1', 'after': '6fb766f7a6acf4558e21db255f621cdb9fd41423', 'size': 575034, 'mode': '100644'}, {'path': '.github/scripts/test_consumer_smoke.py', 'before': 'd348554a1119f385a301e09c29417d7a6cdd9f49', 'after': '5ef66bf2e71cce2ecd1f9a8856107a0a6aeb889e', 'size': 238894, 'mode': '100644'}, {'path': 'plugins/ca/skills/release/SKILL.md', 'before': 'cff834cb76e7481f30de2dfecc0dbaed6e278ba1', 'after': '3de387c2a1dc85d9e4bfb18b2f9093d5d5dc1efc', 'size': 133758, 'mode': '100644'}, {'path': 'plugins/ca-codex/routines/release/SKILL.md', 'before': '923f3b981eebd408f8a49bd82c6635bc9932a14f', 'after': '5845ce70a7cf8d8c8d9479729043728fbe38f93d', 'size': 133134, 'mode': '100644'}, {'path': 'plugins/ca-pi/routines/release/SKILL.md', 'before': 'a2ba36d888ee59d60ade6af8433d263ab8d4af66', 'after': '26405a9ba51b50b7c8ed33076e67b47969ba63d5', 'size': 132974, 'mode': '100644'}, {'path': 'plugins/ca/hooks/tests/test_release_workflow_followup.py', 'before': None, 'after': '1e9613f7d6be0904d3749cae3f68849f81db4d1c', 'size': 20767, 'mode': '100644'}]
ALLOWED = {entry["path"] for entry in FINAL_CHANGES}
ADJUSTMENT_SHA256 = 'bc617767025f39245188adf4cfd1bd346ebc6cad228232bfa67f8e961b17212b'
ADJUSTMENT_GZIP_BASE64 = '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'


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
    # The original transfer is hash-pinned above. This reviewed correction
    # replaces stale test anchors and accurately labels partial fixtures.
    transfer["changes"] = FINAL_CHANGES
    if len(ALLOWED) != len(FINAL_CHANGES):
        raise RuntimeError("Duplicate final path")
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
        adjustment = gzip.decompress(base64.b64decode(ADJUSTMENT_GZIP_BASE64, validate=True))
        if len(adjustment) > 1000000 or hashlib.sha256(adjustment).hexdigest() != ADJUSTMENT_SHA256:
            raise RuntimeError("Adjustment identity mismatch")
        adjustment_path = output / "adjustment.py"
        adjustment_path.write_bytes(adjustment)
        subprocess.run([sys.executable, str(adjustment_path), str(root)], cwd=root, check=True)
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
