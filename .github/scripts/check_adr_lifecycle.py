#!/usr/bin/env python3
"""Validate ADR-0033 lifecycle bindings; optionally emit Verified claims."""

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "core", "pysrc"))

import adr_lifecycle as al
from _gitexec import root_bound_git_env


LEDGER_REL = ".codearbiter/decisions/adr-lifecycle.jsonl"


def select_base_ref(event_name, event):
    if event_name == "pull_request":
        value = event.get("pull_request", {}).get("base", {}).get("sha")
    elif event_name == "merge_group":
        value = event.get("merge_group", {}).get("base_sha")
    elif event_name == "push":
        value = event.get("before")
    else:
        raise ValueError("unsupported GitHub event %r" % event_name)
    if not isinstance(value, str) or not value or set(value) == {"0"}:
        raise ValueError("GitHub event %s has no usable base commit" % event_name)
    return value


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args], capture_output=True, check=False,
        env=root_bound_git_env(),
    )


def _git_blob(root, commit, path):
    if not isinstance(commit, str):
        return None
    resolved = _git(root, "rev-parse", "--verify", "%s^{commit}" % commit)
    if resolved.returncode != 0:
        return None
    result = _git(root, "show", "%s:%s" % (commit, path))
    return result.stdout if result.returncode == 0 else None


def _ledger_at(root, commit):
    entry = _git(root, "ls-tree", "--name-only", commit, LEDGER_REL)
    if entry.returncode != 0:
        raise ValueError("could not inspect lifecycle ledger at %s" % commit)
    if not entry.stdout.strip():
        return None
    blob = _git_blob(root, commit, LEDGER_REL)
    if blob is None:
        raise ValueError("could not read lifecycle ledger at %s" % commit)
    return blob


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    parser.add_argument("--base-ref")
    parser.add_argument("--current-ref")
    parser.add_argument("--github-event", action="store_true")
    parser.add_argument("--verified-json", action="store_true")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    event_error = None
    if args.github_event:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        event_name = os.environ.get("GITHUB_EVENT_NAME")
        if not event_path or not event_name:
            parser.error("--github-event requires GITHUB_EVENT_PATH and GITHUB_EVENT_NAME")
        try:
            with open(event_path, encoding="utf-8") as handle:
                args.base_ref = select_base_ref(event_name, json.load(handle))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            event_error = "could not select GitHub event base: %s" % exc

    ledger = os.path.join(args.root, *LEDGER_REL.split("/"))
    events = al.read_jsonl(ledger)
    errors = [event_error] if event_error else []
    blobs = al.read_adrs(args.root, errors=errors)
    accepted = {adr: blob for adr, blob in blobs.items()
                if al.parse_adr(blob)["status"] == "accepted"}
    errors.extend(al.validate_events(events, blobs))
    bindings = {event.get("adr") for event in events if isinstance(event, dict)
                and event.get("event") in ("acceptance", "baseline")
                and isinstance(event.get("adr"), str)}
    for adr in sorted(set(accepted) - bindings):
        errors.append("%s: accepted ADR has no lifecycle binding" % adr)

    source_blobs = {}
    source_inputs = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("event")
        if kind in ("acceptance", "baseline"):
            commit = event.get("source_commit" if kind == "acceptance" else "observed_commit")
            adr = event.get("adr")
            if isinstance(commit, str) and isinstance(adr, str):
                source_blobs[(commit, adr)] = _git_blob(
                    args.root, commit, ".codearbiter/decisions/%s.md" % adr)
        elif kind in ("implemented", "verified"):
            commit = event.get("source_commit")
            digests = event.get("input_digests")
            if isinstance(digests, dict) and isinstance(commit, str):
                for path in digests:
                    if isinstance(path, str):
                        source_inputs[(commit, path)] = _git_blob(args.root, commit, path)
    errors.extend(al.validate_source_blobs(events, source_blobs))
    errors.extend(al.validate_evidence_sources(events, source_inputs))

    if args.base_ref:
        try:
            base_bytes = _ledger_at(args.root, args.base_ref)
            if args.current_ref:
                current = _ledger_at(args.root, args.current_ref)
                if current is None:
                    errors.append("current ref has no lifecycle ledger: %s" % args.current_ref)
            else:
                with open(ledger, "rb") as handle:
                    current = handle.read()
            if base_bytes is not None and current is not None:
                error = al.append_only_error(base_bytes, current)
                if error:
                    errors.append(error)
        except ValueError as exc:
            errors.append(str(exc))

    exported = None
    diagnostics = []
    if args.verified_json:
        if not args.current_ref or not args.now:
            parser.error("--verified-json requires --current-ref and --now")
        try:
            al._parse_time(args.now)
        except (TypeError, ValueError) as exc:
            errors.append("export time/timezone is invalid: %s" % exc)
        current_commit = _git(
            args.root, "rev-parse", "--verify", "%s^{commit}" % args.current_ref)
        if current_commit.returncode != 0:
            errors.append("current ref is not a resolvable commit: %s" % args.current_ref)
        paths = sorted({path for event in events if isinstance(event, dict)
                        and isinstance(event.get("input_digests"), dict)
                        for path in event["input_digests"] if isinstance(path, str)})
        current_blobs = {path: _git_blob(args.root, args.current_ref, path) for path in paths}
        if not errors:
            exported, export_errors = al.verified_export(
                events, blobs, current_blobs, args.now)
            diagnostics.extend(export_errors)
        if errors:
            exported = []
    if errors:
        if args.verified_json:
            print("[]")
        for error in errors:
            print("::error::" + error, file=sys.stderr)
        return 1
    if args.verified_json:
        print(json.dumps(exported, sort_keys=True, separators=(",", ":")))
        for diagnostic in diagnostics:
            print("::warning::" + diagnostic, file=sys.stderr)
    else:
        print("ADR lifecycle bindings valid; accepted plans are distinct from Verified evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
