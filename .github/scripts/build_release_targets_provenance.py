#!/usr/bin/env python3
"""Generate `.codearbiter/.provenance/release-targets.json` (A-5.6, T-52).

The declared release-targets file names other files — each `manifest`, each
`changelog`, each `artifacts` entry. Nothing watched whether those files
still existed at the paths the rows claim. A renamed manifest leaves the row
pointing at nothing, and the release lane discovers it at tag time.

This records those paths as provenance drift triggers, so a move surfaces on
the next `/ca:standup` sweep instead of during a release.

WHY NOT A CONTEXT.md-SCOPE TRIGGER. `compute_drift` compares whole-file git
oids and has no section-level machinery. A Scope trigger would fire on an
unrelated `stage:` flip and stay SILENT when a manifest path moves — wrong
in both directions at once. The paths themselves are the honest triggers.

ROUTINE BUMPS TRIP THIS BY DESIGN. Every release edits a manifest and a
changelog, which are exactly the files this watches, so the triggers go
stale on every release. `heal_worklist` re-baselines them in the same
release commit. That is intended, and is written down here so a later
maintainer does not delete the triggers to quiet the noise.

Usage:
    python3 .github/scripts/build_release_targets_provenance.py           # write
    python3 .github/scripts/build_release_targets_provenance.py --check   # verify

`--check` is non-mutating and exits 1 when the record's PATH SET disagrees
with the declared file. It deliberately does NOT compare hashes: those drift
on every release by design, and a check that failed on intended drift would
be turned off within a week.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECORD = REPO / ".codearbiter" / ".provenance" / "release-targets.json"
DECLARED = REPO / ".codearbiter" / "release-targets.md"


def _load(name, relpath):
    # core/pysrc must be on sys.path before exec: `_provenancelib` imports
    # its siblings (`_gitexec`, `_hooklib`) by bare name, the way it does
    # when vendored into a plugin's flat hooks/ directory. Loading it by
    # path alone gets as far as the first sibling import and then fails.
    pysrc = str(REPO / "core" / "pysrc")
    if pysrc not in sys.path:
        sys.path.insert(0, pysrc)
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(root: Path = REPO):
    """The record this repo's declared file implies, with live hashes."""
    releaselib = _load("_rtp_releaselib", "core/pysrc/_releaselib.py")
    provenancelib = _load("_rtp_provenancelib", "core/pysrc/_provenancelib.py")

    rows = releaselib.load_targets(str(root / ".codearbiter" / "release-targets.md"))
    paths = releaselib.provenance_trigger_paths(rows)

    previous_cwd = os.getcwd()
    os.chdir(root)
    try:
        hashes = provenancelib.batch_hash(paths)
    finally:
        os.chdir(previous_cwd)

    entries = []
    for path in paths:
        digest = hashes.get(path)
        if digest is None:
            # A declared path that git does not know is exactly the drift
            # this record exists to surface, so it is recorded with a null
            # hash rather than dropped -- `compute_drift` then reports it
            # as "missing" instead of the row silently losing its trigger.
            entries.append({"path": path, "hash": None, "drift_trigger": True})
            continue
        entries.append({"path": path, "hash": digest, "drift_trigger": True})
    return provenancelib.new_record("release-targets", entries=entries), provenancelib


def declared_paths(root: Path = REPO):
    """Every path the declared release rows make provenance-relevant.

    Derived from the declared file through `provenance_trigger_paths`, never
    listed here: a second hand-maintained copy of "which paths matter" is a
    copy that goes stale the first time a row gains a manifest or an
    artifact, and it would go stale silently, because nothing compares the
    two.
    """
    releaselib = _load("_rtp_releaselib_paths", "core/pysrc/_releaselib.py")
    rows = releaselib.load_targets(str(root / ".codearbiter" / "release-targets.md"))
    return releaselib.provenance_trigger_paths(rows)


def check(root: Path = REPO, record_path: Path = None):
    """Errors (empty means the record's path set matches the declaration)."""
    record_path = record_path or (root / ".codearbiter" / ".provenance"
                                  / "release-targets.json")
    provenancelib = _load("_rtp_provenancelib_check", "core/pysrc/_provenancelib.py")
    record = provenancelib.read_provenance(str(record_path))
    if record is None:
        return [f"missing or unreadable provenance record: {record_path}"]
    if not provenancelib.valid_provenance_record(record):
        return [f"{record_path} is not a well-formed v1 provenance record"]

    recorded = {e.get("path") for e in record.get("entries", [])
                if isinstance(e, dict) and e.get("drift_trigger") is True}
    expected = set(declared_paths(root))
    errors = []
    for path in sorted(expected - recorded):
        errors.append(f"declared but not recorded as a drift trigger: {path}")
    for path in sorted(recorded - expected):
        errors.append(f"recorded as a drift trigger but no longer declared: {path}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify without writing; exit 1 on disagreement")
    arguments = parser.parse_args(argv)

    if arguments.check:
        errors = check()
        if errors:
            print("::error::release-targets provenance disagrees with the "
                  "declared file:")
            for error in errors:
                print("  - " + error)
            return 1
        print("release-targets provenance covers every declared path")
        return 0

    record, provenancelib = build()
    provenancelib.write_provenance(str(RECORD), record)
    print(f"wrote {RECORD.relative_to(REPO)} "
          f"({len(record['entries'])} drift trigger(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
