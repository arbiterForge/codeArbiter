#!/usr/bin/env python3
# codeArbiter — bounded Claude subagent usage recovery for tribunal telemetry.
#
# Claude Code documents one transcript per subagent under
# projects/<project>/<session>/subagents/agent-<agentId>.jsonl. This helper
# resolves only an exact returned agent ID, parses only agent/usage records,
# and emits aggregate integers. Malformed or changed host state always becomes
# an explicit unavailable reason.
#
# Public API:
#   default_projects_root() -> str
#   observe_usage(agent_id, projects_root=None) -> dict
#   main(argv=None) -> int

import argparse
import json
import os
import re
import sys


AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
MAX_SCAN_ENTRIES = 100000
MAX_CANDIDATES = 32
MAX_TRANSCRIPT_BYTES = 256 * 1024 * 1024
MAX_JSON_LINE_BYTES = 1024 * 1024


def _unavailable(reason):
    return {"status": "unavailable", "reason": reason}


def _nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _normalize_usage(value):
    if not isinstance(value, dict):
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


def default_projects_root():
    config_root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(config_root, "projects")


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


def _candidate_transcripts(agent_id, projects_root):
    filename = f"agent-{agent_id}.jsonl"
    candidates = []
    root_real = os.path.realpath(projects_root)
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
                    if not (entry.is_file(follow_symlinks=False)
                            and entry.name == filename):
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


def _read_candidate(path, agent_id, projects_root):
    totals = {field: 0 for field in USAGE_FIELDS}
    saw_matching_agent = False
    saw_usage = False
    invalid_usage = False
    descriptor = None
    try:
        root_real = os.path.realpath(projects_root)
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
                    saw_usage_marker = b'"usage"' in line
                    while line and not line.endswith(b"\n"):
                        line = handle.readline(MAX_JSON_LINE_BYTES + 1)
                        total_read += len(line)
                        saw_usage_marker = (saw_usage_marker
                                            or b'"usage"' in line)
                        if total_read > MAX_TRANSCRIPT_BYTES:
                            return None, "transcript-over-limit"
                    if saw_usage_marker:
                        invalid_usage = True
                    continue
                if b'"agentId"' not in line and b'"usage"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except (TypeError, ValueError, RecursionError):
                    if b'"usage"' in line:
                        invalid_usage = True
                    continue
                if not isinstance(record, dict) or record.get("agentId") != agent_id:
                    continue
                saw_matching_agent = True
                message = record.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                if usage is None:
                    continue
                saw_usage = True
                if (record.get("type") != "assistant"
                        or message.get("role") != "assistant"):
                    invalid_usage = True
                    continue
                normalized = _normalize_usage(usage)
                if normalized is None:
                    invalid_usage = True
                    continue
                for field in USAGE_FIELDS:
                    totals[field] += normalized[field]
    except OSError:
        return None, "transcript-unavailable"
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    if not saw_matching_agent:
        return None, "transcript-format-unsupported"
    if invalid_usage:
        return None, "usage-invalid"
    if not saw_usage:
        return None, "transcript-format-unsupported"
    totals["total_tokens"] = sum(totals.values())
    return totals, None


def observe_usage(agent_id, projects_root=None):
    if not isinstance(agent_id, str) or not AGENT_ID_RE.fullmatch(agent_id):
        return _unavailable("invalid-agent-id")
    root = projects_root or default_projects_root()
    candidates, scan_reason = _candidate_transcripts(agent_id, root)
    if scan_reason:
        return _unavailable(scan_reason)
    if not candidates:
        return _unavailable("transcript-unavailable")

    reasons = []
    for path in candidates:
        usage, reason = _read_candidate(path, agent_id, root)
        if usage is not None:
            return {
                "status": "observed",
                "source": "claude-subagent-transcript",
                "tokens": usage["total_tokens"],
                "token_usage": usage,
            }
        reasons.append(reason)
    for reason in (
            "usage-invalid",
            "transcript-format-unsupported",
            "transcript-over-limit"):
        if reason in reasons:
            return _unavailable(reason)
    return _unavailable("transcript-unavailable")


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--agent-id", required=True)
    observe.add_argument("--projects-root")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        result = observe_usage(args.agent_id, args.projects_root)
    except Exception:
        result = _unavailable("usage-invalid")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
