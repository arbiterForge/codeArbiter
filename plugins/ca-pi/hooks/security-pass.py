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

from _gitexec import git_executable
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, SECURITY_DIFF_GIT_ARGS, is_sensitive_scan_exempt,
    line_digest, project_root, sensitive_scan_added_lines, set_host,
    utf8_stdio, warn, write_text_atomic,
)

MAX_UNTRACKED_BYTES = 1_000_000  # an untracked blob bigger than this is not reviewable prose


def run_git(args, cwd):
    return subprocess.run(
        [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
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
    lines = []
    diff = run_git([*SECURITY_DIFF_GIT_ARGS, "HEAD"], root)
    if diff.returncode == 0:
        lines += sensitive_scan_added_lines(diff.stdout)
    else:
        # Unborn branch (no HEAD yet): every tracked file is new content.
        ls = run_git(["ls-files"], root)
        for rel in ls.stdout.splitlines():
            if is_sensitive_scan_exempt(rel):
                continue
            lines += file_lines(root, rel)
    untracked = run_git(["ls-files", "--others", "--exclude-standard"], root)
    for rel in untracked.stdout.splitlines():
        if is_sensitive_scan_exempt(rel):
            continue
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
    # Atomic write (migration-002): a crash mid-write never leaves a half-written
    # marker, which the backstop would read as an unrecognized digest and force a
    # spurious gate re-run.
    write_text_atomic(marker, "\n".join(digests) + ("\n" if digests else ""))
    print(f"security-gate pass recorded: {len(digests)} sensitive line(s) "
          f"bound to {os.path.relpath(marker, root)}")


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
