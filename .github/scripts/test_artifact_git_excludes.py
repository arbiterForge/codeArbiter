#!/usr/bin/env python3
"""Real-Git regression for the completion bridge's selected ignore policy."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
spec = importlib.util.spec_from_file_location("artifact_excludes_bridge", REPO / "core/pysrc/_artifactlib.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class CompletionGitExcludesTest(unittest.TestCase):
    def _assert_inventory(self, explicit):
        git = shutil.which("git")
        if git is None:
            self.skipTest("real Git is required")
        git = str(Path(git).resolve())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "repository"
            root.mkdir()
            config_home = base / "user-config"
            default_excludes = config_home / "git" / "ignore"
            default_excludes.parent.mkdir(parents=True)
            default_excludes.write_text("different-default.txt\n", encoding="utf-8")
            excludes = base / "explicit-ignore" if explicit else default_excludes
            excludes.write_text("ignored-by-host.txt\n", encoding="utf-8")
            config = base / "host.gitconfig"
            config.write_text('[core]\n\texcludesFile = "' + excludes.as_posix() + '"\n' if explicit else "", encoding="utf-8")
            environment = dict(os.environ, CODEARBITER_GIT_EXECUTABLE=git,
                               GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM="1",
                               XDG_CONFIG_HOME=str(config_home),
                               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="alias.unrelated",
                               GIT_CONFIG_VALUE_0="!echo do-not-forward", USER_TOKEN="secret-fixture")
            if explicit:
                override_ignore = base / "override-ignore"
                override_ignore.write_text("producer-visible.txt\n", encoding="utf-8")
                override_config = base / "override.gitconfig"
                override_config.write_text('[core]\n\texcludesFile = "' + override_ignore.as_posix() + '"\n', encoding="utf-8")
                environment["GIT_CONFIG"] = str(override_config)
            subprocess.run([git, "init", "--quiet", str(root)], env=environment, check=True, timeout=15)
            (root / "ignored-by-host.txt").write_text("ordinary ignored local output", encoding="utf-8")
            if explicit:
                (root / "producer-visible.txt").write_text("must remain in inventory", encoding="utf-8")
            command = [git, "-C", str(root), "status", "--porcelain=v2", "-z", "--untracked-files=all"]
            expected = subprocess.run(command, env=environment, capture_output=True, check=True, timeout=15).stdout
            self.assertEqual(expected, b"? producer-visible.txt\0" if explicit else b"")
            with mock.patch.dict(os.environ, environment, clear=True):
                native = bridge._native_child_environment(["pinned-engine", "evidence-context", "--root", str(root), "--request", "-"])
            actual = subprocess.run(command, env=native, capture_output=True, check=True, timeout=15).stdout
            self.assertEqual(actual, expected, "native inventory must retain the producer's effective global ignore policy")
            self.assertEqual(set(native), {"CODEARBITER_GIT_EXECUTABLE", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"})
            self.assertEqual(native["GIT_CONFIG_COUNT"], "1")
            self.assertEqual(native["GIT_CONFIG_KEY_0"], "core.excludesFile")
            self.assertEqual(Path(native["GIT_CONFIG_VALUE_0"]).resolve(), excludes)

    def test_native_inventory_preserves_default_user_ignore(self):
        self._assert_inventory(explicit=False)

    def test_native_inventory_preserves_explicit_host_excludes(self):
        self._assert_inventory(explicit=True)


if __name__ == "__main__":
    unittest.main()
