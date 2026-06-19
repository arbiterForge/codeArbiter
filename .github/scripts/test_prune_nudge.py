#!/usr/bin/env python3
"""CI runner for the cold-miss nudge unit tests.

Mirrors .github/scripts/test_preview_lib.py's sys.path pattern:
adds plugins/ca/hooks/tests to sys.path so test_prune_nudge can import
_prunelib and _helpers without a package install.

Exit 0 = all tests pass; exit 1 = any failure.

Run as: python .github/scripts/test_prune_nudge.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
HOOKS_TESTS = os.path.join(HOOKS, "tests")

sys.path.insert(0, HOOKS)
sys.path.insert(0, HOOKS_TESTS)

import test_prune_nudge  # noqa: E402 — needs sys.path mutation above

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(test_prune_nudge)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
