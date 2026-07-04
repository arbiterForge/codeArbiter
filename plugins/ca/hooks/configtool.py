#!/usr/bin/env python3
# codeArbiter — configtool. The one sanctioned way to read and change every
# user-tunable environment variable in the plugin family (CODEARBITER_*,
# FARM_*, CA_SANDBOX_*), driven by the registry at config/registry.json.
#
# Values persist into Claude Code settings.json `env` blocks and become real
# environment variables at the NEXT session start — no plugin code reads the
# registry at runtime; every existing reader keeps reading plain env vars.
#
# Usage:
#   python configtool.py                       # interactive picker on a real tty,
#                                              # otherwise the grouped table + usage
#   python configtool.py list [--json] [--group G]
#   python configtool.py get KEY [--json]
#   python configtool.py explain KEY
#   python configtool.py set KEY VALUE [--scope user|project|local]
#   python configtool.py unset KEY [--scope user|project|local]
#   python configtool.py doctor [--json]
#   python configtool.py launch                # open the picker in a new terminal
#
# Options (mainly for testing, mirroring wire-statusline.py):
#   --settings-user/-project/-local PATH   override a layer's settings.json path
#   --project-dir PATH                     override the project root

import argparse
import json
import os
import sys

# Self-sufficient regardless of how this file is loaded — resolve sibling libs
# relative to THIS file rather than the caller's sys.path state.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _configlib  # noqa: E402
import _configtuilib  # noqa: E402


def _paths(args):
    paths = _configlib.settings_paths(project_dir=getattr(args, "project_dir", None))
    for scope in ("user", "project", "local"):
        override = getattr(args, "settings_%s" % scope, None)
        if override:
            paths[scope] = os.path.abspath(override)
    return paths


def _fmt_value(v):
    return v if v is not None else "(unset)"


def cmd_list(reg, args, out):
    recs = _configlib.snapshot(reg, os.environ, _paths(args), group=args.group)
    if args.group and not recs:
        raise SystemExit("unknown group %r (groups: %s)" % (args.group, ", ".join(reg["groups"])))
    if args.json:
        out.write(json.dumps({"version": reg["version"], "settings": recs}, indent=2) + "\n")
        return
    for group in reg["groups"]:
        rows = [r for r in recs if r["group"] == group]
        if not rows:
            continue
        out.write("\n%s — %s\n" % (group, reg["groups"][group]))
        for r in rows:
            star = "*" if r["source"] != "default" else " "
            badge = " [preview]" if r["status"] == "preview" else ""
            pending = "  (pending restart, or overridden by shell)" if r["pending"] else ""
            out.write(" %s %-36s %-20s source=%-8s default=%s%s%s\n" % (
                star, r["name"], _fmt_value(r["effective"]), r["source"],
                _fmt_value(r["default"]), badge, pending))
            out.write("      %s\n" % r["description"])
    out.write("\n* = set somewhere (not at its default). %s\n" % _configlib.RESTART_NOTICE)


def cmd_get(reg, args, out):
    recs = [r for r in _configlib.snapshot(reg, os.environ, _paths(args)) if r["name"] == args.key]
    if not recs:
        _, suggestion = _configlib.find_entry(reg, args.key)
        hint = (" — did you mean %s?" % suggestion) if suggestion else ""
        raise SystemExit("unknown setting %r%s" % (args.key, hint))
    r = recs[0]
    if args.json:
        out.write(json.dumps(r, indent=2) + "\n")
        return
    out.write("%s = %s  (source: %s)\n" % (r["name"], _fmt_value(r["effective"]), r["source"]))
    if r["pending"]:
        out.write("  settings layer disagrees with the live session — pending restart, or overridden by shell\n")


def cmd_explain(reg, args, out):
    entry, suggestion = _configlib.find_entry(reg, args.key)
    if entry is None:
        hint = (" — did you mean %s?" % suggestion) if suggestion else ""
        raise SystemExit("unknown setting %r%s" % (args.key, hint))
    r = [x for x in _configlib.snapshot(reg, os.environ, _paths(args)) if x["name"] == args.key][0]
    out.write("%s  [%s, %s]\n  %s\n" % (entry["name"], entry["group"],
                                        entry.get("status", "stable"), entry["description"]))
    out.write("  type: %s%s\n" % (entry["type"],
              (" (%s)" % ", ".join(entry["values"])) if entry.get("values") else ""))
    out.write("  default: %s   effective: %s (source: %s)\n" % (
        _fmt_value(r["default"]), _fmt_value(r["effective"]), r["source"]))
    for scope in ("local", "project", "user"):
        if r["layers"].get(scope) is not None:
            out.write("  %s settings: %s\n" % (scope, r["layers"][scope]))
    if entry.get("requires"):
        for dep, allowed in entry["requires"].items():
            out.write("  requires: %s in [%s]\n" % (dep, ", ".join(allowed)))
    if entry.get("sensitive"):
        out.write("  sensitive: never persisted to settings.json — export it in your shell\n")
    if entry.get("docs"):
        out.write("  docs: %s\n" % entry["docs"])


