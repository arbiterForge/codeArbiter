#!/usr/bin/env python3
# codeArbiter v2 — record a security-gate pass bound to the exact staged candidate.
#
# The crypto-compliance / secret-handling skills run this ON PASS. The existing
# /ca:override security ceiling may instead invoke the explicit binary-override
# mode, which appends its mandatory audit row before writing a distinct marker.
# Both replace the old `touch` of an empty
# marker. An empty marker only proved that *some* gate passed *recently*; any
# different crypto/secret change committed inside the 30-minute freshness
# window rode through on it (a TOCTOU hole). This helper hashes every added
# line in the exact staged diff supplied to the independent reviewer that matches the
# shared CRYPTO_RE/SECRET_RE and writes the candidate and diagnostic digests to
# .codearbiter/.markers/security-gate-passed; pre-bash.py H-09b/H-10b then
# admits a commit only when the complete staged diff still matches the recorded
# candidate and every sensitive diagnostic binding remains covered.
#
# Invoked by skill prose as (interpreter resolved once by presence, never a
# `python3 X || python X` fold -- #577; recording itself stays idempotent):
#   "$PY" "<plugin>/hooks/security-pass.py"

import argparse
import os
import subprocess

from _gitexec import (active_index_recovery, binary_candidate_binding,
                      git_executable, root_bound_git_env)
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    BINARY_SECURITY_CONTEXT, BinarySecurityContext, SECURITY_DIFF_GIT_ARGS,
    binary_override_binding, binary_security_recovery,
    mixed_binary_security_recovery,
    security_scan_diff, set_host, utf8_stdio, warn,
    worktree_marker_binding, write_text_atomic,
)

def run_git(args, cwd):
    return subprocess.run(
        [git_executable()] + args, cwd=cwd, capture_output=True, timeout=30,
        env=root_bound_git_env(preserve_index=True),
    )


NON_UTF8_SECURITY_CONTEXT = object()


def candidate_scan(root):
    """Classify exactly the staged diff supplied to the independent reviewer.

    #1037: the previous producer also absorbed unstaged and untracked rows.
    Those rows were not part of commit-gate's staged review and therefore
    could inherit a PASS the reviewer never issued for them.  Future work must
    be staged, reviewed, and recorded again rather than silently widened here.
    """
    staged = run_git([*SECURITY_DIFF_GIT_ARGS, "--cached"], root)
    if staged.returncode != 0 or not isinstance(staged.stdout, bytes):
        return None
    try:
        stdout = staged.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return NON_UTF8_SECURITY_CONTEXT
    return security_scan_diff(stdout)


def reviewed_request(argv=None):
    """Resolve the producer's source from its explicit root or actual cwd.

    Deliberately ignore CLAUDE_PROJECT_DIR: a coordinator may inherit another
    session's root.  The standalone producer must bind the checkout named in
    its own command, or the checkout it is actually running inside.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root")
    parser.add_argument("--binary-override", action="store_true")
    parser.add_argument("--security-finding")
    parser.add_argument("--reason")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except SystemExit:
        return None
    fields = (args.security_finding, args.reason)
    if args.binary_override != all(fields) or any(fields) and not args.binary_override:
        return None
    selected = args.root or os.getcwd()
    if not os.path.isdir(selected):
        return None
    top = hostapi.git_toplevel(selected)
    if not top:
        return None
    if args.root and os.path.normcase(os.path.realpath(top)) != os.path.normcase(
            os.path.realpath(selected)):
        return None
    return top, args


def reviewed_root(argv=None):
    request = reviewed_request(argv)
    return request[0] if request else None


def main(argv=None):
    utf8_stdio()
    request = reviewed_request(argv)
    if request is None:
        warn("security-gate pass refused: use --root <reviewed repository root> "
             "or run the standalone producer from that root")
        sys.exit(1)
    root, args = request
    if not os.path.isdir(os.path.join(root, ".codearbiter")):
        warn("no .codearbiter/ here — security-pass.py records nothing outside "
             "an initialized repo")
        sys.exit(1)
    index_recovery = active_index_recovery(root)
    if index_recovery:
        warn("security-gate pass refused: " + index_recovery)
        sys.exit(1)
    try:
        scan = candidate_scan(root)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        scan = None
    if scan is NON_UTF8_SECURITY_CONTEXT:
        warn("security-gate pass refused: staged diff contains non-UTF-8 text bytes; "
             "convert the file to UTF-8, or, if it is genuinely binary, mark it "
             "binary in .gitattributes and use the audited binary override")
        sys.exit(1)
    if isinstance(scan, BinarySecurityContext):
        if scan.digests:
            warn("binary security override refused: " + mixed_binary_security_recovery())
            sys.exit(1)
        if not args.binary_override:
            warn("security-gate pass refused: " + binary_security_recovery())
            sys.exit(1)
        binding = binary_override_binding(binary_candidate_binding(
            root, preserve_index=True))
        if binding is None:
            warn("binary security override refused: the staged binary set is unreadable "
                 "or exceeds 32 files, 100 MB per file, or 200 MB total across staged "
                 "and HEAD blobs; reduce or move the asset set, restage, and retry")
            sys.exit(1)
        from _overrideappendlib import OverrideAppendError, append_override
        try:
            append_override(security_finding=args.security_finding,
                            reason=args.reason, cwd=root)
        except (OSError, OverrideAppendError) as error:
            warn(f"binary security override refused: {error}")
            sys.exit(1)
        write_root = hostapi.git_worktree_main_root(root) or root
        marker_dir = os.path.join(write_root, ".codearbiter", ".markers")
        os.makedirs(marker_dir, exist_ok=True)
        marker = os.path.join(marker_dir, "security-gate-passed")
        write_text_atomic(marker, "\n".join(
            (worktree_marker_binding(root), binding)) + "\n")
        print("binary security override recorded: exact staged candidate bound to "
              + os.path.relpath(marker, write_root))
        return
    if scan is None:
        warn("security-gate pass refused: unavailable or malformed crypto/secret context")
        sys.exit(1)
    if args.binary_override:
        warn("binary security override refused: staged diff has reviewable text context")
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
    write_root = hostapi.git_worktree_main_root(root) or root
    marker_dir = os.path.join(write_root, ".codearbiter", ".markers")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "security-gate-passed")
    digests = [worktree_marker_binding(root), scan.candidate, *sorted(scan.digests)]
    # Atomic write (migration-002): a crash mid-write never leaves a half-written
    # marker, which the backstop would read as an unrecognized digest and force a
    # spurious gate re-run.
    write_text_atomic(marker, "\n".join(digests) + ("\n" if digests else ""))
    print(f"security-gate pass recorded: exact staged candidate with {len(scan.digests)} "
          f"sensitive line(s) bound to {os.path.relpath(marker, write_root)}")


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
                               pass_argv=True, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
