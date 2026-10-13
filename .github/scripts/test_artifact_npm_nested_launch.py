#!/usr/bin/env python3
# codeArbiter — reject unbound Windows npm delegation before verification launch.
"""Focused native-launch qualification regressions; no npm dependencies installed."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))
adapter = importlib.import_module("_artifactauthoritylib")


@unittest.skipUnless(os.name == "nt", "Windows npm.cmd redirection contract")
class WindowsNestedNpmLaunchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-npm-nested-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cwd = self.root / "project"
        self.cwd.mkdir()
        self.installation = self.root / "node"
        self.bin = self.installation / "node_modules" / "npm" / "bin"
        self.bin.mkdir(parents=True)
        self.executable = self.installation / "npm.cmd"
        self.helper = self.bin / "npm-prefix.js"
        for path in (self.executable, self.installation / "node.exe", self.bin / "npm-cli.js", self.helper):
            path.write_text("fixture bytes; never executed\n", encoding="utf-8")
        self.prefix = str(self.installation).encode() + b"\n"
        self.config = b"script-shell=null\nnode-options=null\n"
        self.failure = None
        self.calls = []

    def _probe(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.failure:
            raise self.failure
        output = self.prefix if Path(argv[1]) == self.helper else self.config
        return subprocess.CompletedProcess(argv, 0, output, b"")

    def _qualify(self):
        with mock.patch.object(adapter, "_resolve_executable", return_value=self.executable), \
                mock.patch.object(adapter, "_run_contained", side_effect=self._probe):
            return adapter._validate_nested_npm_launch(self.executable, self.cwd)

    def test_same_installation_binds_prefix_helper(self):
        self.assertEqual(self._qualify(), [adapter._launch_file(self.helper, "npm-prefix")])
        self.assertEqual(len(self.calls), 2)
        for argv, options in self.calls:
            self.assertEqual(argv[0], str(self.installation / "node.exe"))
            self.assertEqual(options["cwd"], str(self.cwd))
            self.assertLessEqual(options["timeout_seconds"], 15)

    def test_existing_global_cli_redirect_is_rejected(self):
        redirected = self.root / "global" / "node_modules" / "npm" / "bin" / "npm-cli.js"
        redirected.parent.mkdir(parents=True)
        redirected.write_text("different npm CLI\n", encoding="utf-8")
        self.prefix = str(self.root / "global").encode() + b"\n"
        with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*redirect"):
            self._qualify()

    def test_custom_script_shell_is_rejected(self):
        self.config = b"script-shell=custom-shell.exe\nnode-options=null\n"
        with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*shell"):
            self._qualify()

    def test_configured_node_options_are_rejected(self):
        self.config = b"script-shell=null\nnode-options=--require injected.js\n"
        with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*node-options"):
            self._qualify()

    def test_missing_prefix_helper_is_rejected(self):
        self.helper.unlink()
        with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*prefix"):
            self._qualify()

    def test_prefix_helper_drift_during_qualification_is_rejected(self):
        original_probe = self._probe
        def mutate_helper(argv, **kwargs):
            result = original_probe(argv, **kwargs)
            if Path(argv[1]) == self.helper:
                self.helper.write_text("changed helper bytes\n", encoding="utf-8")
            return result
        with mock.patch.object(adapter, "_resolve_executable", return_value=self.executable), \
                mock.patch.object(adapter, "_run_contained", side_effect=mutate_helper), \
                self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*changed"):
            adapter._validate_nested_npm_launch(self.executable, self.cwd)

    def test_unavailable_config_probe_is_rejected(self):
        self.failure = subprocess.TimeoutExpired("fixture-probe", 15)
        with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE.*qualification"):
            self._qualify()

    def test_malformed_or_oversized_prefix_result_is_rejected(self):
        for value in (b"relative\n", b"C:\\first\nC:\\second\n", b"\xff", b"x" * 32769):
            with self.subTest(value_kind=(len(value), value[:8])):
                self.prefix = value
                with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_EXECUTABLE"):
                    self._qualify()


class NestedNpmPrefixContextTest(unittest.TestCase):
    def test_nested_delegation_with_non_dot_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ca-npm-prefix-context-") as temporary:
            root = Path(temporary).resolve()
            site = root / "site"
            client = site / "client"
            client.mkdir(parents=True)
            (site / "package.json").write_text(json.dumps({
                "workspaces": ["client"],
                "scripts": {"test:client": "npm --workspace @fixture/client run test"},
            }), encoding="utf-8")
            (client / "package.json").write_text(json.dumps({
                "name": "@fixture/client", "scripts": {"test": "vitest run --reporter=verbose"},
            }), encoding="utf-8")
            with self.assertRaisesRegex(adapter.AuthorityError, "UNSUPPORTED_COLLECTOR.*prefix"):
                adapter._npm_runner(["npm", "--prefix", "site", "run", "test:client"], root)


if __name__ == "__main__":
    unittest.main()
