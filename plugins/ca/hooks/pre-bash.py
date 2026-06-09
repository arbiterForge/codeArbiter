#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Bash) guard. Branch/push/staging + security gate.
# Python port of pre-bash.sh (issues #24, #25): no jq, fails loud, blocks via
# exit 2. Adds H-09b/H-10b — a BLOCKING crypto/secret commit gate (#24): the
# prior post-write reminder was advisory only, so a routine commit could ship
# crypto/secret changes without the gate ever running.

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, block, marker_fresh, project_root, read_input, tool_input,
)


def current_branch():
    try:
        out = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def staged_added_lines(root):
    """The added (`+`) lines of the staged diff — what this commit introduces."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached"], cwd=root,
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(
        line[1:] for line in out.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def main():
    cmd = tool_input(read_input()).get("command", "") or ""

    # H-01: no commit directly to main/master
    if re.search(r"git\s+commit", cmd):
        branch = current_branch()
        if branch in ("main", "master"):
            block("H-01", f"Direct commit to {branch} is prohibited (ORCHESTRATOR §3). "
                          f"Create a feature branch.")

    # H-02: no force-push
    if re.search(r"git\s+push.*(--force|-f)(\s|$)", cmd):
        block("H-02", "Force-push is prohibited (ORCHESTRATOR §3).")

    # H-03: no wildcard git staging — stage explicitly (commit-gate)
    if re.search(r"git\s+add\s+(-A|\.)(\s|$)", cmd):
        block("H-03", "'git add -A' / 'git add .' are prohibited. Stage files "
                      "explicitly (commit-gate skill).")

    # H-09b / H-10b: BLOCK a commit that stages crypto/secret changes without a
    # recorded security-gate pass. The crypto-compliance / secret-handling skills
    # drop `.codearbiter/.markers/security-gate-passed` when they pass; a security
    # gate is NOT bypassable by a plain commit.
    if re.search(r"git\s+commit", cmd):
        root = project_root()
        added = staged_added_lines(root)
        touches_crypto = bool(CRYPTO_RE.search(added))
        touches_secret = bool(SECRET_RE.search(added))
        if touches_crypto or touches_secret:
            marker = os.path.join(root, ".codearbiter", ".markers", "security-gate-passed")
            if not marker_fresh(marker, 30):
                kind = "crypto/TLS" if touches_crypto else "secret"
                tag = "H-09b" if touches_crypto else "H-10b"
                block(tag, f"Staged changes touch {kind}, but no security-gate pass is "
                           f"recorded (.codearbiter/.markers/security-gate-passed). Run the "
                           f"{'crypto-compliance' if touches_crypto else 'secret-handling'} gate "
                           f"(it records the pass), then commit. To bypass a security gate, "
                           f"/override requires its heavier security-acknowledgement path.")

    sys.exit(0)


if __name__ == "__main__":
    main()
