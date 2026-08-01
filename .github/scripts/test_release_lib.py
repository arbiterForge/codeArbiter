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

Portable-release split (issue #563, .codearbiter/specs/release-portable-fixture.md,
slice 1). The classes below this point exercise `core/pysrc/_releaselib.py` — the
PORTABLE mechanism module, loaded under a distinct module name (`_core_releaselib`)
so it never collides with `.github/scripts/_releaselib.py` (the repo's own,
data-carrying, currently-unmodified shim) imported above as `_releaselib`:

  DenylistTest              A-1.2 — no repo-namespace/CI-vocabulary literal in the mechanism
  RequiredParamsTest        A-1.3 — repo defaults became required parameters
  LoadTargetsTest           A-1.4 — load_targets(path) returns the full row schema
  AbsentBlockTest           A-1.5 — an absent delimiter block raises a declared error
  ParserContractTest        A-1.6 — each parser-contract violation raises its own error
  EmptyBlockTest            A-1.7 — an empty delimiter block raises a declared error
  SeriesIsolationTest       A-1.8 — series isolation against loaded target data

Adversarial-review remediation (2026-07-31, mutation campaign against
core/pysrc/_releaselib.py). Each class below exercises `core_releaselib`
directly, closing the gap where the mechanism shipped in a new module but its
proof still lived only against the old, unmodified shim:

  CoreDelimiterInValueTest        H1 — value-embedded delimiter errors, both directions
  CoreRequiredKeyEmptyValueTest   H2 — an empty/whitespace required-key value is MISSING
  CoreClassifyPublishStateTest    H3 — classify_publish_state against the portable module
  CoreNotesHeadingTest            H3 — notes_heading_matches / _bare_version, ditto
  CoreReleaseDatesTest            H3 — release_dates_consistent, ditto
  CorePeelTagTest                 H3 — peel_tag, ditto
  CoreSemverTest                  H3 — semver_key / semver_greater, previously untested anywhere
  CoreMergeReadinessArmsTest      H3 — classify_merge_readiness's 4 non-green arms
  CoreSelectReleaseTargetArmsTest H3 — select_release_target's arity/multiple arms
  CorePrereleaseMarkerScopeTest   M2 — marker denylist scoped to the version, not the prefix
  CoreColonInValueTest            M4 — values split on the FIRST colon only
  CoreEscapeHatchWrappingTest     M5 — non-string input / unreadable path stay in-hierarchy
"""

import importlib.util
import inspect
import io
import json
import os
import subprocess
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _releaselib  # noqa: E402 — needs sys.path mutation above

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
_CORE_RELEASELIB_PATH = os.path.join(REPO_ROOT, "core", "pysrc", "_releaselib.py")
_core_spec = importlib.util.spec_from_file_location(
    "_core_releaselib", _CORE_RELEASELIB_PATH)
core_releaselib = importlib.util.module_from_spec(_core_spec)
# Registered in sys.modules (not just bound to a local name) so `inspect.
# getsourcefile` can resolve it — inspect looks the object's `__module__` up
# in sys.modules to find `__file__`, and an unregistered dynamically-loaded
# module reads back as a "built-in class" with no source file at all.
sys.modules[_core_spec.name] = core_releaselib
_core_spec.loader.exec_module(core_releaselib)


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

    def test_nondraft_release_on_a_tag_at_another_commit_is_abort(self):
        # Issue #380: a published Release used to short-circuit to
        # `already_published` BEFORE the tag was compared to HEAD, so a
        # resumed publish accepted a Release sitting on the wrong commit.
        # Mismatch outranks publication state — the tag identifies what
        # consumers actually install.
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="xyz", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=True),
            "abort_mismatch")

    def test_nondraft_release_with_a_version_mismatch_is_abort(self):
        self.assertEqual(
            _releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.5.0", manifest_version="2.6.0", release_is_nondraft=True),
            "abort_mismatch")


class SelectReleaseTargetTest(unittest.TestCase):
    """Issue #378: one dispatch selects exactly one plugin, or none at all.

    The confirmation inputs are independent optional strings, so the workflow's
    publish jobs used to test only their own input — supplying two started two
    write-token publishers from one dispatch.

    Issue #382 widened the register from two plugins to four. The inputs are
    POSITIONAL in RELEASE_TARGETS order, which makes ordering part of the
    contract: a caller that passed them in a different order would resolve the
    wrong plugin and publish an irreversible tag for it."""

    VERSIONS = ("2.6.1", "0.2.4", "0.1.5", "0.1.28")

    def _inputs(self, **supplied):
        """A full-arity argument list, blank except where named by target."""
        values = {target: "" for target in _releaselib.RELEASE_TARGETS}
        values.update(supplied)
        return [values[target] for target in _releaselib.RELEASE_TARGETS]

    def test_the_register_is_the_four_shipped_plugins(self):
        self.assertEqual(_releaselib.RELEASE_TARGETS,
                         ("ca", "ca-codex", "ca-sandbox", "ca-pi"))
        self.assertEqual(len(self.VERSIONS), len(_releaselib.RELEASE_TARGETS))

    def test_each_position_selects_its_own_target(self):
        for index, target in enumerate(_releaselib.RELEASE_TARGETS):
            with self.subTest(target=target):
                args = [""] * len(_releaselib.RELEASE_TARGETS)
                args[index] = self.VERSIONS[index]
                self.assertEqual(_releaselib.select_release_target(*args), target)

    def test_none_is_none(self):
        self.assertEqual(
            _releaselib.select_release_target(*self._inputs()), "none")

    def test_any_two_is_multiple(self):
        targets = _releaselib.RELEASE_TARGETS
        pairs = [(a, b) for i, a in enumerate(targets) for b in targets[i + 1:]]
        self.assertEqual(len(pairs), 6)
        for first, second in pairs:
            with self.subTest(pair=(first, second)):
                selected = self._inputs(**{first: "1.0.0", second: "2.0.0"})
                self.assertEqual(
                    _releaselib.select_release_target(*selected), "multiple")

    def test_all_four_is_multiple(self):
        self.assertEqual(
            _releaselib.select_release_target(*self.VERSIONS), "multiple")

    def test_whitespace_is_not_a_selection(self):
        # A stray space in a dispatch field must not read as a second target.
        self.assertEqual(
            _releaselib.select_release_target(*self._inputs(**{"ca": "   ",
                                                              "ca-pi": "0.1.28"})),
            "ca-pi")
        self.assertEqual(
            _releaselib.select_release_target("  ", "\t", "\n", " "), "none")

    def test_never_raises_on_non_string(self):
        self.assertEqual(
            _releaselib.select_release_target(None, None, None, None), "none")
        self.assertEqual(
            _releaselib.select_release_target(42, "", "", ()), "none")
        self.assertEqual(
            _releaselib.select_release_target(42, "0.2.4", None, ""), "ca-codex")

    def test_the_wrong_number_of_inputs_resolves_no_target(self):
        # A caller wired for two would otherwise resolve `ca` from a dispatch
        # that also selected ca-pi. `arity` is not a target and matches no
        # `case` arm in release.yml, so the fail-closed `*)` default refuses it.
        for args in ((), ("2.6.1",), ("2.6.1", ""), ("", "", ""),
                     ("", "", "", "", "")):
            with self.subTest(count=len(args)):
                verdict = _releaselib.select_release_target(*args)
                self.assertEqual(verdict, "arity")
                self.assertNotIn(verdict, _releaselib.RELEASE_TARGETS)

    def test_the_cli_refuses_a_wrong_length_invocation(self):
        # The shell assigns from this command under `set -e`, so a non-zero exit
        # with no label on stdout refuses the dispatch.
        self.assertEqual(_releaselib.main(["select-target", "2.6.1", ""]), 2)
        self.assertEqual(_releaselib.main(["select-target", "2.6.1", "", "", "", ""]), 2)


class MergeReadinessTest(unittest.TestCase):
    """Issue #385: the exact commit being tagged must carry green evidence."""

    SHA = "a" * 40
    OTHER = "b" * 40

    def _run(self, status="completed", conclusion="success", head_sha=None, name=None):
        return {
            "name": _releaselib.MERGE_READINESS_CHECK if name is None else name,
            "status": status,
            "conclusion": conclusion,
            "head_sha": self.SHA if head_sha is None else head_sha,
        }

    def test_completed_success_is_green(self):
        self.assertEqual(
            _releaselib.classify_merge_readiness([self._run()], self.SHA), "green")

    def test_unrelated_checks_do_not_stand_in_for_the_gate(self):
        others = [self._run(name="CA | [Tools] - Vitest"), self._run(name="lint")]
        self.assertEqual(
            _releaselib.classify_merge_readiness(others, self.SHA), "missing")

    def test_no_checks_at_all_is_missing(self):
        self.assertEqual(_releaselib.classify_merge_readiness([], self.SHA), "missing")

    def test_queued_and_in_progress_are_pending(self):
        for status in ("queued", "in_progress", "waiting", "pending", "requested"):
            with self.subTest(status=status):
                run = self._run(status=status, conclusion=None)
                self.assertEqual(
                    _releaselib.classify_merge_readiness([run], self.SHA), "pending")

    def test_every_non_success_conclusion_is_rejected(self):
        for conclusion in ("failure", "cancelled", "skipped", "timed_out",
                           "action_required", "neutral", "stale", None, ""):
            with self.subTest(conclusion=conclusion):
                run = self._run(conclusion=conclusion)
                self.assertEqual(
                    _releaselib.classify_merge_readiness([run], self.SHA),
                    "not_successful")

    def test_success_on_another_commit_is_rejected(self):
        run = self._run(head_sha=self.OTHER)
        self.assertEqual(
            _releaselib.classify_merge_readiness([run], self.SHA), "sha_mismatch")

    def test_a_green_rerun_alongside_a_red_one_is_rejected(self):
        # Fail closed: with two verdicts on the name we cannot tell which is
        # authoritative, so we do not get to pick the convenient one.
        runs = [self._run(), self._run(conclusion="failure")]
        self.assertEqual(
            _releaselib.classify_merge_readiness(runs, self.SHA), "not_successful")

    def test_never_raises_on_garbage(self):
        self.assertEqual(_releaselib.classify_merge_readiness(None, self.SHA), "missing")
        self.assertEqual(
            _releaselib.classify_merge_readiness(["nonsense", 7], self.SHA), "missing")
        self.assertEqual(
            _releaselib.classify_merge_readiness([self._run()], None), "sha_mismatch")


class PeelTagTest(unittest.TestCase):
    """Issue #380: an annotated tag's object id is not the commit it names."""

    TAG_OBJ = "1" * 40
    COMMIT = "2" * 40

    def test_annotated_tag_resolves_to_the_peeled_commit(self):
        text = (f"{self.TAG_OBJ}\trefs/tags/v2.6.0\n"
                f"{self.COMMIT}\trefs/tags/v2.6.0^{{}}\n")
        self.assertEqual(_releaselib.peel_tag(text, "v2.6.0"), self.COMMIT)

    def test_lightweight_tag_resolves_to_its_direct_target(self):
        text = f"{self.COMMIT}\trefs/tags/v2.6.0\n"
        self.assertEqual(_releaselib.peel_tag(text, "v2.6.0"), self.COMMIT)

    def test_namespaced_tag(self):
        text = (f"{self.TAG_OBJ}\trefs/tags/ca-codex-v0.2.4\n"
                f"{self.COMMIT}\trefs/tags/ca-codex-v0.2.4^{{}}\n")
        self.assertEqual(_releaselib.peel_tag(text, "ca-codex-v0.2.4"), self.COMMIT)

    def test_a_prefix_sharing_tag_is_not_mistaken_for_it(self):
        # `v2.6.0` must not be resolved from `v2.6.0-beta.1`'s ref line.
        text = f"{self.COMMIT}\trefs/tags/v2.6.0-beta.1\n"
        self.assertEqual(_releaselib.peel_tag(text, "v2.6.0"), "")

    def test_absent_tag_is_empty(self):
        self.assertEqual(_releaselib.peel_tag("", "v2.6.0"), "")

    def test_never_raises_on_non_string(self):
        self.assertEqual(_releaselib.peel_tag(None, "v2.6.0"), "")
        self.assertEqual(_releaselib.peel_tag("whatever", None), "")


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

    def test_select_target_prints_the_label(self):
        # The workflow cases on the label, so the label — not the exit code —
        # is the contract; an unknown label lands on its fail-closed `*` arm.
        # Arguments are positional in RELEASE_TARGETS order (#382).
        for args, expected in ((("2.6.1", "", "", ""), "ca"),
                               (("", "0.2.4", "", ""), "ca-codex"),
                               (("", "", "0.1.5", ""), "ca-sandbox"),
                               (("", "", "", "0.1.28"), "ca-pi"),
                               (("", "", "", ""), "none"),
                               (("2.6.1", "", "", "0.1.28"), "multiple")):
            with self.subTest(args=args):
                rc, out = self._run(["select-target", *args])
                self.assertEqual(rc, 0)
                self.assertEqual(out, expected)

    def test_merge_readiness_reads_check_runs_json(self):
        import json
        import tempfile
        sha = "c" * 40
        payload = [{"name": _releaselib.MERGE_READINESS_CHECK, "status": "completed",
                    "conclusion": "success", "head_sha": sha}]
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(payload, f)
            path = f.name
        try:
            rc_ok, out_ok = self._run(["merge-readiness", sha, path])
            rc_bad, out_bad = self._run(["merge-readiness", "d" * 40, path])
        finally:
            os.unlink(path)
        self.assertEqual((rc_ok, out_ok), (0, "green"))
        self.assertEqual((rc_bad, out_bad), (0, "sha_mismatch"))

    def test_merge_readiness_on_unreadable_input_is_missing(self):
        rc, out = self._run(["merge-readiness", "e" * 40, "no/such/file.json"])
        self.assertEqual((rc, out), (0, "missing"))

    def test_peel_tag_reads_ls_remote_from_stdin(self):
        commit = "f" * 40
        stdin = ("9" * 40 + "\trefs/tags/v2.6.0\n"
                 + commit + "\trefs/tags/v2.6.0^{}\n")
        rc, out = self._run(["peel-tag", "v2.6.0"], stdin)
        self.assertEqual((rc, out), (0, commit))

    def test_peel_tag_prints_nothing_for_an_absent_tag(self):
        rc, out = self._run(["peel-tag", "v9.9.9"], "")
        self.assertEqual((rc, out), (0, ""))


