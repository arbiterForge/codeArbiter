import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

# Ensure hooks/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import babysit  # noqa: E402 — the thin entry hook for /ca:pr, /ca:watch (#179)
import _babysitlib  # noqa: E402


class TestBabysitEntry(unittest.TestCase):
    """babysit.py: thin entry hook delegating to _babysitlib.main. Proves
    /ca:pr and /ca:watch now invoke a non-underscore entry point rather than
    running the underscore library itself as a script (architecture-006/#179)."""

    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("CODEARBITER_BABYSIT", "CODEARBITER_BABYSIT_ONRED")}
        for k in self._saved:
            os.environ.pop(k, None)
        self.root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_no_such_repo_xyz")

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_delegates_to_babysitlib_main(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = babysit.main(["--root", self.root])
        self.assertEqual(rc, 0)
        cfg = json.loads(buf.getvalue().strip())
        self.assertIn("enabled", cfg)
        self.assertIn("on_red", cfg)

    def test_babysitlib_has_no_dunder_main_guard(self):
        # Convention check: _babysitlib is import-only (no `if __name__ ==
        # "__main__"` block) — the __main__ entry point now lives only in the
        # thin babysit.py wrapper.
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_babysitlib.py",
        )
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn('__name__ == "__main__"', src)
        self.assertNotIn("__name__ == '__main__'", src)


if __name__ == "__main__":
    unittest.main()
