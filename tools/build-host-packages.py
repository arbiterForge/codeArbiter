#!/usr/bin/env python3
"""Generate dependency-free host package metadata from canonical descriptors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_descriptors import HostDescriptor, host_descriptor  # noqa: E402


REPO = Path(__file__).resolve().parents[1]
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def render_package(
    host: HostDescriptor,
    version: str,
    license_spdx: str = "AGPL-3.0-only",
) -> bytes:
    """Render root Pi Git-package metadata as deterministic UTF-8 bytes."""
    if host.name != "pi":
        raise ValueError(f"root Git package metadata is unsupported for host {host.name!r}")
    document = {
        "name": "ca-pi",
        "version": version,
        "private": True,
        "license": license_spdx,
        "engines": {"node": ">=22.19.0"},
        "pi": {
            "extensions": [f"./{host.plugin_dir}/extensions/codearbiter.js"],
            "skills": [f"./{host.plugin_dir}/skills"],
        },
    }
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def expected_package(repo: Path = REPO) -> bytes:
    host = host_descriptor("pi", str(repo))
    nested = repo / host.plugin_dir / "package.json"
    metadata = json.loads(nested.read_text(encoding="utf-8"))
    version = metadata["version"]
    if not isinstance(version, str) or not version:
        raise ValueError(f"{nested}: version must be a non-empty string")
    license_spdx = metadata.get("license")
    if not isinstance(license_spdx, str) or not license_spdx:
        raise ValueError(f"{nested}: license must be a non-empty SPDX string")
    return render_package(host, version, license_spdx)


def _semver_key(value: str) -> tuple[int, int, int, tuple[tuple[int, object], ...] | None]:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ValueError(f"{value!r} is not valid SemVer")
    prerelease = match.group(4)
    if prerelease is None:
        pre_key = None
    else:
        pre_key = tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in prerelease.split(".")
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), pre_key


def _semver_greater(current: str, base: str) -> bool:
    current_key = _semver_key(current)
    base_key = _semver_key(base)
    if current_key[:3] != base_key[:3]:
        return current_key[:3] > base_key[:3]
    current_pre, base_pre = current_key[3], base_key[3]
    if current_pre is None:
        return base_pre is not None
    if base_pre is None:
        return False
    return current_pre > base_pre


def validate_pi_release_advance(
    *,
    current_version: str,
    base_version: str,
    root_version: str,
    changelog: str,
    base_changelog: str,
    root_changed: bool,
    changelog_changed: bool,
) -> str | None:
    """Return an actionable diagnosis when Pi release metadata is inconsistent."""
    try:
        advances = _semver_greater(current_version, base_version)
    except ValueError as error:
        return str(error)
    if not advances:
        return f"ca-pi version must strictly advance from {base_version} to a higher SemVer (got {current_version})"
    if root_version != current_version:
        return f"root Pi version {root_version} does not match ca-pi {current_version}"
    if not root_changed:
        return "ca-pi version advanced without regenerated root metadata"
    if not changelog_changed:
        return "ca-pi version advanced without a changelog change"
    heading = re.compile(rf"^## \[{re.escape(current_version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?$", re.MULTILINE)
    if heading.search(changelog) is None:
        return f"missing exact changelog heading for ca-pi {current_version}"
    if heading.search(base_changelog) is not None:
        return f"changelog heading for ca-pi {current_version} was not newly introduced relative to base"
    return None


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO, text=True, encoding="utf-8", capture_output=True, check=check
    )


def pi_release_guard(base_ref: str) -> int:
    plugin_manifest = REPO / "plugins" / "ca-pi" / "package.json"
    changelog_path = REPO / "plugins" / "ca-pi" / "CHANGELOG.md"
    if _git("diff", "--quiet", f"{base_ref}...HEAD", "--", "plugins/ca-pi", "package.json", check=False).returncode == 0:
        print("no Pi payload change - version bump not required")
        return 0
    if _git("rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}", check=False).returncode != 0:
        print(f"{base_ref} does not resolve to a commit - bad ref or failed fetch", file=sys.stderr)
        return 1
    current = json.loads(plugin_manifest.read_text(encoding="utf-8"))["version"]
    root = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["version"]
    changelog = changelog_path.read_text(encoding="utf-8")
    try:
        _semver_key(current)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    base_file = f"{base_ref}:plugins/ca-pi/package.json"
    if _git("cat-file", "-e", base_file, check=False).returncode != 0:
        if root != current or re.search(rf"^## \[{re.escape(current)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?$", changelog, re.MULTILINE) is None:
            print("new ca-pi package has inconsistent root version or changelog heading", file=sys.stderr)
            return 1
        print("ca-pi is new on the base - first introduction metadata is consistent")
        return 0
    base = json.loads(_git("show", base_file).stdout)["version"]
    base_changelog = _git("show", f"{base_ref}:plugins/ca-pi/CHANGELOG.md", check=False)
    if base_changelog.returncode != 0:
        print("base ca-pi package is missing CHANGELOG.md", file=sys.stderr)
        return 1
    diagnosis = validate_pi_release_advance(
        current_version=current,
        base_version=base,
        root_version=root,
        changelog=changelog,
        base_changelog=base_changelog.stdout,
        root_changed=_git("diff", "--quiet", f"{base_ref}...HEAD", "--", "package.json", check=False).returncode != 0,
        changelog_changed=_git("diff", "--quiet", f"{base_ref}...HEAD", "--", "plugins/ca-pi/CHANGELOG.md", check=False).returncode != 0,
    )
    if diagnosis:
        print(diagnosis, file=sys.stderr)
        return 1
    if _git("rev-parse", "--verify", "--quiet", f"refs/tags/ca-pi-v{current}", check=False).returncode == 0:
        print(f"ca-pi version {current} is already tagged", file=sys.stderr)
        return 1
    print(f"Pi payload, version, changelog, and root metadata advanced together: {base} -> {current}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--release-guard-base")
    args = parser.parse_args(argv)
    target = REPO / "package.json"
    expected = expected_package()
    if args.check:
        if not target.is_file() or target.read_bytes() != expected:
            print("package.json is stale; run python tools/build-host-packages.py", file=sys.stderr)
            return 1
        print("package.json matches plugins/ca-pi/package.json and the Pi descriptor")
        if not args.release_guard_base:
            return 0
    if args.release_guard_base:
        return pi_release_guard(args.release_guard_base)
    target.write_bytes(expected)
    print("generated package.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
