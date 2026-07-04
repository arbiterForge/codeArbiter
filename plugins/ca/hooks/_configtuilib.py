"""codeArbiter config — interactive terminal picker (no curses).

Claude Code's Bash tool is non-interactive, so this UI only ever runs when a
human launches configtool.py directly in a real terminal (or via `launch`,
which opens one). Two rendering modes share the same flow:

  raw       arrow-key navigation — termios/tty on POSIX, msvcrt on Windows
  fallback  numbered menus over plain input() — dumb terminals, pipes, and
            anything supports_raw() declines

curses is deliberately absent: it does not exist on stock Windows Python, and
the whole picker is three screens (group -> setting -> value). Deliberately
NOT here: alternate screen buffer, resize handling, mouse — that is the
lightweight line this tool stays under (ADR 0004 spirit: no infrastructure
the job doesn't need).

Everything takes injected streams/env so the tests never need a real tty.
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _configlib  # noqa: E402

ESC = "\x1b"
_ANSI = {
    "reset": ESC + "[0m", "bold": ESC + "[1m", "dim": ESC + "[2m",
    "invert": ESC + "[7m", "cyan": ESC + "[36m", "yellow": ESC + "[33m",
    "up": ESC + "[1A", "clearline": ESC + "[2K",
}


# --------------------------------------------------------------------------- #
# Capability probes — each one small and injectable, so the truth tables are
# unit-testable without a terminal.
# --------------------------------------------------------------------------- #

def supports_raw(stdin=None, stdout=None, environ=None, platform=None):
    """Raw-mode arrow keys need: both streams on a tty, a terminal that is not
    'dumb', and a per-key reader for the platform (termios or msvcrt)."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    environ = environ if environ is not None else os.environ
    platform = platform or sys.platform
    try:
        if not (stdin.isatty() and stdout.isatty()):
            return False
    except Exception:  # noqa: BLE001 — stream without isatty
        return False
    if environ.get("TERM", "").lower() == "dumb":
        return False
    if platform == "win32":
        try:
            import msvcrt  # noqa: F401
            return True
        except ImportError:
            return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
        return True
    except ImportError:
        return False


def can_launch(environ=None, platform=None):
    """Best launch method for popping the picker in a NEW terminal, or None
    when there is nowhere to put a window (headless SSH, containers,
    remote/web sessions). tmux wins when present — a split lands right next
    to the session the user is already in."""
    environ = environ if environ is not None else os.environ
    platform = platform or sys.platform
    if environ.get("TMUX"):
        return "tmux"
    if platform == "darwin":
        return "macos"
    if platform == "win32":
        return "windows"
    if environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"):
        return "linux"
    return None


_LINUX_TERMS = ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm")


def launch_command(method, script, environ=None, which=shutil.which):
    """argv to open the picker in a new terminal via `method`, or None when
    the method's prerequisites are missing after all."""
    environ = environ if environ is not None else os.environ
    py = sys.executable or "python3"
    inner = '%s "%s"' % (py, script)
    if method == "tmux":
        return ["tmux", "split-window", "-h", inner]
    if method == "macos":
        return ["osascript", "-e",
                'tell application "Terminal" to do script "%s"' % inner.replace('"', '\\"'),
                "-e", 'tell application "Terminal" to activate']
    if method == "windows":
        return ["cmd", "/c", "start", "codeArbiter config", py, script]
    if method == "linux":
        term = environ.get("TERMINAL")
        if term and which(term):
            return [term, "-e", py, script]
        for cand in _LINUX_TERMS:
            if which(cand):
                if cand == "gnome-terminal":
                    return [cand, "--", py, script]
                return [cand, "-e", py, script]
    return None


def launch(script, environ=None, platform=None, spawn=None):
    """Detached best-effort spawn. Returns a human message either way — this
    must degrade to instructions, never a stack trace."""
    method = can_launch(environ, platform)
    py = sys.executable or "python3"
    manual = 'run it yourself in a terminal:  %s "%s"' % (py, script)
    if method is None:
        return ("no display detected (headless/remote session) — " + manual)
    argv = launch_command(method, script, environ)
    if argv is None:
        return ("no terminal emulator found — " + manual)
    spawn = spawn or (lambda a: subprocess.Popen(
        a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=(os.name != "nt")))
    try:
        spawn(argv)
        return "opened the interactive picker via %s" % method
    except Exception as e:  # noqa: BLE001
        return ("could not open a terminal (%s) — %s" % (e, manual))


