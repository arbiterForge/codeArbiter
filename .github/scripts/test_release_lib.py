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
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _releaselib  # noqa: E402 — needs sys.path mutation above

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
_CORE_RELEASELIB_PATH = os.path.join(REPO_ROOT, "core", "pysrc", "_releaselib.py")
_core_spec = importlib.util.spec_from_file_location(
    "_core_releaselib", _CORE_RELEASELIB_PATH)
core_releaselib = importlib.util.module_from_spec(_core_spec)
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

    def test_artifact_freshness_is_unconditional(self):
        # The rebuild + diff must be present and described as unconditional...
        self.assertIn("git diff --quiet", self.text)
        self.assertIn("unconditional", self.text.lower())
        # ...and NOT gated behind the old in-window farm.ts conditional (0002).
        self.assertNotIn(
            "if `plugins/ca/tools/farm.ts` was modified in the release window",
            self.text,
            "0002: the rebuild must not be conditional on an in-window source change")

    def test_every_shipped_bundle_is_named_for_its_target(self):
        # #382 generalised the freshness step over four targets, so the check
        # that used to name ONE artifact now has to name all of them: a plugin
        # whose bundle is absent from the Targets table can release a stale one
        # simply because nothing told the orchestrator to rebuild it. Listed
        # explicitly rather than derived, because ca-pi's bundles are NOT in
        # payload_scope.SHIPPED_TOOLS_ARTIFACTS - they live under extensions/,
        # which is already inside the payload scope.
        for artifact in ("plugins/ca/tools/farm.js",
                         "plugins/ca-sandbox/tools/sandbox.js",
                         "plugins/ca-sandbox/tools/claude-inside.js",
                         "plugins/ca-pi/extensions/codearbiter.js",
                         "plugins/ca-pi/extensions/codearbiter-child.js"):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, self.text,
                              "the Targets table must name every shipped bundle")

    def test_every_release_target_is_reachable_from_the_command(self):
        # The command half of #382: one command, four targets. Each target and
        # its namespace must appear, and the namespace must come from the shared
        # register rather than being typed into the prose.
        self.assertIn("_releaselib.py tag-prefix", self.text,
                      "the skill must ASK for the namespace, not restate four of them")
        for target, prefix in _releaselib.RELEASE_TAG_PREFIXES.items():
            with self.subTest(target=target):
                self.assertIn(f"`{target}`", self.text)
                self.assertIn(f"`{prefix}`", self.text)

    def test_each_target_names_its_own_manifest_and_changelog(self):
        for path in ("plugins/ca/.claude-plugin/plugin.json",
                     "plugins/ca-codex/.codex-plugin/plugin.json",
                     "plugins/ca-sandbox/.claude-plugin/plugin.json",
                     "plugins/ca-pi/package.json",
                     "plugins/ca-codex/CHANGELOG.md",
                     "plugins/ca-sandbox/CHANGELOG.md",
                     "plugins/ca-pi/CHANGELOG.md"):
            with self.subTest(path=path):
                self.assertIn(path, self.text)

    def test_only_ca_may_claim_the_latest_badge(self):
        # One repo-wide "Latest" across four series; a sibling claiming it hides
        # ca's current release from every visitor.
        self.assertIn("MUST NOT assert `--latest` for any target except `ca`",
                      self.text)

    def test_the_pi_root_manifest_is_generated_not_hand_edited(self):
        # Pi installs the repository ROOT as the package, so the root manifest is
        # a second thing that must agree with the tag - and it is generated.
        self.assertIn("tools/build-host-packages.py", self.text)
        self.assertIn("never hand-edit", self.text.lower())

    def test_names_ci_tools_job_as_backstop(self):
        self.assertIn("`tools` job", self.text,
                      "AC-5: the local check must name the CI tools job as the mechanical backstop")

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
        self.assertEqual(tuple(_releaselib.RELEASE_TAG_PREFIXES),
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
        for target, prefix in _releaselib.RELEASE_TAG_PREFIXES.items():
            with self.subTest(target=target):
                self.assertEqual(_releaselib.last_tag_select(self.TAGS, prefix),
                                 expected[target])

    def test_no_series_resolves_another_series_tag(self):
        # The defect this prevents: basing an entire release on another plugin's
        # baseline, which `git describe --tags` does by commit-graph ancestry.
        for target, prefix in _releaselib.RELEASE_TAG_PREFIXES.items():
            with self.subTest(target=target):
                chosen = _releaselib.last_tag_select(self.TAGS, prefix)
                self.assertTrue(chosen.startswith(prefix), chosen)
                for other, other_prefix in _releaselib.RELEASE_TAG_PREFIXES.items():
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
        for prefix in _releaselib.RELEASE_TAG_PREFIXES.values():
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
        for target, prefix in _releaselib.RELEASE_TAG_PREFIXES.items():
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

class DenylistTest(unittest.TestCase):
    """A-1.2: the portable mechanism (core/pysrc/_releaselib.py) must carry no
    literal from this repository's namespace or CI vocabulary. `.github/
    scripts/_releaselib.py` (imported above as `_releaselib`) is EXEMPT — it
    still temporarily retains this repo's own data constants (A-1.9,
    transitional) and is deliberately not scanned here."""

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
        "manifest: package.json\n"
        "manifest: nested/package.json\n"
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
        self.assertEqual(row["manifest"], ["package.json", "nested/package.json"])
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
        self.assertEqual(row["manifest"], [])
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


if __name__ == "__main__":
    unittest.main()
