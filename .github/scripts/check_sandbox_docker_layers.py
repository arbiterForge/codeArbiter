#!/usr/bin/env python3
"""Assert every ca-sandbox real-container layer actually EXECUTED (issue #406).

`docker info` answering once at the top of the CI job proves the daemon was
alive for one probe.  It does not prove that the isolation, mount, network,
lifecycle and teardown suites ran - and those suites are the only evidence that
ca-sandbox, the driver that clones UNTRUSTED repositories, actually contains
them.  Before this gate a runner Docker outage turned all 31 of them into skips
and the required job still exited 0.

The mechanism has two halves:

  * `plugins/ca-sandbox/tools/docker-gate.ts` appends one line per gated layer
    to $CA_SANDBOX_DOCKER_SENTINEL when that layer's suite STARTS;
  * this script scans the same directory for the layers the sources DECLARE and
    fails unless the recorded set matches.

Both directions are enforced.  A declared layer that never recorded means a
suite silently stopped running; a recorded layer nothing declares means the
sentinel and the scanner have drifted apart, which makes the first check
untrustworthy.

Usage:
    python .github/scripts/check_sandbox_docker_layers.py --sentinel <path>
                                                         [--repo-root <path>]

Stdlib-only, like the rest of .github/scripts.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_TOOLS = ("plugins", "ca-sandbox", "tools")

# `const d = dockerGate("isolation", { linux: true });`
_GATE_CALL = re.compile(r'dockerGate\(\s*"(?P<layer>[A-Za-z0-9][A-Za-z0-9._-]*)"')

# Files whose `dockerGate("...")` occurrences are NOT layer declarations:
#   docker-gate.test.ts  - the gate's own unit test, which drives it with
#                          throwaway layer names that no suite ever records;
#   __fixtures__/**      - the #406 reproduction fixture, deliberately run only
#                          as a failing child process.
_SCAN_SKIP_NAMES = frozenset({"docker-gate.test.ts"})
_SCAN_SKIP_DIRS = frozenset({"__fixtures__", "node_modules"})


def sandbox_test_files(repo_root: Path) -> list[Path]:
    """Every ca-sandbox Vitest file that may declare a docker-gated layer."""
    tools = repo_root.joinpath(*SANDBOX_TOOLS)
    if not tools.is_dir():
        return []
    found = [
        path
        for path in tools.rglob("*.test.ts")
        if not _SCAN_SKIP_DIRS.intersection(path.relative_to(tools).parts)
        and path.name not in _SCAN_SKIP_NAMES
    ]
    return sorted(found)


def declared_layer_sites(repo_root: Path) -> dict[str, list[str]]:
    """Layer name -> the files declaring it.  A layer must have exactly one site."""
    sites: dict[str, list[str]] = {}
    for path in sandbox_test_files(repo_root):
        text = path.read_text(encoding="utf-8")
        for layer in {match.group("layer") for match in _GATE_CALL.finditer(text)}:
            sites.setdefault(layer, []).append(path.name)
    return {layer: sorted(files) for layer, files in sites.items()}


def declared_layers(repo_root: Path) -> set[str]:
    """Layer names the committed ca-sandbox sources gate a real-container suite on."""
    return set(declared_layer_sites(repo_root))


def recorded_layers(sentinel: Path) -> set[str]:
    """Layer names the gate appended at runtime.  Repeats collapse."""
    return {
        line.strip()
        for line in sentinel.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def verify(repo_root: Path, sentinel: Path) -> tuple[int, str]:
    """Return (exit code, human report)."""
    sites = declared_layer_sites(repo_root)
    shared = {layer: files for layer, files in sites.items() if len(files) > 1}
    if shared:
        # Two suites behind one sentinel key: either one alone recording makes
        # both look executed, so the coverage check silently loses a layer.
        return 1, "layer names shared by more than one suite: " + "; ".join(
            f"{layer} <- {', '.join(files)}" for layer, files in sorted(shared.items())
        )
    declared = set(sites)
    if not declared:
        return 1, (
            "no dockerGate() layer declarations found under "
            f"{'/'.join(SANDBOX_TOOLS)} - the scan drifted off the sources, so a "
            "green sentinel would prove nothing."
        )
    if not sentinel.is_file():
        return 1, (
            f"the execution sentinel {sentinel} does not exist. Not one docker-gated "
            "ca-sandbox layer recorded that it ran, which is exactly the silent-skip "
            "failure this gate exists to catch (issue #406)."
        )
    recorded = recorded_layers(sentinel)
    if not recorded:
        return 1, (
            f"the execution sentinel {sentinel} is empty - no docker-gated ca-sandbox "
            "layer recorded that it ran."
        )
    missing = sorted(declared - recorded)
    unknown = sorted(recorded - declared)
    problems: list[str] = []
    if missing:
        problems.append(
            "real-container layers that never executed: "
            + ", ".join(missing)
            + ". Docker was reachable at preflight but these suites did not run; "
            "the containment guarantees they own are unproven."
        )
    if unknown:
        problems.append(
            "sentinel layers no source declares: "
            + ", ".join(unknown)
            + ". The runtime gate and this scanner disagree, so the coverage check "
            "above cannot be trusted."
        )
    if problems:
        return 1, "\n".join(problems)
    return 0, "every declared real-container layer executed: " + ", ".join(sorted(declared))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sentinel",
        required=True,
        help="path of the append-only file written by CA_SANDBOX_DOCKER_SENTINEL",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repository root to scan for layer declarations",
    )
    args = parser.parse_args(argv)
    code, report = verify(Path(args.repo_root), Path(args.sentinel))
    if code == 0:
        print(report)
    else:
        print(f"::error::ca-sandbox docker layer sentinel: {report}", file=sys.stderr)
        print(report, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
