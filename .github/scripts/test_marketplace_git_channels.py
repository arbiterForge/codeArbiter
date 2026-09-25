#!/usr/bin/env python3
"""Contracts for the Git distribution channels that carry the native engine.

Claude Code installs `ca` from main's catalog, which points at the
`ca-marketplace` branch; Codex installs from `ca-codex-marketplace`, whose
catalog pins an immutable `ca-codex-dist-v*` tag. Both channels must carry the
qualified `helpers/artifacts` payload, re-run as a no-op, and refuse to name
different bytes for a published version or to roll back.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))
from _gitexec import _ROOT_OVERRIDE_ENV, root_bound_git_env  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PACKAGER = _load("build_host_packages", REPO / "tools" / "build-host-packages.py")
CLAUDE = _load("promote_claude_marketplace", REPO / "tools" / "promote-claude-marketplace.py")
CODEX = _load("promote_codex_marketplace", REPO / "tools" / "promote-codex-marketplace.py")
IDENTITY = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}


def git(argv, cwd, **kwargs):
    environment = root_bound_git_env()
    environment.update(IDENTITY)
    for name in _ROOT_OVERRIDE_ENV:
        environment.pop(name, None)
    return subprocess.run(["git", *argv], cwd=cwd, env=environment, check=True,
                          capture_output=True, text=True, **kwargs).stdout.strip()


def archive_bytes(members: dict[str, bytes]) -> bytes:
    import gzip
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if "/ca-artifact-" in name else 0o644
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    # A fixed gzip mtime keeps same-input archives byte-identical across runs,
    # as the release lane's reproducible packages are.
    return gzip.compress(stream.getvalue(), mtime=0)


class ChannelFixture(unittest.TestCase):
    HOST = ""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.remote = self.root / "remote.git"
        git(["init", "--quiet", "--bare", str(self.remote)], cwd=self.root)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "README").write_text("source\n", encoding="utf-8")
        git(["init", "--quiet"], cwd=self.source)
        git(["add", "."], cwd=self.source)
        git(["commit", "--quiet", "-m", "source"], cwd=self.source)
        self.source_commit = git(["rev-parse", "HEAD"], cwd=self.source)
        self.runs = 0

    def package(self, version: str, *, binary: bytes = b"qualified-native-binary",
                extra: dict[str, bytes] | None = None) -> tuple[Path, str]:
        root = self.root / f"packages-{version}-{self.runs}"
        self.runs += 1
        root.mkdir()
        members = dict(self.members(version, binary))
        members.update(extra or {})
        data = archive_bytes(members)
        name = f"codearbiter-{self.PLUGIN}-{version}.tar.gz"
        (root / name).write_bytes(data)
        receipt_members = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                payload = archive.extractfile(member).read()
                receipt_members[member.name] = {
                    "type": "file", "mode": f"{member.mode:04o}", "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "origin": "promotion" if "/helpers/artifacts/" in member.name else "source",
                    "source": member.name}
        receipt = {"format": PACKAGER.ARTIFACT_PACKAGE_FORMAT,
                   "source_commit": self.source_commit,
                   "packages": {self.HOST: {"file": name, "version": version, "size": len(data),
                                            "sha256": hashlib.sha256(data).hexdigest(),
                                            "members": receipt_members}}}
        path = root / "artifact-package-cohort.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return root, hashlib.sha256(path.read_bytes()).hexdigest()

    def work(self) -> Path:
        self.runs += 1
        return self.root / f"work-{self.runs}"

    def remote_ref(self, ref: str) -> str:
        return git(["rev-parse", ref], cwd=self.remote)

    def remote_show(self, ref: str, path: str) -> bytes:
        return git(["show", f"{ref}:{path}"], cwd=self.remote).encode()


class ClaudeChannelTests(ChannelFixture):
    HOST = "claude"
    PLUGIN = "ca"

    def members(self, version, binary):
        catalog = (b'{"name":"codearbiter","owner":{"name":"arbiterForge"},'
                   b'"plugins":[{"name":"ca","source":"./plugins/ca"}]}\n')
        return {
            ".claude-plugin/marketplace.json": catalog,
            "plugins/ca/.claude-plugin/plugin.json": json.dumps(
                {"name": "ca", "version": version}).encode() + b"\n",
            "plugins/ca/hooks/hook.py": b"print('hook')\n",
            "plugins/ca/helpers/artifacts/release.json": b'{"format":"codearbiter.artifact-release/0.1.0"}\n',
            "plugins/ca/helpers/artifacts/ca-artifact-linux-amd64": binary,
        }

    def promote(self, version, **kwargs):
        root, digest = self.package(version, **kwargs)
        return CLAUDE.promote(package_root=root, cohort_sha256=digest,
                              source_commit=self.source_commit,
                              remote_url=str(self.remote), version=version,
                              work=self.work(), push=True)

    def test_channel_carries_the_native_payload_under_the_git_subdir_path(self):
        result = self.promote("2.0.0")
        self.assertEqual(result["marketplace_commit"], self.remote_ref("refs/heads/ca-marketplace"))
        self.assertEqual(result["distribution_commit"], self.remote_ref("refs/tags/ca-dist-v2.0.0"))
        self.assertEqual(self.remote_show("ca-marketplace", "plugins/ca/helpers/artifacts/ca-artifact-linux-amd64"),
                         b"qualified-native-binary")
        manifest = json.loads(self.remote_show("ca-marketplace", "plugins/ca/.claude-plugin/plugin.json"))
        self.assertEqual(manifest["version"], "2.0.0")

    def test_rerun_with_identical_inputs_is_a_no_op(self):
        first = self.promote("2.0.0")
        second = self.promote("2.0.0")
        self.assertEqual(first["marketplace_commit"], second["marketplace_commit"])
        self.assertEqual(second["marketplace_previous_commit"], second["marketplace_commit"])

    def test_same_version_with_different_bytes_is_refused(self):
        self.promote("2.0.0")
        with self.assertRaisesRegex(ValueError, "different bytes"):
            self.promote("2.0.0", binary=b"substituted-binary")

    def test_newer_version_advances_as_a_descendant(self):
        first = self.promote("2.0.0")
        second = self.promote("2.1.0")
        self.assertNotEqual(first["marketplace_commit"], second["marketplace_commit"])
        git(["merge-base", "--is-ancestor", first["marketplace_commit"], second["marketplace_commit"]],
            cwd=self.remote)

    def test_channel_refuses_to_roll_back(self):
        self.promote("2.1.0")
        with self.assertRaisesRegex(ValueError, "roll back"):
            self.promote("2.0.0")

    def test_version_must_match_the_qualified_manifest(self):
        root, digest = self.package("2.0.0")
        with self.assertRaisesRegex(ValueError, "does not match"):
            CLAUDE.promote(package_root=root, cohort_sha256=digest, source_commit=self.source_commit,
                           remote_url=str(self.remote), version="2.0.1", work=self.work(), push=True)

    def test_package_without_native_payload_is_refused(self):
        root = self.root / "bare"
        root.mkdir()
        with self.assertRaisesRegex(ValueError, "omits required"):
            members = self.members("2.0.0", b"x")
            del members["plugins/ca/helpers/artifacts/ca-artifact-linux-amd64"]
            self.members = lambda version, binary: members  # type: ignore[assignment]
            self.promote("2.0.0")


class ClaudeCatalogTests(unittest.TestCase):
    def test_main_catalog_points_ca_at_the_distribution_branch(self):
        catalog = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        entry = [item for item in catalog["plugins"] if item["name"] == "ca"]
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry[0]["source"], PACKAGER.CLAUDE_DISTRIBUTION_SOURCE)

    def test_archive_catalog_is_relative_so_the_archive_installs_locally(self):
        installer = PACKAGER._artifact_installer_module()
        source = (REPO / ".claude-plugin/marketplace.json").read_bytes()
        archived = json.loads(PACKAGER._claude_catalog(source, installer))
        self.assertEqual([item["name"] for item in archived["plugins"]], ["ca"])
        self.assertEqual(archived["plugins"][0]["source"], "./plugins/ca")

    def test_unexpected_ca_source_is_refused(self):
        installer = PACKAGER._artifact_installer_module()
        bad = b'{"name":"codearbiter","plugins":[{"name":"ca","source":{"source":"github","repo":"x/y"}}]}'
        with self.assertRaisesRegex(ValueError, "canonical ca package"):
            PACKAGER._claude_catalog(bad, installer)


class CodexGitChannelTests(ChannelFixture):
    HOST = "codex"
    PLUGIN = "ca-codex"
    CATALOG = (b'{"name":"codearbiter","plugins":[{"name":"ca-codex",'
               b'"source":{"source":"local","path":"./plugins/ca-codex"},'
               b'"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"}}]}\n')

    def setUp(self):
        super().setUp()
        (self.source / ".agents/plugins").mkdir(parents=True)
        (self.source / ".agents/plugins/marketplace.json").write_bytes(self.CATALOG)
        git(["add", "."], cwd=self.source)
        git(["commit", "--quiet", "-m", "catalog"], cwd=self.source)
        self.source_commit = git(["rev-parse", "HEAD"], cwd=self.source)

    def members(self, version, binary):
        return {
            ".agents/plugins/marketplace.json": self.CATALOG,
            "plugins/ca-codex/.codex-plugin/plugin.json": json.dumps(
                {"name": "ca-codex", "version": version}).encode() + b"\n",
            "plugins/ca-codex/helpers/artifacts/release.json": b'{"format":"codearbiter.artifact-release/0.1.0"}\n',
            "plugins/ca-codex/helpers/artifacts/ca-artifact-linux-amd64": binary,
        }

    def promote(self, version, *, advance: bool):
        root, digest = self.package(version)
        return CODEX.promote(package_root=root, cohort_sha256=digest, source_repo=self.source,
                             source_commit=self.source_commit, remote_url=str(self.remote),
                             catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                             version=version, work=self.work(), push=True,
                             advance_channel=advance)

    def test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag(self):
        self.promote("0.20.0", advance=False)
        result = self.promote("0.20.0", advance=True)
        catalog = json.loads(self.remote_show("ca-codex-marketplace", ".agents/plugins/marketplace.json"))
        source = catalog["plugins"][0]["source"]
        self.assertEqual(source["source"], "git-subdir")
        self.assertEqual(source["ref"], "refs/tags/ca-codex-dist-v0.20.0")
        self.assertEqual(source["sha"], result["distribution_commit"])
        self.assertEqual(source["sha"], self.remote_ref("refs/tags/ca-codex-dist-v0.20.0"))
        self.assertEqual(CODEX._catalog_version(json.dumps(catalog).encode()), "0.20.0")

    def test_git_mode_needs_no_npm_package(self):
        result = self.promote("0.20.0", advance=False)
        self.assertEqual(result["npm_file"], "")


if __name__ == "__main__":
    unittest.main()
