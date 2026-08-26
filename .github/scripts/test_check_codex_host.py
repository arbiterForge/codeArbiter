#!/usr/bin/env python3
"""Regression tests for credential-free Codex hook-install validation."""
from __future__ import annotations

import importlib.util
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
    def _results_for(self, command: str, hook_setup=None):
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

            def fake_run(args, _home):
                if args[-1] == "list":
                    text = f"ca-codex@codearbiter installed enabled {version}\n"
                else:
                    text = ""
                return subprocess.CompletedProcess(args, 0, stdout=text, stderr="")

            with mock.patch.object(CHECKER, "_run", side_effect=fake_run):
                return CHECKER.check_install(home)

    @staticmethod
    def _hook_result(results):
        return next(item for item in results if item["code"] == "CODEX-HOST-HOOK-SCRIPTS")

    @staticmethod
    def _agent_route_result(results):
        return next(item for item in results if item["code"] == "CODEX-HOST-AGENT-ROUTES")

    def test_missing_installed_agent_charters_fail_the_real_host_check(self):
        # The fixture installs hooks only.  A host check that looked at source
        # paths, or only at the manifest, would incorrectly accept it.
        result = self._agent_route_result(self._results_for(
            'python3 "${PLUGIN_ROOT}/hooks/example.py"'
        ))
        self.assertEqual(result["status"], "fail")

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