class SkillProseTest(unittest.TestCase):
    """AC-5 (0002) + skill-side wiring of AC-1..4 into release/SKILL.md.

    T-41a-d (issue #563) rewrote the skill from a hardcoded four-row table to
    a declared-file loader, so this class now reads the SOURCE
    (`core/surface/skills/release/SKILL.md`) rather than a generated payload —
    the spec's own "Source of truth" rule ("every skill and command edit
    lands in core/surface/, never a generated plugins/*/ copy. Guards and
    structural assertions target the surface source"), which the pre-rewrite
    version of this class violated by reading `plugins/ca/skills/...`
    directly. Assertions that pinned this repo's four hardcoded rows
    (`test_every_shipped_bundle_is_named_for_its_target`,
    `test_every_release_target_is_reachable_from_the_command`,
    `test_each_target_names_its_own_manifest_and_changelog`,
    `test_only_ca_may_claim_the_latest_badge`,
    `test_the_pi_root_manifest_is_generated_not_hand_edited`,
    `test_names_ci_tools_job_as_backstop`) are retired below in favor of
    `SkillPortabilityTest`, which asserts the LOADER-based replacement shape
    instead — asserting the OLD literal text would now be asserting the
    defect this migration exists to remove."""

    @classmethod
    def setUpClass(cls):
        repo = os.path.dirname(os.path.dirname(HERE))
        path = os.path.join(
            repo, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_invokes_each_helper(self):
        for token in ("_releaselib.py", "last_tag_select", "notes_heading_matches",
                      "release_dates_consistent", "classify_publish_state"):
            self.assertIn(token, self.text, f"SKILL.md must invoke {token}")

    def test_artifact_freshness_is_unconditional(self):
        # The rebuild + diff must be present and described as unconditional...
        self.assertIn("git diff --quiet", self.text)
        self.assertIn("unconditional", self.text.lower())
        # ...and NOT gated behind the old in-window farm.ts conditional (0002).
        self.assertNotIn(
            "if `plugins/ca/tools/farm.ts` was modified in the release window",
            self.text,
            "0002: the rebuild must not be conditional on an in-window source change")

    def test_date_derived_once(self):
        # The release date is computed once and reused (no second hand-typed date).
        self.assertIn("date +%F", self.text)

    def test_changelog_roll_uses_bracket_heading(self):
        # The repo's CHANGELOG.md and the _releaselib guards both use the
        # Keep-a-Changelog `## [X.Y.Z]` heading form; the roll instruction must
        # name that, not the bare `## vX.Y.Z` form that contradicted both (and
        # made notes-match no-match on the real v2.6.0 publish). `vMAJOR.MINOR.
        # PATCH` without the `## ` prefix is still correct for tag names, so the
        # assertion is scoped to the markdown-heading form only.
        self.assertIn("## [MAJOR.MINOR.PATCH]", self.text)
        self.assertNotIn("## vMAJOR.MINOR.PATCH", self.text)


class SkillPortabilityTest(unittest.TestCase):
    """T-41a-d (issue #563, A-6.0): the release skill's Targets table becomes
    a `load_targets()` call, its helper invocations resolve under
    `${CLAUDE_PLUGIN_ROOT}` (rendered; the SOURCE spells it
    `{{PLUGIN_ROOT}}`), its Phase-3 tag-provenance step reads the row's
    `provenance-manifest` field, and its hosted-lane/immutability prose is
    conditional on what the consumer's own repo has. Reads the SURFACE
    SOURCE, never a generated payload (spec: "Source of truth")."""

    @classmethod
    def setUpClass(cls):
        cls.repo = os.path.dirname(os.path.dirname(HERE))
        path = os.path.join(
            cls.repo, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    # -- T-41a: table -> loader; no hardcoded row survives ------------------

    def test_skill_uses_loader(self):
        self.assertIn("load", self.text.lower())
        self.assertIn("declared file", self.text)
        self.assertIn("release-targets.md", self.text)
        # No hardcoded row survives: neither this repo's four target names,
        # nor any of its literal manifest/changelog/artifact paths, appear as
        # skill PROSE any longer (a bare filename with no directory qualifier,
        # e.g. `CHANGELOG.md`/`package.json` as a placeholder VALUE label,
        # remains fine and is not checked here).
        for literal in (
                "ca-codex", "ca-sandbox", "ca-pi",
                "plugins/ca/.claude-plugin/plugin.json",
                "plugins/ca-codex/.codex-plugin/plugin.json",
                "plugins/ca-sandbox/.claude-plugin/plugin.json",
                "plugins/ca-pi/package.json",
                "plugins/ca-codex/CHANGELOG.md",
                "plugins/ca-sandbox/CHANGELOG.md",
                "plugins/ca-pi/CHANGELOG.md",
                "plugins/ca/tools/farm.js",
                "plugins/ca-sandbox/tools/sandbox.js",
                "plugins/ca-sandbox/tools/claude-inside.js",
                "plugins/ca-pi/extensions/codearbiter.js",
                "plugins/ca-pi/extensions/codearbiter-child.js"):
            with self.subTest(literal=literal):
                self.assertNotIn(
                    literal, self.text,
                    f"a hardcoded row literal {literal!r} survives the "
                    "table -> loader rewrite")
        self.assertNotIn(
            "| `$TARGET` | `$TAG_PREFIX` |", self.text,
            "the old hardcoded Targets table header survives")

    def test_skill_uses_loader_field_names(self):
        # The row's own field vocabulary (grammar names, spec "File grammar")
        # must appear so an agent following the prose knows which key to read.
        for field in ("prefix", "manifest", "changelog", "payload",
                      "payload-exclude", "rebuild", "artifacts",
                      "provenance-manifest", "pre-tag", "latest-eligible",
                      "generated-manifest", "generate", "display-name"):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", self.text)

    # -- T-41b: helpers repoint under {{PLUGIN_ROOT}}; no .github/scripts/,
    #    and the four prose-only mentions no longer name a repo path --------

    def test_skill_helpers_repoint_under_plugin_root(self):
        self.assertNotIn(".github/scripts/", self.text)
        self.assertIn("{{PLUGIN_ROOT}}/hooks/_releaselib.py", self.text)

    def test_skill_no_longer_names_the_four_prose_only_scripts(self):
        # MEDIUM-4 (ratchet comment, known-unresolved-refs.txt): these four
        # were NAMED without being invoked, so a criterion about invocations
        # alone would never clear them. Reworded to a conditional CI
        # reference (AC-6.3 precedent) rather than a literal repo path.
        for script in ("check_badge_consistency.py", "check_tag_immutability.py",
                       "payload_scope.py", "test_release_lib.py"):
            with self.subTest(script=script):
                self.assertNotIn(script, self.text)
        # The ca-pi-specific root-manifest regeneration invocation is gone
        # entirely -- it is now DATA (a declared `pre-tag` command in this
        # repo's own release-targets.md), never skill prose.
        self.assertNotIn("tools/build-host-packages.py", self.text)

    # -- T-41c: Phase 3 provenance step reads the row field -----------------

    def test_skill_provenance_field(self):
        self.assertIn("provenance-manifest", self.text)
        self.assertIn("$PROVENANCE_MANIFEST", self.text)
        self.assertNotIn(".github/published-tags.json", self.text)
        # The absent-row-field skip must be documented explicitly in the
        # report, not silent (A-3.5).
        idx = self.text.index("Record the tag's provenance")
        window = self.text[idx:idx + 1200]
        self.assertIn("skips this step", window)
        self.assertIn("say so explicitly in the report", window)

    # -- T-41d: hosted-lane and immutability prose are conditional ----------

    def test_skill_conditional_prose(self):
        phase3_idx = self.text.index("## Phase 3")
        recovering_idx = self.text.index("## Recovering from a bad release")
        phase3_preamble = self.text[phase3_idx:phase3_idx + 900]
        recovering = self.text[recovering_idx:]

        self.assertIn("If this project has a hosted release workflow", phase3_preamble)
        self.assertIn("A project with no hosted workflow", phase3_preamble)

        self.assertIn("If this project runs an automated tag-immutability",
                       recovering)
        self.assertIn("A project with no such CI check", recovering)
        # This repo's own concrete CI check name/artifact must not survive as
        # an unconditional claim about every consumer's repo.
        self.assertNotIn("[CHECK] | [REPO] | Published tag immutability",
                          self.text)
        self.assertNotIn(".github/published-tags.json", self.text)
        self.assertNotIn("repository rulesets", self.text)

        # The doctrine itself must survive: immutable-tag rule, no
        # break-glass, correction-by-new-version, "manifest is the witness".
        self.assertIn("A published tag is immutable", recovering)
        self.assertIn("no break-glass", recovering.lower())
        self.assertIn("the manifest is the witness, not the suspect", recovering)
        for step_text in ("git push --force", "git push --delete",
                          "gh release delete", "gh release edit"):
            with self.subTest(step_text=step_text):
                self.assertIn(step_text, recovering)

    def test_skill_latest_is_row_driven(self):
        self.assertIn("latest-eligible", self.text)
        self.assertNotIn(
            "MUST NOT assert `--latest` for any target except `ca`", self.text)
        self.assertIn(
            "MUST NOT assert `--latest` for any target whose row does not "
            "declare `latest-eligible: true`", self.text)

    def test_skill_pre_tag_replaces_the_hardcoded_surface_sync(self):
        # The old per-target badge/root-manifest bullet list is gone; the
        # portable replacement is the row's declared `pre-tag` commands
        # (DECISION-0034), run in declared order with a BLOCK on non-zero.
        self.assertNotIn("the README version badge (`version-X.Y.Z`)", self.text)
        self.assertIn("pre-tag", self.text)
        self.assertIn("DECISION-0034", self.text)

    # -- T-49/T-50 (issue #563, A-5.3/A-5.4): the back-fill lane itself now
    #    exists (replacing the HIGH-1 canary from 2026-07-31, which asserted
    #    the ABSENCE of this prose and was written to be replaced, not
    #    loosened, the moment this landed — see BackfillSkillProseTest and
    #    test_consumer_smoke.py's two-arm proof). --------------------------

    def test_skill_names_the_backfill_lane_and_still_names_context_creation(self):
        self.assertIn("back-fill", self.text.lower())
        self.assertIn("context-creation", self.text)

    # -- HIGH-3 (adversarial review 2026-07-31): a manifest path that is
    #    GENERATED output is declarable, never hand-edited by this skill. --

    def test_skill_generated_manifest_is_never_hand_edited(self):
        self.assertIn("generated-manifest", self.text)
        # A bare `assertIn("generate", ...)` would pass on the substring
        # inside "generated-manifest"/"regenerate" alone and never actually
        # exercise the field-name reference — check the backticked field
        # name, the same way test_skill_uses_loader_field_names does.
        self.assertIn("`generate`", self.text)
        self.assertIn("never hand-edited", self.text)
        self.assertIn("MUST NOT hand-edit a path also listed in "
                       "`$GENERATED_MANIFEST`", self.text)

    # -- M-1 (adversarial review 2026-07-31): the Release title convention
    #    names a "display name" no grammar key ever supplied. -------------

    def test_skill_release_title_uses_a_declared_display_name(self):
        self.assertIn("display-name", self.text)
        self.assertIn(
            "The title convention is `<$DISPLAY_NAME> MAJOR.MINOR.PATCH: "
            "<summary>`", self.text)
        self.assertNotIn("<$TARGET display name>", self.text)

    # -- M-2 (adversarial review 2026-07-31): the command and a hosted
    #    lane reading "the same declared file" is false until slice 4
    #    (T-43-T-46) repoints the workflow/gate off hardcoded constants;
    #    the claim must be conditional on that, not asserted outright. ----

    def test_skill_tag_prefix_agreement_with_a_hosted_lane_is_conditional(self):
        self.assertNotIn(
            "the same declared file a hosted publish lane (if this project "
            "has one) reads, so the command and the lane cannot disagree",
            self.text)
        idx = self.text.index("Resolve `$TAG_PREFIX`")
        window = self.text[idx:idx + 700]
        self.assertIn("is ALSO wired to read this declared file", window)
        self.assertIn("the two can drift", window)

    # -- Portability guard proxy (T-41b's own criterion; the guard SCRIPT
    #    that will enforce this mechanically, check_skill_portability.py, is
    #    T-68a/T-68b's own deliverable and is deliberately NOT authored here
    #    -- see the plan's dependency order). This is the honest local
    #    equivalent until then. --------------------------------------------

    def test_no_github_scripts_invocation_remains_in_the_source(self):
        self.assertNotIn(".github/scripts/", self.text)

    def test_generated_payloads_carry_no_github_scripts_reference(self):
        # The source-only assertions above prove the SOURCE is clean, but
        # `tools/build-surface.py --check` only proves the generator is
        # IDEMPOTENT, not that what it rendered is free of `.github/scripts/`
        # -- and `test_consumer_smoke.py`'s reference-resolution ratchet,
        # which is the suite that would otherwise catch a payload-rendering
        # regression, reads `git archive HEAD` and is blind to an uncommitted
        # change. This is the one thing in this repo's GREEN, re-runnable
        # test surface that actually reads the three full generated copies
        # (`ca`, the `ca-codex`/`ca-pi` "routines" copies) rather than only
        # the surface source or a stale committed snapshot.
        payloads = (
            ("ca", os.path.join("plugins", "ca", "skills", "release", "SKILL.md")),
            ("ca-codex", os.path.join(
                "plugins", "ca-codex", "routines", "release", "SKILL.md")),
            ("ca-pi", os.path.join(
                "plugins", "ca-pi", "routines", "release", "SKILL.md")),
        )
        host_plugin_root_token = {"ca": "claude", "ca-codex": "codex", "ca-pi": "pi"}
        hosts_json_path = os.path.join(self.repo, "core", "hosts.json")
        with open(hosts_json_path, encoding="utf-8") as fh:
            hosts_data = json.load(fh)
        tokens_by_host = {
            host["name"]: host["tokens"]["PLUGIN_ROOT"] for host in hosts_data["hosts"]
        }
        for label, relpath in payloads:
            with self.subTest(payload=label):
                path = os.path.join(self.repo, relpath)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                self.assertNotIn(
                    ".github/scripts/", text,
                    f"{label!r}'s generated release skill still carries a "
                    ".github/scripts/ invocation")
                plugin_token = tokens_by_host[host_plugin_root_token[label]]
                self.assertIn(
                    f"{plugin_token}/hooks/_releaselib.py", text,
                    f"{label!r}'s generated release skill does not resolve "
                    f"its helper invocations under its own host's "
                    f"plugin-root token ({plugin_token!r})")



class LastTagPerSeriesTest(unittest.TestCase):
    """#382: `LAST_TAG` has to resolve for whichever plugin is being released.

    Before this, `last_tag_select` matched `^vMAJOR.MINOR.PATCH` only, so it
    could answer for `ca` and for nothing else - which is why the release command
    could only ever target `ca`. Series isolation is a property of the ANCHORED
    match rather than an exclusion list: a fifth plugin cannot leak into an
    existing series by being forgotten somewhere."""

    TAGS = ["v2.9.1", "v2.10.0", "ca-pi-v0.1.30", "ca-pi-v0.1.9",
            "ca-sandbox-v0.1.3", "ca-codex-v0.3.0", "v3.0.0-beta.1"]

    def test_the_prefix_register_covers_exactly_the_release_targets(self):
        self.assertEqual(tuple(_releaselib.release_tag_prefixes()),
                         _releaselib.RELEASE_TARGETS,
                         "every releasable target needs a tag namespace, and no"
                         " namespace may exist for a target that cannot release")

    def test_every_series_resolves_its_own_highest_tag(self):
        expected = {
            "ca": "v2.10.0",
            "ca-codex": "ca-codex-v0.3.0",
            "ca-sandbox": "ca-sandbox-v0.1.3",
            "ca-pi": "ca-pi-v0.1.30",
        }
        for target, prefix in _releaselib.release_tag_prefixes().items():
            with self.subTest(target=target):
                self.assertEqual(_releaselib.last_tag_select(self.TAGS, prefix),
                                 expected[target])

    def test_no_series_resolves_another_series_tag(self):
        # The defect this prevents: basing an entire release on another plugin's
        # baseline, which `git describe --tags` does by commit-graph ancestry.
        for target, prefix in _releaselib.release_tag_prefixes().items():
            with self.subTest(target=target):
                chosen = _releaselib.last_tag_select(self.TAGS, prefix)
                self.assertTrue(chosen.startswith(prefix), chosen)
                for other, other_prefix in _releaselib.release_tag_prefixes().items():
                    if other == target or not other_prefix.startswith(prefix):
                        continue
                    self.assertFalse(
                        chosen.startswith(other_prefix),
                        f"{target} resolved {other}'s tag {chosen!r}")

    def test_ca_does_not_pick_up_a_namespaced_sibling(self):
        # `^v` must not match `ca-pi-v0.1.30`. This is the whole reason the
        # sibling series are prefixed rather than bare.
        self.assertEqual(
            _releaselib.last_tag_select(["ca-pi-v9.9.9", "ca-sandbox-v9.9.9"], "v"),
            _releaselib.NONE_SENTINEL)

    def test_the_default_series_is_ca_so_existing_callers_are_unchanged(self):
        self.assertEqual(_releaselib.last_tag_select(self.TAGS),
                         _releaselib.last_tag_select(self.TAGS, "v"))

    def test_a_series_with_no_release_yet_is_the_none_sentinel(self):
        # ca-pi's real state until #382 gave it a lane: guards existed, tags did not.
        self.assertEqual(_releaselib.last_tag_select(["v1.0.0"], "ca-pi-v"),
                         _releaselib.NONE_SENTINEL)

    def test_prereleases_are_excluded_in_every_series(self):
        for prefix in _releaselib.release_tag_prefixes().values():
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    _releaselib.last_tag_select(
                        [f"{prefix}1.0.0-beta.1", f"{prefix}1.0.0-rc.2",
                         f"{prefix}1.0.0-alpha"], prefix),
                    _releaselib.NONE_SENTINEL)

    def test_a_missing_or_empty_prefix_resolves_nothing(self):
        # Fail-closed: an unusable series must not silently fall back to ca's.
        for bad in ("", None, 42):
            with self.subTest(prefix=bad):
                self.assertEqual(_releaselib.last_tag_select(self.TAGS, bad),
                                 _releaselib.NONE_SENTINEL)

    def test_the_cli_answers_for_a_named_series_and_defaults_to_ca(self):
        import io
        import contextlib
        for args, expected in ((["last-tag"], "v2.10.0"),
                               (["last-tag", "ca-pi-v"], "ca-pi-v0.1.30")):
            with self.subTest(args=args):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    stdin = sys.stdin
                    sys.stdin = io.StringIO(" ".join(self.TAGS))
                    try:
                        rc = _releaselib.main(args)
                    finally:
                        sys.stdin = stdin
                self.assertEqual(rc, 0)
                self.assertEqual(out.getvalue().strip(), expected)

    def test_the_cli_exposes_the_namespace_lookup(self):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = _releaselib.main(["tag-prefix", "ca-sandbox"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "ca-sandbox-v")

    def test_the_cli_refuses_an_unknown_target(self):
        import io
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = _releaselib.main(["tag-prefix", "ca-nope"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown release target", err.getvalue())


class NotesHeadingNamespacedTagTest(unittest.TestCase):
    """#493's sibling lanes abort at the notes guard, on every dispatch.

    `_bare_version` stripped only a LEADING "v" (`tag.lstrip("v")`), which is
    right for ca's bare `v2.9.1` and wrong for every namespaced sibling:
    `"ca-pi-v0.1.31".lstrip("v")` is unchanged, so it never equals the `0.1.31`
    parsed out of the changelog heading.

    The hosted publish action runs

        python3 .github/scripts/_releaselib.py notes-match "$TAG" notes.md

    and a non-zero exit STOPS the publish. So the ca-codex, ca-sandbox and ca-pi
    lanes added by #382 could never have completed a release - they would have
    aborted at this guard every time, on a correct changelog. Undetected because
    the lanes had never been dispatched and every existing test here used a bare
    `v` tag."""

    def _notes(self, version):
        return f"## [{version}] - 2026-07-26\n\n### Added\n\n- a thing\n"

    def test_every_release_series_matches_its_own_notes(self):
        for target, prefix in _releaselib.release_tag_prefixes().items():
            version = "1.2.3"
            with self.subTest(target=target):
                self.assertTrue(
                    _releaselib.notes_heading_matches(
                        self._notes(version), f"{prefix}{version}"),
                    f"{target}: a correct changelog must satisfy its own tag")

    def test_a_namespaced_tag_still_rejects_the_wrong_section(self):
        # The guard must keep its actual job: a stale notes file publishes the
        # wrong changelog section under the right tag.
        self.assertFalse(
            _releaselib.notes_heading_matches(self._notes("0.1.30"), "ca-pi-v0.1.31"))
        self.assertFalse(
            _releaselib.notes_heading_matches(self._notes("1.0.0"), "ca-sandbox-v2.0.0"))

    def test_one_series_does_not_satisfy_another(self):
        # `ca-pi-v1.2.3` and `ca-sandbox-v1.2.3` share a version. The guard
        # compares VERSIONS, so both match a 1.2.3 section - which is correct:
        # the tag namespace is enforced by the lane that chose it, not here.
        # Pinned so a future "strip the prefix" change cannot quietly start
        # rejecting a legitimate release.
        notes = self._notes("1.2.3")
        self.assertTrue(_releaselib.notes_heading_matches(notes, "ca-pi-v1.2.3"))
        self.assertTrue(_releaselib.notes_heading_matches(notes, "ca-sandbox-v1.2.3"))

    def test_bare_version_extracts_the_semver_from_any_spelling(self):
        cases = {
            "v2.6.0": "2.6.0",
            "2.6.0": "2.6.0",
            "[2.6.0]": "2.6.0",
            "ca-pi-v0.1.31": "0.1.31",
            "ca-codex-v0.3.0": "0.3.0",
            "ca-sandbox-v0.1.5": "0.1.5",
        }
        for spelling, want in cases.items():
            with self.subTest(spelling=spelling):
                self.assertEqual(_releaselib._bare_version(spelling), want)


class ShimReexportCompletenessTest(unittest.TestCase):
    """The shim must re-export every name ANY consumer imports, not just the
    names the tests happen to use.

    This exists because of a real regression. The first shim conversion
    re-exported `semver_key` and `semver_greater` but dropped `SEMVER`, which
    `tools/build-host-packages.py` imports. Nothing failed: the whole suite
    stayed green, because no test imported `SEMVER`. The re-export surface was
    covered for the names the tests use rather than the names consumers use,
    and the break only surfaced when a declared `pre-tag` command ran it.

    The required set is DERIVED by scanning the repo, never restated here. A
    hand-maintained list would reproduce the same defect the moment someone
    adds an import without updating it.
    """

    _IMPORT_RE = re.compile(r"^\s*from\s+_releaselib\s+import\s+(.+)$", re.M)

    def _required_names(self):
        roots = [os.path.join(REPO_ROOT, ".github", "scripts"),
                 os.path.join(REPO_ROOT, "tools")]
        required = {}
        for root in roots:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root)):
                if not entry.endswith(".py"):
                    continue
                path = os.path.join(root, entry)
                with io.open(path, encoding="utf-8") as handle:
                    text = handle.read()
                for clause in self._IMPORT_RE.findall(text):
                    clause = clause.split("#", 1)[0]
                    for raw in clause.split(","):
                        name = raw.strip().split(" as ")[0].strip()
                        if name and name.isidentifier():
                            required.setdefault(name, []).append(entry)
        return required

    def test_the_scan_finds_real_consumers(self):
        """Guard the guard: an empty or trivial scan would make the next test
        vacuously pass, which is exactly how the original defect survived."""
        required = self._required_names()
        self.assertGreaterEqual(
            len(required), 3,
            "the import scan found almost nothing, so the completeness check "
            "below would pass without measuring anything: %r" % (required,))

    def test_shim_reexports_every_name_any_consumer_imports(self):
        required = self._required_names()
        missing = {n: v for n, v in sorted(required.items())
                   if not hasattr(_releaselib, n)}
        self.assertEqual(
            missing, {},
            "the shim does not export every name its consumers import. Each "
            "entry maps a missing name to the files importing it; a consumer "
            "importing it will fail at module load: %r" % (missing,))


class ReleaselibShimTest(unittest.TestCase):
    """The shim (`.github/scripts/_releaselib.py`, imported above as
    `_releaselib`) must be a thin RE-EXPORT of the portable mechanism
    (`core_releaselib`), not a second implementation.

    A-1.9's TRANSITIONAL clause is RETIRED here, as A-4.4 requires in the
    same commit that removes the constants. That clause said "no commit may
    leave RELEASE_TAG_PREFIXES unimportable from this module" -- a rule that
    existed only to keep consumers working while the data still lived here.
    T-46 removed the literal (payload_version_gate.py derives its own map,
    nothing else consumed it), so the rule now protects nothing and would
    forbid the very change it was written to enable."""

    def test_releaselib_shim_exports_constants(self):
        # payload_version_gate.py:53 imports exactly these three names from
        # this shim at module load; they must still resolve.
        self.assertEqual(_releaselib.release_tag_prefixes(),
                          {"ca": "v", "ca-codex": "ca-codex-v",
                           "ca-sandbox": "ca-sandbox-v", "ca-pi": "ca-pi-v"})
        self.assertTrue(callable(_releaselib.semver_greater))
        self.assertTrue(callable(_releaselib.semver_key))

    def test_shim_error_hierarchy_is_the_portable_modules_not_a_duplicate(self):
        # A duplicate hierarchy would let the two modules' exceptions
        # silently diverge: a caller catching the shim's ReleaseTargetsError
        # would not catch one raised by core/pysrc/_releaselib.py, and vice
        # versa. `inspect.getsourcefile` -- rather than `assertIs` -- is the
        # right proof here: the shim loads its own copy of the mechanism
        # module under a private name (`_release_mechanism`), so its classes
        # are never the SAME objects as this test's own independently-loaded
        # `core_releaselib` (a second, distinct exec of the same file).
        # Source-file identity is what "re-exported, not reimplemented"
        # actually means; a hand-written duplicate hierarchy inside the shim
        # itself would report the SHIM's own path here, not the core one.
        self.assertEqual(
            inspect.getsourcefile(_releaselib.AbsentBlockError), _CORE_RELEASELIB_PATH)
        self.assertEqual(
            inspect.getsourcefile(_releaselib.ReleaseTargetsError), _CORE_RELEASELIB_PATH)
        self.assertEqual(
            inspect.getsourcefile(_releaselib.MissingRequiredKeyError),
            _CORE_RELEASELIB_PATH)

    # M-3 (adversarial review, 2026-07-31): the 3-name spot-check above
    # proves PROVENANCE (the class comes from the core file) but not
    # IDENTITY (it is the RIGHT class from that file) -- a swap bug like
    # `AbsentBlockError = _mechanism.MalformedBlockError` inside the shim
    # would still pass every assertion above unchanged, since both classes
    # live in the same core file. Enumerated explicitly, all 11 names.
    _EXCEPTION_NAMES = (
        "ReleaseTargetsError", "AbsentBlockError", "EmptyBlockError",
        "MalformedBlockError", "UnknownKeyError", "DuplicateKeyError",
        "DuplicateTargetError", "InvalidBooleanError", "MultipleBlocksError",
        "DelimiterInValueError", "MissingRequiredKeyError",
        "FileExistsNoBlockError",
    )

    def test_shim_exception_names_are_not_silently_swapped(self):
        # `__name__` is set at CLASS-DEFINITION time in the core module and
        # is independent of whichever shim-level variable currently holds a
        # reference to it -- so a swap (the shim name binds to the WRONG
        # core class) shows up here even though `inspect.getsourcefile`
        # alone cannot see it (both classes share one file). Paired with the
        # existing source-file check and `issubclass`, this closes both
        # directions the review named: a same-file swap (caught by
        # `__name__`) and a hand-written duplicate under the right name
        # (caught by `getsourcefile`).
        for name in self._EXCEPTION_NAMES:
            with self.subTest(name=name):
                cls = getattr(_releaselib, name)
                self.assertEqual(cls.__name__, name)
                self.assertEqual(inspect.getsourcefile(cls), _CORE_RELEASELIB_PATH)
                self.assertTrue(issubclass(cls, _releaselib.ReleaseTargetsError))

    def test_shim_mechanism_functions_are_the_portable_modules_not_a_duplicate(self):
        # Same reasoning as the error-hierarchy test above, applied to every
        # non-defaulted mechanism function: each must be DEFINED in
        # core/pysrc/_releaselib.py, never reimplemented in the shim. (The
        # three wrapped functions -- last_tag_select, select_release_target,
        # classify_merge_readiness -- restore this repo's OLD default
        # arguments and so are legitimately NEW, thin functions defined in
        # the shim itself; they are covered by the wrapper test below, not
        # here.)
        for fn in (_releaselib.semver_key, _releaselib.semver_greater,
                   _releaselib.notes_heading_matches,
                   _releaselib.release_dates_consistent,
                   _releaselib.classify_publish_state, _releaselib.peel_tag,
                   _releaselib.load_targets, _releaselib.parse_release_targets):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(inspect.getsourcefile(fn), _CORE_RELEASELIB_PATH)

    def test_shim_wrapped_functions_restore_the_old_default_arguments(self):
        # last_tag_select, select_release_target, and classify_merge_readiness
        # now REQUIRE, in the portable module, the argument that used to
        # default (A-1.3). The shim's own wrappers must still work with no
        # argument, exactly as every existing caller invokes them.
        self.assertEqual(_releaselib.last_tag_select(["v1.0.0"]), "v1.0.0")
        self.assertEqual(
            _releaselib.select_release_target("1.0.0", "", "", ""), "ca")
        self.assertEqual(
            _releaselib.classify_merge_readiness(
                [{"name": _releaselib.MERGE_READINESS_CHECK, "head_sha": "a" * 40,
                  "status": "completed", "conclusion": "success"}], "a" * 40),
            "green")

    def test_shim_resolves_the_mechanism_regardless_of_cwd(self):
        # The whole point of locating the mechanism via this file's own
        # __file__ rather than the process cwd (mirroring
        # payload_version_gate.py's own REPO resolution): invoking the CLI
        # from a directory with no relationship to this repo must not break
        # the import. A cwd-dependent relative lookup would fail here.
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as elsewhere:
            result = subprocess.run(
                [sys.executable, os.path.join(HERE, "_releaselib.py"), "last-tag"],
                cwd=elsewhere, input="v1.0.0\nv1.1.0\n",
                capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "v1.1.0"))

    def test_payload_version_gate_imports_and_runs_unchanged(self):
        # The load-bearing consumer (payload_version_gate.py:53) does
        # `from _releaselib import RELEASE_TAG_PREFIXES, semver_greater,
        # semver_key` at module load. This used to shell out to the gate CLI
        # with `--base origin/main`, but the hooks job's checkout has no
        # `fetch-depth: 0` and never fetches `origin/main`, so that
        # subprocess correctly returned FAIL (exit 1) there for a reason that
        # has nothing to do with this shim (HIGH-3). It also duplicated the
        # `version-bump-ca` gate's verdict under a different trigger set,
        # coupling this shim's own test to this repo's release/payload state.
        #
        # A plain in-process `import` exercises the EXACT statement the
        # consumer runs, in the same interpreter this test file is already
        # running in (`sys.path.insert(0, HERE)` above puts `.github/scripts`
        # first, exactly where `payload_version_gate.py` itself inserts it).
        # `from … import` binds names to the SAME objects the module-level
        # `_releaselib` import at the top of this file already produced, so
        # `assertIs` is a genuine identity proof of the shim/consumer wiring
        # — no git, no network, no repo release-state dependency at all.
        import payload_version_gate  # noqa: E402 — needs sys.path mutation above
        # Repointed for A-4.1/T-43: the gate stopped importing
        # RELEASE_TAG_PREFIXES and now derives every namespace from the
        # declared file. The test's PURPOSE is unchanged — it proves the
        # gate's names bind to the shim's own objects — so it follows the
        # import list rather than being deleted. Retiring it outright
        # belongs to T-46, which removes the data constants themselves.
        self.assertIs(payload_version_gate.load_targets, _releaselib.load_targets)
        self.assertIs(payload_version_gate.semver_greater, _releaselib.semver_greater)
        self.assertIs(payload_version_gate.semver_key, _releaselib.semver_key)
        # And the constant is genuinely no longer reachable through the gate,
        # so a silent re-import cannot pass this test by accident.
        self.assertFalse(hasattr(payload_version_gate, "RELEASE_TAG_PREFIXES"))

    def test_bare_invocation_exits_2(self):
        # Argparse's own required-argument failure, not a crash -- the args
        # are required, so a bare invocation must refuse rather than guess.
        # In-process (`main([])` raises SystemExit before any git call is
        # made, so this never depended on repo state) rather than a 120s-
        # timeout subprocess with its own cwd dependency.
        import payload_version_gate
        with self.assertRaises(SystemExit) as ctx:
            payload_version_gate.main([])
        self.assertEqual(ctx.exception.code, 2)


class DenylistTest(unittest.TestCase):
    """A-1.2: the portable mechanism (core/pysrc/_releaselib.py) must carry no
    literal from this repository's namespace or CI vocabulary. `.github/
    scripts/_releaselib.py` (imported above as `_releaselib`) is EXEMPT — it
    still carries this repo's own MERGE_READINESS_CHECK (a CI check-run
    name, which the declared file has no field for) and is deliberately not
    scanned here."""

    DENYLIST = (
        "[REPO]", "ca-pi", "ca-codex", "ca-sandbox", "plugins/",
        "RELEASE_TAG_PREFIXES", "RELEASE_TARGETS",
    )

    @classmethod
    def setUpClass(cls):
        with open(_CORE_RELEASELIB_PATH, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_denylist_has_no_repo_namespace_or_ci_vocabulary_literal(self):
        for token in self.DENYLIST:
            with self.subTest(token=token):
                self.assertNotIn(
                    token, self.text,
                    f"core/pysrc/_releaselib.py must not contain the "
                    f"repo-specific literal {token!r}")


class RequiredParamsTest(unittest.TestCase):
    """A-1.3: repo-specific defaults became required parameters, so no
    module-global fact can survive to detonate later. Each of the three
    functions must reject a call missing the argument that used to default."""

    def test_required_params_classify_merge_readiness_requires_check_name(self):
        with self.assertRaises(TypeError):
            core_releaselib.classify_merge_readiness([], "a" * 40)

    def test_required_params_last_tag_select_requires_prefix(self):
        with self.assertRaises(TypeError):
            core_releaselib.last_tag_select(["v1.0.0"])

    def test_required_params_select_release_target_requires_targets(self):
        with self.assertRaises(TypeError):
            core_releaselib.select_release_target("1.0.0", "")

    def test_required_params_still_work_when_supplied(self):
        # Non-regression: removing the default must not have broken the
        # happy path, only removed the silent fallback.
        self.assertEqual(
            core_releaselib.last_tag_select(["v1.0.0"], "v"), "v1.0.0")
        self.assertEqual(
            core_releaselib.classify_merge_readiness(
                [{"name": "gate", "head_sha": "a" * 40, "status": "completed",
                  "conclusion": "success"}], "a" * 40, "gate"),
            "green")
        self.assertEqual(
            core_releaselib.select_release_target(
                "1.0.0", "", targets=["app", "lib"]),
            "app")


class LoadTargetsTest(unittest.TestCase):
    """A-1.4: load_targets(path) returns rows carrying the full declared
    schema, reading a real file from disk (stdlib only)."""

    FIXTURE = (
        "prose before the block is ignored\n\n"
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "display-name: My App\n"
        "manifest: package.json\n"
        "manifest: nested/package.json\n"
        "generated-manifest: nested/package.json\n"
        "generate: node scripts/regen-nested-manifest.js\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "payload-exclude: tools/\n"
        "rebuild: npm run build\n"
        "artifacts: dist/bundle.js\n"
        "artifacts: dist/bundle.min.js\n"
        "provenance-manifest: .well-known/published-tags.json\n"
        "latest-eligible: true\n"
        "pre-tag: npm run lint\n"
        "pre-tag: npm run typecheck\n"
        "<!-- /release-targets -->\n"
        "prose after the block is ignored\n"
    )

    def _write_fixture(self, tmp_path_dir, text=None):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".md", dir=tmp_path_dir)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text if text is not None else self.FIXTURE)
        return path

    def test_load_targets_returns_the_full_row_schema(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_fixture(tmp)
            rows = core_releaselib.load_targets(path)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["target"], "app")
        self.assertEqual(row["prefix"], "v")
        self.assertEqual(row["display_name"], "My App")
        self.assertEqual(row["manifest"], ["package.json", "nested/package.json"])
        self.assertEqual(row["generated_manifest"], ["nested/package.json"])
        self.assertEqual(row["generate"], "node scripts/regen-nested-manifest.js")
        self.assertEqual(row["changelog"], "CHANGELOG.md")
        self.assertEqual(row["payload"], ".")
        self.assertEqual(row["payload_exclude"], ["tools/"])
        self.assertEqual(row["rebuild"], "npm run build")
        self.assertEqual(row["artifacts"], ["dist/bundle.js", "dist/bundle.min.js"])
        self.assertEqual(row["provenance_manifest"], ".well-known/published-tags.json")
        self.assertEqual(row["pre_tag"], ["npm run lint", "npm run typecheck"])
        self.assertIs(row["latest_eligible"], True)

    def test_load_targets_minimal_row_has_documented_defaults(self):
        text = ("<!-- release-targets -->\n"
                "[app]\n"
                "prefix: v\n"
                "changelog: CHANGELOG.md\n"
                "payload: .\n"
                "<!-- /release-targets -->\n")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_fixture(tmp, text)
            rows = core_releaselib.load_targets(path)
        row = rows[0]
        self.assertIsNone(row["display_name"])
        self.assertEqual(row["manifest"], [])
        self.assertEqual(row["generated_manifest"], [])
        self.assertIsNone(row["generate"])
        self.assertEqual(row["payload_exclude"], [])
        self.assertIsNone(row["rebuild"])
        self.assertEqual(row["artifacts"], [])
        self.assertIsNone(row["provenance_manifest"])
        self.assertEqual(row["pre_tag"], [])
        self.assertIs(row["latest_eligible"], False)

    def test_load_targets_multiple_targets_all_load(self):
        text = ("<!-- release-targets -->\n"
                "[one]\n"
                "prefix: one-v\n"
                "changelog: CHANGELOG.md\n"
                "payload: .\n"
                "\n"
                "[two]\n"
                "prefix: two-v\n"
                "changelog: two/CHANGELOG.md\n"
                "payload: two/\n"
                "<!-- /release-targets -->\n")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_fixture(tmp, text)
            rows = core_releaselib.load_targets(path)
        self.assertEqual([row["target"] for row in rows], ["one", "two"])


