#!/usr/bin/env python3
# codeArbiter — durable-vs-ephemeral install-root detection.
#
# WHY THIS EXISTS (found in-session on 2026-07-25, after it broke the
# maintainer's statusline three times in one day):
#
# A plugin cannot own a statusLine and ${CLAUDE_PLUGIN_ROOT} is NOT expanded
# inside settings.json, so codeArbiter has to write an ABSOLUTE, version-pinned
# renderer path into the user's GLOBAL ~/.claude/settings.json — and re-point it
# on every SessionStart so a plugin update does not leave the old version wired.
# That refresh had no notion of a root that will not survive the session. When a
# session starts inside a git worktree (subagents routinely run in
# <repo>/.claude/worktrees/<id>/), the plugin root IS the worktree's plugins/ca,
# and the heal happily pinned the user's global config there:
#
#   "...\.claude\worktrees\wf_58ee3fa6-de1-8\plugins\ca\hooks\statusline.py"
#
# The worktree is then pruned — that is what worktrees are FOR — and the
# statusline renders nothing until someone notices and re-runs /ca:statusline.
#
# This module answers exactly one question, for callers about to write a path
# into a long-lived config: may this path be trusted to still be there?
#
# TWO INDEPENDENT SIGNALS, because each alone has a blind spot:
#   1. LEXICAL (has_worktree_segment) — a `worktrees` or `*-worktrees` path
#      segment. Free, no I/O at all, works even when the checkout is already
#      gone. Covers the confirmed `.claude/worktrees/<id>/` case and the
#      `../.codearbiter-worktrees/<slug>` layout the using-git-worktrees skill
#      creates.
#   2. GIT (in_linked_worktree) — the path lives in a LINKED worktree, read
#      straight off git's own on-disk marker. Generalizes to a worktree parked
#      anywhere under any name, which the lexical rule cannot see.
#
# NO SUBPROCESS, DELIBERATELY. This predicate is consulted on EVERY SessionStart,
# before the dormant gate, in every repo on the machine. An earlier draft shelled
# out to `git rev-parse --git-dir --git-common-dir`; that probe fails by design
# in the ordinary plugin-cache install (which is not a git repository at all), so
# it bought nothing in the common case while charging every session a process
# spawn plus a timeout hazard. Git writes the answer to disk anyway: a LINKED
# worktree's `.git` is a FILE reading `gitdir: <common>/.git/worktrees/<name>`,
# while a normal checkout's `.git` is a DIRECTORY. A handful of stat() calls
# gives the same answer, with no dependency on git being installed at all.
#
# FAILURE DIRECTION IS "DURABLE", DELIBERATELY. Anything unreadable, unparseable
# or absent reads as durable. Reading uncertainty as "ephemeral" would silently
# disable the self-heal for users whose installs are perfectly fine — a far worse
# outcome than the residual it protects against.
#
# The lexical rule is deliberately a little broad (any `worktrees` segment, not
# only one under `.claude`). The asymmetry justifies it: a false positive costs
# an un-refreshed pin the user fixes with one explicit /ca:statusline run, while
# a false negative corrupts their global config.
#
# Design principles (mirroring _gitexec.py / _gitlib.py):
#   - Stdlib only; no third-party imports ever (ADR-0004).
#   - Zero side effects at import time.
#   - NEVER raises. This sits on the SessionStart path; it must not be the thing
#     that crashes startup, whatever it is handed.
#
# Public API:
#   has_worktree_segment(path) -> bool   lexical signal, no I/O
#   in_linked_worktree(path) -> bool     git's on-disk marker, no subprocess
#   is_ephemeral_path(path) -> bool      either signal

import os
import re

# The walk from a plugin root to the filesystem root is a handful of levels; the
# bound exists only so a pathological path can never spin this on the hot path.
MAX_ANCESTOR_WALK = 64

# A `.git` FILE is at most a line or two. Reading a bounded prefix means a
# directory entry that is unexpectedly enormous cannot stall startup.
GITFILE_READ_BYTES = 4096

_SEP_RE = re.compile(r"[\\/]+")


