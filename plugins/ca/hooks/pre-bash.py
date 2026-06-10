#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Bash|PowerShell) guard. Branch/push/staging +
# security gate. Python port of pre-bash.sh (issues #24, #25): no jq, fails
# loud, blocks via exit 2. Adds H-09b/H-10b — a BLOCKING crypto/secret commit
# gate (#24): the prior post-write reminder was advisory only, so a routine
# commit could ship crypto/secret changes without the gate ever running.
#
# All guards run only in arbiter-enabled repos (the plugin.json activation
# contract); elsewhere this exits 0 immediately.

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, arbiter_active, block, marker_fresh, project_root,
    read_input, tool_input, utf8_stdio,
)

# `git` followed by any run of global options (-C <dir>, -c k=v, --git-dir=…,
# --no-pager, …) before the subcommand — `git -C ../x commit` must not slip
# past a bare `git\s+commit` match.
GIT = r"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?|-\w+))*"
COMMIT_RE = re.compile(GIT + r"\s+commit\b(?P<args>[^|;&]*)")
PUSH_RE = re.compile(GIT + r"\s+push\b(?P<args>[^|;&]*)")
ADD_RE = re.compile(GIT + r"\s+add\b(?P<args>[^|;&]*)")
GIT_C_DIR_RE = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
# Force-push in any spelling: --force, --force-with-lease[=…], -f as its own
# token (not a ref like `fix-f`), or a forcing `+refspec`.
FORCE_RE = re.compile(r"(?:^|\s)(?:--force(?:-with-lease|-if-includes)?(?:=\S+)?|-f)(?=\s|$)")
FORCE_REFSPEC_RE = re.compile(r"\s\+[\w./:~^-]+")
WILDCARD_ADD_RE = re.compile(r"(?:^|\s)(?:-A|--all|\.)(?=\s|$)")
COMMIT_ALL_RE = re.compile(r"(?:^|\s)(?:-[a-zA-Z]*a[a-zA-Z]*|--all)(?=\s|$)")
# Truncation (`>` but not `>>`) or destructive verbs aimed at an audit log
# (overrides.log, triage.log — both append-only).
LOG_TRUNC_RE = re.compile(r"(?<!>)>(?!>)\s*\S*(?:overrides|triage)\.log")
LOG_DESTROY_RE = re.compile(
    r"\b(rm|del|mv|Remove-Item|Move-Item|Clear-Content|Set-Content|Out-File)\b"
    r"[^|;&]*(?:overrides|triage)\.log", re.I,
)


def git_cwd(cmd, root):
    """The directory a `git -C <dir>` invocation actually targets."""
    m = GIT_C_DIR_RE.search(cmd)
    if not m:
        return root
    return m.group(1).strip("\"'")


def current_branch(cwd):
    try:
        out = subprocess.run(
            ["git", "branch", "--show-current"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def added_lines(cwd, ref):
    """The added (`+`) lines of a diff — what a commit would introduce."""
    try:
        out = subprocess.run(
            ["git", "diff", ref], cwd=cwd,
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
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    cmd = tool_input(read_input()).get("command", "") or ""

    commit = COMMIT_RE.search(cmd)
    cwd = git_cwd(cmd, root)

    # H-01: no commit directly to main/master
    if commit:
        branch = current_branch(cwd)
        if branch in ("main", "master"):
            block("H-01", f"Direct commit to {branch} is prohibited (ORCHESTRATOR §3). "
                          f"Create a feature branch.")

    # H-02: no force-push — any spelling, including --force-with-lease and +refspec
    push = PUSH_RE.search(cmd)
    if push and (FORCE_RE.search(push.group("args")) or FORCE_REFSPEC_RE.search(push.group("args"))):
        block("H-02", "Force-push is prohibited (ORCHESTRATOR §3).")

    # H-03: no wildcard git staging — stage explicitly (commit-gate)
    add = ADD_RE.search(cmd)
    if add and WILDCARD_ADD_RE.search(add.group("args")):
        block("H-03", "'git add -A' / 'git add .' / 'git add --all' are prohibited. "
                      "Stage files explicitly (commit-gate skill).")

    # H-05: the audit trail is append-only — block truncation/removal of
    # overrides.log via shell verbs (Write/Edit are guarded separately).
    if ("overrides.log" in cmd or "triage.log" in cmd) and (
            LOG_TRUNC_RE.search(cmd) or LOG_DESTROY_RE.search(cmd)):
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log) are append-only "
                      "(ORCHESTRATOR §7). Truncating, overwriting, or deleting the audit trail "
                      "is prohibited; append with '>>' only.")

    # H-09b / H-10b: BLOCK a commit that introduces crypto/secret changes without
    # a recorded security-gate pass. The crypto-compliance / secret-handling skills
    # drop `.codearbiter/.markers/security-gate-passed` when they pass; a security
    # gate is NOT bypassable by a plain commit. Scans the staged diff, plus the
    # worktree diff when the commit uses -a/--all or the same command stages files
    # (`git add x && git commit`) — both land content this hook would otherwise
    # never see (the hook runs before the `add` executes).
    if commit:
        added = added_lines(cwd, "--cached")
        if COMMIT_ALL_RE.search(commit.group("args")) or add:
            added += "\n" + added_lines(cwd, "HEAD")
        touches_crypto = bool(CRYPTO_RE.search(added))
        touches_secret = bool(SECRET_RE.search(added))
        if touches_crypto or touches_secret:
            marker = os.path.join(root, ".codearbiter", ".markers", "security-gate-passed")
            if not marker_fresh(marker, 30):
                kind = "crypto/TLS" if touches_crypto else "secret"
                tag = "H-09b" if touches_crypto else "H-10b"
                block(tag, f"This commit introduces {kind} changes, but no security-gate pass is "
                           f"recorded (.codearbiter/.markers/security-gate-passed). Run the "
                           f"{'crypto-compliance' if touches_crypto else 'secret-handling'} gate "
                           f"(it records the pass), then commit. To bypass a security gate, "
                           f"/override requires its heavier security-acknowledgement path.")

    sys.exit(0)


if __name__ == "__main__":
    main()
