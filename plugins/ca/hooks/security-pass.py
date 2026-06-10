#!/usr/bin/env python3
# codeArbiter v2 — record a security-gate pass BOUND to the lines it approved.
#
# The crypto-compliance / secret-handling skills (and /ca:override's heavier
# security ceiling) run this ON PASS, replacing the old `touch` of an empty
# marker. An empty marker only proved that *some* gate passed *recently*; any
# different crypto/secret change committed inside the 30-minute freshness
# window rode through on it (a TOCTOU hole). This helper hashes every added
# line in the working tree (vs HEAD, plus untracked files) that matches the
# shared CRYPTO_RE/SECRET_RE and writes the digests to
# .codearbiter/.markers/security-gate-passed; pre-bash.py H-09b/H-10b then
# admits a commit only when every sensitive line being committed is in the
# recorded set.
#
# Invoked by skill prose as:
#   python3 "<plugin>/hooks/security-pass.py" || python "<plugin>/hooks/security-pass.py"
# (same interpreter-fallback shape as hooks.json; rerun-safe — recording is
# idempotent).

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, line_digest, project_root, utf8_stdio, warn,
)

MAX_UNTRACKED_BYTES = 1_000_000  # an untracked blob bigger than this is not reviewable prose


def run_git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


def file_lines(root, rel):
    p = os.path.join(root, rel)
    try:
        if os.path.getsize(p) > MAX_UNTRACKED_BYTES:
            return []
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:  # noqa: BLE001
        return []


def candidate_lines(root):
    """Every line the next commit could introduce: added lines of the
    worktree-vs-HEAD diff (staged and unstaged alike), plus the full content
    of untracked files — `git diff HEAD` never shows those, but they land in
    the staged diff the moment commit-gate stages them."""
    lines = []
    diff = run_git(["diff", "HEAD"], root)
    if diff.returncode == 0:
        lines += [ln[1:] for ln in diff.stdout.splitlines()
                  if ln.startswith("+") and not ln.startswith("+++")]
    else:
        # Unborn branch (no HEAD yet): every tracked file is new content.
        ls = run_git(["ls-files"], root)
        for rel in ls.stdout.splitlines():
            lines += file_lines(root, rel)
    untracked = run_git(["ls-files", "--others", "--exclude-standard"], root)
    for rel in untracked.stdout.splitlines():
        lines += file_lines(root, rel)
    return lines


def main():
    utf8_stdio()
    root = project_root()
    if not os.path.isdir(os.path.join(root, ".codearbiter")):
        warn("no .codearbiter/ here — security-pass.py records nothing outside "
             "an initialized repo")
        sys.exit(1)
    sensitive = [ln for ln in candidate_lines(root)
                 if CRYPTO_RE.search(ln) or SECRET_RE.search(ln)]
    marker_dir = os.path.join(root, ".codearbiter", ".markers")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "security-gate-passed")
    digests = sorted({line_digest(ln) for ln in sensitive})
    with open(marker, "w", encoding="utf-8") as f:
        f.write("\n".join(digests) + ("\n" if digests else ""))
    print(f"security-gate pass recorded: {len(digests)} sensitive line(s) "
          f"bound to {os.path.relpath(marker, root)}")


if __name__ == "__main__":
    main()
