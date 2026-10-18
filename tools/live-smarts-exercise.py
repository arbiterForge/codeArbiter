#!/usr/bin/env python3
"""Live exercise of conditional SMARTS in /ca:feature brainstorming (plan T-29).

Runs two headless Claude Code sessions with the installed ca plugin, each in its
own throwaway repository outside this checkout, then reads the spec each one
wrote through the engine's own model block:

  material  - a feature with two or more materially plausible approaches; the
              spec's SEC-SMARTS must carry a comparison across the lenses.
  single    - a feature with one obvious approach; SEC-SMARTS must hold a
              one-line statement and no SMARTS table.

This calls a real model and costs tokens, so it is a manual check, not a CI step.
Exit 0 only when every selected case matches. Options: --keep retains the throwaway
repos; --plugin-dir DIR tests an unreleased plugin directory (for example this
checkout's plugins/ca) with the installed ca plugin disabled for the session;
--case NAME runs one case.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LENSES = ("Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable")

APP = '''"""Tiny exchange-rate CLI."""
import argparse
import time

__version__ = "0.3.1"


def fetch_rates(base: str) -> dict[str, float]:
    """Fetch rates from the (simulated) upstream service; slow and rate-limited."""
    time.sleep(2)
    return {"USD": 1.0, "EUR": 0.92, "GBP": 0.79} if base == "USD" else {base: 1.0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rates")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("base")
    args = parser.parse_args(argv)
    if args.command == "show":
        for code, rate in fetch_rates(args.base).items():
            print(f"{code} {rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

TEST = '''from rates import main


def test_show_usd(capsys):
    assert main(["show", "USD"]) == 0
    assert "EUR 0.92" in capsys.readouterr().out
'''

CASES = {
    "material": (
        "Add persistent caching of fetch_rates() results across separate CLI runs, expiring after "
        "10 minutes, with a new --cache-dir option to choose where the cache lives."
    ),
    "single": "Add a new `version` subcommand to the rates CLI that prints the package version.",
}

SUFFIX = (
    "\n\nThis is an unattended evaluation run in a throwaway repository. Do not stop to ask "
    "questions: choose reasonable defaults for any open choice yourself and record them. Use the "
    "full lane, complete brainstorming and write the spec through the installed engine, then stop "
    "before writing-plans. Do not implement anything."
)


def option(name: str) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def plugin_root() -> Path:
    if option("--plugin-dir"):
        return Path(option("--plugin-dir")).resolve()
    data = json.loads((Path.home() / ".claude/plugins/installed_plugins.json").read_text(encoding="utf-8"))
    entries = data.get("plugins", data).get("ca@codearbiter") or []
    if not entries:
        sys.exit("ca@codearbiter is not installed")
    return Path(entries[0]["installPath"])


def run(argv: list[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def scaffold(root: Path, plugin: Path) -> None:
    (root / "rates.py").write_text(APP, encoding="utf-8")
    (root / "test_rates.py").write_text(TEST, encoding="utf-8")
    for argv in (["git", "init", "-q", "-b", "main"], ["git", "add", "."],
                 ["git", "-c", "user.name=exercise", "-c", "user.email=exercise@example.invalid",
                  "commit", "-q", "-m", "initial"]):
        run(argv, root).check_returncode()
    init = run([sys.executable, str(plugin / "hooks/init-codearbiter.py"), "--root", str(root)], root)
    if init.returncode != 0:
        sys.exit(f"init-codearbiter failed:\n{init.stdout}\n{init.stderr}")


def spec_model(root: Path) -> dict | None:
    specs = sorted((root / ".codearbiter/specs").glob("*.html"))
    if not specs:
        return None
    html = specs[0].read_text(encoding="utf-8")
    match = re.search(r'<script[^>]*application/json[^>]*>(.*?)</script>', html, re.S)
    return json.loads(match.group(1)) if match else None


def smarts_section(model: dict) -> dict | None:
    return next((s for s in model["normative"].get("sections", []) if s.get("id") == "SEC-SMARTS"), None)


def section_text(section: dict) -> str:
    return json.dumps(section.get("blocks", []), ensure_ascii=False)


def judge(case: str, root: Path) -> tuple[bool, str]:
    model = spec_model(root)
    triage = (root / ".codearbiter/triage.log")
    lane = triage.read_text(encoding="utf-8") if triage.exists() else ""
    if model is None:
        return False, f"no HTML spec was written (triage: {lane.strip() or 'none'})"
    section = smarts_section(model)
    approach = json.dumps(model["normative"].get("approach", {}), ensure_ascii=False)
    if section is None:
        return False, f"spec has no SEC-SMARTS section; approach={approach[:400]}"
    text = section_text(section)
    blocks = section.get("blocks", [])
    lenses = [lens for lens in LENSES if lens in text]
    has_table = any(b.get("type") == "table" for b in blocks) or "|---" in text
    detail = f"blocks={len(blocks)} lenses={lenses} table={has_table}\nSEC-SMARTS={text[:1500]}"
    if case == "material":
        return len(lenses) >= 3, detail
    one_line = len(blocks) == 1 and len(text) < 600
    return one_line and not has_table and len(lenses) <= 1, detail


def main() -> int:
    keep = "--keep" in sys.argv
    plugin = plugin_root()
    print(f"plugin: {plugin}")
    selected = {name: CASES[name] for name in ([option("--case")] if option("--case") else CASES)}
    host = []
    if option("--plugin-dir"):
        host = ["--plugin-dir", str(plugin), "--settings", json.dumps({"enabledPlugins": {"ca@codearbiter": False}})]
    results = {}
    for case, request in selected.items():
        root = Path(tempfile.mkdtemp(prefix=f"smarts-live-{case}-"))
        try:
            scaffold(root, plugin)
            env = dict(os.environ)
            env.pop("NO_COLOR", None)
            session = run(["claude", "-p", f"/ca:feature {request}{SUFFIX}",
                           "--permission-mode", "acceptEdits",
                           "--allowedTools", "Bash Read Write Edit Glob Grep Skill",
                           "--output-format", "text", *host], root, env=env, timeout=3600)
            ok, detail = judge(case, root)
            results[case] = ok
            print(f"\n=== {case}: {'PASS' if ok else 'FAIL'} (session exit {session.returncode}) ===")
            print(detail)
            print("--- session tail ---")
            print(session.stdout[-1500:])
        finally:
            if keep:
                print(f"kept: {root}")
            else:
                shutil.rmtree(root, ignore_errors=True)
    return 0 if all(results.values()) and len(results) == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
