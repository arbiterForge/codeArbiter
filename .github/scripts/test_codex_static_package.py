#!/usr/bin/env python3
"""Adversarial contracts for the trusted static ca-codex package checker."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / ".github" / "scripts" / "check_codex_static_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_static_package", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StaticPackageContractTest(unittest.TestCase):
    def setUp(self):
        self.checker = load_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "ca-codex"
        shutil.copytree(REPO_ROOT / "plugins" / "ca-codex", self.package)

    def assert_rejects(self, expected: str):
        with self.assertRaisesRegex(ValueError, expected):
            self.checker.candidate_static_contract(self.package)

    def hooks(self):
        path = self.package / "hooks" / "hooks.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def write_hooks(self, value):
        path = self.package / "hooks" / "hooks.json"
        path.write_text(json.dumps(value), encoding="utf-8", newline="\n")

    def test_accepts_the_exact_shipped_package(self):
        result = self.checker.candidate_static_contract(self.package)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["plugin_version"], "0.7.5")

    def test_rejects_missing_or_ambiguous_manifest_identity(self):
        manifest_path = self.package / ".codex-plugin" / "plugin.json"
        cases = {
            "missing": None,
            "wrong name": '{"name":"other","version":"0.7.5"}\n',
            "non semver": '{"name":"ca-codex","version":"0_bad"}\n',
            "duplicate": '{"name":"ca-codex","name":"other","version":"0.7.5"}\n',
        }
        original = manifest_path.read_bytes()
        for label, content in cases.items():
            with self.subTest(label=label):
                if content is None:
                    manifest_path.unlink()
                else:
                    manifest_path.write_text(content, encoding="utf-8", newline="\n")
                self.assert_rejects("manifest|duplicate")
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_bytes(original)

    def test_rejects_missing_duplicate_malformed_or_misnamed_front_matter(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        original = skill.read_text(encoding="utf-8")
        cases = {
            "missing": original.split("---\n", 2)[-1],
            "duplicate": original.replace(
                "name: ca-add-dep\n", "name: ca-add-dep\nname: ca-add-dep\n", 1
            ),
            "malformed quote": original.replace("name: ca-add-dep", 'name: "ca-add-dep', 1),
            "wrong path name": original.replace("name: ca-add-dep", "name: other", 1),
        }
        for label, content in cases.items():
            with self.subTest(label=label):
                skill.write_text(content, encoding="utf-8", newline="\n")
                self.assert_rejects("front matter")
                skill.write_text(original, encoding="utf-8", newline="\n")

    def test_rejects_agent_without_classification(self):
        agent = self.package / "agents" / "dependency-reviewer.md"
        agent.write_text(
            agent.read_text(encoding="utf-8").replace("classification: reviewer\n", "", 1),
            encoding="utf-8", newline="\n",
        )
        self.assert_rejects("classification")

    def test_rejects_misnamed_routine_and_agent_front_matter(self):
        cases = (
            (
                self.package / "routines" / "commit-gate" / "SKILL.md",
                "name: commit-gate",
                "name: other",
            ),
            (
                self.package / "agents" / "dependency-reviewer.md",
                "name: dependency-reviewer",
                "name: other",
            ),
        )
        for path, expected, replacement in cases:
            with self.subTest(path=path.relative_to(self.package)):
                original = path.read_text(encoding="utf-8")
                path.write_text(
                    original.replace(expected, replacement, 1),
                    encoding="utf-8", newline="\n",
                )
                self.assert_rejects("front matter name")
                path.write_text(original, encoding="utf-8", newline="\n")

    def test_static_wrapper_rejects_missing_and_escaping_resource_links(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        original = skill.read_text(encoding="utf-8")
        for target in ("missing-resource.md", "../../../outside.md"):
            with self.subTest(target=target):
                skill.write_text(
                    original + f"\n[contract]({target})\n",
                    encoding="utf-8", newline="\n",
                )
                self.assert_rejects("escaped or unresolved")
                skill.write_text(original, encoding="utf-8", newline="\n")

    def test_rejects_hook_command_injection_and_non_native_roots(self):
        path, hooks = self.hooks()
        original = path.read_text(encoding="utf-8")
        cases = (
            original.replace(
                'python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\"',
                'python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\" && external', 1,
            ),
            original.replace("${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}", 1),
        )
        for content in cases:
            path.write_text(content, encoding="utf-8", newline="\n")
            self.assert_rejects("hook command")
            path.write_text(original, encoding="utf-8", newline="\n")

    def test_rejects_missing_hook_target(self):
        (self.package / "hooks" / "session-start.py").unlink()
        self.assert_rejects("hook target")

    def test_rejects_duplicate_or_unknown_hook_schema(self):
        path, hooks = self.hooks()
        original = path.read_text(encoding="utf-8")
        hooks["unexpected"] = True
        self.write_hooks(hooks)
        self.assert_rejects("schema")
        path.write_text(
            original.replace('{\n  "hooks":', '{\n  "hooks": {},\n  "hooks":', 1),
            encoding="utf-8", newline="\n",
        )
        self.assert_rejects("duplicate")

    def test_rejects_removed_security_events(self):
        for event in ("PreToolUse", "PostToolUse"):
            with self.subTest(event=event):
                _path, hooks = self.hooks()
                del hooks["hooks"][event]
                self.write_hooks(hooks)
                self.assert_rejects("hook inventory")
                shutil.copy2(
                    REPO_ROOT / "plugins" / "ca-codex" / "hooks" / "hooks.json",
                    self.package / "hooks" / "hooks.json",
                )

    def test_rejects_changed_matcher_or_rerouted_security_hook(self):
        _path, hooks = self.hooks()
        hooks["hooks"]["PreToolUse"][0]["matcher"] = "NeverMatches"
        self.write_hooks(hooks)
        self.assert_rejects("hook inventory")

        shutil.copy2(
            REPO_ROOT / "plugins" / "ca-codex" / "hooks" / "hooks.json",
            self.package / "hooks" / "hooks.json",
        )
        _path, hooks = self.hooks()
        entry = hooks["hooks"]["PostToolUse"][0]["hooks"][0]
        entry["command"] = 'python3 "${PLUGIN_ROOT}/hooks/session-start.py"'
        entry["commandWindows"] = 'python "${PLUGIN_ROOT}/hooks/session-start.py"'
        self.write_hooks(hooks)
        self.assert_rejects("hook inventory")


class DirectoryBoundContractTest(unittest.TestCase):
    def setUp(self):
        self.checker = load_module()._load_resource_checker()
        self.limits = {
            "max_archive_bytes": 8,
            "max_entries": 2,
            "max_entry_uncompressed_bytes": 2,
            "max_total_uncompressed_bytes": 3,
            "max_compression_ratio": 100,
        }

    def assert_bounded(self, contents=(), directories=0):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            for index, content in enumerate(contents):
                (package / f"file-{index}.md").write_bytes(content)
            for index in range(directories):
                (package / f"empty-{index}").mkdir()
            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=self.limits
            ), self.assertRaises(ValueError):
                self.checker._candidate_package_files(package)

    def test_rejects_entry_count_per_file_and_total_bytes(self):
        self.assert_bounded(contents=(b"a", b"b", b"c"))
        self.assert_bounded(contents=(b"abc",))
        self.assert_bounded(contents=(b"ab", b"cd"))

    def test_rejects_empty_directories_over_entry_limit(self):
        self.assert_bounded(directories=3)

    def test_stops_scanning_at_the_entry_limit_before_sorting(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            for index in range(4):
                (package / f"file-{index}.md").write_bytes(b"a")

            original_scandir = self.checker.os.scandir
            observed = {"entries": 0}

            class CountingScandir:
                def __init__(inner_self, directory):
                    inner_self._scan = original_scandir(directory)

                def __enter__(inner_self):
                    inner_self._scan.__enter__()
                    return inner_self

                def __exit__(inner_self, *arguments):
                    return inner_self._scan.__exit__(*arguments)

                def __iter__(inner_self):
                    return inner_self

                def __next__(inner_self):
                    observed["entries"] += 1
                    if observed["entries"] > self.limits["max_entries"] + 1:
                        raise AssertionError("directory traversal read beyond the rejection bound")
                    return next(inner_self._scan)

            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=self.limits
            ), mock.patch.object(self.checker.os, "scandir", CountingScandir), self.assertRaisesRegex(
                ValueError, "entry-count limit"
            ):
                self.checker._candidate_package_files(package)
            self.assertEqual(observed["entries"], self.limits["max_entries"] + 1)

    def test_rejects_file_growth_using_only_bounded_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            candidate = package / "growing.md"
            candidate.write_bytes(b"a")
            original_open = Path.open
            initial = candidate.stat()

            class GrowingStream:
                def __init__(inner_self):
                    inner_self._chunks = iter((b"ab", b"c"))

                def __enter__(inner_self):
                    return inner_self

                def __exit__(inner_self, *_arguments):
                    return False

                def fileno(inner_self):
                    return 123

                def read(inner_self, size=-1):
                    if size < 0 or size > self.limits["max_entry_uncompressed_bytes"] + 1:
                        raise AssertionError("candidate file was read without a hard byte bound")
                    return next(inner_self._chunks, b"")

            def controlled_open(path, *arguments, **keywords):
                if path == candidate:
                    return GrowingStream()
                return original_open(path, *arguments, **keywords)

            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=self.limits
            ), mock.patch.object(Path, "open", controlled_open), mock.patch.object(
                self.checker.os, "fstat", return_value=initial
            ), self.assertRaisesRegex(
                ValueError, "changed while being read"
            ):
                self.checker._candidate_package_files(package)

    def test_rechecks_the_per_entry_limit_on_the_opened_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            candidate = package / "growing.md"
            candidate.write_bytes(b"a")
            original_validate = self.checker._validate_candidate_paths

            def grow_after_enumeration(paths):
                result = original_validate(paths)
                candidate.write_bytes(b"abc")
                return result

            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=self.limits
            ), mock.patch.object(
                self.checker, "_validate_candidate_paths", grow_after_enumeration
            ), self.assertRaisesRegex(ValueError, "entry exceeds the size limit"):
                self.checker._candidate_package_files(package)

    def test_rejects_an_opened_file_with_a_different_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            candidate = package / "replaced.md"
            candidate.write_bytes(b"a")
            initial = candidate.stat()
            replacement = SimpleNamespace(
                st_mode=initial.st_mode,
                st_dev=initial.st_dev,
                st_ino=initial.st_ino + 1,
                st_size=initial.st_size,
            )

            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=self.limits
            ), mock.patch.object(
                self.checker.os, "fstat", return_value=replacement
            ), self.assertRaisesRegex(ValueError, "changed while being read"):
                self.checker._candidate_package_files(package)


if __name__ == "__main__":
    unittest.main()
