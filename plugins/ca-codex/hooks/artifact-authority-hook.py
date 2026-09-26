#!/usr/bin/env python3
# codeArbiter — Codex and Claude Code hook bridge for artifact authority.
"""Correlate closed production verification and review requests with host hooks."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402
import _approvallib  # noqa: E402
import _artifactauthoritylib  # noqa: E402
import _hooklib  # noqa: E402
import _replylib  # noqa: E402


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
    if tool == _replylib.ASK_TOOL and event in {"PreToolUse", "PostToolUse"}:
        return _claude_ask(event, payload)
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
    except Exception as exc:  # noqa: BLE001 - an authority seam must fail closed
        reason = f"codeArbiter authority producer blocked: {exc}"
        if event == "PreToolUse" and (
            isinstance(exc, _artifactauthoritylib.AuthorityError) or _authority_call(payload)
        ):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }}))
        else:
            sys.stderr.write(reason + "\n")
    return 0


def _claude_ask(event: str, payload: dict) -> int:
    """Click-to-approve through Claude Code's own question dialog.

    An ordinary question is never touched. An armed approval question with a
    pre-filled answer is denied; the user's Approve selection on a clean call
    is applied through the normal approval adapter."""
    if event == "PreToolUse":
        try:
            _replylib.observe_ask_pre(payload)
        except (_replylib.ReplyCodeError, OSError) as exc:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"codeArbiter approval question refused: {exc}",
            }}))
        return 0
    try:
        chosen = _replylib.observe_ask_post(payload)
    except (_replylib.ReplyCodeError, OSError) as exc:
        sys.stderr.write(f"codeArbiter approval question not recorded: {exc}\n")
        return 0
    if chosen is None or chosen["route"] != "approval":
        return 0
    session = payload.get("session_id") if isinstance(payload.get("session_id"), str) else ""
    text = _approvallib.consume_from_hook(
        root=chosen["root"], plugin_root=_hooklib.get_host().plugin_root(),
        prompt=chosen["prompt"], host="claude", session_id=session, seam="AskUserQuestion",
    )
    if text:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": text,
        }}))
    return 0


def _authority_call(payload: dict) -> bool:
    """Whether an unexpected failure must deny: an ordinary tool call is never
    refused, but a SendMessage could steer a running review and an authority
    launch or wrapper must not proceed unobserved."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool == "SendMessage":
        return True
    if tool == "Agent":
        prompt = tool_input.get("prompt")
        return isinstance(prompt, str) and prompt.startswith("[CODEARBITER_AUTHORITY_REQUEST:")
    if tool == "Bash":
        command = tool_input.get("command")
        return isinstance(command, str) and "artifact-authority" in command.casefold()
    return False


def run(host) -> int:
    _hooklib.set_host(host)
    if host.name == "claude":
        return claude_main()
    if host.name != "codex":
        return 0
    return main()


if __name__ == "__main__":
    raise SystemExit(run(hostapi.load_host()))
