import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _protectedstatelib  # noqa: E402
from _protectedstatelib import (  # noqa: E402
    MARKER_FRESHNESS_MINUTES,
    ProtectedPolicy,
    lookup_policy,
    marker_gated_write_admitted,
    marker_name_for,
)


def _touch(path, age_seconds=0):
    """Create an empty file at `path`, optionally backdating its mtime by
    `age_seconds` (the one filesystem-writing test helper, kept in one place
    so every marker test backdates the same way)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("")
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))


class TestPolicyEnum(unittest.TestCase):
    """B-01: the registry carries a per-entry policy enum with exactly the
    three declared values, and an unknown policy string is an internal
    programming error (a typo'd registry entry) that is correct to raise on,
    not degrade from (coding-standards.md's "never raise on malformed user
    input" rule is about INPUT reaching a hook, not a broken call site)."""

    def test_policy_enum(self):
        self.assertEqual(
            {p.value for p in ProtectedPolicy},
            {"marker-gated", "helper-only", "append-only"},
        )
        self.assertIs(ProtectedPolicy("marker-gated"), ProtectedPolicy.MARKER_GATED)
        self.assertIs(ProtectedPolicy("helper-only"), ProtectedPolicy.HELPER_ONLY)
        self.assertIs(ProtectedPolicy("append-only"), ProtectedPolicy.APPEND_ONLY)
        with self.assertRaises(ValueError):
            ProtectedPolicy("some-unrecognized-policy")

    def test_policy_enum_members_are_str_and_compare_equal_to_plain_values(self):
        # Pins the `str` mixin itself (M4): dropping `class ProtectedPolicy(Enum)`
        # (no str mixin) still satisfies `.value` checks, but `==` against a
        # plain string and `isinstance(..., str)` both flip false without the
        # mixin - these are the two assertions that actually depend on it.
        self.assertEqual(ProtectedPolicy.MARKER_GATED, "marker-gated")
        self.assertEqual(ProtectedPolicy.HELPER_ONLY, "helper-only")
        self.assertEqual(ProtectedPolicy.APPEND_ONLY, "append-only")
        self.assertIsInstance(ProtectedPolicy.MARKER_GATED, str)


class TestRegistryLookup(unittest.TestCase):
    """B-01: a registered path returns its policy; an unregistered path
    returns None. `registry` is an explicit parameter (defaulting to the
    module REGISTRY) so this stays generic machinery testable with a
    synthetic map, rather than something wired to a specific consumer set -
    release-targets.md is NOT hardcoded into this module (its own later task
    registers it; see the second test below)."""

    def test_registry_lookup(self):
        registry = {".codearbiter/release-targets.md": ProtectedPolicy.MARKER_GATED}
        self.assertEqual(
            lookup_policy(".codearbiter/release-targets.md", registry),
            ProtectedPolicy.MARKER_GATED,
        )
        self.assertIsNone(lookup_policy(".codearbiter/open-tasks.md", registry))

    def test_registry_lookup_normalizes_backslash_paths(self):
        registry = {".codearbiter/release-targets.md": ProtectedPolicy.MARKER_GATED}
        self.assertEqual(
            lookup_policy(".codearbiter\\release-targets.md", registry),
            ProtectedPolicy.MARKER_GATED,
        )

    def test_registry_lookup_normalizes_backslash_registry_keys(self):
        # M6: a typo'd registry KEY (backslash-separated) must not silently
        # protect nothing - the same normalization applies to keys as to the
        # query path.
        registry = {".codearbiter\\release-targets.md": ProtectedPolicy.MARKER_GATED}
        self.assertEqual(
            lookup_policy(".codearbiter/release-targets.md", registry),
            ProtectedPolicy.MARKER_GATED,
        )

    def test_registry_lookup_default_registry_has_no_hardcoded_consumers(self):
        # B1 ships the registry mechanism, not entries - release-targets.md
        # is registered by its OWN later task (B-13), never by this module.
        self.assertIsNone(lookup_policy(".codearbiter/release-targets.md"))

    def test_registry_lookup_default_registry_is_empty(self):
        # H1: a direct positive fact about the production registry itself,
        # not just a negative lookup - catches a mutant that seeds REGISTRY
        # with a bogus entry, which the negative test above cannot detect
        # (it would only notice a seeded entry that happens to collide with
        # this one literal path).
        self.assertEqual(_protectedstatelib.REGISTRY, {})

    def test_registry_lookup_reads_the_default_module_registry(self):
        # H1: the three "positive lookup" tests above all inject a synthetic
        # registry, so none of them proves lookup_policy's default path
        # (`registry is None -> registry = REGISTRY`) actually reads the
        # module-level REGISTRY at all - a mutant hardcoding `registry = {}`
        # passed every existing test. Patch REGISTRY itself and call
        # lookup_policy with NO registry argument, through the real default
        # path, then restore.
        original = _protectedstatelib.REGISTRY
        try:
            _protectedstatelib.REGISTRY = {
                ".codearbiter/release-targets.md": ProtectedPolicy.MARKER_GATED,
            }
            self.assertEqual(
                lookup_policy(".codearbiter/release-targets.md"),
                ProtectedPolicy.MARKER_GATED,
            )
        finally:
            _protectedstatelib.REGISTRY = original


class TestMarkerGatedWrite(unittest.TestCase):
    """B-02: for the `marker-gated` policy, a Write/Edit/shell mutation is
    admitted only under a fresh authoring marker (the H-11 pattern) - a fresh
    marker admits, an absent marker blocks."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.markers_dir = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(self.markers_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_marker_gated_write_fresh_marker_admits(self):
        _touch(os.path.join(self.markers_dir, "release-targets-authoring"))
        self.assertTrue(
            marker_gated_write_admitted(".codearbiter/release-targets.md", self.root)
        )

    def test_marker_gated_write_absent_marker_blocks(self):
        self.assertFalse(
            marker_gated_write_admitted(".codearbiter/release-targets.md", self.root)
        )

    def test_marker_gated_write_derives_stem_authoring_marker_name(self):
        self.assertEqual(
            marker_name_for(".codearbiter/release-targets.md"),
            "release-targets-authoring",
        )

    def test_marker_gated_write_honors_custom_minutes_parameter(self):
        # L8: `minutes` is a real parameter, not dead - a 2-minute-old marker
        # is stale under a 1-minute window and fresh under a 5-minute one.
        _touch(
            os.path.join(self.markers_dir, "release-targets-authoring"),
            age_seconds=120,
        )
        self.assertFalse(
            marker_gated_write_admitted(
                ".codearbiter/release-targets.md", self.root, minutes=1
            )
        )
        self.assertTrue(
            marker_gated_write_admitted(
                ".codearbiter/release-targets.md", self.root, minutes=5
            )
        )


class TestMarkerStale(unittest.TestCase):
    """B-10: a marker older than the freshness window does not admit a
    write. Exercises the boundary in both directions so the test is not
    vacuous against an implementation that ignores mtime entirely."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.markers_dir = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(self.markers_dir)
        self.marker_name = "release-targets-authoring"

    def tearDown(self):
        self._tmp.cleanup()

    def test_marker_stale_blocks(self):
        _touch(
            os.path.join(self.markers_dir, self.marker_name),
            age_seconds=MARKER_FRESHNESS_MINUTES * 60 + 60,
        )
        self.assertFalse(
            marker_gated_write_admitted(".codearbiter/release-targets.md", self.root)
        )

    def test_marker_stale_just_inside_window_still_admits(self):
        _touch(
            os.path.join(self.markers_dir, self.marker_name),
            age_seconds=MARKER_FRESHNESS_MINUTES * 60 - 60,
        )
        self.assertTrue(
            marker_gated_write_admitted(".codearbiter/release-targets.md", self.root)
        )


class TestFreshnessWindow(unittest.TestCase):
    """H2: the freshness window's VALUE is part of the contract, not just its
    boundary arithmetic - both stale-window tests above compute their ages
    from MARKER_FRESHNESS_MINUTES itself, so they pin the boundary logic but
    would pass unchanged if the constant were widened (or narrowed) to any
    other value. Pin the value directly, matching the H-11 ADR-authoring
    window it is designed to mirror."""

    def test_marker_freshness_minutes_is_30(self):
        self.assertEqual(MARKER_FRESHNESS_MINUTES, 30)


class TestMarkerNameFor(unittest.TestCase):
    """B-02/M5/M7: marker_name_for's derivation - collision-freedom across
    sub-directories, backslash normalization, and non-raising degenerate
    input."""

    def test_marker_name_for_normalizes_backslash_paths(self):
        # M7: lookup_policy has a backslash-normalization test; marker_name_for
        # had no counterpart, so a mutant swapping norm_path(rel_path) for a
        # bare `rel_path or ""` survived on both platforms.
        self.assertEqual(
            marker_name_for(".codearbiter\\release-targets.md"),
            marker_name_for(".codearbiter/release-targets.md"),
        )

    def test_marker_name_for_is_collision_free_across_sub_directories(self):
        # M5: two registry entries that merely share a filename in different
        # directories must mint two DIFFERENT markers - minting the marker
        # for one would otherwise admit a write to the other.
        self.assertNotEqual(
            marker_name_for(".codearbiter/release-targets.md"),
            marker_name_for(".codearbiter/nested/release-targets.md"),
        )
        self.assertNotEqual(
            marker_name_for("a/x.md"),
            marker_name_for("b/x.yml"),
        )

    def test_marker_name_for_degenerate_inputs_never_raise_and_stay_flat(self):
        # M5: "", None, and a bare directory must not silently crash and must
        # stay a single, traversal-safe basename (no separators reaching the
        # returned name).
        for degenerate in ("", None, "docs/", ".", ".."):
            name = marker_name_for(degenerate)
            self.assertIsInstance(name, str)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertNotIn("..", name)
        self.assertEqual(marker_name_for(""), "-authoring")
        self.assertEqual(marker_name_for(None), "-authoring")

    def test_marker_name_for_degenerate_input_never_collides_with_a_real_path(self):
        self.assertNotEqual(marker_name_for(""), marker_name_for("release-targets.md"))


if __name__ == "__main__":
    unittest.main()
