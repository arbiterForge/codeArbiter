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
#   python wire-statusline.py refresh      # self-heal a stale ca-owned path only
#                                          # (no-op unless ours AND changed) — run
#                                          # from SessionStart so a plugin update
#                                          # re-points the pin automatically
#
# Options (mainly for testing):
#   --settings PATH     target settings.json (default: ~/.claude/settings.json)
#   --plugin-root PATH  plugin root (default: $CLAUDE_PLUGIN_ROOT or this script's parent)
#   --interp CMD        interpreter token for the command
#                       (default: this Python's own absolute path, i.e. sys.executable)

import argparse
import json
import os
import re
import sys

# Self-sufficient regardless of how this file is loaded (direct `python
# wire-statusline.py` run, or importlib spec_from_file_location as
# session-start.py and the test suite both do) — always resolve _hooklib
# relative to THIS file rather than relying on the caller's sys.path state.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hooklib  # noqa: E402
import hostapi  # noqa: E402 — host seam (ADR-0011): plugin-root resolution

BACKUP_KEY = "_codearbiterStatuslineBackup"       # holds the prior statusLine value
OWNER_KEY = "_codearbiterStatuslineOwner"         # exact command last written by us
SPINNER_BACKUP_KEY = "_codearbiterSpinnerVerbsBackup"  # holds prior spinnerVerbs
_COMMAND_RE = re.compile(
    r'''^\s*(?P<interp>"[^"]*"|'[^']*'|\S+)\s+'''
    r'''(?P<script>"[^"]*"|'[^']*'|\S+)\s*$''')