class AbsentBlockTest(unittest.TestCase):
    """A-1.5: an absent delimiter block raises a distinguishable declared
    error, never a silent empty result."""

    def test_no_delimiter_at_all_raises_absent_block_error(self):
        with self.assertRaises(core_releaselib.AbsentBlockError):
            core_releaselib.parse_release_targets("just some prose, no block\n")

    def test_empty_string_raises_absent_block_error(self):
        with self.assertRaises(core_releaselib.AbsentBlockError):
            core_releaselib.parse_release_targets("")

    def test_absent_block_error_is_a_release_targets_error(self):
        # Callers that only need the broad category can catch the base class.
        self.assertTrue(
            issubclass(core_releaselib.AbsentBlockError,
                       core_releaselib.ReleaseTargetsError))


class EmptyBlockTest(unittest.TestCase):
    """A-1.7: a present-but-empty delimiter block raises a distinguishable
    declared error, distinct from AbsentBlockError."""

    def test_whitespace_only_block_raises_empty_block_error(self):
        text = "<!-- release-targets -->\n   \n\n<!-- /release-targets -->\n"
        with self.assertRaises(core_releaselib.EmptyBlockError):
            core_releaselib.parse_release_targets(text)

    def test_zero_byte_block_raises_empty_block_error(self):
        text = "<!-- release-targets --><!-- /release-targets -->"
        with self.assertRaises(core_releaselib.EmptyBlockError):
            core_releaselib.parse_release_targets(text)

    def test_empty_block_error_is_distinct_from_absent_block_error(self):
        self.assertFalse(
            issubclass(core_releaselib.EmptyBlockError,
                       core_releaselib.AbsentBlockError))
        self.assertFalse(
            issubclass(core_releaselib.AbsentBlockError,
                       core_releaselib.EmptyBlockError))


class FileExistsNoBlockTest(unittest.TestCase):
    """HIGH-1 (adversarial review 2026-07-31): an EXISTING declared-target
    file that carries no delimiter block at all must raise a DIFFERENT,
    distinguishable error than a genuinely ABSENT file -- the release
    skill's Back-fill lane triggers on `AbsentBlockError` alone, and
    treating "exists but no block" as the same case would make the lane
    silently overwrite an operator's own existing (bad) file. Only
    `load_targets` can make this distinction (it is the one function that
    knows whether `open()` succeeded); `parse_release_targets` sees text
    only and is UNCHANGED -- it keeps raising `AbsentBlockError` for a
    blockless string, proven by `AbsentBlockTest` above, which this class
    must not weaken."""

    def test_existing_file_with_no_block_raises_file_exists_no_block_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("just some prose, no block at all\n")
            with self.assertRaises(core_releaselib.FileExistsNoBlockError):
                core_releaselib.load_targets(path)

    def test_genuinely_missing_file_still_raises_absent_block_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "does-not-exist.md")
            with self.assertRaises(core_releaselib.AbsentBlockError):
                core_releaselib.load_targets(path)

    def test_existing_no_block_is_never_caught_by_except_absent_block_error(self):
        # The exact hazard HIGH-1 names: a caller written BEFORE this class
        # existed, with `except AbsentBlockError:` as its Back-fill trigger,
        # must not accidentally widen to catch the existing-file case too.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("no block here either\n")
            caught_as_absent = False
            try:
                try:
                    core_releaselib.load_targets(path)
                except core_releaselib.AbsentBlockError:
                    caught_as_absent = True
            except core_releaselib.FileExistsNoBlockError:
                pass
            self.assertFalse(
                caught_as_absent,
                "an existing-but-blockless file must never be caught by "
                "`except AbsentBlockError:` -- that is the Back-fill "
                "lane's genuinely-absent-only trigger")

    def test_file_exists_no_block_error_is_a_sibling_not_a_subclass(self):
        # Deliberately NOT `issubclass(FileExistsNoBlockError,
        # AbsentBlockError)` in either direction -- both are siblings under
        # ReleaseTargetsError, so a pre-existing `except AbsentBlockError`
        # clause's behavior is unchanged by this class's addition.
        self.assertFalse(
            issubclass(core_releaselib.FileExistsNoBlockError,
                       core_releaselib.AbsentBlockError))
        self.assertFalse(
            issubclass(core_releaselib.AbsentBlockError,
                       core_releaselib.FileExistsNoBlockError))
        self.assertTrue(
            issubclass(core_releaselib.FileExistsNoBlockError,
                       core_releaselib.ReleaseTargetsError))

    def test_parse_release_targets_on_synthetic_text_is_unchanged(self):
        # parse_release_targets has no file to have opened, so a blockless
        # STRING still raises the ORIGINAL AbsentBlockError -- this class
        # must not weaken AbsentBlockTest's existing proof.
        with self.assertRaises(core_releaselib.AbsentBlockError):
            core_releaselib.parse_release_targets("just prose, no block\n")


class ParserContractTest(unittest.TestCase):
    """A-1.6: each parser-contract violation raises its own distinguishable
    declared error. Eight cases, matching the spec's enumeration: malformed
    block, CRLF-bearing boolean (correct-parse case, not an error), non-
    boolean boolean, duplicate scalar key, duplicate target block, unknown
    key, multiple delimiter blocks, delimiter-in-value."""

    VALID_HEADER = ("<!-- release-targets -->\n"
                     "[app]\n"
                     "prefix: v\n"
                     "changelog: CHANGELOG.md\n"
                     "payload: .\n")
    CLOSE = "<!-- /release-targets -->\n"

    def test_parser_contract_malformed_block_empty_header(self):
        text = ("<!-- release-targets -->\n[]\nprefix: v\n"
                "changelog: CHANGELOG.md\npayload: .\n" + self.CLOSE)
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_malformed_block_header_bad_characters(self):
        text = ("<!-- release-targets -->\n[app name!]\nprefix: v\n"
                "changelog: CHANGELOG.md\npayload: .\n" + self.CLOSE)
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_malformed_block_key_before_first_header(self):
        text = ("<!-- release-targets -->\n"
                "prefix: v\n[app]\nchangelog: CHANGELOG.md\npayload: .\n"
                + self.CLOSE)
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_crlf_bearing_boolean_parses_as_the_boolean_not_an_error(self):
        # This repo has documented LF->CRLF drift from editing on Windows. A
        # naive parser would turn "latest-eligible: true\r" into a value that
        # is not "true" and either silently drop the flag or raise the wrong
        # error. The trailing \r must be stripped BEFORE the boolean check.
        text = ("<!-- release-targets -->\r\n[app]\r\nprefix: v\r\n"
                "changelog: CHANGELOG.md\r\npayload: .\r\n"
                "latest-eligible: true\r\n"
                "<!-- /release-targets -->\r\n")
        rows = core_releaselib.parse_release_targets(text)
        self.assertIs(rows[0]["latest_eligible"], True)

    def test_parser_contract_non_boolean_boolean_raises_invalid_boolean_error(self):
        text = self.VALID_HEADER + "latest-eligible: yes\n" + self.CLOSE
        with self.assertRaises(core_releaselib.InvalidBooleanError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_duplicate_scalar_key_raises_duplicate_key_error(self):
        text = self.VALID_HEADER + "prefix: w\n" + self.CLOSE
        with self.assertRaises(core_releaselib.DuplicateKeyError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_list_keys_repeat_without_error(self):
        # Non-regression: manifest/artifacts/pre-tag/payload-exclude are
        # explicitly NOT subject to the duplicate-scalar-key rule.
        text = (self.VALID_HEADER + "manifest: a.json\nmanifest: b.json\n"
                + self.CLOSE)
        rows = core_releaselib.parse_release_targets(text)
        self.assertEqual(rows[0]["manifest"], ["a.json", "b.json"])

    def test_parser_contract_generated_manifest_repeats_without_error(self):
        # HIGH-3: generated-manifest is a list key too, same as manifest.
        text = (self.VALID_HEADER
                + "manifest: a.json\nmanifest: b.json\n"
                + "generated-manifest: a.json\ngenerated-manifest: b.json\n"
                + self.CLOSE)
        rows = core_releaselib.parse_release_targets(text)
        self.assertEqual(rows[0]["generated_manifest"], ["a.json", "b.json"])

    def test_parser_contract_duplicate_target_block_raises_duplicate_target_error(self):
        text = (self.VALID_HEADER + "[app]\nprefix: w\n"
                "changelog: CHANGELOG.md\npayload: .\n" + self.CLOSE)
        with self.assertRaises(core_releaselib.DuplicateTargetError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_unknown_key_raises_unknown_key_error(self):
        text = self.VALID_HEADER + "latest-eligibile: true\n" + self.CLOSE
        with self.assertRaises(core_releaselib.UnknownKeyError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_multiple_delimiter_blocks_raises_multiple_blocks_error(self):
        text = (self.VALID_HEADER + self.CLOSE + "\nmore prose\n\n"
                + self.VALID_HEADER + self.CLOSE)
        with self.assertRaises(core_releaselib.MultipleBlocksError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_delimiter_in_value_raises_delimiter_in_value_error(self):
        # A value that literally contains the closing delimiter must not
        # silently truncate the block under a non-greedy match.
        text = (self.VALID_HEADER
                + "rebuild: echo '<!-- /release-targets -->'\n" + self.CLOSE)
        with self.assertRaises(core_releaselib.DelimiterInValueError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_missing_required_key_raises_missing_required_key_error(self):
        # M3: previously untested — gutting _finish_row's check, or shrinking
        # _REQUIRED_KEYS to one entry, both left the suite green. Each of the
        # three required keys is dropped in its own fixture so a shrink of
        # _REQUIRED_KEYS to any single remaining entry is still caught,
        # rather than only a shrink that happens to keep the one key this
        # class's fixtures omit.
        cases = {
            "prefix": "changelog: CHANGELOG.md\npayload: .\n",
            "changelog": "prefix: v\npayload: .\n",
            "payload": "prefix: v\nchangelog: CHANGELOG.md\n",
        }
        for missing_key, body in cases.items():
            with self.subTest(missing=missing_key):
                text = "<!-- release-targets -->\n[app]\n" + body + self.CLOSE
                with self.assertRaises(core_releaselib.MissingRequiredKeyError):
                    core_releaselib.parse_release_targets(text)

    def test_parser_contract_boolean_is_exact_case_true_or_false_only(self):
        # M6: `value == "true"` mutated to a case-insensitive comparison
        # (`value.lower() == "true"`) survived the suite otherwise — the
        # spec requires the boolean to be EXACTLY "true"/"false".
        text = self.VALID_HEADER + "latest-eligible: TRUE\n" + self.CLOSE
        with self.assertRaises(core_releaselib.InvalidBooleanError):
            core_releaselib.parse_release_targets(text)

    def test_parser_contract_unclosed_block_raises_malformed_block_error(self):
        # M6: the unclosed-block branch (no `<!-- /release-targets -->` at
        # all) was previously untested directly.
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(self.VALID_HEADER)

    def test_parser_contract_every_violation_is_its_own_distinguishable_type(self):
        # The point of the contract: a caller can tell these apart by type.
        types = {
            core_releaselib.MalformedBlockError,
            core_releaselib.InvalidBooleanError,
            core_releaselib.DuplicateKeyError,
            core_releaselib.DuplicateTargetError,
            core_releaselib.UnknownKeyError,
            core_releaselib.MultipleBlocksError,
            core_releaselib.DelimiterInValueError,
            core_releaselib.MissingRequiredKeyError,
        }
        self.assertEqual(len(types), 8, "the 8 non-CRLF violations must be distinct types")
        for cls in types:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, core_releaselib.ReleaseTargetsError))


class SeriesIsolationTest(unittest.TestCase):
    """A-1.8: series isolation holds against LOADED data — a fixture
    declaring two series resolves each declared prefix to its own newest
    tag, with pre-releases excluded, composing `load_targets` with
    `last_tag_select`."""

    FIXTURE = (
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "\n"
        "[app-pi]\n"
        "prefix: ca-pi-v\n"
        "changelog: sub/CHANGELOG.md\n"
        "payload: sub/\n"
        "<!-- /release-targets -->\n"
    )

    TAGS = [
        "v1.0.0", "v0.9.0", "v1.1.0-beta.1",
        "ca-pi-v0.1.0", "ca-pi-v0.0.9", "ca-pi-v0.2.0-beta.1",
    ]

    def test_series_isolation_each_series_resolves_its_own_newest_tag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            import os as _os
            path = _os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(self.FIXTURE)
            rows = core_releaselib.load_targets(path)

        resolved = {
            row["target"]: core_releaselib.last_tag_select(self.TAGS, row["prefix"])
            for row in rows
        }
        self.assertEqual(resolved["app"], "v1.0.0")
        self.assertEqual(resolved["app-pi"], "ca-pi-v0.1.0")

    def test_series_isolation_prereleases_excluded_from_both_series(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            import os as _os
            path = _os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(self.FIXTURE)
            rows = core_releaselib.load_targets(path)

        for row in rows:
            chosen = core_releaselib.last_tag_select(self.TAGS, row["prefix"])
            with self.subTest(target=row["target"]):
                self.assertNotIn("beta", chosen)

    def test_series_isolation_no_series_resolves_the_others_tag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            import os as _os
            path = _os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(self.FIXTURE)
            rows = core_releaselib.load_targets(path)

        prefixes = [row["prefix"] for row in rows]
        for row in rows:
            chosen = core_releaselib.last_tag_select(self.TAGS, row["prefix"])
            for other_prefix in prefixes:
                if other_prefix == row["prefix"]:
                    continue
                with self.subTest(target=row["target"], other=other_prefix):
                    self.assertFalse(chosen.startswith(other_prefix))


# --------------------------------------------------------------------------- #
# Adversarial-review remediation (2026-07-31). See the module docstring for
# the finding each class closes. Every class here loads `core_releaselib`
# directly (never the old, unmodified `.github/scripts/_releaselib.py` shim),
# because the mutation gap this remediates was exactly that: real logic now
# ships in core/pysrc/_releaselib.py, but its only proof lived against the
# untouched shim.
# --------------------------------------------------------------------------- #


class CoreDelimiterInValueTest(unittest.TestCase):
    """H1: a value containing the literal closing delimiter must error in BOTH
    directions — never silently truncate (even when the embedded delimiter is
    the ONLY close in the text), and never misdiagnose a legitimate stray
    mention of the delimiter text in prose that follows a properly-closed
    block."""

    HEADER = ("<!-- release-targets -->\n"
              "[app]\n"
              "prefix: v\n"
              "changelog: CHANGELOG.md\n")

    def test_a_non_required_value_embedding_the_delimiter_errors_not_truncates(self):
        # Was: parses OK with rebuild == 'echo' (silently truncated).
        text = self.HEADER + "payload: .\nrebuild: echo <!-- /release-targets -->\n"
        with self.assertRaises(core_releaselib.DelimiterInValueError):
            core_releaselib.parse_release_targets(text)

    def test_a_required_value_embedding_the_delimiter_errors_not_emptied(self):
        # Was: parses OK with payload == '' — a REQUIRED key silently emptied,
        # the worst case the finding names.
        text = self.HEADER + "payload: <!-- /release-targets -->\n"
        with self.assertRaises(core_releaselib.DelimiterInValueError):
            core_releaselib.parse_release_targets(text)

    def test_a_stray_close_in_trailing_prose_is_not_misdiagnosed(self):
        # Two close-delimiter matches exist in the text, but the FIRST one is
        # the genuine, own-line block terminator; the second is a legitimate
        # mention in prose AFTER the block. Only the direction above (a match
        # embedded mid-line, encountered BEFORE any genuine terminator) is a
        # violation.
        text = (self.HEADER + "payload: .\n"
                "<!-- /release-targets -->\n"
                "\n"
                "See also <!-- /release-targets --> in this doc as an example.\n")
        rows = core_releaselib.parse_release_targets(text)
        self.assertEqual(rows[0]["payload"], ".")


class CoreRequiredKeyEmptyValueTest(unittest.TestCase):
    """H2: a required key present with an empty or whitespace-only value must
    be treated as MISSING. An `is None` check alone lets `prefix:` (no value)
    through as `''`, which then resolves `last_tag_select`'s `<none>`
    sentinel — a typo'd declaration silently becomes a first-release
    baseline."""

    def test_empty_value_on_a_required_key_is_missing(self):
        text = ("<!-- release-targets -->\n[app]\n"
                "prefix:\n"
                "changelog: CHANGELOG.md\npayload: .\n"
                "<!-- /release-targets -->\n")
        with self.assertRaises(core_releaselib.MissingRequiredKeyError):
            core_releaselib.parse_release_targets(text)

    def test_whitespace_only_value_on_a_required_key_is_missing(self):
        text = ("<!-- release-targets -->\n[app]\n"
                "prefix:   \n"
                "changelog: CHANGELOG.md\npayload: .\n"
                "<!-- /release-targets -->\n")
        with self.assertRaises(core_releaselib.MissingRequiredKeyError):
            core_releaselib.parse_release_targets(text)

    def test_a_genuinely_present_value_still_passes(self):
        # Non-regression: the stricter check must not reject real content.
        text = ("<!-- release-targets -->\n[app]\n"
                "prefix: v\nchangelog: CHANGELOG.md\npayload: .\n"
                "<!-- /release-targets -->\n")
        rows = core_releaselib.parse_release_targets(text)
        self.assertEqual(rows[0]["prefix"], "v")


class CorePrereleaseMarkerScopeTest(unittest.TestCase):
    """M2: the pre-release marker denylist must test the VERSION portion
    only, never the whole tag (prefix included) — a consumer whose own
    prefix happens to contain one of the marker substrings must not lose
    every release tag in that series."""

    def test_a_prefix_containing_beta_still_resolves_its_own_releases(self):
        tags = ["web-beta-v1.0.0", "web-beta-v1.2.0"]
        self.assertEqual(
            core_releaselib.last_tag_select(tags, "web-beta-v"), "web-beta-v1.2.0")

    def test_a_prefix_containing_rc_still_resolves_its_own_releases(self):
        tags = ["api-rc-v2.0.0", "api-rc-v2.1.0"]
        self.assertEqual(
            core_releaselib.last_tag_select(tags, "api-rc-v"), "api-rc-v2.1.0")

    def test_a_prefix_containing_alpha_still_resolves_its_own_releases(self):
        tags = ["thing-alpha-v0.1.0", "thing-alpha-v0.2.0"]
        self.assertEqual(
            core_releaselib.last_tag_select(tags, "thing-alpha-v"), "thing-alpha-v0.2.0")


class CorePrereleaseMarkersSecondLineOfDefenseTest(unittest.TestCase):
    """Adversarial-review remediation (M-4, 2026-07-31): `_PRERELEASE_MARKERS`
    is documented in `core/pysrc/_releaselib.py` as an explicit SECOND line of
    defense behind the anchored `_release_re` matcher — but `_release_re`'s
    own trailing `$` already rejects any tag carrying a suffix past
    `MAJOR.MINOR.PATCH`, so a marker-bearing tag never reaches the
    `_PRERELEASE_MARKERS` check at all through the public `last_tag_select`
    API today. Mutating `_PRERELEASE_MARKERS` to `()` therefore changes
    NOTHING observable through that path — confirmed empirically, and
    exactly what the review found ("survives both suites").

    A bare `assertEqual(_PRERELEASE_MARKERS, (...))` would die to that
    mutant too, but would prove only that the tuple's literal value is
    pinned, not that the defense DOES anything — the constant could be
    renamed to nonsense words and that test would still only check its own
    copy of the value. This test instead exercises the second line of
    defense in the scenario it exists FOR: a hypothetical relaxation of the
    first line. It monkeypatches `_release_re` to an UNANCHORED matcher (no
    trailing `$`) for the duration of one call, so a marker-bearing "version"
    now clears the (weakened) regex and reaches the `_PRERELEASE_MARKERS`
    check on its own merits — the only way to make this line reachable
    without weakening the shipped regex itself, which is out of scope here.
    """

    def test_marker_check_still_excludes_when_the_regex_alone_would_not(self):
        import re as _re
        import unittest.mock as mock
        lax = _re.compile(r"^v(\d+)\.(\d+)\.(\d+)")  # deliberately no trailing $
        with mock.patch.object(core_releaselib, "_release_re", return_value=lax):
            tags = ["v1.0.0", "v1.1.0-beta.1"]
            # Under the lax regex alone, "v1.1.0-beta.1" matches (span
            # v1.1.0) and is numerically higher than v1.0.0 — only
            # _PRERELEASE_MARKERS can still exclude it here.
            self.assertEqual(core_releaselib.last_tag_select(tags, "v"), "v1.0.0")


class CoreColonInValueTest(unittest.TestCase):
    """M4: values split on the FIRST colon only; a later colon is part of the
    value. `line.find(":")` vs `line.rfind(":")` are indistinguishable
    without a fixture value that itself contains a colon."""

    def test_a_value_containing_a_colon_is_preserved_whole(self):
        text = ("<!-- release-targets -->\n[app]\n"
                "prefix: v\nchangelog: CHANGELOG.md\npayload: .\n"
                'rebuild: echo "a:b" && date +%H:%M:%S\n'
                "<!-- /release-targets -->\n")
        rows = core_releaselib.parse_release_targets(text)
        self.assertEqual(rows[0]["rebuild"], 'echo "a:b" && date +%H:%M:%S')


class CoreEscapeHatchWrappingTest(unittest.TestCase):
    """M5: two escape hatches must not bypass the declared ReleaseTargetsError
    hierarchy the module promises callers can catch as one type."""

    def test_non_string_input_stays_in_the_declared_hierarchy(self):
        with self.assertRaises(core_releaselib.AbsentBlockError):
            core_releaselib.parse_release_targets(None)

    def test_an_unreadable_path_stays_in_the_declared_hierarchy(self):
        with self.assertRaises(core_releaselib.AbsentBlockError):
            core_releaselib.load_targets("no/such/release-targets.md")


class CoreClassifyPublishStateTest(unittest.TestCase):
    """H3: classify_publish_state exercised against the portable module —
    previously only the (untouched) shim's copy carried this proof."""

    def test_no_tag_is_publish_fresh(self):
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=False, tag_sha=None, head_sha="abc",
                tag_version=None, manifest_version="2.6.0", release_is_nondraft=False),
            "publish_fresh")

    def test_tag_at_head_version_match_no_release_is_resume(self):
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=False),
            "resume_publish")

    def test_nondraft_release_is_already_published(self):
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=True),
            "already_published")

    def test_tag_points_elsewhere_is_abort(self):
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha="xyz", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=False),
            "abort_mismatch")

    def test_version_mismatch_is_abort(self):
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha="abc", head_sha="abc",
                tag_version="2.5.0", manifest_version="2.6.0", release_is_nondraft=False),
            "abort_mismatch")

    def test_nondraft_release_on_a_tag_at_another_commit_is_abort(self):
        # Mismatch outranks publication state (issue #380's original defect).
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha="xyz", head_sha="abc",
                tag_version="2.6.0", manifest_version="2.6.0", release_is_nondraft=True),
            "abort_mismatch")