# --------------------------------------------------------------------------- #
# Key input
# --------------------------------------------------------------------------- #

def decode_posix(read1):
    """One normalized key token from a byte-at-a-time reader: UP/DOWN/LEFT/
    RIGHT/ENTER/ESC or the literal character."""
    ch = read1()
    if ch in ("\r", "\n"):
        return "ENTER"
    if ch != ESC:
        return ch
    nxt = read1()
    if nxt != "[":
        return "ESC"
    final = read1()
    return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(final, "ESC")


def decode_windows(getwch):
    ch = getwch()
    if ch in ("\r", "\n"):
        return "ENTER"
    if ch == ESC:
        return "ESC"
    if ch in ("\xe0", "\x00"):
        return {"H": "UP", "P": "DOWN", "M": "RIGHT", "K": "LEFT"}.get(getwch(), "ESC")
    return ch


def read_key(stdin=None):
    """Blocking single-key read in raw/cbreak mode. Only called after
    supports_raw() said yes."""
    if sys.platform == "win32":
        import msvcrt
        return decode_windows(msvcrt.getwch)
    import termios
    import tty
    stdin = stdin if stdin is not None else sys.stdin
    fd = stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return decode_posix(lambda: stdin.read(1))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _c(stdout, code, text):
    if getattr(stdout, "isatty", lambda: False)():
        return _ANSI[code] + text + _ANSI["reset"]
    return text


def banner(stdout):
    line = "═" * 38
    stdout.write(_c(stdout, "cyan", "╔%s╗\n" % line))
    stdout.write(_c(stdout, "cyan", "║") + _c(stdout, "bold", "   ⚖   codeArbiter · configuration   ") + _c(stdout, "cyan", "║\n"))
    stdout.write(_c(stdout, "cyan", "╚%s╝\n" % line))
    stdout.write(_c(stdout, "dim", "  values persist to Claude Code settings.json; applied at next session start\n\n"))


def _option_line(label, selected, stdout):
    marker = "» " if selected else "  "
    text = marker + label
    return _c(stdout, "invert", text) if selected else text


def pick(options, title, stdout, stdin, raw, key_reader=None):
    """Select one of `options` (list of display strings). Returns the index or
    None (back/quit). Raw mode: arrow keys + enter, q/ESC backs out. Fallback:
    numbered menu, blank/q backs out."""
    key_reader = key_reader or read_key
    stdout.write(_c(stdout, "bold", title) + "\n")
    if not raw:
        for i, label in enumerate(options, 1):
            stdout.write("  %2d. %s\n" % (i, label))
        stdout.write("  (number to select, blank/q to go back)\n")
        while True:
            stdout.write("> ")
            stdout.flush()
            line = stdin.readline()
            if not line:
                return None
            s = line.strip().lower()
            if s in ("", "q", "b", "back"):
                return None
            if s.isdigit() and 1 <= int(s) <= len(options):
                return int(s) - 1
            stdout.write("  pick 1-%d\n" % len(options))

    idx = 0
    for i, label in enumerate(options):
        stdout.write(_option_line(label, i == idx, stdout) + "\n")
    stdout.flush()
    while True:
        key = key_reader(stdin)
        if key in ("q", "Q", "ESC"):
            return None
        if key == "ENTER":
            return idx
        if key == "UP":
            idx = (idx - 1) % len(options)
        elif key == "DOWN":
            idx = (idx + 1) % len(options)
        else:
            continue
        stdout.write((_ANSI["up"] + _ANSI["clearline"]) * len(options))
        for i, label in enumerate(options):
            stdout.write(_option_line(label, i == idx, stdout) + "\n")
        stdout.flush()


# --------------------------------------------------------------------------- #
# The three-screen flow
# --------------------------------------------------------------------------- #

def _setting_label(rec):
    val = rec["effective"] if rec["effective"] is not None else "(unset)"
    badge = "  [preview]" if rec["status"] == "preview" else ""
    star = "*" if rec["source"] != "default" else " "
    return "%s %-36s = %-22s (%s)%s" % (star, rec["name"], val, rec["source"], badge)


def _prompt_line(stdout, stdin, prompt):
    stdout.write(prompt)
    stdout.flush()
    line = stdin.readline()
    return None if not line else line.strip()


