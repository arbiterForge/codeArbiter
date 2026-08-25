#!/usr/bin/env python3
"""Issue #408 — prove ca-codex installs into a REAL Codex host.

The live-parity runbook already says what the static adapter test cannot do: it
cannot prove that Codex delivers payloads, discovers hooks, or honours a block.
Every required parity check invokes Python directly, and no workflow has ever
installed or launched a real Codex runtime — so a protocol, trust, or
hook-discovery regression can merge with every gate green.

WHAT THIS COVERS, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------
A 2026-07-26 spike measured the boundary. Installing the checked-out plugin
through a real host needs NO credential and NO network:

    codex plugin marketplace add <checkout>     # local path is a valid SOURCE
    codex plugin add ca-codex@<marketplace>
    codex plugin list                           # -> installed, enabled, <version>

Proving a hook FIRES does not. A hook runs inside a turn and a turn needs a
model: `codex exec` against an unreachable provider initialises a complete
session and then dies at the network boundary, having injected nothing. So the
live enforcement proof needs a provider credential, which cannot be a required
check on fork PRs, and is tracked separately.

This script is therefore the credential-free half, and it says so rather than
implying the rest is covered.

THE GATE, mirroring `plugins/ca-sandbox/tools/docker-gate.ts` (#406)
--------------------------------------------------------------------
A missing runtime must not look like a pass:

    CA_REQUIRE_CODEX=1   a real host is a PREREQUISITE. An absent or unusable
                         `codex` exits non-zero instead of skipping. CI sets
                         this; developer machines do not.

Without it, an absent runtime SKIPS with an explicit notice and exit 0, which is
right on a laptop and wrong on a merge gate.

Usage:
    python .github/scripts/check_codex_host.py          # audit, JSON to stdout
    python .github/scripts/check_codex_host.py --json   # same, machine-readable only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json"
HOOKS_JSON = REPO / "plugins" / "ca-codex" / "hooks" / "hooks.json"

# A workspace-relative home, NOT the system temp directory. Measured: Codex
# refuses to create its helper binaries under a temp dir and warns on every
# invocation ("Refusing to create helper binaries under temporary dir"), which
# buries the lane's real output in noise.
CODEX_HOME = REPO / ".codex-host-check"

SCHEMA = "codearbiter-codex-host-v1"


def _run(args: list[str], home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CODEX_HOME"] = str(home)
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=str(REPO))


def codex_version() -> str | None:
    """The runtime's version, or None when no usable `codex` is on PATH."""
    if shutil.which("codex") is None:
        return None
    try:
        proc = subprocess.run(["codex", "--version"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def expected_version() -> str:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def check_install(home: Path) -> list[dict]:
    """Install the CHECKED-OUT plugin through the real host and read it back."""
    results: list[dict] = []

    def record(code: str, ok: bool, detail: str = "") -> None:
        results.append({"code": code, "status": "pass" if ok else "fail",
                        **({"detail": detail} if detail and not ok else {})})

    added = _run(["codex", "plugin", "marketplace", "add", str(REPO)], home)
    record("CODEX-HOST-MARKETPLACE", added.returncode == 0,
           (added.stderr or added.stdout).strip()[-400:])
    if added.returncode != 0:
        return results

    installed = _run(["codex", "plugin", "add", "ca-codex@codearbiter"], home)
    record("CODEX-HOST-INSTALL", installed.returncode == 0,
           (installed.stderr or installed.stdout).strip()[-400:])
    if installed.returncode != 0:
        return results

    listed = _run(["codex", "plugin", "list"], home)
    out = listed.stdout
    record("CODEX-HOST-LIST", listed.returncode == 0,
           (listed.stderr or out).strip()[-400:])

    # The read-back is the point: an install that reports success but leaves the
    # plugin DISABLED is exactly the drift a static adapter test cannot see.
    row = next((line for line in out.splitlines() if line.startswith("ca-codex@")), "")
    record("CODEX-HOST-ENABLED", "installed" in row and "enabled" in row, row.strip())

    # What this version check can and cannot do, stated because a mutation test
    # showed the obvious reading is wrong: bumping the manifest to 9.9.9 does NOT
    # fail it, because the host installs FROM that same manifest and both sides
    # move together. There is one source of truth, so this cannot detect drift
    # between the checkout and the install.
    #
    # It does catch the failure that is actually possible here: a host that
    # reports no version at all, or resolves a DIFFERENT one - which a stale
    # marketplace snapshot can genuinely cause, since `plugin marketplace
    # upgrade` exists precisely because a snapshot can lag its source.
    want = expected_version()
    record("CODEX-HOST-VERSION", bool(want) and want in row,
           f"expected {want!r} in {row.strip()!r}")

    # The installed CACHE path carries the resolved version independently of the
    # listing text, so a host that reported one version and installed another
    # shows up as a mismatch between these two.
    resolved = sorted(d.name for d in home.glob("plugins/cache/*/ca-codex/*") if d.is_dir())
    record("CODEX-HOST-RESOLVED-VERSION", resolved == [want],
           f"cache holds {resolved}, listing claims {want!r}")

    # The hooks the plugin claims must be present in the INSTALLED copy, not
    # merely in the source tree - the install is a copy, and a copy can drop a
    # dotfile or a subdirectory.
    cached = list(home.glob("plugins/cache/*/ca-codex/*/hooks/hooks.json"))
    record("CODEX-HOST-HOOKS-INSTALLED", len(cached) == 1,
           f"found {len(cached)} installed hooks.json")
    if cached:
        try:
            declared = json.loads(cached[0].read_text(encoding="utf-8"))["hooks"]
            source = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
            record("CODEX-HOST-HOOKS-MATCH", set(declared) == set(source),
                   f"installed {sorted(declared)} vs source {sorted(source)}")
        except (ValueError, KeyError) as error:
            record("CODEX-HOST-HOOKS-MATCH", False, str(error))

        # Issue #408 AC-3. HOOKS-MATCH above compares the installed manifest to
        # the SOURCE manifest — and the install is a fresh copy of that same
        # source, so for anything the source declares the two agree by
        # construction. Measured: adding a hook to source that ships no script
        # left HOOKS-MATCH passing. It can catch the install DROPPING a file
        # (its stated purpose) and nothing else.
        #
        # A hook Codex cannot execute is indistinguishable, from the outside,
        # from a hook that allowed the operation. So resolve every script the
        # INSTALLED manifest points at and require it to exist in the install.
        # Still credential-free: this asks whether the host has something to
        # run, not whether running it blocks.
        plugin_root = cached[0].parent.parent
        missing: list[str] = []
        scripts: set[str] = set()
        try:
            installed = json.loads(cached[0].read_text(encoding="utf-8"))["hooks"]
            for entries in installed.values():
                for entry in entries:
                    for hook in entry.get("hooks", []):
                        for key in ("command", "commandWindows"):
                            command = hook.get(key)
                            if not isinstance(command, str):
                                continue
                            for match in re.finditer(
                                    r"\$\{PLUGIN_ROOT\}/(\S+?\.py)", command):
                                rel = match.group(1)
                                scripts.add(rel)
                                if not (plugin_root / rel).is_file():
                                    missing.append(rel)
            record("CODEX-HOST-HOOK-SCRIPTS", not missing and bool(scripts),
                   f"{len(scripts)} script(s) referenced, missing from the install: "
                   f"{sorted(set(missing))}" if missing
                   else "no hook script references were found to check")
        except (ValueError, KeyError) as error:
            record("CODEX-HOST-HOOK-SCRIPTS", False, str(error))

    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ca-codex real-host install gate (#408)")
    parser.add_argument("--json", action="store_true",
                        help="print only the JSON report")
    arguments = parser.parse_args(argv)

    required = os.environ.get("CA_REQUIRE_CODEX") == "1"
    version = codex_version()

    if version is None:
        report = {"schema": SCHEMA, "status": "fail" if required else "skip",
                  "runtime": None, "results": []}
        print(json.dumps(report))
        if required:
            print("::error::CA_REQUIRE_CODEX=1 but no usable `codex` runtime is on PATH; "
                  "a missing host must not read as a passing gate (#408)", file=sys.stderr)
            return 1
        if not arguments.json:
            print("codex host: no runtime on PATH - SKIPPED "
                  "(set CA_REQUIRE_CODEX=1 to make this a failure)", file=sys.stderr)
        return 0

    # A disposable home, rebuilt every run: a leftover marketplace or a cached
    # plugin from a previous run would let a BROKEN checkout pass on stale state.
    if CODEX_HOME.exists():
        shutil.rmtree(CODEX_HOME, ignore_errors=True)
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    try:
        results = check_install(CODEX_HOME)
    finally:
        shutil.rmtree(CODEX_HOME, ignore_errors=True)

    failed = [r for r in results if r["status"] != "pass"]
    report = {"schema": SCHEMA, "status": "fail" if failed else "pass",
              "runtime": version, "results": results}
    print(json.dumps(report))

    if failed:
        for r in failed:
            print(f"::error::{r['code']}: {r.get('detail', 'failed')}", file=sys.stderr)
        return 1
    if not arguments.json:
        print(f"codex host: {version} installed the checked-out ca-codex "
              f"{expected_version()} and read it back enabled", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
