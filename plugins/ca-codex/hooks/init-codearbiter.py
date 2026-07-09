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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _hooklib  # noqa: E402 — set_host DI seam (#257)

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

In-flight and queued work. One top-level `- ` bullet per task; the statusline and
SessionStart hook count these, EXCLUDING done (`- [x]`).

Schema (one task = a lifecycle line + indented content sub-bullets):

```
- [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)
  - Desc: reject expired/forged tokens at the auth middleware
  - Done when: an expired token returns 401; a valid one passes
  - Boundaries: auth, secrets
```

- Marker: `[ ]` queued | `[~]` in-progress | `[x]` done. In-progress and done
  carry a dated `(started YYYY-MM-DD)` / `(done YYYY-MM-DD)` parenthetical; a
  stale `[~]` is surfaced at SessionStart.
- ID `<group>.<type>.<seq>`: `group` = build phase (poc/mvp1/v1...), `type` =
  domain (auth/api/ui/infra...), `seq` = >=4-digit, numbered within each
  `group.type`. ID + title + marker are required.
- `Desc` / `Done when` / `Boundaries` are filled when known (`TBD` until then).
  Keep `Done when` to one coarse sentence — per-step verification belongs to a
  plan, not here. `Boundaries` names the security/trust boundary the task is
  expected to touch (auth, crypto, secrets, ...).
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

    # #161: install the git-level enforcement backstop (pre-commit/pre-push) so
    # git mutations are gated at the operation itself, not only at the literal
    # Bash command string. Best-effort — a repo without a git dir, or a foreign
    # existing hook, is reported by install(), never fatal to scaffolding.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _githooks import install as _install_git_hooks
        gh = _install_git_hooks(root)
        if gh:
            print("git hooks: " + ", ".join(gh))
    except Exception as e:  # noqa: BLE001
        print(f"git hooks: install skipped ({e})", file=sys.stderr)

    print(f"SCAFFOLDED .codearbiter/ at {cad}")
    print("created: " + ", ".join(created))
    print(f"arbiter: enabled (stage {args.stage}); CONTEXT.md is a stub (no <!--INITIALIZED--> sentinel).")
    print("Next: run /ca:create-context (source exists) or /ca:decompose (greenfield) to populate.")


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main(argv) unchanged — main()'s return value
    stays discarded exactly as the old bare `main()` guard discarded it (so
    the process still exits 0 on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    _hooklib.set_host(host)
    main(argv)
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
