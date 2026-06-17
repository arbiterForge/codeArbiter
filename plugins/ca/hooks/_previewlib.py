#!/usr/bin/env python3
# codeArbiter — preview helpers (issue #81, /ca:preview).
#
# A library beside _hooklib.py, NOT a hook: it exposes building blocks the
# /ca:preview command composes (T-03 here covers diff collection only; the
# secret scan and test-gap detection are later tasks). Same house style as
# _hooklib.py: stdlib only (ADR-0004), no network, and every git invocation
# goes through one capture_output/text/utf-8/timeout subprocess.run wrapper so
# Windows pipe encoding never surprises us.
#
# collect_diff is strictly READ-ONLY: it runs only inspecting git commands
# (rev-parse, diff --name-only, ls-files) and writes nothing to the worktree,
# the index, or disk.

import os
import re
import subprocess
import sys
from collections import namedtuple

# Reuse the ONE secret pattern defined in _hooklib.py — never a second copy, so
# the preview scan and the commit-time gate (H-10b) can never drift apart.
# _hooklib sits beside this file; ensure that dir is importable the same way the
# test harness mounts it (sys.path.insert of the hooks dir), then import the
# regex by reference.
_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
from _hooklib import SECRET_RE  # noqa: E402 — needs the sys.path mount above

# One changed file. `path` is repo-relative with forward slashes (so later
# content scans and reporting are platform-stable). `kinds` is the set of
# change categories the file appears under — a file can be both staged and
# modified-unstaged at once, and we keep all of them rather than collapsing.
ChangedFile = namedtuple("ChangedFile", ["path", "kinds"])

# One secret hit: `path` is the repo-relative (forward-slash) changed file,
# `line_no` is 1-based, `snippet` is the matching line with the credential
# VALUE masked (keyword/operator/quoting preserved for context) and trailing
# whitespace stripped so reporting is stable across CRLF/LF worktrees. The
# snippet never carries the plaintext secret value.
SecretFinding = namedtuple("SecretFinding", ["path", "line_no", "snippet"])

# Change categories used in ChangedFile.kinds.
KIND_UNSTAGED = "unstaged"   # tracked, differs from HEAD in the worktree
KIND_STAGED = "staged"       # staged in the index vs HEAD
KIND_UNTRACKED = "untracked"  # new file git is not yet tracking

# Skip files larger than this before reading them. Kept in lockstep with
# security-pass.py's MAX_UNTRACKED_BYTES (1_000_000): a blob bigger than this is
# not reviewable prose, and a preview must not slurp a giant file into memory.
# Oversize files are skipped exactly like binary/unreadable ones — no raise.
MAX_SCAN_BYTES = 1_000_000

# The credential value run inside a SECRET_RE hit, masked before the snippet
# leaves scan_secrets so the plaintext secret never rides out in preview data.
# Matches the keyword=open-quote prefix (captured group 1) and the value run up
# to the closing quote or end of line; the value is replaced by the mask while
# the keyword, operator, and quoting structure are preserved for context.
_SECRET_VALUE_RE = re.compile(
    r"""(\b(?:password|secret|token|api_key|apikey|private_key|passphrase"""
    r"""|credential)\s*=\s*["'])([^"']{4,})""",
    re.I,
)
_SECRET_MASK = "****"


def _redact_secret(line):
    """Mask the credential value inside a matched line so the returned snippet
    keeps useful context (keyword + quoting) but never carries the plaintext
    secret value. Convention mirrors security-pass.py: the raw sensitive value
    is never echoed back out — here it is replaced in place by _SECRET_MASK."""
    return _SECRET_VALUE_RE.sub(lambda m: m.group(1) + _SECRET_MASK, line)


