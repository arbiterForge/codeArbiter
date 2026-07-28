#!/usr/bin/env python3
"""Issue #435 — which paths under a plugin count as SHIPPED payload.

The per-plugin version gates exist for one reason: `claude plugin update` is a
NO-OP when the manifest version string is unchanged, so a changed payload riding
an already-published version silently never reaches installed users.

They path-scoped to `plugins/<name>` WHOLESALE, which made a dev-only
`plugins/<name>/tools/package-lock.json` bump demand a manifest advance and a
CHANGELOG heading for a change no installed user can observe. The real cost is
not the annoyance — it is that a version bump is supposed to mean "installed
users need this", and training contributors to bump one to silence a gate is
precisely the habit the gate exists to prevent.

`plugins/<name>/tools/` is a BUILD directory: TypeScript sources, a vitest
config, a lockfile, node_modules. Nothing there runs on an installed machine —
EXCEPT the committed esbuild artifacts, which absolutely do. So the rule is:
everything under the plugin counts, except its `tools/` build directory, of
which the declared artifacts count.

The artifact list is deliberately explicit rather than a glob. It is the load-
bearing half of the exclusion: an artifact that is renamed, relocated, or newly
added and not declared here silently stops being gated, which is the exact
failure the gate prevents. `test_payload_scope.py` pins it in both directions —
every declared artifact must exist, and every committed `*.js` under a `tools/`
directory must be declared.

Usage (CI):
    python .github/scripts/payload_scope.py --plugin plugins/ca --base origin/main
prints `changed` or `unchanged`, and exits 0 either way. A git failure exits
non-zero, so an unreadable base fails the gate rather than passing it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Committed build artifacts that live INSIDE a plugin's excluded `tools/`
# directory and DO ship. ca-pi's bundles live in `extensions/`, outside the
# excluded scope, so it declares none.
SHIPPED_TOOLS_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "plugins/ca": ("plugins/ca/tools/farm.js",),
    # #377: ca-sandbox ships TWO binaries. `claude-inside.js` is deliberately
    # separate from `sandbox.js` - it starts a container holding a live OAuth
    # token, and the sandbox-claude-inside skill's five BLOCK gates are what
    # make that safe, so it is not a `sandbox` subcommand anyone can reach.
    "plugins/ca-sandbox": (
        "plugins/ca-sandbox/tools/sandbox.js",
        "plugins/ca-sandbox/tools/claude-inside.js",
    ),
    "plugins/ca-pi": (),
    # #530: ca-codex's gate used to diff the plugin WHOLESALE, so it was the one
    # lane with no declared scope at all. It has no `tools/` directory and ships
    # no committed `.js`, so declaring it changes nothing today - and the day it
    # grows a build directory, it inherits the same rule as its siblings instead
    # of quietly demanding a version bump for a lockfile.
    "plugins/ca-codex": (),
}


def pathspec(plugin: str) -> list[str]:
    """The `git diff` pathspec for `plugin`'s shipped payload, minus `tools/`.

    Directory-shaped, not a denylist of known dev filenames: a build-time file
    nobody has thought of yet must not reintroduce the tax by default."""
    return [plugin, f":(exclude){plugin}/tools"]


def _diff_is_empty(args: list[str], root: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed ({result.returncode}): {result.stderr.strip()}")
    return result.returncode == 0


def payload_changed(base: str, plugin: str, root: Path = REPO) -> bool:
    """True iff `plugin`'s SHIPPED payload differs between `base` and HEAD.

    Two diffs rather than one pathspec: git's exclusions are subtractive only,
    so an excluded directory cannot be partially re-included. Excluding `tools/`
    and then asking about the declared artifacts separately says exactly what is
    meant, and keeps the artifact list somewhere a test can read it."""
    if not _diff_is_empty([f"{base}...HEAD", "--", *pathspec(plugin)], root):
        return True
    artifacts = SHIPPED_TOOLS_ARTIFACTS.get(plugin, ())
    if not artifacts:
        return False
    return not _diff_is_empty([f"{base}...HEAD", "--", *artifacts], root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", required=True, help="e.g. plugins/ca-sandbox")
    parser.add_argument("--base", required=True, help="base ref, e.g. origin/main")
    arguments = parser.parse_args(argv)
    if arguments.plugin not in SHIPPED_TOOLS_ARTIFACTS:
        print(
            f"unknown plugin {arguments.plugin!r}; declare its shipped tools artifacts in "
            f"{Path(__file__).name} before gating it",
            file=sys.stderr,
        )
        return 2
    print("changed" if payload_changed(arguments.base, arguments.plugin) else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
