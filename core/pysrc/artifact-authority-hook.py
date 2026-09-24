#!/usr/bin/env python3
# codeArbiter — Codex and Claude Code hook bridge for artifact authority.
"""Correlate closed production verification and review requests with host hooks."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402
import _artifactauthoritylib  # noqa: E402
import _hooklib  # noqa: E402


def main() -> int:
    _hooklib.utf8_stdio()
    payload = _hooklib.read_input()
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name")
    if event not in {"PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop"}:
        return 0
    tool = payload.get("tool_name")
    root = _hooklib.project_root(payload)
    try:
        if event in {"PreToolUse", "PostToolUse"} and tool != "spawn_agent":
            result = _artifactauthoritylib.observe_verifier_hook(root, payload)
            if result is None:
                return 0
        else:
            result = _artifactauthoritylib.observe_codex_hook(root, payload)
            if result is None:
                return 0
    except _artifactauthoritylib.AuthorityError as exc:
        reason = f"codeArbiter authority producer blocked: {exc}"
        if event == "PreToolUse":
            print(json.dumps({"decision": "block", "reason": reason}))
        else:
            sys.stderr.write(reason + "\n")
        return 0
    if event == "PreToolUse" and result.get("state") == "AUTHORIZED":
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "codeArbiter authorized this wrapper for the exact resolved child set: "
                + json.dumps(result["command_bindings"], sort_keys=True)
            ),
        }))
    if event == "SubagentStop" and result.get("state") == "COMPLETED":
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": (
                    "codeArbiter: independent review observation recorded for request "
                    + result["request_id"]
                    + "; publish it through the production authority adapter."
                ),
            },
        }))
    return 0


def claude_main() -> int:
    """Claude Code seams. Success is silent: an explicit allow would bypass the
    user's permission rules, and a SubagentStop block would make the reviewer
    keep going. Only a PreToolUse refusal prints (a Claude deny decision)."""
    _hooklib.utf8_stdio()
    payload = _hooklib.read_input()
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    root = _hooklib.project_root(payload)
    try:
        if event in {"PreToolUse", "PostToolUse", "PostToolUseFailure"} and tool == "Bash":
            _artifactauthoritylib.observe_verifier_hook(root, payload, host="claude")
        elif (
            (event in {"PreToolUse", "PostToolUse"} and tool == "Agent")
            or (event == "PreToolUse" and tool == "SendMessage")
            or event in {"SubagentStart", "SubagentStop"}
        ):
            _artifactauthoritylib.observe_claude_hook(root, payload)
    except _artifactauthoritylib.AuthorityError as exc:
        reason = f"codeArbiter authority producer blocked: {exc}"
        if event == "PreToolUse":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }}))
        else:
            sys.stderr.write(reason + "\n")
    return 0


def run(host) -> int:
    _hooklib.set_host(host)
    if host.name == "claude":
        return claude_main()
    if host.name != "codex":
        return 0
    return main()


if __name__ == "__main__":
    raise SystemExit(run(hostapi.load_host()))
