#!/usr/bin/env python3
"""Regression tests for credential-free Codex hook-install validation."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_codex_host_under_test", HERE / "check_codex_host.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CHECKER)


class HookScriptContainmentTest(unittest.TestCase):
    def _results_for(self, command: str, hook_setup=None, *, require_artifact=False,
                     qualified_members=False, receipt_mutator=None):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            version = CHECKER.expected_version()
            root = home / "plugins/cache/test/ca-codex" / version
            hooks = root / "hooks"
            hooks.mkdir(parents=True)
            config = {
                "hooks": {"SessionStart": [{"hooks": [{"command": command}]}]}
            }
            (hooks / "hooks.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            if hook_setup is not None:
                hook_setup(root)
            metadata = None
            if qualified_members:
                members = {}
                for path in root.rglob("*"):
                    if path.is_file():
                        data = path.read_bytes()
                        members[f"package/{path.relative_to(root).as_posix()}"] = {
                            "size": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                if receipt_mutator is not None:
                    receipt_mutator(members)
                metadata = home / "qualified-npm.json"
                metadata.write_text(
                    json.dumps({"members": members}), encoding="utf-8"
                )

            def fake_run(args, _home):
                if args[-1] == "list":
                    text = f"ca-codex@codearbiter installed enabled {version}\n"
                else:
                    text = ""
                return subprocess.CompletedProcess(args, 0, stdout=text, stderr="")

            with mock.patch.object(CHECKER, "_run", side_effect=fake_run):
                return CHECKER.check_install(
                    home, require_artifact_capability=require_artifact,
                    qualified_npm_metadata=metadata,
                )

    @staticmethod
    def _hook_result(results):
        return next(item for item in results if item["code"] == "CODEX-HOST-HOOK-SCRIPTS")

    @staticmethod
    def _agent_route_result(results):
        return next(item for item in results if item["code"] == "CODEX-HOST-AGENT-ROUTES")

    @staticmethod
    def _artifact_result(results):
        return next(item for item in results if item["code"] == "CODEX-HOST-ARTIFACT-CAPABILITY")

    def test_missing_installed_agent_charters_fail_the_real_host_check(self):
        # The fixture installs hooks only.  A host check that looked at source
        # paths, or only at the manifest, would incorrectly accept it.
        result = self._agent_route_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"'
        ))
        self.assertEqual(result["status"], "fail")

    def test_missing_installed_artifact_engine_fails_the_real_host_check(self):
        # A normal marketplace install can copy every declared hook and still
        # omit the native engine required for structured artifact operations.
        results = self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"',
            require_artifact=True,
        )
        capability = next(
            (item for item in results
             if item["code"] == "CODEX-HOST-ARTIFACT-CAPABILITY"),
            None,
        )
        self.assertIsNotNone(
            capability, "real-host install never checked the artifact engine"
        )
        self.assertEqual(capability["status"], "fail")

    def test_valid_installed_artifact_engine_passes_capabilities(self):
        def write_bridge(root):
            (root / "hooks/_artifactlib.py").write_text(
                "def helper_installation(_path): return object()\n"
                "class ArtifactClient:\n"
                "    def __init__(self, _home, _install): pass\n"
                "    def call(self, _operation):\n"
                "        return {'repository_operations_available': True, "
                "'host_default_enabled': True, 'runtime_downloads': False}\n",
                encoding="utf-8",
            )

        result = self._artifact_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"',
            write_bridge, require_artifact=True,
        ))
        self.assertEqual(result["status"], "pass")

    def test_malformed_installed_capabilities_fail_cleanly(self):
        def write_bridge(root):
            (root / "hooks/_artifactlib.py").write_text(
                "def helper_installation(_path): return object()\n"
                "class ArtifactClient:\n"
                "    def __init__(self, _home, _install): pass\n"
                "    def call(self, _operation): return []\n",
                encoding="utf-8",
            )

        result = self._artifact_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"',
            write_bridge, require_artifact=True,
        ))
        self.assertEqual(result["status"], "fail")

    def test_qualified_npm_member_receipt_matches_installed_cache_exactly(self):
        results = self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"', qualified_members=True
        )
        result = next(
            item for item in results if item["code"] == "CODEX-HOST-PACKAGE-MEMBERS"
        )
        self.assertEqual(result["status"], "pass")

    def test_qualified_npm_member_receipt_rejects_dropped_member(self):
        def add_missing(members):
            members["package/helpers/artifacts/missing"] = {
                "size": 1, "sha256": hashlib.sha256(b"x").hexdigest(),
            }

        results = self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"',
            qualified_members=True, receipt_mutator=add_missing,
        )
        result = next(
            item for item in results if item["code"] == "CODEX-HOST-PACKAGE-MEMBERS"
        )
        self.assertEqual(result["status"], "fail")

    def test_qualified_npm_member_receipt_rejects_same_size_substitution(self):
        def substitute_digest(members):
            receipt = members["package/hooks/hooks.json"]
            receipt["sha256"] = hashlib.sha256(
                b"x" * receipt["size"]
            ).hexdigest()

        results = self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"',
            qualified_members=True, receipt_mutator=substitute_digest,
        )
        result = next(
            item for item in results if item["code"] == "CODEX-HOST-PACKAGE-MEMBERS"
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("installed member bytes drifted", result["detail"])

    def test_qualified_npm_member_receipt_rejects_unreadable_member_cleanly(self):
        original_read_bytes = Path.read_bytes

        def fail_installed_member(path):
            if path.name == "hooks.json":
                raise OSError("simulated read failure")
            return original_read_bytes(path)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "plugin"
            hooks = root / "hooks"
            hooks.mkdir(parents=True)
            installed = hooks / "hooks.json"
            installed.write_bytes(b"{}")
            metadata = Path(raw) / "qualified-npm.json"
            metadata.write_text(json.dumps({"members": {
                "package/hooks/hooks.json": {
                    "size": 2,
                    "sha256": hashlib.sha256(b"{}").hexdigest(),
                }
            }}), encoding="utf-8")
            with mock.patch.object(Path, "read_bytes", fail_installed_member):
                errors = CHECKER._installed_member_errors(root, metadata)

        self.assertEqual(len(errors), 1)
        self.assertIn("installed member is unreadable", errors[0])

    def test_source_development_install_does_not_claim_qualified_artifact_capability(self):
        results = self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"'
        )
        self.assertFalse(any(
            item["code"] == "CODEX-HOST-ARTIFACT-CAPABILITY" for item in results
        ))

    def test_traversal_hook_target_is_rejected_even_when_outside_file_exists(self):
        def write_outside(root):
            outside = root.parent / "outside.py"
            outside.write_text("print('outside')\n", encoding="utf-8")

        result = self._hook_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/../outside.py"', write_outside
        ))
        self.assertEqual(result["status"], "fail")

    def test_symlink_hook_target_is_rejected_when_it_resolves_outside_plugin(self):
        def link_outside(root):
            outside = root.parent / "outside.py"
            outside.write_text("print('outside')\n", encoding="utf-8")
            try:
                (root / "hooks/linked.py").symlink_to(outside)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink fixture unavailable: {error}")

        result = self._hook_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/linked.py"', link_outside
        ))
        self.assertEqual(result["status"], "fail")


if __name__ == "__main__":
    unittest.main()
