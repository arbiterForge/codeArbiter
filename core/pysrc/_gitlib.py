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


# Statusline rendering is UI-critical and runs in a fresh process per refresh.
# Keep the full porcelain semantics, but never let the dirty probe stall the UI.
DIRTY_CHECK_TIMEOUT_SECONDS = 0.1


def _valid_ref_name(name):
    """Return whether *name* follows Git's safe reference-name shape."""
    if (not name or name == "@" or name.startswith("/") or name.endswith("/")
            or ".." in name or "@{" in name or "//" in name):
        return False
    if any(ord(ch) <= 32 or ord(ch) == 127 or ch in "~^:?*[\\" for ch in name):
        return False
    return all(part and not part.startswith(".") and not part.endswith(".")
               and not part.endswith(".lock") for part in name.split("/"))


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
        git_meta = os.path.join(cur, ".git")
        if (os.path.isdir(git_meta) or os.path.isfile(git_meta)
                or os.path.isdir(os.path.join(cur, ".codearbiter"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(pd)
        cur = parent


def head_branch(root):
    try:
        git_meta = os.path.join(root, ".git")
        if os.path.isfile(git_meta):
            with open(git_meta, encoding="utf-8", errors="replace") as f:
                pointer = f.read().rstrip("\r\n")
            if not pointer.startswith("gitdir: "):
                return None
            git_dir = pointer[len("gitdir: "):]
            if not git_dir:
                return None
            if not os.path.isabs(git_dir):
                git_dir = os.path.normpath(os.path.join(os.path.dirname(git_meta), git_dir))
        else:
            git_dir = git_meta
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8", errors="replace") as f:
            ref = f.read().rstrip("\r\n")
        if not ref:
            return None
        if ref.startswith("ref: "):
            name = ref[len("ref: "):]
            if not _valid_ref_name(name):
                return None
            for p in ("refs/heads/", "refs/remotes/", "refs/tags/"):
                if name.startswith(p):
                    return name[len(p):]
            return name
        if len(ref) not in (40, 64) or any(ch not in "0123456789abcdefABCDEF" for ch in ref):
            return None
        return ref[:7]   # detached HEAD -> short sha
    except OSError:
        return None


def git_dirty(root):
    """Return dirty state, suppressing the marker when Git fails or times out."""
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                             capture_output=True, text=True,
                             timeout=DIRTY_CHECK_TIMEOUT_SECONDS,
                             encoding="utf-8", errors="replace")
        return out.returncode == 0 and bool((out.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return False
