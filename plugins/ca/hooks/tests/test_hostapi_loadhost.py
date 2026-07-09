"""Tests for hostapi.load_host() fail-closed semantics (tribunal #255).

A `_host.py` that is PRESENT but fails to load must NOT silently degrade to the
Claude-default Host() — on a Codex install that un-guards every apply_patch
write (architecture-004 / typesafety-001). load_host() must instead return a
FailClosedHost (writes blocked) and leave a breadcrumb. An ABSENT `_host.py`
(the bare-core case) still returns the Claude default.

stdlib unittest only; no subprocess.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import hostapi


def _dir_with_host(body):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "_host.py"), "w", encoding="utf-8") as f:
        f.write(body)
    return d


class LoadHostFailClosedTests(unittest.TestCase):
    def test_absent_host_returns_claude_default(self):
        d = tempfile.mkdtemp()  # no _host.py written
        host = hostapi.load_host(d)
        self.assertIsInstance(host, hostapi.Host)
        self.assertNotIsInstance(host, hostapi.FailClosedHost)
        self.assertEqual(host.name, "claude")

    def test_valid_host_is_returned(self):
        d = _dir_with_host(
            "import hostapi\n"
            "class _Probe(hostapi.Host):\n"
            "    name = 'probe'\n"
            "HOST = _Probe()\n"
        )
        host = hostapi.load_host(d)
        self.assertEqual(host.name, "probe")
        self.assertNotIsInstance(host, hostapi.FailClosedHost)

    def test_broken_host_fails_closed_with_opaque_op(self):
        d = _dir_with_host("raise RuntimeError('boom')\n")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            host = hostapi.load_host(d)
        self.assertIsInstance(host, hostapi.FailClosedHost)
        # The write gate must see an opaque op regardless of payload shape, so
        # pre-write.py blocks (H-21) instead of assuming a host's semantics.
        ops = host.iter_file_ops({
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Begin Patch\n*** Add File: x\n+y\n*** End Patch\n"},
        })
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["kind"], "opaque")
        # And a breadcrumb was emitted — a broken host is never silent.
        self.assertIn("_host.py is present but failed to load", buf.getvalue())

    def test_missing_HOST_symbol_fails_closed(self):
        d = _dir_with_host("X = 1\n")  # loads fine but declares no HOST
        with contextlib.redirect_stderr(io.StringIO()):
            host = hostapi.load_host(d)
        self.assertIsInstance(host, hostapi.FailClosedHost)

    def test_failclosed_capabilities_are_conservative(self):
        h = hostapi.FailClosedHost()
        self.assertFalse(h.has_statusline)
        self.assertFalse(h.has_read_tool)
        self.assertFalse(h.has_prunable_transcript)
        self.assertEqual(h.name, "unknown")


if __name__ == "__main__":
    unittest.main()
