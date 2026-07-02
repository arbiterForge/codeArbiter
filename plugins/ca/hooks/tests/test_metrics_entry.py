import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

# Ensure hooks/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics  # noqa: E402 — the thin entry hook for /ca:metrics (#179)


class TestMetricsEntry(unittest.TestCase):
    """metrics.py: thin entry hook wrapping _metricslib.compute. Proves the
    serialization/argv-parsing glue that formerly lived as inline `python -c`
    prose in commands/metrics.md is now import-covered."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Not a git repo: commit_timeline() degrades to an empty timeline,
        # so compute() runs its full degrade-safe path with no git dependency.
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = metrics.main(argv)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue().strip())

    def test_prints_valid_json_with_fixed_keys(self):
        result = self._run(["--root", self.root])
        self.assertEqual(
            set(result.keys()),
            {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
        )

    def test_default_window_matches_direct_compute_call(self):
        import _metricslib

        expected = _metricslib.compute(self.root)
        result = self._run(["--root", self.root])
        self.assertEqual(result, expected)

    def test_custom_window_is_threaded_through(self):
        import _metricslib

        expected = _metricslib.compute(self.root, window_size=5)
        result = self._run(["--root", self.root, "--window", "5"])
        self.assertEqual(result, expected)

    def test_degrades_gracefully_on_nonexistent_root(self):
        # Never raise — a missing/garbage root must still print the fixed
        # sentinel shape rather than crash.
        missing = os.path.join(self.root, "_no_such_dir_xyz")
        result = self._run(["--root", missing])
        self.assertEqual(result["override_rate"], {"current": 0, "prior": 0, "arrow": "→"})


if __name__ == "__main__":
    unittest.main()
