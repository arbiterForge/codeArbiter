#!/usr/bin/env python3
"""Validate ADR-0033 lifecycle bindings; optionally emit Verified claims."""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "core", "pysrc"))

import adr_lifecycle as al
import prepare_adr_acceptance as paa
from _gitexec import root_bound_git_env


LEDGER_REL = ".codearbiter/decisions/adr-lifecycle.jsonl"
DECISION_LOG_REL = ".codearbiter/decisions/decision-log.md"
LEGACY_BASELINE_OBSERVED_COMMIT = "10d9b012d91681498bdf911dd82ffa28e112407f"


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
        ["git", "--no-replace-objects", "-C", root, *args],
        capture_output=True, check=False,
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


def _index_blob(root, path):
    result = _git(root, "show", ":%s" % path)
    return result.stdout if result.returncode == 0 else None


def _valid_decision_log_append(base, current, stem):
    """Accept one canonical, sequential, accepted decision entry for the ADR."""
    try:
        base_text = base.decode("utf-8")
        current_text = current.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not current_text.startswith(base_text) or current_text == base_text:
        return False
    suffix = current_text[len(base_text):].strip("\n").splitlines()
    if len(suffix) < 24 or suffix[-1] != "---":
        return False
    prior = re.findall(r"(?m)^## DECISION-(\d{4}) — ", base_text)
    header = re.fullmatch(
        r"## DECISION-(\d{4}) — adr-(\d{4})-ratified — .+", suffix[0])
    if not prior or header is None:
        return False
    number = stem.split("-", 1)[0]
    if int(header.group(1)) != int(prior[-1]) + 1 or header.group(2) != number:
        return False
    fixed = (
        r"\*\*Date:\*\* \d{4}-\d{2}-\d{2}",
        r"\*\*Status:\*\* accepted",
        r"\*\*Supersedes:\*\* .+",
        r"\*\*Decided by:\*\* .+",
        r"\*\*Decision category:\*\* .+",
        r"\*\*Artifact-section-hash:\*\* (?:n/a|[0-9a-f]{64})",
    )
    if len(suffix) < 9 or suffix[1] != "" or any(
            re.fullmatch(pattern, suffix[index + 2]) is None
            for index, pattern in enumerate(fixed)):
        return False
    required = (
        "### Variance summary", "- **Artifact position:** ",
        "- **Scaffold position:** ", "- **Status type:** ",
        "### Decision", "### SMARTS rationale", "### Implementation implication",
    )
    positions = []
    for required_line in required:
        exact = required_line.startswith("### ")
        matches = [index for index, line in enumerate(suffix)
                   if line == required_line or
                   (not exact and line.startswith(required_line))]
        if len(matches) != 1:
            return False
        positions.append(matches[0])
    if positions != sorted(positions) or any(
            line.startswith("## DECISION-") for line in suffix[1:]):
        return False
    for heading in ("### Decision", "### SMARTS rationale", "### Implementation implication"):
        start = suffix.index(heading) + 1
        end = next((index for index in range(start, len(suffix))
                    if suffix[index].startswith("### ") or suffix[index] == "---"), len(suffix))
        if not any(line.strip() for line in suffix[start:end]):
            return False
    return True


