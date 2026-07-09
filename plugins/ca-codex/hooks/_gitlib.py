#!/usr/bin/env python3
# codeArbiter — statusline git-context helpers (extracted from statusline.py,
# architecture-004).
#
# Owns resolving the project root (walking up for .git or .codearbiter), reading
# the current branch straight off .git/HEAD (no git binary needed for the common
# case), and a `git status --porcelain` dirty check. Also reused by session-start.py
# (statusline.head_branch) so the two hooks agree on branch resolution.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed input — degrade to a safe default (None/False).
#
# Public API:
#   project_root(data) -> str          nearest ancestor with .git or .codearbiter
#   head_branch(root) -> str|None      current branch (or short sha if detached)
#   git_dirty(root) -> bool            True if `git status --porcelain` is non-empty

import os
import subprocess


def get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    return cur


def project_root(data):
    pd = (get(data, "workspace", "project_dir")
          or get(data, "workspace", "current_dir")
          or get(data, "cwd") or os.getcwd())
    cur = os.path.abspath(pd)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isdir(os.path.join(cur, ".codearbiter")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(pd)
        cur = parent


def head_branch(root):
    try:
        with open(os.path.join(root, ".git", "HEAD"), encoding="utf-8", errors="replace") as f:
            ref = f.read().strip()
        if ref.startswith("ref:"):
            name = ref.split(" ", 1)[1].strip() if " " in ref else ref[4:].strip()
            for p in ("refs/heads/", "refs/remotes/", "refs/tags/"):
                if name.startswith(p):
                    return name[len(p):]
            return name
        return ref[:7]   # detached HEAD -> short sha
    except OSError:
        return None


def git_dirty(root):
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=1.5,
                             encoding="utf-8", errors="replace")
        return bool((out.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return False
