#!/usr/bin/env python3
"""Best-effort Codex subagent usage recovery for tribunal telemetry.

Codex exposes a transcript path to hooks, but its transcript wire format is not
a stable extension interface. This helper therefore treats every parse failure
as an explicit unavailable state. It reads only session metadata and cumulative
token-count events; it never emits conversation or tool content.
"""
import argparse
import json
import os
import re
import sys


THREAD_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
OBSERVED_SOURCE = "codex-session-transcript-best-effort"
MAX_SCAN_ENTRIES = 100000
MAX_CANDIDATES = 32
MAX_TRANSCRIPT_BYTES = 256 * 1024 * 1024
MAX_JSON_LINE_BYTES = 1024 * 1024
MAX_RUN_LOG_BYTES = 16 * 1024 * 1024
MAX_RUN_EVENTS = 10000
LENS_UNAVAILABLE_REASONS = frozenset({
    "host-usage-unsupported",
    "host-result-missing",
    "transcript-unavailable",
    "transcript-format-unsupported",
    "transcript-scan-limit-exceeded",
    "transcript-over-limit",
    "usage-invalid",
    "invalid-agent-thread-id",
})


def _unavailable(reason):
    return {"status": "unavailable", "reason": reason}


def _nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _normalize_usage(value):
    if not isinstance(value, dict) or not _nonnegative_int(value.get("total_tokens")):
        return None
    normalized = {}
    for field in USAGE_FIELDS:
        if field not in value:
            return None
        raw = value[field]
        if not _nonnegative_int(raw):
            return None
        normalized[field] = raw
    return normalized


def default_sessions_root():
    codex_home = os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    return os.path.join(codex_home, "sessions")


def _is_linklike(path):
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def _contained_realpath(path, root_real):
    try:
        resolved = os.path.realpath(path)
        common = os.path.commonpath((root_real, resolved))
    except (OSError, ValueError):
        return None
    if os.path.normcase(common) != os.path.normcase(root_real):
        return None
    return resolved