def _local_pending_acceptance(root, events, blobs):
    """Return one exact staged first-leg ADR stem, or None.

    This is deliberately index-bound and local-only. A clean checkout, mixed
    staged set, unstaged decision edit, existing accepted HEAD, or incomplete
    decision-log append receives no transition allowance and remains strict.
    """
    bindings = {event.get("adr") for event in events if isinstance(event, dict)
                and event.get("event") in ("acceptance", "baseline")
                and isinstance(event.get("adr"), str)}
    accepted = {adr for adr, blob in blobs.items()
                if al.parse_adr(blob)["status"] == "accepted"}
    missing = sorted(accepted - bindings)
    if len(missing) != 1:
        return None
    stem = missing[0]
    adr_rel = ".codearbiter/decisions/%s.md" % stem
    expected_paths = {adr_rel, DECISION_LOG_REL}

    staged = _git(root, "diff", "--cached", "--name-only", "-z", "--no-renames")
    if staged.returncode != 0:
        return None
    try:
        staged_paths = {path.decode("utf-8").replace("\\", "/")
                        for path in staged.stdout.split(b"\0") if path}
    except UnicodeDecodeError:
        return None
    if staged_paths != expected_paths:
        return None

    status = _git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--", ".codearbiter/decisions")
    if status.returncode != 0:
        return None
    seen = set()
    for raw in status.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            entry = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if (len(entry) < 4 or entry[0] not in ("A", "M") or
                entry[1] not in (" ", "M")):
            return None
        seen.add(entry[3:].replace("\\", "/"))
    if seen != expected_paths:
        return None

    index_adr = _index_blob(root, adr_rel)
    index_log = _index_blob(root, DECISION_LOG_REL)
    try:
        with open(os.path.join(root, *DECISION_LOG_REL.split("/")), "rb") as handle:
            worktree_log = handle.read()
    except OSError:
        return None
    if (index_adr is None or index_log is None or stem not in blobs or
            al._normalized_text(blobs[stem]) != al._normalized_text(index_adr) or
            al._normalized_text(worktree_log) != al._normalized_text(index_log)):
        return None
    try:
        if al.parse_adr(index_adr)["status"] != "accepted":
            return None
    except (UnicodeError, ValueError):
        return None

    head_adr = _git_blob(root, "HEAD", adr_rel)
    if head_adr is not None:
        try:
            if (al.parse_adr(head_adr)["status"] == "accepted" or
                    paa.transition_body(head_adr) != paa.transition_body(index_adr)):
                return None
        except (UnicodeError, ValueError):
            return None

    head_log = _git_blob(root, "HEAD", DECISION_LOG_REL)
    if head_log is None or not _valid_decision_log_append(
            head_log, index_log, stem):
        return None

    packet = paa.read_packet(root)
    if packet is None:
        return None
    expected_fields = {
        "schema", "repository", "head", "index_tree", "adr",
        "adr_blob_sha256", "transition_body_sha256",
        "decision_log_base_sha256", "decision_log_index_sha256",
        "obligations", "obligations_sha256", "reviewed_by",
        "reviewed_at", "valid_until",
    }
    if set(packet) != expected_fields or packet.get("schema") != paa.SCHEMA:
        return None
    digest = lambda value: hashlib.sha256(value).hexdigest()
    try:
        now = dt.datetime.now(dt.timezone.utc)
        reviewed_at = al._parse_time(packet.get("reviewed_at"))
        valid_until = al._parse_time(packet.get("valid_until"))
        index_tree = _git(root, "write-tree")
        if index_tree.returncode != 0:
            return None
        obligations = packet.get("obligations")
        synthetic = {
            "schema": "adr-lifecycle/v1", "event": "acceptance", "adr": stem,
            "recorded_at": packet["reviewed_at"], "source_commit": "0" * 40,
            "blob_sha256": digest(index_adr),
            "body_sha256": digest(al.immutable_body(index_adr)),
            "obligations": obligations,
            "obligations_sha256": al.obligation_set_digest(obligations),
            "obligations_sealed": True,
        }
        if (packet["repository"] != paa.repository_identity(root) or
                packet["head"] != _git(root, "rev-parse", "HEAD").stdout.decode().strip() or
                packet["index_tree"] != index_tree.stdout.decode().strip() or
                packet["adr"] != stem or
                packet["adr_blob_sha256"] != digest(index_adr) or
                packet["transition_body_sha256"] != digest(paa.transition_body(index_adr)) or
                packet["decision_log_base_sha256"] != digest(head_log) or
                packet["decision_log_index_sha256"] != digest(index_log) or
                packet["obligations_sha256"] != synthetic["obligations_sha256"] or
                not isinstance(packet["reviewed_by"], list) or
                not packet["reviewed_by"] or
                any(not isinstance(item, str) or not item.strip()
                    for item in packet["reviewed_by"]) or
                reviewed_at > now or now > valid_until or
                valid_until - reviewed_at > paa.MAX_LIFETIME or
                al.validate_events([synthetic], {stem: index_adr})):
            return None
    except (KeyError, TypeError, UnicodeError, ValueError):
        return None
    return stem


