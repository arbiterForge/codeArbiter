#!/usr/bin/env python3
# codeArbiter — standup hygiene parsers (sprint: session-hygiene, Feature 1).
#
# PURE functions only: no I/O, no subprocess, no os.environ. Each function takes
# the OUTPUT STRING of a git command and returns structured data. The git calls
# themselves happen elsewhere (a later task); keeping parsing pure makes every
# branch unit-testable from fixture strings, and keeps this module compliant with
# the stdlib-only / fail-loud hook posture.

import os

__all__ = [
    "parse_porcelain",
    "parse_ahead_behind",
    "merged_branch_candidates",
    "parse_worktrees",
    "parse_stash_count",
    "ff_pull_eligible",
    "stale_worktree_candidates",
    "any_actionable",
]


def parse_porcelain(text):
    """Parse `git status --porcelain=v1` output into a summary.

    Returns {"dirty": bool, "staged": int, "unstaged": int, "untracked": int}.

    Each status line is `XY <path>` where X is the index (staged) column and Y is
    the worktree (unstaged) column. A space means "no change" in that column.
    Untracked files use the `??` code and are counted separately (not as
    staged/unstaged). A file modified in both index and worktree (e.g. "MM")
    counts toward BOTH staged and unstaged. Empty/whitespace input is clean.
    """
    staged = unstaged = untracked = 0
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        code = raw[:2]
        if code == "??":
            untracked += 1
            continue
        x = code[0:1]
        y = code[1:2]
        if x and x != " " and x != "?":
            staged += 1
        if y and y != " " and y != "?":
            unstaged += 1
    dirty = (staged + unstaged + untracked) > 0
    return {
        "dirty": dirty,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def parse_ahead_behind(text):
    """Parse `git rev-list --left-right --count <upstream>...HEAD` output.

    The single output line is `<behind>\\t<ahead>` (left side = upstream-only
    commits = behind; right side = HEAD-only commits = ahead). Returns
    (behind, ahead). Empty or malformed (wrong field count, non-numeric) → (0, 0).
    """
    line = (text or "").strip()
    if not line:
        return (0, 0)
    parts = line.split()
    if len(parts) != 2:
        return (0, 0)
    try:
        behind = int(parts[0])
        ahead = int(parts[1])
    except ValueError:
        return (0, 0)
    return (behind, ahead)


def merged_branch_candidates(branch_vv_text, current, default):
    """Parse `git branch -vv` output for local branches safe to prune.

    PRUNE RULE (single, deterministic): a branch is a candidate iff its line shows
    its upstream is `gone` — i.e. it contains the `: gone]` marker that git prints
    when the tracked remote branch no longer exists (typically because the PR was
    merged and the remote branch deleted). The current branch (line begins with
    `* `) and the `default` branch (e.g. "main") are NEVER candidates, regardless
    of their upstream state. Order of first appearance is preserved.
    """
    candidates = []
    for raw in (branch_vv_text or "").splitlines():
        if not raw.strip():
            continue
        is_current = raw.startswith("* ")
        # Strip the `* ` / leading spaces marker, then the branch name is token 0.
        body = raw[2:] if is_current else raw.lstrip()
        tokens = body.split()
        if not tokens:
            continue
        name = tokens[0]
        if ": gone]" not in raw:
            continue
        if is_current or name == current or name == default:
            continue
        candidates.append(name)
    return candidates


def _strip_trailing_sep(path):
    """Drop a single trailing / or \\ so a repo_root with a trailing separator
    still matches the worktree path git reports (which has none)."""
    if path and path[-1] in ("/", "\\"):
        return path[:-1]
    return path


def parse_worktrees(porcelain_text, repo_root):
    """Parse `git worktree list --porcelain` output.

    Returns a list of {"path": str, "branch": str|None, "is_main": bool}. Records
    are separated by blank lines; each starts with a `worktree <path>` line and may
    carry a `branch refs/heads/<name>` line (absent / `detached` => branch None).
    The main worktree is the record whose path equals `repo_root` (trailing
    separator tolerated). Parses faithfully; staleness/merge classification is a
    later task's job.
    """
    root = _strip_trailing_sep(repo_root or "")
    out = []
    cur = None
    for raw in (porcelain_text or "").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            if cur is not None:
                out.append(cur)
                cur = None
            continue
        if line.startswith("worktree "):
            if cur is not None:
                out.append(cur)
            path = line[len("worktree "):].strip()
            cur = {"path": path, "branch": None, "is_main": path == root}
        elif line.startswith("branch ") and cur is not None:
            ref = line[len("branch "):].strip()
            cur["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        # HEAD / detached / bare / locked lines carry no fields we surface here.
    if cur is not None:
        out.append(cur)
    return out


def parse_stash_count(text):
    """Count stashes from `git stash list` output (one stash per line). Empty → 0."""
    return sum(1 for ln in (text or "").splitlines() if ln.strip())


def ff_pull_eligible(porcelain_text, behind):
    """SH-6: True iff a fast-forward pull should be OFFERED — the working tree is
    CLEAN (no staged/unstaged/untracked changes per parse_porcelain) AND we are
    behind (`behind > 0`). A dirty tree withholds the offer (a ff-pull on a dirty
    tree is unsafe); behind == 0 means there is nothing to pull. PURE: porcelain
    OUTPUT STRING + behind count in, bool out. This only IDENTIFIES eligibility;
    it never pulls — the /ca:standup command acts on explicit user confirmation."""
    if behind <= 0:
        return False
    return not parse_porcelain(porcelain_text)["dirty"]


def stale_worktree_candidates(worktrees, gone_or_merged_branches, path_exists=os.path.exists):
    """SD-B1: from parsed `worktrees` (parse_worktrees output) plus the set of
    branch names that are gone/merged on the remote, return the NON-MAIN worktrees
    that are STALE CANDIDATES. A worktree is stale iff its branch is in
    `gone_or_merged_branches` OR its path no longer exists on disk. The main
    worktree (is_main) is NEVER a candidate. Order of input is preserved.

    `path_exists(path) -> bool` is injectable so the disk check is deterministic in
    tests (pass a fake predicate); production defaults to os.path.exists. This is a
    PURE classifier: it only IDENTIFIES candidates and removes/mutates nothing —
    the /ca:standup command removes a worktree only on explicit per-item user
    confirmation, which is why the broad (gone OR missing) candidate rule is safe."""
    gone = gone_or_merged_branches or set()
    out = []
    for wt in worktrees or []:
        if wt.get("is_main"):
            continue
        branch = wt.get("branch")
        path = wt.get("path")
        is_stale = (branch in gone) or (not path_exists(path))
        if is_stale:
            out.append(wt)
    return out


def any_actionable(summary):
    """True if the assembled briefing summary has ANY actionable condition.

    Drives the "emit an offer line only if actionable" behavior. Triggers: a dirty
    tree, behind > 0, ahead/unpushed > 0, non-empty prune_candidates, non-empty
    stale_worktrees, or stashes > 0. Missing keys default to falsy.
    """
    s = summary or {}
    if s.get("dirty"):
        return True
    if (s.get("behind") or 0) > 0:
        return True
    if (s.get("ahead") or 0) > 0:
        return True
    if (s.get("unpushed") or 0) > 0:
        return True
    if s.get("prune_candidates"):
        return True
    if s.get("stale_worktrees"):
        return True
    if (s.get("stashes") or 0) > 0:
        return True
    return False
