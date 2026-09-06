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
# Invoked by skill prose as (interpreter resolved once by presence, never a
# `python3 X || python X` fold -- #577; recording itself stays idempotent):
#   "$PY" "<plugin>/hooks/security-pass.py"

import os
import subprocess

from _gitexec import git_executable
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    SECURITY_DIFF_GIT_ARGS, SecurityScan, is_sensitive_scan_exempt,
    marker_root, project_root, security_scan_diff, security_scan_source,
    set_host, utf8_stdio, warn, write_text_atomic,
)

MAX_UNTRACKED_BYTES = 1_000_000  # an untracked blob bigger than this is not reviewable prose


def run_git(args, cwd):
    return subprocess.run(
        [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


def file_scan(root, rel):
    p = os.path.join(root, rel)
    try:
        if os.path.getsize(p) > MAX_UNTRACKED_BYTES:
            return SecurityScan(False, set())
        with open(p, encoding="utf-8", errors="replace") as f:
            source = f.read()
        return security_scan_source(rel, source, range(1, len(source.splitlines()) + 1))
    except Exception:  # noqa: BLE001
        return None


def candidate_scan(root):
    """Separate classified index and worktree snapshots, plus untracked content.

    Every line the next commit could introduce: added lines of the
    staged diff AND worktree-vs-HEAD diff, plus the full content
    of untracked files — `git diff HEAD` never shows those, but they land in
    the staged diff the moment commit-gate stages them.

    Excludes gate-events.log (#279, is_sensitive_scan_exempt): the crypto/
    secret gate's own machine-written audit sink, which structurally echoes
    the detector's message text back at itself. The diff branch drops those
    lines via the shared path-aware `sensitive_scan_added_lines`; the
    unborn-branch and untracked-file branches skip the file outright since
    they read whole-file content rather than a diff.

    The diff is read via SECURITY_DIFF_GIT_ARGS (not a bare `["diff", ...]`):
    it pins the `a/`/`b/` prefix format `sensitive_scan_added_lines` depends
    on for path attribution, regardless of the caller's `diff.mnemonicPrefix`
    / `diff.noprefix` / external-diff config (#279 review MEDIUM-1)."""
    staged = run_git([*SECURITY_DIFF_GIT_ARGS, "--cached"], root)
    if staged.returncode != 0:
        return None
    scans = [security_scan_diff(staged.stdout)]
    diff = run_git([*SECURITY_DIFF_GIT_ARGS, "HEAD"], root)
    if diff.returncode == 0:
        scans.append(security_scan_diff(diff.stdout))
    else:
        # Confirm an absent branch ref, not merely a failed diff read. A real
        # read/parse failure must never be laundered through the unborn path.
        head = run_git(["rev-parse", "--verify", "--quiet", "HEAD"], root)
        branch = run_git(["symbolic-ref", "--quiet", "HEAD"], root)
        if head.returncode != 1 or branch.returncode != 0:
            return None
        absent = run_git(["show-ref", "--verify", "--quiet", branch.stdout.strip()], root)
        if absent.returncode != 1:
            return None
        ls = run_git(["ls-files"], root)
        if ls.returncode != 0:
            return None
        for rel in ls.stdout.splitlines():
            if is_sensitive_scan_exempt(rel):
                continue
            scans.append(file_scan(root, rel))
    untracked = run_git(["ls-files", "--others", "--exclude-standard"], root)
    if untracked.returncode != 0:
        return None
    for rel in untracked.stdout.splitlines():
        if is_sensitive_scan_exempt(rel):
            continue
        scans.append(file_scan(root, rel))
    if any(scan is None for scan in scans):
        return None
    return SecurityScan(any(scan.crypto for scan in scans),
                        set().union(*(scan.digests for scan in scans)))


def main():
    utf8_stdio()
    root = project_root()
    if not os.path.isdir(os.path.join(root, ".codearbiter")):
        warn("no .codearbiter/ here — security-pass.py records nothing outside "
             "an initialized repo")
        sys.exit(1)
    try:
        scan = candidate_scan(root)
    except (OSError, subprocess.SubprocessError, ValueError):
        scan = None
    if scan is None:
        warn("security-gate pass refused: unavailable or malformed crypto/secret context")
        sys.exit(1)
    # #604: the MARKER root is deliberately NOT `root` above. `root` (plain
    # project_root()) must stay wherever this process is actually running —
    # candidate_scan(root) just scanned exactly that tree's diff, and binding
    # digests to a DIFFERENT tree would review lines nobody staged. But in a
    # linked git worktree, `root` names the worktree's own (gitignored,
    # never-checked-out) `.codearbiter/.markers/`, while the H-09b/H-10b
    # guard reads the marker from the MAIN checkout (D-2) — marker_root()
    # gives the write the same main-checkout answer the guard's read already
    # has, without moving the scan.
    write_root = marker_root()
    marker_dir = os.path.join(write_root, ".codearbiter", ".markers")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "security-gate-passed")
    digests = sorted(scan.digests)
    # Atomic write (migration-002): a crash mid-write never leaves a half-written
    # marker, which the backstop would read as an unrecognized digest and force a
    # spurious gate re-run.
    write_text_atomic(marker, "\n".join(digests) + ("\n" if digests else ""))
    print(f"security-gate pass recorded: {len(digests)} sensitive line(s) "
          f"bound to {os.path.relpath(marker, write_root)}")


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