def _local_binding_transition_error(root, events, blobs):
    """Bind the staged second leg to the reviewed first-leg packet."""
    staged = _git(root, "diff", "--cached", "--name-only", "-z", "--no-renames")
    if staged.returncode != 0:
        return "could not inspect staged ADR acceptance binding"
    try:
        paths = {path.decode("utf-8").replace("\\", "/")
                 for path in staged.stdout.split(b"\0") if path}
    except UnicodeDecodeError:
        return "staged ADR acceptance binding paths are not UTF-8"
    head_ledger = _ledger_at(root, "HEAD")
    index_ledger = _index_blob(root, LEDGER_REL)
    ledger_path = os.path.join(root, *LEDGER_REL.split("/"))
    try:
        with open(ledger_path, "rb") as handle:
            worktree_ledger = handle.read()
    except OSError:
        return "staged ADR acceptance binding ledger is unreadable"
    try:
        head_events = [json.loads(line.decode("utf-8"))
                       for line in (head_ledger or b"").splitlines() if line.strip()]
        head_acceptances = [json.dumps(event, sort_keys=True, separators=(",", ":"))
                            for event in head_events if isinstance(event, dict)
                            and event.get("event") == "acceptance"]
        work_acceptances = [json.dumps(event, sort_keys=True, separators=(",", ":"))
                            for event in events if isinstance(event, dict)
                            and event.get("event") == "acceptance"]
        new_work_acceptance = any(
            work_acceptances.count(item) > head_acceptances.count(item)
            for item in set(work_acceptances))
    except (TypeError, UnicodeError, ValueError):
        new_work_acceptance = False
    if LEDGER_REL not in paths:
        return ("ADR acceptance binding is present only in unstaged working-tree bytes"
                if new_work_acceptance else None)
    if head_ledger is None or index_ledger is None or not index_ledger.startswith(head_ledger):
        return "staged ADR lifecycle ledger is not an exact append"
    appended = [line for line in index_ledger[len(head_ledger):].splitlines() if line.strip()]
    try:
        new_events = [json.loads(line.decode("utf-8")) for line in appended]
    except (UnicodeError, ValueError):
        return "staged ADR acceptance binding append is malformed"
    acceptances = [event for event in new_events if isinstance(event, dict)
                   and event.get("event") == "acceptance"]
    if not acceptances:
        return ("ADR acceptance binding is not fully staged"
                if new_work_acceptance else None)
    if (paths != {LEDGER_REL} or
            al._normalized_text(worktree_ledger) != al._normalized_text(index_ledger)):
        return "staged ADR acceptance binding is not the sole exact append"
    if len(new_events) != 1 or len(acceptances) != 1:
        return "staged ADR acceptance binding must append exactly one acceptance"

    event = acceptances[0]
    packet = paa.read_packet(root)
    if packet is None:
        return "staged ADR acceptance binding has no reviewed pending packet"
    stem = event.get("adr")
    if not isinstance(stem, str):
        return "staged ADR acceptance binding has no ADR stem"
    adr_blob = _git_blob(root, "HEAD", ".codearbiter/decisions/%s.md" % stem)
    decision_log = _git_blob(root, "HEAD", DECISION_LOG_REL)
    head = _git(root, "rev-parse", "HEAD")
    parent = _git(root, "rev-parse", "HEAD^")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if (adr_blob is None or decision_log is None or head.returncode != 0 or
            parent.returncode != 0 or tree.returncode != 0):
        return "could not resolve the pending ADR acceptance source commit"
    head_text = head.stdout.decode().strip()
    try:
        expected_packet_fields = {
            "schema", "repository", "head", "index_tree", "adr",
            "adr_blob_sha256", "transition_body_sha256",
            "decision_log_base_sha256", "decision_log_index_sha256",
            "obligations", "obligations_sha256", "reviewed_by",
            "reviewed_at", "valid_until",
        }
        reviewed_at = al._parse_time(packet.get("reviewed_at"))
        valid_until = al._parse_time(packet.get("valid_until"))
        recorded_at = al._parse_time(event.get("recorded_at"))
        now = dt.datetime.now(dt.timezone.utc)
        packet_head_ledger = _ledger_at(root, packet.get("head"))
        packet_head_log = _git_blob(root, packet.get("head"), DECISION_LOG_REL)
        expected_event_fields = {
            "schema", "event", "adr", "recorded_at", "source_commit",
            "blob_sha256", "body_sha256", "obligations",
            "obligations_sha256", "obligations_sealed",
        }
        if (set(packet) != expected_packet_fields or
                set(event) != expected_event_fields or
                packet.get("schema") != paa.SCHEMA or
                packet.get("repository") != paa.repository_identity(root) or
                packet.get("adr") != stem or
                packet.get("head") != parent.stdout.decode().strip() or
                packet.get("index_tree") != tree.stdout.decode().strip() or
                packet.get("adr_blob_sha256") != hashlib.sha256(adr_blob).hexdigest() or
                packet.get("transition_body_sha256") != hashlib.sha256(
                    paa.transition_body(adr_blob)).hexdigest() or
                packet.get("decision_log_index_sha256") != hashlib.sha256(
                    decision_log).hexdigest() or
                packet_head_log is None or
                packet.get("decision_log_base_sha256") != hashlib.sha256(
                    packet_head_log).hexdigest() or
                packet_head_ledger != head_ledger or
                not isinstance(packet.get("reviewed_by"), list) or
                not packet.get("reviewed_by") or
                any(not isinstance(item, str) or not item.strip()
                    for item in packet.get("reviewed_by")) or
                packet.get("obligations_sha256") != al.obligation_set_digest(
                    packet.get("obligations")) or
                event.get("schema") != "adr-lifecycle/v1" or
                event.get("source_commit") != head_text or
                event.get("blob_sha256") != packet.get("adr_blob_sha256") or
                event.get("body_sha256") != hashlib.sha256(
                    al.immutable_body(adr_blob)).hexdigest() or
                event.get("obligations") != packet.get("obligations") or
                event.get("obligations_sha256") != packet.get("obligations_sha256") or
                event.get("obligations_sealed") is not True or
                reviewed_at > now or
                valid_until - reviewed_at > paa.MAX_LIFETIME or
                recorded_at < reviewed_at or recorded_at > now or
                recorded_at > valid_until or now > valid_until):
            return "staged ADR acceptance binding does not match its reviewed pending packet"
    except (KeyError, TypeError, UnicodeError, ValueError):
        return "staged ADR acceptance binding packet is malformed or stale"
    return None