class CoreNotesHeadingTest(unittest.TestCase):
    """H3: notes_heading_matches / _bare_version exercised against the
    portable module."""

    def test_matching_heading(self):
        notes = "## v2.6.0 — 2026-06-26\n\n### Added\n- thing\n"
        self.assertTrue(core_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_matching_bracket_heading(self):
        notes = "## [2.6.0] — 2026-06-27\n\n### Added\n- thing\n"
        self.assertTrue(core_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_mismatched_heading(self):
        notes = "## v2.5.0 — 2026-06-01\n\n### Fixed\n- bug\n"
        self.assertFalse(core_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_first_heading_is_authoritative(self):
        notes = "## v2.5.0 — 2026-06-01\n\n## v2.6.0 — 2026-06-26\n"
        self.assertFalse(core_releaselib.notes_heading_matches(notes, "v2.6.0"))

    def test_no_heading_is_false(self):
        self.assertFalse(
            core_releaselib.notes_heading_matches("no headings here", "v2.6.0"))

    def test_never_raises_on_non_string(self):
        self.assertFalse(core_releaselib.notes_heading_matches(None, "v2.6.0"))

    def test_namespaced_tag_matches_via_bare_version(self):
        notes = "## [0.1.31] - 2026-07-26\n\n### Added\n\n- a thing\n"
        self.assertTrue(
            core_releaselib.notes_heading_matches(notes, "ca-pi-v0.1.31"))

    def test_bare_version_extracts_the_semver_from_any_spelling(self):
        cases = {
            "v2.6.0": "2.6.0",
            "2.6.0": "2.6.0",
            "[2.6.0]": "2.6.0",
            "ca-pi-v0.1.31": "0.1.31",
        }
        for spelling, want in cases.items():
            with self.subTest(spelling=spelling):
                self.assertEqual(core_releaselib._bare_version(spelling), want)

    def test_bare_version_never_raises_on_non_string(self):
        self.assertIsNone(core_releaselib._bare_version(None))


class CoreReleaseDatesTest(unittest.TestCase):
    """H3: release_dates_consistent exercised against the portable module."""

    def test_consistent_dates(self):
        section = "## v2.6.0 — 2026-06-26\n\n### Added\n- thing\n"
        tagmsg = "codeArbiter 2.6.0\n\nstuff\n\nReleased-at: 2026-06-26\n"
        self.assertTrue(core_releaselib.release_dates_consistent(section, tagmsg))

    def test_inconsistent_dates(self):
        section = "## v2.6.0 — 2026-06-26\n"
        tagmsg = "Released-at: 2026-06-25\n"
        self.assertFalse(core_releaselib.release_dates_consistent(section, tagmsg))

    def test_missing_changelog_date_is_false(self):
        self.assertFalse(core_releaselib.release_dates_consistent(
            "## v2.6.0\n", "Released-at: 2026-06-26\n"))

    def test_missing_tag_date_is_false(self):
        self.assertFalse(core_releaselib.release_dates_consistent(
            "## v2.6.0 — 2026-06-26\n", "no footer"))

    def test_never_raises(self):
        self.assertFalse(core_releaselib.release_dates_consistent(None, None))


class CorePeelTagTest(unittest.TestCase):
    """H3: peel_tag exercised against the portable module."""

    TAG_OBJ = "1" * 40
    COMMIT = "2" * 40

    def test_annotated_tag_resolves_to_the_peeled_commit(self):
        text = (f"{self.TAG_OBJ}\trefs/tags/v2.6.0\n"
                f"{self.COMMIT}\trefs/tags/v2.6.0^{{}}\n")
        self.assertEqual(core_releaselib.peel_tag(text, "v2.6.0"), self.COMMIT)

    def test_lightweight_tag_resolves_to_its_direct_target(self):
        text = f"{self.COMMIT}\trefs/tags/v2.6.0\n"
        self.assertEqual(core_releaselib.peel_tag(text, "v2.6.0"), self.COMMIT)

    def test_a_prefix_sharing_tag_is_not_mistaken_for_it(self):
        text = f"{self.COMMIT}\trefs/tags/v2.6.0-beta.1\n"
        self.assertEqual(core_releaselib.peel_tag(text, "v2.6.0"), "")

    def test_absent_tag_is_empty(self):
        self.assertEqual(core_releaselib.peel_tag("", "v2.6.0"), "")

    def test_never_raises_on_non_string(self):
        self.assertEqual(core_releaselib.peel_tag(None, "v2.6.0"), "")
        self.assertEqual(core_releaselib.peel_tag("whatever", None), "")


class CoreSemverTest(unittest.TestCase):
    """H3: semver_key / semver_greater exercised against the portable
    module — previously untested against ANY module, old shim included."""

    def test_semver_key_parses_a_plain_version(self):
        self.assertEqual(core_releaselib.semver_key("2.9.1"), (2, 9, 1, None))

    def test_semver_key_none_on_unparseable(self):
        self.assertIsNone(core_releaselib.semver_key("not-a-version"))
        self.assertIsNone(core_releaselib.semver_key(None))
        self.assertIsNone(core_releaselib.semver_key(42))

    def test_semver_key_discards_build_metadata_for_equality(self):
        self.assertEqual(
            core_releaselib.semver_key("1.0.0+a"),
            core_releaselib.semver_key("1.0.0+b"))

    def test_semver_greater_numeric_advance(self):
        self.assertTrue(core_releaselib.semver_greater("2.10.0", "2.9.0"))
        self.assertFalse(core_releaselib.semver_greater("2.9.0", "2.10.0"))
        self.assertFalse(core_releaselib.semver_greater("2.9.0", "2.9.0"))

    def test_semver_greater_release_beats_its_own_prerelease(self):
        self.assertTrue(core_releaselib.semver_greater("1.0.0", "1.0.0-beta"))
        self.assertFalse(core_releaselib.semver_greater("1.0.0-beta", "1.0.0"))

    def test_semver_greater_degrades_to_false_on_unparseable_input(self):
        self.assertFalse(core_releaselib.semver_greater("nope", "1.0.0"))
        self.assertFalse(core_releaselib.semver_greater("1.0.0", "nope"))


class CoreMergeReadinessArmsTest(unittest.TestCase):
    """H3: classify_merge_readiness's non-green arms exercised against the
    portable module — replacing this module's own copy with a hardcoded
    constant previously stayed green, because only the shim's copy was
    tested for anything but the required-parameter contract."""

    SHA = "a" * 40
    OTHER = "b" * 40
    CHECK = "gate"

    def _run(self, status="completed", conclusion="success", head_sha=None, name=None):
        return {
            "name": self.CHECK if name is None else name,
            "status": status,
            "conclusion": conclusion,
            "head_sha": self.SHA if head_sha is None else head_sha,
        }

    def test_missing_when_no_run_matches_the_name(self):
        self.assertEqual(
            core_releaselib.classify_merge_readiness(
                [self._run(name="other")], self.SHA, self.CHECK),
            "missing")

    def test_missing_on_empty_check_runs(self):
        self.assertEqual(
            core_releaselib.classify_merge_readiness([], self.SHA, self.CHECK),
            "missing")

    def test_pending_when_not_completed(self):
        run = self._run(status="in_progress", conclusion=None)
        self.assertEqual(
            core_releaselib.classify_merge_readiness([run], self.SHA, self.CHECK),
            "pending")

    def test_sha_mismatch_on_a_different_commit(self):
        run = self._run(head_sha=self.OTHER)
        self.assertEqual(
            core_releaselib.classify_merge_readiness([run], self.SHA, self.CHECK),
            "sha_mismatch")

    def test_not_successful_on_a_failed_conclusion(self):
        run = self._run(conclusion="failure")
        self.assertEqual(
            core_releaselib.classify_merge_readiness([run], self.SHA, self.CHECK),
            "not_successful")

    def test_green_is_still_reachable(self):
        self.assertEqual(
            core_releaselib.classify_merge_readiness([self._run()], self.SHA, self.CHECK),
            "green")


class CoreSelectReleaseTargetArmsTest(unittest.TestCase):
    """H3: select_release_target's `arity` and `multiple` arms exercised
    against the portable module."""

    TARGETS = ["app", "lib"]

    def test_multiple_when_more_than_one_selected(self):
        self.assertEqual(
            core_releaselib.select_release_target(
                "1.0.0", "2.0.0", targets=self.TARGETS),
            "multiple")

    def test_arity_on_a_length_mismatch(self):
        self.assertEqual(
            core_releaselib.select_release_target("1.0.0", targets=self.TARGETS),
            "arity")

    def test_none_when_nothing_selected(self):
        self.assertEqual(
            core_releaselib.select_release_target("", "", targets=self.TARGETS),
            "none")

    def test_the_matching_position_selects_its_target(self):
        self.assertEqual(
            core_releaselib.select_release_target("", "2.0.0", targets=self.TARGETS),
            "lib")


class CoreCLITest(unittest.TestCase):
    """T-41f (issue #563): `core/pysrc/_releaselib.py` gains a `__main__` CLI
    entry point. Without this, T-41b's repointing of the release skill's
    helper invocations under `${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py`
    would aim prose at a file with no runnable entry point at all —
    `tag-prefix`, `last-tag`, and `classify` would fail in a consumer even
    though the rewrite reports success. Every case here calls
    `core_releaselib.main(argv)` directly EXCEPT
    `test_consumer_shaped_subprocess_invocation_exits_zero`, which shells out
    for real (the literal verification named in the plan: `python
    "<plugin-root>/hooks/_releaselib.py" tag-prefix ca` exits 0 from a
    consumer-shaped environment) — a direct-call test alone could pass while
    the file has a syntax error or an import that only breaks when actually
    executed as a script."""

    def _write_targets(self, tmp_dir, block):
        path = os.path.join(tmp_dir, "release-targets.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(block)
        return path

    APP_BLOCK = (
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "<!-- /release-targets -->\n"
    )

    def test_no_argv_prints_usage_and_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main([])
        self.assertEqual(rc, 2)
        self.assertIn("usage", err.getvalue())

    def test_bad_invocation_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["nonsense"])
        self.assertEqual(rc, 2)

    def test_tag_prefix_resolves_via_explicit_targets_file(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_targets(tmp, self.APP_BLOCK)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(
                    ["tag-prefix", "app", "--targets-file", path])
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue().strip(), "v")

    def test_tag_prefix_unknown_target_exits_2(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_targets(tmp, self.APP_BLOCK)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = core_releaselib.main(
                    ["tag-prefix", "nope", "--targets-file", path])
            self.assertEqual(rc, 2)
            self.assertIn("unknown release target", err.getvalue())

    def test_tag_prefix_targets_file_flag_with_no_value_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["tag-prefix", "app", "--targets-file"])
        self.assertEqual(rc, 2)
        self.assertIn("--targets-file requires a value", err.getvalue())

    def test_targets_file_flag_is_not_special_cased_for_other_subcommands(self):
        # The flag-stripping pass lives INSIDE the tag-prefix branch only, so
        # a caller-supplied positional value that happens to equal the flag
        # spelling is never lexically special-cased out of a DIFFERENT
        # subcommand's argument list.
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = core_releaselib.main(
                ["classify", "false", "--targets-file", "-", "1.0.0", "1.0.0", "false"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "publish_fresh")

    def test_tag_prefix_absent_declared_file_exits_3_not_a_traceback(self):
        # HIGH-1 (adversarial review 2026-07-31): a genuinely absent file
        # gets its OWN exit code (3), never the generic bad-invocation/
        # unknown-target code (2) it used to share with everything else.
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(
                ["tag-prefix", "app", "--targets-file",
                 os.path.join(tempfile.gettempdir(),
                              "codearbiter-cli-test-does-not-exist.md")])
        self.assertEqual(rc, 3)
        self.assertIn("could not read declared release targets", err.getvalue())
        self.assertIn("AbsentBlockError", err.getvalue())

    def test_tag_prefix_existing_no_block_file_exits_4_distinct_from_absent(self):
        # HIGH-1: an EXISTING file with no block is a DIFFERENT declared-file
        # state than a genuinely absent one and must exit with a DIFFERENT
        # code -- the exact discrimination the finding says the CLI lacked.
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("no block in this file at all\n")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = core_releaselib.main(
                    ["tag-prefix", "app", "--targets-file", path])
            self.assertEqual(rc, 4)
            self.assertIn("FileExistsNoBlockError", err.getvalue())

    def test_list_targets_prints_every_declared_name(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_targets(
                tmp,
                "<!-- release-targets -->\n"
                "[one]\n"
                "prefix: v\n"
                "changelog: CHANGELOG.md\n"
                "payload: .\n"
                "\n"
                "[two]\n"
                "prefix: two-v\n"
                "changelog: two/CHANGELOG.md\n"
                "payload: two/\n"
                "<!-- /release-targets -->\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(
                    ["list-targets", "--targets-file", path])
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue().splitlines(), ["one", "two"])

    def test_list_targets_absent_file_exits_3(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(
                ["list-targets", "--targets-file",
                 os.path.join(tempfile.gettempdir(),
                              "codearbiter-cli-list-targets-does-not-exist.md")])
        self.assertEqual(rc, 3)

    def test_list_targets_bad_invocation_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["list-targets", "unexpected-positional"])
        self.assertEqual(rc, 2)

    # `dates-match` (run 4). Phase 1 step 5 and Phase 2 step 1 both named
    # `release_dates_consistent`, and Phase 2 said it "must pass" — with no
    # CLI entry point, so an operator following the prose could not run the
    # check the prose demanded. The exercising agent reached it only by
    # importing the module, which the skill never instructs.
    def _dates_files(self, tmp, section_date, released_at):
        section = os.path.join(tmp, "section.md")
        message = os.path.join(tmp, "msg.txt")
        with open(section, "w", encoding="utf-8") as fh:
            fh.write(f"## [1.3.0] - {section_date}\n\n### Added\n\n- A thing.\n")
        with open(message, "w", encoding="utf-8") as fh:
            fh.write(f"## [1.3.0] - {section_date}\n\n- A thing.\n\n"
                     f"Released-at: {released_at}\n")
        return section, message

    def test_dates_match_exits_0_when_the_two_dates_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            section, message = self._dates_files(tmp, "2026-07-31", "2026-07-31")
            self.assertEqual(core_releaselib.main(["dates-match", section, message]), 0)

    def test_dates_match_exits_1_when_the_dates_disagree(self):
        # The defect the guard exists for: a hand-typed second date.
        with tempfile.TemporaryDirectory() as tmp:
            section, message = self._dates_files(tmp, "2026-07-31", "2026-01-01")
            self.assertEqual(core_releaselib.main(["dates-match", section, message]), 1)

    def test_dates_match_exits_1_on_an_unreadable_file_never_a_traceback(self):
        # Same contract as notes-match: an unreadable file is empty text,
        # which has no date, so the comparison is False and the exit is 1.
        # A traceback here would break a `set -e` lane with no diagnosis.
        with tempfile.TemporaryDirectory() as tmp:
            _section, message = self._dates_files(tmp, "2026-07-31", "2026-07-31")
            missing = os.path.join(tmp, "does-not-exist.md")
            self.assertEqual(core_releaselib.main(["dates-match", missing, message]), 1)

    # `semver-greater` (run 6). The hard rules say the version MUST NOT be
    # guessed, yet the bump arithmetic and the strictly-greater assertion
    # were both hand-done: `semver_greater` was public API reachable only
    # by import. This is also the mechanism the manifest-FLOOR check needs
    # (HIGH, run 6).
    def test_semver_greater_exits_0_when_strictly_greater(self):
        self.assertEqual(
            core_releaselib.main(["semver-greater", "1.5.0", "1.4.2"]), 0)

    def test_semver_greater_exits_1_when_lesser(self):
        # The exact defect: a never-tagged project deriving 0.1.0 against a
        # manifest already at 1.4.2.
        self.assertEqual(
            core_releaselib.main(["semver-greater", "0.1.0", "1.4.2"]), 1)

    def test_semver_greater_exits_1_when_equal_not_0(self):
        # "Strictly" is the whole point -- re-releasing the same version is
        # the case an inclusive comparison would wave through.
        self.assertEqual(
            core_releaselib.main(["semver-greater", "1.4.2", "1.4.2"]), 1)

    def test_semver_greater_exits_2_on_an_unparseable_version(self):
        # Distinct from exit 1. `semver_greater` is non-raising and returns
        # False for garbage, which is fail-closed but indistinguishable
        # from a real "not greater" -- the same conflation the exit-3-vs-4
        # work already removed from the declared-file path.
        import io, contextlib
        for argv in (["semver-greater", "nope", "1.4.2"],
                     ["semver-greater", "1.4.2", "nope"]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = core_releaselib.main(argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("not valid SemVer", err.getvalue())

    # ---- A-2.4: the declared-value cap (ADR-0002 precedent) ----
    @staticmethod
    def _block(lines):
        """Wrap declaration lines in the delimiter block, so a cap test
        exercises the REAL parser entry point rather than an internal."""
        return ("<!-- release-targets -->\n" + "\n".join(lines)
                + "\n<!-- /release-targets -->\n")

    def test_pre_tag_cap_rejects_an_over_long_value(self):
        block = self._block([
            "[app]", "prefix: v", "changelog: CHANGELOG.md", "payload: .",
            "pre-tag: " + "A" * (core_releaselib.VALUE_MAX_CHARS + 1)])
        with self.assertRaises(core_releaselib.ValueTooLongError):
            core_releaselib.parse_release_targets(block)

    def test_pre_tag_cap_admits_a_value_exactly_at_the_limit(self):
        # Off-by-one in the boundary is the whole risk of a cap: a `>=`
        # would reject a legitimate 1024-char value, a `>` on the wrong
        # side would admit 1025.
        block = self._block([
            "[app]", "prefix: v", "changelog: CHANGELOG.md", "payload: .",
            "pre-tag: " + "A" * core_releaselib.VALUE_MAX_CHARS])
        rows = core_releaselib.parse_release_targets(block)
        self.assertEqual(len(rows[0]["pre_tag"][0]), core_releaselib.VALUE_MAX_CHARS)

    def test_pre_tag_cap_applies_to_every_key_not_only_pre_tag(self):
        # The cap exists because these values are operator-authored input a
        # `contents: write` lane later executes or interpolates. `rebuild`
        # and `generate` are executed exactly as `pre-tag` is, so capping
        # only the key that motivated the rule would leave the identical
        # exposure one field over.
        for key in ("rebuild", "generate", "payload", "prefix"):
            with self.subTest(key=key):
                block = self._block([
                    "[app]", "prefix: v", "changelog: CHANGELOG.md", "payload: .",
                    f"{key}: " + "A" * (core_releaselib.VALUE_MAX_CHARS + 1)])
                with self.assertRaises(core_releaselib.ValueTooLongError):
                    core_releaselib.parse_release_targets(block)

    def test_value_too_long_is_a_declared_file_error_exiting_4_not_3(self):
        # Exit 3 is the Back-fill lane's ONE trigger. An over-long value is
        # a malformed declaration on a file that plainly exists; routing it
        # to 3 would send the lane to overwrite that file.
        self.assertIsInstance(
            core_releaselib.ValueTooLongError("x"), core_releaselib.ReleaseTargetsError)
        self.assertNotIsInstance(
            core_releaselib.ValueTooLongError("x"), core_releaselib.AbsentBlockError)
        self.assertEqual(
            core_releaselib._targets_error_exit_code(
                core_releaselib.ValueTooLongError("x")), 4)

    # ---- run-pre-tag: the tree assertion is "changed nothing NEW" ----
    def _pretag_repo(self, tmp, commands, dirty=False):
        """A consumer with `commands` declared, optionally left with the
        uncommitted manifest/changelog edits Phase 1 makes BEFORE this step
        runs -- which is the normal lane, not an edge case."""
        root = os.path.join(tmp, "consumer")
        os.makedirs(os.path.join(root, ".codearbiter"))
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"version": "1.0.0"}\n')
        with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
            fh.write("# Changelog\n")
        with open(os.path.join(root, ".codearbiter", "release-targets.md"), "w") as fh:
            fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                     "changelog: CHANGELOG.md\npayload: .\n"
                     + "".join(f"pre-tag: {c}\n" for c in commands)
                     + "<!-- /release-targets -->\n")
        # HERMETIC and CHECKED. Unconfigured `subprocess.run(["git"] + argv)`
        # inherits the developer's global config and ignores the exit code,
        # so a host with `commit.gpgsign=true`, a `core.hooksPath`, or a
        # commit template can make `commit` fail while this helper returns a
        # fixture that merely LOOKS built -- and the test then asserts
        # against a repo with no commit in it, passing or failing for a
        # reason that has nothing to do with the code under test.
        env = dict(os.environ,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        base = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=",
                "-c", "init.defaultBranch=main"]
        for argv in (["init", "-q"],
                     ["add", "package.json", "CHANGELOG.md",
                      ".codearbiter/release-targets.md"],
                     ["commit", "-q", "-m", "init", "--no-verify"]):
            proc = subprocess.run(base + argv, cwd=root, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(
                proc.returncode, 0,
                f"fixture git {argv[0]} failed: {proc.stderr.strip()}")
        if dirty:
            with open(os.path.join(root, "package.json"), "w") as fh:
                fh.write('{"version": "1.1.0"}\n')
            with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
                fh.write("# Changelog\n\n## [1.1.0] - 2026-07-31\n")
        return root

    def _run_pre_tag(self, root):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "run-pre-tag", "app"],
            cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True)

    def test_run_pre_tag_tolerates_the_release_edits_that_precede_it(self):
        # HIGH, run 9: the assertion used to be "the tree is pristine",
        # which BLOCKED EVERY RELEASE -- Phase 1 rolls the changelog and
        # bumps the manifest before this step, and it must, because a badge
        # check compares a surface against the NEW version.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, ['python -c "print(1)"'], dirty=True)
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_run_pre_tag_exits_0_with_no_declared_commands_on_a_dirty_tree(self):
        # The starkest form of the same defect: a row declaring NOTHING
        # still exited 6.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [], dirty=True)
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_run_pre_tag_still_catches_a_mutation_on_top_of_those_edits(self):
        # The property the loosening must NOT cost: a declared command's
        # own writes still surface, even when the tree was already dirty.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(
                tmp, ['python -c "open(\'sneaky.txt\',\'w\').write(\'x\')"'],
                dirty=True)
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn("sneaky.txt", proc.stderr)
            # Only the NEW path is reported, not the operator's own edits.
            self.assertNotIn("package.json", proc.stderr)

    # ---- A-4.2: name-keyed target selection ----
    TARGETS = ["ca", "ca-codex", "ca-sandbox", "ca-pi"]

    def test_select_target_name_keyed_resolves_the_named_target(self):
        self.assertEqual(
            core_releaselib.select_release_target_by_name(
                ["ca-pi=0.1.44", "ca=", "ca-codex="], self.TARGETS),
            "ca-pi")

    def test_select_target_name_keyed_is_immune_to_row_order(self):
        # THE defect this closes. The positional resolver aligns
        # confirmations to `targets` by INDEX, so it is correct only while
        # the workflow's input order and the declared file's row order
        # agree -- and nothing enforced that. Insert one row at the front
        # of the declared file and every confirmation shifts by one: a
        # dispatch meaning to publish `ca-codex` publishes `ca` instead,
        # holding a contents:write token, and every downstream check passes
        # because the WRONG release is internally consistent.
        shifted = ["NEW"] + self.TARGETS
        self.assertEqual(
            core_releaselib.select_release_target(
                "", "2.4.0", "", "", targets=self.TARGETS),
            "ca-codex")
        self.assertEqual(
            core_releaselib.select_release_target(
                "", "2.4.0", "", "", targets=shifted[:4]),
            "ca",
            "if this stops being 'ca', the positional hazard changed shape "
            "and this test no longer demonstrates what it claims")
        # Same intent, name-keyed, against BOTH registers:
        for register in (self.TARGETS, shifted):
            self.assertEqual(
                core_releaselib.select_release_target_by_name(
                    ["ca-codex=2.4.0"], register),
                "ca-codex")

    def test_select_target_name_keyed_refuses_a_multi_target_dispatch(self):
        # One dispatch, one publisher. Two confirmations must never start
        # two contents:write jobs.
        self.assertEqual(
            core_releaselib.select_release_target_by_name(
                ["ca=1.0.0", "ca-pi=2.0.0"], self.TARGETS),
            "multiple")

    def test_select_target_name_keyed_treats_blank_as_not_selected(self):
        for pairs in (["ca="], ["ca=   "], ["ca=", "ca-pi="], []):
            self.assertEqual(
                core_releaselib.select_release_target_by_name(pairs, self.TARGETS),
                "none", pairs)

    def test_select_target_name_keyed_reports_an_undeclared_name(self):
        # Distinct from `none`: a fail-closed caller refuses both, but only
        # this one means the workflow and the declared file disagree, which
        # is worth reporting rather than passing off as an empty dispatch.
        self.assertEqual(
            core_releaselib.select_release_target_by_name(
                ["nope=1.0.0"], self.TARGETS),
            "unknown")
        self.assertNotEqual("unknown", "none")

    def test_select_target_name_keyed_ignores_a_pair_with_no_equals(self):
        # An empty workflow input can arrive as a bare name; that is a
        # missing value, not a malformed dispatch.
        self.assertEqual(
            core_releaselib.select_release_target_by_name(
                ["bare-name"], self.TARGETS),
            "none")

    def test_select_target_name_keyed_never_raises_on_junk(self):
        for pairs in (None, 42, ["ca=1.0.0", None, 7], "ca=1.0.0"):
            result = core_releaselib.select_release_target_by_name(
                pairs, self.TARGETS)
            self.assertIn(result, self.TARGETS + ["none", "multiple", "unknown"])

    def test_select_target_name_keyed_agrees_with_the_declared_register(self):
        # Against this repo's real declared names, so a rename in the
        # declared file surfaces here rather than at dispatch time.
        rows = core_releaselib.load_targets(
            os.path.join(REPO_ROOT, ".codearbiter", "release-targets.md"))
        names = [r["target"] for r in rows]
        for name in names:
            with self.subTest(target=name):
                self.assertEqual(
                    core_releaselib.select_release_target_by_name(
                        [f"{name}=1.2.3"], names),
                    name)

    # ---- Slice 3: which assertions a row's declared fields turn on ----
    ROW_FULL = {
        "target": "app", "prefix": "v", "changelog": "CHANGELOG.md",
        "payload": "plugins/app/", "manifest": ["plugins/app/plugin.json"],
        "rebuild": "cd plugins/app/tools && npm run build",
        "artifacts": ["plugins/app/tools/bundle.js"],
        "payload_exclude": ["plugins/app/tools/"],
        "provenance_manifest": ".github/published-tags.json",
    }
    ROW_BARE = {
        "target": "bare", "prefix": "v", "changelog": "CHANGELOG.md",
        "payload": ".",
    }

    def test_manifest_declared_asserts_equality(self):
        # A-3.1. A declared manifest means the lane compares versions.
        verdict = core_releaselib.row_assertions(self.ROW_FULL)
        self.assertTrue(verdict["assert_manifest_equal"])
        self.assertEqual(verdict["version_source"], "manifest")
        self.assertEqual(verdict["manifests"], ["plugins/app/plugin.json"])
        self.assertNotIn("manifest-equality",
                         [name for name, _reason in verdict["skipped"]])

    def test_manifest_declared_covers_every_path_not_just_the_first(self):
        # A row may declare several; asserting only the first is the
        # partial-bump hole run 12 found from the other direction.
        row = dict(self.ROW_FULL, manifest=["a/plugin.json", "b/package.json"])
        self.assertEqual(core_releaselib.row_assertions(row)["manifests"],
                         ["a/plugin.json", "b/package.json"])

    def test_manifest_absent_uses_the_tag_as_version_source(self):
        # A-3.2. No manifest is a legitimate consumer shape, not an error:
        # the derived tag IS the version, and there is nothing to compare.
        verdict = core_releaselib.row_assertions(self.ROW_BARE)
        self.assertFalse(verdict["assert_manifest_equal"])
        self.assertEqual(verdict["version_source"], "tag")
        self.assertEqual(verdict["manifests"], [])

    def test_manifest_absent_is_reported_as_skipped_not_silently_dropped(self):
        # The skill's own rule: a skipped step and a forgotten step must
        # never look alike. Absence is an operator decision, so it is named.
        skipped = dict(core_releaselib.row_assertions(self.ROW_BARE)["skipped"])
        self.assertIn("manifest-equality", skipped)
        self.assertIn("no manifest", skipped["manifest-equality"])

    def test_version_source_and_manifest_assertion_cannot_disagree(self):
        # The reason these are ONE derivation. Two independent checks could
        # report "tag is the version source" while also asserting manifest
        # equality; a single derivation structurally cannot.
        for row in (self.ROW_FULL, self.ROW_BARE, {},
                    dict(self.ROW_FULL, manifest=[])):
            verdict = core_releaselib.row_assertions(row)
            self.assertEqual(
                verdict["assert_manifest_equal"],
                verdict["version_source"] == "manifest", row.get("target"))

    def test_rebuild_artifacts_are_reported_together(self):
        # A-3.3. `rebuild` runs, then every `artifacts` entry is asserted
        # clean; a stale bundle blocks.
        verdict = core_releaselib.row_assertions(self.ROW_FULL)
        self.assertEqual(verdict["rebuild"],
                         "cd plugins/app/tools && npm run build")
        self.assertEqual(verdict["artifacts"], ["plugins/app/tools/bundle.js"])

    def test_rebuild_artifacts_absent_are_named_as_skipped(self):
        skipped = dict(core_releaselib.row_assertions(self.ROW_BARE)["skipped"])
        self.assertIn("rebuild", skipped)
        self.assertIn("artifacts-clean", skipped)

    def test_provenance_optional_absent_is_skipped_and_reported(self):
        # A-3.5. Absent means the recording step is skipped AND the report
        # says so -- silence here reads as "forgotten", which is the exact
        # ambiguity this field's optionality creates.
        verdict = core_releaselib.row_assertions(self.ROW_BARE)
        self.assertFalse(verdict["record_provenance"])
        self.assertIsNone(verdict["provenance_manifest"])
        self.assertIn("provenance-recording",
                      [name for name, _reason in verdict["skipped"]])

    def test_provenance_optional_present_records(self):
        verdict = core_releaselib.row_assertions(self.ROW_FULL)
        self.assertTrue(verdict["record_provenance"])
        self.assertEqual(verdict["provenance_manifest"],
                         ".github/published-tags.json")

    def test_row_assertions_never_raises_on_junk(self):
        for junk in (None, 42, "row", [], {"manifest": 7, "artifacts": None}):
            verdict = core_releaselib.row_assertions(junk)
            self.assertEqual(verdict["version_source"], "tag")
            self.assertEqual(verdict["manifests"], [])

    def test_payload_exclude_removes_paths_under_the_excluded_directory(self):
        # A-3.4, against ca-pi's real shape: tools/ ships neither generated
        # policy nor a built runtime artifact, so a change there must not
        # gate the release.
        kept = core_releaselib.window_excludes_payload_paths(
            ["plugins/ca-pi/extensions/codearbiter.js",
             "plugins/ca-pi/tools/build.mjs",
             "plugins/ca-pi/package.json"],
            "plugins/ca-pi/", ["plugins/ca-pi/tools/"])
        self.assertEqual(kept, ["plugins/ca-pi/extensions/codearbiter.js",
                                "plugins/ca-pi/package.json"])

    def test_payload_exclude_is_a_path_prefix_not_a_substring(self):
        # "tools" must not swallow "toolsmith/". A substring test would
        # silently drop a sibling directory whose name merely starts the
        # same way -- a dropped commit, not a loud failure.
        kept = core_releaselib.window_excludes_payload_paths(
            ["a/toolsmith/x.js", "a/tools/y.js"], "a", ["a/tools"])
        self.assertEqual(kept, ["a/toolsmith/x.js"])

    def test_payload_exclude_scopes_to_the_payload_first(self):
        # A sibling target's paths are outside this row's payload and must
        # not enter its window at all.
        kept = core_releaselib.window_excludes_payload_paths(
            ["plugins/ca-pi/a.js", "plugins/ca/b.py"], "plugins/ca-pi/", [])
        self.assertEqual(kept, ["plugins/ca-pi/a.js"])

    def test_payload_exclude_whole_repo_payload_keeps_everything(self):
        # A consumer's `payload: .` scopes to the whole tree.
        kept = core_releaselib.window_excludes_payload_paths(
            ["src/a.py", "docs/b.md"], ".", [])
        self.assertEqual(kept, ["src/a.py", "docs/b.md"])

    def test_payload_exclude_matches_this_repos_declared_ca_pi_row(self):
        # The spec names ca-pi's tools/ exclusion specifically, so assert
        # against the DECLARED row rather than a synthetic one.
        rows = {r["target"]: r for r in core_releaselib.load_targets(
            os.path.join(REPO_ROOT, ".codearbiter", "release-targets.md"))}
        verdict = core_releaselib.row_assertions(rows["ca-pi"])
        self.assertEqual(verdict["payload_exclude"], ["plugins/ca-pi/tools/"])
        self.assertEqual(len(verdict["manifests"]), 2)

    # ---- A-2.10: pre-tag content-hash confirmation (releasehash.py) ----
    def _releasehash(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_rh_under_test", os.path.join(REPO_ROOT, "core", "pysrc", "releasehash.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_pre_tag_hash_is_order_sensitive(self):
        # The commands run in DECLARED ORDER, and a check that ran after a
        # rebuild is not the same check as one that ran before it. A
        # reorder must therefore invalidate the confirmation, not preserve
        # it -- an order-insensitive digest (sorted, or a set) would call a
        # reordered lane "confirmed".
        rh = self._releasehash()
        self.assertNotEqual(
            rh.pre_tag_digest(["check_a.py", "check_b.py"]),
            rh.pre_tag_digest(["check_b.py", "check_a.py"]))

    def test_pre_tag_hash_cannot_collide_across_a_join(self):
        # The length prefix's ACTUAL job, found by a surviving mutant: my
        # first version of this test used ["ab","c"] vs ["a","bc"], which
        # already differ once joined on a newline, so removing the prefix
        # left the test green. The collision the prefix really prevents
        # needs a command CONTAINING the separator:
        #
        #   ["a\n b"]  -> "1\na\nb"     (one command, embedded newline)
        #   ["a", "b"] -> "1\na\nb"     (two commands)
        #
        # Identical without the prefix. That is not academic here: these
        # are shell command strings, and a multi-line command in a declared
        # row would let a two-command list masquerade as the one-command
        # list an operator confirmed.
        rh = self._releasehash()
        self.assertNotEqual(rh.pre_tag_digest(["a\nb"]),
                            rh.pre_tag_digest(["a", "b"]))
        # And the plain adjacent-content case, kept for completeness.
        self.assertNotEqual(rh.pre_tag_digest(["ab", "c"]),
                            rh.pre_tag_digest(["a", "bc"]))

    def test_pre_tag_hash_never_raises_on_junk(self):
        # Mechanism invariant: this runs inside a release lane, so a
        # malformed row must degrade rather than raise mid-release.
        rh = self._releasehash()
        for junk in (None, 42, "a string", [None, 7], {}):
            self.assertEqual(len(rh.pre_tag_digest(junk)), 64)

    def test_pre_tag_hash_state_machine_over_a_real_marker(self):
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            original = ["python3 checks/a.py"]
            self.assertEqual(
                rh.confirmation_state(root, "app", original), rh.NEVER)
            rh.record_confirmation(root, "app", rh.pre_tag_digest(original))
            self.assertEqual(
                rh.confirmation_state(root, "app", original), rh.CONFIRMED)
            # THE case this exists for: the executed commands changed after
            # somebody confirmed them.
            self.assertEqual(
                rh.confirmation_state(root, "app", ["python3 checks/evil.py"]),
                rh.CHANGED)
            # Appending is a change too -- a lane that only compared the
            # first entry would admit a smuggled second command.
            self.assertEqual(
                rh.confirmation_state(root, "app", original + ["python3 x.py"]),
                rh.CHANGED)

    def test_pre_tag_hash_confirmation_is_per_target(self):
        # A multi-target repo confirming one row must not thereby confirm
        # its siblings -- that would let a target's commands change under
        # a confirmation earned by a different target entirely.
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            commands = ["python3 checks/a.py"]
            rh.record_confirmation(root, "ca", rh.pre_tag_digest(commands))
            self.assertEqual(rh.confirmation_state(root, "ca", commands), rh.CONFIRMED)
            self.assertEqual(rh.confirmation_state(root, "ca-pi", commands), rh.NEVER)

    def test_pre_tag_hash_reports_no_commands_distinctly_from_confirmed(self):
        # A row declaring nothing has nothing to confirm. Reporting it as
        # "confirmed" would claim an operator approved content that does
        # not exist; both proceed, but only one is a claim about review.
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(rh.confirmation_state(root, "app", []), rh.NO_COMMANDS)
            self.assertNotEqual(rh.NO_COMMANDS, rh.CONFIRMED)

    def test_pre_tag_hash_unreadable_marker_reads_as_never_confirmed(self):
        # Conservative direction: an empty or unreadable marker prompts
        # rather than admits.
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            path = rh.confirmation_path(root, "app")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("   " + os.linesep)
            self.assertEqual(
                rh.confirmation_state(root, "app", ["python3 a.py"]), rh.NEVER)

    def test_pre_tag_marker_names_do_not_collide_across_targets(self):
        # CodeRabbit MAJOR, confirmed. The sanitizer folded every
        # disallowed character to "_", so the legal, distinct target names
        # `a.b` and `a_b` shared one marker file -- confirming either
        # silently confirmed the other, which is exactly the cross-target
        # confirmation `confirmation_path` promises not to do.
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            collide_pairs = [("a.b", "a_b"), ("x/y", "x_y"), ("p q", "p_q")]
            for left, right in collide_pairs:
                with self.subTest(pair=(left, right)):
                    self.assertNotEqual(rh.confirmation_path(root, left),
                                        rh.confirmation_path(root, right))
            # Deterministic: the same name must resolve to the same marker
            # across calls, or a confirmation could never be read back.
            self.assertEqual(rh.confirmation_path(root, "a.b"),
                             rh.confirmation_path(root, "a.b"))

    def test_confirming_one_target_does_not_confirm_its_collider(self):
        # The consequence, driven end to end rather than asserted on paths.
        rh = self._releasehash()
        cmds = ["python3 check.py"]
        with tempfile.TemporaryDirectory() as root:
            rh.record_confirmation(root, "a.b", rh.pre_tag_digest(cmds))
            self.assertEqual(rh.confirmation_state(root, "a.b", cmds), rh.CONFIRMED)
            self.assertEqual(rh.confirmation_state(root, "a_b", cmds), rh.NEVER)

    def test_pre_tag_hash_module_is_vendored_byte_identically(self):
        # A-2.10 ships through sync-core, so the plugins' copies must match
        # core/pysrc exactly -- a lane running a stale vendored copy would
        # confirm against a different digest construction.
        source = os.path.join(REPO_ROOT, "core", "pysrc", "releasehash.py")
        with open(source, "rb") as fh:
            canonical = fh.read()
        seen = 0
        for plugin in ("ca", "ca-codex", "ca-pi"):
            vendored = os.path.join(REPO_ROOT, "plugins", plugin, "hooks",
                                    "releasehash.py")
            if not os.path.isfile(vendored):
                continue
            seen += 1
            with open(vendored, "rb") as fh:
                self.assertEqual(fh.read(), canonical, f"{plugin} copy drifted")
        self.assertEqual(seen, 3, "releasehash.py must vendor to all three plugins")

    # ---- check-manifests: the all-paths equality guard (run 12 HIGH) ----
    def test_classify_short_circuits_before_comparing_versions_on_a_fresh_publish(self):
        # The defect that motivated check-manifests, pinned as a FACT about
        # classify rather than a claim in prose. The skill asserted this
        # comparison catches a partial bump; it cannot, because
        # `if not tag_exists: return "publish_fresh"` runs first.
        head = "a" * 40
        self.assertEqual(
            core_releaselib.classify_publish_state(
                False, "", head, "1.4.3", "1.1.0", False),
            "publish_fresh",
            "if this ever returns abort_mismatch, classify grew a fresh-path "
            "version check and the check-manifests rationale needs revisiting")
        self.assertEqual(
            core_releaselib.classify_publish_state(
                True, head, head, "1.4.3", "1.1.0", False),
            "abort_mismatch")

    def test_manifest_version_reads_json_and_toml_and_refuses_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            js = os.path.join(tmp, "package.json")
            with open(js, "w") as fh:
                fh.write('{"version": "1.2.3"}')
            self.assertEqual(core_releaselib._manifest_version(js), "1.2.3")
            tm = os.path.join(tmp, "pyproject.toml")
            with open(tm, "w") as fh:
                fh.write('[project]\nversion = "4.5.6"\n')
            self.assertEqual(core_releaselib._manifest_version(tm), "4.5.6")
            # An unknown extension is "no comparison happened", not a guess.
            other = os.path.join(tmp, "version.txt")
            with open(other, "w") as fh:
                fh.write("7.8.9\n")
            self.assertIsNone(core_releaselib._manifest_version(other))
            self.assertIsNone(
                core_releaselib._manifest_version(os.path.join(tmp, "missing.json")))

    def test_manifest_version_never_raises_on_malformed_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "package.json")
            with open(bad, "w") as fh:
                fh.write("{not json")
            self.assertIsNone(core_releaselib._manifest_version(bad))

    def _manifest_fixture(self, tmp, versions):
        """A consumer declaring one manifest per entry in `versions`."""
        root = os.path.join(tmp, "consumer")
        os.makedirs(os.path.join(root, ".codearbiter"))
        lines = ["[app]", "prefix: v", "changelog: CHANGELOG.md", "payload: ."]
        for i, version in enumerate(versions):
            rel = f"m{i}.json"
            with open(os.path.join(root, rel), "w") as fh:
                fh.write('{"version": "%s"}' % version)
            lines.append(f"manifest: {rel}")
        with open(os.path.join(root, ".codearbiter", "release-targets.md"), "w") as fh:
            fh.write("<!-- release-targets -->\n" + "\n".join(lines)
                     + "\n<!-- /release-targets -->\n")
        return root

    def _run_check_manifests(self, root, version):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "check-manifests", "app", version],
            cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True)

    def test_check_manifests_passes_when_every_declared_path_agrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._manifest_fixture(tmp, ["1.4.3", "1.4.3"])
            self.assertEqual(self._run_check_manifests(root, "1.4.3").returncode, 0)

    def test_check_manifests_catches_a_PARTIAL_bump_and_names_the_laggard(self):
        # The exact fresh-publish hole: one path bumped, one left behind.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._manifest_fixture(tmp, ["1.4.3", "1.1.0"])
            proc = self._run_check_manifests(root, "1.4.3")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("m1.json", proc.stderr)
            self.assertNotIn("m0.json", proc.stderr)

    def test_check_manifests_exit_2_is_unparseable_not_disagreeing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._manifest_fixture(tmp, ["1.4.3"])
            with open(os.path.join(root, "m0.json"), "w") as fh:
                fh.write("{not json")
            proc = self._run_check_manifests(root, "1.4.3")
            self.assertEqual(
                proc.returncode, 2,
                "an unreadable manifest must not be reported as a version "
                "disagreement -- no comparison happened")
            self.assertIn("NOT the same answer", proc.stderr)

    # ---- Conventional-Commits classification + footer scan ----
    def test_breaking_marker_is_major_with_and_without_a_scope(self):
        # THE defect this helper exists for. Run 11's agent wrote
        # `subject.split('(')[0].split(':')[0].rstrip('!')`, which strips
        # the `!` BEFORE anything checks for it -- so a breaking change
        # ships as a minor, or as no release at all.
        for subject in ("feat!: drop the legacy endpoint",
                        "feat(api)!: drop the legacy endpoint",
                        "chore!: rip out the vendored copy"):
            with self.subTest(subject=subject):
                self.assertEqual(
                    core_releaselib.classify_commit(subject)["bump"], "major")
                self.assertTrue(core_releaselib.classify_commit(subject)["breaking"])

    def test_a_breaking_chore_still_bumps_and_is_footer_checked(self):
        # `chore` is not in the bumping-type list, so a type-list check
        # misses `chore!:` entirely -- it bumps major AND is therefore
        # subject to the footer rule.
        window = core_releaselib.classify_window(
            [{"sha": "a" * 40, "subject": "chore!: rip it out", "body": ""}])
        self.assertEqual(window["bump"], "major")
        self.assertEqual(len(window["missing_footer"]), 1)

    def test_breaking_change_footer_must_start_a_line(self):
        # Prose merely DISCUSSING a breaking change must not bump major.
        self.assertEqual(
            core_releaselib.classify_commit(
                "docs: prose", "this mentions a BREAKING CHANGE: inline")["bump"],
            "none")
        self.assertEqual(
            core_releaselib.classify_commit(
                "docs: prose", "BREAKING CHANGE: config moved")["bump"],
            "major")

    def test_ordinary_types_map_to_their_documented_bumps(self):
        for subject, want in (("feat(api): add", "minor"), ("fix: a bug", "patch"),
                              ("perf: faster", "patch"), ("refactor(core): split", "patch"),
                              ("docs: prose", "none"), ("chore: routine", "none"),
                              ("test: cover", "none"), ("ci: pipeline", "none")):
            with self.subTest(subject=subject):
                self.assertEqual(
                    core_releaselib.classify_commit(subject)["bump"], want)

    def test_a_non_conventional_subject_cannot_bump(self):
        # An unparseable subject degrades to "no bump", the safe direction.
        for subject in ("not conventional at all", "", "feat missing colon"):
            self.assertEqual(
                core_releaselib.classify_commit(subject)["bump"], "none")

    def test_classify_commit_never_raises_on_junk(self):
        for subject, body in ((None, None), (42, []), ({}, 7)):
            self.assertEqual(
                core_releaselib.classify_commit(subject, body)["bump"], "none")

    def test_window_bump_is_the_highest_precedence_present(self):
        commits = [
            {"sha": "a" * 40, "subject": "fix: a", "body": "CHANGELOG: x"},
            {"sha": "b" * 40, "subject": "feat: b", "body": "CHANGELOG: y"},
            {"sha": "c" * 40, "subject": "docs: c", "body": ""},
        ]
        self.assertEqual(core_releaselib.classify_window(commits)["bump"], "minor")

    def test_missing_footer_lists_only_bumping_commits_in_window_order(self):
        commits = [
            {"sha": "1" * 40, "subject": "feat: a", "body": ""},           # bumping, no footer
            {"sha": "2" * 40, "subject": "docs: b", "body": ""},           # non-bumping
            {"sha": "3" * 40, "subject": "fix: c", "body": "CHANGELOG: z"},  # has footer
            {"sha": "4" * 40, "subject": "perf: d", "body": ""},           # bumping, no footer
        ]
        missing = core_releaselib.classify_window(commits)["missing_footer"]
        self.assertEqual([m["sha"][0] for m in missing], ["1", "4"])

    def test_parse_window_log_round_trips_the_prescribed_format(self):
        text = ("aaaaaaa\nfeat: one\nCHANGELOG: first\n----\n"
                "bbbbbbb\nfix: two\n\n----\n")
        entries = core_releaselib.parse_window_log(text)
        self.assertEqual([e["sha"] for e in entries], ["aaaaaaa", "bbbbbbb"])
        self.assertEqual(entries[0]["subject"], "feat: one")
        self.assertIn("CHANGELOG: first", entries[0]["body"])

    def test_classify_window_cli_exit_codes_discriminate(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def run(text):
            return subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
                input=text, capture_output=True, text=True, env=env)

        clean = run("aaaaaaa\nfeat: one\nCHANGELOG: first\n----\n")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stdout.splitlines()[0], "minor")

        blocked = run("bbbbbbb\nfeat: one\n\n----\n")
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("[NEEDS-TRIAGE] bbbbbbb feat: one", blocked.stdout)

        nonbumping = run("ccccccc\ndocs: prose\n\n----\n")
        self.assertEqual(nonbumping.returncode, 2, nonbumping.stderr)
        self.assertEqual(nonbumping.stdout.splitlines()[0], "none")

    # ---- A-5.5: the first-release baseline ----
    def test_first_release_baseline_returns_the_adoption_commit(self):
        self.assertEqual(
            core_releaselib.first_release_baseline("f3394f8\n"), "f3394f8")

    def test_first_release_baseline_takes_the_EARLIEST_of_several(self):
        # git log prints newest-first, so the LAST line is the earliest
        # addition. A file added, deleted and re-added yields two entries;
        # taking the newest would treat the re-adoption as the boundary and
        # silently drop every commit in between -- the same class of quiet
        # history loss this function exists to prevent.
        text = "bbbbbbb\naaaaaaa\n"      # newest first
        self.assertEqual(core_releaselib.first_release_baseline(text), "aaaaaaa")

    def test_first_release_baseline_is_empty_when_never_adopted(self):
        # A repo that never onboarded is a NORMAL answer, not an error.
        for text in ("", "\n", "   \n\n"):
            self.assertEqual(core_releaselib.first_release_baseline(text), "")

    def test_first_release_baseline_never_raises_on_junk(self):
        # Mechanism-function invariant: degrade to the refusing answer.
        for junk in (None, 42, [], "not-a-sha\n", "zzz\n"):
            self.assertEqual(core_releaselib.first_release_baseline(junk), "")

    def test_first_release_baseline_tolerates_trailing_fields(self):
        # `--format=%H` alone is what the prose names, but an operator who
        # adds a date or subject must not get a mangled sha back.
        self.assertEqual(
            core_releaselib.first_release_baseline("f3394f8 2026-06-04 Phase 2\n"),
            "f3394f8")

    def test_adoption_commit_cli_prints_the_sha_and_exits_0(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "adoption-commit"],
            input="f3394f8\n", capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "f3394f8")

    def test_adoption_commit_cli_exits_0_with_no_output_when_never_adopted(self):
        # Exit 0 deliberately: a non-zero here would break a `set -e` lane
        # on the ordinary path, and the caller distinguishes the cases by
        # empty output exactly as it already does for `peel-tag`.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "adoption-commit"],
            input="", capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_run_pre_tag_catches_a_mutation_of_an_ALREADY_MODIFIED_file(self):
        # HIGH, run 10. The assertion was a set difference over porcelain
        # LINES, so a command mutating a file that was already ` M`
        # produced a byte-identical line and fell out of the difference --
        # exit 0, content changed. The blind spot covered exactly
        # $CHANGELOG and $MANIFEST: the two files Phase 1 touches
        # immediately before this step, and the two that actually ship
        # (one into the tag message and the Release notes, the other as
        # the version the tag claims).
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [], dirty=True)
            injector = os.path.join(root, "inject.py")
            with open(injector, "w") as fh:
                fh.write("f=open('CHANGELOG.md','a')\n"
                         "f.write('INJECTED'+chr(10))\nf.close()\n")
            targets = os.path.join(root, ".codearbiter", "release-targets.md")
            with open(targets, encoding="utf-8") as fh:
                text = fh.read()
            with open(targets, "w", encoding="utf-8", newline="") as fh:
                fh.write(text.replace("<!-- /release-targets -->",
                                      "pre-tag: python inject.py\n<!-- /release-targets -->"))
            changelog = os.path.join(root, "CHANGELOG.md")
            with open(changelog, "rb") as fh:
                before = fh.read()
            proc = self._run_pre_tag(root)
            with open(changelog, "rb") as fh:
                after = fh.read()
            self.assertNotEqual(
                before, after,
                "the fixture must actually mutate the file, or this test "
                "cannot distinguish a working guard from a broken one")
            self.assertEqual(
                proc.returncode, 6,
                "a command that appends to the already-modified CHANGELOG "
                "must be caught; a porcelain-line comparison cannot see it "
                f"(stdout={proc.stdout} stderr={proc.stderr})")
            self.assertIn("CHANGELOG.md", proc.stderr)

    def test_run_pre_tag_runs_commands_in_the_project_root(self):
        # MEDIUM, run 9: commands used to run in the inherited cwd while
        # the declaration came from CLAUDE_PROJECT_DIR, so a check could
        # pass having inspected a DIFFERENT repository. The subprocess
        # above is deliberately launched from the system temp dir.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(
                tmp, ['python -c "import json;print(json.load(open(\'package.json\'))[\'version\'])"'],
                dirty=True)
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("1.1.0", proc.stdout)

    def test_semver_greater_bad_invocation_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["semver-greater", "1.0.0"])
        self.assertEqual(rc, 2)

    def test_usage_banner_names_every_implemented_subcommand(self):
        # LOW (run 6): `dates-match` was implemented and working but absent
        # from the tool's own help, so an operator checking `--help`-shaped
        # output would conclude the skill's instruction was stale. Derived
        # from the dispatch table rather than a hand-list, so a future
        # subcommand cannot be added without appearing here.
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            core_releaselib.main([])
        banner = err.getvalue()
        for name in ("tag-prefix", "list-targets", "last-tag", "notes-match",
                     "dates-match", "semver-greater", "classify", "peel-tag",
                     "backfill-detect"):
            self.assertIn(
                name, banner,
                f"{name!r} is implemented but missing from the usage banner")

    def test_dates_match_bad_invocation_exits_2(self):
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["dates-match", "only-one-arg"])
        self.assertEqual(rc, 2)

    def test_default_targets_path_prefers_claude_project_dir_env(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = os.path.join("some", "project", "root")
        try:
            self.assertEqual(
                core_releaselib.default_targets_path(),
                os.path.join("some", "project", "root",
                             ".codearbiter", "release-targets.md"))
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old

    def test_default_targets_path_falls_back_to_cwd(self):
        old = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        try:
            self.assertEqual(
                core_releaselib.default_targets_path(),
                os.path.join(os.getcwd(), ".codearbiter", "release-targets.md"))
        finally:
            if old is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old

    def test_tag_prefix_resolves_via_claude_project_dir_env_with_no_flag(self):
        # The exact shape a consumer session actually invokes this in: no
        # --targets-file at all, resolution purely from the env var the
        # harness sets.
        import io, contextlib
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".codearbiter"), exist_ok=True)
            with open(os.path.join(tmp, ".codearbiter", "release-targets.md"),
                      "w", encoding="utf-8") as fh:
                fh.write(self.APP_BLOCK)
            os.environ["CLAUDE_PROJECT_DIR"] = tmp
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = core_releaselib.main(["tag-prefix", "app"])
                self.assertEqual(rc, 0)
                self.assertEqual(out.getvalue().strip(), "v")
            finally:
                if old is None:
                    os.environ.pop("CLAUDE_PROJECT_DIR", None)
                else:
                    os.environ["CLAUDE_PROJECT_DIR"] = old

    def test_last_tag_and_notes_match_and_classify_all_dispatch(self):
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            stdin = sys.stdin
            sys.stdin = io.StringIO("v1.0.0 v1.1.0 v1.1.0-beta.1")
            try:
                rc = core_releaselib.main(["last-tag", "v"])
            finally:
                sys.stdin = stdin
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "v1.1.0")

        with tempfile.TemporaryDirectory() as tmp:
            notes_path = os.path.join(tmp, "notes.md")
            with open(notes_path, "w", encoding="utf-8") as fh:
                fh.write("## [1.1.0] - 2026-07-31\n\n### Added\n\n- a thing\n")
            self.assertEqual(
                core_releaselib.main(["notes-match", "v1.1.0", notes_path]), 0)
            self.assertEqual(
                core_releaselib.main(["notes-match", "v9.9.9", notes_path]), 1)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = core_releaselib.main(
                ["classify", "false", "-", "-", "1.1.0", "1.1.0", "false"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "publish_fresh")

    # HIGH-1 (adversarial review 2026-07-31): before this fix, this module's
    # own CLI had NO `peel-tag` subcommand at all -- `.github/scripts/
    # _releaselib.py` (the CI-only shim) had one, but the CONSUMER-facing
    # copy (this file, vendored byte-identically into every plugin's
    # `hooks/`) did not. A caller shelling out to the vendored copy had no
    # sanctioned way to turn an annotated tag into the commit it names, and
    # would reach for a bare `git rev-parse <tag>` instead -- which returns
    # the tag OBJECT, not the commit, and silently misclassifies a healthy
    # tag as `abort_mismatch`.
    TAG_OBJ = "1" * 40
    COMMIT = "2" * 40

    def test_peel_tag_dispatches_and_peels_an_annotated_tag(self):
        import io, contextlib
        # Real `git show-ref --tags -d` / `git ls-remote --tags` shape: the
        # tag's own object id on one line, the peeled `^{}` commit on the
        # next -- verified against a real repo (v2.8.13) before this test
        # was written, not merely asserted from the docstring.
        stdin_text = (f"{self.TAG_OBJ} refs/tags/v2.6.0\n"
                      f"{self.COMMIT} refs/tags/v2.6.0^{{}}\n")
        out = io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(["peel-tag", "v2.6.0"])
        finally:
            sys.stdin = stdin
        self.assertEqual(rc, 0)
        # This is the exact assertion a mutant that reverted `peel_tag`'s
        # `peeled or direct` ordering (printing the RAW tag-object id
        # instead of the peeled commit) would fail: it pins the PEELED
        # value, not merely "some tag-shaped output was printed".
        self.assertEqual(out.getvalue().strip(), self.COMMIT)
        self.assertNotEqual(out.getvalue().strip(), self.TAG_OBJ)

    def test_peel_tag_prints_empty_for_an_absent_tag(self):
        import io, contextlib
        out = io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(["peel-tag", "v9.9.9"])
        finally:
            sys.stdin = stdin
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "")

    def test_a_naive_rev_parse_value_misclassifies_a_healthy_tag_but_the_peeled_value_does_not(self):
        # This is the finding itself, pinned as one test with the contrast
        # as the evidence (HIGH-1): the SAME healthy annotated tag, at the
        # SAME HEAD commit, fed to `classify` two different ways.
        #
        #   - the value a bare `git rev-parse <tag>` would produce (the tag
        #     OBJECT id) -> `abort_mismatch`, a hard STOP on a release that
        #     is actually fine;
        #   - the value `peel-tag` produces (the commit the tag names) ->
        #     `resume_publish` (or `publish_fresh`/`already_published`
        #     depending on release state), never a mismatch.
        #
        # `classify_publish_state` itself is not the defect -- feeding it
        # the tag object IS a mismatch by its own contract. The defect is
        # procedural: which value a caller derives. This test proves the
        # skill's newly-documented derivation (peel-tag) resolves to the
        # non-aborting answer for a tag that is genuinely healthy, where
        # the naive derivation would not.
        head_sha = self.COMMIT
        manifest_version = tag_version = "2.6.0"

        # The naive value: an annotated tag's own object id.
        naive_tag_sha = self.TAG_OBJ
        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha=naive_tag_sha, head_sha=head_sha,
                tag_version=tag_version, manifest_version=manifest_version,
                release_is_nondraft=False),
            "abort_mismatch")

        # The correct value: peel-tag's output for the SAME tag/HEAD.
        stdin_text = (f"{self.TAG_OBJ} refs/tags/v2.6.0\n"
                      f"{head_sha} refs/tags/v2.6.0^{{}}\n")
        import io, contextlib
        out = io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(["peel-tag", "v2.6.0"])
        finally:
            sys.stdin = stdin
        self.assertEqual(rc, 0)
        peeled_tag_sha = out.getvalue().strip()
        self.assertEqual(peeled_tag_sha, head_sha)

        self.assertEqual(
            core_releaselib.classify_publish_state(
                tag_exists=True, tag_sha=peeled_tag_sha, head_sha=head_sha,
                tag_version=tag_version, manifest_version=manifest_version,
                release_is_nondraft=False),
            "resume_publish")

    def test_consumer_shaped_subprocess_invocation_exits_zero(self):
        # The literal verification named in the plan: the mechanism's CLI
        # runs as a standalone script (no sibling `core/pysrc/` import
        # available), resolving `tag-prefix ca` against a declared file it
        # finds via CLAUDE_PROJECT_DIR — mirroring the vendored copy at
        # `${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py`, which is executed
        # from a directory that is NOT the consumer's project root either.
        # Run twice: once against a scratch consumer-shaped tree (no fact
        # from this repository at all), once against this repo's own vendored
        # copy and its own declared file, so both readings of "consumer-
        # shaped" are covered rather than asserted only in the abstract.
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = os.path.join(tmp, "plugin-root")
            project_root = os.path.join(tmp, "project-root")
            os.makedirs(plugin_root, exist_ok=True)
            os.makedirs(os.path.join(project_root, ".codearbiter"), exist_ok=True)
            vendored = os.path.join(plugin_root, "_releaselib.py")
            with open(_CORE_RELEASELIB_PATH, "rb") as src, open(vendored, "wb") as dst:
                dst.write(src.read())
            with open(os.path.join(project_root, ".codearbiter",
                                    "release-targets.md"), "w", encoding="utf-8") as fh:
                fh.write(self.APP_BLOCK)
            env = dict(os.environ)
            env["CLAUDE_PROJECT_DIR"] = project_root
            result = subprocess.run(
                [sys.executable, vendored, "tag-prefix", "app"],
                cwd=plugin_root, capture_output=True, encoding="utf-8",
                env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "v")

        # This repo's own vendored plugins/ca copy against its own real
        # .codearbiter/release-targets.md, cwd = the plugin's hooks/ dir
        # (never the project root) so only the CLAUDE_PROJECT_DIR/cwd-fallback
        # resolution logic under test can be finding the right file.
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = REPO_ROOT
        vendored_ca = os.path.join(REPO_ROOT, "plugins", "ca", "hooks", "_releaselib.py")
        result = subprocess.run(
            [sys.executable, vendored_ca, "tag-prefix", "ca"],
            cwd=os.path.dirname(vendored_ca), capture_output=True,
            encoding="utf-8", env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "v")


