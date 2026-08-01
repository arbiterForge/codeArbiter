#!/usr/bin/env python3
"""Issue #530 — a shipped payload change must ride a version that can reach an install.

`claude plugin update` is a NO-OP when the manifest version string is unchanged,
so a changed payload riding an already-shipped version silently never reaches
installed users. That is the whole reason the per-plugin version gates exist.

The gates USED to ask "does tag `v<version>` exist?" — and a marketplace install
populates its cache from the MANIFEST VERSION, with no tag involved. So a version
can be installed somewhere while being untagged, and in exactly that window the
guard was inert against the changes it exists to catch.

Found live on 2026-07-27: `plugins/ca` had read `2.9.1` since 2026-07-24 with no
`v2.9.1` tag ever pushed, so three payload PRs merged green under
"payload changed on unpublished version - allowed". Two of them carried real
changes — a coverage-exemption tightening and an H-11/H-05 hook reclassification —
and neither reached the maintainer's own install. The hook fix stayed dormant in
the very session that wrote it.

THE RULE (#530 AC-1/AC-2): once a version string is on the default branch with
payload attached, that string is SPENT. The next payload change must advance the
manifest. A genuinely first-time version — one whose manifest does not exist on
the base at all — still passes, so the ordinary bump-then-ship flow is unaffected.

Since the base always carries both a manifest and a payload, "already on the
default branch with payload attached" reduces to "the version did not advance
from base", which is checkable with no tag and no network.

`ca-pi` is NOT gated here (#530 AC-3). Its guard lives in
`tools/build-host-packages.py --release-guard-base`, which ALREADY required a
strict advance and was never exposed to this bug; it additionally enforces
changelog and root-metadata synchronization that the other three do not have. The
two paths share one definition of "advance" — `_releaselib.semver_greater` — so
they cannot drift apart on the question this gate turns on.

Usage (CI):
    python3 .github/scripts/payload_version_gate.py --plugin plugins/ca --base origin/main
exits 0 when the payload may ship, 1 with a GitHub error annotation when it may
not, and 2 on a usage error. A git failure exits non-zero, so an unreadable base
fails the gate rather than passing it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _releaselib import load_targets, semver_greater, semver_key  # noqa: E402
import payload_scope  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DECLARED_TARGETS = REPO / ".codearbiter" / "release-targets.md"


def tag_prefixes(targets_path: Path = DECLARED_TARGETS) -> dict[str, str]:
    """`{payload directory basename: tag prefix}`, DERIVED from the declared
    release-targets file (A-4.1) rather than from a constant.

    Before this, the map was `_releaselib.RELEASE_TAG_PREFIXES` — a literal
    in the CI shim listing four plugin names and their namespaces. Two
    sources of truth for the same fact: a target declared in
    `.codearbiter/release-targets.md` with a prefix the constant disagreed
    with would be GATED under one namespace and RELEASED under another, and
    nothing compared them. Adding a fifth plugin meant editing both, and
    forgetting the constant produced a `KeyError` at gate time rather than
    a diagnosable message.

    Keyed on the payload's basename, not on the target NAME, because that
    is what the caller has: the gate walks `plugins/*` directories and asks
    "what namespace does this directory release under". A row whose payload
    is not a single directory (a consumer's `payload: .`) contributes no
    entry — this gate is a codeArbiter-repo check over `plugins/*`, and a
    whole-repo payload has no basename to key on.
    """
    prefixes: dict[str, str] = {}
    for row in load_targets(str(targets_path)):
        payload = (row.get("payload") or "").strip().strip("/")
        if not payload or payload == ".":
            continue
        prefixes[payload.rsplit("/", 1)[-1]] = row["prefix"]
    return prefixes

# Each gated plugin's manifest, relative to the repo root. `ca-codex` is a Codex
# package and keeps its manifest under `.codex-plugin/`; the other two are Claude
# Code plugins under `.claude-plugin/`. The tag namespace is NOT repeated here —
# it is DERIVED from `.codearbiter/release-targets.md` by `tag_prefixes()` above
# (A-4.1), so a plugin cannot be gated under one namespace and released under
# another — the gate and the release lane now read the same declaration.
#
# `plugins/ca-pi` is deliberately absent: see the module docstring. Its exclusion
# is asserted by test_payload_version_gate.py, so adding it here without removing
# the build-host-packages guard turns that suite red rather than double-gating.
GATED_MANIFESTS: dict[str, str] = {
    "plugins/ca": "plugins/ca/.claude-plugin/plugin.json",
    "plugins/ca-sandbox": "plugins/ca-sandbox/.claude-plugin/plugin.json",
    "plugins/ca-codex": "plugins/ca-codex/.codex-plugin/plugin.json",
}

PASS = 0
FAIL = 1
USAGE = 2


def _git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )


def _manifest_version(text: str) -> str | None:
    """The `version` string from manifest `text`, or None if it is not one."""
    try:
        value = json.loads(text)["version"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) and value else None


def head_version(plugin: str, root: Path = REPO) -> str | None:
    manifest = root / GATED_MANIFESTS[plugin]
    try:
        return _manifest_version(manifest.read_text(encoding="utf-8"))
    except OSError:
        return None


def base_version(base: str, plugin: str, root: Path = REPO) -> str | None:
    """The manifest version at `base`, or None when the manifest is absent there.

    None means FIRST INTRODUCTION and is a pass. `git cat-file -e` on the
    `tree-ish:path` form exits 128 rather than 1 when the path is missing, so
    absence cannot be told from a bad ref by exit code — the caller resolves the
    ref first (see `gate`), and only then is a read failure genuine absence."""
    shown = _git(["show", f"{base}:{GATED_MANIFESTS[plugin]}"], root)
    if shown.returncode != 0:
        return None
    return _manifest_version(shown.stdout)


def tag_exists(tag: str, root: Path = REPO) -> bool:
    return _git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}"], root).returncode == 0


def gate(base: str, plugin: str, root: Path = REPO) -> tuple[int, str]:
    """Return `(exit_code, message)` for one plugin's payload-version decision."""
    manifest = GATED_MANIFESTS[plugin]
    annotate = f"::error file={manifest}::"

    # Resolve the base FIRST. `payload_scope.payload_changed` raises on an
    # unresolvable ref, so checking afterwards left this branch unreachable and
    # surfaced a traceback where an operator needs a diagnosis. Fail-closed
    # either way, but only one of the two says what to do about it.
    if _git(["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], root).returncode != 0:
        return FAIL, f"::error::{base} does not resolve to a commit - bad ref or failed fetch"

    if not payload_scope.payload_changed(base, plugin, root=root):
        return PASS, "no shipped payload change - version bump not required"

    current = head_version(plugin, root)
    if current is None:
        return FAIL, f"{annotate}{manifest} is missing or has no usable version string"

    # Diagnose an unparseable version HERE rather than letting it fall through.
    # `semver_greater` degrades to False on malformed input, which is the right
    # gate answer and the wrong explanation: it would report "the version is
    # still <garbage>", sending the reader to look for a bump they already made.
    if semver_key(current) is None:
        return FAIL, (
            f"{annotate}{manifest} declares version {current!r}, which is not valid SemVer, "
            f"so whether it advances cannot be decided. Fix the version string."
        )

    previous = base_version(base, plugin, root)
    if previous is None:
        # The plugin does not exist on the base at all. Nothing is published, so
        # no install can be holding a stale copy of this version. #530 AC-2.
        return PASS, f"{plugin} is new on the base - first introduction, version {current}"

    if not semver_greater(current, previous):
        return FAIL, (
            f"{annotate}{plugin}/** shipped payload changed, but the manifest version is "
            f"still {current} (base has {previous}). That version string is already on the "
            f"default branch WITH payload attached, so a marketplace install already holds a "
            f"copy of it and `claude plugin update` no-ops on an unchanged version - this "
            f"change would silently never reach installed users. A tag is NOT what makes a "
            f"version published (issue #530). Advance the version."
        )

    namespaces = tag_prefixes()
    name = Path(plugin).name
    if name not in namespaces:
        return FAIL, (
            f"{annotate}{plugin}/** is gated here but declares no release target "
            f"in .codearbiter/release-targets.md, so this gate cannot tell which "
            f"tag namespace it publishes under. Declare a row for it, or remove "
            f"it from GATED_MANIFESTS — a gated payload with no declared "
            f"namespace is exactly the drift this derivation exists to end. "
            f"(Before A-4.1 this was a KeyError against a hardcoded map.)"
        )
    tag = f"{namespaces[name]}{current}"
    if tag_exists(tag, root):
        return FAIL, (
            f"{annotate}{plugin}/** shipped payload changed on version {current}, which is "
            f"already released (tag {tag} exists). The version advanced from {previous}, so "
            f"it was claimed by another branch or reused after a revert. Pick an unreleased "
            f"version."
        )

    return PASS, f"shipped payload changed and version advanced: {previous} -> {current}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", required=True, help="e.g. plugins/ca-sandbox")
    parser.add_argument("--base", required=True, help="base ref, e.g. origin/main")
    arguments = parser.parse_args(argv)
    if arguments.plugin not in GATED_MANIFESTS:
        print(
            f"unknown plugin {arguments.plugin!r}; declare its manifest in "
            f"{Path(__file__).name} before gating it (ca-pi is gated by "
            f"tools/build-host-packages.py instead - see this file's docstring)",
            file=sys.stderr,
        )
        return USAGE
    code, message = gate(arguments.base, arguments.plugin)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
