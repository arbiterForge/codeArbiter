#!/usr/bin/env python3
"""Promote one qualified Claude Code package through Git distribution refs.

The native artifact engine is never committed to main, so main's public
catalog points `ca` at the `ca-marketplace` branch (a git-subdir source). This
tool publishes the exact qualified release archive as an immutable orphan
`ca-dist-v<version>` tag, then advances `ca-marketplace` to a commit carrying
the same tree. Re-running with the same inputs is a no-op; a same-version tag
naming different bytes, or a channel rollback, is refused.
"""
from __future__ import annotations
import argparse, importlib.util, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("packager", HERE / "build-host-packages.py")
PACKAGER = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PACKAGER)
CODEX_SPEC = importlib.util.spec_from_file_location("codex_promoter", HERE / "promote-codex-marketplace.py")
CODEX = importlib.util.module_from_spec(CODEX_SPEC); CODEX_SPEC.loader.exec_module(CODEX)
MARKETPLACE_REF = "refs/heads/" + PACKAGER.CLAUDE_MARKETPLACE_BRANCH
MANIFEST = "plugins/ca/.claude-plugin/plugin.json"


def _channel_version(repo: Path, commit: str) -> str | None:
    shown = CODEX._git(repo, "show", f"{commit}:{MANIFEST}", check=False)
    if shown.returncode != 0: return None
    try: version = json.loads(shown.stdout)["version"]
    except (KeyError, TypeError, ValueError): return None
    return version if PACKAGER.semver_key(version) is not None else None


def promote(*, package_root: Path, cohort_sha256: str, source_commit: str,
            remote_url: str, version: str, work: Path, push: bool) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None: raise ValueError("source commit must be a full lowercase commit id")
    if not remote_url or "\n" in remote_url or "\r" in remote_url: raise ValueError("publication remote URL is invalid")
    if PACKAGER.semver_key(version) is None: raise ValueError("Claude distribution version must be SemVer")
    work = work.absolute()
    if work.exists() or work.is_symlink(): raise ValueError("Claude distribution work path already exists")
    work.mkdir(); distribution = work / "distribution"
    staged = PACKAGER.stage_claude_marketplace_distribution(package_root=package_root,
        package_cohort_sha256=cohort_sha256, output=distribution)
    if staged.get("source_commit") != source_commit: raise ValueError("Claude distribution cohort is bound to a different source commit")
    manifest = json.loads((distribution / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("version") != version: raise ValueError("Claude distribution version does not match the qualified package")

    CODEX._git(distribution, "init", "--quiet"); CODEX._git(distribution, "remote", "add", "publication", remote_url)
    CODEX._git(distribution, "add", "--all"); tree = CODEX._git(distribution, "write-tree").stdout.strip()
    distribution_commit = CODEX._commit_tree(distribution, tree, message=(
        f"codeArbiter ca {version} qualified distribution\n\n"
        f"source-commit: {source_commit}\npackage-cohort-sha256: {cohort_sha256}\n"
        f"archive-sha256: {staged['archive_sha256']}"), parents=[])
    distribution_ref = f"refs/tags/ca-dist-v{version}"
    existing_distribution = CODEX._remote_commit(distribution, distribution_ref)
    if existing_distribution is not None and existing_distribution != distribution_commit:
        raise ValueError("same-version Claude distribution ref already names different bytes")

    existing_marketplace = CODEX._remote_commit(distribution, MARKETPLACE_REF)
    channel_commit = None
    if existing_marketplace is not None:
        CODEX._git(distribution, "fetch", "--quiet", "--no-tags", "publication",
                   f"{MARKETPLACE_REF}:refs/remotes/codearbiter/marketplace")
        current_version = _channel_version(distribution, existing_marketplace)
        if current_version is not None and PACKAGER.semver_key(version) < PACKAGER.semver_key(current_version):
            raise ValueError("Claude marketplace channel cannot roll back to an older version")
        current_tree = CODEX._git(distribution, "rev-parse", f"{existing_marketplace}^{{tree}}").stdout.strip()
        if current_tree == tree: channel_commit = existing_marketplace
    if channel_commit is None:
        channel_commit = CODEX._commit_tree(distribution, tree,
            message=f"Promote ca {version} qualified distribution",
            parents=([existing_marketplace] if existing_marketplace else []) + [distribution_commit])

    result = {**staged, "distribution_ref": distribution_ref,
              "distribution_commit": distribution_commit, "marketplace_ref": MARKETPLACE_REF,
              "marketplace_previous_commit": existing_marketplace,
              "marketplace_commit": channel_commit}
    if push:
        if existing_distribution is None:
            CODEX._git(distribution, "push", "publication", f"{distribution_commit}:{distribution_ref}")
        if CODEX._remote_commit(distribution, distribution_ref) != distribution_commit:
            raise RuntimeError("Claude distribution tag readback drifted")
        if existing_marketplace != channel_commit:
            lease = f"--force-with-lease={MARKETPLACE_REF}:{existing_marketplace or '0' * 40}"
            CODEX._git(distribution, "push", lease, "publication", f"{channel_commit}:{MARKETPLACE_REF}")
        if CODEX._remote_commit(distribution, MARKETPLACE_REF) != channel_commit:
            raise RuntimeError("Claude marketplace channel readback drifted")
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ("cohort-sha256", "source-commit", "remote-url", "version"): p.add_argument("--" + name, required=True)
    for name in ("package-root", "work"): p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--push", action="store_true")
    a = p.parse_args(argv)
    print(json.dumps(promote(package_root=a.package_root, cohort_sha256=a.cohort_sha256,
        source_commit=a.source_commit, remote_url=a.remote_url, version=a.version,
        work=a.work, push=a.push), indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
