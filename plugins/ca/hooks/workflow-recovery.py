#!/usr/bin/env python3
"""Bounded local workflow continuation through the executing host installation."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi
from _hooklib import project_root, set_host, utf8_stdio
import _workflowrecoverylib as recovery


def _owned_helper(host):
    """Use the existing executing-anchor/manifest authentication, never PATH."""
    try:
        helper = Path(__file__).absolute()
        if not recovery._regular(helper.lstat(), owner=False) or helper.name != "workflow-recovery.py":
            return False
        plugin = Path(host.plugin_root()).resolve(strict=True)
        if helper.parent.name != "hooks" or helper.parent.parent.resolve(strict=True) != plugin:
            return False
        for name in ("_workflowrecoverylib.py", "work.py", "hostapi.py"):
            if not recovery._regular((helper.parent / name).lstat(), owner=False):
                return False
        return getattr(host, "name", None) in ("claude", "codex", "pi")
    except Exception:
        return False


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    registration = sub.add_parser("register", help="Durably capture up to 32 sanitized candidates from bounded JSON stdin")
    registration.add_argument("--input", help="Bounded local JSON file instead of stdin")
    scan = sub.add_parser("scan", help="Read one page without creating or repairing anything")
    scan.add_argument("--cursor")
    get = sub.add_parser("get", help="Read one exact obligation")
    get.add_argument("--obligation-id", required=True)
    sub.add_parser("repair", help="Explicitly repair a retained record/index transaction under its OS lock")
    for action in ("resume", "reconcile", "claim", "correct", "restore", "restore-authority", "cancel", "decline", "supersede", "compact"):
        command = sub.add_parser(action)
        command.add_argument("--obligation-id", required=True)
        command.add_argument("--expected-revision", required=True, type=int)
        if action == "correct":
            command.add_argument("--input", help="Bounded JSON containing candidate and source; default stdin")
        if action == "supersede":
            command.add_argument("--replacement", required=True)
        if action == "restore-authority":
            command.add_argument("--authority-source", required=True,
                help="Sanitized actual user/host lift reference; context only, never permission")
    return parser


def _input(path=None):
    if path is not None:
        raw = recovery._read_regular(Path(path), recovery.BOUNDS["registration_max_bytes"])
    else:
        raw = sys.stdin.buffer.read(recovery.BOUNDS["registration_max_bytes"] + 1)
    if len(raw) > recovery.BOUNDS["registration_max_bytes"]:
        raise recovery.RecoveryError("invalid")
    return recovery._decode(raw)


def main(argv=None):
    utf8_stdio()
    args = _parser().parse_args(argv)
    host = hostapi.load_host()
    set_host(host)
    if not _owned_helper(host):
        result = {"status": "unavailable", "reason": "untrusted-helper", "durable": False}
    else:
        try:
            if args.action == "register":
                request = _input(args.input)
            elif args.action == "scan":
                request = {"cursor": args.cursor} if args.cursor is not None else {}
            elif args.action == "repair":
                request = {}
            else:
                request = {"obligation_id": args.obligation_id}
                if args.action != "get":
                    request["expected_revision"] = args.expected_revision
                if args.action == "correct":
                    correction = _input(args.input)
                    if not isinstance(correction, dict) or set(correction) != {"candidate", "source"}:
                        raise recovery.RecoveryError("invalid")
                    request.update(correction)
                elif args.action == "supersede":
                    request["replacement"] = args.replacement
                elif args.action == "restore-authority":
                    request["authority_source"] = args.authority_source
            result = recovery.dispatch(project_root(), args.action, request)
        except recovery.RecoveryError as exc:
            result = {"status": "unavailable", "reason": exc.reason, "durable": False}
        except (OSError, ValueError, TypeError):
            result = {"status": "unavailable", "reason": "storage-unavailable", "durable": False}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if result.get("status") == "conflict":
        return 5
    if result.get("reason") == "busy":
        return 4
    if result.get("reason") == "invalid":
        return 2
    return 3 if result.get("status") == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