class ThisRepoRowsTest(unittest.TestCase):
    """A-1.10 (T-26): this repository's own `.codearbiter/release-targets.md`
    loads as four rows (`this_repo_rows`) whose `target` and `prefix` equal
    an INDEPENDENT oracle restated in this class (the shim's own map is now
    derived from this same file, so comparing against it would be
    circular), and every one of the four declares
    `provenance-manifest` — a maintainer decision (2026-07-31) tighter than
    the spec's own grammar example, which shows the field on `ca` alone. An
    absent field silently skips the tag-provenance recording step (A-3.5), so
    three of four release lanes would otherwise stop recording published tags
    with no signal at all — a behavior change this migration must not
    introduce. Every method name below carries `this_repo_rows` so `-k
    this_repo_rows` (the verification command named in the plan) selects the
    whole class."""

    REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
    TARGETS_PATH = os.path.join(REPO_ROOT, ".codearbiter", "release-targets.md")

    @classmethod
    def setUpClass(cls):
        cls.rows = core_releaselib.load_targets(cls.TARGETS_PATH)
        cls.by_target = {row["target"]: row for row in cls.rows}

    def test_this_repo_rows_exactly_four_load(self):
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(set(self.by_target), {"ca", "ca-codex", "ca-sandbox", "ca-pi"})

    # The independent oracle. This USED to be a comparison against the
    # shim's RELEASE_TAG_PREFIXES literal, which was a genuinely separate
    # source. T-46 made the shim derive that map from this very file, so
    # the old comparison became CIRCULAR -- the declared file checked
    # against itself, passing no matter what either said. Restating the
    # expectation here keeps a second source, now owned by the test.
    PRE_CHANGE_NAMESPACES = {
        "ca": "v",
        "ca-codex": "ca-codex-v",
        "ca-sandbox": "ca-sandbox-v",
        "ca-pi": "ca-pi-v",
    }

    def test_this_repo_rows_target_and_prefix_equal_the_pre_change_constants(self):
        # Both directions against the oracle above: a renamed target, a
        # changed namespace, an added row, or a dropped row all fail here.
        for target, prefix in self.PRE_CHANGE_NAMESPACES.items():
            with self.subTest(target=target):
                self.assertIn(target, self.by_target)
                self.assertEqual(self.by_target[target]["prefix"], prefix)
        self.assertEqual({row["target"] for row in self.rows},
                         set(self.PRE_CHANGE_NAMESPACES))

    def test_this_repo_rows_the_shim_derivation_matches_the_oracle(self):
        # The derivation T-46 introduced, checked against the same
        # independent oracle rather than against its own input -- so a
        # broken derivation (empty map, wrong key, first-row-only) fails
        # here instead of agreeing with itself.
        self.assertEqual(_releaselib.release_tag_prefixes(),
                         self.PRE_CHANGE_NAMESPACES)
        self.assertEqual(tuple(_releaselib.RELEASE_TARGETS),
                         ("ca", "ca-codex", "ca-sandbox", "ca-pi"))

    def test_this_repo_rows_every_row_declares_a_provenance_manifest(self):
        for target, row in self.by_target.items():
            with self.subTest(target=target):
                self.assertEqual(row["provenance_manifest"], ".github/published-tags.json")

    def test_this_repo_rows_only_ca_is_latest_eligible(self):
        for target, row in self.by_target.items():
            with self.subTest(target=target):
                self.assertEqual(row["latest_eligible"], target == "ca")

    def test_this_repo_rows_ca_pi_declares_two_manifests_and_excludes_tools(self):
        row = self.by_target["ca-pi"]
        self.assertEqual(
            row["manifest"], ["plugins/ca-pi/package.json", "package.json"])
        self.assertEqual(row["payload_exclude"], ["plugins/ca-pi/tools/"])

    # HIGH-3 (adversarial review 2026-07-31): the generated repo-root
    # `package.json` is declarable, not folklore -- `generated-manifest`
    # names it as a subset of `manifest` and `generate` is the row's own
    # regeneration command, mirroring the `rebuild`/`artifacts` pairing.
    def test_this_repo_rows_ca_pi_root_manifest_is_declared_generated(self):
        row = self.by_target["ca-pi"]
        self.assertEqual(row["generated_manifest"], ["package.json"])
        # The generated entry must also be a real manifest entry -- declaring
        # a path as generated without also declaring it a manifest would
        # mean nothing ever asserts its version, silently defeating the
        # whole point of naming it.
        self.assertIn("package.json", row["manifest"])
        self.assertEqual(row["generate"], "python3 tools/build-host-packages.py")

    def test_this_repo_rows_ca_declares_a_display_name(self):
        # M-1 (adversarial review 2026-07-31): the Phase-3 Release title has
        # no grammar key to source a "display name" from without this field
        # -- `ca` releases as "codeArbiter X.Y.Z", not "ca X.Y.Z".
        self.assertEqual(self.by_target["ca"]["display_name"], "codeArbiter")

    def test_this_repo_rows_only_ca_declares_a_display_name(self):
        # Every other target's display name defaults to $TARGET itself
        # (undeclared), which is already correct for `ca-codex`/`ca-sandbox`/
        # `ca-pi` -- their tag prefix and target name already match the name
        # a Release title should show.
        for target, row in self.by_target.items():
            if target == "ca":
                continue
            with self.subTest(target=target):
                self.assertIsNone(row["display_name"])

    def test_this_repo_rows_every_manifest_and_changelog_path_exists_on_disk(self):
        for target, row in self.by_target.items():
            for rel in [row["changelog"], *row["manifest"]]:
                with self.subTest(target=target, path=rel):
                    self.assertTrue(
                        os.path.isfile(os.path.join(self.REPO_ROOT, rel)),
                        f"{target}: declared path {rel!r} does not exist on disk")

    # -- M-2 (adversarial review, 2026-07-31): "6 of 6 row mutants survived,
    # including replacing ca-pi's pre-tag with `rm -rf plugins/`, pointing
    # payload at the wrong plugin, and deleting an artifact line." The
    # methods below assert this repo's declared executable input by exact
    # content, not merely by existence, closing each named mutant. --

    # Sourced from plugins/ca/skills/release/SKILL.md's own Targets table
    # (the authoritative source .codearbiter/release-targets.md transcribes)
    # -- an EXACT list per target, so a deleted or reordered artifact line
    # cannot survive: "each artifacts path exists" alone does not catch a
    # deletion, since every surviving path in a shortened list still exists.
    _EXPECTED_ARTIFACTS = {
        "ca": ["plugins/ca/tools/farm.js"],
        "ca-codex": [],
        "ca-sandbox": [
            "plugins/ca-sandbox/tools/sandbox.js",
            "plugins/ca-sandbox/tools/claude-inside.js",
        ],
        "ca-pi": [
            "plugins/ca-pi/extensions/codearbiter.js",
            "plugins/ca-pi/extensions/codearbiter-child.js",
        ],
    }

    def test_this_repo_rows_artifacts_exactly_match_the_declared_set(self):
        for target, expected in self._EXPECTED_ARTIFACTS.items():
            with self.subTest(target=target):
                self.assertEqual(self.by_target[target]["artifacts"], expected)

    def test_this_repo_rows_every_artifact_path_exists_on_disk(self):
        for target, row in self.by_target.items():
            for rel in row["artifacts"]:
                with self.subTest(target=target, path=rel):
                    self.assertTrue(
                        os.path.isfile(os.path.join(self.REPO_ROOT, rel)),
                        f"{target}: declared artifact {rel!r} does not exist on disk")

    def test_this_repo_rows_payload_is_scoped_to_its_own_target(self):
        # Catches "payload points at the wrong plugin": every target's
        # declared payload must be `plugins/<target>/` -- its OWN directory,
        # never a sibling's.
        for target, row in self.by_target.items():
            with self.subTest(target=target):
                self.assertEqual(row["payload"], f"plugins/{target}/")

    def test_this_repo_rows_rebuild_follows_the_cd_and_run_convention(self):
        # HIGH-4: a declared `rebuild` with no `cd` (e.g. the pre-fix
        # `node plugins/ca-pi/tools/build.mjs`) resolves its own
        # relative-path inputs against the repo root rather than the
        # rebuild directory, and fails only at release time. Every declared
        # `rebuild` must be `cd <existing dir> && <cmd>`, with the entrypoint
        # `cmd` names resolving relative to that directory -- structurally,
        # never by actually invoking `npm run build` / `node build.mjs`
        # here, which belongs to the per-plugin `tools` CI jobs, not a suite
        # also run on this repo's hooks matrix.
        import json as _json
        import re as _re
        cd_re = _re.compile(r"^cd (\S+) && (.+)$")
        for target, row in self.by_target.items():
            rebuild = row["rebuild"]
            if rebuild is None:
                continue
            with self.subTest(target=target):
                match = cd_re.match(rebuild)
                self.assertIsNotNone(
                    match,
                    f"{target}: rebuild {rebuild!r} does not follow "
                    "'cd <dir> && <cmd>'")
                rel_dir, cmd = match.groups()
                abs_dir = os.path.join(self.REPO_ROOT, rel_dir)
                self.assertTrue(
                    os.path.isdir(abs_dir), f"{target}: {rel_dir!r} does not exist")
                if cmd.startswith("node "):
                    entry = cmd[len("node "):].strip()
                    self.assertTrue(
                        os.path.isfile(os.path.join(abs_dir, entry)),
                        f"{target}: rebuild entrypoint {entry!r} does not exist "
                        f"under {rel_dir!r}")
                elif cmd == "npm run build":
                    package_json = os.path.join(abs_dir, "package.json")
                    self.assertTrue(
                        os.path.isfile(package_json),
                        f"{target}: no package.json under {rel_dir!r}")
                    with open(package_json, encoding="utf-8") as fh:
                        manifest = _json.load(fh)
                    self.assertIn(
                        "build", manifest.get("scripts", {}),
                        f"{target}: package.json under {rel_dir!r} declares no "
                        "'build' script")
                else:
                    self.fail(f"{target}: unrecognised rebuild command shape {cmd!r}")

    # The review's own literal wording ("each pre-tag entry names a script
    # under .github/scripts/") is falsified by ca-pi's real, CORRECT row --
    # `python3 tools/build-host-packages.py --check`, under the repo-root
    # `tools/`, not `.github/scripts/`. The allowlist is therefore BOTH
    # roots, not one.
    _PRE_TAG_ALLOWED_ROOTS = (".github/scripts/", "tools/")
    # check_command_catalog.py was T-34's one declared, KNOWN-pending forward
    # reference (PENDING, not yet authored). HIGH-2 (adversarial review
    # 2026-07-31) authored it, so the forward reference is retired here in
    # the SAME commit -- leaving it in _PRE_TAG_KNOWN_PENDING would now
    # assert the opposite of what just became true (this class's own
    # sibling assertion below, `self.assertFalse(exists, ...)`, exists
    # precisely to catch that and force this exact edit).
    _PRE_TAG_KNOWN_PENDING = frozenset()

    def test_this_repo_rows_pre_tag_scripts_resolve_under_an_allowlisted_root(self):
        import re as _re
        cmd_re = _re.compile(r"^python3\s+(\S+\.py)\b")
        for target, row in self.by_target.items():
            for command in row["pre_tag"]:
                with self.subTest(target=target, command=command):
                    match = cmd_re.match(command)
                    self.assertIsNotNone(
                        match,
                        f"{target}: pre-tag {command!r} is not a "
                        "'python3 <script>[.py] ...' command")
                    script = match.group(1)
                    self.assertTrue(
                        any(script.startswith(root)
                            for root in self._PRE_TAG_ALLOWED_ROOTS),
                        f"{target}: pre-tag script {script!r} is outside the "
                        f"allowlisted roots {self._PRE_TAG_ALLOWED_ROOTS}")
                    exists = os.path.isfile(os.path.join(self.REPO_ROOT, script))
                    if script in self._PRE_TAG_KNOWN_PENDING:
                        self.assertFalse(
                            exists,
                            f"{target}: {script!r} is listed as a KNOWN-pending "
                            "(T-34) forward reference but now exists on disk -- "
                            "remove it from _PRE_TAG_KNOWN_PENDING")
                    else:
                        self.assertTrue(
                            exists,
                            f"{target}: pre-tag script {script!r} does not exist "
                            "on disk")


