#!/usr/bin/env python3
"""codeArbiter: root-bound, committed lifecycle proof shared by CI and installs.

API: read_committed_evidence, validate_committed_sources, source_ancestry,
merge_method. No working-tree fallback, pending-packet allowance, or network.
"""

import json
import subprocess

import _adrlifecycle as al
from _gitexec import git_executable, root_bound_git_env

LEDGER_REL = ".codearbiter/decisions/adr-lifecycle.jsonl"


class GitPrerequisiteError(Exception):
    """The selected Git cannot provide the required offline proof boundary."""


def _git(root, *args):
    prerequisite = ("ADR lifecycle proof requires Git 2.45.0+ with --no-lazy-fetch; "
                    "upgrade the selected Git executable. Proof is never retried without that flag.")
    try:
        executable = git_executable()
        env = root_bound_git_env()
        result = subprocess.run(
            [executable, "--no-replace-objects", "--no-lazy-fetch", "-C", root, *args],
            capture_output=True, check=False, env=env)
        if result.returncode:
            # Diagnose the actual safety capability, not localized error text or
            # a version string. This probe reads no repository and never retries
            # the failed proof command with its network protection removed.
            capability = subprocess.run(
                [executable, "--no-lazy-fetch", "--version"],
                capture_output=True, check=False, env=env)
            if capability.returncode:
                raise GitPrerequisiteError(prerequisite)
    except (OSError, RuntimeError) as exc:
        raise GitPrerequisiteError(prerequisite) from exc
    return result


def _git_blob(root, commit, path):
    if not isinstance(commit, str):
        return None
    resolved = _git(root, "rev-parse", "--verify", "--end-of-options", "%s^{commit}" % commit)
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


def source_ancestry(root, events, current_ref, base_ref=None):
    """Require retained source identities; select a merge that preserves them."""
    errors = []
    refs = {}
    for label, ref in (("current", current_ref), ("base", base_ref)):
        if ref is None and label == "base":
            continue
        if not isinstance(ref, str) or not ref:
            errors.append("%s ref is not a resolvable commit: %s" % (label, ref))
            continue
        resolved = _git(root, "rev-parse", "--verify", "--end-of-options",
                        "%s^{commit}" % ref)
        if resolved.returncode:
            errors.append("%s ref is not a resolvable commit: %s" % (label, ref))
        else:
            refs[label] = resolved.stdout.decode("ascii").strip()
    if errors:
        return errors, None
    method = "squash"
    sources = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("event")
        if kind in ("acceptance", "implemented", "verified"):
            source = event.get("source_commit")
        elif kind == "baseline":
            source = event.get("observed_commit")
        else:
            continue
        if not isinstance(source, str) or not al.HEX40.fullmatch(source):
            errors.append("lifecycle source commit is malformed")
            continue
        sources.add(source)
    for source in sorted(sources):
        retained = _git(root, "merge-base", "--is-ancestor", source, refs["current"])
        if retained.returncode == 1:
            errors.append("%s: source commit is not an ancestor of current ref" % source)
        elif retained.returncode:
            errors.append("%s: could not verify source commit ancestry" % source)
        if "base" in refs:
            in_base = _git(root, "merge-base", "--is-ancestor", source, refs["base"])
            if in_base.returncode == 1:
                method = "merge"
            elif in_base.returncode:
                errors.append("%s: could not verify source commit base ancestry" % source)
    return errors, None if errors else method



def read_committed_evidence(root, current_ref):
    """Read only direct, canonical ADR paths from an exact Git snapshot."""
    committed = _ledger_at(root, current_ref)
    if committed is None:
        raise ValueError("current ref has no lifecycle ledger")
    events = [json.loads(line) for line in committed.decode("utf-8").splitlines()
              if line.strip()]
    tree = _git(root, "ls-tree", "-r", "--name-only", "-z",
                current_ref, ".codearbiter/decisions/")
    if tree.returncode:
        raise ValueError("could not inspect current ADR tree")
    blobs = {}
    for path in tree.stdout.decode("utf-8").split("\0"):
        prefix = ".codearbiter/decisions/"
        if not path.startswith(prefix):
            continue
        name = path[len(prefix):]
        if "/" in name:
            continue
        match = al.ADR_RE.fullmatch(name)
        if match:
            blob = _git_blob(root, current_ref, path)
            if blob is None:
                raise ValueError("could not read current ADR blob: %s" % path)
            al.parse_adr(blob)
            blobs[match.group(1)] = blob
    return events, blobs, committed


def validate_committed_sources(root, events):
    """Recompute existing source-blob and evidence digests from exact Git bytes."""
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
                    root, commit, ".codearbiter/decisions/%s.md" % adr)
        elif kind in ("implemented", "verified"):
            commit = event.get("source_commit")
            digests = event.get("input_digests")
            if isinstance(digests, dict) and isinstance(commit, str):
                for path in digests:
                    if isinstance(path, str):
                        source_inputs[(commit, path)] = _git_blob(root, commit, path)
    return (al.validate_source_blobs(events, source_blobs) +
            al.validate_evidence_sources(events, source_inputs))


def merge_method(root, base_ref, current_ref):
    """Strict portable preflight; inherited baselines are not migration authority."""
    errors = []
    refs = []
    for label, ref in (("base", base_ref), ("current", current_ref)):
        if not isinstance(ref, str) or not ref:
            return ["%s ref is not a resolvable commit" % label], None
        result = _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        if result.returncode:
            return ["%s ref is not a resolvable commit: %s" % (label, ref)], None
        refs.append(result.stdout.decode("ascii").strip())
    base, head = refs
    try:
        events, blobs, committed = read_committed_evidence(root, head)
        base_bytes = _ledger_at(root, base)
        base_events = [json.loads(line) for line in (base_bytes or b"").decode("utf-8").splitlines()
                       if line.strip()]
        errors.extend(al.validate_events(events, blobs))
        bindings = {event.get("adr") for event in events if isinstance(event, dict)
                    and event.get("event") in ("acceptance", "baseline")
                    and isinstance(event.get("adr"), str)}
        errors.extend("%s: accepted ADR has no lifecycle binding" % adr
                      for adr, blob in sorted(blobs.items())
                      if al.parse_adr(blob)["status"] == "accepted" and adr not in bindings)
        if base_bytes is not None:
            prefix_error = al.append_only_error(base_bytes, committed)
            if prefix_error:
                errors.append(prefix_error)
        # A consumer cannot import this repository's closed migration epoch.
        # Only exact already-committed base events may carry baseline records.
        for event in events:
            if (isinstance(event, dict) and event.get("event") == "baseline"
                    and event not in base_events):
                errors.append("%s: new legacy baseline is not permitted by merge preflight"
                              % event.get("adr"))
        errors.extend(validate_committed_sources(root, events))
        ancestry_errors, method = source_ancestry(root, events, head, base)
        errors.extend(ancestry_errors)
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        return ["could not validate committed lifecycle evidence: %s" % exc], None
    return errors, None if errors else method
