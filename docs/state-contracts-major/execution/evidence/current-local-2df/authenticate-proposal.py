"""Validate the prospective39-row metadata overlay with the unmodified owner."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
SOURCE = "2df782d48576e72bd01ef303c9f3546f3b620b05"
PREFIX = "docs/state-contracts-major/execution/evidence/current-local-2df/"
GIT = r"C:/Program Files/Git/cmd/git.exe"


def main():
    home = ROOT / "owner-private-home"
    home.mkdir(exist_ok=True)
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        os.environ[name] = str(home)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(REPO / ".github/scripts"))
    owner_path = REPO / ".github/scripts/major_readiness.py"
    spec = importlib.util.spec_from_file_location("current_local_disposition_owner", owner_path)
    owner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = owner
    spec.loader.exec_module(owner)
    source_cache = {}
    overlay = {}
    for path in sorted((ROOT / "proofs").glob("*.json")):
        overlay[PREFIX + path.relative_to(ROOT).as_posix()] = path.read_bytes()
        for raw in json.loads(path.read_bytes())["raw_evidence"]:
            assert raw["path"].startswith(PREFIX)
            relative = raw["path"][len(PREFIX):]
            overlay[raw["path"]] = (ROOT / relative).read_bytes()

    def load(commit, path):
        if path in overlay:
            assert commit == SOURCE
            return overlay[path]
        key = (commit, path)
        if key not in source_cache:
            source_cache[key] = subprocess.check_output(
                [GIT, "--no-lazy-fetch", "show", commit + ":" + path], cwd=REPO)
        return source_cache[key]

    proof = json.loads((ROOT / "cas-proposal.json").read_bytes())
    ledger = json.loads((REPO / proof["ledger_path"]).read_bytes())
    progress = json.loads(load(SOURCE, "docs/state-contracts-major/execution/progress.json"))
    added = {row["transition_id"]: row for row in progress["new_transition_rows"]}
    transitions = {row["transition_id"]: row for row in json.loads(load(
        SOURCE, "docs/state-contracts-major/contracts/transition-coverage.json"))["transitions"]}
    machines = {row["machine_id"]: row for row in json.loads(load(
        SOURCE, "docs/state-contracts-major/contracts/machine-coverage.json"))["machines"]}
    result = []
    cache = {}
    for update in proof["updates"]:
        table, identity = update["table"], update["id"]
        before = ledger[table][identity]
        encoded = json.dumps(before, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == update["old_row_sha256"]
        if table == "transitions":
            paths = {item["path"] for item in transitions[identity]["baseline"]["source"]}
        else:
            row = machines[identity] if table == "machines" else added[identity]
            paths = {ref.split(":", 1)[1] for ref in row["source_refs"]}
        cell = "disposition:" + table + ":" + identity
        bound = owner.authenticate_disposition(REPO, SOURCE, cell, update["proposed_row"], paths, load, cache)
        result.append({"cell": cell, "state": "PASSED_PROSPECTIVE_OWNER_VALIDATION", "bound": bound})
    assert len(result) == 39
    report = {"format": "prospective-current-proof-owner-validation/1", "source_commit": SOURCE,
              "owner": str(owner_path), "owner_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest(),
              "results": result, "source_blob_reads": len(source_cache),
              "new_metadata_overlay_paths": sorted(overlay), "argv": sys.argv, "cwd": os.getcwd(),
              "limits": ["Prospective new metadata overlay only; source and existing records are actual immutable Git blobs.",
                         "No missing-object fallback, reader weakening, API/artifact fetch, fakeCI or source mutation.",
                         "Root must retain files and bind their eventual actual metadata commit before recorded-history admission."]}
    (ROOT / "owner-authentication.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "PASSED_PROSPECTIVE_OWNER_VALIDATION", "cells": len(result),
                      "source_blob_reads": len(source_cache)}))


if __name__ == "__main__":
    main()
