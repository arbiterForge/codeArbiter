#!/usr/bin/env python3
# codeArbiter — record a migration-review pass BOUND to the migration files it
# approved (H-14, issue #77).
#
# There was no commit-time migration gate before #77: a migration committed via
# bare /commit or the /feature small lane never reached migration-reviewer (the
# /review, /pr, /checkpoint, and sprint lanes did dispatch it). commit-gate now
# dispatches migration-reviewer when it classifies a staged migration and runs
# THIS script on PASS. It mirrors security-pass.py: it hashes the content of
# every staged/worktree/untracked migration file (detected by is_migration_path)
# and writes the digests to .codearbiter/.markers/migration-gate-passed;
# pre-bash.py's H-14 then admits a commit only when every migration file being
# committed is in the recorded set.
#
# Binding is by content digest with no freshness window: a migration is
# immutable, so a recorded pass stays valid while the content is unchanged, and
# any edit changes the digest -> the backstop re-blocks (closing TOCTOU and
# enforcing immutability at commit time).
#
# Invoked by skill prose as:
#   python3 "<plugin>/hooks/migration-pass.py" || python "<plugin>/hooks/migration-pass.py"
# (same interpreter-fallback shape as hooks.json; rerun-safe — recording is a
# deterministic overwrite.)

import os
import subprocess

from _gitexec import git_executable
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    content_digest, is_migration_path, project_root, set_host, utf8_stdio,
    warn, write_text_atomic,
)

MAX_FILE_BYTES = 1_000_000  # a blob bigger than this is not a reviewable migration


def run_git(args, cwd):
    return subprocess.run(
        [git_executable()] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


def candidate_paths(root):
    """Every path the next commit could introduce a migration through: tracked
    changes vs HEAD (staged and unstaged), plus untracked files. On an unborn
    branch (no HEAD) every tracked file is new content."""
    paths = set()
    for args in (["diff", "--cached", "--name-only"], ["diff", "--name-only"]):
        r = run_git(args, root)
        if r.returncode == 0:
            paths.update(p for p in r.stdout.splitlines() if p.strip())
    if not paths:
        r = run_git(["ls-files"], root)
        if r.returncode == 0:
            paths.update(p for p in r.stdout.splitlines() if p.strip())
    u = run_git(["ls-files", "--others", "--exclude-standard"], root)
    if u.returncode == 0:
        paths.update(p for p in u.stdout.splitlines() if p.strip())
    return paths


def read_text(root, rel):
    p = os.path.join(root, rel)
    try:
        if os.path.getsize(p) > MAX_FILE_BYTES:
            return None
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def main():
    utf8_stdio()
    root = project_root()
    if not os.path.isdir(os.path.join(root, ".codearbiter")):
        warn("no .codearbiter/ here — migration-pass.py records nothing outside "
             "an initialized repo")
        sys.exit(1)
    migs = sorted(rel for rel in candidate_paths(root) if is_migration_path(rel, root))
    digests = set()
    for rel in migs:
        text = read_text(root, rel)
        if text is not None:
            digests.add(content_digest(text))
    marker_dir = os.path.join(root, ".codearbiter", ".markers")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "migration-gate-passed")
    digests = sorted(digests)
    # Atomic write (migration-002): a crash mid-write never leaves a half-written
    # marker, which the backstop would read as an unrecognized digest and force a
    # spurious gate re-run.
    write_text_atomic(marker, "\n".join(digests) + ("\n" if digests else ""))
    print(f"migration-gate pass recorded: {len(digests)} migration file(s) "
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
    set_host(host)
    main()
    return 0


if __name__ == "__main__":
    # hostapi is imported here (not at module top) so OB-S1's stdlib-import
    # scan of this producer keeps its exact allowlist; hostapi is the same-dir
    # host seam (ADR-0011), stdlib-only like _hooklib.
    import hostapi  # noqa: PLC0415
    sys.exit(run(hostapi.load_host()) or 0)