_PYTHON_EXE_RE = re.compile(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?$")

ARBITER_SPINNER_VERBS = {
    "mode": "replace",
    "verbs": [
        "Deliberating",
        "Weighing the evidence",
        "Consulting precedent",
        "Reviewing the docket",
        "Summoning the council",
        "In chambers",
        "Examining exhibits",
        "Drafting the ruling",
        "Calling order",
        "Overruling prior context",
        "Sustaining the objection",
        "Issuing findings",
        "Cross-examining the codebase",
        "Invoking arbitration",
        "Rendering judgment",
    ],
}


def plugin_root(opt):
    if opt:
        return os.path.abspath(opt)
    # Host seam (ADR-0011): CLAUDE_PLUGIN_ROOT then this script's parent —
    # exactly the prior inline lookup (hostapi.py lives in the same hooks/ dir,
    # so its file-relative fallback names the same root). get_host() (#257),
    # not a direct hostapi.load_host(): resolves the SAME Host run(host)
    # injected instead of triggering a second disk load.
    return os.path.abspath(_hooklib.get_host().plugin_root())


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


def _owned_command(command):
    """Recognize legacy versioned codeArbiter renderer commands.

    Accept the exact two-token command shape only when the script argument ends
    in codearbiter/{ca|ca-codex}/VERSION/hooks/statusline.py.
    """
    parsed = _python_script(command)
    if parsed is None:
        return False
    script, windows_path = parsed
    suffix = re.split(r"[\\/]", script)[-8:]
    if len(suffix) < 8:
        return False
    expected = [".claude", "plugins", "cache", "codearbiter", None,
                None, "hooks", "statusline.py"]
    compared = [part.lower() for part in suffix] if windows_path else suffix
    fixed = [part.lower() if windows_path and part is not None else part
             for part in expected]
    return (
        compared[0:4] == fixed[0:4]
        and compared[4] == "ca"
        and bool(suffix[5])
        and compared[6:] == fixed[6:]
    )


def _python_script(command):
    if not isinstance(command, str):
        return None
    match = _COMMAND_RE.fullmatch(command)
    if not match:
        return None
    script = match.group("script")
    if len(script) >= 2 and script[0] == script[-1] and script[0] in "\"'":
        script = script[1:-1]
    windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", script)) or "\\" in script
    interp = match.group("interp")
    if len(interp) >= 2 and interp[0] == interp[-1] and interp[0] in "\"'":
        interp = interp[1:-1]
    interp_name = re.split(r"[\\/]", interp)[-1]
    if not _PYTHON_EXE_RE.fullmatch(interp_name.lower() if windows_path else interp_name):
        return None
    return script, windows_path


def _legacy_source_command(command):
    """Recognize the exact pre-metadata source-tree install path."""
    parsed = _python_script(command)
    if parsed is None:
        return False
    script, windows_path = parsed
    suffix = re.split(r"[\\/]", script)[-5:]
    expected = ["codeArbiter", "plugins", "ca", "hooks", "statusline.py"]
    if windows_path:
        suffix = [part.lower() for part in suffix]
        expected = [part.lower() for part in expected]
    return suffix == expected
def is_ours(statusline, settings=None):
    command = statusline.get("command") if isinstance(statusline, dict) else statusline
    if (isinstance(settings, dict)
            and isinstance(command, str)
            and settings.get(OWNER_KEY) == command):
        return True
    if not isinstance(statusline, dict):
        if isinstance(statusline, str):
            return _owned_command(statusline) or _legacy_source_command(statusline)
        return False
    return (_owned_command(statusline.get("command"))
            or _legacy_source_command(statusline.get("command")))


def owned_statusline(command):
    return {
        "type": "command",
        "command": command,
        "padding": 0,
    }


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
    """Write `data` to `path` atomically (reliability-009).

    Routed through _hooklib.write_text_atomic, which stages to a UNIQUE
    per-process temp file (tempfile.mkstemp, not a fixed `path + ".tmp"`
    sibling name) before os.replace(). settings.json is the user's WHOLE host
    configuration, not a ca-owned file: two sessions racing a heal/install
    right after a plugin update previously both staged to the same fixed
    `.tmp` name and could clobber each other's temp content on interleave. A
    unique name per call removes that collision entirely."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    _hooklib.write_text_atomic(path, text)


def cmd_status(settings, exists, script_abs):
    sl = settings.get("statusLine")
    print(f"settings.json: {'present' if exists else 'absent'}")
    print(f"statusline.py: {script_abs}  ({'found' if os.path.exists(script_abs) else 'MISSING'})")
    if sl is None:
        print("statusLine.command: (none set)")
    else:
        cmd = sl.get("command") if isinstance(sl, dict) else sl
        print(f"statusLine.command: {cmd}")
        print("wired to codeArbiter: " + ("YES" if is_ours(sl, settings) else "no (a different statusline owns it)"))
    if BACKUP_KEY in settings:
        b = settings[BACKUP_KEY]
        print(f"backup on file: {b.get('command') if isinstance(b, dict) else b}")
    sv = settings.get("spinnerVerbs")
    if sv is None:
        print("spinnerVerbs: (none set)")
    else:
        count = len(sv.get("verbs", [])) if isinstance(sv, dict) else "?"
        owned = SPINNER_BACKUP_KEY in settings
        print(f"spinnerVerbs: {count} verb(s), {'codeArbiter' if owned else 'user-owned'}")


def cmd_install(settings, path, script_abs, interp):
    if not os.path.exists(script_abs):
        raise SystemExit(f"ERROR: renderer not found at {script_abs}; nothing wired.")
    new_cmd = build_command(interp, script_abs)
    current = settings.get("statusLine")
    if is_ours(current, settings):
        # already ours: just refresh the path (e.g. after a plugin upgrade)
        settings["statusLine"] = owned_statusline(new_cmd)
        settings[OWNER_KEY] = new_cmd
        _install_spinner_verbs(settings, refresh=True)
        save_settings(path, settings)
        print(f"REFRESHED codeArbiter statusline path -> {new_cmd}")
        return
    # Back up whatever is there. If a stale backup exists from an earlier cycle
    # but the user has since wired a DIFFERENT third-party statusline, the live
    # one wins — overwriting it without a fresh backup would lose the user's
    # current line and restore the wrong one on uninstall.
    if BACKUP_KEY not in settings or current is not None:
        settings[BACKUP_KEY] = current  # may be None
    settings["statusLine"] = owned_statusline(new_cmd)
    settings[OWNER_KEY] = new_cmd
    _install_spinner_verbs(settings, refresh=False)
    save_settings(path, settings)
    print(f"WIRED codeArbiter statusline -> {new_cmd}")
    prior = settings[BACKUP_KEY]
    if prior is not None:
        pc = prior.get("command") if isinstance(prior, dict) else prior
        print(f"backed up prior statusLine: {pc}")
    else:
        print("no prior statusLine existed; uninstall will simply remove ours.")


def refresh_if_stale(settings, script_abs, interp):
    """Self-heal a ca-owned statusLine whose command has gone stale (e.g. it points
    at a previous plugin-version dir after an update). Mutates `settings` IN PLACE
    and returns True iff something changed.

    Scope is deliberately narrow — this is NOT install:
      - statusLine is ours AND its command != the desired current command -> rewrite, True
      - statusLine is ours and already current                            -> no change, False
      - statusLine is a third-party line, or absent                       -> never touched, False

    Returning a changed-flag lets the caller persist ONLY on a real change, so a
    steady-state session start never churns settings.json."""
    current = settings.get("statusLine")
    if not is_ours(current, settings):
        return False
    desired = build_command(interp, script_abs)
    cur_cmd = current.get("command") if isinstance(current, dict) else current
    if cur_cmd == desired and settings.get(OWNER_KEY) == desired:
        return False
    settings["statusLine"] = owned_statusline(desired)
    settings[OWNER_KEY] = desired
    return True


def cmd_refresh(settings, path, script_abs, interp):
    """SessionStart self-heal entry. Refresh a stale ca-owned path and persist ONLY
    if it changed; otherwise leave settings.json untouched (no mtime churn)."""
    if not os.path.exists(script_abs):
        # Renderer missing (mid-update?) — do nothing rather than write a path that
        # 404s. A later session with the file present will heal it.
        return
    if refresh_if_stale(settings, script_abs, interp):
        save_settings(path, settings)
        print(f"REFRESHED stale codeArbiter statusline path -> {settings['statusLine']['command']}")


def _install_spinner_verbs(settings, refresh):
    current_sv = settings.get("spinnerVerbs")
    already_ours = SPINNER_BACKUP_KEY in settings
    if already_ours:
        # Refresh: update to latest verb list, preserve the backup.
        settings["spinnerVerbs"] = ARBITER_SPINNER_VERBS
        return
    # First install: back up whatever is there (may be None), then set ours.
    if not refresh or current_sv is not None:
        settings[SPINNER_BACKUP_KEY] = current_sv
    settings["spinnerVerbs"] = ARBITER_SPINNER_VERBS


def cmd_uninstall(settings, path, script_abs):
    current = settings.get("statusLine")
    current_cmd = current.get("command") if isinstance(current, dict) else current
    if OWNER_KEY in settings and settings.get(OWNER_KEY) != current_cmd:
        # The user replaced our line after install. Never restore an older backup
        # over that newer choice; only discard our now-stale bookkeeping.
        settings.pop(OWNER_KEY, None)
        settings.pop(BACKUP_KEY, None)
        _uninstall_spinner_verbs(settings)
        save_settings(path, settings)
        print("codeArbiter statusline was replaced; preserved the current line.")
        return
    if not is_ours(current, settings) and BACKUP_KEY not in settings:
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
    settings.pop(OWNER_KEY, None)
    _uninstall_spinner_verbs(settings)
    save_settings(path, settings)


def _uninstall_spinner_verbs(settings):
    if SPINNER_BACKUP_KEY not in settings:
        return
    prior_sv = settings.pop(SPINNER_BACKUP_KEY)
    if prior_sv is None:
        settings.pop("spinnerVerbs", None)
    else:
        settings["spinnerVerbs"] = prior_sv


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("action", nargs="?", default="status",
                    choices=["install", "uninstall", "status", "refresh"])
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
    elif args.action == "refresh":
        cmd_refresh(settings, spath, script_abs, interp)


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main(argv) unchanged — main()'s return value
    stays discarded exactly as the old bare `main()` guard discarded it (so
    the process still exits 0 on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so `plugin_root()`'s `get_host()` call
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    _hooklib.set_host(host)
    main(argv)
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
