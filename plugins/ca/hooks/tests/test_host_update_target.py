"""Tests for host-owned update release targets and native remediation commands."""
import os
import sys
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import hostapi


class HostUpdateTargetTests(unittest.TestCase):
    def _load_sibling(self, name):
        hooks = os.path.abspath(os.path.join(
            _HOOKS_DIR, "..", "..", name, "hooks"))
        return hostapi.load_host(hooks)

    def test_claude_descriptor_owns_its_release_series_and_command(self):
        host = hostapi.Host()
        self.assertEqual(host.update_target, "ca")
        self.assertEqual(host.update_tag_prefix, "v")
        self.assertEqual(host.update_command,
                         "/plugin marketplace update codearbiter")

    def test_codex_descriptor_owns_its_release_series_and_command(self):
        host = self._load_sibling("ca-codex")
        self.assertEqual(host.update_target, "ca-codex")
        self.assertEqual(host.update_tag_prefix, "ca-codex-v")
        self.assertEqual(host.update_command,
                         "codex plugin add ca-codex@codearbiter")

    def test_pi_descriptor_owns_its_release_series_and_command(self):
        host = self._load_sibling("ca-pi")
        self.assertEqual(host.update_target, "ca-pi")
        self.assertEqual(host.update_tag_prefix, "ca-pi-v")
        self.assertEqual(host.update_command,
                         "pi update npm:@arbiterforge/ca-pi")

    def test_unknown_host_disables_update_notices(self):
        host = hostapi.FailClosedHost()
        self.assertIsNone(host.update_target)
        self.assertIsNone(host.update_tag_prefix)
        self.assertIsNone(host.update_command)


if __name__ == "__main__":
    unittest.main()