def cmd_set(reg, args, out):
    rep = _configlib.set_value(reg, args.key, args.value, args.scope, _paths(args))
    if rep["changed"]:
        out.write("set %s = %s in %s scope (%s)\n" % (rep["name"], rep["value"], rep["scope"], rep["path"]))
        out.write("  previous value there: %s\n" % _fmt_value(rep["prior"]))
    else:
        out.write("%s already = %s in %s scope — nothing written\n" % (rep["name"], rep["value"], rep["scope"]))
    if rep.get("warning"):
        out.write("  %s\n" % rep["warning"])
    out.write("  %s\n" % _configlib.RESTART_NOTICE)


def cmd_unset(reg, args, out):
    rep = _configlib.unset_value(reg, args.key, args.scope, _paths(args))
    if rep["changed"]:
        out.write("unset %s in %s scope (was: %s)\n" % (rep["name"], rep["scope"], rep["prior"]))
        out.write("  %s\n" % _configlib.RESTART_NOTICE)
    else:
        out.write("%s was not set in %s scope — nothing to do\n" % (rep["name"], rep["scope"]))


def cmd_doctor(reg, args, out):
    findings = _configlib.doctor(reg, os.environ, _paths(args))
    if args.json:
        out.write(json.dumps({"findings": findings}, indent=2) + "\n")
    elif not findings:
        out.write("config: healthy — every set variable is registered and valid\n")
    else:
        for f in findings:
            out.write("%s: %s\n" % (f["level"].upper(), f["message"]))
    return 1 if any(f["level"] == "error" for f in findings) else 0


def cmd_launch(reg, args, out):
    script = os.path.abspath(__file__)
    out.write(_configtuilib.launch(script) + "\n")


def main(argv=None):
    # Path overrides live on a parent parser shared by every subcommand, so
    # they are accepted both before and after the subcommand token.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--settings-user")
    common.add_argument("--settings-project")
    common.add_argument("--settings-local")
    common.add_argument("--project-dir")

    ap = argparse.ArgumentParser(prog="configtool", parents=[common],
                                 description="codeArbiter settings tool")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", parents=[common])
    p.add_argument("--json", action="store_true"); p.add_argument("--group")
    p = sub.add_parser("get", parents=[common])
    p.add_argument("key"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("explain", parents=[common]); p.add_argument("key")
    p = sub.add_parser("set", parents=[common])
    p.add_argument("key"); p.add_argument("value")
    p.add_argument("--scope", default="user", choices=list(_configlib.WRITE_SCOPES))
    p = sub.add_parser("unset", parents=[common]); p.add_argument("key")
    p.add_argument("--scope", default="user", choices=list(_configlib.WRITE_SCOPES))
    p = sub.add_parser("doctor", parents=[common]); p.add_argument("--json", action="store_true")
    sub.add_parser("launch", parents=[common])

    args = ap.parse_args(argv)
    out = sys.stdout
    reg = _configlib.load_registry()

    if args.cmd is None:
        if _configtuilib.supports_raw() or (sys.stdin.isatty() and sys.stdout.isatty()):
            _configtuilib.run_interactive(reg)
            return 0
        # Non-interactive invocation with no subcommand: show the inventory
        # instead of hanging on key input.
        args.json, args.group = False, None
        cmd_list(reg, args, out)
        out.write("\n(no tty detected — run a subcommand, or run this script in a terminal for the picker)\n")
        return 0

    handler = {"list": cmd_list, "get": cmd_get, "explain": cmd_explain,
               "set": cmd_set, "unset": cmd_unset, "doctor": cmd_doctor,
               "launch": cmd_launch}[args.cmd]
    return handler(reg, args, out) or 0


if __name__ == "__main__":
    sys.exit(main())
