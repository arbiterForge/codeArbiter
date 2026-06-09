#!/usr/bin/env python3
# codeArbiter v2 — SessionStart activation hook (the linchpin).
# Python port of session-start.sh (#25): no awk/grep/find, cross-platform, and
# fails LOUD — if CONTEXT.md exists but its frontmatter is malformed, it now
# prints a stderr breadcrumb instead of going silently dormant (the worst
# failure shape for a plugin whose whole job is to be active).
#
# Detects an arbiter-enabled repo and injects the orchestrator persona + startup
# state into context. A plugin has no CLAUDE.md to load an always-on persona, so
# the SessionStart hook does it: in a repo whose `.codearbiter/CONTEXT.md`
# frontmatter sets `arbiter: enabled`, this prints ORCHESTRATOR.md (+ live state)
# to stdout, which Claude Code adds to context.
#
# Injection is via PLAIN STDOUT, not hookSpecificOutput.additionalContext:
# additionalContext from a plugin-scoped hook is unreliable (claude-code #16538),
# whereas plain stdout is added to context dependably.
#
# In any repo WITHOUT the flag, the hook exits silently (dormant) — the plugin
# can be installed globally and stays out of the way everywhere else.

import os
import re
import subprocess
import sys

ARBITER_RE = re.compile(r"^\s*arbiter:\s*enabled\s*$", re.I)
INITIALIZED_RE = re.compile(r"<!--\s*INITIALIZED\s*-->")
STAGE_RE = re.compile(r"^stage:\s*([0-9]+)", re.I | re.M)
CONFIRM_RE = re.compile(r"CONFIRM-[0-9]+")


def project_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def arbiter_enabled(ctx):
    """Return (enabled, malformed). `enabled` iff `arbiter: enabled` appears in a
    properly-closed leading YAML frontmatter block. `malformed` iff a block opens
    (`---` on line 1) but never closes — the fail-loud case. A file with no
    frontmatter at all is simply dormant (not malformed)."""
    text = read_text(ctx)
    if text is None:
        return (False, False)
    lines = text.split("\n")
    if not lines:
        return (False, False)
    first = lines[0].lstrip("﻿")  # tolerate a leading UTF-8 BOM
    if first.strip() != "---":
        return (False, False)  # no opening delimiter — dormant, not malformed
    found = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            return (found, False)  # closing delimiter — decision is final
        if ARBITER_RE.match(ln):
            found = True
    return (False, True)  # opened but never closed — malformed


def has_source(root):
    """True if the repo contains any file that isn't arbiter/scaffold cruft —
    distinguishes brownfield (adopt existing code) from greenfield. Returns on the
    first match, so it does not walk a large tree."""
    excl_top = {".git", ".codearbiter", ".claude", "legacy"}
    excl_names = {"README.md", "LICENSE", ".gitignore", "AGENTS.md", "CLAUDE.md", ".gitmodules"}
    for cur, dirs, files in os.walk(root):
        if cur == root:
            dirs[:] = [d for d in dirs if d not in excl_top]
        else:
            dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            if fn not in excl_names:
                return True
    return False


def main():
    root = project_root()
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")

    # /dev developer-override is per-session: clear its statusline marker on
    # startup — a new session restores orchestration.
    try:
        os.remove(os.path.join(root, ".codearbiter", ".markers", "dev-active"))
    except OSError:
        pass

    enabled, malformed = arbiter_enabled(ctx)
    if not enabled:
        if malformed:
            print("codeArbiter: .codearbiter/CONTEXT.md is present but its frontmatter is "
                  "malformed (opening '---' with no closing '---'). The plugin is DORMANT — "
                  "fix the frontmatter to activate.", file=sys.stderr)
        sys.exit(0)

    # --- Arbiter active: inject persona ---
    orch = os.path.join(plugin, "ORCHESTRATOR.md")
    orch_text = read_text(orch)
    if orch_text is not None:
        sys.stdout.write(orch_text)
        print()
    else:
        print(f"codeArbiter: ORCHESTRATOR.md not found at {orch} — persona not injected. "
              f"Check CLAUDE_PLUGIN_ROOT.", file=sys.stderr)

    # --- Inject live startup state ---
    print("=== codeArbiter startup state ===")

    ctx_text = read_text(ctx) or ""
    if not INITIALIZED_RE.search(ctx_text):
        if has_source(root):
            print("NOT INITIALIZED: source exists but .codearbiter/CONTEXT.md is a stub. "
                  "Run /create-context before any other command.")
        else:
            print("NOT INITIALIZED: empty project. Run /decompose to begin.")
        print("Type /ca:commands for the catalog.")
        sys.exit(0)

    m = STAGE_RE.search(ctx_text)
    print(f"stage: {m.group(1) if m else '—'}")

    oq = os.path.join(root, ".codearbiter", "open-questions.md")
    oq_text = read_text(oq)
    if oq_text is not None:
        confirms = CONFIRM_RE.findall(oq_text)
        if confirms:
            print(f"BLOCKING questions (CONFIRM-NN): {len(confirms)} — must resolve before "
                  f"dependent work proceeds:")
            for ln in oq_text.splitlines():
                if CONFIRM_RE.search(ln):
                    print(f"  {ln}")
        else:
            print("open questions: 0")

    ot = os.path.join(root, ".codearbiter", "open-tasks.md")
    ot_text = read_text(ot)
    if ot_text is not None:
        tn = sum(1 for ln in ot_text.splitlines() if ln.startswith("- "))
        print(f"in-flight tasks: {tn}")

    print("Present this state, then await a slash command. Type /ca:commands for the catalog.")
    sys.exit(0)


if __name__ == "__main__":
    main()
