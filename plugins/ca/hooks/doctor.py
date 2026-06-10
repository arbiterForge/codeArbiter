#!/usr/bin/env python3
# codeArbiter v2 — install-health doctor (the mechanical half of /ca:doctor).
#
# Silent dormancy is the worst failure shape this plugin has: the gates look
# installed but never fire, and nothing says so. It has happened in the wild —
# a stale plugin cache survived `claude plugin update` because the version
# string was unchanged, leaving months-old hooks in place until a full
# uninstall+reinstall. This script checks everything checkable from a single
# process; the one thing it cannot prove from the inside — that Claude Code
# actually fires the hooks on tool calls — is the live-fire probe step in
# commands/doctor.md.
#
# Output: one OK / WARN / FAIL line per check, then a verdict. Exit 0 when
# nothing FAILed; exit 1 otherwise. Read-only — changes nothing.

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import frontmatter_enabled, utf8_stdio  # noqa: E402

HOOK_SCRIPTS = ("session-start.py", "pre-bash.py", "pre-write.py",
                "pre-edit.py", "post-write-edit.py")

results = []  # (level, line)


def ok(line):
    results.append(("OK", line))


def warn(line):
    results.append(("WARN", line))


def fail(line):
    results.append(("FAIL", line))


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15, **kw)


def plugin_root():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return os.path.abspath(env)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def check_interpreters():
    """The hooks need python3 OR python on PATH; the dual registration in
    hooks.json tolerates a Store-alias python3 stub as long as real `python`
    exists behind it."""
    p3, p = shutil.which("python3"), shutil.which("python")
    stub = False
    if p3:
        try:
            stub = run([p3, "-c", ""]).returncode != 0
        except Exception:  # noqa: BLE001
            stub = True
    if p3 and not stub:
        ok(f"python3 resolves and runs ({p3})")
    elif p3 and stub:
        (warn if p else fail)(
            f"python3 resolves but does not run ({p3}) — the Microsoft Store "
            f"alias stub. " + ("The hook fallback entries cover this via `python`."
                               if p else "And no `python` behind it: EVERY GATE IS "
                               "DORMANT. Install Python or disable the Store alias."))
    elif not p3 and p:
        ok("no python3 on PATH, but `python` resolves — the hook fallback entries cover this")
    else:
        fail("neither python3 nor python resolves on PATH — every hook fails loud, "
             "no gate evaluates. Install Python 3.")
    if p and not (p3 and not stub):
        ok(f"python resolves ({p})")


def check_payload(root):
    manifest = os.path.join(root, ".claude-plugin", "plugin.json")
    version = None
    try:
        with open(manifest, encoding="utf-8") as f:
            version = json.load(f).get("version")
        ok(f"plugin payload at {root} (version {version})")
    except Exception as e:  # noqa: BLE001
        fail(f"plugin.json unreadable at {manifest}: {e}")
    hooks_json = os.path.join(root, "hooks", "hooks.json")
    try:
        with open(hooks_json, encoding="utf-8") as f:
            config = json.load(f)["hooks"]
        entries = sum(len(g["hooks"]) for groups in config.values() for g in groups)
        ok(f"hooks.json parses: {len(config)} events, {entries} entries")
    except Exception as e:  # noqa: BLE001
        fail(f"hooks/hooks.json unreadable or malformed: {e} — no gate is registered")
    missing = [s for s in HOOK_SCRIPTS
               if not os.path.isfile(os.path.join(root, "hooks", s))]
    if missing:
        fail(f"hook script(s) missing from the payload: {', '.join(missing)}")
    else:
        ok(f"all {len(HOOK_SCRIPTS)} hook scripts present")

    # The stale-cache trap: `claude plugin update` no-ops when the version
    # string is unchanged, so a cache dir can hold a payload months older
    # than the marketplace. Multiple cached versions are the breadcrumb.
    norm = root.replace("\\", "/")
    if "/plugins/cache/" in norm:
        versions_dir = os.path.dirname(root)
        try:
            siblings = sorted(d for d in os.listdir(versions_dir)
                              if os.path.isdir(os.path.join(versions_dir, d)))
            if len(siblings) > 1:
                warn(f"multiple cached plugin versions ({', '.join(siblings)}) under "
                     f"{versions_dir} — if behavior looks stale, uninstall+reinstall; "
                     f"`claude plugin update` no-ops on an unchanged version string")
            else:
                ok("single cached plugin version (no stale siblings)")
        except Exception:  # noqa: BLE001
            pass


def check_repo():
    r = run(["git", "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        warn("not inside a git repository — repo-level checks skipped")
        return
    root = r.stdout.strip()
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")
    if not os.path.isfile(ctx):
        ok(f"no .codearbiter/CONTEXT.md in {root} — codeArbiter is dormant here "
           f"by design (run /ca:init to opt in)")
        return
    enabled, malformed = frontmatter_enabled(ctx)
    if malformed:
        fail("CONTEXT.md frontmatter opens with --- but never closes — the "
             "activation check cannot evaluate; fix the frontmatter")
    elif enabled:
        ok("repo is arbiter-enabled (CONTEXT.md frontmatter)")
    else:
        ok("CONTEXT.md present but not arbiter-enabled — gates dormant by design")
    if enabled:
        with open(ctx, encoding="utf-8", errors="replace") as f:
            body = f.read()
        if "<!--INITIALIZED-->" in body:
            ok("project is initialized (<!--INITIALIZED--> marker present)")
        else:
            warn("no <!--INITIALIZED--> marker — startup will route to "
                 "/ca:decompose or /ca:create-context")
        email = run(["git", "config", "user.email"]).stdout.strip()
        if email:
            ok(f"git identity for audit attribution: {email}")
        else:
            warn("git user.email is unset — overrides/ADRs cannot be attributed; "
                 "set it before gated work")


def check_statusline(root):
    settings = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        with open(settings, encoding="utf-8") as f:
            cmd = (json.load(f).get("statusLine") or {}).get("command", "")
    except Exception:  # noqa: BLE001
        cmd = ""
    if "statusline.py" in cmd:
        ok("statusline wired in ~/.claude/settings.json")
    else:
        ok("statusline not wired (optional — /ca:statusline installs it)")


def main():
    utf8_stdio()
    root = plugin_root()
    check_interpreters()
    check_payload(root)
    check_repo()
    check_statusline(root)
    width = max(len(lvl) for lvl, _ in results)
    for lvl, line in results:
        print(f"{lvl:<{width}}  {line}")
    fails = sum(1 for lvl, _ in results if lvl == "FAIL")
    warns = sum(1 for lvl, _ in results if lvl == "WARN")
    print(f"\ndoctor: {fails} FAIL, {warns} WARN, "
          f"{len(results) - fails - warns} OK")
    if fails:
        print("verdict: UNHEALTHY — at least one gate cannot function as installed")
        sys.exit(1)
    print("verdict: healthy (static checks) — the live-fire probe in /ca:doctor "
          "proves hooks actually fire")


if __name__ == "__main__":
    main()
