#!/usr/bin/env python3
"""codeArbiter — unit tests for the release-skill hardening helpers (_releaselib).

Spec: .codearbiter/specs/release-skill-hardening.md. Each test class maps to one
acceptance criterion:

  LastTagSelectTest      AC-1 (0006) — baseline tag selection, pre-release + ca-sandbox excluded
  NotesHeadingTest       AC-2 (0005) — release-notes heading matches the tag
  ReleaseDatesTest       AC-3 (0004) — changelog date == Released-at date
  ClassifyPublishTest    AC-4 (0003) — half-finished-publish state classifier
  SkillProseTest         AC-5 (0002) + skill-side wiring of AC-1..4 (structural, Batch 2)

The helpers are pure functions exercised with synthetic input — no git, no I/O.
Stdlib only. Exit 0 = all pass; non-zero = failure.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _releaselib  # noqa: E402 — needs sys.path mutation above


class LastTagSelectTest(unittest.TestCase):
    """AC-1 (0006): highest ca SemVer tag, excluding pre-releases and ca-sandbox-v*."""

    def test_picks_highest_release_excluding_prerelease_and_sandbox(self):
        tags = ["v2.5.0", "v2.5.1", "v2.6.0-beta.1", "ca-sandbox-v0.1.0"]
        self.assertEqual(_releaselib.last_tag_select(tags), "v2.5.1")

    def test_none_when_only_prerelease_and_sandbox(self):
        tags = ["ca-sandbox-v0.1.0", "v2.7.0-rc.1"]
        self.assertEqual(_releaselib.last_tag_select(tags), _releaselib.NONE_SENTINEL)

    def test_empty_returns_sentinel(self):
        self.assertEqual(_releaselib.last_tag_select([]), _releaselib.NONE_SENTINEL)

    def test_numeric_order_not_lexical(self):
        # 2.10.0 > 2.9.0 numerically, but sorts BEFORE it lexically.
        tags = ["v2.9.0", "v2.10.0"]
        self.assertEqual(_releaselib.last_tag_select(tags), "v2.10.0")

    def test_alpha_excluded(self):
        self.assertEqual(
            _releaselib.last_tag_select(["v3.0.0-alpha.2", "v2.9.9"]), "v2.9.9")

    def test_never_raises_on_garbage(self):
        # Mixed junk must degrade, never raise (coding-standards: never raise on bad input).
        self.assertEqual(
            _releaselib.last_tag_select(["", "vX.Y.Z", None, 42, "v1.0.0"]), "v1.0.0")


class NotesHeadingTest(unittest.TestCase):
    """AC-2 (0005): the notes' first `## vX.Y.Z` heading must equal the tag."""

    def test_matching_heading(self):
        notes = "## v2.6.0 — 2026-06-26\n\n### Added\n- thing\n"
        self.assertTrue(_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_matching_bracket_heading(self):
        # Keep-a-Changelog bracket form — the repo's actual CHANGELOG convention
        # (every released section + every prior GitHub Release body). The tag is
        # `vX.Y.Z`; the heading carries `[X.Y.Z]` with no leading `v`. Regression
        # for the v2.6.0 publish, where this guard no-matched purely on style.
        notes = "## [2.6.0] — 2026-06-27\n\n### Added\n- thing\n"
        self.assertTrue(_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_mismatched_heading(self):
        notes = "## v2.5.0 — 2026-06-01\n\n### Fixed\n- bug\n"
        self.assertFalse(_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_mismatched_bracket_heading(self):
        # Protective value preserved: a stale bracket-form notes file whose first
        # section is an older version must still fail, so accepting the bracket
        # style never degrades into matching any version.
        notes = "## [2.5.0] — 2026-06-01\n\n### Fixed\n- bug\n"
        self.assertFalse(_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_first_heading_is_authoritative(self):
        notes = "## v2.5.0 — 2026-06-01\n\n## v2.6.0 — 2026-06-26\n"
        # Stale notes whose FIRST section is the wrong (old) version must fail.
        self.assertFalse(_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_no_heading_is_false(self):
        self.assertFalse(_releaselib.notes_heading_matches("no headings here", "v2.6.0"))

    def test_never_raises_on_non_string(self):
        self.assertFalse(_releaselib.notes_heading_matches(None, "v2.6.0"))


class ReleaseDatesTest(unittest.TestCase):
    """AC-3 (0004): the changelog `## vX.Y.Z — DATE` date == the `Released-at: DATE`."""

    def test_consistent_dates(self):
        section = "## v2.6.0 — 2026-06-26\n\n### Added\n- thing\n"
        tagmsg = "codeArbiter 2.6.0\n\nstuff\n\nReleased-at: 2026-06-26\n"
        self.assertTrue(_releaselib.release_dates_consistent(section, tagmsg))

    def test_consistent_dates_bracket_heading(self):
        # Bracket-form changelog section (the repo convention). The date must be
        # read from `## [X.Y.Z] — DATE`, not only from `## vX.Y.Z — DATE`.
        section = "## [2.6.0] — 2026-06-27\n\n### Added\n- thing\n"
        tagmsg = "codeArbiter 2.6.0\n\nstuff\n\nReleased-at: 2026-06-27\n"
        self.assertTrue(_releaselib.release_dates_consistent(section, tagmsg))

    def test_inconsistent_dates(self):
        section = "## v2.6.0 — 2026-06-26\n"
        tagmsg = "Released-at: 2026-06-25\n"
        self.assertFalse(_releaselib.release_dates_consistent(section, tagmsg))

    def test_missing_changelog_date_is_false(self):
        self.assertFalse(
            _releaselib.release_dates_consistent("## v2.6.0\n", "Released-at: 2026-06-26\n"))

    def test_missing_tag_date_is_false(self):
        self.assertFalse(
            _releaselib.release_dates_consistent("## v2.6.0 — 2026-06-26\n", "no footer"))

    def test_never_raises(self):
        self.assertFalse(_releaselib.release_dates_consistent(None, None))


class ClassifyPublishTest(unittest.TestCase):
    """AC-4 (0003): half-finished-publish state classifier."""

    def test_no_tag_is_publish_fresh(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=False, tag_sha=None, head_sha="abc",
                tag_version=None, manifest_version="2.6.0", release_is_nondraft=False),
            "publish_fresh")

    def test_tag_at_head_version_match_no_release_is_resume(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=False),
            "resume_publish")

    def test_nondraft_release_is_already_published(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=True),
            "already_published")

    def test_tag_points_elsewhere_is_abort(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="xyz", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=False),
            "abort_mismatch")

    def test_version_mismatch_is_abort(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.5.0", manifest_version="2.6.0", release_is_nondraft=False),
            "abort_mismatch")


class CLITest(unittest.TestCase):
    """The thin CLI dispatch the release skill shells out to."""

    def _run(self, argv, stdin_text=""):
        import io
        import contextlib
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out):
                rc = _releaselib.main(argv)
        finally:
            sys.stdin = old_stdin
        return rc, out.getvalue().strip()

    def test_last_tag_from_stdin(self):
        rc, out = self._run(
            ["last-tag"], "v2.5.0\nv2.5.1\nv2.6.0-beta.1\nca-sandbox-v0.1.0\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "v2.5.1")

    def test_notes_match_exit_codes(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
                "w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("## v2.6.0 — 2026-06-26\n")
            path = f.name
        try:
            rc_ok, _ = self._run(["notes-match", "v2.6.0", path])
            rc_bad, _ = self._run(["notes-match", "v2.5.0", path])
        finally:
            os.unlink(path)
        self.assertEqual(rc_ok, 0)
        self.assertEqual(rc_bad, 1)

    def test_classify_prints_label(self):
        rc, out = self._run(
            ["classify", "true", "abc", "abc", "2.6.0", "2.6.0", "false"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "resume_publish")

    def test_bad_invocation_returns_2(self):
        rc, _ = self._run(["nonsense"])
        self.assertEqual(rc, 2)


class SkillProseTest(unittest.TestCase):
    """AC-5 (0002) + skill-side wiring of AC-1..4 into release/SKILL.md.

    Structural: the prose is what the orchestrator follows, so we assert the
    helpers are invoked and the farm.js freshness instruction is unconditional
    and points at CI as the backstop."""

    @classmethod
    def setUpClass(cls):
        repo = os.path.dirname(os.path.dirname(HERE))
        path = os.path.join(repo, "plugins", "ca", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_invokes_each_helper(self):
        for token in ("_releaselib.py", "last_tag_select", "notes_heading_matches",
                      "release_dates_consistent", "classify_publish_state"):
            self.assertIn(token, self.text, f"SKILL.md must invoke {token}")

    def test_farmjs_freshness_is_unconditional(self):
        # The rebuild + diff must be present and described as unconditional...
        self.assertIn("git diff --quiet -- plugins/ca/tools/farm.js", self.text)
        self.assertIn("unconditional", self.text.lower())
        # ...and NOT gated behind the old in-window farm.ts conditional (0002).
        self.assertNotIn(
            "if `plugins/ca/tools/farm.ts` was modified in the release window",
            self.text,
            "0002: the farm.js rebuild must not be conditional on an in-window farm.ts change")

    def test_names_ci_tools_job_as_backstop(self):
        self.assertIn("CI `tools` job", self.text,
                      "AC-5: the local check must name the CI tools job as the mechanical backstop")

    def test_date_derived_once(self):
        # The release date is computed once and reused (no second hand-typed date).
        self.assertIn("date +%F", self.text)


if __name__ == "__main__":
    unittest.main()
