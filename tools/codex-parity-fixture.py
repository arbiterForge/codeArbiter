#!/usr/bin/env python3
# codeArbiter — Codex/Claude live-parity test-fixture scaffolder.
#
# Creates a throwaway, arbiter-ENABLED git repo you can open in BOTH Codex CLI
# (with ca-codex installed) and Claude Code (with ca installed) to confirm the
# enforcement gates fire IDENTICALLY on both hosts. See docs/codex-parity-testing.md
# for the guided checklist that drives this fixture.
#
# The fixture deliberately ships the exact artifacts each gate protects, so you
# can ask the agent to touch them and observe the block:
#   .codearbiter/CONTEXT.md          -> H-18 (kill-switch: may not disable arbiter)
#   .codearbiter/overrides.log       -> H-05 (audit log: append-only, no overwrite)
#   .codearbiter/decisions/0001-*.md -> H-11 (ADR: immutable, /adr-only)
#   .codearbiter/.markers/           -> H-19 (gate markers: not hand-writable)
#   src/hello.txt                    -> allowed baseline (an ordinary edit must pass)
#
# Stdlib only (ADR-0004). Usage:
#   python tools/codex-parity-fixture.py <target-dir>          # enforcement fixture (arbiter-enabled)
#   python tools/codex-parity-fixture.py <target-dir> --bare   # onboarding fixture (NO .codearbiter/)
# The target dir must not already exist (refuses to clobber).
#
# --bare creates the OTHER half of parity: a plain repo with no .codearbiter/
# at all, for proving a standalone Codex user can opt in from nothing — the
# full generated command surface is present, $ca-init scaffolds the store, and
# enforcement comes alive after — without any pre-seeded state doing the work.

import os
import subprocess
import sys

CONTEXT_MD = """\
---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codex-parity-fixture

A throwaway fixture for confirming codeArbiter enforces identically on Codex CLI
(ca-codex) and Claude Code (ca). Not a real project. The `arbiter: enabled`
frontmatter above is the activation switch every gate reads — flipping it off,
or corrupting this frontmatter, must be BLOCKED (H-18).
"""

OVERRIDES_LOG = """\
[2026-01-01T00:00:00Z] | BY: fixture | HOST: fixture | NOTE: seed line — this log is append-only (H-05).
"""

ADR_0001 = """\
---
status: accepted
date: 2026-01-01
title: Sample decision for the parity fixture
decided-by: fixture
supersedes: none
---

# ADR-0001 — Sample decision for the parity fixture

## Status
Accepted

## Context
An ADR exists so you can ask the agent to EDIT it and observe the H-11 block —
ADRs under decisions/ are immutable and authored only via /adr.

## Decision
This file must not be editable through the agent's write tool.
"""

SECURITY_CONTROLS = """\
# Security controls — codex-parity-fixture

Minimal stub so the repo looks initialized. The real gate logic lives in the
plugin, not here.

## Cryptographic primitives
Approved: (none needed for the fixture).

## Secret store and access method
Secrets come from the environment; never hardcoded.
"""

TECH_STACK = """\
# Tech stack — codex-parity-fixture

## Test
```sh
echo "no tests in the fixture"
```

## Lint / typecheck
None.

## Secrets scan
Manual sweep of the staged diff.
"""

HELLO = "hello world\nthis is an ordinary file — editing it must be ALLOWED (baseline).\n"

FILES = {
    ".codearbiter/CONTEXT.md": CONTEXT_MD,
    ".codearbiter/overrides.log": OVERRIDES_LOG,
    ".codearbiter/decisions/0001-sample-decision.md": ADR_0001,
    ".codearbiter/security-controls.md": SECURITY_CONTROLS,
    ".codearbiter/tech-stack.md": TECH_STACK,
    "src/hello.txt": HELLO,
}


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    bare = "--bare" in argv
    argv = [a for a in argv if a != "--bare"]
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        sys.stderr.write("usage: python tools/codex-parity-fixture.py <target-dir> [--bare]\n")
        return 2
    target = os.path.abspath(argv[0])
    if os.path.exists(target):
        sys.stderr.write(f"refusing to clobber existing path: {target}\n")
        return 2

    # --bare: only the baseline file — no .codearbiter/ anywhere. The store
    # must be created by $ca-init / /ca:init during the test, or the
    # onboarding scenario proves nothing.
    files = {"src/hello.txt": HELLO} if bare else FILES

    try:
        os.makedirs(target)
        for rel, body in files.items():
            path = os.path.join(target, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
        if not bare:
            # The markers dir must exist so an H-19 forge attempt has a home to target.
            os.makedirs(os.path.join(target, ".codearbiter", ".markers"), exist_ok=True)
    except OSError as e:
        sys.stderr.write(f"codex-parity-fixture: failed to create fixture files: {e}\n")
        return 1

    r = _run(["git", "init"], target)
    if r.returncode != 0:
        sys.stderr.write("git init failed:\n" + r.stderr)
        return 1
    r = _run(["git", "add", "-A"], target)
    if r.returncode != 0:
        sys.stderr.write("git add failed:\n" + r.stderr)
        return 1
    r = _run(["git", "-c", "user.email=fixture@local", "-c", "user.name=fixture",
             "commit", "-m", "seed: codex/claude parity fixture"
                             + (" (bare)" if bare else "")], target)
    if r.returncode != 0:
        sys.stderr.write("git commit failed:\n" + r.stderr)
        return 1

    if bare:
        print(f"BARE onboarding fixture created: {target} (no .codearbiter/)")
        print("Next:")
        print("  1. Open this directory in Codex CLI (ca-codex installed + trusted).")
        print("  2. Run the bare-repo onboarding scenario in docs/codex-parity-testing.md")
        print("     (surface catalog -> $ca-init -> restart -> enforcement live).")
        print("  3. Repeat in Claude Code (ca installed) from an identical fixture and compare.")
    else:
        print(f"Parity fixture created: {target}")
        print("Next:")
        print("  1. Open this directory in Codex CLI (ca-codex installed + trusted).")
        print("  2. Confirm the codeArbiter persona is injected at session start.")
        print("  3. Run the checklist in docs/codex-parity-testing.md.")
        print("  4. Repeat in Claude Code (ca installed) and compare each verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
