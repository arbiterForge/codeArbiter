"""Statusline contract for context-relevant prune savings."""

import json
import os
import re
import sys
import tempfile
import time
import unittest


_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

import _segmentslib as S  # noqa: E402
from _helpers import redirect_home, restore_home  # noqa: E402


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class PruneStatusMetricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_home = redirect_home(self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, ".codearbiter"))

    def tearDown(self):
        restore_home(self.saved_home)
        self.tmp.cleanup()

    def _render(self, record):
        path = os.path.join(self.tmp.name, ".codearbiter", "prune-state.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"session": record}, handle)
        return ANSI_RE.sub("", S.seg_prune({}, "session") or "")

    def test_new_records_render_context_tokens_not_file_percentage(self):
        rendered = self._render({
            "file_bytes_freed": 800_000,
            "file_pct": 40.0,
            "context_bytes_freed": 8_000,
            "context_est_tokens_freed": 2_000,
            "last_run_ts": time.time(),
        })
        self.assertIn("ctx:2.0K", rendered)
        self.assertNotIn("40%", rendered)

    def test_sidecar_only_record_makes_zero_context_savings_visible(self):
        rendered = self._render({
            "file_bytes_freed": 800_000,
            "file_pct": 40.0,
            "context_bytes_freed": 0,
            "context_est_tokens_freed": 0,
            "last_run_ts": time.time(),
        })
        self.assertIn("ctx:0", rendered)


if __name__ == "__main__":
    unittest.main()
