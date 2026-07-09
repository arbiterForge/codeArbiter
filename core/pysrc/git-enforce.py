#!/usr/bin/env python3
# codeArbiter — git-level enforcement backstop (#161).
#
# Installed into .git/hooks/pre-commit and .git/hooks/pre-push by _githooks.py.
# It runs at the GIT OPERATION itself, OUTSIDE Claude Code — so a commit built
# through shell indirection (`g=git; c=commit; $g $c -m x`) still triggers it,
# unlike the PreToolUse Bash hook (pre-bash.py), which only ever sees the literal
# command string and is defeated by variable/expansion spellings. The two layers
# are complementary: pre-bash.py gives fast, well-worded feedback on the common
# spellings; this is the spelling-proof backstop underneath.
#
# It mirrors pre-bash.py's commit/push gates and reuses the SAME detection
# primitives from _hooklib (CRYPTO_RE / SECRET_RE / line_digest / content_digest
# / is_migration_path / marker_fresh), so the two enforcement points can never
# drift on what counts as sensitive or as a migration, or on how a gate-pass
# marker binds to the lines it approved.
#
# Contract: a git hook aborts its operation on ANY non-zero exit, so a BLOCK is
# exit 1 with a loud stderr message. Exit 0 allows. The security/migration scans
# fail CLOSED on a git read error (pre-bash's "ambiguity resolves CLOSED"
# stance); a repo that is not arbiter-enabled is a no-op (exit 0).

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, arbiter_active, content_digest, is_migration_path,
    line_digest, marker_fresh, utf8_stdio,
)