def _git(args, root):
    """Run a read-only git command in `root`. Returns the CompletedProcess, or
    None if git could not be invoked at all (missing binary, timeout). Never
    raises — callers branch on returncode/None, matching the fail-without-stack
    posture the non-repo edge requires."""
    try:
        return subprocess.run(
            ["git"] + args, cwd=root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
    except Exception:  # noqa: BLE001 — missing git, timeout, etc.
        return None


def _is_repo(root):
    """True iff `root` is inside a git work tree. Detected by the exit code of
    `git rev-parse --is-inside-work-tree` (non-zero -> not a repo), NOT by
    catching a stack trace from a later command."""
    r = _git(["rev-parse", "--is-inside-work-tree"], root)
    return bool(r) and r.returncode == 0 and r.stdout.strip() == "true"


def _name_lines(result):
    """Non-empty, slash-normalized paths from a `--name-only` style output."""
    if not result or result.returncode != 0:
        return []
    return [
        ln.strip().replace("\\", "/")
        for ln in result.stdout.splitlines()
        if ln.strip()
    ]


def collect_diff(root=None):
    """Collect the changed files in a working tree, unioned across three kinds.

    Args:
        root: directory to inspect; defaults to the current working directory.

    Returns:
        dict mapping each changed repo-relative path (forward slashes) to a
        ChangedFile(path, kinds), where `kinds` is the set of categories the
        file falls under (any of KIND_UNSTAGED / KIND_STAGED / KIND_UNTRACKED).
        A file changed in more than one way (e.g. staged AND further modified)
        carries all matching kinds. Empty dict when `root` is not a git repo or
        the tree is clean — never raises for those edges.

    Read-only: runs only `git rev-parse`, `git diff --name-only`, and
    `git ls-files`; writes nothing.
    """
    if root is None:
        root = os.getcwd()

    if not _is_repo(root):
        return {}

    sources = (
        # tracked changes vs HEAD, present in the worktree but not staged
        (KIND_UNSTAGED, ["diff", "--name-only", "HEAD"]),
        # tracked changes staged in the index vs HEAD
        (KIND_STAGED, ["diff", "--cached", "--name-only"]),
        # files git is not tracking yet, honouring .gitignore
        (KIND_UNTRACKED, ["ls-files", "--others", "--exclude-standard"]),
    )

    found = {}
    for kind, args in sources:
        for path in _name_lines(_git(args, root)):
            entry = found.get(path)
            if entry is None:
                found[path] = ChangedFile(path=path, kinds={kind})
            else:
                entry.kinds.add(kind)
    return found


def scan_secrets(root=None):
    """Scan every changed file's current worktree content for credential lines.

    For each path from collect_diff(root), read the file as text (read-only) and
    report every line matching the shared _hooklib.SECRET_RE.

    Args:
        root: directory to inspect; defaults to the current working directory.

    Returns:
        list of SecretFinding(path, line_no, snippet). `path` is repo-relative
        with forward slashes (as collect_diff yields it); `line_no` is 1-based.
        Empty list when nothing matches, when `root` is not a repo, or when the
        tree is clean.

    Strictly READ-ONLY: opens files for reading only and writes nothing. Files
    that cannot be read as text (binary, deleted, permission-denied) are skipped
    silently rather than raising — a preview must never crash on the worktree it
    is merely describing.
    """
    if root is None:
        root = os.getcwd()

    findings = []
    for path in collect_diff(root):
        abspath = os.path.join(root, path)
        try:
            # Size cap first, so an oversize blob is skipped before we read it
            # (consistent with security-pass.py's MAX_UNTRACKED_BYTES). Treated
            # like binary/unreadable files: skipped, never raised.
            if os.path.getsize(abspath) > MAX_SCAN_BYTES:
                continue
            with open(abspath, "r", encoding="utf-8", errors="strict") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            # Deleted/unreadable (OSError) or binary/non-UTF-8 (UnicodeDecodeError):
            # skip without raising. errors="strict" makes binary blobs raise here
            # rather than yielding mojibake we might then false-positive on.
            continue
        for i, line in enumerate(lines, start=1):
            if SECRET_RE.search(line):
                # Mask the credential value before it leaves the function: the
                # snippet keeps keyword/quoting context but never the plaintext.
                findings.append(
                    SecretFinding(
                        path=path, line_no=i,
                        snippet=_redact_secret(line).rstrip(),
                    )
                )
    return findings
