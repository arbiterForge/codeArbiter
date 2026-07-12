"""Tests for the host runtime-vocabulary seam (codex-support M3, DECISION-0013).

Every RUNTIME-emitted command reference (startup briefing, block reasons,
doctor lines, the init scaffold's stub text) flows through Host.cmd_ref so the
same core emits /ca:<name> under Claude Code and $ca-<name> under Codex — the
runtime twin of build-surface.py's {{CMD:name}} token. These tests pin both
hosts' spellings and the briefing noun, so a drift between the markdown
renderer and the runtime seam is a test failure, not a live surprise.

stdlib unittest only; no subprocess.
"""
import os
import sys
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import hostapi


class ClaudeCmdRefTest(unittest.TestCase):
    def test_claude_default_spelling(self):
        self.assertEqual(hostapi.Host().cmd_ref("commit"), "/ca:commit")

    def test_claude_command_noun(self):
        self.assertEqual(hostapi.Host().command_noun, "slash command")

    def test_fail_closed_host_inherits_claude_spelling(self):
        # FailClosedHost blocks writes but still has to render SOME pointer;
        # the Claude default is the documented conservative choice.
        self.assertEqual(hostapi.FailClosedHost().cmd_ref("doctor"), "/ca:doctor")


class CodexCmdRefTest(unittest.TestCase):
    """Loads the REAL ca-codex _host.py so the shipped override is what's
    tested, mirroring how the codex adapter suite resolves it."""

    @classmethod
    def setUpClass(cls):
        codex_hooks = os.path.abspath(os.path.join(
            _HOOKS_DIR, "..", "..", "ca-codex", "hooks"))
        cls.host = hostapi.load_host(codex_hooks)

    def test_codex_spelling(self):
        self.assertEqual(self.host.name, "codex")
        self.assertEqual(self.host.cmd_ref("init"), "$ca-init")

    def test_codex_command_noun(self):
        self.assertEqual(self.host.command_noun, "command")

    def test_spelling_agrees_with_build_surface(self):
        # The runtime seam and the markdown renderer must produce the same
        # per-host spellings ({{CMD:x}} <-> cmd_ref) or rendered docs and
        # live briefings drift apart.
        import importlib.util
        tool = os.path.abspath(os.path.join(
            _HOOKS_DIR, "..", "..", "..", "tools", "build-surface.py"))
        spec = importlib.util.spec_from_file_location("build_surface", tool)
        B = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(B)
        self.assertEqual(B.CMD_FORM["claude"].format(name="x"),
                         hostapi.Host().cmd_ref("x"))
        self.assertEqual(B.CMD_FORM["codex"].format(name="x"),
                         self.host.cmd_ref("x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