def accepted_binding_errors(root, events, blobs, allow_local_pending=False):
    """Validate accepted-ADR binding completeness for a repository state."""
    bindings = {event.get("adr") for event in events if isinstance(event, dict)
                and event.get("event") in ("acceptance", "baseline")
                and isinstance(event.get("adr"), str)}
    accepted = {adr for adr, blob in blobs.items()
                if al.parse_adr(blob)["status"] == "accepted"}
    pending = (_local_pending_acceptance(root, events, blobs)
               if allow_local_pending else None)
    errors = ["%s: accepted ADR has no lifecycle binding" % adr
              for adr in sorted(accepted - bindings - ({pending} if pending else set()))]
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "baseline":
            continue
        stem = event.get("adr")
        observed = event.get("observed_commit")
        if not isinstance(stem, str) or not isinstance(observed, str):
            continue
        if observed != LEGACY_BASELINE_OBSERVED_COMMIT:
            errors.append(
                "%s: legacy baseline lies outside the closed migration epoch" % stem)
    if allow_local_pending:
        transition_error = _local_binding_transition_error(root, events, blobs)
        if transition_error:
            errors.append(transition_error)
    return errors, pending


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    parser.add_argument("--base-ref")
    parser.add_argument("--current-ref")
    parser.add_argument("--github-event", action="store_true")
    parser.add_argument("--verified-json", action="store_true")
    parser.add_argument("--merge-method", action="store_true",
                        help="emit squash or merge for exact committed base/head evidence")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    if args.merge_method and (not args.base_ref or not args.current_ref or
                              args.github_event or args.verified_json):
        parser.error("--merge-method requires --base-ref and --current-ref only")
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
    errors = [event_error] if event_error else []
    if args.current_ref is not None:
        if not args.merge_method:
            # Preserve the existing strict local-pending/export boundary too:
            # dirty invalid evidence cannot be blessed by naming an older ref.
            working_events = al.read_jsonl(ledger)
            working_blobs = al.read_adrs(args.root, errors=errors)
            errors.extend(al.validate_events(working_events, working_blobs))
            working_errors, _pending = accepted_binding_errors(
                args.root, working_events, working_blobs, allow_local_pending=False)
            errors.extend(working_errors)
        events, blobs = [], {}
        # Explicit revision checks are derived from committed bytes, never a dirty
        # working-tree ledger that can hide a new source binding.
        try:
            committed = _ledger_at(args.root, args.current_ref)
            if committed is None:
                raise ValueError("current ref has no lifecycle ledger")
            events = [json.loads(line) for line in committed.decode("utf-8").splitlines()
                      if line.strip()]
            tree = _git(args.root, "ls-tree", "-r", "--name-only", "-z",
                        args.current_ref, ".codearbiter/decisions/")
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
                    blob = _git_blob(args.root, args.current_ref, path)
                    if blob is None:
                        raise ValueError("could not read current ADR blob: %s" % path)
                    al.parse_adr(blob)
                    blobs[match.group(1)] = blob
        except (ValueError, UnicodeError) as exc:
            errors.append("could not read committed current ref evidence: %s" % exc)
    else:
        events = al.read_jsonl(ledger)
        blobs = al.read_adrs(args.root, errors=errors)
    errors.extend(al.validate_events(events, blobs))
    allow_pending = (args.base_ref is None and args.current_ref is None and
                     not args.github_event and not args.verified_json)
    try:
        binding_errors, pending = accepted_binding_errors(
            args.root, events, blobs, allow_local_pending=allow_pending)
    except (OSError, UnicodeError, ValueError):
        binding_errors, pending = accepted_binding_errors(
            args.root, events, blobs, allow_local_pending=False)
    errors.extend(binding_errors)

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
    merge_method = None
    if args.current_ref is not None:
        ancestry_errors, merge_method = source_ancestry(
            args.root, events, args.current_ref,
            args.base_ref if args.merge_method else None)
        errors.extend(ancestry_errors)

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
    if args.merge_method:
        print(merge_method)
    elif args.verified_json:
        print(json.dumps(exported, sort_keys=True, separators=(",", ":")))
        for diagnostic in diagnostics:
            print("::warning::" + diagnostic, file=sys.stderr)
    else:
        if pending:
            print("ADR lifecycle valid pending acceptance source commit for %s; "
                  "binding is not yet recorded" % pending)
        else:
            print("ADR lifecycle bindings valid; accepted plans are distinct from Verified evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
