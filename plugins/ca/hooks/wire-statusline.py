#!/usr/bin/env python3
# codeArbiter — statusline wire-up. Writes (or removes) the statusLine.command
# in the user's ~/.claude/settings.json so the renderer at hooks/statusline.py
# runs everywhere.
#
# A plugin cannot own a statusLine, and ${CLAUDE_PLUGIN_ROOT} is NOT expanded
# inside settings.json, so the absolute path must be resolved and written at
# install time — which is exactly what this does.
#
# Usage:
#   python wire-statusline.py install      # back up any existing line, wire ours
#   python wire-statusline.py uninstall    # restore the backed-up line (or remove)
#   python wire-statusline.py status       # report current wiring, change nothing
#
# Options (mainly for testing):
#   --settings PATH     target settings.json (default: ~/.claude/settings.json)
#   --plugin-root PATH  plugin root (default: $CLAUDE_PLUGIN_ROOT or this script's parent)
#   --interp CMD        interpreter token for the command
#                       (default: this Python's own absolute path, i.e. sys.executable)

import argparse
import json
import os
import sys

BACKUP_KEY = "_codearbiterStatuslineBackup"   # holds the prior statusLine value
MARKER = "statusline.py"                        # how we recognize our own line


def plugin_root(opt):
    if opt:
        return os.path.abspath(opt)
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return os.path.abspath(env)
    # this script lives in <root>/hooks/
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def settings_path(opt):
    if opt:
        return os.path.abspath(opt)
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def default_interp(opt):
    if opt:
        return opt
    # Prefer this Python's own absolute path: bare `python` is PATH-dependent and
    # renders a blank bar when it resolves to nothing or the wrong interpreter.
    if sys.executable:
        return sys.executable
    return "python" if os.name == "nt" else "python3"


def build_command(interp, script_abs):
    # Quote BOTH tokens; the host pipes the statusline JSON to this command on
    # stdin. On Windows an unquoted interp path (even one without spaces) makes
    # Claude Code's statusLine runner silently emit nothing — a blank bar.
    return f'"{interp}" "{script_abs}"'


def is_ours(statusline):
    if not isinstance(statusline, dict):
        if isinstance(statusline, str):
            return MARKER in statusline
        return False
    return MARKER in str(statusline.get("command", ""))


def load_settings(path):
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return (json.loads(text) if text.strip() else {}), True
    except ValueError as e:
        raise SystemExit(
            f"REFUSING TO WRITE: {path} is not valid JSON ({e}). "
            "Fix it by hand, then re-run - I will not clobber an unparseable settings file.")


def save_settings(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def cmd_status(settings, exists, script_abs):
    sl = settings.get("statusLine")
    print(f"settings.json: {'present' if exists else 'absent'}")
    print(f"statusline.py: {script_abs}  ({'found' if os.path.exists(script_abs) else 'MISSING'})")
    if sl is None:
        print("statusLine.command: (none set)")
    else:
        cmd = sl.get("command") if isinstance(sl, dict) else sl
        print(f"statusLine.command: {cmd}")
        print("wired to codeArbiter: " + ("YES" if is_ours(sl) else "no (a different statusline owns it)"))
    if BACKUP_KEY in settings:
        b = settings[BACKUP_KEY]
        print(f"backup on file: {b.get('command') if isinstance(b, dict) else b}")


def cmd_install(settings, path, script_abs, interp):
    if not os.path.exists(script_abs):
        raise SystemExit(f"ERROR: renderer not found at {script_abs}; nothing wired.")
    new_cmd = build_command(interp, script_abs)
    current = settings.get("statusLine")
    if is_ours(current):
        # already ours: just refresh the path (e.g. after a plugin upgrade)
        settings["statusLine"] = {"type": "command", "command": new_cmd, "padding": 0}
        save_settings(path, settings)
        print(f"REFRESHED codeArbiter statusline path -> {new_cmd}")
        return
    # back up whatever is there (only if we haven't already stashed one)
    if BACKUP_KEY not in settings:
        settings[BACKUP_KEY] = current  # may be None
    settings["statusLine"] = {"type": "command", "command": new_cmd, "padding": 0}
    save_settings(path, settings)
    print(f"WIRED codeArbiter statusline -> {new_cmd}")
    prior = settings[BACKUP_KEY]
    if prior is not None:
        pc = prior.get("command") if isinstance(prior, dict) else prior
        print(f"backed up prior statusLine: {pc}")
    else:
        print("no prior statusLine existed; uninstall will simply remove ours.")


def cmd_uninstall(settings, path, script_abs):
    current = settings.get("statusLine")
    if not is_ours(current) and BACKUP_KEY not in settings:
        print("codeArbiter statusline is not wired here; nothing to do.")
        return
    if BACKUP_KEY in settings:
        prior = settings.pop(BACKUP_KEY)
        if prior is None:
            settings.pop("statusLine", None)
            print("REMOVED codeArbiter statusline; no prior line to restore.")
        else:
            settings["statusLine"] = prior
            pc = prior.get("command") if isinstance(prior, dict) else prior
            print(f"RESTORED prior statusLine: {pc}")
    else:
        settings.pop("statusLine", None)
        print("REMOVED codeArbiter statusline.")
    save_settings(path, settings)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("action", nargs="?", default="status",
                    choices=["install", "uninstall", "status"])
    ap.add_argument("--settings")
    ap.add_argument("--plugin-root")
    ap.add_argument("--interp")
    args = ap.parse_args(argv)

    root = plugin_root(args.plugin_root)
    script_abs = os.path.join(root, "hooks", "statusline.py")
    spath = settings_path(args.settings)
    interp = default_interp(args.interp)

    settings, exists = load_settings(spath)

    if args.action == "status":
        cmd_status(settings, exists, script_abs)
    elif args.action == "install":
        cmd_install(settings, spath, script_abs, interp)
    elif args.action == "uninstall":
        cmd_uninstall(settings, spath, script_abs)


if __name__ == "__main__":
    main()