# --------------------------------------------------------------------------- #
# The finding that outranks all of them (adversarial review 2026-07-31): a
# mutation campaign deleted governance prose from the release skill payloads
# and re-ran both suites. 11 of 12 deletions survived -- the recovery
# section, the CHANGELOG:-footer BLOCK/never-auto-fill rule, Phase-3 publish
# read-back, the notes-heading guard, the immutable-published-tag hard rule,
# derive-never-guess, the pre-tag BLOCK-on-nonzero rule, and the
# payload-scoped window rule could each be deleted with the suite staying
# green. Only the `--latest` row-driven assertion
# (test_skill_latest_is_row_driven) caught its mutant.
#
# Coverage followed what the T-41 rewrite ADDED, not the doctrine that had
# to SURVIVE it -- the same shape as the SEMVER regression this campaign's
# own tests elsewhere are named after. This class closes that: it asserts
# PRESENCE of each load-bearing rule, in EVERY payload that actually renders
# the release skill's prose, derived mechanically (never a hand-maintained
# path list) via `tools/build-surface.py`'s own `_output_rel` against
# `core/hosts.json` -- so a fourth host or a renamed output directory
# cannot silently exit this test's scope.
# --------------------------------------------------------------------------- #

_BUILD_SURFACE_PATH = os.path.join(REPO_ROOT, "tools", "build-surface.py")
_build_surface_spec = importlib.util.spec_from_file_location(
    "_release_lib_build_surface", _BUILD_SURFACE_PATH)
