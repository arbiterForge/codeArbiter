import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _hooklib import frontmatter_enabled  # noqa: E402


def _write_ctx(tmp, content):
    """Write content (str or bytes) to a CONTEXT.md in tmp and return its path."""
    path = os.path.join(tmp, "CONTEXT.md")
    if isinstance(content, str):
        content = content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(content)
    return path


class TestFrontmatterEnabled(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_frontmatter_returns_false_false(self):
        # A file whose first line is NOT "---" is dormant — not malformed.
        path = _write_ctx(self.tmp, "# Just a heading\narbiter: enabled\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_valid_frontmatter_arbiter_enabled(self):
        path = _write_ctx(self.tmp, "---\narbiter: enabled\n---\n# Body\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_unclosed_frontmatter_returns_false_true(self):
        # Opening "---" with no closing "---" is the fail-loud case.
        path = _write_ctx(self.tmp, "---\narbiter: enabled\n# no closing delimiter\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertTrue(malformed)

    def test_bom_on_first_line_frontmatter_enabled(self):
        # A UTF-8 BOM (\xef\xbb\xbf) before the opening "---" must be tolerated.
        content = b"\xef\xbb\xbf---\narbiter: enabled\n---\n# Body\n"
        path = _write_ctx(self.tmp, content)
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_arbiter_enabled_mixed_case(self):
        # The regex is case-insensitive; "Enabled" must be accepted.
        path = _write_ctx(self.tmp, "---\narbiter: Enabled\n---\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_arbiter_disabled_returns_false_false(self):
        # "arbiter: disabled" is a valid, closed frontmatter — dormant, not malformed.
        path = _write_ctx(self.tmp, "---\narbiter: disabled\n---\n# ctx\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_missing_file_returns_false_false(self):
        # A nonexistent file must not raise — dormant, not malformed.
        path = os.path.join(self.tmp, "does_not_exist.md")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_empty_file_returns_false_false(self):
        path = _write_ctx(self.tmp, "")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_closed_frontmatter_without_arbiter_key(self):
        # A properly closed frontmatter that lacks the arbiter key is dormant.
        path = _write_ctx(self.tmp, "---\ntitle: My project\nauthor: Alice\n---\n# Body\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)


if __name__ == "__main__":
    unittest.main()
