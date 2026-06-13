"""Tests for governs_index() and the H-12 governs check in post-write-edit.py."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the symbols under test directly from the module file to avoid
# triggering main() or any side-effects at import time.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "post_write_edit",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "post-write-edit.py"),
)
_mod = _ilu.module_from_spec(_spec)
# The module calls sys.path.insert at module level to locate _hooklib; that
# path is already on sys.path from the line above, so the exec is safe.
_spec.loader.exec_module(_mod)

governs_index = _mod.governs_index
GOVERNS_RE = _mod.GOVERNS_RE
STATUS_RE = _mod.STATUS_RE


def _write_adr(ddir, filename, governs=None, status="accepted", title=None):
    """Write a minimal ADR file in *ddir*."""
    lines = ["---"]
    if title:
        lines.append(f"title: {title}")
    if status:
        lines.append(f"status: {status}")
    if governs:
        lines.append(f"governs: {governs}")
    lines.append("---")
    lines.append("# Body")
    with open(os.path.join(ddir, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class TestGovernsIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ddir = os.path.join(self.root, ".codearbiter", "decisions")
        os.makedirs(self.ddir, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _cache_path(self):
        return os.path.join(self.root, ".codearbiter", ".markers", "governs-cache.json")

    # ------------------------------------------------------------------
    # D-16: cache miss — no cache file → builds and writes cache
    # ------------------------------------------------------------------
    def test_cache_miss_builds_index_and_writes_cache(self):
        _write_adr(self.ddir, "0001-api-design.md",
                   governs="src/api/**/*.py", title="API Design")
        index = governs_index(self.root)
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["adr"], "0001")
        self.assertIn("src/api/**/*.py", index[0]["globs"])
        # Cache must now exist on disk.
        self.assertTrue(os.path.isfile(self._cache_path()))

    # ------------------------------------------------------------------
    # D-16: cache hit — valid stamp → returns cached data, no re-scan
    # ------------------------------------------------------------------
    def test_cache_hit_with_valid_stamp_skips_rescan(self):
        adr_path = os.path.join(self.ddir, "0001-api-design.md")
        _write_adr(self.ddir, "0001-api-design.md",
                   governs="src/api/**/*.py", title="API Design")
        # Prime the cache by running governs_index once.
        governs_index(self.root)

        # Poison the ADR file on disk — if the cache is truly returned, the
        # poison never reaches the caller.
        with open(adr_path, "w") as f:
            f.write("POISONED — no valid frontmatter\n")

        # governs_index uses max(mtime of each ADR file) as the cache stamp.
        # After poisoning, the file has a new mtime. We update the cache on
        # disk so its stamp matches the poisoned file's current mtime — that
        # makes governs_index believe the cache is fresh and return it.
        new_stamp = os.path.getmtime(adr_path)
        cache_path = self._cache_path()
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)
        cached["stamp"] = new_stamp
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f)

        index2 = governs_index(self.root)
        self.assertEqual(len(index2), 1)
        self.assertIn("src/api/**/*.py", index2[0]["globs"])

    # ------------------------------------------------------------------
    # D-16: superseded / rejected ADR → excluded from governs list
    # ------------------------------------------------------------------
    def test_superseded_adr_excluded_from_index(self):
        _write_adr(self.ddir, "0002-old-pattern.md",
                   governs="src/legacy/**", status="superseded")
        index = governs_index(self.root)
        self.assertEqual(index, [])

    def test_rejected_adr_excluded_from_index(self):
        _write_adr(self.ddir, "0003-nope.md",
                   governs="src/nope/**", status="rejected")
        index = governs_index(self.root)
        self.assertEqual(index, [])

    def test_accepted_adr_included_while_superseded_excluded(self):
        _write_adr(self.ddir, "0001-good.md",
                   governs="src/good/**", status="accepted", title="Good ADR")
        _write_adr(self.ddir, "0002-old.md",
                   governs="src/old/**", status="superseded")
        index = governs_index(self.root)
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["adr"], "0001")

    # ------------------------------------------------------------------
    # D-16: H-12 governs check fires on matching path, not on non-matching
    # ------------------------------------------------------------------
    def test_governs_check_fires_on_matching_path(self):
        import fnmatch
        _write_adr(self.ddir, "0010-schema.md",
                   governs="src/models/*.py", title="Schema ADR")
        index = governs_index(self.root)
        self.assertTrue(index)
        entry = index[0]
        # A path that matches should be governed.
        self.assertTrue(
            any(fnmatch.fnmatch("src/models/user.py", g) for g in entry["globs"])
        )

    def test_governs_check_does_not_fire_on_non_matching_path(self):
        import fnmatch
        _write_adr(self.ddir, "0010-schema.md",
                   governs="src/models/*.py", title="Schema ADR")
        index = governs_index(self.root)
        self.assertTrue(index)
        entry = index[0]
        # A path outside the governed glob must NOT match.
        self.assertFalse(
            any(fnmatch.fnmatch("tests/test_user.py", g) for g in entry["globs"])
        )

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------
    def test_empty_decisions_dir_returns_empty_list(self):
        index = governs_index(self.root)
        self.assertEqual(index, [])

    def test_missing_decisions_dir_returns_empty_list(self):
        import shutil
        shutil.rmtree(self.ddir)
        index = governs_index(self.root)
        self.assertEqual(index, [])

    def test_adr_without_governs_field_excluded(self):
        _write_adr(self.ddir, "0005-no-governs.md",
                   governs=None, status="accepted", title="No governs")
        index = governs_index(self.root)
        self.assertEqual(index, [])

    def test_multiple_governs_globs_parsed(self):
        _write_adr(self.ddir, "0006-multi.md",
                   governs="src/*.py, tests/*.py, docs/*.md", title="Multi")
        index = governs_index(self.root)
        self.assertEqual(len(index), 1)
        self.assertEqual(sorted(index[0]["globs"]),
                         sorted(["src/*.py", "tests/*.py", "docs/*.md"]))


if __name__ == "__main__":
    unittest.main()
