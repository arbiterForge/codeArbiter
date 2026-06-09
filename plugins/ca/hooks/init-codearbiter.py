#!/usr/bin/env python3
# codeArbiter — first-run scaffolder. Creates the root-level .codearbiter/ project
# state directory that opts a repo into arbiter management. Idempotent: it never
# overwrites a file that already exists, so it is safe to re-run.
#
# The `arbiter: enabled` frontmatter in CONTEXT.md is the single activation flag —
# it gates both the SessionStart persona injection and the arbiter statusline
# segments. CONTEXT.md is scaffolded WITHOUT the <!--INITIALIZED--> body sentinel,
# so the next session routes to /ca:create-context (source exists) or /ca:decompose
# (greenfield) to populate it.
#
# Usage:
#   python init-codearbiter.py [--root PATH] [--stage N]
#   python init-codearbiter.py --check        # report state, create nothing

import argparse
import os
import sys

# NOTE: this stub deliberately does NOT contain the initialization sentinel
# (an HTML comment wrapping the word INITIALIZED). The SessionStart hook greps
# for that exact token to decide whether the project is populated, so emitting it
# here — even inside a comment — would falsely mark an empty stub as initialized.
# The populator flow (/ca:create-context or /ca:decompose) adds it on its own line.
CONTEXT = """\
---
arbiter: enabled
stage: {stage}
---

# Project: {name}

<!-- This .codearbiter/ directory is the root-level project-state store. It lives
outside .claude/ so it survives even if the codeArbiter plugin is uninstalled.
The `arbiter: enabled` frontmatter above is the activation flag.

This CONTEXT.md is a stub: it carries no initialization sentinel yet, so the
orchestrator routes you to /ca:create-context (if source already exists) or
/ca:decompose (greenfield) to populate the real project context. That flow writes
the sentinel and normal operation begins. -->

_Not yet initialized. Run /ca:create-context or /ca:decompose to populate._
"""

OPEN_TASKS = """\
# Open tasks

In-flight and queued work. One `- ` bullet per task (the statusline and
SessionStart hook count these).
"""

OPEN_QUESTIONS = """\
# Open questions

Unresolved `[CONFIRM-NN]` items. Each blocks dependent work until resolved.
The SessionStart hook and statusline count `CONFIRM-NN` occurrences here.

_None open._
"""

OVERRIDES = """\
# codeArbiter override log - append-only audit artifact. Never edit or delete prior lines.
# Format: [ISO-8601] | BY: <name> <<email>> | GATE: <gate bypassed> | REASON: <reason>
# Written only by /override. The statusline counts non-comment lines after the
# last-checkpoint marker as "overrides since last checkpoint."
"""

FILES = {
    "open-tasks.md": OPEN_TASKS,
    "open-questions.md": OPEN_QUESTIONS,
    "overrides.log": OVERRIDES,
    "last-checkpoint": "0\n",
}


def project_root(opt):
    if opt:
        return os.path.abspath(opt)
    # prefer git toplevel; fall back to cwd
    try:
        import subprocess
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2)
        top = out.stdout.strip()
        if out.returncode == 0 and top:
            return os.path.abspath(top)
    except Exception:
        pass
    return os.path.abspath(os.getcwd())


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--root")
    ap.add_argument("--stage", type=int, default=1)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    root = project_root(args.root)
    cad = os.path.join(root, ".codearbiter")
    ctx = os.path.join(cad, "CONTEXT.md")
    name = os.path.basename(root.rstrip("/\\")) or "project"

    if args.check:
        if os.path.exists(ctx):
            print(f"ALREADY SCAFFOLDED: {ctx} exists.")
            with open(ctx, encoding="utf-8", errors="replace") as f:
                text = f.read()
            import re
            initd = bool(re.search(r"(?m)^\s*<!--\s*INITIALIZED\s*-->\s*$", text))
            print("arbiter: " + ("enabled" if re.search(r"(?m)^arbiter:\s*enabled\s*$", text) else "not enabled"))
            print("initialized body: " + ("yes" if initd else "no (run /ca:create-context or /ca:decompose)"))
        else:
            print(f"NOT SCAFFOLDED: {cad} would be created. Run without --check to scaffold.")
        return

    if os.path.exists(ctx):
        raise SystemExit(
            f"REFUSING: {ctx} already exists. .codearbiter/ is already scaffolded here. "
            "To populate it, run /ca:create-context or /ca:decompose; to repair, edit by hand.")

    os.makedirs(cad, exist_ok=True)
    created = []
    if not os.path.exists(ctx):
        with open(ctx, "w", encoding="utf-8") as f:
            f.write(CONTEXT.format(stage=args.stage, name=name))
        created.append("CONTEXT.md")
    for fname, content in FILES.items():
        fp = os.path.join(cad, fname)
        if not os.path.exists(fp):
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            created.append(fname)

    print(f"SCAFFOLDED .codearbiter/ at {cad}")
    print("created: " + ", ".join(created))
    print(f"arbiter: enabled (stage {args.stage}); CONTEXT.md is a stub (no <!--INITIALIZED--> sentinel).")
    print("Next: run /ca:create-context (source exists) or /ca:decompose (greenfield) to populate.")


if __name__ == "__main__":
    main()