def edit_setting(reg, rec, paths, environ, stdout, stdin, raw, key_reader=None):
    """Editor for one setting: choice list for enum/bool, validated free line
    for the rest; then scope, confirm, write."""
    entry, _ = _configlib.find_entry(reg, rec["name"])
    stdout.write("\n%s\n  %s\n  default: %s   current: %s (%s)\n" % (
        _c(stdout, "bold", rec["name"]), rec["description"],
        rec["default"] if rec["default"] is not None else "(unset)",
        rec["effective"] if rec["effective"] is not None else "(unset)", rec["source"]))
    if entry.get("sensitive"):
        stdout.write(_c(stdout, "yellow",
                        "  sensitive: never persisted here — export it in your shell profile instead\n"))
        return False

    if entry["type"] in ("enum", "bool"):
        values = entry.get("values") or ["on", "off"]
        i = pick(list(values) + ["(unset — fall back to default)"],
                 "new value:", stdout, stdin, raw, key_reader)
        if i is None:
            return False
        unset = i == len(values)
        value = None if unset else values[i]
    else:
        line = _prompt_line(stdout, stdin, "new value (blank to cancel, '-' to unset): ")
        if not line:
            return False
        if line == "-":
            unset, value = True, None
        else:
            ok, value, msg = _configlib.validate(entry, line)
            if not ok:
                stdout.write(_c(stdout, "yellow", "  invalid: %s\n" % msg))
                return False
            unset = False

    scopes = ["user", "project", "local"]
    default_scope = entry.get("scope", "user")
    labels = ["%s%s  (%s)" % (s, "  <- suggested" if s == default_scope else "", paths[s])
              for s in scopes]
    si = pick(labels, "write to which scope?", stdout, stdin, raw, key_reader)
    if si is None:
        return False
    scope = scopes[si]

    action = ("unset %s" % rec["name"]) if unset else ("%s = %s" % (rec["name"], value))
    ci = pick(["yes — write it", "no — leave everything untouched"],
              "confirm: %s -> %s settings?" % (action, scope), stdout, stdin, raw, key_reader)
    if ci != 0:
        return False

    if unset:
        rep = _configlib.unset_value(reg, rec["name"], scope, paths)
    else:
        rep = _configlib.set_value(reg, rec["name"], value, scope, paths, environ)
    if rep["changed"]:
        stdout.write("  wrote %s (was: %s)\n" % (rep["path"], rep.get("prior") or "(unset)"))
    else:
        stdout.write("  no change needed\n")
    if rep.get("warning"):
        stdout.write(_c(stdout, "yellow", "  %s\n" % rep["warning"]))
    stdout.write(_c(stdout, "yellow", "  %s\n" % _configlib.RESTART_NOTICE))
    return bool(rep["changed"])


def run_interactive(reg=None, environ=None, paths=None,
                    stdin=None, stdout=None, raw=None, key_reader=None):
    """Group -> setting -> editor, looping until the user backs all the way
    out. Returns the number of writes performed."""
    reg = reg or _configlib.load_registry()
    environ = environ if environ is not None else os.environ
    paths = paths or _configlib.settings_paths()
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    raw = supports_raw(stdin, stdout, environ) if raw is None else raw

    banner(stdout)
    group_keys = list(reg["groups"])
    writes = 0
    while True:
        recs = _configlib.snapshot(reg, environ, paths)
        changed_counts = {g: sum(1 for r in recs if r["group"] == g and r["source"] != "default")
                          for g in group_keys}
        glabels = ["%-14s %s%s" % (g, reg["groups"][g],
                                   ("   [%d set]" % changed_counts[g]) if changed_counts[g] else "")
                   for g in group_keys]
        gi = pick(glabels, "settings groups  (q to quit)", stdout, stdin, raw, key_reader)
        if gi is None:
            break
        group = group_keys[gi]
        while True:
            recs = [r for r in _configlib.snapshot(reg, environ, paths) if r["group"] == group]
            si = pick([_setting_label(r) for r in recs],
                      "%s  (q for groups)" % group, stdout, stdin, raw, key_reader)
            if si is None:
                break
            if edit_setting(reg, recs[si], paths, environ, stdout, stdin, raw, key_reader):
                writes += 1
    if writes:
        stdout.write("\n%d change(s) written. %s\n" % (writes, _configlib.RESTART_NOTICE))
    return writes
