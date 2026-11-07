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
# / is_migration_path / sensitive_scan_added_lines), so the two
# enforcement points can never drift on what counts as sensitive or as a
# migration, on how a gate-pass marker binds to the lines it approved, or on
# which path (gate-events.log, #279) is exempt from the sensitive-line scan.
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
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _gitexec import (  # noqa: E402
    binary_candidate_binding, git_executable, read_head_blob_digest,
    git_read_error_summary, read_index_text, root_bound_git_env,
    staged_changes,
)
from _hooklib import (  # noqa: E402
    BINARY_SECURITY_CONTEXT, BinarySecurityContext, CRYPTO_RE, SECRET_RE, SECURITY_DIFF_GIT_ARGS,
    arbiter_active, binary_override_binding, binary_security_recovery, content_digest, is_migration_path, line_digest,
    migration_candidate_binding, migration_gate_recovery, security_finding_summary,
    mixed_binary_security_recovery,
    security_gate_recovery,
    security_scan_diff,
    set_host, utf8_stdio, worktree_marker_binding,
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
            [git_executable(), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def _git_read(args, cwd):
    try:
        return subprocess.run(
            [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        ), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except PermissionError:
        return None, "access"
    except FileNotFoundError:
        return None, "spawn"
    except UnicodeError:
        return None, "output"
    except (OSError, subprocess.SubprocessError):
        return None, "failure"
    except Exception:  # noqa: BLE001 — fail closed with a sanitized recovery
        return None, "failure"


def _git(args, cwd):
    return _git_read(args, cwd)[0]


def block(tag, msg):
    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)
    sys.exit(1)


# The most recent git-read failure, surfaced in the H-01 fail-closed block
# message — same rationale and format as pre-bash.py's _READ_ERRS: "git
# unavailable or timed out" alone is not enough evidence to root-cause a false
# block.
_READ_ERRS = []


def _note_read_err(operation, failure_kind):
    _READ_ERRS.append(git_read_error_summary(operation, failure_kind))


def _exception_failure_kind(error):
    """Classify an exception without copying its potentially sensitive text."""
    if isinstance(error, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(error, PermissionError):
        return "access"
    if isinstance(error, FileNotFoundError):
        return "spawn"
    if isinstance(error, UnicodeError):
        return "output"
    return "failure"


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
    r, failure_kind = _git_read(argv, cwd)
    if r is None or r.returncode != 0:
        _note_read_err("branch", failure_kind or "exit")
        return None
    return r.stdout.strip()


def head_on_protected_tip(cwd):
    """True when HEAD (typically detached) points at a protected branch's tip —
    a commit there still lands on main/master's history. Mirrors pre-bash.py.

    reliability-001 (#189): returns None (not False) when git could not answer,
    so H-01 fails CLOSED on a git-read error rather than concluding "not on a
    protected tip" from a failed read."""
    argv = ["show-ref", "--head", "refs/heads/main", "refs/heads/master"]
    r, failure_kind = _git_read(argv, cwd)
    if r is None or r.returncode not in (0, 1):
        _note_read_err("show-ref", failure_kind or "exit")
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
    time). None on a git read error -> caller fails closed.

    Excludes gate-events.log (#279): `sensitive_scan_added_lines` walks the
    diff path-aware, dropping lines that belong to the crypto/secret gate's
    own machine-written audit sink, so this backstop's view of "sensitive
    lines" never drifts from the producer (security-pass.py) or the
    PreToolUse gate (pre-bash.py) — see the shared helper's docstring in
    `_hooklib`. Reads the diff via SECURITY_DIFF_GIT_ARGS (pinned a/ b/
    prefixes, no external diff) so a hostile `diff.mnemonicPrefix`/
    `diff.noprefix`/external-diff config can never break that attribution
    (#279 review MEDIUM-1) — a merge commit's `--cc` combined-diff sections
    are also handled correctly (MEDIUM-2): the diff walk resets attribution on
    ANY `diff ` section header, not just `diff --git`."""
    try:
        r = subprocess.run(
            [git_executable(), *SECURITY_DIFF_GIT_ARGS, "--cached"], cwd=cwd,
            capture_output=True, timeout=10,
            env=root_bound_git_env(preserve_index=True),
        )
    except Exception as e:  # noqa: BLE001 — fail closed with a sanitized recovery
        _note_read_err("diff", _exception_failure_kind(e))
        return None
    if r.returncode != 0 or not isinstance(r.stdout, bytes):
        _note_read_err("diff", "exit" if r.returncode != 0 else "output")
        return None
    try:
        stdout = r.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _note_read_err("diff", "non-utf8")
        return None
    result = security_scan_diff(stdout)
    if result is None:
        _note_read_err("diff", "output")
    return result


def cached_names(cwd):
    """Exact no-rename index delta; retained name for existing test seams."""
    return staged_changes(cwd, preserve_index=True)


def _marker_set(root, name):
    try:
        with open(os.path.join(root, ".codearbiter", ".markers", name),
                  encoding="utf-8") as f:
            return set(f.read().split())
    except Exception:  # noqa: BLE001
        return set()


def _marker_root(root):
    """Escalate only gate-marker reads to the main checkout for a linked
    worktree; all Git and worktree reads remain anchored at ``root`` (#695)."""
    return hostapi.git_worktree_main_root(root) or root


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

    # H-09b / H-10b: a commit introducing crypto/secret changes needs a recorded,
    # exact-candidate security-gate pass (plus diagnostic row bindings).
    # Reuses the exact _hooklib primitives.
    added = cached_added_lines(cwd)
    if added is None:
        block("H-09b", "the staged diff for the crypto/secret scan could not be decoded "
                       "or read — failing closed (ORCHESTRATOR §2). Repair the reported "
                       "cause and retry; a reviewer PASS cannot substitute for an "
                       "unreadable diff." + _read_err_hint())
    if isinstance(added, BinarySecurityContext):
        if added.digests:
            block("H-09b", mixed_binary_security_recovery())
        approved = _marker_set(_marker_root(root), "security-gate-passed")
        expected = binary_override_binding(binary_candidate_binding(
            root, preserve_index=True))
        if (worktree_marker_binding(root) not in approved
                or expected is None or expected not in approved):
            block("H-09b", "No audited binary override is recorded for this exact staged "
                           "candidate. " + binary_security_recovery())
        sensitive = set()
    else:
        sensitive = added.digests
    if sensitive:
        crypto_count, sensitive_match_count, locations = security_finding_summary(
            added.findings, crypto_fallback=added.crypto)
        tag = "H-09b" if added.crypto else "H-10b"
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        recovery = security_gate_recovery(
            plugin_root, root, crypto_count, sensitive_match_count, locations,
            requires_staging=True)
        marker_root = _marker_root(root)
        marker = os.path.join(marker_root, ".codearbiter", ".markers", "security-gate-passed")
        if not os.path.isfile(marker):
            block(tag, "No security-gate PASS is recorded for this staged candidate "
                       "(#161 git backstop). " + recovery)
        approved = _marker_set(marker_root, "security-gate-passed")
        if worktree_marker_binding(root) not in approved:
            block(tag, "The security-gate PASS is unreadable, legacy, or bound to a "
                       "different worktree (#161 git backstop). " + recovery)
        if added.candidate not in approved:
            block(tag, "The staged candidate differs from the exact diff independently "
                       "reviewed and recorded (#161 git backstop). " + recovery)
        uncovered = sensitive - approved
        if uncovered:
            uncovered_findings = [f for f in added.findings if f.digest in uncovered]
            crypto_count, sensitive_match_count, uncovered_locations = security_finding_summary(
                uncovered_findings, crypto_fallback=added.crypto and bool(uncovered))
            block(tag, f"{len(uncovered)} sensitive binding(s) changed or were omitted "
                       f"after review (#161 git backstop). " + security_gate_recovery(
                           plugin_root, root, crypto_count, sensitive_match_count,
                           uncovered_locations, requires_staging=True))

    # H-14: a staged migration needs a content-bound migration-review pass.
    names = cached_names(cwd)
    if names is None:
        block("H-14", "the staged file list for the migration scan could not be read — "
                      "failing closed (ORCHESTRATOR §2). Repair Git readability and retry; "
                      "a reviewer PASS cannot substitute for an unreadable candidate.")
    migs = sorted(p for p in names if is_migration_path(p, root))
    if migs:
        approved = _marker_set(_marker_root(root), "migration-gate-passed")
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if worktree_marker_binding(root) not in approved:
            block("H-14", "The migration PASS is missing, unreadable, legacy, or bound "
                          "to a different worktree (#161 git backstop). " +
                          migration_gate_recovery(plugin_root, root, migs,
                                                  requires_staging=True))
        uncovered = []
        reviewed = []
        for rel in migs:
            status = names.get(rel, "M") if hasattr(names, "get") else "M"
            text = None if status == "D" else read_index_text(
                cwd, rel, preserve_index=True)
            preimage = None if status == "A" else read_head_blob_digest(cwd, rel)
            if ((status != "D" and (text is None or content_digest(text) not in approved))
                    or (status != "A" and preimage is None)):
                uncovered.append(rel)
            reviewed.append((rel, status, text, preimage))
        if uncovered:
            block("H-14", f"{len(uncovered)} staged migration file(s) changed or were "
                          f"omitted after review (#161 git backstop). " +
                          migration_gate_recovery(plugin_root, root, uncovered,
                                                  requires_staging=True))
        if migration_candidate_binding(reviewed) not in approved:
            block("H-14", "The staged migration set differs from the complete candidate "
                          "independently reviewed and recorded (#161 git backstop). " +
                          migration_gate_recovery(plugin_root, root, migs,
                                                  requires_staging=True))


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
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, set_host,
                               pass_argv=False, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