def _candidate_transcripts(thread_id, sessions_root):
    suffix = f"-{thread_id}.jsonl"
    candidates = []
    root_real = os.path.realpath(sessions_root)
    if not os.path.isdir(root_real):
        return [], None
    stack = [root_real]
    seen_dirs = {os.path.normcase(root_real)}
    entries_seen = 0
    try:
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_SCAN_ENTRIES:
                        return [], "transcript-scan-limit-exceeded"
                    path = entry.path
                    if _is_linklike(path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        resolved = _contained_realpath(path, root_real)
                        key = os.path.normcase(resolved) if resolved else None
                        if resolved and key not in seen_dirs:
                            seen_dirs.add(key)
                            stack.append(resolved)
                        continue
                    name = entry.name
                    if not (entry.is_file(follow_symlinks=False)
                            and (name.endswith(suffix)
                                 or name == f"{thread_id}.jsonl")):
                        continue
                    resolved = _contained_realpath(path, root_real)
                    if not resolved:
                        continue
                    try:
                        candidates.append((os.path.getmtime(resolved), resolved))
                    except OSError:
                        continue
                    if len(candidates) > MAX_CANDIDATES:
                        return [], "transcript-scan-limit-exceeded"
    except OSError:
        return [], "transcript-unavailable"
    return [path for _, path in sorted(candidates, reverse=True)], None


def _read_candidate(path, thread_id, sessions_root=None):
    saw_matching_meta = False
    saw_token_event = False
    invalid_usage = False
    latest = None
    descriptor = None
    try:
        root_real = os.path.realpath(sessions_root or os.path.dirname(path))
        if (_is_linklike(path)
                or _contained_realpath(path, root_real) is None):
            return None, "transcript-unavailable"
        before_open = os.stat(path, follow_symlinks=False)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if ((before_open.st_dev, before_open.st_ino)
                != (opened.st_dev, opened.st_ino)):
            return None, "transcript-unavailable"
        if opened.st_size > MAX_TRANSCRIPT_BYTES:
            return None, "transcript-over-limit"
        total_read = 0
        handle = os.fdopen(descriptor, "rb")
        descriptor = None
        with handle:
            while True:
                line = handle.readline(MAX_JSON_LINE_BYTES + 1)
                if not line:
                    break
                total_read += len(line)
                if total_read > MAX_TRANSCRIPT_BYTES:
                    return None, "transcript-over-limit"
                if (len(line) > MAX_JSON_LINE_BYTES
                        and not line.endswith(b"\n")):
                    saw_usage_marker = b'"token_count"' in line
                    while line and not line.endswith(b"\n"):
                        line = handle.readline(MAX_JSON_LINE_BYTES + 1)
                        total_read += len(line)
                        saw_usage_marker = (saw_usage_marker
                                            or b'"token_count"' in line)
                        if total_read > MAX_TRANSCRIPT_BYTES:
                            return None, "transcript-over-limit"
                    if saw_usage_marker:
                        invalid_usage = True
                    continue
                # Do not parse or retain conversation/tool records. The cheap
                # discriminator also avoids decoding arbitrarily large content
                # lines that cannot contain either required event.
                if (b'"session_meta"' not in line
                        and b'"token_count"' not in line):
                    continue
                try:
                    record = json.loads(line)
                except (TypeError, ValueError, RecursionError):
                    if b'"token_count"' in line:
                        invalid_usage = True
                    continue
                if record.get("type") == "session_meta":
                    payload = record.get("payload")
                    if isinstance(payload, dict) and payload.get("id") == thread_id:
                        saw_matching_meta = True
                    continue
                payload = record.get("payload")
                if not (record.get("type") == "event_msg"
                        and isinstance(payload, dict)
                        and payload.get("type") == "token_count"):
                    continue
                saw_token_event = True
                info = payload.get("info")
                usage = _normalize_usage(
                    info.get("total_token_usage") if isinstance(info, dict) else None)
                if usage is None:
                    invalid_usage = True
                else:
                    latest = usage
    except OSError:
        return None, "transcript-unavailable"
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    if not saw_matching_meta:
        return None, "transcript-format-unsupported"
    if latest is not None:
        return latest, None
    if saw_token_event or invalid_usage:
        return None, "usage-invalid"
    return None, "transcript-format-unsupported"


def observe_usage(thread_id, sessions_root=None):
    if not isinstance(thread_id, str) or not THREAD_ID_RE.fullmatch(thread_id):
        return _unavailable("invalid-agent-thread-id")
    root = sessions_root or default_sessions_root()
    candidates, scan_reason = _candidate_transcripts(thread_id, root)
    if scan_reason:
        return _unavailable(scan_reason)
    if not candidates:
        return _unavailable("transcript-unavailable")

    reasons = []
    for path in candidates:
        usage, reason = _read_candidate(path, thread_id, root)
        if usage is not None:
            return {
                "status": "observed",
                "source": OBSERVED_SOURCE,
                "tokens": usage["total_tokens"],
                "token_usage": usage,
            }
        reasons.append(reason)
    if "usage-invalid" in reasons:
        return _unavailable("usage-invalid")
    if "transcript-format-unsupported" in reasons:
        return _unavailable("transcript-format-unsupported")
    if "transcript-over-limit" in reasons:
        return _unavailable("transcript-over-limit")
    return _unavailable("transcript-unavailable")


def aggregate_events(events):
    completed = [event for event in events
                 if isinstance(event, dict) and event.get("event") == "lens-completed"]
    if not completed:
        return {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["no-completed-lenses"],
        }

    actual = 0
    observed = 0
    reasons = set()
    for event in completed:
        tokens_status = event.get("tokens_status")
        tokens = event.get("tokens")
        if tokens_status == "unavailable":
            reason = event.get("tokens_reason")
            reasons.add(reason if reason in LENS_UNAVAILABLE_REASONS
                        else "reason-invalid")
            continue
        if tokens_status == "observed":
            usage = _normalize_usage(event.get("token_usage"))
            if (_nonnegative_int(tokens)
                    and event.get("tokens_source") == OBSERVED_SOURCE
                    and usage is not None
                    and usage["total_tokens"] == tokens):
                actual += tokens
                observed += 1
            else:
                reasons.add("usage-invalid")
            continue
        # Pre-instrumentation run logs had no status field. Preserve their
        # numeric observations while requiring explicit states on new events.
        if tokens_status is None and _nonnegative_int(tokens):
            actual += tokens
            observed += 1
            continue
        if tokens_status is None:
            reasons.add("host-result-missing")
        else:
            reasons.add("reason-invalid")

    if observed == len(completed):
        status = "complete"
    elif observed:
        status = "partial"
    else:
        status = "unavailable"
    return {
        "tokens_actual": actual if observed else None,
        "tokens_actual_status": status,
        "tokens_unavailable_reasons": sorted(reasons),
    }


def _read_run_log(path):
    events = []
    try:
        if os.path.getsize(path) > MAX_RUN_LOG_BYTES:
            return None, "run-log-over-limit"
        total_read = 0
        with open(path, "rb") as handle:
            while True:
                line = handle.readline(MAX_JSON_LINE_BYTES + 1)
                if not line:
                    break
                total_read += len(line)
                if (total_read > MAX_RUN_LOG_BYTES
                        or (len(line) > MAX_JSON_LINE_BYTES
                            and not line.endswith(b"\n"))):
                    return None, "run-log-over-limit"
                if b'"lens-completed"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except (TypeError, ValueError, RecursionError):
                    return None, "run-log-invalid"
                if (isinstance(record, dict)
                        and record.get("event") == "lens-completed"):
                    events.append(record)
                    if len(events) > MAX_RUN_EVENTS:
                        return None, "run-log-over-limit"
    except OSError:
        return None, "run-log-unavailable"
    return events, None


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--thread-id", required=True)
    observe.add_argument("--sessions-root")
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--run-log", required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.mode == "observe":
            result = observe_usage(args.thread_id, args.sessions_root)
        else:
            events, read_reason = _read_run_log(args.run_log)
            if read_reason:
                result = {
                    "tokens_actual": None,
                    "tokens_actual_status": "unavailable",
                    "tokens_unavailable_reasons": [read_reason],
                }
            else:
                result = aggregate_events(events)
    except Exception:
        if args.mode == "observe":
            result = _unavailable("usage-invalid")
        else:
            result = {
                "tokens_actual": None,
                "tokens_actual_status": "unavailable",
                "tokens_unavailable_reasons": ["run-log-invalid"],
            }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
