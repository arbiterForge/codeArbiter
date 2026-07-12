#!/usr/bin/env python3
"""Preserve shared exit-2 guards across Codex's Windows shell boundary."""

import json
import os
import subprocess
import sys


def main():
    raw = sys.stdin.read()
    try:
        tool_name = json.loads(raw or "{}").get("tool_name", "")
    except (TypeError, ValueError):
        tool_name = ""
    script = "pre-write.py" if tool_name in {"apply_patch", "Write", "Edit"} else "pre-bash.py"
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), script)],
        input=raw,
        text=True,
        capture_output=True,
    )
    if result.returncode == 2:
        reason = result.stderr.strip() or "Blocked by codeArbiter policy"
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