def _segments(path):
    """Path segments of `path`, split on BOTH separators (a Windows path may be
    read from a POSIX host and vice versa). Empty tuple on any non-string."""
    if not isinstance(path, str) or not path:
        return ()
    return tuple(part for part in _SEP_RE.split(path) if part)


def has_worktree_segment(path):
    """True iff `path` contains a segment named `worktrees` or `*-worktrees`
    (case-insensitive). Purely lexical — no filesystem access, no subprocess.

    Matches `<repo>/.claude/worktrees/<id>/...` (Claude Code's own subagent
    worktrees) and `../.codearbiter-worktrees/<slug>/...` (the
    using-git-worktrees skill). Compares whole SEGMENTS, never substrings: a
    directory literally called `worktrees-archive` is a name of its own, not a
    container of worktrees, and matching it would decline to heal a perfectly
    durable root."""
    for part in _segments(path):
        low = part.lower()
        if low == "worktrees" or low.endswith("-worktrees"):
            return True
    return False


def _ancestors(path):
    """`path` (or its directory, if it names a file) and every parent above it,
    nearest first, bounded by MAX_ANCESTOR_WALK. Yields nothing for junk."""
    if not isinstance(path, str) or not path:
        return
    try:
        cur = os.path.abspath(path)
        if not os.path.isdir(cur):
            cur = os.path.dirname(cur)
    except Exception:  # noqa: BLE001 — a probe must never crash its caller
        return
    for _ in range(MAX_ANCESTOR_WALK):
        if not cur:
            return
        yield cur
        parent = os.path.dirname(cur)
        if parent == cur:  # filesystem root: dirname is a fixed point
            return
        cur = parent


def _gitfile_points_at_worktree(gitfile):
    """True iff the `.git` FILE at `gitfile` is a LINKED WORKTREE pointer.

    Git writes `gitdir: <path>` into `.git` for both linked worktrees and
    submodules, and the two must not be confused: a worktree points into
    `<common>/.git/worktrees/<name>` (disposable), a submodule into
    `<super>/.git/modules/<name>` (an ordinary long-lived checkout). The
    `worktrees` segment in the TARGET is what separates them."""
    try:
        with open(gitfile, "rb") as f:
            head = f.read(GITFILE_READ_BYTES)
        lines = head.decode("utf-8", "replace").splitlines()
        if not lines:
            return False
        first = lines[0].strip()
        if not first.lower().startswith("gitdir:"):
            return False
        # split(":", 1) — the FIRST colon only, so a Windows target like
        # `C:/Users/...` survives intact.
        return has_worktree_segment(first.split(":", 1)[1].strip())
    except Exception:  # noqa: BLE001 — unreadable reads as durable, by design
        return False


def in_linked_worktree(path):
    """True iff `path` sits inside a LINKED git worktree.

    Walks up from `path` to the first `.git` it meets — the boundary of the
    repository the path actually belongs to — and decides there:
      - `.git` is a DIRECTORY -> the main worktree. Durable. Stop.
      - `.git` is a FILE      -> a linked worktree or a submodule; the pointer's
                                 target says which. Stop either way.
      - no `.git` at any level -> not in a repository at all (the ordinary
                                 plugin-cache install). Durable.
    Stopping at the NEAREST boundary is load-bearing: a real checkout nested
    below some unrelated worktree marker must read as durable.

    `path` may name a file (its directory is walked) or a directory, and need
    not exist. Never raises."""
    try:
        for cur in _ancestors(path):
            gitpath = os.path.join(cur, ".git")
            if os.path.isdir(gitpath):
                return False
            if os.path.isfile(gitpath):
                return _gitfile_points_at_worktree(gitpath)
        return False
    except Exception:  # noqa: BLE001 — a probe must never crash its caller
        return False


def is_ephemeral_path(path):
    """True iff `path` must NOT be pinned into a long-lived global config.

    Checks the free lexical signal FIRST and short-circuits on it, so the
    confirmed production case is decided with zero I/O. Never raises."""
    try:
        if has_worktree_segment(path):
            return True
        return in_linked_worktree(path)
    except Exception:  # noqa: BLE001 — a probe must never crash its caller
        return False