build_surface = importlib.util.module_from_spec(_build_surface_spec)
sys.modules[_build_surface_spec.name] = build_surface
_build_surface_spec.loader.exec_module(build_surface)

# Each rule is a short list of tokens that must ALL appear (in any order,
# not necessarily adjacent) for the rule to count as present. Short,
# co-occurring tokens rather than a pinned sentence: a full-sentence anchor
# dies to the next copyedit, and a test that fails on every copyedit is a
# test that gets deleted at the next rewrite (the review's own warning).
# Each token set below is still fatal to an actual deletion of the rule it
# names -- verified by `test_a_deleted_rule_is_detected` below, and by the
# live mutation recorded in this remediation's report.
_GOVERNANCE_RULES = {
    "recovery section": ("## Recovering from a bad release",),
    "footer BLOCK / never-auto-fill": ("CHANGELOG:", "auto-fill"),
    "publish read-back": ("gh release view", "non-draft"),
    "immutable-tag hard rule": ("published tag is immutable",),
    "derive-never-guess": ("MUST NOT guess the version",),
    "pre-tag BLOCK-on-nonzero": ("pre-tag", "non-zero exit", "BLOCK"),
    "payload-scoped window rule": ("$PAYLOAD", "MUST scope"),
    # T-49/T-50 (issue #563, A-5.3/A-5.4): the back-fill lane must not be
    # collapsible to a silent default -- both the requirement to confirm and
    # the requirement to persist (rather than re-detect) are load-bearing.
    "back-fill requires explicit confirmation": ("Back-fill", "explicit confirmation"),
    "back-fill persists and does not re-detect": ("does not re-detect",),
    # DECISION-0036: a multi-target declared file requires an explicit
    # $TARGET; a bare invocation must STOP rather than defaulting.
    "bare multi-target invocation stops": ("$TARGET` is required", "STOP and ask"),
    # Adversarial-review remediation (2026-07-31, agent-judgment exercise):
    # each token set below is fatal to the SPECIFIC regression its finding
    # names, not just a paraphrase of the rule -- see
    # .codearbiter/reports/agent-lane-proof.json for the finding IDs.
    "HIGH-1: back-fill distinguishes exists-vs-absent": (
        "FileExistsNoBlockError", "mechanically distinct"),
    "HIGH-1: back-fill re-checks existence at write time, belt-and-braces": (
        "regardless of how this lane was entered", "STOP without writing",
        "never overwrite an existing file at this path"),
    "HIGH-2: CONTEXT.md is conditional on the Back-fill path": (
        "Back-fill lane above has no", "not itself a STOP"),
    "HIGH-3: back-fill's own write is committed before Pre-flight": (
        "This write itself dirties the tree", "commit-gate", "chore: declare release targets"),
    "HIGH-4: resume_publish still requires authorization": (
        "resume_publish", "still requires explicit user authorization"),
    "MEDIUM: footer BLOCK covers the full harvested set": (
        "feat`/`fix`/`perf`/`refactor` commit", "MUST carry a `CHANGELOG:` footer"),
    "MEDIUM: a footer on a non-bumping commit is harvested, not dropped": (
        "Also harvest a `CHANGELOG:` footer from any", "test`/`docs`/`chore`/`ci` commit"),
    "MEDIUM: list-targets exists": ("sanctioned enumeration", "list-targets"),
    # Re-run of the agent-judgment exercise (2026-07-31): two more HIGH
    # findings and the six MEDIUMs it raised. Distinct key names from the
    # PRIOR round's HIGH-1..4 above -- same date, a different pass, and a
    # different set of findings; these must not collide with (or silently
    # replace) the earlier dict entries.
    "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse": (
        "git rev-parse ${TAG_PREFIX}MAJOR.MINOR.PATCH", "peel-tag"),
    "HIGH-2 (re-run): back-fill declares latest-eligible for its one target": (
        "latest-eligible: true`", "single-target"),
    "MEDIUM (re-run): omitted single target resolves via list-targets, not assumption": (
        "mechanically, never by assumption", "list-targets"),
    "MEDIUM (re-run): manifest bump is stated once (step 6), not twice": (
        "one action described two ways",),
    "MEDIUM (re-run): last_tag_select's ancestry-blind residual is documented": (
        "abandoned permanently", "no ancestry awareness"),
    "MEDIUM (re-run): NEEDS-TRIAGE has a defined shape, destination, and plural form": (
        "EVERY offending commit", "own `[NEEDS-TRIAGE]` line"),
    "MEDIUM (re-run): the footer BLOCK states its own remedy": (
        "remedy is the operator's to choose",),
    "MEDIUM (re-run): the Phase-1 section file's home is outside the tree": (
        "OUTSIDE the working tree", "mktemp"),
    # Run 4 (2026-07-31). The first two are defects this campaign's own
    # earlier "fix" introduced: run 3 found three classify arguments named
    # but never sourced, and the sourcing added in response was wrong for
    # two of them. Pinned here because a prose-only fix has no other guard.
    # Anchored on the flag AS IT APPEARS IN THE COMMAND, not the bare
    # `--cleanup=verbatim` token: that token occurs twice on this line
    # (once in the command, once in the sentence explaining it), so a rule
    # anchored on it survives deletion from the command while the
    # explanation keeps the rule green — the precise inversion of what it
    # guards. Found by mutating it: the bare-token form SURVIVED.
    "HIGH (run 4): the tag message is written verbatim, not strip-cleaned": (
        "-F <message-file> --cleanup=verbatim", "DEFAULT cleanup mode is `strip`"),
    "HIGH (run 4): the stored tag message is verified, not assumed": (
        "verify it round-tripped", "%(contents)"),
    "HIGH (run 4): manifest_version is re-read after the bump, not carried": (
        "re-read from the file NOW", "never the value Pre-flight read"),
    "HIGH (run 4): release_nondraft inverts gh's isDraft": (
        "with its answer inverted", "--jq '.isDraft'"),
    # Re-anchored on the INVOCATION, not the bare subcommand name: run 10's
    # step-7 fix added a second mention of `dates-match` in prose (naming
    # why it cannot see an uncommitted tree), so the bare token stopped
    # being able to detect deletion of the command itself. The ratchet
    # caught this rather than letting it rot.
    "MEDIUM (run 4): the required date check has a runnable command": (
        "_releaselib.py dates-match <Phase-1 section file> <message-file>",),
    # Run 5 (2026-07-31).
    "HIGH (run 5): the <none> sentinel is derived into a range, never substituted": (
        "is a sentinel, not a revision", "WINDOW=HEAD"),
    "MEDIUM (run 5): the possibly-empty tag_sha is quoted": (
        'Quote it', '"$TAG_SHA"'),
    "MEDIUM (runs 5+7): manifest_version is parsed by the file's own format": (
        "FORMAT'S OWN parser rather than a line-grep",),
    "LOW (run 5): the round-trip check reads the raw object, not a reconstruction": (
        "git cat-file tag ${TAG_PREFIX}MAJOR.MINOR.PATCH",),
    # Run 6 (2026-07-31).
    "HIGH (runs 6+7): one base version, the max of tag and every manifest": (
        "one base, computed the same way in every case",
        "the highest version any declared `manifest` currently carries"),
    "HIGH (run 7): the strictly-greater check names its own remedy": (
        "semver-greater <derived> $BASE_VERSION",
        "re-derive from `$BASE_VERSION` rather than raising the bump"),
    "MEDIUM (run 7): the manifest reader follows the file's format": (
        "import tomllib,sys",),
    # Re-anchored: run 12 corrected this paragraph's FALSE claim (that
    # `classify` catches a partial bump -- it short-circuits first), which
    # deleted the old anchor. The rule now pins the corrected statement
    # AND the guard that replaced the imaginary one.
    "MEDIUM (run 7) / HIGH (run 12): max-vs-first coupling, with a REAL guard": (
        "reads the FIRST declared manifest, while Pre-flight",
        "check-manifests $TARGET <derived>"),
    "LOW (run 6): the show-ref exit-status rationale is corrected, not repeated": (
        "the reason given for it was wrong",),
    # Run 10 (2026-07-31).
    "HIGH (run 10): the release edits are committed before tagging": (
        "this is not conditional", "names a COMMIT, not the working tree"),
    "HIGH (run 10): the Phase-1 gate requires a clean tree on exit": (
        "the release edits are COMMITTED",),
    # Run 11 (2026-07-31).
    "HIGH (run 11): exit 6 names the declaration as the fault, with a terminating remedy": (
        "a broken DECLARATION, not a dirty tree",
        "cannot converge"),
    "A-5.5 (run 11 prose): the first-release window floors at the adoption commit": (
        "floor the window at the adoption commit",
        "_releaselib.py adoption-commit"),
    "A-3.6: the interpreter fallback is stated as a file-wide convention": (
        "Interpreter convention, stated once",),
    "HIGH-adjacent (run 11): window classification runs through the helper": (
        "Two operators writing two parses", "_releaselib.py classify-window"),
}

# Rules whose every anchor token also occurs elsewhere in the skill, so the
# rule cannot detect deletion of the sentence it guards. Discovered while
# mutation-testing the run-4 rules (issue #571). Declared here as a ratchet
# rather than silently tolerated: the test below fails in BOTH directions,
# so a newly-weak rule is caught and a repaired one must be removed from
# this set. Re-anchoring these six means finding a span unique to each
# protected sentence, which is prose work on a dense file and is tracked
# separately rather than rushed into a HIGH-remediation commit.
_KNOWN_WEAK_ANCHORS = {
    "footer BLOCK / never-auto-fill",
    "publish read-back",
    "immutable-tag hard rule",
    "pre-tag BLOCK-on-nonzero",
    "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse",
    "HIGH-2 (re-run): back-fill declares latest-eligible for its one target",
}