def repo_root():
    """The repo THIS git hook is firing in — deliberately does NOT use
    _hooklib.project_root() (reliability-005, #190).

    git-enforce.py is installed as `.git/hooks/pre-commit`/`pre-push` of
    whatever repo the git OPERATION targets. _hooklib.project_root() trusts
    CLAUDE_PROJECT_DIR first — the right contract for a Claude Code hook
    subprocess, but the wrong one here: a `git -C ../otherRepo commit` issued
    from a Claude session inherits CLAUDE_PROJECT_DIR pointing at the
    session's repo, yet the pre-commit hook that fires is ../otherRepo's own,
    invoked with its OWN cwd/GIT_DIR — never the session's. Trusting
    CLAUDE_PROJECT_DIR here scanned the session's repo (branch/staged
    diff/markers) while the commit actually landed in ../otherRepo, both a
    fail-open (a dirty ../otherRepo passes if the session repo is clean) and
    a false-block (a dirty session repo blocks a clean ../otherRepo commit).

    Git invokes pre-commit/pre-push with the process cwd set to the target
    repo's work-tree top-level, so `git rev-parse --show-toplevel` run with NO
    cwd override (inheriting this process's actual cwd) resolves the repo the
    hook is actually running in. GIT_DIR/GIT_WORK_TREE (set by git for some
    invocation shapes, e.g. `git -C X commit` invoking the hook with those
    exported) are honored by that same `git rev-parse` call automatically, so
    no separate env read is needed here."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def _git(args, cwd):
    try:
        return subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except Exception:  # noqa: BLE001
        return None


def block(tag, msg):
    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)
    sys.exit(1)


# The most recent git-read failure, surfaced in the H-01 fail-closed block
# message — same rationale and format as pre-bash.py's _READ_ERRS: "git
# unavailable or timed out" alone is not enough evidence to root-cause a false
# block.
_READ_ERRS = []


def _note_read_err(argv, detail):
    _READ_ERRS.append(f"`{' '.join(argv)}` -> {(detail or '').strip()[:200]}")


def _read_err_hint():
    return f" Underlying git error: {_READ_ERRS[-1]}" if _READ_ERRS else ""


def is_protected_branch(branch):
    return (branch or "").lower() in ("main", "master")


def current_branch(cwd):
    """The current branch name, "" for a legitimate detached HEAD, or None when
    git could not answer (spawn failure/timeout/nonzero exit). reliability-001
    (#189): the None sentinel lets H-01 fail CLOSED on a git-read error instead
    of the prior `else ""`, which collapsed "unknown" and "detached, not on a
    protected tip" into the same value and let a commit through."""
    argv = ["branch", "--show-current"]
    r = _git(argv, cwd)
    if r is None or r.returncode != 0:
        _note_read_err(["git"] + argv, (r.stderr if r else None) or "git spawn failed")
        return None
    return r.stdout.strip()


def head_on_protected_tip(cwd):
    """True when HEAD (typically detached) points at a protected branch's tip —
    a commit there still lands on main/master's history. Mirrors pre-bash.py.

    reliability-001 (#189): returns None (not False) when git could not answer,
    so H-01 fails CLOSED on a git-read error rather than concluding "not on a
    protected tip" from a failed read."""
    argv = ["show-ref", "--head", "refs/heads/main", "refs/heads/master"]
    r = _git(argv, cwd)
    if r is None or r.returncode not in (0, 1):
        _note_read_err(["git"] + argv, (r.stderr if r else None) or "git spawn failed")
        return None
    head_sha, protected = None, set()
    for ln in r.stdout.splitlines():
        parts = ln.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == "HEAD":
            head_sha = sha
        elif ref in ("refs/heads/main", "refs/heads/master"):
            protected.add(sha)
    return head_sha is not None and head_sha in protected


def cached_added_lines(cwd):
    """Added (`+`) lines of the staged diff — exactly what a commit records
    (including `commit -a` sweeps, which git has already staged by pre-commit
    time). None on a git read error → caller fails closed."""
    r = _git(["diff", "--cached"], cwd)
    if r is None or r.returncode != 0:
        return None
    return [ln[1:] for ln in r.stdout.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")]


def cached_names(cwd):
    r = _git(["diff", "--cached", "--name-only"], cwd)
    if r is None or r.returncode != 0:
        return None
    return {p for p in r.stdout.splitlines() if p.strip()}


def read_worktree(cwd, rel):
    p = rel if os.path.isabs(rel) else os.path.join(cwd, rel)
    try:
        if os.path.getsize(p) > 1_000_000:
            return None
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def _marker_set(root, name):
    try:
        with open(os.path.join(root, ".codearbiter", ".markers", name),
                  encoding="utf-8") as f:
            return set(f.read().split())
    except Exception:  # noqa: BLE001
        return set()


def pre_commit(root):
    cwd = root
    # H-01: no commit onto a protected branch (or a detached HEAD on its tip).
    # A git-read failure fails CLOSED (reliability-001, #189) — the ambiguity
    # otherwise resolves to "not protected", the same hole H-09b/H-14 below
    # already close.
    branch = current_branch(cwd)
    if branch is None:
        block("H-01", "branch state could not be determined (git unavailable or timed "
                      "out) — failing closed (ORCHESTRATOR §2, #161 git backstop)." +
                      _read_err_hint())
    tip = None
    if not branch:
        tip = head_on_protected_tip(cwd)
        if tip is None:
            block("H-01", "HEAD's protected-branch-tip state could not be determined "
                          "(git unavailable or timed out) — failing closed (ORCHESTRATOR "
                          "§2, #161 git backstop)." + _read_err_hint())
    if is_protected_branch(branch) or (not branch and tip):
        target = branch or "main/master (detached HEAD)"
        block("H-01", f"Direct commit to {target} is prohibited (ORCHESTRATOR §3) — this is "
                      f"the git-level backstop (#161). Create a feature branch.")

    # H-09b / H-10b: a commit introducing crypto/secret changes needs a fresh,
    # line-covering security-gate pass. Reuses the exact _hooklib primitives.
    added = cached_added_lines(cwd)
    if added is None:
        block("H-09b", "the staged diff for the crypto/secret scan could not be read — "
                       "failing closed (ORCHESTRATOR §2).")
    sensitive = [ln for ln in added if CRYPTO_RE.search(ln) or SECRET_RE.search(ln)]
    if sensitive:
        joined = "\n".join(added)
        touches_crypto = bool(CRYPTO_RE.search(joined))
        kind = "crypto/TLS" if touches_crypto else "secret"
        tag = "H-09b" if touches_crypto else "H-10b"
        skill = "crypto-compliance" if touches_crypto else "secret-handling"
        marker = os.path.join(root, ".codearbiter", ".markers", "security-gate-passed")
        if not marker_fresh(marker, 30):
            block(tag, f"This commit introduces {kind} changes, but no security-gate pass is "
                       f"recorded (#161 git backstop). Run the {skill} gate, then commit.")
        approved = _marker_set(root, "security-gate-passed")
        uncovered = [ln for ln in sensitive if line_digest(ln) not in approved]
        if uncovered:
            block(tag, f"{len(uncovered)} {kind} line(s) in this commit are not covered by the "
                       f"recorded security-gate pass (#161 git backstop) — re-run the {skill} "
                       f"gate so it reviews the current diff, then commit.")

    # H-14: a staged migration needs a content-bound migration-review pass.
    names = cached_names(cwd)
    if names is None:
        block("H-14", "the staged file list for the migration scan could not be read — "
                      "failing closed (ORCHESTRATOR §2).")
    migs = sorted(p for p in names if is_migration_path(p, root))
    if migs:
        approved = _marker_set(root, "migration-gate-passed")
        uncovered = []
        for rel in migs:
            text = read_worktree(cwd, rel)
            if text is None or content_digest(text) not in approved:
                uncovered.append(rel)
        if uncovered:
            block("H-14", f"{len(uncovered)} staged migration file(s) lack a recorded "
                          f"migration-review pass (#161 git backstop): {', '.join(uncovered)}. "
                          f"Run the migration-review gate, then commit.")


def pre_push(root):
    cwd = root
    # Git feeds pre-push one line per ref: `<local ref> <local sha> <remote ref>
    # <remote sha>`. A deletion has an all-zero local sha; a create has an
    # all-zero remote sha.
    data = ""
    try:
        data = sys.stdin.read()
    except Exception:  # noqa: BLE001
        data = ""
    for ln in data.splitlines():
        parts = ln.split()
        if len(parts) < 4:
            continue
        _lref, lsha, rref, rsha = parts[0], parts[1], parts[2], parts[3]
        # H-01: no push whose destination is a protected branch (main/master),
        # in any refspec spelling — `HEAD:main`, `feature:main`, `:main`.
        if rref.startswith("refs/heads/") and is_protected_branch(rref.rsplit("/", 1)[-1]):
            block("H-01", f"Pushing to a protected branch ('{rref}') is prohibited "
                          f"(ORCHESTRATOR §3, #161 git backstop) — main moves only via a merged PR.")
        # H-02: no force / non-fast-forward update. Skip creates/deletes
        # (all-zero sha). A non-ff update is one where the remote sha is NOT an
        # ancestor of the local sha; treat an unresolvable check as force (closed).
        zero = lambda s: set(s) == {"0"}  # noqa: E731
        if lsha and rsha and not zero(lsha) and not zero(rsha):
            anc = _git(["merge-base", "--is-ancestor", rsha, lsha], cwd)
            if anc is None or anc.returncode != 0:
                block("H-02", "Force-push / non-fast-forward update is prohibited "
                              "(ORCHESTRATOR §3, #161 git backstop).")


def main():
    utf8_stdio()
    root = repo_root()
    if not arbiter_active(root):
        sys.exit(0)
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "pre-commit":
        pre_commit(root)
    elif phase == "pre-push":
        pre_push(root)
    # Unknown phase: no-op allow.
    sys.exit(0)


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through)."""
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
