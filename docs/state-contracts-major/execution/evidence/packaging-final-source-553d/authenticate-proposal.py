"""Prospective metadata overlay only; source bytes always come from real Git."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
EPOCH = "553d07fefa2195ee1f137be2b452981a330ce54f"
PREFIX = "docs/state-contracts-major/execution/evidence/packaging-final-source-553d/"


def main():
    home = ROOT / "private-home"
    home.mkdir(exist_ok=True)
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        os.environ[key] = str(home)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(REPO / ".github/scripts"))
    owner_path = REPO / ".github/scripts/major_readiness.py"
    spec = importlib.util.spec_from_file_location("packaging_proposal_owner", owner_path)
    owner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = owner
    spec.loader.exec_module(owner)
    proposal = json.loads((ROOT / "cas-proposal.json").read_bytes())
    frozen = json.loads((ROOT / "working-data.json").read_bytes())
    overlay = {}
    for path in [ROOT / "raw/inspection.json", ROOT / "raw/source-joins.json", *sorted((ROOT / "proofs").glob("*.json"))]:
        overlay[PREFIX + path.relative_to(ROOT).as_posix()] = path.read_bytes()
    loaded = {}
    overlay_reads = set()

    def load(commit, path):
        if path in overlay:
            assert commit == EPOCH
            overlay_reads.add(path)
            return overlay[path]
        key = (commit, path)
        if key not in loaded:
            loaded[key] = subprocess.check_output(
                ["git", "--no-lazy-fetch", "show", commit + ":" + path], cwd=REPO)
        return loaded[key]

    started = time.monotonic()
    cache = {}
    results = []
    current = json.loads((REPO / proposal["ledger_path"]).read_bytes())
    for update in proposal["updates"]:
        table, identity = update["table"], update["id"]
        # Exact current row CAS, independently of other concurrent metadata.
        before = current[table][identity]
        encoded = json.dumps(before, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == update["old_row_sha256"]
        if table == "transitions":
            paths = {item["path"] for item in frozen["transitions"][identity]["baseline"]["source"]}
        else:
            paths = {ref.split(":", 1)[1] for ref in frozen["machines"][identity]["source_refs"]}
        cell = "disposition:" + table + ":" + identity
        bound = owner.authenticate_disposition(REPO, EPOCH, cell, update["proposed_row"], paths, load, cache)
        results.append({"cell": cell, "state": "PASSED_PROSPECTIVE_OWNER_VALIDATION", "bound": bound})
    # No source exposure changed while the proposal was read/validated.
    joins = json.loads((ROOT / "raw/source-joins.json").read_bytes())["inputs"]
    assert all(hashlib.sha256((REPO / path).read_bytes()).hexdigest() == record["git_sha256"]
               for path, record in joins.items())
    report = {
        "format": "prospective-disposition-owner-validation/1",
        "source_commit": EPOCH,
        "owner": str(owner_path),
        "owner_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest(),
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "elapsed_seconds": time.monotonic() - started,
        "results": results,
        "new_metadata_overlay_paths": sorted(overlay_reads),
        "committed_source_and_existing_evidence_reads": len(loaded),
        "literal_source_physical_join_after": True,
        "limits": [
            "The explicit new-proof/raw path overlay is prospective metadata, not files already committed at553d.",
            "All source/old evidence reads are actual immutable Git blobs; there is no missing-object fallback.",
            "No runtime test, artifact fetch, publication or installed effect is executed or qualified.",
            "Root must retain/admit and bind the eventual actual metadata commit; this is not final retained-history authentication.",
        ],
    }
    (ROOT / "raw/owner-authentication.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "PASSED_PROSPECTIVE_OWNER_VALIDATION", "cells": len(results), "actual_blob_reads": len(loaded)}))


if __name__ == "__main__":
    main()