def _missing_governance_rules(text):
    """The subset of `_GOVERNANCE_RULES` names whose token set is NOT fully
    present in `text`, in declaration order. Empty when every rule survives.
    A pure function so the checker itself can be exercised against a
    synthetic fixture, not only against today's real skill text."""
    missing = []
    for name, tokens in _GOVERNANCE_RULES.items():
        if not all(token in text for token in tokens):
            missing.append(name)
    return missing


class GovernanceRuleCheckerTest(unittest.TestCase):
    """Proves `_missing_governance_rules` itself discriminates a deletion,
    rather than trusting a checker that could vacuously report nothing
    missing no matter what it is given."""

    def test_every_rule_is_present_in_a_fixture_carrying_all_of_them(self):
        fixture = " ".join(
            token for tokens in _GOVERNANCE_RULES.values() for token in tokens)
        self.assertEqual(_missing_governance_rules(fixture), [])

    def test_deleting_one_rules_tokens_is_detected_and_only_that_one(self):
        for name, tokens in _GOVERNANCE_RULES.items():
            with self.subTest(rule=name):
                fixture = " ".join(
                    token for other, other_tokens in _GOVERNANCE_RULES.items()
                    for token in other_tokens if other != name)
                self.assertEqual(_missing_governance_rules(fixture), [name])

    def test_an_empty_text_is_missing_every_rule(self):
        self.assertEqual(
            sorted(_missing_governance_rules("")),
            sorted(_GOVERNANCE_RULES))


class GovernanceSurvivalTest(unittest.TestCase):
    """Applies the proven checker above to the SOURCE and to every payload
    that actually renders `core/surface/skills/release/SKILL.md`'s prose.

    Deliberately 4 texts (source + 3 rendered copies: `ca`, `ca-codex`
    routines, `ca-pi` routines), not 5. The release-portable-fixture spec
    ("Source of truth") counts FIVE release-skill-family payloads in this
    repository, but the other two -- `plugins/ca-codex/skills/ca-release/
    SKILL.md` and `plugins/ca-pi/skills/ca-release/SKILL.md` -- are thin
    router STUBS rendered from `core/surface/commands/release.md`, a
    DIFFERENT template that never carried this governance prose to begin
    with (verified: `_output_rel` for `skills/release/SKILL.md` names only
    the three below for the three governance hosts). Scoping to the two
    stubs' non-existent copy of this prose would not test anything; scoping
    to only a subset that happens to carry the text is exactly the mistake
    this campaign has already made twice (MEDIUM-3's ca-codex/routines
    omission) -- so the set here is every payload `_output_rel` says this
    ONE template renders to, mechanically, not a hand-picked list."""

    @classmethod
    def setUpClass(cls):
        cls.repo = REPO_ROOT
        source_path = os.path.join(
            cls.repo, "core", "surface", "skills", "release", "SKILL.md")
        with open(source_path, encoding="utf-8") as fh:
            source_text = fh.read()
        cls.texts = {"core/surface (source)": source_text}
        descriptors = build_surface.load_host_descriptors(cls.repo)
        for descriptor in descriptors:
            dst, _rule = build_surface._output_rel(
                "skills/release/SKILL.md", descriptor)
            if dst is None:
                continue
            path = os.path.join(cls.repo, descriptor.plugin_dir, dst)
            with open(path, encoding="utf-8") as fh:
                cls.texts[f"{descriptor.plugin_dir}/{dst}"] = fh.read()

    def test_at_least_the_three_rendered_copies_plus_source_are_covered(self):
        # A sanity floor on the derivation itself: if `_output_rel` ever
        # returned nothing (a descriptor.json edit that broke the release
        # skill's own surface rule), this class would silently check ONLY
        # the source and never notice a rendering regression -- the same
        # vacuous-scope failure mode MEDIUM-3 found by a different door.
        self.assertGreaterEqual(len(self.texts), 4)

    def test_every_rule_has_at_least_one_uniquely_occurring_anchor(self):
        # A rule fires only when ALL its tokens are present, so it can
        # detect its own deletion only if at least ONE token disappears
        # entirely when the protected sentence goes. A rule whose every
        # token also occurs elsewhere stays green while the doctrine it
        # guards is deleted — the exact inversion of its purpose.
        #
        # A live defect, not a hypothetical: the run-4 `--cleanup=verbatim`
        # rule was first anchored on the bare flag, which occurs once in
        # the `git tag` command and once in the sentence explaining it.
        # Mutating the flag OUT of the command left the rule green. Only
        # running the mutant caught it; it is now anchored on the flag as
        # it appears IN the command.
        #
        # The manual habit this replaces was itself unreliable: `grep -c`
        # counts matching LINES, and Phase 2 step 1 is a single line
        # thousands of characters long, so two occurrences on it report as
        # one. Counting occurrences is the only form that discriminates.
        #
        # Ratchet, not a clean sweep: six PRE-EXISTING rules fail this and
        # are declared below rather than silently tolerated or hastily
        # re-anchored. New rules must be sound from the start.
        weak = set()
        for label, text in self.texts.items():
            for rule, tokens in _GOVERNANCE_RULES.items():
                if not any(text.count(token) == 1 for token in tokens):
                    weak.add(rule)
        self.assertEqual(
            weak, _KNOWN_WEAK_ANCHORS,
            "the weak-anchor ratchet moved. Newly weak rules (fix by "
            f"re-anchoring): {sorted(weak - _KNOWN_WEAK_ANCHORS)}. Rules "
            "that are now sound (remove them from _KNOWN_WEAK_ANCHORS): "
            f"{sorted(_KNOWN_WEAK_ANCHORS - weak)}")

    def test_every_governance_rule_survives_in_every_payload(self):
        for label, text in self.texts.items():
            with self.subTest(payload=label):
                missing = _missing_governance_rules(text)
                self.assertEqual(
                    missing, [],
                    f"{label}: governance rule(s) missing: {missing} -- "
                    "a deletion of load-bearing doctrine slipped through "
                    "(adversarial review 2026-07-31, the mutation campaign "
                    "this class exists to close)")


# --------------------------------------------------------------------------- #
# T-49/T-50 (issue #563, A-5.3/A-5.4): the back-fill lane -- detection
# mechanism, its CLI, and the release-skill prose describing it, all in this
# same diff (the campaign's own governing rule after HIGH-1/HIGH-2 one slice
# ago: prose and the machinery it describes land together, or not at all).
# --------------------------------------------------------------------------- #


class BackfillDetectionTest(unittest.TestCase):
    """`detect_candidate_target` / `scan_backfill_candidates` /
    `format_release_targets_block`: pure mechanism, exercised directly.
    Ambiguity is asserted in BOTH directions per candidate kind (zero AND
    multiple), not merely "zero raises" -- a checker that only covers one
    arm leaves the other mutation-dead, which is exactly the arm the
    never-guess posture exists for."""

    def test_exactly_one_of_each_returns_a_row(self):
        row = core_releaselib.detect_candidate_target(
            ["package.json"], ["CHANGELOG.md"])
        self.assertEqual(row, {
            "target": "app", "prefix": "v",
            "manifest": ["package.json"], "changelog": "CHANGELOG.md",
            "payload": ".",
            "latest_eligible": True,
        })

    def test_the_proposed_row_is_latest_eligible(self):
        # HIGH-2 (adversarial review 2026-07-31): a back-filled project is,
        # by construction, single-target -- the detector fires on exactly
        # one candidate manifest and one candidate changelog -- so its one
        # release must not be silently demoted out of the "Latest" position
        # by the sibling-series rule the hard rule exists to police. Pinned
        # with `assertIs` against the boolean, not a substring on the
        # printed text, so a mutant that emits the STRING "True"/"true"
        # without the actual Python bool is still caught.
        row = core_releaselib.detect_candidate_target(
            ["package.json"], ["CHANGELOG.md"])
        self.assertIs(row["latest_eligible"], True)

    def test_zero_manifests_is_ambiguous(self):
        with self.assertRaises(core_releaselib.BackfillAmbiguousError):
            core_releaselib.detect_candidate_target([], ["CHANGELOG.md"])

    def test_two_manifests_is_ambiguous(self):
        with self.assertRaises(core_releaselib.BackfillAmbiguousError):
            core_releaselib.detect_candidate_target(
                ["package.json", "pyproject.toml"], ["CHANGELOG.md"])

    def test_zero_changelogs_is_ambiguous(self):
        with self.assertRaises(core_releaselib.BackfillAmbiguousError):
            core_releaselib.detect_candidate_target(["package.json"], [])

    def test_two_changelogs_is_ambiguous(self):
        with self.assertRaises(core_releaselib.BackfillAmbiguousError):
            core_releaselib.detect_candidate_target(
                ["package.json"], ["CHANGELOG.md", "HISTORY.md"])

    def test_ambiguous_errors_are_declared_release_targets_errors(self):
        # A caller catching the general ReleaseTargetsError family (the same
        # contract every other declared parser error already honors) must
        # also catch this one.
        self.assertTrue(
            issubclass(core_releaselib.BackfillAmbiguousError,
                       core_releaselib.ReleaseTargetsError))

    def test_ambiguous_message_names_what_was_found(self):
        with self.assertRaises(core_releaselib.BackfillAmbiguousError) as ctx:
            core_releaselib.detect_candidate_target(
                ["package.json", "pyproject.toml"], ["CHANGELOG.md"])
        self.assertIn("package.json", str(ctx.exception))
        self.assertIn("pyproject.toml", str(ctx.exception))

    def test_scan_reads_only_the_top_level_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("package.json", "CHANGELOG.md"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                    fh.write("{}")
            os.makedirs(os.path.join(tmp, "nested"), exist_ok=True)
            with open(os.path.join(tmp, "nested", "pyproject.toml"),
                      "w", encoding="utf-8") as fh:
                fh.write("")
            manifests, changelogs = core_releaselib.scan_backfill_candidates(tmp)
            self.assertEqual(manifests, ["package.json"])
            self.assertEqual(changelogs, ["CHANGELOG.md"])

    def test_scan_of_a_missing_root_finds_nothing_rather_than_raising(self):
        manifests, changelogs = core_releaselib.scan_backfill_candidates(
            os.path.join(tempfile.gettempdir(),
                         "codearbiter-backfill-scan-does-not-exist"))
        self.assertEqual(manifests, [])
        self.assertEqual(changelogs, [])

    def test_format_round_trips_through_the_real_parser(self):
        row = core_releaselib.detect_candidate_target(
            ["package.json"], ["CHANGELOG.md"])
        text = core_releaselib.format_release_targets_block(row)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            rows = core_releaselib.load_targets(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "app")
        self.assertEqual(rows[0]["prefix"], "v")
        self.assertEqual(rows[0]["manifest"], ["package.json"])
        self.assertEqual(rows[0]["changelog"], "CHANGELOG.md")
        self.assertEqual(rows[0]["payload"], ".")
        # HIGH-2 (adversarial review 2026-07-31): the emitted
        # `latest-eligible: true` line must round-trip back through the
        # REAL grammar parser as the boolean `True`, not merely appear as a
        # substring of the printed text -- `assertIs` against the parsed
        # value is what would catch a mutant emitting an unparseable or
        # wrong-case literal (`InvalidBooleanError`) or the wrong boolean.
        self.assertIs(rows[0]["latest_eligible"], True)

    def test_format_omits_the_key_entirely_when_the_row_declares_none(self):
        # A caller supplying a row shaped like the module docstring's
        # minimum ("at least target/prefix/changelog/payload/manifest")
        # with no `latest_eligible` key at all must not have one invented --
        # `format_release_targets_block` is a generic renderer, not only
        # `detect_candidate_target`'s own private serializer.
        row = {"target": "app", "prefix": "v", "manifest": ["package.json"],
               "changelog": "CHANGELOG.md", "payload": "."}
        text = core_releaselib.format_release_targets_block(row)
        self.assertNotIn("latest-eligible", text)

    def test_a_second_load_reads_the_persisted_row_without_detecting_again(self):
        # T-50: "a second run reads it rather than re-detecting" -- proven
        # mechanically by never calling detect_candidate_target/
        # scan_backfill_candidates a second time and still getting the row.
        row = core_releaselib.detect_candidate_target(
            ["pyproject.toml"], ["HISTORY.md"], target="widgets", prefix="w")
        text = core_releaselib.format_release_targets_block(row)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            second_read = core_releaselib.load_targets(path)
        self.assertEqual(second_read[0]["target"], "widgets")
        self.assertEqual(second_read[0]["prefix"], "w")


class BackfillCLITest(unittest.TestCase):
    """`backfill-detect` end-to-end through `main(argv)` -- the shape the
    release skill's back-fill lane actually shells out to."""

    def test_exactly_one_candidate_of_each_prints_the_loadable_block_and_exits_0(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                fh.write("{}")
            with open(os.path.join(tmp, "CHANGELOG.md"), "w", encoding="utf-8") as fh:
                fh.write("# Changelog\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(["backfill-detect", tmp])
            self.assertEqual(rc, 0)
            printed = out.getvalue()
            with tempfile.TemporaryDirectory() as tmp2:
                path = os.path.join(tmp2, "release-targets.md")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(printed)
                rows = core_releaselib.load_targets(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["manifest"], ["package.json"])
            self.assertEqual(rows[0]["changelog"], "CHANGELOG.md")
            # HIGH-2 (adversarial review 2026-07-31): the full CLI path
            # (`backfill-detect` -> printed text -> real parser) must also
            # carry the eligibility declaration, not just the pure-function
            # call tested above.
            self.assertIs(rows[0]["latest_eligible"], True)

    def test_backfill_detect_writes_nothing_to_disk_even_on_success(self):
        # T-49: detection alone is the mechanical half of "does not proceed
        # without explicit confirmation" -- the CLI must ONLY print the
        # candidate block, never persist it as a side effect. Snapshot the
        # scanned root's own tree before/after: a passing exit code alone
        # would not catch a mutant that also writes .codearbiter/
        # release-targets.md into the scanned root.
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                fh.write("{}")
            with open(os.path.join(tmp, "CHANGELOG.md"), "w", encoding="utf-8") as fh:
                fh.write("# Changelog\n")
            before = sorted(
                os.path.relpath(os.path.join(dirpath, name), tmp)
                for dirpath, _, names in os.walk(tmp) for name in names)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = core_releaselib.main(["backfill-detect", tmp])
            self.assertEqual(rc, 0)
            after = sorted(
                os.path.relpath(os.path.join(dirpath, name), tmp)
                for dirpath, _, names in os.walk(tmp) for name in names)
            self.assertEqual(before, after)
            self.assertFalse(
                os.path.isdir(os.path.join(tmp, ".codearbiter")),
                "backfill-detect must never create .codearbiter/ itself")

    def test_no_candidates_exits_non_zero_and_writes_no_block(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = core_releaselib.main(["backfill-detect", tmp])
            self.assertNotEqual(rc, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("candidate manifest", err.getvalue())

    def test_multiple_candidates_exits_non_zero_and_writes_no_block(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("package.json", "CHANGELOG.md", "HISTORY.md"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                    fh.write("{}" if name == "package.json" else "# x\n")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = core_releaselib.main(["backfill-detect", tmp])
            self.assertNotEqual(rc, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("candidate changelog", err.getvalue())

    def test_root_defaults_to_cwd_when_no_env_var_is_set(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Cargo.toml"), "w", encoding="utf-8") as fh:
                fh.write("")
            with open(os.path.join(tmp, "CHANGES.md"), "w", encoding="utf-8") as fh:
                fh.write("")
            old_cwd = os.getcwd()
            old_env = os.environ.pop("CLAUDE_PROJECT_DIR", None)
            os.chdir(tmp)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = core_releaselib.main(["backfill-detect"])
            finally:
                os.chdir(old_cwd)
                if old_env is not None:
                    os.environ["CLAUDE_PROJECT_DIR"] = old_env
            self.assertEqual(rc, 0)
            self.assertIn("Cargo.toml", out.getvalue())
            self.assertIn("CHANGES.md", out.getvalue())

    def test_root_resolves_via_claude_project_dir_env_regardless_of_cwd(self):
        # T-41f's own defect class, re-applied here: a subprocess is not
        # guaranteed to start with the project directory as its cwd. Run
        # from an UNRELATED cwd with CLAUDE_PROJECT_DIR pointed at the real
        # candidate root and confirm resolution follows the env var, not
        # wherever the caller happens to be sitting.
        import io, contextlib
        with tempfile.TemporaryDirectory() as project_root, \
                tempfile.TemporaryDirectory() as unrelated_cwd:
            with open(os.path.join(project_root, "package.json"),
                      "w", encoding="utf-8") as fh:
                fh.write("{}")
            with open(os.path.join(project_root, "CHANGELOG.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("")
            old_cwd = os.getcwd()
            old_env = os.environ.get("CLAUDE_PROJECT_DIR")
            os.chdir(unrelated_cwd)
            os.environ["CLAUDE_PROJECT_DIR"] = project_root
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = core_releaselib.main(["backfill-detect"])
            finally:
                os.chdir(old_cwd)
                if old_env is None:
                    os.environ.pop("CLAUDE_PROJECT_DIR", None)
                else:
                    os.environ["CLAUDE_PROJECT_DIR"] = old_env
            self.assertEqual(rc, 0)
            self.assertIn("manifest: package.json", out.getvalue())
            self.assertIn("changelog: CHANGELOG.md", out.getvalue())

    def test_default_backfill_root_prefers_claude_project_dir_env(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = os.path.join("some", "consumer", "root")
        try:
            self.assertEqual(
                core_releaselib.default_backfill_root(),
                os.path.join("some", "consumer", "root"))
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old


class BackfillSkillProseTest(unittest.TestCase):
    """T-49/T-50 (issue #563, A-5.3/A-5.4): the release skill's own
    'Back-fill' lane. Replaces the 2026-07-31 canary
    (`test_skill_does_not_claim_a_backfill_lane_yet`, which asserted the
    ABSENCE of this prose and was written to be replaced -- not loosened --
    the moment this landed). These are the plan's own named verification
    targets (`-k backfill_requires_confirmation`, `-k backfill_persists`)."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()
        idx = cls.text.index("## Back-fill")
        end = cls.text.index("## Pre-flight")
        cls.section = cls.text[idx:end]

    def test_backfill_requires_confirmation(self):
        # Presents the detected shape and explicitly does not proceed
        # (write, or advance to any later phase) without confirmation.
        self.assertIn("explicit confirmation", self.section)
        self.assertIn("Do NOT write it", self.section)
        self.assertIn("STOPs the lane", self.section)
        self.assertIn("nothing is written", self.section)
        # It never guesses among ambiguous candidates either.
        self.assertIn("never guesses among candidates", self.section)

    def test_backfill_persists(self):
        # On confirmation the file is actually written...
        self.assertIn("Write the confirmed block", self.section)
        self.assertIn("release-targets.md", self.section)
        # ...and a second run reads rather than re-detecting.
        self.assertIn("does not re-detect", self.section)
        self.assertIn("never runs again for this project", self.section)

    def test_backfill_fires_only_on_a_genuinely_absent_file(self):
        # The distinct failure mode this whole lane must not step on: an
        # EXISTING but malformed file still STOPs outright per "Targets"
        # above, rather than being treated as a detection opportunity.
        self.assertIn("AbsentBlockError", self.section)
        self.assertIn("however broken", self.section)
        targets_idx = self.text.index("## Targets")
        targets_section = self.text[targets_idx:self.text.index("## Back-fill")]
        self.assertIn("unparseable declared file", targets_section)
        self.assertIn("STOP and surface the parse error", targets_section)

    def test_backfill_invokes_the_detection_cli(self):
        self.assertIn("backfill-detect", self.section)
        self.assertIn("{{PLUGIN_ROOT}}/hooks/_releaselib.py", self.section)


class ContextCreationBackfillTest(unittest.TestCase):
    """T-48 (issue #563, A-5.2): `context-creation` scouts a candidate
    manifest/changelog and writes a file `load_targets` accepts. The
    assertion is on the WRITTEN FILE's validity (the spec's own wording),
    not on skill prose -- the exact template block the skill instructs an
    agent to produce is extracted and parsed for real, the same way
    `SkillPortabilityTest`/`BackfillDetectionTest` treat other template
    blocks in this campaign."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "context-creation", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    def _extract_template(self):
        start = self.text.index("<!-- release-targets -->")
        end = self.text.index(
            "<!-- /release-targets -->", start) + len("<!-- /release-targets -->")
        return self.text[start:end]

    def test_context_creation_names_the_destination_and_the_grammar_source(self):
        self.assertIn("release-targets.md", self.text)
        self.assertIn("{{PLUGIN_ROOT}}/hooks/_releaselib.py", self.text)

    def test_context_creation_writes_loadable(self):
        template = self._extract_template()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "release-targets.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(template + "\n")
            rows = core_releaselib.load_targets(path)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["target"], "app")
        self.assertEqual(row["prefix"], "v")
        self.assertEqual(row["manifest"], ["package.json"])
        self.assertEqual(row["changelog"], "CHANGELOG.md")
        self.assertEqual(row["payload"], ".")

    def test_context_creation_defers_to_confirm_nn_when_ambiguous(self):
        # Never scaffolded from an ambiguous scan -- the same "no signal, or
        # conflicting signals -> [CONFIRM-NN]" rule the rest of Phase 3
        # already applies, extended (not special-cased) to this doc.
        idx = self.text.index("HIGH-confidence only when")
        window = self.text[idx:idx + 900]
        self.assertIn("[CONFIRM-NN]", window)
        self.assertIn("never scaffolded from an ambiguous scan", window.lower())


class DecisionZeroZeroThreeSixTest(unittest.TestCase):
    """DECISION-0036 pin (this-slice test obligation): a multi-target
    declared file requires an explicit `$TARGET`; a bare invocation STOPs. A
    single-target file still resolves implicitly. No hardcoded target name
    resolves as a fallback -- this decision has no dedicated resolution
    FUNCTION to unit-test (verified: `tag-prefix` always requires a
    positional target name; `select_release_target` is the CI dispatch
    arm's OWN selection, not this). The pin is therefore structural, over
    the surface source that states the rule -- see this class's own
    mutation-kill proof in the accompanying report for the text mutant this
    was verified to catch."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_single_target_resolves_implicitly(self):
        self.assertIn(
            "the declared file names exactly one target, that target is "
            "used", self.text)

    def test_multi_target_bare_invocation_stops(self):
        self.assertIn("$TARGET` is required", self.text)
        self.assertIn("STOP and ask rather than guessing which one a bare "
                       "invocation meant", self.text)

    def test_no_hardcoded_target_name_resolves_as_a_fallback(self):
        # Scoped to the SENTENCE that states the rule, not the whole
        # document -- a regression restoring the pre-DECISION-0036 behavior
        # would add a hardcoded fallback name right where the multi-target
        # STOP is declared. `core/surface/commands/release.md` still carries
        # the old "targets the `ca` plugin only" wording (T-71's job, not
        # this skill's, and out of scope here) -- deliberately not scanned,
        # since a stale sentence in a DIFFERENT file must not make this
        # narrower check look like it covers ground it doesn't.
        idx = self.text.index("$TARGET` is required")
        window = self.text[max(0, idx - 200): idx + 200]
        self.assertNotIn("`ca`", window)
        self.assertNotIn("defaults to", window.lower())


if __name__ == "__main__":
    unittest.main()
