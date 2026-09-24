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

import contextlib
import importlib.util
import inspect
import io
import json
import os
import subprocess
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

_BASH_PROBE = []


def working_bash():
    """Path to a `bash` that actually runs a script fed on stdin, or None.

    RESOLVING the name is the load-bearing half here, and it is why this
    returns a path rather than a bool. `subprocess.run(["bash", ...])`
    without `shell=True` leaves the lookup to `CreateProcess`, whose search
    order is not `PATH` order; on GitHub's `windows-latest` image that
    picked something which exits 1 with BOTH streams empty — read back as
    `AssertionError: 1 != 0` with an empty message, indistinguishable from
    the script under test failing silently. Handing `subprocess` the
    absolute path `shutil.which` finds by walking `PATH` runs the real Git
    Bash and the same round trip passes. (Measured: CI run 30691314813 red,
    run 30692612801 green with no other change to the exec path.)

    The PROBE is the belt to that braces: it separates "no usable shell on
    this platform" from "the shell ran and disagreed", so the round-trip arm
    can skip the former while still failing hard on the latter, on some
    future runner where `which` finds nothing usable either. It is not what
    fixed windows-latest — that test now passes there rather than skipping.

    Result is cached: the probe spawns a process, and the answer cannot
    change within one run."""
    if not _BASH_PROBE:
        _BASH_PROBE.append(_probe_bash())
    return _BASH_PROBE[0]


def _probe_bash():
    exe = shutil.which("bash")
    if not exe:
        return None
    try:
        probe = subprocess.run([exe, "-s"], input=b"printf ca-probe-ok\n",
                               capture_output=True, timeout=60)
    # TimeoutExpired is a SubprocessError, NOT an OSError, so catching only
    # OSError leaves the hole open on the exact platform this probe exists
    # for: a `bash` that HANGS rather than exits (a WSL stub blocking on an
    # install prompt is the canonical windows-latest shape) would propagate
    # out and ERROR the test instead of skipping it.
    except (OSError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0 or probe.stdout.strip() != b"ca-probe-ok":
        return None
    return exe


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

    def test_auto_eligible_true_when_manifest_advances(self):
        rc, out = self._run(["auto-eligible", "2.12.1", "v"],
                            "v2.12.0\nv2.11.0\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "true")

    def test_auto_eligible_false_when_manifest_equals_last_tag(self):
        rc, out = self._run(["auto-eligible", "2.12.0", "v"],
                            "v2.12.0\nv2.11.0\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "false")

    def test_auto_eligible_true_on_first_introduction(self):
        # No tag at all for this series yet — always eligible, the same
        # "first introduction" pass payload_version_gate.py's base_version()
        # grants when a target is new on the base.
        rc, out = self._run(["auto-eligible", "1.0.0", "zzz-v"], "")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "true")

    def test_auto_eligible_respects_the_tag_namespace(self):
        # A last-tag lookup scoped to the wrong prefix must not see the
        # other series' tag at all — same series-isolation guarantee
        # last-tag itself carries.
        rc, out = self._run(["auto-eligible", "0.1.5", "ca-sandbox-v"],
                            "v2.12.0\nca-pi-v0.3.1\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "true")

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
        self.assertIn("## [${VERSION}]", self.text)
        self.assertNotIn("## v${VERSION}", self.text)


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

    # -- T-41d: hosted publication is mandatory; immutability prose conditional

    def test_skill_conditional_prose(self):
        phase3_idx = self.text.index("## Phase 3")
        recovering_idx = self.text.index("## Recovering from a bad release")
        phase3_preamble = self.text[phase3_idx:phase3_idx + 1600]
        recovering = self.text[recovering_idx:]

        self.assertIn("A qualifying hosted release workflow is mandatory", phase3_preamble)
        self.assertIn("requires green merge readiness for that exact SHA", phase3_preamble)
        self.assertIn("Otherwise dispatch the reviewed hosted lane", phase3_preamble)

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
            "The title convention is `<$DISPLAY_NAME> ${VERSION}: "
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


class ShimDocumentedApiTest(unittest.TestCase):
    """AC-06 / T-07 (issue #626 finding 1, spec P4): the shim's header
    'Public API' comment used to document `select_release_target_by_name
    (pairs) -> str` as though it were a locally-defined, importable
    module-level function, matching the shape of its genuine siblings on
    the same list (`last_tag_select`, `select_release_target`,
    `classify_merge_readiness`, all defined in THIS file). No such function
    is defined here -- the only call site is inside `main()`'s CLI dispatch
    (`select-target-named`), which reaches the imported `_mechanism` module
    directly (`_mechanism.select_release_target_by_name(...)`). P4 is
    explicit: correct the doc only; do not add the missing wrapper."""

    _SHIM_PATH = os.path.join(HERE, "_releaselib.py")

    # Matches a `name(args) -> type` call-signature entry, applied to ONE
    # paren-balanced logical entry at a time (see
    # `_documented_call_signature_names` below) -- never to raw multi-entry
    # text -- so it cannot bleed across an unrelated bullet or a later
    # arrow that happens to follow, elsewhere, a name this entry never
    # actually calls. Anchored (`re.match`, not `re.search`): a name
    # merely MENTIONED mid-prose (e.g. this task's own new explanatory text
    # naming `_mechanism.select_release_target_by_name(...)` as what a CLI
    # route reaches THROUGH) is not "documented as a call signature of this
    # entry" unless the entry itself STARTS with `name(`.
    _SIGNATURE_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\(.*?\)\s*->", re.S)

    def _header_text(self):
        # The 'Public API' comment block lives entirely before the first
        # import statement. Slicing to just that block keeps this test from
        # matching the real CLI dispatch code below it, which legitimately
        # contains the string "select_release_target_by_name" as a call
        # THROUGH the imported mechanism -- not a claim about this shim's
        # own surface.
        with open(self._SHIM_PATH, encoding="utf-8") as fh:
            text = fh.read()
        marker = "\nimport importlib.util\n"
        idx = text.index(marker)
        return text[:idx]

    def _public_api_block(self):
        # Narrower than the full header: starts at the first "Public API"
        # comment block, excluding the module's earlier design-rationale
        # prose (which is full of unrelated parentheses and would otherwise
        # make paren-balance joining sprawl across unrelated sentences).
        header = self._header_text()
        return header[header.index("# Public API (re-exported"):]

    def _documented_call_signature_names(self, text):
        # Joins only lines whose accumulated, un-stripped parenthesis count
        # is still positive (an entry's signature wrapped onto a deeper-
        # indented continuation comment line, e.g. classify_publish_state's
        # two-line entry) -- a line with BALANCED parens (like this task's
        # own new prose, which opens and closes its parentheticals within
        # each line) never merges with its neighbor, so a mid-paragraph
        # mention several lines later cannot join back onto an earlier
        # bullet's name. Each resulting logical entry is then matched
        # independently and anchored at its own start.
        entries, pending, depth = [], "", 0
        for raw in text.splitlines():
            stripped = raw.lstrip("#")
            joined = (pending + "\n" + stripped) if pending else stripped
            depth += stripped.count("(") - stripped.count(")")
            if depth > 0:
                pending = joined
                continue
            entries.append(joined)
            pending, depth = "", 0
        if pending:
            entries.append(pending)
        names = []
        for entry in entries:
            m = self._SIGNATURE_RE.match(entry)
            if m:
                names.append(m.group(1))
        return names

    def test_every_documented_call_signature_resolves_as_a_real_attribute(self):
        # Derived, not hand-restated -- the same reasoning
        # ShimReexportCompletenessTest applies to a CONSUMER's imports,
        # applied here to the header's own claims about ITSELF. A
        # hand-restated name list would keep passing if the header were
        # later reworded to claim a DIFFERENT, still-false signature for a
        # name that still does not exist (e.g.
        # `select_release_target_by_name(pairs, targets) -> str`); this scan
        # does not care what the signature SAYS, only what NAME it
        # documents, so it catches that mutant too. This is the check that
        # would have caught T-07's own originating defect (#626 finding 1)
        # unaided.
        names = sorted(set(
            self._documented_call_signature_names(self._public_api_block())))
        self.assertGreaterEqual(
            len(names), 10,
            "the signature scan found almost nothing, so the completeness "
            "check below would pass without measuring anything: %r" % (names,))
        missing = [n for n in names if not hasattr(_releaselib, n)]
        self.assertEqual(
            missing, [],
            "the header documents a call signature for a name that is not "
            "actually an attribute of this shim module: %r" % (missing,))

    def test_header_no_longer_claims_an_importable_wrapper(self):
        header = self._header_text()
        self.assertNotIn(
            "select_release_target_by_name(pairs) -> str", header,
            "the header still documents select_release_target_by_name as an "
            "importable module-level function; this shim defines no such "
            "wrapper")

    def test_no_wrapper_was_actually_added(self):
        # P4: this is a documentation-only fix. A future caller genuinely
        # needing importable access is a plan amendment, not something this
        # task adds speculatively.
        self.assertFalse(
            hasattr(_releaselib, "select_release_target_by_name"),
            "a select_release_target_by_name wrapper now exists on the shim; "
            "P4 authorizes correcting the doc only, not adding this API")

    def test_header_documents_the_real_cli_route(self):
        header = self._header_text()
        self.assertIn(
            "select-target-named", header,
            "the header does not name the real CLI route "
            "(select-target-named) that reaches this functionality")

    def test_main_docstring_lists_select_target_named(self):
        # The header now POINTS a reader at "the real CLI route" -- that
        # pointer is only honest if main()'s own dispatch docstring (the
        # CLI's actual usage reference) lists the subcommand it names.
        # Without this, AC-06's "documents the real select-target-named CLI
        # route instead" would be true of the header alone while the file's
        # other documented-API surface (the CLI's own docstring) still
        # didn't acknowledge the route existed.
        import _releaselib as shim_module
        self.assertIn("select-target-named", shim_module.main.__doc__,
                      "main()'s dispatch docstring does not list the "
                      "select-target-named subcommand")

    def test_named_selection_cli_still_works_unchanged(self):
        # Existing exports and named-selection behavior are unchanged by
        # this doc-only fix: the real route the corrected doc now points at
        # must still function exactly as before.
        result = subprocess.run(
            [sys.executable, self._SHIM_PATH, "select-target-named",
             "ca=1.2.3"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "ca"))


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

    def test_target_names_cannot_be_cli_option_shaped(self):
        text = ("<!-- release-targets -->\n"
                "[--field]\n"
                "prefix: v\n"
                "changelog: CHANGELOG.md\n"
                "payload: .\n"
                "<!-- /release-targets -->\n")
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(text)

    def test_targets_cannot_share_or_overlap_a_tag_prefix(self):
        for first, second in (("v", "v"), ("v", "v1"), ("pkg-v2", "pkg-v")):
            text = ("<!-- release-targets -->\n"
                    f"[one]\nprefix: {first}\nchangelog: ONE.md\npayload: one/\n"
                    f"[two]\nprefix: {second}\nchangelog: TWO.md\npayload: two/\n"
                    "<!-- /release-targets -->\n")
            with self.subTest(first=first, second=second), \
                    self.assertRaises(core_releaselib.MalformedBlockError):
                core_releaselib.parse_release_targets(text)

    def test_only_one_target_can_be_latest_eligible(self):
        text = ("<!-- release-targets -->\n"
                "[one]\nprefix: one-v\nchangelog: ONE.md\npayload: one/\n"
                "latest-eligible: true\n"
                "[two]\nprefix: two-v\nchangelog: TWO.md\npayload: two/\n"
                "latest-eligible: true\n"
                "<!-- /release-targets -->\n")
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(text)

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

    def test_non_utf8_existing_file_is_unreadable_and_cli_exits_four(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, ".codearbiter")
            os.makedirs(state)
            path = os.path.join(state, "release-targets.md")
            with open(path, "wb") as handle:
                handle.write(b"<!-- release-targets -->\n[app\xff]\n")
            with self.assertRaises(core_releaselib.UnreadableTargetsFileError):
                core_releaselib.load_targets(path)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=tmp,
                       PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "list-targets"],
                cwd=tempfile.gettempdir(), env=env, capture_output=True)
        stderr = result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 4, stderr)
        self.assertIn("UnreadableTargetsFileError", stderr)
        self.assertNotIn("Traceback", stderr)

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


class UnreadableTargetsFileTest(unittest.TestCase):
    """[[never-fold-unreadable-into-absent]] / #578 robustness finding: before
    this class existed, `load_targets` caught a bare `OSError` and raised
    `AbsentBlockError` for EVERY unreadable path, including one that exists
    but could not be opened for a reason other than "not found" (a
    permissions error, or the path naming a directory). That silently
    satisfied the release skill's Back-fill lane's ONE sanctioned trigger
    (`except AbsentBlockError:`), so a declared-targets file an operator
    could not currently read -- not one that was actually missing -- could
    drive Back-fill to write a fresh file over it. A directory path is used
    here as the portable, no-chmod-needed stand-in for "OSError other than
    FileNotFoundError": opening a directory as a file always fails --
    `IsADirectoryError` on POSIX, `PermissionError` on Windows (measured on
    this repository's own CI/dev hosts) -- and either way it is a real,
    non-ENOENT `OSError`, which is the only property this distinction is
    keyed on; chmod-based permission tests were avoided because permission
    semantics differ too much across hosts to pin reliably in a unit test."""

    def test_a_path_that_exists_but_cannot_be_opened_raises_unreadable_not_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # A directory can never be open()'d as a file -- a real,
            # non-FileNotFoundError OSError -- the path is there.
            with self.assertRaises(core_releaselib.UnreadableTargetsFileError):
                core_releaselib.load_targets(tmp)

    def test_genuinely_missing_file_still_raises_absent_block_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "does-not-exist.md")
            with self.assertRaises(core_releaselib.AbsentBlockError):
                core_releaselib.load_targets(path)

    def test_unreadable_is_never_caught_by_except_absent_block_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            caught_as_absent = False
            try:
                try:
                    core_releaselib.load_targets(tmp)
                except core_releaselib.AbsentBlockError:
                    caught_as_absent = True
            except core_releaselib.UnreadableTargetsFileError:
                pass
            self.assertFalse(
                caught_as_absent,
                "an unreadable-but-present path must never be caught by "
                "`except AbsentBlockError:` -- that is the Back-fill "
                "lane's genuinely-absent-only trigger")

    def test_unreadable_targets_file_error_is_a_sibling_not_a_subclass(self):
        self.assertFalse(
            issubclass(core_releaselib.UnreadableTargetsFileError,
                       core_releaselib.AbsentBlockError))
        self.assertFalse(
            issubclass(core_releaselib.AbsentBlockError,
                       core_releaselib.UnreadableTargetsFileError))
        self.assertTrue(
            issubclass(core_releaselib.UnreadableTargetsFileError,
                       core_releaselib.ReleaseTargetsError))

    def test_targets_error_exit_code_maps_unreadable_to_4_not_3(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            try:
                core_releaselib.load_targets(tmp)
                self.fail("expected UnreadableTargetsFileError")
            except core_releaselib.UnreadableTargetsFileError as exc:
                self.assertEqual(
                    core_releaselib._targets_error_exit_code(exc), 4)


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

    def test_parser_contract_rejects_prefixes_that_are_not_safe_tag_names(self):
        for prefix in ("-f v", "v x", "v~", "v..", "v@{", "/v", "v/",
                       "v.lock/", "refs/heads/release-"):
            with self.subTest(prefix=prefix):
                text = ("<!-- release-targets -->\n[app]\n"
                        f"prefix: {prefix}\n"
                        "changelog: CHANGELOG.md\npayload: .\n" + self.CLOSE)
                with self.assertRaises(core_releaselib.MalformedBlockError):
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

    def test_release_series_rejects_noncanonical_numeric_identifiers(self):
        tags = ["v1.2.3", "v02.0.0", "v١٠.٠.٠"]
        self.assertEqual(
            core_releaselib.last_tag_select(tags, "v"), "v1.2.3")


class NumericSequenceParserTest(unittest.TestCase):
    """AC-01/03: policy declarations are explicit and fail closed."""

    _BASE = ("<!-- release-targets -->\n[app]\n"
             "prefix: preview-\nchangelog: CHANGELOG.md\npayload: .\n")

    def _parse(self, extra=""):
        return core_releaselib.parse_release_targets(
            self._BASE + extra + "<!-- /release-targets -->\n")[0]

    def test_omitted_policy_preserves_the_semver_default(self):
        row = self._parse()
        self.assertEqual(row["version_policy"], "semver")
        self.assertIsNone(row["initial_version"])

    def test_numeric_sequence_requires_a_valid_fixed_shape_initial_version(self):
        row = self._parse(
            "version-policy: numeric-sequence\ninitial-version: 0.1\n")
        self.assertEqual(row["version_policy"], "numeric-sequence")
        self.assertEqual(row["initial_version"], "0.1")

        for initial in ("", "0", "01.2", "1.02", "1.2.3-beta", "1.two"):
            with self.subTest(initial=initial):
                declaration = "version-policy: numeric-sequence\n"
                if initial != "":
                    declaration += f"initial-version: {initial}\n"
                with self.assertRaises(core_releaselib.MalformedBlockError):
                    self._parse(declaration)

    def test_unknown_policy_and_policy_incompatible_initial_version_are_rejected(self):
        with self.assertRaises(core_releaselib.MalformedBlockError):
            self._parse("version-policy: calendar\n")
        with self.assertRaises(core_releaselib.MalformedBlockError):
            self._parse("version-policy: semver\ninitial-version: 1.2.3\n")

    def test_scratch_exclusions_cover_every_declared_surface_field(self):
        scalar_fields = ("changelog", "provenance_manifest")
        list_fields = ("manifest", "generated_manifest", "artifacts",
                       "release_assets")
        scratches = (
            ".codearbiter/gate-events.log",
            ".codearbiter/.markers",
        )
        for scratch in scratches:
            for field in scalar_fields + list_fields:
                with self.subTest(scratch=scratch, field=field):
                    row = core_releaselib._new_row("app")
                    row["payload"] = "src/"
                    value = scratch + ("/receipt" if scratch.endswith(".markers") else "")
                    row[field] = value if field in scalar_fields else [value]
                    self.assertNotIn(
                        scratch,
                        core_releaselib.governance_scratch_exclusions(row))

    def test_scratch_overlap_is_casefolded_and_globs_fail_closed(self):
        for payload in (
                ".CODEARBITER", ".codearbiter/*", ":(top).codearbiter",
                ".codearbiter/gate-events.log src/"):
            with self.subTest(payload=payload):
                row = core_releaselib._new_row("app")
                row["payload"] = payload
                self.assertEqual(
                    core_releaselib.governance_scratch_exclusions(row), [])

        row = core_releaselib._new_row("app")
        row["payload"] = "src/"
        row["manifest"] = [".codearbiter./gate-events.log"]
        self.assertEqual(
            core_releaselib.governance_scratch_exclusions(row), [])

        row["manifest"] = [".codearbiter/GATE-E~1.LOG"]
        self.assertEqual(
            core_releaselib.governance_scratch_exclusions(row), [])

    def test_payload_exclude_subtracts_payload_but_direct_surfaces_win(self):
        row = core_releaselib._new_row("app")
        row["payload"] = "."
        row["payload_exclude"] = [".CODEARBITER/"]
        self.assertEqual(
            core_releaselib.governance_scratch_exclusions(row),
            [".codearbiter/gate-events.log", ".codearbiter/.markers"])

        row["payload_exclude"] = [".codearbiter/gate-events.log"]
        self.assertEqual(
            core_releaselib.governance_scratch_exclusions(row),
            [".codearbiter/gate-events.log"])

        for exclusion in (
                ".codearbiter/*", ":(top).codearbiter",
                ".codearbiter/gate-events.log src/", ".codearbiter./",
                ".codearbiter/gate-events.log.bak"):
            with self.subTest(exclusion=exclusion):
                row["payload_exclude"] = [exclusion]
                self.assertEqual(
                    core_releaselib.governance_scratch_exclusions(row), [])

        row["payload_exclude"] = [".codearbiter/"]
        row["manifest"] = [".CODEARBITER/gate-events.log"]
        self.assertEqual(
            core_releaselib.governance_scratch_exclusions(row),
            [".codearbiter/.markers"])


class ReleaseTreeStatusTimeoutTest(unittest.TestCase):
    """AC-02/#627 Finding 1 — `release_tree_status()`'s internal
    `git status --porcelain` probe must bound its `subprocess.run` call with
    `timeout=30` (matching every other of this module's 12 internal Git-probe
    call sites) and convert a hang into a failed synthetic probe rather than
    letting `subprocess.TimeoutExpired` escape uncaught. Reuses the fix design
    and regression-test idiom from issue #627's 2026-09-17 comment verbatim."""

    def test_a_hung_probe_returns_a_failed_result_not_an_exception(self):
        hang = subprocess.TimeoutExpired(
            cmd=["git", "status", "--porcelain"], timeout=30)
        with mock.patch.object(
                core_releaselib.subprocess, "run", side_effect=hang):
            probe = core_releaselib.release_tree_status({}, ".")
        self.assertNotEqual(probe.returncode, 0)
        self.assertIn("timed out", probe.stderr.lower())

    def test_a_normal_git_status_is_unaffected(self):
        # Sanity check against the real repository: an ordinary, fast probe
        # still succeeds and still returns porcelain-shaped output, proving
        # the timeout/exception-handling addition does not change the
        # non-hanging path.
        probe = core_releaselib.release_tree_status({}, REPO_ROOT)
        self.assertEqual(probe.returncode, 0)
        self.assertIsInstance(probe.stdout, str)


def _hermetic_pretag_fixture(test, tmp, commands=()):
    """A minimal, hermetic single-target consumer fixture shared by the
    T-03 AC-03 characterization classes below (`TreeStatusReturnCodeContractTest`,
    `RunPreTagProbeFailurePathTest`, `RunPreTagOperatorCommandTimeoutTest`).
    Mirrors `CoreCLITest._pretag_repo`'s hermetic git-identity/config
    sandbox in miniature -- duplicated here rather than reached into, since
    `CoreCLITest` is an unrelated, standalone giant class and this module's
    existing convention is a per-class-cluster fixture, not a shared
    top-level one."""
    root = os.path.join(tmp, "consumer")
    os.makedirs(os.path.join(root, ".codearbiter"))
    with open(os.path.join(root, "package.json"), "w") as fh:
        fh.write('{"version": "1.0.0"}\n')
    with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
        fh.write("# Changelog\n")
    with open(os.path.join(root, ".codearbiter", "release-targets.md"),
              "w") as fh:
        fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                 "changelog: CHANGELOG.md\npayload: .\n"
                 + "".join(f"pre-tag: {c}\n" for c in commands)
                 + "<!-- /release-targets -->\n")
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
        test.assertEqual(
            proc.returncode, 0,
            f"fixture git {argv[0]} failed: {proc.stderr.strip()}")
    return root


def _argv_text(call_args):
    """First-positional-arg text of a recorded `subprocess.run` call, for
    probe/dispatch discrimination in the spy-based tests below. Handles both
    dispatch shapes this module uses: a single command string (`shell=True`)
    and an argv list (`[posix_shell, "-c", command]` on Windows)."""
    if not call_args:
        return ""
    first = call_args[0]
    if isinstance(first, str):
        return first
    try:
        return " ".join(str(item) for item in first)
    except TypeError:
        return str(first)


class TreeStatusReturnCodeContractTest(unittest.TestCase):
    """AC-03 (T-03) -- `clean-tree-status` (the CLI route to
    `release_tree_status()`, `core/pysrc/_releaselib.py`) returns
    `probe.returncode` directly and never reinterprets porcelain CONTENT
    into an exit code. A clean tree and a dirty tree must BOTH exit 0 --
    only the porcelain STDOUT distinguishes them, never the return code --
    and a genuine probe failure (including the exact
    `subprocess.TimeoutExpired` case T-02 added a catch for) must reach this
    CLI route as a nonzero exit, never a false 0. The clean/dirty cases run
    the real CLI dispatch against a real, hermetic git fixture; the timeout
    case reuses T-02's own `side_effect` idiom
    (`ReleaseTreeStatusTimeoutTest` above), because a real 30-second hang
    cannot be exercised in a unit-test time budget."""

    def _clean_tree_status(self, root):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            exit_code = core_releaselib.main(["clean-tree-status", "app"])
        return exit_code, out.getvalue(), err.getvalue()

    def test_a_clean_tree_returns_zero_with_empty_porcelain_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp)
            exit_code, stdout, stderr = self._clean_tree_status(root)
        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(stdout.strip(), "")

    def test_a_dirty_tree_also_returns_zero_only_output_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp)
            with open(os.path.join(root, "package.json"), "w") as fh:
                fh.write('{"version": "1.1.0"}\n')
            exit_code, stdout, stderr = self._clean_tree_status(root)
        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("package.json", stdout)

    def test_a_probe_timeout_reaches_clean_tree_status_as_a_nonzero_exit(self):
        # The ONLY `subprocess.run` call on this route is
        # `release_tree_status()`'s own probe (`load_targets` is a pure
        # text parser), so an unconditional `TimeoutExpired` side_effect
        # exercises exactly the T-02 catch path without touching an
        # unrelated call.
        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp)
            hang = subprocess.TimeoutExpired(
                cmd=["git", "status", "--porcelain"], timeout=30)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                       side_effect=hang), \
                    contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                exit_code = core_releaselib.main(["clean-tree-status", "app"])
        self.assertNotEqual(exit_code, 0)
        self.assertIn("timed out", err.getvalue().lower())


class RunPreTagProbeFailurePathTest(unittest.TestCase):
    """AC-03 (T-03) -- a Git-probe FAILURE (nonzero returncode), specifically
    including the T-02 `subprocess.TimeoutExpired` catch, must reach
    `run-pre-tag`'s `_tree_state()` through the PROBE-FAILURE path (exit 8,
    "the tree-state PROBE itself failed") and never through the
    MUTATION-DETECTED path (exit 6, "MUTATED the tree") or a false success
    (exit 0). These are two distinct branches in `run-pre-tag`'s dispatch
    (`core/pysrc/_releaselib.py`): `_tree_state()` returns `(None, failure)`
    on any `probe.returncode != 0` BEFORE any content digest is ever
    computed, so a probe failure can never fall through into the
    digest-comparison branch that produces exit 6. `_tree_state()` has TWO
    call sites with independently reachable failure branches -- the
    baseline call (line ~3417, before any declared command runs) and the
    post-command call (line ~3514, immediately beside the exit-6 mutation
    comparison it feeds) -- so both are exercised separately below, not
    just the baseline. The pre-existing
    `CoreCLITest.test_run_pre_tag_exits_8_when_the_tree_state_probe_fails`
    already proves the baseline site for an UNRELATED failure cause (a
    directory that was never `git init`ed); this class proves both sites
    for the exact TIMEOUT cause T-02 introduced, which that pre-existing
    test does not exercise."""

    def test_a_timed_out_baseline_probe_takes_the_probe_failure_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp)
            hang = subprocess.TimeoutExpired(
                cmd=["git", "status", "--porcelain"], timeout=30)
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                       side_effect=hang), \
                    contextlib.redirect_stderr(err):
                exit_code = core_releaselib.main(["run-pre-tag", "app"])
        self.assertEqual(exit_code, 8, err.getvalue())
        self.assertIn("PROBE itself failed", err.getvalue())
        self.assertIn("timed out", err.getvalue().lower())
        self.assertNotIn("MUTATED", err.getvalue())

    def test_a_timed_out_post_command_probe_also_takes_the_probe_failure_path(self):
        # The baseline probe must succeed FOR REAL here (a real git inventory
        # over the real fixture, not mocked), so the run reaches the
        # post-command `_tree_state()` call -- the one sitting immediately
        # beside the exit-6 mutation-comparison branch -- and the timeout is
        # injected ONLY on the second probe call. If a future change ever
        # folded "probe failed after a command ran" into the mutation
        # branch instead of keeping it a distinct exit-8 outcome, this is
        # the test that would catch it; the baseline-only test above cannot.
        command = f'"{sys.executable}" -c "pass"'
        real_run = core_releaselib.subprocess.run
        probe_calls = {"count": 0}

        def spy(*args, **kwargs):
            argv = _argv_text(args)
            if ("ls-files" in argv and "--cached" in argv
                    and "--others" in argv):
                probe_calls["count"] += 1
                if probe_calls["count"] == 2:
                    raise subprocess.TimeoutExpired(cmd=args[0], timeout=30)
            return real_run(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp, [command])
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                       side_effect=spy), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(err):
                exit_code = core_releaselib.main(["run-pre-tag", "app"])
        self.assertEqual(exit_code, 8, err.getvalue())
        self.assertIn("PROBE itself failed after", err.getvalue())
        self.assertIn("timed out", err.getvalue().lower())
        self.assertNotIn("MUTATED", err.getvalue())


class RunPreTagOperatorCommandTimeoutTest(unittest.TestCase):
    """AC-03/P2 (T-03) -- the internal `timeout=30` T-02 added to
    `release_tree_status()`'s OWN `subprocess.run` call must not leak onto
    operator-declared `pre-tag` commands, dispatched through a SEPARATE
    `subprocess.run` call site (`run-pre-tag`'s command-dispatch loop,
    `core/pysrc/_releaselib.py`), which keeps its existing, untimed
    behavior -- required by the spec's P2 ("does not apply to
    operator-declared `pre-tag` commands"). Proven by spying on every real
    `subprocess.run` call made while `run-pre-tag` actually executes --
    nothing about the dispatch itself is faked, only observed -- and
    asserting that every call carrying `timeout=30` is an internal Git
    inventory/index probe (its argv names `ls-files`), while the call that actually runs the
    declared command carries no `timeout` kwarg at all.

    Platform note: this module dispatches a declared command through ONE of
    two branches depending on host (`core/pysrc/_releaselib.py`,
    `run-pre-tag`) -- `subprocess.run([posix_shell, "-c", command],
    shell=False, ...)` when a POSIX-compatible shell was resolved (always
    true off Windows; true on Windows only when Git for Windows' `bash.exe`
    resolves), or `subprocess.run(command, shell=True, ...)` otherwise. A
    single CI host only ever exercises one of the two branches per run, so
    full coverage of BOTH dispatch call sites is a union across this
    suite's Windows and POSIX CI legs, not a property any one host's run
    proves alone -- the same platform-fork shape `tech-stack.md` documents
    for `exec.ts`'s `awaitTaskkill`."""

    def test_declared_command_dispatch_carries_no_timeout(self):
        command = f'"{sys.executable}" -c "pass"'
        calls = []
        real_run = core_releaselib.subprocess.run

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return real_run(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            root = _hermetic_pretag_fixture(self, tmp, [command])
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                       side_effect=spy), \
                    contextlib.redirect_stdout(out):
                exit_code = core_releaselib.main(["run-pre-tag", "app"])

        self.assertEqual(exit_code, 0, out.getvalue())

        timed_calls = [(a, kw) for a, kw in calls if "timeout" in kw]
        self.assertTrue(
            timed_calls, "expected the internal tree-state probe to appear")
        for call_args, kwargs in timed_calls:
            self.assertEqual(kwargs["timeout"], 30)
            self.assertIn("ls-files", _argv_text(call_args))

        untimed_calls = [(a, kw) for a, kw in calls if "timeout" not in kw]
        declared_dispatch = [
            c for c in untimed_calls if command in _argv_text(c[0])]
        self.assertTrue(
            declared_dispatch,
            "expected the declared pre-tag command's own subprocess.run "
            "call, which must carry no `timeout` kwarg at all")


class AncestryRefusalTest(unittest.TestCase):
    """T-10, AC-09/#570 finding BODY-03: `last_tag_select`/`last_tag_select_
    for_policy` choose a series' highest tag by VALUE alone (pure functions,
    no git access, per this module's design invariants) -- they cannot know
    whether that tag's commit is actually in HEAD's own history. A sibling
    branch that diverged before the newest tag, an abandoned branch's stray
    push, or an unrelated orphan history sharing the series' prefix can
    still win the scan even though HEAD never descends from it, silently
    corrupting the derived `$BASE_VERSION`. `verify_tag_ancestor` /
    `verify-tag-ancestor` close this: confirm the SELECTED tag resolves to a
    commit reachable from HEAD before it is used for anything, refuse with
    the tag and the cause when it is not, and leave both the zero-tag
    first-release path and a genuine ancestor's behavior completely
    unaffected (P5 -- detects ambiguity, never chooses a different baseline,
    never implements maintenance-branch allocation policy).

    Exercises BOTH the direct function (`core_releaselib.verify_tag_
    ancestor`) and the CLI route (`core_releaselib.main(["verify-tag-
    ancestor", ...])`) against REAL disposable git repositories -- the
    ancestry graphs below are exactly the shapes #570's own comment names:
    a sibling branch, an unrelated/orphan history, a tag reachable only
    through a merge commit, and both annotated and lightweight tag forms."""

    def _git(self, repo, *args, check=True):
        environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_AUTHOR_NAME="ancestry-fixture",
            GIT_AUTHOR_EMAIL="ancestry@example.invalid",
            GIT_COMMITTER_NAME="ancestry-fixture",
            GIT_COMMITTER_EMAIL="ancestry@example.invalid",
        )
        return subprocess.run(
            [core_releaselib.git_executable(),
             "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false",
             "-c", "core.hooksPath=", "-c", "init.defaultBranch=main",
             *args],
            cwd=repo, env=environment, capture_output=True, text=True,
            timeout=30, check=check)

    def _init_repo(self, root):
        os.makedirs(root, exist_ok=True)
        self._git(root, "init", "--quiet")
        with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        self._git(root, "add", "seed.txt")
        self._git(root, "commit", "--quiet", "-m", "chore: seed")
        return root

    def _commit(self, root, name, message):
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write(f"{name}\n")
        self._git(root, "add", name)
        self._git(root, "commit", "--quiet", "-m", message)

    # -- the direct function, `verify_tag_ancestor` -------------------- #

    def test_zero_tag_sentinel_skips_the_check_entirely(self):
        # The zero-tag first-release path is a DISTINCT code path from tag
        # selection (P5) -- it must never even attempt a git probe, proven
        # here by pointing `project_root` at a directory that is not a git
        # repository at all and confirming no failure results.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = core_releaselib.verify_tag_ancestor(
                core_releaselib.NONE_SENTINEL, tmp)
        self.assertEqual(verdict, "zero-tag")

    def test_a_genuine_ancestor_tag_is_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "v1.0.0")
            self._commit(root, "later.txt", "feat: later work")
            verdict = core_releaselib.verify_tag_ancestor("v1.0.0", root)
        self.assertEqual(verdict, "ancestor")

    def test_an_annotated_ancestor_tag_is_confirmed_identically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "-a", "v1.0.0", "-m", "release v1.0.0")
            self._commit(root, "later.txt", "feat: later work")
            verdict = core_releaselib.verify_tag_ancestor("v1.0.0", root)
        self.assertEqual(verdict, "ancestor")

    def test_ancestor_reached_only_through_a_merge_commit_is_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "-b", "feature")
            self._commit(root, "feature.txt", "feat: feature work")
            self._git(root, "tag", "v1.0.0")
            self._git(root, "checkout", "-q", "main")
            self._git(root, "merge", "--no-ff", "-q", "-m",
                      "merge: bring in feature", "feature")
            verdict = core_releaselib.verify_tag_ancestor("v1.0.0", root)
        self.assertEqual(verdict, "ancestor")

    def test_a_sibling_branch_tag_that_diverged_before_head_is_refused(self):
        # The exact shape #570 finding BODY-03 names: a series tag pushed
        # from a sibling branch that diverged from HEAD before the tag was
        # made. Numerically it may still be the highest tag in the series,
        # but HEAD never descends from it.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "-b", "sibling")
            self._commit(root, "sibling.txt", "feat: sibling work")
            self._git(root, "tag", "v9.9.9")
            self._git(root, "checkout", "-q", "main")
            self._commit(root, "mainline.txt", "feat: mainline work")
            verdict = core_releaselib.verify_tag_ancestor("v9.9.9", root)
        self.assertEqual(verdict, "not-ancestor")

    def test_a_tag_on_an_unrelated_orphan_history_is_refused(self):
        # A completely disjoint root (no common ancestor at all) -- distinct
        # from the sibling-branch case above (which shares a root but
        # diverged), and independently confirmed to return the same
        # not-ancestor verdict rather than an error.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "--orphan", "orphan-history")
            self._git(root, "commit", "--quiet", "--allow-empty",
                      "-m", "chore: unrelated orphan root")
            self._git(root, "tag", "v9.9.9")
            self._git(root, "checkout", "-q", "main")
            verdict = core_releaselib.verify_tag_ancestor("v9.9.9", root)
        self.assertEqual(verdict, "not-ancestor")

    def test_an_unresolvable_tag_name_is_refused_as_unresolvable_not_not_ancestor(self):
        # A tag that does not exist at all must be classified distinctly
        # from a tag that exists but fails the reachability check -- no
        # verdict about reachability was ever reached for a ref that never
        # resolved.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            verdict = core_releaselib.verify_tag_ancestor(
                "v404.0.0-does-not-exist", root)
        self.assertEqual(verdict, "unresolvable")

    def test_a_probe_that_cannot_run_is_unresolvable_not_an_exception(self):
        # Mirrors the T-02 idiom (`ReleaseTreeStatusTimeoutTest`): a hang or
        # OSError from the underlying git probe must degrade to a
        # classification, never escape as an uncaught exception.
        hang = subprocess.TimeoutExpired(cmd=["git", "merge-base"], timeout=30)
        with mock.patch.object(
                core_releaselib.subprocess, "run", side_effect=hang):
            verdict = core_releaselib.verify_tag_ancestor("v1.0.0", ".")
        self.assertEqual(verdict, "unresolvable")

    # -- the CLI route, `verify-tag-ancestor` --------------------------- #

    def _run_cli(self, tag, project_root):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": project_root}), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = core_releaselib.main(["verify-tag-ancestor", tag])
        return rc, out.getvalue(), err.getvalue()

    def test_cli_zero_tag_sentinel_exits_0_unaffected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _out, err = self._run_cli(core_releaselib.NONE_SENTINEL, tmp)
        self.assertEqual(rc, 0, err)

    def test_cli_ancestor_exits_0_today_s_behavior_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "v1.0.0")
            self._commit(root, "later.txt", "feat: later work")
            rc, _out, err = self._run_cli("v1.0.0", root)
        self.assertEqual(rc, 0, err)
        self.assertEqual(err, "")

    def test_cli_refuses_a_non_ancestor_tag_naming_the_tag_and_the_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "-b", "sibling")
            self._commit(root, "sibling.txt", "feat: sibling work")
            self._git(root, "tag", "v9.9.9")
            self._git(root, "checkout", "-q", "main")
            self._commit(root, "mainline.txt", "feat: mainline work")
            rc, _out, err = self._run_cli("v9.9.9", root)
        self.assertEqual(rc, 1)
        self.assertIn("v9.9.9", err)
        self.assertIn("not", err.lower())
        self.assertNotIn("fall back to an older tag", err)  # never says it WILL

    def test_cli_refuses_an_unresolvable_tag_naming_the_tag_and_the_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            rc, _out, err = self._run_cli("v404.0.0-does-not-exist", root)
        self.assertEqual(rc, 2)
        self.assertIn("v404.0.0-does-not-exist", err)
        self.assertIn("resolve", err.lower())

    def test_cli_never_prints_a_replacement_tag_on_refusal(self):
        # AC-09's own wording: "never a silent fallback to an older tag".
        # Stdout must stay empty on every refusal path -- a caller piping
        # stdout into `$LAST_TAG` (as Pre-flight's own prose does for the
        # SELECTION step) must never receive a substitute value from this
        # verification step.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "-b", "sibling")
            self._commit(root, "sibling.txt", "feat: sibling work")
            self._git(root, "tag", "v9.9.9")
            self._git(root, "checkout", "-q", "main")
            self._commit(root, "mainline.txt", "feat: mainline work")
            rc_bad, out_bad, _err = self._run_cli("v9.9.9", root)
            rc_missing, out_missing, _err2 = self._run_cli(
                "v404.0.0-does-not-exist", root)
        self.assertEqual((rc_bad, out_bad), (1, ""))
        self.assertEqual((rc_missing, out_missing), (2, ""))

    def test_end_to_end_selection_then_verification_on_a_genuine_ancestor(self):
        # The full Pre-flight sequence: select LAST_TAG via the existing,
        # UNCHANGED `last-tag-for-policy` command, then verify it via the
        # new command -- proving the two compose exactly as the skill's
        # prose now wires them, with neither step's own behavior altered.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "v1.0.0")
            self._commit(root, "later.txt", "feat: later work")
            tags_out = self._git(root, "tag", "-l").stdout
            select_out = io.StringIO()
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(tags_out)
            try:
                with contextlib.redirect_stdout(select_out):
                    select_rc = core_releaselib.main(
                        ["last-tag-for-policy", "v", "semver", ""])
            finally:
                sys.stdin = old_stdin
            selected_tag = select_out.getvalue().strip()
            self.assertEqual(select_rc, 0)
            self.assertEqual(selected_tag, "v1.0.0")
            verify_rc, _out, verify_err = self._run_cli(selected_tag, root)
        self.assertEqual(verify_rc, 0, verify_err)


class VerifyTagAncestorArgvGuardTest(unittest.TestCase):
    """R-01, Scope-C security-review finding 1 (MEDIUM): `verify_tag_ancestor`
    validated `tag` only with `not isinstance(tag, str) or not tag` before
    placing it as a bare argv element in `git merge-base --is-ancestor <tag>
    <candidate>`, with no end-of-options `--` separator -- unlike this
    module's established precedent for the identical input class at
    `_committed_changelog_text`, which explicitly rejects a leading `-` and
    an embedded NUL before a revision reaches git. `verify_tag_ancestor` now
    mirrors that same predicate (`startswith("-")` / `"\\0" in`) for BOTH
    `tag` and `candidate` -- both reach the identical argv position -- and
    additionally inserts `--` before the two revisions, matching this
    module's own `--` precedent (lines ~984, ~2096, ~2565).

    Every rejection case asserts `subprocess.run` is never even called --
    not merely that the verdict happens to read `"unresolvable"`, which a
    dash-prefixed tag could also reach today via git's own option-parse
    failure (exit 129) without the guard existing at all. That weaker
    assertion would pass against the unpatched function and prove nothing."""

    def test_leading_dash_tag_is_refused_before_the_subprocess_call(self):
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict = core_releaselib.verify_tag_ancestor("-v1.0.0", ".")
        self.assertEqual(verdict, "unresolvable")
        run.assert_not_called()

    def test_nul_containing_tag_is_refused_before_the_subprocess_call(self):
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict = core_releaselib.verify_tag_ancestor("v1.0\x000", ".")
        self.assertEqual(verdict, "unresolvable")
        run.assert_not_called()

    def test_leading_dash_candidate_is_refused_before_the_subprocess_call(self):
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict = core_releaselib.verify_tag_ancestor(
                "v1.0.0", ".", candidate="--upload-pack=evil")
        self.assertEqual(verdict, "unresolvable")
        run.assert_not_called()

    def test_nul_containing_candidate_is_refused_before_the_subprocess_call(self):
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict = core_releaselib.verify_tag_ancestor(
                "v1.0.0", ".", candidate="HEAD\x00")
        self.assertEqual(verdict, "unresolvable")
        run.assert_not_called()

    def test_non_string_and_empty_tag_still_refused_pre_existing_leg_unchanged(self):
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict_none = core_releaselib.verify_tag_ancestor(None, ".")
            verdict_empty = core_releaselib.verify_tag_ancestor("", ".")
        self.assertEqual(verdict_none, "unresolvable")
        self.assertEqual(verdict_empty, "unresolvable")
        run.assert_not_called()

    def test_zero_tag_sentinel_wins_even_with_a_dash_like_candidate(self):
        # NONE_SENTINEL must keep short-circuiting ahead of the new guard --
        # the zero-tag first-release path stays a completely distinct code
        # path (P5), never touching the subprocess boundary at all.
        with mock.patch.object(core_releaselib.subprocess, "run") as run:
            verdict = core_releaselib.verify_tag_ancestor(
                core_releaselib.NONE_SENTINEL, ".", candidate="-evil")
        self.assertEqual(verdict, "zero-tag")
        run.assert_not_called()

    def test_an_ordinary_tag_reaches_the_probe_with_the_end_of_options_separator(self):
        # The guard must not over-reject ordinary input, and the `--`
        # insertion itself must be proven, not merely assumed: the captured
        # argv must place `--` immediately before the two revisions, in
        # order, not merely appear somewhere in the argument list.
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        with mock.patch.object(
                core_releaselib.subprocess, "run",
                return_value=completed) as run:
            verdict = core_releaselib.verify_tag_ancestor("v1.0.0", ".")
        self.assertEqual(verdict, "ancestor")
        run.assert_called_once()
        argv = run.call_args.args[0]
        self.assertEqual(argv[-4:], ["--is-ancestor", "--", "v1.0.0", "HEAD"])


class AncestryGraphsTest(unittest.TestCase):
    """T-11, AC-09/AC-16 (#570 finding BODY-03): proves the END-TO-END
    SKILL.md-documented Pre-flight flow -- `last-tag-for-policy` (stdin =
    `git tag -l`'s output) piped into `verify-tag-ancestor` on the SELECTED
    tag, then `$BASE_VERSION` derived from the result -- against REAL
    disposable git repositories with more elaborate graph shapes than
    `AncestryRefusalTest` (T-10) needed.

    T-10's suite proves `verify_tag_ancestor`/`verify-tag-ancestor` in
    ISOLATION: it hands the function (or the CLI) an already-known tag name
    directly. This class never does that -- every test here starts from
    `git tag -l` and lets `last-tag-for-policy` do the SELECTING, exactly as
    Pre-flight's prose wires the two commands (`core/surface/skills/release/
    SKILL.md`, "Resolve `LAST_TAG`..." immediately followed by "Verify
    `LAST_TAG` is actually reachable..."), so a defect in how the two
    compose -- not either one alone -- has somewhere to surface. Both stages
    run as REAL subprocess calls against the actual CLI entry point
    (`_CORE_RELEASELIB_PATH`), chained by captured stdout, never `shell=True`
    and never `core_releaselib.main()` called in-process -- a hermeticity or
    argv-shape defect at the real subprocess boundary is exactly what an
    in-process call cannot catch."""

    def _git(self, repo, *args, check=True):
        environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_AUTHOR_NAME="ancestry-graph-fixture",
            GIT_AUTHOR_EMAIL="ancestry-graph@example.invalid",
            GIT_COMMITTER_NAME="ancestry-graph-fixture",
            GIT_COMMITTER_EMAIL="ancestry-graph@example.invalid",
        )
        return subprocess.run(
            [core_releaselib.git_executable(),
             "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false",
             "-c", "core.hooksPath=", "-c", "init.defaultBranch=main",
             *args],
            cwd=repo, env=environment, capture_output=True, text=True,
            timeout=30, check=check)

    def _init_repo(self, root):
        os.makedirs(root, exist_ok=True)
        self._git(root, "init", "--quiet")
        with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        self._git(root, "add", "seed.txt")
        self._git(root, "commit", "--quiet", "-m", "chore: seed")
        return root

    def _commit(self, root, name, message):
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write(f"{name}\n")
        self._git(root, "add", name)
        self._git(root, "commit", "--quiet", "-m", message)

    def _run_last_tag_for_policy(self, tags_text, prefix, policy, initial, cwd):
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH,
             "last-tag-for-policy", prefix, policy, initial or ""],
            input=tags_text, capture_output=True, text=True, cwd=cwd,
            timeout=30)

    def _run_verify_ancestor(self, tag, project_root):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=project_root)
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "verify-tag-ancestor", tag],
            capture_output=True, text=True, cwd=project_root, env=env,
            timeout=30)

    def _repo_fingerprint(self, root):
        # `git status --porcelain` (working-tree/index mutation) and `git
        # for-each-ref` (every ref -- tags, branches, HEAD -- and the exact
        # object each one names) together are the "refusal precedes any
        # mutation" proof surface: a written file, a moved ref, or a newly
        # created tag would change one or the other.
        status = self._git(root, "status", "--porcelain").stdout
        refs = self._git(root, "for-each-ref").stdout
        return status, refs

    def _full_flow(self, root, prefix, policy="semver", initial=""):
        """Run the exact documented two-stage Pre-flight pipeline for real:
        `git tag -l` -> `last-tag-for-policy` -> `verify-tag-ancestor`.
        Returns `(last_tag, verify_rc, verify_stdout, verify_stderr)`."""
        tags_text = self._git(root, "tag", "-l").stdout
        select = self._run_last_tag_for_policy(
            tags_text, prefix, policy, initial, root)
        self.assertEqual(select.returncode, 0, select.stderr)
        last_tag = select.stdout.strip()
        verify = self._run_verify_ancestor(last_tag, root)
        return last_tag, verify.returncode, verify.stdout, verify.stderr

    def _base_version(self, last_tag, policy="semver", initial=None):
        # Mirrors Pre-flight's own `$BASE_VERSION` rule with no declared
        # manifest in play: the bare `LAST_TAG` version, or the policy's
        # first-release floor (`0.0.0` for semver, `$INITIAL_VERSION` for
        # numeric-sequence) when `LAST_TAG` is the `<none>` sentinel.
        if last_tag == core_releaselib.NONE_SENTINEL:
            return initial if policy == "numeric-sequence" else "0.0.0"
        return core_releaselib._bare_version(last_tag, policy, initial)

    def test_sibling_branch_diverged_before_tag_full_flow_refuses_and_mutates_nothing(self):
        # The exact shape #570 finding BODY-03 names, run through the FULL
        # documented flow (selection THEN verification) rather than handing
        # `verify-tag-ancestor` an already-known tag directly.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "checkout", "-q", "-b", "sibling")
            self._commit(root, "sibling.txt", "feat: sibling work")
            self._git(root, "tag", "v9.9.9")
            self._git(root, "checkout", "-q", "main")
            self._commit(root, "mainline.txt", "feat: mainline work")

            before = self._repo_fingerprint(root)
            last_tag, rc, out, err = self._full_flow(root, "v")
            after = self._repo_fingerprint(root)

        self.assertEqual(
            last_tag, "v9.9.9",
            "the sibling tag is genuinely the numeric-highest in the "
            "series -- selection alone cannot and must not catch this")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "", "a refusal must never print a substitute "
                          "tag on stdout -- a caller piping this into "
                          "$LAST_TAG must never receive one")
        self.assertIn("v9.9.9", err)
        self.assertEqual(
            before, after,
            "the full refusal flow must not write a file, move a ref, or "
            "create a tag -- refusal precedes any mutation")

    def test_decoy_sibling_series_prefix_scoping_plus_ancestry_produce_correct_pass(self):
        # A DIFFERENT target's tag series ("docs-v99.0.0") numerically
        # outranks EVERY tag in this target's own "v" series and sits on a
        # branch this target's HEAD never descends from. A regex anchored
        # on "^v" would never even match "docs-v99.0.0" regardless of the
        # graph shape, so a decoy excluded on prefix ALONE would leave this
        # test true for a reason that has nothing to do with the graph --
        # this fixture also declares a GENUINE, same-prefix, REACHABLE
        # higher tag ("v2.0.0") so last-tag-for-policy must still do real
        # selection work among "v"-series candidates while ignoring the
        # differently-prefixed decoy, not merely default to the one
        # pre-decoy tag because nothing else matched. If prefix scoping in
        # `last-tag-for-policy` ever leaked the decoy into this target's
        # selection, ancestry verification would independently refuse it
        # too (proven below by calling `verify-tag-ancestor` on the decoy
        # directly) -- but the CORRECT behavior is that scoping excludes it
        # FIRST and correctly picks "v2.0.0" over both "v1.0.0" and the
        # decoy, so verification runs against this target's own genuine
        # ancestor tag and the full flow PASSES. Neither mechanism alone
        # proves this composed outcome: a scoping-only test cannot show the
        # flow still passes end-to-end, and an ancestry-only test cannot
        # show the decoy never reaches selection in the first place.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "v1.0.0")
            self._git(root, "checkout", "-q", "-b", "docs-series")
            self._commit(root, "docs.txt", "docs: unrelated docs series")
            self._git(root, "tag", "docs-v99.0.0")
            self._git(root, "checkout", "-q", "main")
            self._commit(root, "mainline.txt", "feat: mainline work")
            self._git(root, "tag", "v2.0.0")
            self._commit(root, "mainline2.txt", "feat: further mainline work")

            last_tag, rc, out, err = self._full_flow(root, "v")
            # What WOULD have happened had the decoy leaked past scoping --
            # confirms the "or the ancestry check" half of the composed
            # claim, not merely that scoping happened to exclude it.
            decoy_verify = self._run_verify_ancestor("docs-v99.0.0", root)

        self.assertEqual(
            last_tag, "v2.0.0",
            "must select the genuine highest REACHABLE same-prefix tag -- "
            "neither the older real tag nor the numerically-higher decoy "
            "from a DIFFERENT declared series")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(
            decoy_verify.returncode, 1,
            "the decoy tag, checked directly, is independently confirmed "
            "NOT an ancestor -- scoping and ancestry agree, they do not "
            "merely happen not to collide")
        self.assertEqual(self._base_version(last_tag), "2.0.0")

    def test_annotated_tag_survives_the_full_documented_command_chain(self):
        # T-10's `AncestryRefusalTest.test_an_annotated_ancestor_tag_is_
        # confirmed_identically` proves `verify_tag_ancestor` itself does
        # not care whether a tag is annotated or lightweight. This proves
        # the SAME fact survives the FULL two-stage CLI chain -- `git tag
        # -l` listing the annotated tag's NAME (not its own tag-object
        # SHA), `last-tag-for-policy` selecting that name from stdin, and
        # `verify-tag-ancestor` transparently peeling the annotated tag
        # object down to its target commit the way `git merge-base
        # --is-ancestor` does internally -- and that the value stays the
        # tag's NAME throughout, never silently resolved to a commit or
        # tag-object SHA, which would corrupt every later step that reuses
        # `$LAST_TAG` as a string (deriving `$RELEASE_TAG`, comparing
        # against the changelog heading).
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "-a", "v1.0.0", "-m", "release v1.0.0")
            self._commit(root, "later.txt", "feat: later work")

            tag_object_sha = self._git(root, "rev-parse", "v1.0.0").stdout.strip()
            tag_commit_sha = self._git(
                root, "rev-parse", "v1.0.0^{commit}").stdout.strip()
            self.assertNotEqual(
                tag_object_sha, tag_commit_sha,
                "fixture premise check -- this must be a real annotated "
                "tag OBJECT distinct from the commit it points at, or "
                "the rest of this test proves nothing about peeling")

            last_tag, rc, out, err = self._full_flow(root, "v")

        self.assertEqual(last_tag, "v1.0.0")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(self._base_version(last_tag), "1.0.0")

    def test_zero_tag_path_through_full_flow_computes_base_version_correctly(self):
        # A fresh repository, no tags at all -- `git tag -l` prints
        # nothing, `last-tag-for-policy` prints the `<none>` sentinel, and
        # `verify-tag-ancestor` must treat that sentinel as its own
        # distinct, unaffected code path (never attempting a git probe
        # against a nonexistent ref) -- proven here through the actual CLI
        # chain, not by calling the function with the sentinel directly as
        # T-10's suite already does.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))

            before = self._repo_fingerprint(root)
            last_tag, rc, out, err = self._full_flow(root, "v")
            after = self._repo_fingerprint(root)

        self.assertEqual(last_tag, core_releaselib.NONE_SENTINEL)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(
            before, after,
            "the zero-tag pass-through must not write a file, move a "
            "ref, or create a tag either")
        self.assertEqual(self._base_version(last_tag), "0.0.0")
        # Policy-aware, not a hardcoded "0.0.0" -- the zero-tag path's
        # $BASE_VERSION floor is $INITIAL_VERSION under numeric-sequence.
        self.assertEqual(
            self._base_version(last_tag, "numeric-sequence", "0.30"), "0.30")


class AncestryRepoRootBindingTest(unittest.TestCase):
    """R-02, Scope-C security review finding 2 (MEDIUM): `verify_tag_
    ancestor`/`verify-tag-ancestor` already resolved their own `project_
    root` from `CLAUDE_PROJECT_DIR` (env-first, `os.getcwd()` fallback,
    T-10/R-01) -- but the bare `git tag -l` / `git fetch --tags origin` /
    `git fetch origin "$DEFAULT_BRANCH"` / `git branch --show-current`
    commands immediately adjacent to it in SKILL.md's Pre-flight sequence
    had no such pinning and resolved against whatever the invoking shell's
    OWN cwd happened to be. When `CLAUDE_PROJECT_DIR` and the shell's
    actual cwd name two different checkouts of the SAME repository (this
    repository's own linked-worktree session today is exactly that shape),
    the tag SELECTED from one checkout's tag list could be ancestry-
    VERIFIED against a DIFFERENT checkout's `HEAD`.

    The fix has TWO parts, both proven here against the real CLI at
    `_CORE_RELEASELIB_PATH`, never `core_releaselib.main()` called
    in-process:

      1. Every bare `git` command in the sequence is pinned via `-C
         "$PROJECT_ROOT"` to ONE value resolved once, up front.
      2. `verify-tag-ancestor` now accepts `$PROJECT_ROOT` as an explicit
         SECOND argument, which is used VERBATIM -- no environment read
         happens at all when it is given. Without this second half, the
         shell's `$PROJECT_ROOT` and this CLI's OWN internal `CLAUDE_
         PROJECT_DIR`-or-`os.getcwd()` resolution are still two
         INDEPENDENT reads that merely happen to agree whenever the
         environment variable is set and unchanged since -- never a
         guarantee, and on a host with no such variable at all (or any
         session where it is unset), both legs silently fall back to
         "current directory" read at two different MOMENTS, which can
         diverge with no error of any kind.

    `test_pinned_project_root_keeps_selection_and_verification_bound_to_
    the_same_checkout` proves part 1 (the pre-R-02 split, and the `-C`
    fix). `test_explicit_second_argument_closes_the_gap_even_with_no_
    environment_variable_at_all` proves part 2 in isolation: it never
    sets `CLAUDE_PROJECT_DIR` at all, so the CLI's OWN internal resolution
    (if it were still relied on) would silently read `os.getcwd()` --
    whatever the subprocess's own cwd happens to be -- and could disagree
    with the SAME `project_root` the caller already resolved and is
    passing explicitly."""

    def _git(self, repo, *args, check=True):
        environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_AUTHOR_NAME="repo-root-binding-fixture",
            GIT_AUTHOR_EMAIL="repo-root-binding@example.invalid",
            GIT_COMMITTER_NAME="repo-root-binding-fixture",
            GIT_COMMITTER_EMAIL="repo-root-binding@example.invalid",
        )
        return subprocess.run(
            [core_releaselib.git_executable(),
             "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false",
             "-c", "core.hooksPath=", "-c", "init.defaultBranch=main",
             *args],
            cwd=repo, env=environment, capture_output=True, text=True,
            timeout=30, check=check)

    def _init_repo(self, root):
        os.makedirs(root, exist_ok=True)
        self._git(root, "init", "--quiet")
        with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as fh:
            fh.write("seed\n")
        self._git(root, "add", "seed.txt")
        self._git(root, "commit", "--quiet", "-m", "chore: seed")
        return root

    def _commit(self, root, name, message):
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write(f"{name}\n")
        self._git(root, "add", name)
        self._git(root, "commit", "--quiet", "-m", message)

    def _clone(self, src, dest):
        self._git(os.path.dirname(dest) or ".", "clone", "--quiet", src, dest)

    def _select_last_tag(self, tag_list_root):
        """Runs the real CLI chain `git tag -l` (against `tag_list_root`)
        piped into `last-tag-for-policy` -- mirrors SKILL.md's `git -C
        "$PROJECT_ROOT" tag -l | ... last-tag-for-policy ...` with
        `tag_list_root` standing in for whatever root the (possibly
        unpinned) `git tag -l` actually resolved against."""
        tags_text = self._git(tag_list_root, "tag", "-l").stdout
        select = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH,
             "last-tag-for-policy", "v", "semver", ""],
            input=tags_text, capture_output=True, text=True,
            cwd=tag_list_root, timeout=30)
        self.assertEqual(select.returncode, 0, select.stderr)
        return select.stdout.strip()

    def _verify_ancestor(self, tag, project_root, *, subprocess_cwd=None):
        """The R-02-fixed call shape: `project_root` is passed as the
        explicit SECOND CLI argument, never via `CLAUDE_PROJECT_DIR` --
        `subprocess_cwd` (defaulting to `project_root` itself when
        omitted) is deliberately allowed to be a DIFFERENT directory, and
        `CLAUDE_PROJECT_DIR` is deliberately POPPED from the environment
        entirely, to prove this call never depends on either."""
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH,
             "verify-tag-ancestor", tag, project_root],
            capture_output=True, text=True,
            cwd=subprocess_cwd or project_root, env=env, timeout=30)

    def test_pinned_project_root_keeps_selection_and_verification_bound_to_the_same_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin = self._init_repo(os.path.join(tmp, "origin"))
            self._git(origin, "tag", "v1.0.0")
            self._commit(origin, "mainline2.txt", "feat: mainline work")

            project_root = os.path.join(tmp, "project-checkout")
            self._clone(origin, project_root)

            # A SEPARATE checkout of the same repo -- e.g. a stray linked
            # worktree or an operator's old clone -- carrying its own
            # LOCAL, never-fetched-into-project_root tag. This is the
            # concrete instance of "an abandoned branch's stray push" the
            # ancestry check's own docstring names, here applied across
            # TWO checkouts rather than two branches of one checkout.
            shell_cwd = os.path.join(tmp, "stray-checkout")
            self._clone(origin, shell_cwd)
            self._commit(shell_cwd, "stray.txt", "feat: stray local work")
            self._git(shell_cwd, "tag", "v9.9.9")

            # -- (1) PRE-R-02: `git tag -l` unpinned, resolving against
            #    shell_cwd -- exactly what a bare command with no `-C`
            #    does when the shell physically sits there.
            old_last_tag = self._select_last_tag(shell_cwd)
            self.assertEqual(
                old_last_tag, "v9.9.9",
                "the decoy from the stray checkout must genuinely win an "
                "unpinned selection, or this fixture proves nothing about "
                "the split")
            old_verify = self._verify_ancestor(old_last_tag, project_root)
            self.assertEqual(
                old_verify.returncode, 2,
                "verifying a tag SELECTED from a DIFFERENT checkout than "
                "the one it is VERIFIED against must produce a spurious "
                "refusal -- project_root has never even fetched a tag "
                "named v9.9.9, even though project_root's OWN v1.0.0 "
                "baseline is a perfectly genuine, unambiguous ancestor")

            # -- (2) R-02 FIX: `git tag -l` pinned to project_root via
            #    `-C "$PROJECT_ROOT"`, regardless of where the shell
            #    physically sits.
            new_last_tag = self._select_last_tag(project_root)
            self.assertEqual(
                new_last_tag, "v1.0.0",
                "pinned to project_root, selection must see ONLY "
                "project_root's own genuine tag -- the stray checkout's "
                "decoy must never even be a candidate")
            new_verify = self._verify_ancestor(new_last_tag, project_root)
            self.assertEqual(
                new_verify.returncode, 0,
                f"{new_verify.stderr} -- selection and verification are "
                "now bound to the IDENTICAL resolved root, so the genuine "
                "ancestor is confirmed cleanly -- the split this test "
                "proves closed")

    def test_explicit_second_argument_closes_the_gap_even_with_no_environment_variable_at_all(self):
        # Isolates part 2 of the fix from part 1: `CLAUDE_PROJECT_DIR` is
        # never set at all (proven by `_verify_ancestor` popping it), and
        # the subprocess's OWN cwd is deliberately pointed at the WRONG
        # checkout (`shell_cwd`) -- if this CLI still relied on its legacy
        # internal env-or-cwd resolution for a caller that happens to omit
        # the second argument, it would silently resolve against
        # `shell_cwd` here. Passing `project_root` EXPLICITLY as the
        # second argument must resolve against `project_root` regardless.
        with tempfile.TemporaryDirectory() as tmp:
            origin = self._init_repo(os.path.join(tmp, "origin"))
            self._git(origin, "tag", "v1.0.0")
            self._commit(origin, "mainline2.txt", "feat: mainline work")

            project_root = os.path.join(tmp, "project-checkout")
            self._clone(origin, project_root)

            # shell_cwd never even fetched v1.0.0 -- if the explicit
            # argument were ignored and this call fell back to resolving
            # against the subprocess's own cwd, `git merge-base` would
            # fail to resolve v1.0.0 there at all.
            shell_cwd = self._init_repo(os.path.join(tmp, "unrelated-repo"))

            verify = self._verify_ancestor(
                "v1.0.0", project_root, subprocess_cwd=shell_cwd)
            self.assertEqual(
                verify.returncode, 0,
                f"{verify.stderr} -- the explicit second argument must "
                "bind ancestry verification to project_root, never to "
                "the subprocess's own cwd, with or without "
                "CLAUDE_PROJECT_DIR set")

    def test_legacy_one_argument_form_is_unchanged_for_backward_compatibility(self):
        # The 1-argument form (env-first, `os.getcwd()` fallback) is kept
        # for any OTHER caller of this CLI -- `AncestryRefusalTest`/
        # `AncestryGraphsTest` (T-10/T-11) already exercise it extensively;
        # this confirms the WIDENED dispatch guard (`len(rest) in (1, 2)`)
        # did not silently change its behavior.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_repo(os.path.join(tmp, "repo"))
            self._git(root, "tag", "v1.0.0")
            self._commit(root, "later.txt", "feat: later work")
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
            proc = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH,
                 "verify-tag-ancestor", "v1.0.0"],
                capture_output=True, text=True, cwd=root, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_skillmd_pins_every_bare_preflight_command_to_project_root(self):
        # Structural companion to the behavioral proofs above: the
        # INSTALLED prose must actually spell the `-C "$PROJECT_ROOT"`
        # pinning on all four named commands, and thread `$PROJECT_ROOT`
        # explicitly into `verify-tag-ancestor`, not just describe the
        # concept. `test_consumer_smoke.AncestryRepoRootBindingTest` runs
        # the LITERAL extracted text for the two ancestry-adjacent
        # commands; this covers the two this task's own verification
        # command does not otherwise exercise end-to-end
        # (`git fetch --tags origin` / `git fetch origin "$DEFAULT_BRANCH"`
        # never mutate a real remote in a unit test).
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        preflight = text[text.index("## Pre-flight"):text.index("## Phase 1")]
        # Host-conditional resolution (`{{IF:claude}}`/`{{ELSE}}`/`{{END}}`,
        # per `core/hosts.json`'s per-host token grammar): the Claude-only
        # env-var name must never leak into the unconditional prose a
        # Codex/Pi render would also carry verbatim.
        self.assertIn("{{IF:claude}}", text)
        self.assertIn(
            'PROJECT_ROOT=${CLAUDE_PROJECT_DIR:-$(pwd)}', text)
        self.assertIn("{{ELSE}}", text)
        self.assertIn('PROJECT_ROOT=$(pwd)', text)
        self.assertIn("{{END}}", text)
        self.assertIn('git -C "$PROJECT_ROOT" branch --show-current', preflight)
        self.assertIn('git -C "$PROJECT_ROOT" fetch --tags origin', preflight)
        self.assertIn(
            'git -C "$PROJECT_ROOT" fetch origin "$DEFAULT_BRANCH"', preflight)
        self.assertIn('git -C "$PROJECT_ROOT" tag -l', preflight)
        # `verify-tag-ancestor` takes $PROJECT_ROOT as an explicit SECOND
        # argument -- never merely relying on its own internal environment
        # read to happen to match.
        self.assertIn(
            '"$PY" "{{PLUGIN_ROOT}}/hooks/_releaselib.py" '
            'verify-tag-ancestor "$LAST_TAG" "$PROJECT_ROOT"', preflight)


class NumericSequenceVersionPolicyTest(unittest.TestCase):
    """AC-01/02/04/10: generic fixed-shape sequencing and SemVer parity."""

    def test_numeric_key_accepts_only_canonical_fixed_shape_values(self):
        self.assertEqual(
            core_releaselib.numeric_sequence_key("0.31", "0.1"), (0, 31))
        for candidate in ("0.31.0", "00.31", "0.031", "0.-1", "0.x", "0"):
            with self.subTest(candidate=candidate):
                self.assertIsNone(
                    core_releaselib.numeric_sequence_key(candidate, "0.1"))

    def test_selects_highest_same_shape_tag_and_ignores_malformed_candidates(self):
        tags = [
            "preview-0.9", "preview-0.30", "preview-0.31",
            "preview-0.032", "preview-0.31.1", "preview-1", "v9.9.9",
        ]
        self.assertEqual(
            core_releaselib.last_tag_select_for_policy(
                tags, "preview-", "numeric-sequence", "0.1"),
            "preview-0.31")

    def test_first_release_uses_initial_then_each_later_release_advances_once(self):
        self.assertEqual(
            core_releaselib.derive_version(
                core_releaselib.NONE_SENTINEL, "minor",
                "numeric-sequence", "0.30"),
            "0.30")
        self.assertEqual(
            core_releaselib.derive_version(
                "0.30", "patch", "numeric-sequence", "0.1"),
            "0.31")
        self.assertEqual(
            core_releaselib.derive_version(
                "0.31", "major", "numeric-sequence", "0.1"),
            "0.32")
        self.assertTrue(
            core_releaselib.version_greater(
                "0.30", core_releaselib.NONE_SENTINEL,
                "numeric-sequence", "0.30"))

    def test_one_unchanged_parsed_declaration_drives_consecutive_releases(self):
        text = (
            "<!-- release-targets -->\n[preview]\n"
            "prefix: preview-\nchangelog: CHANGELOG.md\npayload: .\n"
            "version-policy: numeric-sequence\ninitial-version: 0.30\n"
            "<!-- /release-targets -->\n")
        row = core_releaselib.parse_release_targets(text)[0]
        selected = core_releaselib.last_tag_select_for_policy(
            ["preview-0.29", "preview-0.30"], row["prefix"],
            row["version_policy"], row["initial_version"])
        first_base = selected[len(row["prefix"]):]
        first_next = core_releaselib.derive_version(
            first_base, "patch", row["version_policy"], row["initial_version"])
        second_next = core_releaselib.derive_version(
            first_next, "minor", row["version_policy"], row["initial_version"])
        self.assertEqual((selected, first_next, second_next),
                         ("preview-0.30", "0.31", "0.32"))

    def test_every_bumping_word_advances_numeric_sequence_but_none_refuses(self):
        for word in ("patch", "minor", "major"):
            with self.subTest(word=word):
                self.assertEqual(
                    core_releaselib.derive_version(
                        "2.9", word, "numeric-sequence", "0.1"),
                    "2.10")
        self.assertIsNone(
            core_releaselib.derive_version(
                "2.9", "none", "numeric-sequence", "0.1"))

    def test_regressing_or_shape_changing_floor_is_refused(self):
        self.assertFalse(
            core_releaselib.version_greater(
                "0.30", "0.31", "numeric-sequence", "0.1"))
        self.assertFalse(
            core_releaselib.version_greater(
                "0.32.0", "0.31", "numeric-sequence", "0.1"))
        self.assertTrue(
            core_releaselib.version_greater(
                "0.32", "0.31", "numeric-sequence", "0.1"))

    def test_initial_version_constrains_candidate_not_a_lower_historical_floor(self):
        self.assertTrue(
            core_releaselib.version_greater(
                "0.30", "0.29", "numeric-sequence", "0.30"))
        self.assertFalse(
            core_releaselib.version_greater(
                "0.29", "0.28", "numeric-sequence", "0.30"))

    def test_three_component_numeric_sequence_preserves_shape(self):
        tags = ["train-1.0.9", "train-1.0.10", "train-1.00.11", "train-1.1"]
        self.assertEqual(
            core_releaselib.last_tag_select_for_policy(
                tags, "train-", "numeric-sequence", "1.0.0"),
            "train-1.0.10")
        self.assertEqual(
            core_releaselib.derive_version(
                "1.0.10", "major", "numeric-sequence", "1.0.0"),
            "1.0.11")

    def test_default_policy_delegates_to_existing_semver_behavior(self):
        tags = ["v1.9.9", "v2.0.0", "v2.0.1-rc.1"]
        self.assertEqual(
            core_releaselib.last_tag_select_for_policy(tags, "v"),
            core_releaselib.last_tag_select(tags, "v"))
        self.assertEqual(
            core_releaselib.derive_version("2.3.4", "minor"),
            core_releaselib.apply_bump("2.3.4", "minor"))
        self.assertEqual(
            core_releaselib.version_greater("2.4.0", "2.3.4"),
            core_releaselib.semver_greater("2.4.0", "2.3.4"))


class NumericSequenceCLITest(unittest.TestCase):
    """AC-01/02/04/10: scheme-aware helpers are available to release prose."""

    def _run(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, *args], input=stdin,
            capture_output=True, text=True, cwd=REPO_ROOT)

    def test_scheme_aware_cli_selects_compares_and_derives_numeric_versions(self):
        selected = self._run(
            "last-tag-for-policy", "preview-", "numeric-sequence", "0.1",
            stdin="preview-0.30\npreview-0.31\npreview-0.032\n")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout, "preview-0.31\n")

        compared = self._run(
            "version-greater", "0.32", "0.31", "numeric-sequence", "0.1")
        self.assertEqual(compared.returncode, 0, compared.stderr)

        derived = self._run(
            "derive-version", "0.31", "minor", "numeric-sequence", "0.1")
        self.assertEqual(derived.returncode, 0, derived.stderr)
        self.assertEqual(derived.stdout, "0.32\n")

        first = self._run(
            "version-greater", "0.30", core_releaselib.NONE_SENTINEL,
            "numeric-sequence", "0.30")
        self.assertEqual(first.returncode, 0, first.stderr)

    def test_scheme_aware_cli_refuses_bad_policy_state(self):
        cases = (
            ("version-greater", "0.32.0", "0.31", "numeric-sequence", "0.1"),
            ("derive-version", "0.31", "none", "numeric-sequence", "0.1"),
            ("derive-version", "0.31", "patch", "calendar", "0.1"),
        )
        for args in cases:
            with self.subTest(args=args):
                proc = self._run(*args)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_version_greater_cli_distinguishes_comparison_from_invalid_policy_state(self):
        for candidate, floor in (("0.31", "0.31"), ("0.30", "0.31")):
            with self.subTest(candidate=candidate, floor=floor):
                proc = self._run(
                    "version-greater", candidate, floor,
                    "numeric-sequence", "0.30")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        for candidate, floor in (("0.29", "0.28"), ("0.31.0", "0.30")):
            with self.subTest(candidate=candidate, floor=floor):
                proc = self._run(
                    "version-greater", candidate, floor,
                    "numeric-sequence", "0.30")
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_scheme_aware_cli_default_semver_matches_existing_commands(self):
        tags = "v1.9.9\nv2.0.0\nv2.0.1-rc.1\n"
        selected = self._run(
            "last-tag-for-policy", "v", "semver", "", stdin=tags)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout, "v2.0.0\n")
        compared = self._run(
            "version-greater", "2.4.0", "2.3.4", "semver", "")
        self.assertEqual(compared.returncode, 0, compared.stderr)
        derived = self._run(
            "derive-version", "2.3.4", "minor", "semver", "")
        self.assertEqual(derived.returncode, 0, derived.stderr)
        self.assertEqual(derived.stdout, "2.4.0\n")

    def test_show_row_includes_policy_fields_in_the_full_report(self):
        declaration = (
            "<!-- release-targets -->\n[preview]\n"
            "prefix: preview-\nchangelog: CHANGELOG.md\npayload: .\n"
            "version-policy: numeric-sequence\ninitial-version: 0.30\n"
            "<!-- /release-targets -->\n")
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".codearbiter"))
            with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                      "w", encoding="utf-8", newline="\n") as handle:
                handle.write(declaration)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
            policy = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "show-row", "preview",
                 "--field", "version-policy"],
                capture_output=True, text=True, env=env)
            initial = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "show-row", "preview",
                 "--field", "initial-version"],
                capture_output=True, text=True, env=env)
            legacy = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "show-row", "preview"],
                capture_output=True, text=True, env=env)
        self.assertEqual(policy.returncode, 0, policy.stderr)
        self.assertEqual(policy.stdout, "numeric-sequence\n")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertEqual(initial.stdout, "0.30\n")
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertIn("VERSION_POLICY=numeric-sequence", legacy.stdout)
        self.assertIn("INITIAL_VERSION=0.30", legacy.stdout)


class DeclaredVersionChangelogTest(unittest.TestCase):
    """AC-12: changelog and notes helpers honor the declared version shape."""

    _CHANGELOG = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n- pending\n\n"
        "## [0.31] - 2026-09-13\n\n### Added\n\n- preview feature\n\n"
        "## [0.30] - 2026-09-01\n\n### Fixed\n\n- older fix\n")

    def test_numeric_sequence_extracts_and_validates_matching_notes(self):
        section = core_releaselib.changelog_section(
            self._CHANGELOG, "0.31", "numeric-sequence", "0.1")
        self.assertEqual(
            section,
            "## [0.31] - 2026-09-13\n\n### Added\n\n- preview feature\n")
        self.assertTrue(core_releaselib.notes_heading_matches(
            section, "preview-0.31", "numeric-sequence", "0.1"))
        self.assertFalse(core_releaselib.notes_heading_matches(
            section, "preview-0.30", "numeric-sequence", "0.1"))

    def test_numeric_sequence_rejects_wrong_shape_and_noncanonical_headings(self):
        malformed = (
            "## [0.031] - 2026-09-13\n\n- leading zero\n",
            "## [0.31.0] - 2026-09-13\n\n- wrong shape\n",
            "## [٠.٣١] - 2026-09-13\n\n- non-ASCII digits\n",
        )
        for text in malformed:
            with self.subTest(text=text):
                section, status = core_releaselib._changelog_section_result(
                    text, "0.31", "numeric-sequence", "0.1")
                self.assertIsNone(section)
                self.assertEqual(status, core_releaselib._SECTION_INVALID)

    def test_default_semver_contract_remains_strict(self):
        numeric = "## [0.31] - 2026-09-13\n\n- preview feature\n"
        self.assertIsNone(core_releaselib.changelog_section(numeric, "0.31"))
        self.assertFalse(
            core_releaselib.notes_heading_matches(numeric, "preview-0.31"))
        semver = "## [1.2.3] - 2026-09-13\n\n- stable feature\n"
        self.assertEqual(
            core_releaselib.changelog_section(
                semver, "1.2.3", "semver", None),
            semver)
        self.assertTrue(core_releaselib.notes_heading_matches(
            semver, "v1.2.3", "semver", None))

    def test_scheme_aware_cli_accepts_numeric_sequence_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = os.path.join(tmp, "notes.md")
            with open(notes_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "## [0.31] - 2026-09-13\n\n- preview feature\n")
            self.assertEqual(core_releaselib.main([
                "notes-match", "preview-0.31", notes_path,
                "numeric-sequence", "0.1",
            ]), 0)

        out = io.StringIO()
        with mock.patch.object(
                core_releaselib, "_committed_changelog_text",
                return_value=(self._CHANGELOG, None)), \
                mock.patch("sys.stdout", out):
            rc = core_releaselib.main([
                "changelog-section", "repo", "preview-0.31", "CHANGELOG.md",
                "0.31", "numeric-sequence", "0.1",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(
            out.getvalue(),
            "## [0.31] - 2026-09-13\n\n### Added\n\n- preview feature\n")

    def test_numeric_notes_reject_a_suffix_of_a_wrong_shape_dotted_tag(self):
        cases = (
            ("## [31.0] - 2026-09-13\n\n- wrong shape\n",
             "preview-0.31.0"),
            ("## [0.31] - 2026-09-13\n\n- wrong shape\n",
             "preview-9.0.31"),
        )
        for notes, tag in cases:
            with self.subTest(tag=tag):
                self.assertFalse(core_releaselib.notes_heading_matches(
                    notes, tag, "numeric-sequence", "0.1"))

    def test_numeric_release_dates_round_trip_through_function_and_cli(self):
        section = "## [0.31] - 2026-09-13\n\n- preview feature\n"
        matching = "Preview 0.31\n\nReleased-at: 2026-09-13\n"
        stale = "Preview 0.31\n\nReleased-at: 2026-09-12\n"
        self.assertTrue(core_releaselib.release_dates_consistent(
            section, matching, "numeric-sequence", "0.1"))
        self.assertFalse(core_releaselib.release_dates_consistent(
            section, stale, "numeric-sequence", "0.1"))
        self.assertFalse(core_releaselib.release_dates_consistent(
            section, matching))

        with tempfile.TemporaryDirectory() as tmp:
            section_path = os.path.join(tmp, "section.md")
            message_path = os.path.join(tmp, "message.txt")
            with open(section_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(section)
            with open(message_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(matching)
            self.assertEqual(core_releaselib.main([
                "dates-match", section_path, message_path,
                "numeric-sequence", "0.1",
            ]), 0)

    def test_numeric_changelog_cli_distinguishes_absent_invalid_and_duplicate(self):
        invalid_err = io.StringIO()
        with contextlib.redirect_stderr(invalid_err):
            invalid_rc = core_releaselib.main([
                "changelog-section", "repo", "preview-0.31", "CHANGELOG.md",
                "0.31", "calendar", "0.1",
            ])
        self.assertEqual(invalid_rc, 2)
        self.assertEqual(
            invalid_err.getvalue(),
            "changelog-section: invalid policy declaration\n")

        cases = (
            ("## [0.30] - 2026-09-01\n\n- older\n", 1),
            ("## [0.31] - 2026-09-13\n\n- target\n\n"
             "## [0.031] - 2026-09-01\n\n- malformed later\n", 4),
            ("## [0.31] - 2026-09-13\n\n- first\n\n"
             "## v0.31 - 2026-09-13\n\n- duplicate\n", 4),
        )
        for changelog, expected in cases:
            with self.subTest(expected=expected, changelog=changelog):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(
                        core_releaselib, "_committed_changelog_text",
                        return_value=(changelog, None)), \
                        contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    rc = core_releaselib.main([
                        "changelog-section", "repo", "preview-0.31",
                        "CHANGELOG.md", "0.31", "numeric-sequence", "0.1",
                    ])
                self.assertEqual(rc, expected, out.getvalue() + err.getvalue())
                self.assertEqual(out.getvalue(), "")

    def test_legacy_and_explicit_semver_arities_are_equivalent(self):
        section = "## [1.2.3] - 2026-09-13\n\n- stable feature\n"
        message = "Stable 1.2.3\n\nReleased-at: 2026-09-13\n"
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = os.path.join(tmp, "notes.md")
            message_path = os.path.join(tmp, "message.txt")
            with open(notes_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(section)
            with open(message_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(message)
            self.assertEqual(
                core_releaselib.main(["notes-match", "v1.2.3", notes_path]),
                core_releaselib.main([
                    "notes-match", "v1.2.3", notes_path, "semver", ""]))
            self.assertEqual(
                core_releaselib.main(["dates-match", notes_path, message_path]),
                core_releaselib.main([
                    "dates-match", notes_path, message_path, "semver", ""]))

        def run_changelog(extra):
            out = io.StringIO()
            with mock.patch.object(
                    core_releaselib, "_committed_changelog_text",
                    return_value=(section, None)), \
                    contextlib.redirect_stdout(out):
                rc = core_releaselib.main([
                    "changelog-section", "repo", "v1.2.3", "CHANGELOG.md",
                    "1.2.3", *extra,
                ])
            return rc, out.getvalue()

        self.assertEqual(run_changelog([]), run_changelog(["semver", ""]))


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


class CorePrereleaseMarkersRemovedTest(unittest.TestCase):
    """Issue #568: `_PRERELEASE_MARKERS` and its second `last_tag_select`
    check were confirmed unreachable through the public API — the anchored
    `_release_re`'s trailing `$` already rejects any tag carrying a suffix
    past `MAJOR.MINOR.PATCH`, so no tag could ever both match the regex and
    carry a marker in its stripped version portion (proven by the deleted
    `CorePrereleaseMarkersSecondLineOfDefenseTest`, which monkeypatched an
    UNANCHORED matcher to reach it at all — the only way to exercise code
    that has no live caller). Deleted rather than kept as unreachable dead
    code or made load-bearing by relaxing the anchor (that option changes
    behavior — it would newly admit `v1.0.0+build.5`/`v1.0.0.1`-shaped tags
    the anchor currently rejects wholesale — and needs its own deliberate
    analysis, out of scope for this bug-fix cluster).

    `CorePrereleaseMarkerScopeTest` above already proves the property that
    matters (a prefix containing "beta"/"rc"/"alpha" still resolves its own
    releases) continues to hold with the anchor alone. This test instead
    pins that the dead code is actually GONE, so a future edit cannot
    silently reintroduce it — a mutant re-adding
    `_PRERELEASE_MARKERS = ("-beta", "-rc", "-alpha")` anywhere in the
    module fails this test."""

    def test_the_dead_marker_tuple_no_longer_exists(self):
        self.assertFalse(
            hasattr(core_releaselib, "_PRERELEASE_MARKERS"),
            "_PRERELEASE_MARKERS was deleted as unreachable dead code "
            "(issue #568) and must not reappear")


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

    def test_heading_version_token_must_match_exactly(self):
        malformed = (
            "## [1.2.3-rc.1] - 2026-09-01\n",
            "## [1.2.3+build.7] - 2026-09-01\n",
            "## [1.2.3.4] - 2026-09-01\n",
            "## [1.2.3 - 2026-09-01\n",
            "## [1.2.3]garbage\n",
            "## 1.2.3 - 2026-09-01\n",
            "##\n[1.2.3] - 2026-09-01\n",
        )
        for notes in malformed:
            with self.subTest(notes=notes):
                self.assertFalse(
                    core_releaselib.notes_heading_matches(notes, "v1.2.3"))

    def test_first_h2_unreleased_is_rejected_not_skipped(self):
        notes = (
            "## [Unreleased]\n\n- pending\n\n"
            "## [1.2.3] - 2026-09-01\n\n- released\n")
        self.assertFalse(
            core_releaselib.notes_heading_matches(notes, "v1.2.3"))

    def test_duplicate_matching_sections_are_rejected(self):
        notes = (
            "## [1.2.3] - 2026-09-01\n\n- first\n\n"
            "## [1.2.3] - 2026-09-01\n\n- second\n")
        self.assertFalse(
            core_releaselib.notes_heading_matches(notes, "v1.2.3"))


class CoreChangelogSectionTest(unittest.TestCase):
    """Blind exercise run 19, HIGH-2: `changelog_section` mechanically
    reconstructs a Phase-1-composed section from a COMMITTED changelog, so
    `resume_publish` never needs a `mktemp` scratch file that may not have
    survived to a later session."""

    _CHANGELOG = (
        "# Changelog\n"
        "\n"
        "## [2.12.0] — 2026-08-07\n"
        "\n"
        "### Added\n"
        "\n"
        "- newest thing\n"
        "\n"
        "## [2.11.0] — 2026-07-31\n"
        "\n"
        "### Fixed\n"
        "\n"
        "- middle thing\n"
        "\n"
        "## [2.8.13] — 2026-07-12\n"
        "\n"
        "### Fixed\n"
        "\n"
        "- oldest thing\n"
    )

    def test_extracts_middle_section_verbatim_up_to_next_heading(self):
        section = core_releaselib.changelog_section(self._CHANGELOG, "2.11.0")
        self.assertEqual(
            section,
            "## [2.11.0] — 2026-07-31\n\n### Fixed\n\n- middle thing\n")

    def test_extracts_first_section_up_to_next_heading(self):
        section = core_releaselib.changelog_section(self._CHANGELOG, "2.12.0")
        self.assertEqual(
            section,
            "## [2.12.0] — 2026-08-07\n\n### Added\n\n- newest thing\n")

    def test_extracts_last_section_to_end_of_text(self):
        # No following `##` heading -- the boundary is end-of-string, not an
        # index error and not a section that swallows a prior one.
        section = core_releaselib.changelog_section(self._CHANGELOG, "2.8.13")
        self.assertEqual(
            section,
            "## [2.8.13] — 2026-07-12\n\n### Fixed\n\n- oldest thing\n")

    def test_bare_v_prefixed_heading_also_matches(self):
        section = core_releaselib.changelog_section(
            "## v0.1.5 - 2026-07-24\n\n### Fixed\n- x\n", "0.1.5")
        self.assertEqual(section, "## v0.1.5 - 2026-07-24\n\n### Fixed\n- x\n")

    def test_unknown_version_returns_none(self):
        self.assertIsNone(core_releaselib.changelog_section(self._CHANGELOG, "9.9.9"))

    def test_never_raises_on_non_string_changelog(self):
        self.assertIsNone(core_releaselib.changelog_section(None, "2.12.0"))

    def test_never_raises_on_non_string_version(self):
        self.assertIsNone(core_releaselib.changelog_section(self._CHANGELOG, None))

    def test_h3_heading_never_matched_as_a_section_boundary(self):
        # `### Added` must not be mistaken for a `## [...]` version heading --
        # a regex anchored on a bare `##` prefix without excluding a third `#`
        # would swallow the WRONG boundary and either truncate the section
        # early or merge two versions together.
        text = "## [1.0.0] — 2026-01-01\n\n### Added\n\n- a\n\n## [0.9.0] — 2025-12-01\n\n- b\n"
        section = core_releaselib.changelog_section(text, "1.0.0")
        self.assertIn("### Added", section)
        self.assertNotIn("0.9.0", section)

    def test_conventional_unreleased_before_releases_is_allowed_and_excluded(self):
        text = (
            "# Changelog\n\n## [Unreleased]\n\n- pending\n\n"
            "## [1.2.3] - 2026-09-01\n\n- released\n\n"
            "## [1.2.2] - 2026-08-01\n\n- older\n")
        self.assertEqual(
            core_releaselib.changelog_section(text, "1.2.3"),
            "## [1.2.3] - 2026-09-01\n\n- released\n")

    def test_unreleased_cannot_be_requested_as_a_release_version(self):
        text = "## [Unreleased]\n\n- pending\n"
        self.assertIsNone(
            core_releaselib.changelog_section(text, "Unreleased"))

    def test_unreleased_after_a_released_section_is_rejected(self):
        text = (
            "## [1.2.3] - 2026-09-01\n\n- released\n\n"
            "## [Unreleased]\n\n- pending\n")
        self.assertIsNone(
            core_releaselib.changelog_section(text, "1.2.3"))

    def test_duplicate_unreleased_sections_before_releases_are_rejected(self):
        text = (
            "## [Unreleased]\n\n- first pending batch\n\n"
            "## [Unreleased]\n\n- second pending batch\n\n"
            "## [1.2.3] - 2026-09-01\n\n- released\n")
        self.assertIsNone(
            core_releaselib.changelog_section(text, "1.2.3"))

    def test_duplicate_matching_sections_are_rejected_even_when_identical(self):
        section = "## [1.2.3] - 2026-09-01\n\n- released\n"
        self.assertIsNone(
            core_releaselib.changelog_section(section + "\n" + section, "1.2.3"))

    def test_duplicate_matching_sections_are_rejected_when_divergent(self):
        text = (
            "## [1.2.3] - 2026-09-01\n\n- first\n\n"
            "## v1.2.3 - 2026-09-01\n\n- second\n")
        self.assertIsNone(
            core_releaselib.changelog_section(text, "1.2.3"))

    def test_any_h2_terminates_the_selected_section(self):
        text = (
            "## [1.2.3] - 2026-09-01\n\n- released\n\n"
            "## Archive\n\n- not release notes\n")
        self.assertEqual(
            core_releaselib.changelog_section(text, "1.2.3"),
            "## [1.2.3] - 2026-09-01\n\n- released\n")

    def test_legacy_date_h2_is_a_boundary_not_a_malformed_release_heading(self):
        text = (
            "## [1.2.3] - 2026-09-01\n\n- released\n\n"
            "## [2026-05-13] — legacy release notes\n\n- historical\n\n"
            "## [2026-05-13] — more legacy notes\n\n- also historical\n")
        section, status = core_releaselib._changelog_section_result(
            text, "1.2.3")
        self.assertEqual(status, core_releaselib._SECTION_OK)
        self.assertEqual(
            section,
            "## [1.2.3] - 2026-09-01\n\n- released\n")

    def test_malformed_target_headings_are_never_prefix_matches(self):
        malformed = (
            "## [1.2.3-rc.1] - 2026-09-01\n",
            "## [1.2.3+build] - 2026-09-01\n",
            "## [1.2.3.4] - 2026-09-01\n",
            "## [01.2.3] - 2026-09-01\n",
            "## [1.02.3] - 2026-09-01\n",
            "## [1.2.03] - 2026-09-01\n",
            "## [١.٢.٣] - 2026-09-01\n",
            "## v01.2.3 - 2026-09-01\n",
            "## v١.٢.٣ - 2026-09-01\n",
            "## [1.2.3 - 2026-09-01\n",
            "## [1.2.3]garbage\n",
        )
        for heading in malformed:
            with self.subTest(heading=heading):
                text = (
                    heading + "\n- not a valid section\n\n"
                    "## [1.2.3] - 2026-09-01\n\n- canonical target\n")
                section, status = core_releaselib._changelog_section_result(
                    text, "1.2.3")
                self.assertIsNone(section)
                self.assertEqual(status, core_releaselib._SECTION_INVALID)

        non_changelog_h2s = (
            "## 1.2.3 - 2026-09-01\n",
            "##\n[1.2.3] - 2026-09-01\n",
        )
        for heading in non_changelog_h2s:
            with self.subTest(non_changelog_h2=heading):
                self.assertIsNone(core_releaselib.changelog_section(
                    heading + "\n- not a valid section\n", "1.2.3"))

    def test_heading_versions_require_canonical_ascii_semver(self):
        invalid_versions = (
            "01.2.3", "1.02.3", "1.2.03", "١.٢.٣", "1.٢.3")
        for version in invalid_versions:
            with self.subTest(version=version):
                text = f"## [{version}] - 2026-09-01\n\n- invalid version\n"
                section, status = core_releaselib._changelog_section_result(
                    text, "1.2.3")
                self.assertIsNone(section)
                self.assertEqual(status, core_releaselib._SECTION_INVALID)

    def test_requested_versions_independently_require_canonical_ascii_semver(self):
        canonical_text = "## [2.12.0] - 2026-09-01\n\n- released\n"
        invalid_versions = (
            "02.12.0", "2.012.0", "2.12.00", "٢.١٢.٠", "2.١٢.0")
        for version in invalid_versions:
            with self.subTest(version=version):
                section, status = core_releaselib._changelog_section_result(
                    canonical_text, version)
                self.assertIsNone(section)
                self.assertEqual(status, core_releaselib._SECTION_INVALID)


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

    def test_released_at_must_be_one_unique_terminal_footer(self):
        section = "## v2.6.0 — 2026-06-26\n"
        self.assertFalse(core_releaselib.release_dates_consistent(
            section, "Released-at: 2026-06-26\n\nordinary prose\n"))
        self.assertFalse(core_releaselib.release_dates_consistent(
            section,
            "Released-at: 2026-06-26\n\nReleased-at: 2026-06-26\n"))
        self.assertTrue(core_releaselib.release_dates_consistent(
            section, "release notes\n\nReleased-at: 2026-06-26   \n"))

    def test_date_in_body_does_not_satisfy_a_dated_heading(self):
        section = "## [1.2.3]\n\nReleased on 2026-09-01.\n"
        tagmsg = "Released-at: 2026-09-01\n"
        self.assertFalse(
            core_releaselib.release_dates_consistent(section, tagmsg))

    def test_malformed_heading_suffix_does_not_supply_a_release_date(self):
        section = "## [1.2.3]garbage 2026-09-01\n\n- malformed\n"
        tagmsg = "Released-at: 2026-09-01\n"
        self.assertFalse(
            core_releaselib.release_dates_consistent(section, tagmsg))

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

    def test_semver_key_rejects_noncanonical_numeric_identifiers(self):
        invalid_versions = (
            "01.2.3", "1.02.3", "1.2.03", "١.٢.٣", "1.٢.3",
            "1.2.3-00", "1.2.3-01", "1.2.3-٠", "1.2.3-1٢")
        for version in invalid_versions:
            with self.subTest(version=version):
                self.assertIsNone(core_releaselib.semver_key(version))

    def test_semver_build_numeric_identifiers_may_have_leading_zeroes(self):
        self.assertEqual(
            core_releaselib.semver_key("1.2.3+01"),
            core_releaselib.semver_key("1.2.3"))

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

    def _run_core(self, *argv):
        """`main(argv)` with BOTH streams captured, as a SimpleNamespace with
        `.returncode` / `.stdout` / `.stderr`.

        This class otherwise calls `main` bare and asserts only the code;
        `show-row` and `payload-pathspec` answer on STDOUT and diagnose on
        STDERR, so both have to be readable to test them at all.
        """
        import contextlib
        from types import SimpleNamespace
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = core_releaselib.main(list(argv))
        return SimpleNamespace(returncode=rc, stdout=out.getvalue(),
                               stderr=err.getvalue())

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

    def test_classify_rejects_malformed_boolean_evidence(self):
        import io, contextlib
        for tag_exists, release_nondraft in (("maybe", "false"),
                                             ("false", "definitely")):
            with self.subTest(tag_exists=tag_exists,
                              release_nondraft=release_nondraft):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = core_releaselib.main([
                        "classify", tag_exists, "a", "a", "1.2.3", "1.2.3",
                        release_nondraft])
                self.assertEqual(rc, 2)
                self.assertIn("true or false", err.getvalue())

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

    def test_dates_match_rejects_impossible_calendar_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for invalid in ("2026-99-99", "2026-02-29", "2025-04-31"):
                with self.subTest(invalid=invalid):
                    section, message = self._dates_files(tmp, invalid, invalid)
                    self.assertEqual(
                        core_releaselib.main(["dates-match", section, message]), 1)

    def test_dates_match_exits_1_on_an_unreadable_file_never_a_traceback(self):
        # Same contract as notes-match: an unreadable file is empty text,
        # which has no date, so the comparison is False and the exit is 1.
        # A traceback here would break a `set -e` lane with no diagnosis.
        with tempfile.TemporaryDirectory() as tmp:
            _section, message = self._dates_files(tmp, "2026-07-31", "2026-07-31")
            missing = os.path.join(tmp, "does-not-exist.md")
            self.assertEqual(core_releaselib.main(["dates-match", missing, message]), 1)

    def test_notes_and_dates_match_reject_non_utf8_without_tracebacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.md")
            good = os.path.join(tmp, "good.md")
            with open(bad, "wb") as handle:
                handle.write(b"## [1.0.0] - 2026-09-24\n\xff")
            with open(good, "w", encoding="utf-8") as handle:
                handle.write("## [1.0.0] - 2026-09-24\n\nReleased-at: 2026-09-24\n")
            for argv in (("notes-match", "v1.0.0", bad),
                         ("dates-match", bad, good),
                         ("dates-match", good, bad)):
                with self.subTest(argv=argv):
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = core_releaselib.main(list(argv))
                    self.assertEqual(rc, 4, err.getvalue())
                    self.assertIn("not UTF-8", err.getvalue())
                    self.assertNotIn("Traceback", err.getvalue())

    # `changelog-section` (blind exercise run 19, HIGH-2). `resume_publish`
    # needs the exact text Phase 1 composed, and Phase 1's own scratch copy
    # is explicitly discardable -- this is the mechanical way to read it
    # back out of the COMMITTED changelog instead.
    def _git(self, repo, *args, input_bytes=None):
        environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
        )
        return subprocess.run(
            [core_releaselib.git_executable(),
             "-c", "commit.gpgsign=false",
             "-c", "tag.gpgSign=false",
             "-c", "core.hooksPath=", *args],
            cwd=repo, env=environment, input=input_bytes,
            capture_output=True, timeout=30, check=True)

    def _init_changelog_repo(self, root, text=None,
                             changelog_path="docs/CHANGELOG.md",
                             object_format=None):
        os.makedirs(root, exist_ok=True)
        init_args = ["init", "--quiet"]
        if object_format is not None:
            init_args.append(f"--object-format={object_format}")
        self._git(root, *init_args)
        hooks = os.path.join(root, "empty-hooks")
        os.makedirs(hooks, exist_ok=True)
        self._git(root, "config", "core.hooksPath", hooks)
        self._git(root, "config", "core.autocrlf", "false")
        self._git(root, "config", "user.name", "RA-05 fixture")
        self._git(root, "config", "user.email", "ra05@example.invalid")
        if text is None:
            text = self._SAMPLE_CHANGELOG
        disk_path = os.path.join(root, *changelog_path.split("/"))
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        with open(disk_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        self._git(root, "add", "--", changelog_path)
        self._git(root, "commit", "--quiet", "-m", "fixture: release notes")
        self._git(
            root, "tag", "-a", "release-v2.12.0", "-m", "fixture release")
        return disk_path

    _SAMPLE_CHANGELOG = (
        "# Changelog\n\n"
        "## [2.12.0] — 2026-08-07\n\n### Added\n\n- newest thing\n\n"
        "## [2.11.0] — 2026-07-31\n\n### Fixed\n\n- middle thing\n"
    )

    def test_changelog_fixture_ignores_global_signing_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            global_config = os.path.join(tmp, "global.gitconfig")
            with open(global_config, "w", encoding="utf-8") as fh:
                fh.write("[commit]\n\tgpgsign = true\n[tag]\n\tgpgSign = true\n")
            injected = {
                "GIT_CONFIG_GLOBAL": global_config,
                "GIT_CONFIG_SYSTEM": os.path.join(tmp, "missing-system-config"),
            }
            try:
                with mock.patch.dict(os.environ, injected):
                    self._init_changelog_repo(os.path.join(tmp, "repo"))
            except subprocess.CalledProcessError as exc:
                self.fail(
                    "changelog fixture inherited signing configuration: "
                    + exc.stderr.decode(errors="replace"))

    def test_changelog_section_exits_0_and_prints_the_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                result.stdout,
                "## [2.12.0] — 2026-08-07\n\n### Added\n\n- newest thing\n")

    def test_changelog_section_accepts_exact_candidate_commit_before_tag_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            self._git(tmp, "tag", "-d", "release-v2.12.0")
            candidate = self._git(tmp, "rev-parse", "HEAD").stdout.decode().strip()
            result = self._run_core(
                "changelog-section", tmp, candidate,
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("## [2.12.0]", result.stdout)

    def test_changelog_section_requires_a_full_sha256_candidate_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._init_changelog_repo(tmp, object_format="sha256")
            except subprocess.CalledProcessError as exc:
                self.skipTest(
                    "installed Git lacks SHA-256 repository support: "
                    + exc.stderr.decode(errors="replace"))
            self._git(tmp, "tag", "-d", "release-v2.12.0")
            candidate = self._git(
                tmp, "rev-parse", "HEAD").stdout.decode().strip()
            self.assertEqual(len(candidate), 64)

            accepted = self._run_core(
                "changelog-section", tmp, candidate,
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            abbreviated = self._run_core(
                "changelog-section", tmp, candidate[:40],
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(abbreviated.returncode, 3)
            self.assertIn("exact full commit id", abbreviated.stderr)

    def test_changelog_section_rejects_mutable_non_tag_revision_expression(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "HEAD",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertNotEqual(result.returncode, 0)

    def test_changelog_section_rejects_raw_tag_object_as_candidate_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            tag_object = self._git(
                tmp, "rev-parse", "release-v2.12.0^{tag}").stdout.decode().strip()
            result = self._run_core(
                "changelog-section", tmp, tag_object,
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 3)
            self.assertIn("exact full commit id", result.stderr)

    def test_changelog_section_accepts_committed_legacy_date_h2_boundaries(self):
        text = (
            "## [2.12.0] - 2026-09-01\n\n- released\n\n"
            "## [2026-05-13] — legacy release notes\n\n- historical\n\n"
            "## [2026-05-13] — more legacy notes\n\n- also historical\n")
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp, text)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "## [2.12.0] - 2026-09-01\n\n- released\n")

    def test_changelog_section_middle_version_stops_at_next_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.11.0")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                result.stdout,
                "## [2.11.0] — 2026-07-31\n\n### Fixed\n\n- middle thing\n")

    def test_changelog_section_unknown_version_exits_1_not_0(self):
        # exit 1 = "compared and found nothing", distinct from exit 3
        # ("could not compare at all") -- never folded together.
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "9.9.9")
            self.assertEqual(result.returncode, 1)
            self.assertIn("9.9.9", result.stderr)

    def test_changelog_section_unreadable_file_exits_3_not_1(self):
        # An unreadable changelog is NOT the same answer as "no such
        # version" -- [never-fold-unreadable-into-absent].
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "does-not-exist.md", "2.12.0")
            self.assertEqual(result.returncode, 3)

    def test_changelog_section_parent_probe_may_allow_absent_path_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "does-not-exist.md", "2.12.0", "semver", "",
                "--allow-absent-path")
            self.assertEqual(result.returncode, 1, result.stderr)
            invalid = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "does-not-exist.md", "2.12.0", "semver", "",
                "--weaken-everything")
            self.assertEqual(invalid.returncode, 2)

    def test_changelog_section_bad_invocation_exits_2(self):
        result = self._run_core(
            "changelog-section", "root", "revision", "path-only")
        self.assertEqual(result.returncode, 2)

    def test_release_skill_binds_section_to_project_root_tag_and_quoted_path(self):
        skill_path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(skill_path, encoding="utf-8") as fh:
            skill = fh.read()
        self.assertIn(
            'changelog-section "$PROJECT_ROOT" "$RELEASE_TAG" '
            '"$CHANGELOG" "$VERSION"', skill)

    def test_changelog_section_malformed_or_ambiguous_exits_4(self):
        cases = (
            ("## [2.12.0-rc.1] - 2026-09-01\n\n- malformed\n",
             "2.12.0"),
            ("## [02.12.0] - 2026-09-01\n\n- leading zero\n\n"
             "## [2.12.0] - 2026-09-01\n\n- canonical target\n",
             "2.12.0"),
            ("## [٢.١٢.٠] - 2026-09-01\n\n- non-ASCII digits\n\n"
             "## [2.12.0] - 2026-09-01\n\n- canonical target\n",
             "2.12.0"),
            ("## v02.12.0 - 2026-09-01\n\n- v leading zero\n\n"
             "## [2.12.0] - 2026-09-01\n\n- canonical target\n",
             "2.12.0"),
            ("## v٢.١٢.٠ - 2026-09-01\n\n- v non-ASCII digits\n\n"
             "## [2.12.0] - 2026-09-01\n\n- canonical target\n",
             "2.12.0"),
            ("## [2.12.0] - 2026-09-01\n\n- first\n\n"
             "## [2.12.0] - 2026-09-01\n\n- duplicate\n", "2.12.0"),
            ("## [2.12.0] - 2026-09-01\n\n- released\n\n"
             "## [Unreleased]\n\n- misplaced\n", "2.12.0"),
            ("## [Unreleased]\n\n- first pending batch\n\n"
             "## [Unreleased]\n\n- second pending batch\n\n"
             "## [2.12.0] - 2026-09-01\n\n- released\n", "2.12.0"),
            ("## [Unreleased]\n\n- pending\n", "Unreleased"),
        )
        for text, version in cases:
            with self.subTest(version=version, text=text):
                with tempfile.TemporaryDirectory() as tmp:
                    self._init_changelog_repo(tmp, text)
                    result = self._run_core(
                        "changelog-section", tmp, "release-v2.12.0",
                        "docs/CHANGELOG.md", version)
                self.assertEqual(result.returncode, 4, result.stderr)
                self.assertIn("refusing ambiguous release notes", result.stderr)

    def test_changelog_section_noncanonical_requested_version_exits_4(self):
        invalid_versions = (
            "02.12.0", "2.012.0", "2.12.00", "٢.١٢.٠", "2.١٢.0")
        for version in invalid_versions:
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as tmp:
                    self._init_changelog_repo(tmp)
                    result = self._run_core(
                        "changelog-section", tmp, "release-v2.12.0",
                        "docs/CHANGELOG.md", version)
                self.assertEqual(result.returncode, 4, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("refusing ambiguous release notes", result.stderr)

    def test_changelog_section_reads_tag_commit_not_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk_path = self._init_changelog_repo(tmp)
            with open(disk_path, "w", encoding="utf-8", newline="") as fh:
                fh.write("## [2.12.0] - 2026-09-01\n\n- counterfeit\n")
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("counterfeit", result.stdout)

    def test_changelog_section_reads_tag_commit_when_worktree_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk_path = self._init_changelog_repo(tmp)
            os.remove(disk_path)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)

    def test_changelog_section_reads_tag_commit_after_head_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk_path = self._init_changelog_repo(tmp)
            with open(disk_path, "w", encoding="utf-8", newline="") as fh:
                fh.write("## [2.12.0] - 2026-09-02\n\n- later head\n")
            self._git(tmp, "add", "--", "docs/CHANGELOG.md")
            self._git(tmp, "commit", "--quiet", "-m", "fixture: advance head")
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("later head", result.stdout)

    def test_changelog_section_requires_an_exact_tag_not_a_same_named_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            self._git(tmp, "tag", "-d", "release-v2.12.0")
            self._git(tmp, "branch", "release-v2.12.0")
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 3)

    def test_changelog_section_tag_branch_collision_selects_the_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk_path = self._init_changelog_repo(tmp)
            with open(disk_path, "w", encoding="utf-8", newline="") as fh:
                fh.write("## [2.12.0] - 2026-09-02\n\n- branch content\n")
            self._git(tmp, "add", "--", "docs/CHANGELOG.md")
            self._git(tmp, "commit", "--quiet", "-m", "fixture: branch content")
            self._git(tmp, "branch", "release-v2.12.0")
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("branch content", result.stdout)

    def test_changelog_section_refuses_mutable_non_tag_revision_spellings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            for revision in ("HEAD", "release-v2.12.0~0"):
                with self.subTest(revision=revision):
                    result = self._run_core(
                        "changelog-section", tmp, revision,
                        "docs/CHANGELOG.md", "2.12.0")
                    self.assertEqual(result.returncode, 3)

    def test_changelog_section_is_bound_to_explicit_root_not_cwd(self):
        with tempfile.TemporaryDirectory() as intended, \
                tempfile.TemporaryDirectory() as counterfeit:
            self._init_changelog_repo(intended)
            self._init_changelog_repo(
                counterfeit,
                "## [2.12.0] - 2026-09-01\n\n- counterfeit cwd\n")
            old_cwd = os.getcwd()
            os.chdir(counterfeit)
            try:
                result = self._run_core(
                    "changelog-section", intended, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            finally:
                os.chdir(old_cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("counterfeit cwd", result.stdout)

    def test_changelog_section_ignores_ambient_repository_rebinding(self):
        with tempfile.TemporaryDirectory() as intended, \
                tempfile.TemporaryDirectory() as counterfeit:
            self._init_changelog_repo(intended)
            self._init_changelog_repo(
                counterfeit,
                "## [2.12.0] - 2026-09-01\n\n- ambient counterfeit\n")
            rebound = {
                "GIT_DIR": os.path.join(counterfeit, ".git"),
                "GIT_WORK_TREE": intended,
            }
            with mock.patch.dict(os.environ, rebound):
                result = self._run_core(
                    "changelog-section", intended, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("ambient counterfeit", result.stdout)

    def test_changelog_section_ignores_ambient_common_git_directory(self):
        with tempfile.TemporaryDirectory() as intended, \
                tempfile.TemporaryDirectory() as counterfeit:
            self._init_changelog_repo(intended)
            self._init_changelog_repo(
                counterfeit,
                "## [2.12.0] - 2026-09-01\n\n- common-dir counterfeit\n")
            with mock.patch.dict(
                    os.environ,
                    {"GIT_COMMON_DIR": os.path.join(counterfeit, ".git")}):
                result = self._run_core(
                    "changelog-section", intended, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("common-dir counterfeit", result.stdout)

    def test_changelog_section_ignores_ambient_object_directory(self):
        with tempfile.TemporaryDirectory() as intended, \
                tempfile.TemporaryDirectory() as counterfeit:
            self._init_changelog_repo(intended)
            self._init_changelog_repo(
                counterfeit,
                "## [2.12.0] - 2026-09-01\n\n- object-dir counterfeit\n")
            with mock.patch.dict(
                    os.environ,
                    {"GIT_OBJECT_DIRECTORY": os.path.join(
                        counterfeit, ".git", "objects")}):
                result = self._run_core(
                    "changelog-section", intended, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("object-dir counterfeit", result.stdout)

    def test_changelog_section_refuses_ambient_alternate_object_store(self):
        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as alternate:
            self._init_changelog_repo(tmp)
            oid = self._git(
                tmp, "rev-parse",
                "release-v2.12.0:docs/CHANGELOG.md").stdout.decode().strip()
            trusted_object = os.path.join(tmp, ".git", "objects", oid[:2], oid[2:])
            alternate_object = os.path.join(alternate, oid[:2], oid[2:])
            os.makedirs(os.path.dirname(alternate_object), exist_ok=True)
            shutil.copy2(trusted_object, alternate_object)
            os.chmod(trusted_object, 0o666)
            os.remove(trusted_object)
            with mock.patch.dict(
                    os.environ,
                    {"GIT_ALTERNATE_OBJECT_DIRECTORIES": alternate}):
                result = self._run_core(
                    "changelog-section", tmp, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_changelog_section_ignores_command_scoped_git_config_injection(self):
        with tempfile.TemporaryDirectory() as intended, \
                tempfile.TemporaryDirectory() as counterfeit:
            self._init_changelog_repo(intended)
            self._init_changelog_repo(
                counterfeit,
                "## [2.12.0] - 2026-09-01\n\n- config counterfeit\n")
            injected = {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.worktree",
                "GIT_CONFIG_VALUE_0": counterfeit,
            }
            with mock.patch.dict(os.environ, injected):
                result = self._run_core(
                    "changelog-section", intended, "release-v2.12.0",
                    "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("config counterfeit", result.stdout)

    def test_git_environment_sanitizer_removes_all_config_injection_fields(self):
        injected = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": "counterfeit-worktree",
            "GIT_CONFIG_KEY_1": "include.path",
            "GIT_CONFIG_VALUE_1": "counterfeit-config",
        }
        with mock.patch.dict(os.environ, injected):
            sanitized = core_releaselib._sanitized_git_environment()
        self.assertEqual(set(injected).intersection(sanitized), set())

    def test_git_environment_sanitizer_removes_every_declared_repository_field(self):
        repository_fields = {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_DIR",
            "GIT_DISCOVERY_ACROSS_FILESYSTEM",
            "GIT_GRAFT_FILE",
            "GIT_INDEX_FILE",
            "GIT_NAMESPACE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_PREFIX",
            "GIT_QUARANTINE_PATH",
            "GIT_REPLACE_REF_BASE",
            "GIT_SHALLOW_FILE",
            "GIT_WORK_TREE",
        }
        self.assertEqual(core_releaselib._GIT_REPOSITORY_ENV, repository_fields)
        injected = {
            name: f"counterfeit-{index}"
            for index, name in enumerate(sorted(repository_fields))
        }
        with mock.patch.dict(os.environ, injected):
            sanitized = core_releaselib._sanitized_git_environment()
        for name in sorted(repository_fields):
            with self.subTest(name=name):
                self.assertNotIn(name, sanitized)

    def test_changelog_section_ignores_git_replace_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk_path = self._init_changelog_repo(tmp)
            tagged_commit = self._git(tmp, "rev-parse", "HEAD").stdout.strip()
            with open(disk_path, "w", encoding="utf-8", newline="") as fh:
                fh.write("## [2.12.0] - 2026-09-02\n\n- replacement counterfeit\n")
            self._git(tmp, "add", "--", "docs/CHANGELOG.md")
            self._git(tmp, "commit", "--quiet", "-m", "fixture: replacement")
            replacement_commit = self._git(tmp, "rev-parse", "HEAD").stdout.strip()
            self._git(tmp, "replace", tagged_commit, replacement_commit)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)
            self.assertNotIn("replacement counterfeit", result.stdout)

    def test_changelog_section_rejects_a_nested_directory_as_repository_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            nested = os.path.join(tmp, "docs")
            result = self._run_core(
                "changelog-section", nested, "release-v2.12.0",
                "CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 3)
            self.assertIn("repository root", result.stderr)

    def test_changelog_section_accepts_posix_and_windows_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            for path in ("docs/CHANGELOG.md", "docs\\CHANGELOG.md"):
                with self.subTest(path=path):
                    result = self._run_core(
                        "changelog-section", tmp, "release-v2.12.0",
                        path, "2.12.0")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("newest thing", result.stdout)

    def test_changelog_section_rejects_paths_outside_the_git_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            unsafe = (
                "../CHANGELOG.md", "/tmp/CHANGELOG.md",
                "C:\\outside\\CHANGELOG.md", "//server/share/CHANGELOG.md",
                "docs/../../CHANGELOG.md")
            for path in unsafe:
                with self.subTest(path=path):
                    result = self._run_core(
                        "changelog-section", tmp, "release-v2.12.0",
                        path, "2.12.0")
                    self.assertEqual(result.returncode, 3)

    def test_changelog_section_wrong_case_path_is_rejected_on_every_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "DOCS/changelog.md", "2.12.0")
            self.assertEqual(result.returncode, 3)

    def test_changelog_section_handles_spaces_and_unicode_in_root_and_path(self):
        with tempfile.TemporaryDirectory(prefix="ra05 café space ") as tmp:
            path = "release notes/CHANGELOG café.md"
            self._init_changelog_repo(tmp, changelog_path=path)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0", path, "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("newest thing", result.stdout)

    def test_changelog_section_rejects_a_committed_symlink_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            blob = self._git(
                tmp, "hash-object", "-w", "--stdin",
                input_bytes=b"docs/CHANGELOG.md").stdout.decode().strip()
            self._git(
                tmp, "update-index", "--add", "--cacheinfo",
                f"120000,{blob},linked-changelog.md")
            self._git(tmp, "commit", "--quiet", "-m", "fixture: symlink blob")
            self._git(
                tmp, "tag", "-a", "linked-v2.12.0", "-m", "fixture symlink")
            result = self._run_core(
                "changelog-section", tmp, "linked-v2.12.0",
                "linked-changelog.md", "2.12.0")
            self.assertEqual(result.returncode, 3)

    def test_changelog_section_rejects_a_committed_invalid_utf8_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            blob = self._git(
                tmp, "hash-object", "-w", "--stdin",
                input_bytes=(
                    b"## [2.12.0] - 2026-09-01\n\n- invalid byte: \xff\n"
                )).stdout.decode().strip()
            self._git(
                tmp, "update-index", "--add", "--cacheinfo",
                f"100644,{blob},docs/CHANGELOG.md")
            self._git(tmp, "commit", "--quiet", "-m", "fixture: invalid utf8")
            self._git(
                tmp, "tag", "-a", "invalid-v2.12.0", "-m", "fixture invalid")
            result = self._run_core(
                "changelog-section", tmp, "invalid-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("committed changelog is not UTF-8", result.stderr)

    def test_changelog_section_normalizes_committed_crlf_to_utf8_lf(self):
        sample = self._SAMPLE_CHANGELOG.replace("\n", "\r\n")
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp, sample)
            result = self._run_core(
                "changelog-section", tmp, "release-v2.12.0",
                "docs/CHANGELOG.md", "2.12.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("\r", result.stdout)

    def test_changelog_section_round_trips_through_a_real_subprocess_as_utf8(self):
        # Regression for a real bug found while writing this fix: `sys.
        # stdout.write()` is text-mode, and a genuine child process on
        # Windows with no PYTHONIOENCODING/PYTHONUTF8 set encodes stdout
        # using the ambient console codepage (cp1252) rather than UTF-8 --
        # silently mangling the em-dash every changelog heading carries
        # (`## [X.Y.Z] — DATE`) into the wrong byte, and translating `\n`
        # to `\r\n` besides. `core_releaselib.main()` called in-process
        # against an `io.StringIO` (every other test in this class) cannot
        # catch this: `StringIO` has no `.buffer` and does no codepage
        # transcoding at all, so the bug is invisible unless stdout is a
        # REAL process stream. This test shells out for exactly that reason.
        with tempfile.TemporaryDirectory() as tmp:
            self._init_changelog_repo(tmp)
            result = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH,
                 "changelog-section", tmp, "release-v2.12.0",
                 "docs/CHANGELOG.md", "2.12.0"],
                capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = (
                "## [2.12.0] — 2026-08-07\n\n### Added\n\n"
                "- newest thing\n").encode("utf-8")
            self.assertEqual(result.stdout, expected)

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

    def test_list_values_reject_the_show_row_comma_separator(self):
        for key in ("manifest", "artifacts", "generated-manifest",
                    "payload-exclude", "release-asset"):
            with self.subTest(key=key), \
                    self.assertRaises(core_releaselib.MalformedBlockError):
                core_releaselib.parse_release_targets(self._block([
                    "[app]", "prefix: v", "changelog: CHANGELOG.md",
                    "payload: .", f"{key}: one,two"]))

    def test_declared_paths_reject_nul_and_control_bytes(self):
        cases = (
            ("payload", "src/\x00../other"),
            ("payload-exclude", "src/\x1fprivate"),
            ("manifest", "pkg\x7f.json"),
            ("changelog", "docs/CHANGE\x00LOG.md"),
            ("artifacts", "dist/app\x1fbundle.js"),
            ("generated-manifest", "dist/pkg\x7f.json"),
            ("provenance-manifest", ".github/tags\x00.json"),
            ("changelog-reconciliations", ".codearbiter/notes\x1f.json"),
        )
        for key, value in cases:
            required = {
                "changelog": value if key == "changelog" else "CHANGELOG.md",
                "payload": value if key == "payload" else "src/",
            }
            optional = [] if key in required else [f"{key}: {value}"]
            with self.subTest(key=key), \
                    self.assertRaises(core_releaselib.MalformedBlockError):
                core_releaselib.parse_release_targets(self._block([
                    "[app]", "prefix: v",
                    f"changelog: {required['changelog']}",
                    f"payload: {required['payload']}", *optional]))

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
            cwd=tempfile.gettempdir(), env=env, capture_output=True,
            text=True, encoding="utf-8")

    def test_list_field_preserves_a_pre_tag_command_containing_a_comma(self):
        command = '"$PY" -c "import sys,os; assert sys.version_info"'
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [command])
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                       PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH,
                 "list-field", "app", "pre-tag"],
                cwd=tempfile.gettempdir(), env=env,
                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, command + "\n")

    def _run_clean_tree_status(self, root):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "clean-tree-status", "app"],
            cwd=tempfile.gettempdir(), env=env, capture_output=True,
            text=True, encoding="utf-8")

    def test_clean_tree_status_ignores_ambient_repository_rebinding(self):
        with tempfile.TemporaryDirectory() as intended_tmp, \
                tempfile.TemporaryDirectory() as counterfeit_tmp:
            intended = self._pretag_repo(intended_tmp, [], dirty=True)
            counterfeit = self._pretag_repo(counterfeit_tmp, [], dirty=False)
            rebound = {
                "GIT_DIR": os.path.join(counterfeit, ".git"),
                "GIT_WORK_TREE": counterfeit,
            }
            with mock.patch.dict(os.environ, rebound):
                proc = self._run_clean_tree_status(intended)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("package.json", proc.stdout)
            self.assertIn("CHANGELOG.md", proc.stdout)

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

    def test_run_pre_tag_catches_an_index_only_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, ["git add package.json"], dirty=True)
            before = subprocess.check_output(
                ["git", "-C", root, "ls-files", "--stage", "--", "package.json"],
                text=True)
            proc = self._run_pre_tag(root)
            after = subprocess.check_output(
                ["git", "-C", root, "ls-files", "--stage", "--", "package.json"],
                text=True)
            self.assertNotEqual(before, after)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn("package.json", proc.stderr)

    def test_run_pre_tag_does_not_read_through_a_worktree_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [])
            linked = os.path.join(root, "linked.txt")
            outside = os.path.join(tmp, "outside.txt")
            with open(outside, "w", encoding="utf-8") as handle:
                handle.write("outside\n")
            try:
                os.symlink(outside, linked)
            except (OSError, NotImplementedError):
                self.skipTest("file symlink creation unavailable on this host")

            original_open = open

            def guarded_open(path, *args, **kwargs):
                if os.fspath(path) == linked:
                    self.fail("tree snapshot followed a worktree symlink")
                return original_open(path, *args, **kwargs)

            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("builtins.open", side_effect=guarded_open):
                self.assertEqual(core_releaselib.main(["run-pre-tag", "app"]), 0)

    def test_run_pre_tag_snapshots_index_without_one_git_call_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [])
            real_run = subprocess.run
            index_calls = []

            def observed_run(argv, *args, **kwargs):
                if isinstance(argv, list) and "ls-files" in argv:
                    index_calls.append(argv)
                return real_run(argv, *args, **kwargs)

            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                      side_effect=observed_run):
                self.assertEqual(core_releaselib.main(["run-pre-tag", "app"]), 0)
            self.assertLessEqual(len(index_calls), 2, index_calls)

    def test_run_pre_tag_catches_mutation_of_non_ascii_dirty_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = "printf 'PRETAG\\n' >> 'CHANGELOG-é.md'"
            root = self._pretag_repo(tmp, [command], dirty=False)
            os.replace(
                os.path.join(root, "CHANGELOG.md"),
                os.path.join(root, "CHANGELOG-é.md"))
            targets_path = os.path.join(
                root, ".codearbiter", "release-targets.md")
            with open(targets_path, encoding="cp1252") as handle:
                targets = handle.read()
            with open(targets_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(targets.replace(
                    "changelog: CHANGELOG.md",
                    "changelog: CHANGELOG-é.md"))
            with open(os.path.join(root, "CHANGELOG-é.md"), "a",
                      encoding="utf-8", newline="\n") as handle:
                handle.write("PHASE1\n")
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn("CHANGELOG-é.md", proc.stderr)

    def test_run_pre_tag_and_clean_tree_reject_skip_worktree_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = (
                'git update-index --skip-worktree package.json && '
                '"$PY" -c "from pathlib import Path; '
                "Path('package.json').write_text('silently-mutated\\n')\"")
            root = self._pretag_repo(tmp, [command], dirty=False)
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn("package.json", proc.stderr)
            clean = self._run_clean_tree_status(root)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertIn("hidden-index-state package.json", clean.stdout)

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

    def test_select_target_name_keyed_ignores_a_blank_name(self):
        # "=1.2.3" (a stray leading "=") previously fell through the
        # "name and name not in known" unknown-check -- blank is falsy, so
        # it skipped that check -- and then appended "" to `selected`,
        # returning the bare string "" rather than any label in the
        # documented vocabulary (<target>|none|multiple|unknown). A blank
        # NAME identifies no target and must be ignored like a pair with no
        # "=" at all.
        for pairs in (["=1.2.3"], ["  =1.2.3"]):
            result = core_releaselib.select_release_target_by_name(
                pairs, self.TARGETS)
            self.assertEqual(result, "none", pairs)
            self.assertIn(result, self.TARGETS + ["none", "multiple", "unknown"])

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

    def test_blank_rebuild_string_is_treated_as_absent_not_declared(self):
        # A row spelling `rebuild: ""` or `rebuild: "   "` (a stray blank
        # value, not an omitted key) previously passed `isinstance(..., str)`
        # and came back as a truthy-looking "" in `verdict["rebuild"]",
        # skipping the "rebuild" entry in `skipped` even though no command
        # was actually declared -- the same class of gap `provenance` (two
        # lines below in the source) already guards against with a
        # `.strip()` check. Blank must read the same as omitted.
        for blank in ("", "   ", "\t\n"):
            row = dict(self.ROW_BARE, rebuild=blank)
            verdict = core_releaselib.row_assertions(row)
            self.assertIsNone(verdict["rebuild"], repr(blank))
            self.assertIn("rebuild",
                          [name for name, _reason in verdict["skipped"]],
                          repr(blank))

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

    def test_release_build_changes_invalidate_the_same_confirmation_marker(self):
        rh = self._releasehash()
        pre_tag = ["python3 checks/a.py"]
        with tempfile.TemporaryDirectory() as root:
            original = rh.pre_tag_digest(pre_tag, "python3 build.py --mode a")
            changed = rh.pre_tag_digest(pre_tag, "python3 build.py --mode b")
            self.assertNotEqual(original, changed)
            rh.record_confirmation(root, "app", original)
            self.assertEqual(
                rh.confirmation_state(
                    root, "app", pre_tag, "python3 build.py --mode a"),
                rh.CONFIRMED)
            self.assertEqual(
                rh.confirmation_state(
                    root, "app", pre_tag, "python3 build.py --mode b"),
                rh.CHANGED)

    def test_rebuild_and_generate_changes_invalidate_confirmation(self):
        rh = self._releasehash()
        commands = ["python3 checks/a.py"]
        original = rh.pre_tag_digest(
            commands, "python3 package.py", "python3 rebuild.py --mode a",
            "python3 generate.py --mode a")
        self.assertNotEqual(
            original,
            rh.pre_tag_digest(
                commands, "python3 package.py", "python3 rebuild.py --mode b",
                "python3 generate.py --mode a"))
        self.assertNotEqual(
            original,
            rh.pre_tag_digest(
                commands, "python3 package.py", "python3 rebuild.py --mode a",
                "python3 generate.py --mode b"))
        with tempfile.TemporaryDirectory() as root:
            rh.record_confirmation(root, "app", original)
            self.assertEqual(
                rh.confirmation_state(
                    root, "app", commands, "python3 package.py",
                    "python3 rebuild.py --mode a",
                    "python3 generate.py --mode a"),
                rh.CONFIRMED)
            self.assertEqual(
                rh.confirmation_state(
                    root, "app", commands, "python3 package.py",
                    "python3 rebuild.py --mode b",
                    "python3 generate.py --mode a"),
                rh.CHANGED)

    def test_rebuild_or_generate_only_row_requires_cli_reconfirmation(self):
        releasehash = os.path.join(REPO_ROOT, "core", "pysrc", "releasehash.py")
        for field in ("rebuild", "generate"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = self._pretag_repo(tmp, [])
                targets = os.path.join(root, ".codearbiter", "release-targets.md")
                original = Path(targets).read_text(encoding="utf-8")
                Path(targets).write_text(
                    original.replace("<!-- /release-targets -->",
                                     f"{field}: echo first\n<!-- /release-targets -->"),
                    encoding="utf-8")
                env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                           PYTHONDONTWRITEBYTECODE="1")

                def invoke(action):
                    return subprocess.run(
                        [sys.executable, releasehash, action, "app"],
                        cwd=root, env=env, capture_output=True, text=True)

                self.assertEqual(invoke("check").returncode, 2)
                recorded = invoke("record")
                self.assertEqual(recorded.returncode, 0, recorded.stderr)
                confirmed = invoke("check")
                self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
                self.assertEqual(confirmed.stdout.strip(), "confirmed")
                Path(targets).write_text(
                    Path(targets).read_text(encoding="utf-8").replace(
                        f"{field}: echo first", f"{field}: echo second"),
                    encoding="utf-8")
                changed = invoke("check")
                self.assertEqual(changed.returncode, 1, changed.stderr)
                self.assertEqual(changed.stdout.strip(), "changed")

    def test_rows_without_release_build_keep_the_existing_digest_identity(self):
        rh = self._releasehash()
        self.assertEqual(
            rh.pre_tag_digest(["check_a.py", "check_b.py"]),
            "9e41b57a8b69eca55dec9fb6d86e446120686eb8a6b7cc6b163785bde2e24a02")
        self.assertEqual(
            rh.pre_tag_digest(["check_a.py", "check_b.py"], None),
            rh.pre_tag_digest(["check_a.py", "check_b.py"], ""))

    def test_release_build_alone_requires_confirmation(self):
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(
                rh.confirmation_state(root, "app", [], "python3 build.py"),
                rh.NEVER)
            rh.record_confirmation(
                root, "app", rh.pre_tag_digest([], "python3 build.py"))
            self.assertEqual(
                rh.confirmation_state(root, "app", [], "python3 build.py"),
                rh.CONFIRMED)

    def test_show_row_prints_every_declared_field(self):
        # Blind exercise run 14, HIGH. The lane forbids reading the declared
        # file by eye, but only `prefix` and the target names had readers —
        # so nine fields could ONLY be obtained the forbidden way, and an
        # exercising agent did exactly that and said so.
        out = self._run_core("show-row", "ca")
        self.assertEqual(out.returncode, 0, out.stderr)
        keys = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)
        for expected in ("TARGET", "TAG_PREFIX", "MANIFEST", "CHANGELOG", "PAYLOAD",
                         "ARTIFACTS", "PRE_TAG", "PROVENANCE_MANIFEST",
                         "LATEST_ELIGIBLE", "GENERATED_MANIFEST", "GENERATE",
                         "PAYLOAD_EXCLUDE", "REBUILD", "DISPLAY_NAME",
                         "VERSION_POLICY", "INITIAL_VERSION", "RELEASE_BUILD",
                         "RELEASE_ASSETS"):
            self.assertIn(expected, keys, out.stdout)
        self.assertEqual(keys["TARGET"], "ca")
        self.assertEqual(keys["TAG_PREFIX"], "v")
        # An UNDECLARED field prints empty rather than vanishing, so a
        # caller can tell "not declared" from "I did not look". Shell-quoted,
        # so an empty value is the two-character `''`.
        self.assertIn(keys["GENERATED_MANIFEST"], ("", "''"))

    def test_show_row_output_is_shell_quoted_and_eval_executes_nothing(self):
        # Blind exercise run 15, HIGH. Unquoted output made the documented
        # `eval "$(show-row ...)"` EXECUTE declared values: `rebuild: cd x &&
        # npm run build` parsed as `REBUILD=cd` plus the command `x`, with
        # `&& npm run build` next -- and eval still exited 0. These values
        # are operator shell the lane runs only AFTER releasehash confirms a
        # human read them, so executing a fragment at row-read time runs it
        # BEFORE its own gate.
        out = self._run_core("show-row", "ca")
        rebuild = next(line for line in out.stdout.splitlines()
                       if line.startswith("REBUILD="))
        self.assertIn("&&", rebuild, "fixture must carry a shell metachar")
        self.assertTrue(rebuild.startswith("REBUILD='"),
                        f"value must be shell-quoted, got: {rebuild}")
        # The decisive check, and it runs on EVERY platform: POSIX-tokenize
        # each emitted line and require it to be exactly ONE word. A single
        # word is an assignment and nothing else -- there is no room after
        # it for the `&&`, `;` or bare command that the run-15 finding had
        # `eval` execute. Doing this with `shlex` rather than a real shell
        # keeps the security property asserted where no usable `bash`
        # exists (see `working_bash`), instead of silently skipping it on
        # the platform whose quoting is most likely to differ.
        for line in out.stdout.splitlines():
            if not line.strip():
                continue
            words = shlex.split(line)
            self.assertEqual(
                len(words), 1,
                f"row line tokenizes to {len(words)} words, so something "
                f"after the assignment would run: {line!r}")
            name, sep, _ = words[0].partition("=")
            self.assertEqual(sep, "=", f"not an assignment: {line!r}")
            self.assertRegex(name, r"\A[A-Z_][A-Z0-9_]*\Z",
                             f"assignment target is not a plain shell "
                             f"variable name: {line!r}")
        # Corroborating arm: hand the whole block to a real shell and prove
        # it assigns without executing. Skipped where no working shell
        # exists, which is why the tokenizer check above is not optional.
        bash = working_bash()
        if bash is None:
            self.skipTest("no working bash on this platform for the "
                          "shell round-trip arm")
        script = (out.stdout + "\n"
                  + 'printf "%s|%s|%s" "$TAG_PREFIX" "$REBUILD" "$PRE_TAG"\n')
        # Fed on STDIN, not `bash -c <script>`: on Windows the multi-line
        # argument is mangled by the exec-layer quoting and every variable
        # comes back empty, which would make this test pass vacuously by
        # "finding" no shell output.
        # BYTES, not text=True: universal-newline translation rewrites every
        # \n as \r\n on Windows, and bash then reports `$'\r': command not
        # found` for a script this test authored correctly.
        proc = subprocess.run([bash, "-s"], input=script.encode("utf-8"),
                              capture_output=True, cwd=REPO_ROOT)
        stderr = proc.stderr.decode("utf-8", "replace")
        stdout = proc.stdout.decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, stderr)
        self.assertEqual(stderr.strip(), "",
                         f"reading the row produced shell output: {stderr}")
        parts = [p.strip() for p in stdout.split("|")]
        self.assertEqual(len(parts), 3, stdout)
        prefix, rebuilt, pre_tag = parts
        self.assertEqual(prefix, "v",
                         "the assignments did not take effect — this test "
                         "would be vacuous")
        self.assertEqual(rebuilt, "cd plugins/ca/tools && npm run build")
        self.assertTrue(pre_tag, "PRE_TAG must survive the round trip")

    def test_show_row_field_returns_one_raw_value(self):
        out = self._run_core("show-row", "ca", "--field", "payload")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "plugins/ca/")
        self.assertNotIn("=", out.stdout)

    def test_show_row_field_rejects_an_unknown_name(self):
        out = self._run_core("show-row", "ca", "--field", "nope")
        self.assertEqual(out.returncode, 2)
        self.assertIn("unknown field", out.stderr)
        for field in ("version_policy", "initial_version",
                      "release_build", "release_assets"):
            with self.subTest(field=field):
                self.assertIn(field, out.stderr)

    def test_show_row_rejects_an_unknown_target(self):
        out = self._run_core("show-row", "not-a-target")
        self.assertEqual(out.returncode, 2)
        self.assertIn("unknown release target", out.stderr)

    def test_payload_pathspec_emits_the_exclude_form(self):
        # Blind exercise run 14, HIGH. `$PAYLOAD` is documented as "payload
        # minus payload-exclude", and `git log -- <path>` has no
        # subtraction — so for any row declaring an exclude the window was
        # unspellable from the prose, and the excluded commits silently
        # counted toward the bump and the changelog.
        out = self._run_core("payload-pathspec", "ca-pi")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(),
                         ["plugins/ca-pi/", ":(exclude)plugins/ca-pi/tools/"])

    def test_payload_pathspec_on_a_row_without_an_exclude_is_just_the_payload(self):
        out = self._run_core("payload-pathspec", "ca")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "plugins/ca/")

    def test_payload_pathspec_actually_narrows_a_real_git_window(self):
        # Driven through git rather than asserted as a string: the point of
        # the subcommand is that its output works verbatim after `--`.
        pathspec = self._run_core("payload-pathspec", "ca-pi").stdout.splitlines()
        base = ["git", "log", "--oneline", "-40", "--"]
        with_exclude = subprocess.run(base + pathspec, cwd=REPO_ROOT,
                                      capture_output=True, text=True)
        without = subprocess.run(base + ["plugins/ca-pi/"], cwd=REPO_ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(with_exclude.returncode, 0, with_exclude.stderr)
        self.assertLessEqual(len(with_exclude.stdout.splitlines()),
                             len(without.stdout.splitlines()))

    def test_payload_pathspec_preserves_a_payload_containing_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "consumer")
            os.makedirs(os.path.join(root, ".codearbiter"))
            os.makedirs(os.path.join(root, "app dir"))
            with open(os.path.join(root, ".codearbiter", "release-targets.md"), "w") as fh:
                fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                         "manifest: package.json\nchangelog: CHANGELOG.md\n"
                         "payload: app dir/\n<!-- /release-targets -->\n")
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                       PYTHONDONTWRITEBYTECODE="1")
            out = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH,
                 "payload-pathspec", "app"],
                cwd=tempfile.gettempdir(), env=env,
                capture_output=True)
            stderr = out.stderr.decode("utf-8", "replace")
            self.assertEqual(out.returncode, 0, stderr)
            self.assertEqual(out.stdout, b"app dir/\n")
            with open(os.path.join(root, "app dir", "feature.txt"), "w") as fh:
                fh.write("tracked\n")
            subprocess.run(["git", "init"], cwd=root, check=True,
                           capture_output=True, text=True)
            subprocess.run(["git", "config", "user.name", "Test"],
                           cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                           cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "feat: tracked path"],
                           cwd=root, check=True, capture_output=True, text=True)
            selected = subprocess.run(
                ["git", "log", "--format=%s", "--",
                 *out.stdout.decode("utf-8").splitlines()],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout.strip(), "feat: tracked path")

            bash = (core_releaselib._resolve_posix_shell()
                    if os.name == "nt" else working_bash())
            if bash is not None:
                helper = _CORE_RELEASELIB_PATH.replace("\\", "/")
                project = root.replace("\\", "/")
                script = (
                    f'export CLAUDE_PROJECT_DIR={shlex.quote(project)}\n'
                    'set --\n'
                    f'while IFS= read -r pathspec; do set -- "$@" "$pathspec"; '
                    f'done < <(python "{helper}" '
                    'payload-pathspec app)\n'
                    'printf "<%s>" "$1"\n'
                    'git log --format=%s -- "$@"\n')
                shell = subprocess.run(
                    [bash, "-s"], input=script.encode("utf-8"), cwd=root,
                    capture_output=True)
                shell_stderr = shell.stderr.decode("utf-8", "replace")
                shell_stdout = shell.stdout.decode("utf-8", "replace")
                self.assertEqual(shell.returncode, 0, shell_stderr)
                self.assertIn("<app dir/>", shell_stdout)
                self.assertIn("feat: tracked path", shell_stdout)

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
            cargo = os.path.join(tmp, "Cargo.toml")
            with open(cargo, "w") as fh:
                fh.write('[package]\nname = "blind-probe"\nversion = "7.8.9"\n')
            self.assertEqual(core_releaselib._manifest_version(cargo), "7.8.9")
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

    def test_backfilled_cargo_manifest_passes_the_required_manifest_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "consumer")
            os.makedirs(os.path.join(root, ".codearbiter"))
            with open(os.path.join(root, "Cargo.toml"), "w") as fh:
                fh.write('[package]\nname = "blind-probe"\nversion = "1.2.3"\n')
            with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
                fh.write("# Changelog\n")
            with open(os.path.join(root, ".codearbiter", "release-targets.md"), "w") as fh:
                fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                         "manifest: Cargo.toml\nchangelog: CHANGELOG.md\n"
                         "payload: .\nlatest-eligible: true\n"
                         "<!-- /release-targets -->\n")
            proc = self._run_check_manifests(root, "1.2.3")
            self.assertEqual(proc.returncode, 0, proc.stderr)

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

    def test_release_footers_must_be_in_the_terminal_paragraph(self):
        middle = "CHANGELOG: not a footer\n\nordinary closing prose"
        classified = core_releaselib.classify_commit("fix: bug", middle)
        self.assertFalse(classified["has_changelog_footer"])
        breaking = "BREAKING CHANGE: not a footer\n\nordinary closing prose"
        self.assertEqual(
            core_releaselib.classify_commit("docs: prose", breaking)["bump"],
            "none")
        terminal = "Explanation.\n\nCHANGELOG: Fixed the bug."
        self.assertTrue(core_releaselib.classify_commit(
            "fix: bug", terminal)["has_changelog_footer"])
        terminal_breaking = "Explanation.\n\nBREAKING CHANGE: protocol changed"
        self.assertEqual(core_releaselib.classify_commit(
            "docs: prose", terminal_breaking)["bump"], "major")

    def test_changelog_footer_must_be_unique_and_nonempty(self):
        empty = core_releaselib.classify_commit("fix: bug", "CHANGELOG:")
        duplicate = core_releaselib.classify_commit(
            "fix: bug", "CHANGELOG: first\nCHANGELOG: second")
        self.assertFalse(empty["has_changelog_footer"])
        self.assertFalse(duplicate["has_changelog_footer"])
        self.assertEqual(empty["changelog"], "")
        self.assertEqual(duplicate["changelog"], "")

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

    def test_published_reconciliation_clears_only_its_exact_missing_footer(self):
        sha = "a" * 40
        commits = [
            {"sha": sha, "subject": "fix: published squash", "body": ""},
            {"sha": "b" * 40, "subject": "fix: still malformed", "body": ""},
        ]
        try:
            window = core_releaselib.classify_window(
                commits,
                reconciliations={sha: "Recover the exact published release note."},
                published_shas={sha},
            )
        except TypeError as exc:
            self.fail(f"classify_window has no explicit reconciliation seam: {exc}")
        self.assertEqual([row["sha"] for row in window["missing_footer"]], ["b" * 40])
        self.assertEqual(
            window["commits"][0]["changelog"],
            "Recover the exact published release note.")
        self.assertTrue(window["commits"][0]["footer_reconciled"])

    def test_unpublished_or_short_sha_reconciliation_cannot_clear_the_gate(self):
        sha = "c" * 40
        commits = [{"sha": sha, "subject": "feat: candidate", "body": ""}]
        for reconciliations, published in (
                ({sha: "Candidate note."}, set()),
                ({sha[:7]: "Short identity."}, {sha})):
            with self.subTest(reconciliations=reconciliations, published=published):
                try:
                    window = core_releaselib.classify_window(
                        commits,
                        reconciliations=reconciliations,
                        published_shas=published,
                    )
                except TypeError as exc:
                    self.fail(f"classify_window has no explicit reconciliation seam: {exc}")
                self.assertEqual(
                    [row["sha"] for row in window["missing_footer"]], [sha])

    def test_reconciliation_ledger_is_strict_and_duplicate_sha_fails_closed(self):
        parser = getattr(core_releaselib, "parse_changelog_reconciliations", None)
        self.assertIsNotNone(parser, "the release helper lacks a strict ledger parser")
        valid = """{
          "schema_version": 1,
          "entries": [{
            "target": "academy-preview",
            "commit_sha": "dddddddddddddddddddddddddddddddddddddddd",
            "changelog": "Restore the exact published release note.",
            "reason": "The published squash body stored escaped newlines.",
            "authorization": "Maintainer-approved evidence reconciliation."
          }]
        }"""
        parsed = parser(valid, "academy-preview")
        self.assertEqual(
            parsed,
            {"d" * 40: "Restore the exact published release note."})
        duplicate = valid.replace(
            "]\n        }",
            ", {\"target\": \"academy-preview\", "
            "\"commit_sha\": \"dddddddddddddddddddddddddddddddddddddddd\", "
            "\"changelog\": \"Second note.\", \"reason\": \"Duplicate.\", "
            "\"authorization\": \"No.\"}]\n        }")
        with self.assertRaises(core_releaselib.ReleaseTargetsError):
            parser(duplicate, "academy-preview")

    def test_reconciliation_ledger_rejects_every_malformed_schema_arm(self):
        valid_entry = {
            "target": "app",
            "commit_sha": "a" * 40,
            "changelog": "Exact note.",
            "reason": "Published footer was malformed.",
            "authorization": "Maintainer approved.",
        }
        cases = {
            "invalid json": "{",
            "top level list": json.dumps([]),
            "extra top key": json.dumps({
                "schema_version": 1, "entries": [], "extra": True}),
            "boolean schema": json.dumps({
                "schema_version": True, "entries": []}),
            "wrong schema": json.dumps({
                "schema_version": 2, "entries": []}),
            "entries not list": json.dumps({
                "schema_version": 1, "entries": {}}),
            "entry not object": json.dumps({
                "schema_version": 1, "entries": [None]}),
            "missing entry key": json.dumps({
                "schema_version": 1,
                "entries": [{k: v for k, v in valid_entry.items()
                             if k != "reason"}]}),
            "extra entry key": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, extra="no")]}),
            "invalid target": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, target="bad target")]}),
            "uppercase sha": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, commit_sha="A" * 40)]}),
            "short sha": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, commit_sha="a" * 39)]}),
            "leading whitespace": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, changelog=" Exact note.")]}),
            "embedded newline": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, reason="line one\nline two")]}),
            "overlong value": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, authorization="x" * 4097)]}),
            "too many entries": json.dumps({
                "schema_version": 1,
                "entries": [dict(valid_entry, commit_sha=f"{i:040x}")
                            for i in range(1025)]}),
        }
        for label, text in cases.items():
            with self.subTest(label=label), \
                    self.assertRaises(core_releaselib.ChangelogReconciliationError):
                core_releaselib.parse_changelog_reconciliations(text, "app")

        boundary_entry = dict(valid_entry, authorization="x" * 4096)
        boundary_entries = [dict(boundary_entry, target="other",
                                 commit_sha=f"{i:040x}") for i in range(1024)]
        parsed = core_releaselib.parse_changelog_reconciliations(
            json.dumps({"schema_version": 1, "entries": boundary_entries}), "app")
        self.assertEqual(parsed, {})

    def test_reconciliation_ledger_accepts_full_sha256_object_ids(self):
        sha = "a" * 64
        text = json.dumps({
            "schema_version": 1,
            "entries": [{
                "target": "app",
                "commit_sha": sha,
                "changelog": "Exact note.",
                "reason": "Published footer was malformed.",
                "authorization": "Maintainer approved.",
            }],
        })
        self.assertEqual(
            core_releaselib.parse_changelog_reconciliations(text, "app"),
            {sha: "Exact note."})

    def test_malformed_unrelated_target_entry_still_fails_whole_ledger(self):
        ledger = {
            "schema_version": 1,
            "entries": [{
                "target": "other target",
                "commit_sha": "a" * 40,
                "changelog": "Other note.",
                "reason": "Malformed unrelated row.",
                "authorization": "None.",
            }],
        }
        with self.assertRaises(core_releaselib.ChangelogReconciliationError):
            core_releaselib.parse_changelog_reconciliations(
                json.dumps(ledger), "app")

    def test_reconciliation_ledger_rejects_duplicate_json_members(self):
        cases = (
            '{"schema_version":1,"schema_version":1,"entries":[]}',
            '{"schema_version":1,"entries":[{'
            '"target":"app","commit_sha":"' + "a" * 40 + '",'
            '"commit_sha":"' + "b" * 40 + '","changelog":"One.",'
            '"reason":"Why.","authorization":"Who."}]}',
            '{"schema_version":1,"entries":[{'
            '"target":"app","commit_sha":"' + "a" * 40 + '",'
            '"changelog":"One.","changelog":"Two.",'
            '"reason":"Why.","authorization":"Who."}]}',
            '{"schema_version":1,"entries":[{'
            '"target":"app","commit_sha":"' + "a" * 40 + '",'
            '"changelog":"One.","reason":"Why.",'
            '"authorization":"Who.","authorization":"Other."}]}',
        )
        for text in cases:
            with self.subTest(text=text), \
                    self.assertRaises(core_releaselib.ChangelogReconciliationError):
                core_releaselib.parse_changelog_reconciliations(text, "app")

    def test_release_target_can_declare_one_reconciliation_ledger(self):
        text = """<!-- release-targets -->
[academy-preview]
prefix: preview-
changelog: CHANGELOG.md
payload: .
changelog-reconciliations: .codearbiter/release-changelog-reconciliations.json
<!-- /release-targets -->
"""
        try:
            row = core_releaselib.parse_release_targets(text)[0]
        except core_releaselib.ReleaseTargetsError as exc:
            self.fail(f"the declared reconciliation path is not supported: {exc}")
        self.assertEqual(
            row["changelog_reconciliations"],
            ".codearbiter/release-changelog-reconciliations.json")

    def _reconciliation_repo(self, tmp, object_format=None):
        root = os.path.join(tmp, "consumer")
        os.makedirs(os.path.join(root, ".codearbiter"))
        init_args = ["init", "--quiet", "--initial-branch=main"]
        if object_format is not None:
            init_args.append(f"--object-format={object_format}")
        self._git(root, *init_args)
        self._git(root, "config", "user.name", "release fixture")
        self._git(root, "config", "user.email", "release@example.invalid")
        targets = """<!-- release-targets -->
[app]
prefix: v
changelog: CHANGELOG.md
payload: .
changelog-reconciliations: .codearbiter/reconciliations.json
<!-- /release-targets -->
"""
        with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write(targets)
        with open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8",
                  newline="\n") as handle:
            handle.write("# Changelog\n")
        with open(os.path.join(root, "payload.txt"), "w", encoding="utf-8",
                  newline="\n") as handle:
            handle.write("published\n")
        with open(os.path.join(root, ".codearbiter", "reconciliations.json"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write('{"schema_version":1,"entries":[]}\n')
        self._git(root, "add", ".")
        self._git(root, "commit", "--quiet", "-m", "feat: published squash")
        sha = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
        self._git(root, "update-ref", "refs/remotes/origin/main", sha)
        return root, sha

    def _write_reconciliation(self, root, sha):
        ledger = {
            "schema_version": 1,
            "entries": [{
                "target": "app",
                "commit_sha": sha,
                "changelog": "Recover the exact published release note.",
                "reason": "The published squash body stored escaped newlines.",
                "authorization": "Maintainer-approved evidence reconciliation.",
            }],
        }
        with open(os.path.join(root, ".codearbiter", "reconciliations.json"),
                  "w", encoding="utf-8", newline="\n") as handle:
            json.dump(ledger, handle)
            handle.write("\n")

    def _publish_ledger_commit(self, root, message="chore: publish reconciliation"):
        self._git(root, "add", ".codearbiter/reconciliations.json")
        self._git(root, "commit", "--quiet", "-m", message)
        head = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
        self._git(root, "update-ref", "refs/remotes/origin/main", head)
        return head

    def test_classify_window_cli_accepts_only_exact_published_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            self._write_reconciliation(root, sha)
            self._publish_ledger_commit(root)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "[RECONCILED] " + sha[:7] + " feat: published squash :: "
            "Recover the exact published release note.", result.stdout)
        self.assertNotIn("[NEEDS-TRIAGE]", result.stdout)

    def test_classify_window_accepts_sha256_published_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root, sha = self._reconciliation_repo(tmp, "sha256")
            except subprocess.CalledProcessError as exc:
                self.skipTest(
                    "installed Git lacks SHA-256 repository support: "
                    + exc.stderr.decode(errors="replace"))
            self.assertEqual(len(sha), 64)
            self._write_reconciliation(root, sha)
            self._publish_ledger_commit(root)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[RECONCILED] " + sha[:7], result.stdout)

    def test_classify_window_cli_rejects_reconciliation_not_on_published_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, published_sha = self._reconciliation_repo(tmp)
            self._git(root, "switch", "--quiet", "-c", "candidate")
            with open(os.path.join(root, "payload.txt"), "a", encoding="utf-8") as handle:
                handle.write("candidate\n")
            self._git(root, "add", "payload.txt")
            self._git(root, "commit", "--quiet", "-m", "fix: unpublished candidate")
            candidate_sha = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "tag", "main", candidate_sha)
            self._git(root, "switch", "--quiet", "main")
            self._write_reconciliation(root, candidate_sha)
            self._publish_ledger_commit(root)
            log = f"{candidate_sha}\0fix: unpublished candidate\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("[NEEDS-TRIAGE] " + candidate_sha[:7], result.stdout)
        self.assertNotEqual(candidate_sha, published_sha)
        self.assertNotIn("[RECONCILED]", result.stdout)

    def test_classify_window_cli_rejects_candidate_sha_as_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            self._write_reconciliation(root, sha)
            self._publish_ledger_commit(root)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", sha)
        self.assertEqual(result.returncode, 4)
        self.assertIn("refs/remotes/origin/" + sha, result.stderr)

    def test_classify_window_cli_fails_closed_on_missing_declared_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            os.unlink(os.path.join(root, ".codearbiter", "reconciliations.json"))
            self._git(root, "add", ".codearbiter/reconciliations.json")
            self._git(root, "commit", "--quiet", "-m", "chore: remove ledger")
            removed = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "update-ref", "refs/remotes/origin/main", removed)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 4)
        self.assertIn("must be one regular file committed", result.stderr)

    def test_ignored_live_only_ledger_cannot_clear_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            os.unlink(os.path.join(root, ".codearbiter", "reconciliations.json"))
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as handle:
                handle.write("/.codearbiter/reconciliations.json\n")
            self._git(root, "add", ".gitignore", ".codearbiter/reconciliations.json")
            self._git(root, "commit", "--quiet", "-m", "chore: ignore live ledger")
            published = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "update-ref", "refs/remotes/origin/main", published)
            self._write_reconciliation(root, sha)
            self.assertEqual(
                self._git(root, "status", "--porcelain").stdout.decode(), "")
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 4)
        self.assertIn("must be one regular file committed", result.stderr)

    def test_intermediate_symlink_ledger_path_cannot_clear_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            outside = os.path.join(tmp, "outside")
            os.makedirs(outside)
            outside_ledger = os.path.join(outside, "ledger.json")
            with open(outside_ledger, "w", encoding="utf-8") as handle:
                handle.write('{"schema_version":1,"entries":[]}\n')
            linked = os.path.join(root, ".codearbiter", "linked")
            try:
                os.symlink(outside, linked, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlink creation unavailable on this host")
            self._git(root, "config", "core.symlinks", "true")
            targets_path = os.path.join(root, ".codearbiter", "release-targets.md")
            with open(targets_path, encoding="utf-8") as handle:
                targets = handle.read()
            with open(targets_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(targets.replace(
                    ".codearbiter/reconciliations.json",
                    ".codearbiter/linked/ledger.json"))
            self._git(root, "add", ".codearbiter/release-targets.md",
                      ".codearbiter/linked")
            self._git(root, "commit", "--quiet", "-m", "chore: publish linked ledger")
            published = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "update-ref", "refs/remotes/origin/main", published)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 4)
        self.assertIn("must be one regular file committed", result.stderr)

    def test_classify_window_cli_fails_closed_on_non_utf8_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            with open(os.path.join(root, ".codearbiter", "reconciliations.json"),
                      "wb") as handle:
                handle.write(b"\xff\xfe")
            self._publish_ledger_commit(root, "chore: publish invalid ledger")
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 4)
        self.assertIn("committed ledger is not UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_classify_window_cli_fails_closed_on_symlinked_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            ledger_path = os.path.join(root, ".codearbiter", "reconciliations.json")
            outside = os.path.join(tmp, "outside.json")
            os.unlink(ledger_path)
            with open(outside, "w", encoding="utf-8") as handle:
                handle.write('{"schema_version":1,"entries":[]}\n')
            try:
                os.symlink(outside, ledger_path)
            except (OSError, NotImplementedError):
                self.skipTest("file symlink creation unavailable on this host")
            self._git(root, "config", "core.symlinks", "true")
            self._git(root, "add", ".codearbiter/reconciliations.json")
            self._git(root, "commit", "--quiet", "-m", "chore: publish symlink")
            symlink_head = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "update-ref", "refs/remotes/origin/main", symlink_head)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 4)
        self.assertIn("committed regular blob", result.stderr)

    def test_classify_window_cli_fails_when_published_ref_cannot_be_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = self._reconciliation_repo(tmp)
            self._write_reconciliation(root, sha)
            log = f"{sha}\0feat: published squash\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core(
                    "classify-window", "app", "missing")
        self.assertEqual(result.returncode, 4)
        self.assertIn("could not resolve exact published ref", result.stderr)
        self.assertIn("refs/remotes/origin/missing", result.stderr)

    def test_classify_window_cli_does_not_require_published_ref_without_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "consumer")
            os.makedirs(os.path.join(root, ".codearbiter"))
            self._git(root, "init", "--quiet", "--initial-branch=main")
            self._git(root, "config", "user.name", "release fixture")
            self._git(root, "config", "user.email", "release@example.invalid")
            targets = """<!-- release-targets -->
[app]
prefix: v
changelog: CHANGELOG.md
payload: .
<!-- /release-targets -->
"""
            with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                      "w", encoding="utf-8", newline="\n") as handle:
                handle.write(targets)
            log = "a" * 40 + "\0feat: ordinary change\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "minor")
        self.assertIn("[NEEDS-TRIAGE] " + "a" * 7, result.stdout)
        self.assertEqual(result.stderr, "")

    def test_wrong_target_and_out_of_window_entries_remain_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, historical_sha = self._reconciliation_repo(tmp)
            self._git(root, "switch", "--quiet", "-c", "candidate")
            with open(os.path.join(root, "payload.txt"), "a", encoding="utf-8") as handle:
                handle.write("candidate\n")
            self._git(root, "add", "payload.txt")
            self._git(root, "commit", "--quiet", "-m", "fix: current candidate")
            candidate_sha = self._git(root, "rev-parse", "HEAD").stdout.decode().strip()
            self._git(root, "switch", "--quiet", "main")
            ledger = {
                "schema_version": 1,
                "entries": [
                    {"target": "app", "commit_sha": historical_sha,
                     "changelog": "Historical note.", "reason": "Prior defect.",
                     "authorization": "Maintainer approved."},
                    {"target": "other", "commit_sha": candidate_sha,
                     "changelog": "Wrong target note.", "reason": "Other series.",
                     "authorization": "Other maintainer."},
                ],
            }
            with open(os.path.join(root, ".codearbiter", "reconciliations.json"),
                      "w", encoding="utf-8", newline="\n") as handle:
                json.dump(ledger, handle)
                handle.write("\n")
            self._publish_ledger_commit(root)
            log = f"{candidate_sha}\0fix: current candidate\0\0\n"
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}), \
                    mock.patch("sys.stdin", io.StringIO(log)):
                result = self._run_core("classify-window", "app", "main")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "patch")
        self.assertIn("[NEEDS-TRIAGE] " + candidate_sha[:7], result.stdout)
        self.assertNotIn("[RECONCILED]", result.stdout)

    def test_existing_footer_takes_precedence_over_reconciliation_text(self):
        sha = "e" * 40
        window = core_releaselib.classify_window(
            [{"sha": sha, "subject": "fix: complete",
              "body": "CHANGELOG: Authored footer."}],
            reconciliations={sha: "Ledger text must remain inert."},
            published_shas={sha})
        self.assertTrue(window["commits"][0]["has_changelog_footer"])
        self.assertFalse(window["commits"][0]["footer_reconciled"])
        self.assertEqual(
            window["commits"][0]["changelog"], "Authored footer.")

    def test_reconciliation_path_is_a_provenance_trigger(self):
        rows = core_releaselib.parse_release_targets("""<!-- release-targets -->
[app]
prefix: v
changelog: CHANGELOG.md
payload: .
changelog-reconciliations: .codearbiter/reconciliations.json
<!-- /release-targets -->
""")
        self.assertIn(
            ".codearbiter/reconciliations.json",
            core_releaselib.provenance_trigger_paths(rows))

    def test_reconciliation_path_must_be_one_repository_relative_file(self):
        for value in ("../escape.json", "/absolute.json", ".", "a/../../escape"):
            with self.subTest(value=value), \
                    self.assertRaises(core_releaselib.ReleaseTargetsError):
                core_releaselib.parse_release_targets(
                    "<!-- release-targets -->\n[app]\nprefix: v\n"
                    "changelog: CHANGELOG.md\npayload: .\n"
                    f"changelog-reconciliations: {value}\n"
                    "<!-- /release-targets -->\n")

    def test_writable_release_surfaces_must_stay_inside_the_repository(self):
        cases = (
            ("manifest", "../../outside/package.json"),
            ("generated-manifest", "../generated.json"),
            ("changelog", "C:/outside/CHANGELOG.md"),
            ("artifact", "../../outside/bundle.js"),
            ("provenance-manifest", "../published-tags.json"),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value), \
                    self.assertRaises(core_releaselib.ReleaseTargetsError):
                core_releaselib.parse_release_targets(
                    "<!-- release-targets -->\n[app]\nprefix: v\n"
                    "changelog: CHANGELOG.md\npayload: .\n"
                    f"{key}: {value}\n<!-- /release-targets -->\n")

    def test_parse_window_log_round_trips_the_prescribed_format(self):
        text = ("a" * 40 + "\0feat: one\0CHANGELOG: first\n\0\n"
                + "b" * 40 + "\0fix: two\0\0\n")
        entries = core_releaselib.parse_window_log(text)
        self.assertEqual([e["sha"] for e in entries], ["a" * 40, "b" * 40])
        self.assertEqual(entries[0]["subject"], "feat: one")
        self.assertIn("CHANGELOG: first", entries[0]["body"])

    def test_parse_window_log_does_not_treat_body_delimiters_as_records(self):
        text = ("a" * 40 + "\0feat(api): change protocol\0"
                "CHANGELOG: Change protocol\n----\n"
                "BREAKING CHANGE: incompatible protocol\0\n")
        entries = core_releaselib.parse_window_log(text)
        self.assertEqual(len(entries), 1)
        self.assertIn("----", entries[0]["body"])
        self.assertIn("BREAKING CHANGE:", entries[0]["body"])
        self.assertEqual(core_releaselib.classify_window(entries)["bump"], "major")

    def test_classify_window_cli_exit_codes_discriminate(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def run(text):
            return subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
                input=text, capture_output=True, text=True, env=env)

        clean = run("a" * 40 + "\0feat: one\0CHANGELOG: first\0\n")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stdout.splitlines()[0], "minor")
        classified_line = next(
            line for line in clean.stdout.splitlines()
            if line.startswith("[CLASSIFIED] "))
        classified = json.loads(classified_line.removeprefix("[CLASSIFIED] "))
        self.assertEqual(classified["sha"], "a" * 40)
        self.assertEqual(classified["type"], "feat")
        self.assertEqual(classified["bump"], "minor")
        self.assertFalse(classified["breaking"])
        self.assertEqual(classified["changelog"], "first")

        blocked = run("b" * 40 + "\0feat: one\0\0\n")
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("[NEEDS-TRIAGE] bbbbbbb feat: one", blocked.stdout)

        nonbumping = run("c" * 40 + "\0docs: prose\0\0\n")
        self.assertEqual(nonbumping.returncode, 2, nonbumping.stderr)
        self.assertEqual(nonbumping.stdout.splitlines()[0], "none")

        for malformed in ("", "a" * 40 + "\0fix: truncated",
                          "not-a-git-object\0feat: x\0CHANGELOG: x\0\n"):
            with self.subTest(malformed=repr(malformed)):
                failed = run(malformed)
                self.assertEqual(failed.returncode, 4, failed.stderr)
                self.assertIn("malformed NUL-framed", failed.stderr)

    def test_classify_window_executable_boundary_forces_utf8(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="cp1252")
        payload = ("a" * 40 + "\0feat: support café\0"
                   "CHANGELOG: Support café users\0\n").encode("utf-8")
        result = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
            input=payload, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        output = result.stdout.decode("utf-8")
        classified_line = next(
            line for line in output.splitlines()
            if line.startswith("[CLASSIFIED] "))
        classified = json.loads(classified_line.removeprefix("[CLASSIFIED] "))
        self.assertEqual(classified["subject"], "feat: support café")
        self.assertEqual(classified["changelog"], "Support café users")

    def test_classify_window_rejects_non_utf8_without_a_traceback(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        payload = b"a" * 40 + b"\0feat: invalid \xff\0CHANGELOG: bad\0\n"
        result = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
            input=payload, capture_output=True, env=env)
        stderr = result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 4, stderr)
        self.assertIn("not UTF-8", stderr)
        self.assertNotIn("Traceback", stderr)

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

    def test_zero_tag_manifest_adoption_window_derives_first_release_above_manifest(self):
        """Run 30 HIGH-1: an ordinary 0.1.0 manifest is a valid first-tag base.

        The user's explicit never-published choice is a prose authority gate;
        this fixture proves the mechanical path that choice unlocks: zero tags,
        a confirmed adoption boundary, one footer-complete feature, and a
        version derived strictly above the manifest rather than a dead-end STOP.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"],
                           check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email",
                            "test@example.invalid"], check=True)
            (repo / "README.md").write_text("before adoption\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "chore: seed"],
                           check=True)

            state = repo / ".codearbiter"
            state.mkdir()
            (state / "CONTEXT.md").write_text("default branch: main\n", encoding="utf-8")
            (state / "release-targets.md").write_text("adopted\n", encoding="utf-8")
            (repo / "manifest.json").write_text('{"version":"0.1.0"}\n',
                                                encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", ".codearbiter",
                            "manifest.json"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm",
                            "chore: adopt release lane"], check=True)
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "feature.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "feat: first", "-m",
                            "CHANGELOG: first governed feature"], check=True)

            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(repo), "tag", "-l"], text=True), "")
            additions = subprocess.check_output(
                ["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%H", "--",
                 ".codearbiter/CONTEXT.md", ".codearbiter/release-targets.md"],
                text=True)
            adopted = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "adoption-commit"],
                input=additions, capture_output=True, text=True, check=True).stdout.strip()
            window = f"{adopted}^..HEAD"
            log = subprocess.check_output(
                ["git", "-C", str(repo), "log", window,
                 "--format=%H%x00%s%x00%b%x00", "--", "."], text=True)
            classified = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
                input=log, capture_output=True, text=True)
            self.assertEqual(classified.returncode, 0, classified.stderr)
            self.assertEqual(classified.stdout.splitlines()[0], "minor")
            derived = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "derive-version", "0.1.0",
                 "minor", "semver", ""], capture_output=True, text=True, check=True)
            self.assertEqual(derived.stdout.strip(), "0.2.0")

    def test_adoption_commit_cli_two_file_pathspec_prints_the_oldest_addition(self):
        # #585 (2a): the Back-fill lane's own first release floors the
        # window from BOTH candidate adoption files (CONTEXT.md and
        # release-targets.md), fed to `adoption-commit` as ONE combined
        # `git log --diff-filter=A --format=%H -- CONTEXT.md release-
        # targets.md` pipeline. This function does not care how many
        # pathspecs produced its stdin -- it always takes the LAST line,
        # since `git log` prints newest-first -- so a synthetic two-file
        # addition history (interleaved, as a real multi-pathspec `git
        # log` would emit) must still resolve to the OLDEST line.
        # `test_first_release_baseline_takes_the_EARLIEST_of_several`
        # above already pins this at the function level with a bare
        # two-line fixture; this extends the same proof to the actual CLI
        # entry point with a shape that looks like real two-file output.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        # Newest-first, as `git log` emits: the release-targets.md
        # addition (newer, e.g. a Back-fill run today) came after the
        # CONTEXT.md addition (older, e.g. full onboarding months ago).
        two_file_log = "bbbbbbb\naaaaaaa\n"
        proc = subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "adoption-commit"],
            input=two_file_log, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "aaaaaaa")

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

    # ---- #584 MEDIUM-1: the tree-state probe exempts the audit scratch ----
    def _pretag_repo_with_gate_log(self, tmp, commands, payload="src/"):
        """Like `_pretag_repo`, but with `.codearbiter/gate-events.log`
        created and COMMITTED up front, so a declared command that appends
        to it mid-window is appending to a TRACKED file -- the shape the
        hooks actually produce, not an untracked one."""
        root = os.path.join(tmp, "consumer")
        os.makedirs(os.path.join(root, ".codearbiter"))
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"version": "1.0.0"}\n')
        with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
            fh.write("# Changelog\n")
        with open(os.path.join(root, ".codearbiter", "gate-events.log"), "w") as fh:
            fh.write("existing-line\n")
        with open(os.path.join(root, ".codearbiter", "release-targets.md"), "w") as fh:
            fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                     f"changelog: CHANGELOG.md\npayload: {payload}\n"
                     + "".join(f"pre-tag: {c}\n" for c in commands)
                     + "<!-- /release-targets -->\n")
        env = dict(os.environ,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        base = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=",
                "-c", "init.defaultBranch=main"]
        for argv in (["init", "-q"],
                     ["add", "package.json", "CHANGELOG.md",
                      ".codearbiter/release-targets.md",
                      ".codearbiter/gate-events.log"],
                     ["commit", "-q", "-m", "init", "--no-verify"]):
            proc = subprocess.run(base + argv, cwd=root, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(
                proc.returncode, 0,
                f"fixture git {argv[0]} failed: {proc.stderr.strip()}")
        return root

    def test_run_pre_tag_exempts_a_mid_window_gate_events_log_append(self):
        # #584 MEDIUM-1: the hooks append to `.codearbiter/gate-events.log`
        # on essentially every command, INCLUDING the commands this lane
        # runs -- so a pre-tag command that (like a real hook append)
        # writes to the log between the baseline probe and the
        # post-command probe must not read as a mutation. Before the fix,
        # this exact shape returned exit 6, whose stated remedy is "fix the
        # declaration or remove the row entry" -- deleting a release gate
        # over a blameless audit-log append.
        appender = (f'"{sys.executable}" -c '
                    '"open(\'.codearbiter/gate-events.log\',\'a\')'
                    '.write(chr(10))"')
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo_with_gate_log(tmp, [appender])
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_run_pre_tag_does_not_exempt_a_declared_payload_surface(self):
        appender = (f'"{sys.executable}" -c '
                    '"open(\'.codearbiter/gate-events.log\',\'a\')'
                    '.write(chr(10))"')
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo_with_gate_log(
                tmp, [appender], payload=".")
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn(".codearbiter/gate-events.log", proc.stderr)

    def test_clean_tree_status_applies_the_same_target_aware_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            unrelated = self._pretag_repo_with_gate_log(tmp, [], payload="src/")
            with open(os.path.join(unrelated, ".codearbiter", "gate-events.log"),
                      "a") as fh:
                fh.write("scratch\n")
            excluded = self._run_clean_tree_status(unrelated)
            self.assertEqual(excluded.returncode, 0, excluded.stderr)
            self.assertEqual(excluded.stdout, "")

        with tempfile.TemporaryDirectory() as tmp:
            declared = self._pretag_repo_with_gate_log(tmp, [], payload=".")
            with open(os.path.join(declared, ".codearbiter", "gate-events.log"),
                      "a") as fh:
                fh.write("release-surface\n")
            visible = self._run_clean_tree_status(declared)
            self.assertEqual(visible.returncode, 0, visible.stderr)
            self.assertIn(".codearbiter/gate-events.log", visible.stdout)

    def test_clean_tree_status_applies_target_aware_marker_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            unrelated = self._pretag_repo_with_gate_log(tmp, [], payload="src/")
            markers = os.path.join(unrelated, ".codearbiter", ".markers")
            os.makedirs(markers)
            with open(os.path.join(markers, "proof"), "w") as fh:
                fh.write("scratch\n")
            excluded = self._run_clean_tree_status(unrelated)
            self.assertEqual(excluded.returncode, 0, excluded.stderr)
            self.assertEqual(excluded.stdout, "")

        with tempfile.TemporaryDirectory() as tmp:
            declared = self._pretag_repo_with_gate_log(tmp, [], payload=".")
            markers = os.path.join(declared, ".codearbiter", ".markers")
            os.makedirs(markers)
            with open(os.path.join(markers, "proof"), "w") as fh:
                fh.write("release-surface\n")
            visible = self._run_clean_tree_status(declared)
            self.assertEqual(visible.returncode, 0, visible.stderr)
            self.assertIn(".codearbiter/.markers/", visible.stdout)

    # ---- #583 MEDIUM-2 / #584 MEDIUM-3: PY exported to declared commands ----
    def test_run_pre_tag_exports_PY_to_declared_commands(self):
        check = ('python -c "import os,sys;'
                  'sys.exit(0 if os.environ.get(\'PY\') else 1)"')
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [check])
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    # ---- #585 MEDIUM-2 / #584 MEDIUM-1: could-not-run vs. drift ----
    def test_could_not_run_recognizes_only_the_documented_codes(self):
        # Platform-independent proof of the exit-code MAPPING itself
        # (distinct from the end-to-end test below, whose real-world
        # trigger is platform-dependent -- see that test's own docstring).
        for code in (126, 127, 9009):
            with self.subTest(code=code):
                self.assertTrue(core_releaselib._could_not_run(code))
        for code in (0, 1, 2, 5, 6, 8, 128, -1):
            with self.subTest(code=code):
                self.assertFalse(core_releaselib._could_not_run(code))

    def test_run_pre_tag_exits_7_when_a_declared_command_could_not_run(self):
        # A row's command exiting one of the documented could-not-run codes
        # (127: POSIX "command not found") must be diagnosed as "could not
        # run", never folded into exit 5's "ran and disagreed" (#585
        # MEDIUM-2 / #584 MEDIUM-1). Spelled as an explicit `sys.exit(127)`
        # rather than relying on a genuinely-missing PATH entry: a real
        # "not found" failure's exit code is platform-dependent -- POSIX
        # shells report 127, but `cmd.exe`'s own "not recognized" error was
        # MEASURED on a Windows 11 host to report 1, not one of the
        # documented could-not-run codes (a residual gap, noted in
        # `_could_not_run`'s own docstring) -- so this test pins the
        # DIAGNOSIS given a 127, which is the exact code the real-world
        # motivating case (a hardcoded `python3` absent from PATH) reports
        # on a POSIX host, portably across every platform this suite runs
        # on.
        cmd = f'"{sys.executable}" -c "import sys; sys.exit(127)"'
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [cmd])
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 7, proc.stdout + proc.stderr)
            self.assertIn("COULD NOT RUN", proc.stderr)
            self.assertIn("NOT drift", proc.stderr)

    # ---- #584 residual: exit 8, the probe itself failing ----
    def test_run_pre_tag_exits_8_when_the_tree_state_probe_fails(self):
        # A `_tree_state()` probe failure (here: CLAUDE_PROJECT_DIR points
        # at a directory that was never `git init`ed, so `git status`
        # itself exits non-zero) must be diagnosed as "the probe failed, no
        # verdict exists" -- exit 8 -- never exit 6, which names a
        # DECLARED COMMAND as the fault and tells the operator to fix or
        # remove the row. No command has even run yet on this path.
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "not-a-git-repo")
            os.makedirs(os.path.join(root, ".codearbiter"))
            with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                      "w") as fh:
                fh.write("<!-- release-targets -->\n[app]\nprefix: v\n"
                         "changelog: CHANGELOG.md\npayload: .\n"
                         "<!-- /release-targets -->\n")
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 8, proc.stdout + proc.stderr)
            self.assertIn("PROBE itself failed", proc.stderr)
            self.assertNotIn("MUTATED", proc.stderr)

    # ---- #602: Windows POSIX dispatch, resolved so `"$PY"` is portable ----
    def test_run_pre_tag_runs_a_dollar_PY_row_for_real(self):
        # House rule (dry-run the CALLER's actual path, never a mock): a row
        # spelled EXACTLY the #601 convention -- `"$PY" <script>` -- run
        # through the REAL `run-pre-tag` CLI subprocess on THIS host, with
        # nothing about the dispatch mocked anywhere in the path. Before
        # #602, this was measured to exit 1 on Windows (`'"$PY"' is not
        # recognized...` from `cmd.exe`) and be misdiagnosed as drift
        # (exit 5) rather than a missing interpreter; #602 makes it exit 0
        # everywhere this suite runs, POSIX or Windows alike.
        check = ('"$PY" checker.py ok')
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [check])
            with open(os.path.join(root, "checker.py"), "w") as fh:
                fh.write('import sys\n'
                         'sys.exit(0 if sys.argv[1:] == ["ok"] else 1)\n')
            proc = self._run_pre_tag(root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_run_pre_tag_exits_9_when_no_posix_shell_can_be_resolved(self):
        # A genuinely shell-less Windows host (or one whose `git` cannot
        # answer `--exec-path` and has no `bash` on PATH) must get a
        # DISTINCT "could not run" exit -- 9, never 7 or 5 -- before ANY
        # declared command is attempted, per the #585 house rule that
        # "could not run" is never folded into "ran and disagreed". Forced
        # by pointing the trusted git-executable seam at `sys.executable`
        # (which answers `--exec-path` with nothing usable) and stripping
        # PATH down to directories with no `bash.exe` at all -- the real
        # resolution algorithm runs against these REAL, if adverse, inputs;
        # nothing about `_resolve_posix_shell` itself is mocked.
        check = '"$PY" -c "pass"'
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [check])
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                       PYTHONDONTWRITEBYTECODE="1",
                       CODEARBITER_GIT_EXECUTABLE=sys.executable,
                       PATH=r"C:\Windows\System32;C:\Windows")
            proc = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "run-pre-tag", "app"],
                cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True)
            if os.name != "nt":
                self.skipTest(
                    "exit 9 is Windows-only: shell=True already dispatches "
                    "through a POSIX shell elsewhere, so `posix_shell` "
                    "resolution -- and its failure mode -- never triggers "
                    "off Windows (mirrors the existing exit-7 test's own "
                    "platform-dependence note)")
            self.assertEqual(proc.returncode, 9, proc.stdout + proc.stderr)
            self.assertIn("COULD NOT RUN", proc.stderr)
            self.assertIn("NOT drift", proc.stderr)
            self.assertIn("POSIX-compatible shell", proc.stderr)

    def test_run_pre_tag_skips_shell_resolution_for_a_row_with_no_pre_tag(self):
        # A row declaring NO `pre-tag` commands at all never needs a shell,
        # so resolution must never even be ATTEMPTED for it -- proven here
        # as a spy on the real in-process `main()` dispatch (not a
        # replacement of the behavior under test: git and the tree-state
        # probe run for real against a real fixture repo; only the call
        # COUNT on `_resolve_posix_shell` is observed). A subprocess-level
        # black-box equivalent cannot distinguish "skipped" from "attempted
        # and happened to succeed" without independently breaking git and
        # bash resolution in a way that does not itself confound the
        # tree-state probe -- this in-process spy is the precise instrument
        # for the specific claim being pinned.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pretag_repo(tmp, [])
            with mock.patch.object(
                    core_releaselib, "_resolve_posix_shell") as spy, \
                    mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}):
                exit_code = core_releaselib.main(["run-pre-tag", "app"])
            self.assertEqual(exit_code, 0)
            spy.assert_not_called()

    # ---- #585 MEDIUM-3: apply-bump mechanizes the version arithmetic ----
    def test_apply_bump_patch_minor_major(self):
        self.assertEqual(core_releaselib.apply_bump("2.3.4", "patch"), "2.3.5")
        self.assertEqual(core_releaselib.apply_bump("2.3.4", "minor"), "2.4.0")
        self.assertEqual(core_releaselib.apply_bump("2.3.4", "major"), "3.0.0")

    def test_apply_bump_refuses_none_and_nonsense_words(self):
        # `none` is a deliberate, explicit refusal -- not folded into the
        # generic "unrecognised word" case -- because a caller must NEVER
        # apply a non-bump; echoing `base` back unchanged would look like a
        # successful (if inert) bump rather than the caller's own bug.
        self.assertIsNone(core_releaselib.apply_bump("2.3.4", "none"))
        self.assertIsNone(core_releaselib.apply_bump("2.3.4", "nonsense"))

    def test_apply_bump_refuses_a_non_semver_base(self):
        self.assertIsNone(core_releaselib.apply_bump("not-a-version", "patch"))

    def test_apply_bump_cli_prints_exactly_the_version(self):
        for word, expected in (("patch", "2.3.5"), ("minor", "2.4.0"),
                               ("major", "3.0.0")):
            with self.subTest(word=word):
                out = self._run_core("apply-bump", "2.3.4", word)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout.strip(), expected)
                # stdout is EXACTLY the version -- no decoration, no label.
                self.assertEqual(out.stdout, expected + "\n")

    def test_apply_bump_cli_exits_2_on_none_nonsense_or_bad_base(self):
        for base, word in (("2.3.4", "none"), ("2.3.4", "nonsense"),
                           ("not-a-version", "patch")):
            with self.subTest(base=base, word=word):
                out = self._run_core("apply-bump", base, word)
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertEqual(out.stdout, "")

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
                     "dates-match", "semver-greater", "apply-bump", "classify",
                     "peel-tag", "backfill-detect"):
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


class AdoptionBoundaryBackfillFirstReleaseTest(unittest.TestCase):
    """R-05, AC-18 (T-23 round-1 finding HIGH-T23-1): Back-fill's own
    canonical first-release path resolves `$ADOPTED` to the `chore:
    declare release targets` commit it just committed in Back-fill step 3.
    That row's canonical shape always sets `payload-exclude: .codearbiter/`,
    so the declaration commit never itself carries payload content -- and
    being the newest commit in the repository at that moment, it makes
    `${ADOPTED}^..HEAD` a single-commit, payload-scoped-EMPTY range. Phase 1
    step 1's mandatory non-empty check then STOPs as "nothing to release" on
    the project's genuine first release, discarding its entire pre-existing
    feature history by default -- not a corner case, since Back-fill's own
    step 3 always ends by committing that declaration file immediately
    before Pre-flight re-enters.

    Reproduced here with real disposable git repositories, the same way
    T-23 did (never mocked): a fresh repo, one footer-complete pre-existing
    `feat` commit, then a synthetic Back-fill declaration commit touching
    ONLY `.codearbiter/release-targets.md`. Chosen fix shape: (b)+(c) --
    when step 1's payload-scoped check finds this exact shape empty, the
    DOCUMENTED DEFAULT it applies is `EFFECTIVE_WINDOW=HEAD` (the plan's
    own R-05 verification text: "the escape-hatch behavior... becomes the
    documented default for this exact shape, not an undocumented
    accident") -- but that default is still PRESENTED at the pre-existing
    confirm-or-replace gate, never applied silently, so an operator
    adopting deep into a long pre-existing history can still replace it
    with an explicit earlier SHA rather than pull the whole thing into
    step 3's footer-completeness check (the 500-commit-block failure
    `adoption-commit`'s own module docstring already guards against).
    `_releaselib.py` itself is untouched, and `$ADOPTED` still resolves
    to the payload-excluded declaration commit exactly as before -- this
    fix does NOT satisfy R-05's opening clause literally ("no longer
    resolves `$ADOPTED` to its own declaration commit"); it satisfies the
    row's second clause and intent instead (the full-history window
    becomes the documented default), deliberately keeping `adoption-
    commit`/`first_release_baseline` pure-over-text per this module's own
    stated design invariant and keeping the boundary's reported identity
    honest, and changes the WINDOW default at the point of use rather
    than the resolution. Non-regression for every non-Back-fill case is
    `test_zero_tag_manifest_adoption_window_derives_first_release_above_manifest`
    above, unmodified by this task: there, the adoption commit ALSO
    touches the payload (`manifest.json` lands in the same commit as
    `.codearbiter/`), so `$ADOPTED != HEAD`, the narrow `${ADOPTED}^..HEAD`
    window is already non-empty, and it still derives `0.2.0` -- this
    task's new default never engages on that path at all. This class's
    first three tests are pure mechanism reproductions of the underlying
    `adoption-commit`/`classify-window` CLI facts the prose fix reasons
    about; the remaining tests pin the new prose itself, prove it is not
    vacuously true, prove it is reachable BEFORE the STOP verdict it
    corrects (not a dead paragraph after it), prove `$ADOPTED` is never
    dereferenced unbound on a path where it was never assigned, and
    prove the pre-existing #570 root-commit / never-narrow-silently
    wording is untouched."""

    @staticmethod
    def _build_fixture(tmp):
        repo = Path(tmp) / "repo"
        subprocess.run(
            ["git", "init", "-q", "-b", "trunk", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "test"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True)
        (repo / "index.js").write_text(
            "module.exports = {};\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "index.js"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "feat: add index",
             "-m", "CHANGELOG: add index entrypoint"], check=True)

        state = repo / ".codearbiter"
        state.mkdir()
        (state / "release-targets.md").write_text(
            "<!-- release-targets -->\n"
            "[app]\n"
            "prefix: v\n"
            "manifest: package.json\n"
            "changelog: CHANGELOG.md\n"
            "payload: .\n"
            "payload-exclude: .codearbiter/\n"
            "<!-- /release-targets -->\n",
            encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", ".codearbiter/release-targets.md"],
            check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm",
             "chore: declare release targets"], check=True)
        return repo

    @staticmethod
    def _adoption_commit(repo):
        additions = subprocess.check_output(
            ["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%H", "--",
             ".codearbiter/CONTEXT.md", ".codearbiter/release-targets.md"],
            text=True)
        return subprocess.run(
            [sys.executable, _CORE_RELEASELIB_PATH, "adoption-commit"],
            input=additions, capture_output=True, text=True, check=True).stdout.strip()

    # ---- mechanism reproduction (real disposable git, never mocked) ----

    def test_adopted_resolves_to_the_just_committed_declaration_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._build_fixture(tmp)
            self.assertEqual(subprocess.check_output(
                ["git", "-C", str(repo), "tag", "-l"], text=True), "")
            adopted = self._adoption_commit(repo)
            head = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            self.assertEqual(
                adopted, head,
                "the adoption boundary must resolve to Back-fill's own "
                "just-committed declaration commit on this canonical "
                "shape -- if this fails, the fixture no longer matches "
                "HIGH-T23-1's precondition")

    def test_declaration_commits_own_payload_scoped_window_is_empty(self):
        # The mechanical bug itself: `${ADOPTED}^..HEAD`, payload-scoped,
        # prints nothing -- Phase 1 step 1's "nothing to release" STOP
        # fires here on the project's genuine first release.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._build_fixture(tmp)
            adopted = self._adoption_commit(repo)
            window = f"{adopted}^..HEAD"
            log = subprocess.check_output(
                ["git", "-C", str(repo), "log", window, "--format=%H", "--", ".",
                 ":(exclude).codearbiter/"], text=True)
            self.assertEqual(
                log, "",
                "HIGH-T23-1 did not reproduce: the payload-scoped window "
                "rooted at the declaration commit is expected to be empty")

    def test_documented_remedy_effective_window_head_recovers_full_history(self):
        # Step 0's now-documented DEFAULT for this exact shape --
        # `EFFECTIVE_WINDOW=HEAD` (the SAME value the pre-existing
        # root-commit branch already uses) -- extracted from the prose
        # itself (never hand-chosen) and run end-to-end, closing the gap
        # T-23's own report named (it verified the two halves of this
        # fact separately -- root-commit-has-no-parent, and a standalone
        # `classify-window` run -- but never composed them into one
        # command the way an operator actually would).
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        idx = text.index("documented default is to propose")
        window = text[idx: idx + 60]
        self.assertIn("EFFECTIVE_WINDOW=HEAD", window)

        with tempfile.TemporaryDirectory() as tmp:
            repo = self._build_fixture(tmp)
            log = subprocess.check_output(
                ["git", "-C", str(repo), "log", "HEAD",
                 "--format=%H%x00%s%x00%b%x00", "--", ".",
                 ":(exclude).codearbiter/"], text=True)
            self.assertNotEqual(log.strip(), "")
            classified = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "classify-window"],
                input=log, capture_output=True, text=True)
            self.assertEqual(classified.returncode, 0, classified.stderr)
            self.assertEqual(classified.stdout.splitlines()[0], "minor")

    def test_backfill_route_reconciles_real_pre_footer_published_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            subprocess.run(
                ["git", "init", "-q", "-b", "trunk", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "test"],
                check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email",
                 "test@example.invalid"], check=True)
            (repo / "package.json").write_text(
                '{"name":"legacy","version":"0.1.0"}\n', encoding="utf-8")
            (repo / "CHANGELOG.md").write_text(
                "# Changelog\n", encoding="utf-8")
            (repo / "index.js").write_text("legacy();\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm",
                 "feat: legacy published feature"], check=True)
            legacy_sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True).strip()

            state = repo / ".codearbiter"
            state.mkdir()
            row = core_releaselib.detect_candidate_target(
                ["package.json"], ["CHANGELOG.md"])
            (state / "release-targets.md").write_text(
                core_releaselib.format_release_targets_block(row),
                encoding="utf-8")
            ledger = {
                "schema_version": 1,
                "entries": [{
                    "target": "app",
                    "commit_sha": legacy_sha,
                    "changelog": "Document the legacy published feature.",
                    "reason": "The commit predates the changelog-footer policy.",
                    "authorization": "Maintainer approved during Back-fill.",
                }],
            }
            (state / "release-changelog-reconciliations.json").write_text(
                json.dumps(ledger) + "\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", ".codearbiter"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm",
                 "chore: declare release targets and changelog reconciliation"],
                check=True)
            published = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True).strip()
            subprocess.run(
                ["git", "-C", str(repo), "update-ref",
                 "refs/remotes/origin/trunk", published], check=True)
            log = subprocess.check_output(
                ["git", "-C", str(repo), "log", "HEAD",
                 "--format=%H%x00%s%x00%b%x00", "--", ".",
                 ":(exclude).codearbiter/"], text=True)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
            classified = subprocess.run(
                [sys.executable, _CORE_RELEASELIB_PATH, "classify-window",
                 "app", "trunk"], input=log, capture_output=True, text=True,
                env=env)
            self.assertEqual(classified.returncode, 0, classified.stderr)
            self.assertIn("[RECONCILED]", classified.stdout)
            self.assertNotIn("[NEEDS-TRIAGE]", classified.stdout)

    # ---- SKILL.md prose: the documented default this task adds ----

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.phase1 = cls.text[
            cls.text.index("## Phase 1"): cls.text.index("## Phase 2")]

    def test_step_0_names_the_backfill_canonical_shape_and_its_cause(self):
        start = self.phase1.index("On Back-fill's own canonical first-release path")
        end = self.phase1.index("\n1. Reload", start)
        window = self.phase1[start:end]
        self.assertIn("excluded `.codearbiter/` state", window)
        self.assertIn("ORDINARY outcome", window)
        for method in ("fast-forward", "squash", "normal merge"):
            self.assertIn(method, window)
        self.assertIn("never applied silently", window)

    def test_step_0_makes_the_widen_the_documented_default_but_still_confirmed(self):
        # The plan's own R-05 verification text: the escape-hatch behavior
        # "becomes the documented default for this exact shape" -- but
        # `never applied silently` (per "never narrow silently"'s own
        # sibling discipline): it is PRESENTED at the pre-existing
        # confirm-or-replace gate, guarding against the 500-commit-block
        # failure `adoption-commit`'s own module docstring already names.
        idx = self.phase1.index(
            "On Back-fill's own canonical first-release path")
        window = self.phase1[idx:idx + 1500]
        self.assertIn("documented default is to propose", window)
        self.assertIn("EFFECTIVE_WINDOW=HEAD", window)
        self.assertIn(
            "presented for the operator's confirm-or-replace choice", window)
        self.assertIn("never applied silently", window)
        self.assertIn("500-line", window)

    def test_step_1_checks_the_default_shape_BEFORE_the_stop_verdict(self):
        start = self.phase1.index("Before treating empty output here as a genuine STOP")
        end = self.phase1.index("\n2. ", start)
        decision = self.phase1[start:end]
        self.assertIn('merge-base --is-ancestor -- "$ADOPTED" HEAD', decision)
        self.assertIn('"$EFFECTIVE_WINDOW" != "HEAD"', decision)
        self.assertIn("confirm-first-release-window", decision)
        self.assertNotIn('[ "${ADOPTED:-}" =', decision)
        invocation = decision.index('WINDOW_STATE=$(release_window_state "$@") || exit "$?"')
        stop = decision.index("STOPs as nothing to release for `$TARGET`")
        self.assertLess(invocation, stop)

    def test_step_1_guards_ADOPTED_against_unbound_variable_on_non_backfill_paths(self):
        function = self._documented_window_function()
        self.assertIn('[ "$LAST_TAG" = "<none>" ] && [ -n "${ADOPTED:-}" ]', function)
        self.assertNotIn('[ -n "$ADOPTED" ]', function)

    def test_step_1_shape_check_executes_under_pipefail_with_ADOPTED_unset(self):
        # Execute the current source definition, not a transcription of the old
        # ADOPTED==HEAD rule. Neither tagged nor zero-tag empty history can
        # propose widening when there is no confirmed adoption boundary.
        bash = (core_releaselib._resolve_posix_shell()
                if os.name == "nt" else working_bash())
        if bash is None:
            self.skipTest("no working POSIX shell")
        script = ('set -euo pipefail\n'
                  'LAST_TAG="$1"\nPROJECT_ROOT="$2"\nEFFECTIVE_WINDOW=HEAD\n'
                  'unset ADOPTED\n' + self._documented_window_function() +
                  '\nrelease_window_state absent-payload/\n')
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._build_fixture(tmp)
            for last_tag in ("v1.2.3", "<none>"):
                with self.subTest(last_tag=last_tag):
                    result = subprocess.run(
                        [bash, "-s", "--", last_tag, Path(repo).as_posix()],
                        input=script.encode(), capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0,
                                     (result.stdout + result.stderr).decode(errors="replace"))
                    self.assertEqual(result.stdout.decode().strip(), "empty")

    def _documented_window_function(self):
        matches = re.findall(
            r"(?ms)^   release_window_state\(\) \(\n.*?^   \)\n", self.phase1)
        self.assertEqual(len(matches), 1, "one executable window decision must own the rule")
        return "\n".join(line[3:] for line in matches[0].splitlines()) + "\n"

    def test_a_mutated_copy_missing_the_new_default_is_detected(self):
        # Mutation-kill: deleting the new sentence must make the prose
        # tests above fail, proving they are not vacuously true.
        idx = self.phase1.index(
            "On Back-fill's own canonical first-release path")
        end = self.phase1.index("\n1. Reload", idx)
        mutant = self.phase1[:idx] + self.phase1[end:]
        self.assertNotIn("ORDINARY outcome", mutant)
        self.assertNotIn("documented default is to propose", mutant)

    def test_step_3_names_the_step_1_widen_as_its_sole_sanctioned_exception(self):
        # Step 3's own pre-existing sentence ("step 0 has already proposed
        # and confirmed the adoption floor before classification; do not
        # classify the raw full-history $WINDOW first and then try to
        # narrow it here") reads as a contradiction once step 1 can
        # legitimately substitute a full-HEAD window AFTER step 0 ran --
        # a literal executor could read step 3 as forbidding exactly the
        # shape this task's fix introduces. One reconciling clause closes
        # that gap: the step-1 substitution is a CONFIRMED widen at its
        # own documented point of use, not an unconfirmed narrowing
        # performed at step 3 -- the thing step 3's original sentence
        # actually guards against.
        idx = self.phase1.index(
            "do not classify the raw full-history `$WINDOW` first and "
            "then try to narrow it here.")
        window = self.phase1[idx:idx + 500]
        self.assertIn("sole sanctioned exception", window)
        self.assertIn("Back-fill's own canonical first-release shape", window)
        self.assertIn("confirm-or-replace gate", window)
        self.assertIn("not an unconfirmed narrowing performed HERE", window)
        # The pre-existing sentence itself survives byte-for-byte --
        # reconciled by ADDING a clause, never by rewriting the original.
        self.assertIn(
            "On a first release, step 0 has already proposed and "
            "confirmed the adoption floor before classification; do not "
            "classify the raw full-history `$WINDOW` first and then try "
            "to narrow it here.", self.phase1)

    def test_root_commit_escape_hatch_wording_is_unchanged(self):
        # Non-regression: the pre-existing #570 root-commit rule this fix
        # sits next to survives byte-for-byte.
        self.assertIn(
            "when `$ADOPTED` is the root commit and has no parent, use "
            "`EFFECTIVE_WINDOW=HEAD`.", self.phase1)

    def test_never_narrow_silently_and_confirmation_gate_wording_is_unchanged(self):
        self.assertIn("never narrow silently", self.phase1)
        self.assertIn(
            "present `$ADOPTED` as the proposed baseline and require the "
            "user's confirmation or explicit replacement", self.phase1)


class BreakingClassificationTest(unittest.TestCase):
    """T-14, AC-12 (spec P7). `classify_commit`/`classify_window` already
    COMPUTE breaking status -- the `!` bang (both spellings) and a
    `BREAKING CHANGE:`/`BREAKING-CHANGE:` footer -- as part of their
    existing Conventional-Commits classification (core/pysrc/_releaselib.py
    lines 1400-1490). This class proves that data is correct and reusable
    as-is; it adds no production code and no second parser. T-15's
    composition step depends on exactly what this class pins: the
    per-commit `breaking` flag surviving unchanged into `classify_window`'s
    `commits` rows, in window order, so a "prefer the first breaking entry"
    scan (`next(r for r in commits if r["breaking"])`) is possible without
    re-deriving anything, and the aggregate `bump` is unaffected by
    surfacing that flag.
    """

    def test_bang_without_a_scope_is_breaking(self):
        verdict = core_releaselib.classify_commit(
            "feat!: drop the legacy endpoint")
        self.assertTrue(verdict["breaking"])
        self.assertEqual(verdict["bump"], "major")

    def test_bang_after_a_scope_is_breaking(self):
        verdict = core_releaselib.classify_commit(
            "feat(api)!: drop the legacy endpoint")
        self.assertTrue(verdict["breaking"])
        self.assertEqual(verdict["bump"], "major")

    def test_bare_breaking_change_footer_is_breaking_regardless_of_type(self):
        # No `!` anywhere -- the footer alone must set breaking=True, on
        # any Conventional-Commits type, including one with no configured
        # bump of its own (docs/chore).
        for subject, body in (
                ("docs: prose", "BREAKING CHANGE: config moved"),
                ("chore: routine", "BREAKING CHANGE: config moved"),
                # hyphenated spelling: _BREAKING_FOOTER_RE's own comment
                # (core/pysrc/_releaselib.py:1195) calls it spec-permitted.
                ("fix: patch", "BREAKING-CHANGE: config moved"),
        ):
            with self.subTest(subject=subject, body=body):
                verdict = core_releaselib.classify_commit(subject, body)
                self.assertTrue(verdict["breaking"])
                self.assertEqual(verdict["bump"], "major")

    def test_footer_must_start_a_line_not_merely_appear_in_prose(self):
        verdict = core_releaselib.classify_commit(
            "docs: prose", "this mentions a BREAKING CHANGE: inline")
        self.assertFalse(verdict["breaking"])
        self.assertEqual(verdict["bump"], "none")

    def test_ordinary_commits_are_not_breaking(self):
        for subject in ("feat(api): add a thing", "fix: a bug",
                         "perf: faster", "docs: prose", "chore: routine"):
            with self.subTest(subject=subject):
                verdict = core_releaselib.classify_commit(subject)
                self.assertFalse(verdict["breaking"])

    def test_window_rows_carry_the_same_per_commit_breaking_flag(self):
        # The exact seam T-15's composition step depends on: classify_window
        # must not drop or recompute `breaking` when it builds each row.
        commits = [
            {"sha": "a" * 40, "subject": "feat!: drop it", "body": ""},
            {"sha": "b" * 40, "subject": "fix: patch", "body": ""},
        ]
        window = core_releaselib.classify_window(commits)
        rows_by_sha = {row["sha"]: row for row in window["commits"]}
        self.assertTrue(rows_by_sha["a" * 40]["breaking"])
        self.assertFalse(rows_by_sha["b" * 40]["breaking"])

    def test_window_preserves_input_order_so_first_breaking_entry_is_findable(self):
        # T-15's headline rule is "prefer the FIRST breaking entry" -- this
        # only works if classify_window never reorders `commits`.
        commits = [
            {"sha": "1" * 40, "subject": "fix: a", "body": ""},
            {"sha": "2" * 40, "subject": "feat!: first breaking", "body": ""},
            {"sha": "3" * 40, "subject": "feat(api)!: second breaking",
             "body": ""},
        ]
        window = core_releaselib.classify_window(commits)
        first_breaking = next(
            (row for row in window["commits"] if row["breaking"]), None)
        self.assertIsNotNone(first_breaking)
        self.assertEqual(first_breaking["sha"], "2" * 40)

    def test_aggregate_window_bump_is_unaffected_by_breaking_visibility(self):
        # AC-12 / this task: exposing `breaking` must not change the
        # aggregate bump classify_window already computed correctly.
        major_window = core_releaselib.classify_window([
            {"sha": "a" * 40, "subject": "fix: a", "body": ""},
            {"sha": "b" * 40, "subject": "feat!: b", "body": ""},
        ])
        self.assertEqual(major_window["bump"], "major")

        minor_window = core_releaselib.classify_window([
            {"sha": "a" * 40, "subject": "feat: a", "body": ""},
            {"sha": "b" * 40, "subject": "fix: b", "body": ""},
        ])
        self.assertEqual(minor_window["bump"], "minor")
        # a breaking sibling elsewhere in the window must not relabel this
        # row's own non-breaking bump/breaking values
        self.assertEqual(minor_window["commits"][0]["bump"], "minor")
        self.assertFalse(minor_window["commits"][0]["breaking"])
        self.assertEqual(minor_window["commits"][1]["bump"], "patch")
        self.assertFalse(minor_window["commits"][1]["breaking"])

        none_window = core_releaselib.classify_window([
            {"sha": "a" * 40, "subject": "docs: a", "body": ""},
            {"sha": "b" * 40, "subject": "chore: b", "body": ""},
        ])
        self.assertEqual(none_window["bump"], "none")


def _prose_select_headline_commit(rows, bump):
    """Test-only mirror of SKILL.md's `<summary>` derivation rule (Phase 3
    step 2's title-convention paragraph), used only to PROVE the documented
    selection is correct against `classify_window` fixtures -- it consumes
    the `breaking`/`type` fields `classify_window` already computes and
    detects nothing itself. Not production code; T-15's actual change is
    the SKILL.md prose this function is a literal transcription of.
    """
    if bump == "major":
        return next((r for r in rows if r["breaking"]), None)
    if bump == "minor":
        return next((r for r in rows if r["type"] == "feat"), None)
    return next((r for r in rows if r["type"] == "fix"), None)


class BreakingHeadlineTest(unittest.TestCase):
    """T-15, AC-12 (spec P7). Two obligations:

    1. Composed release notes (changelog section / tag message / Release
       notes -- one composed text reused across all three, per SKILL.md's
       own step-5 cross-boundary rule) group a breaking commit under an
       explicit `### Breaking` heading instead of its ordinary type group,
       reusing `classify_window`'s existing `breaking` field.
    2. The `<summary>` title rule gets an explicit `major` branch: a
       major-bump window's title is the first BREAKING entry, not the
       first `Added` entry the old minor-branch fallback would wrongly
       reach via `else`.

    This class proves both against the actual rendered `core/surface/
    skills/release/SKILL.md` prose (structural) and against real
    `classify_window` output (fixture, via `_prose_select_headline_commit`,
    a literal transcription of that prose -- never a second breaking
    parser). No production compose function exists in this lane: grouping
    and title selection are agent-executed SKILL.md steps, the same as
    every other `SkillPortabilityTest`/`SkillProseTest` obligation in this
    file, which is why the proving tests here are structural + fixture
    rather than a direct unit test of new library code.
    """

    # -- structural: the composed-notes prose ------------------------------

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_step5_names_an_explicit_breaking_group(self):
        idx = self.text.index("grouped Added (`feat`) / Fixed (`fix`)")
        window = self.text[idx:idx + 1400]
        self.assertIn("### Breaking", window)
        # Keyed on the classification flag, not on a type spelling -- a
        # `chore!:` (no type group of its own) must still be named as
        # getting a group, proving this isn't "feat! is special Added".
        self.assertIn("`breaking` true", window)
        self.assertIn("chore!", window)
        self.assertIn("classify-window", window)

    def test_step5_breaking_group_never_duplicates_into_the_type_group(self):
        idx = self.text.index("### Breaking` group instead of its type group")
        window = self.text[idx:idx + 500]
        self.assertIn("never also duplicated into its type group", window)
        self.assertIn("never placed in `### Breaking`", window)

    def test_step5_breaking_group_is_the_one_composed_text_all_three_surfaces_reuse(self):
        idx = self.text.index("### Breaking` group instead of its type group")
        window = self.text[idx:idx + 700]
        self.assertIn("<message-file>", window)
        self.assertIn("<Phase-1 section file>", window)

    # -- structural: the <summary> title rule -------------------------------

    def test_summary_rule_has_an_explicit_major_branch(self):
        self.assertIn(
            "the first bullet under `### Breaking` if the window bumped "
            "major, the first bullet under `### Added` if the window "
            "bumped minor, otherwise the first bullet under `### Fixed`, "
            "else the first bullet of the first non-empty group",
            self.text,
            "the major branch must sit ahead of the untouched minor/else "
            "fallback, byte-identical past the new clause")

    def test_summary_rule_title_convention_phrase_is_unchanged(self):
        # M-1's own pinned assertion (SkillPortabilityTest) must still hold
        # -- this task must not touch the title-convention sentence itself.
        self.assertIn(
            "The title convention is `<$DISPLAY_NAME> ${VERSION}: "
            "<summary>`", self.text)

    # -- fixture: a real major-bump window picks the first breaking entry --

    def test_major_window_headline_is_the_first_breaking_entry(self):
        window = core_releaselib.classify_window([
            {"sha": "1" * 40, "subject": "fix: a small bug", "body": ""},
            {"sha": "2" * 40, "subject": "feat!: drop the legacy endpoint",
             "body": ""},
            {"sha": "3" * 40, "subject": "feat(api)!: remove old flag",
             "body": ""},
        ])
        self.assertEqual(window["bump"], "major")
        headline = _prose_select_headline_commit(window["commits"], window["bump"])
        self.assertIsNotNone(headline)
        self.assertEqual(headline["sha"], "2" * 40)
        # authored text is unchanged -- the same subject text classify_commit
        # was given comes back verbatim, never reworded by this selection.
        self.assertEqual(headline["subject"], "feat!: drop the legacy endpoint")

    def test_breaking_chore_with_no_type_group_still_wins_the_major_headline(self):
        # A breaking chore has no `### Added`/`### Fixed` group of its own
        # -- the major branch must still find it via `breaking`, not type.
        window = core_releaselib.classify_window([
            {"sha": "1" * 40, "subject": "chore!: drop legacy config path",
             "body": ""},
        ])
        self.assertEqual(window["bump"], "major")
        headline = _prose_select_headline_commit(window["commits"], window["bump"])
        self.assertIsNotNone(headline)
        self.assertEqual(headline["sha"], "1" * 40)
        self.assertTrue(headline["breaking"])

    def test_footer_only_breaking_change_also_wins_the_major_headline(self):
        window = core_releaselib.classify_window([
            {"sha": "1" * 40, "subject": "feat: add a thing", "body": ""},
            {"sha": "2" * 40, "subject": "fix: patch",
             "body": "BREAKING CHANGE: config moved"},
        ])
        self.assertEqual(window["bump"], "major")
        headline = _prose_select_headline_commit(window["commits"], window["bump"])
        self.assertEqual(headline["sha"], "2" * 40)

    # -- fixture: minor/patch fallback stays intact, never mislabeled ------

    def test_minor_window_is_unaffected_and_has_no_breaking_commit_at_all(self):
        # Obligation: ordinary nonbreaking changes are never mislabeled
        # breaking. By construction a breaking commit always bumps major
        # (classify_commit), so a genuine minor window can contain no
        # breaking commit -- the major branch can never spuriously fire and
        # steal the minor fallback's headline.
        window = core_releaselib.classify_window([
            {"sha": "1" * 40, "subject": "feat: add a thing", "body": ""},
            {"sha": "2" * 40, "subject": "fix: patch a bug", "body": ""},
        ])
        self.assertEqual(window["bump"], "minor")
        self.assertFalse(any(r["breaking"] for r in window["commits"]))
        headline = _prose_select_headline_commit(window["commits"], window["bump"])
        self.assertEqual(headline["sha"], "1" * 40)
        self.assertFalse(headline["breaking"])

    def test_patch_window_fallback_is_also_unaffected(self):
        window = core_releaselib.classify_window([
            {"sha": "1" * 40, "subject": "fix: patch a bug", "body": ""},
            {"sha": "2" * 40, "subject": "perf: faster path", "body": ""},
        ])
        self.assertEqual(window["bump"], "patch")
        self.assertFalse(any(r["breaking"] for r in window["commits"]))
        headline = _prose_select_headline_commit(window["commits"], window["bump"])
        self.assertEqual(headline["sha"], "1" * 40)


class BreakingFooterCompletenessTest(unittest.TestCase):
    """R-03, AC-12 (Scope-C security review finding 3, MEDIUM).

    `classify_window`'s `missing_footer` set (T-14, unchanged here) already
    keys on a row's own `bump != "none"`, never a fixed type list -- and
    `classify_commit` already sets `bump="major"` for ANY type carrying the
    breaking bang or a `BREAKING CHANGE:`/`BREAKING-CHANGE:` footer. So an
    unfootered `chore!:`/`docs!:`/`test!:`/`ci!:` was ALREADY reported in
    `missing_footer` and ALREADY causes `classify-window`'s exit 1 (step 2's
    BLOCK) before step 5's changelog composition is ever reached -- a
    footer-incomplete window cannot produce an empty `### Breaking` group,
    because it never gets past step 3.

    The finding this task closes is the DOCUMENTATION gap, not a missing
    mechanism: step 3's own prose read as scoped to `feat`/`fix`/`perf`/
    `refactor` only ("every `feat`/`fix`/`perf`/`refactor` commit ... MUST
    carry a `CHANGELOG:` footer"), silently underselling what the helper it
    describes actually enforces. A reader who trusted that sentence over the
    helper's own behavior could read an unfootered breaking `chore!:` as
    something the rule does not reach. This class pins the corrected,
    explicit step 3 prose (structural) and re-proves, under this task's own
    verification name, that `classify_window` already implements the wider
    rule end to end (fixture) -- for BOTH new breaking non-listed types and
    the pre-existing `feat`/`fix`/`perf`/`refactor` obligation, which this
    task must leave completely unchanged. No production code changes:
    `classify_commit`/`classify_window` are untouched (R-03 scope
    discipline) -- there is no second breaking-detection mechanism here.
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()

    # -- structural: step 3's prose states the widened rule explicitly -----

    def test_step3_names_the_breaking_regardless_of_type_rule(self):
        idx = self.text.index(
            "Verify footer completeness for the already-established")
        window = self.text[idx:idx + 2600]
        self.assertIn("regardless of type", window)
        self.assertIn("`breaking`", window)
        self.assertIn("chore!", window)

    def test_step3_ties_the_rule_to_classify_window_missing_footer(self):
        idx = self.text.index(
            "Verify footer completeness for the already-established")
        window = self.text[idx:idx + 2600]
        # The rule must be tied back to the exact mechanism that enforces
        # it, not restated as a second, independent description an agent
        # could implement by hand and get wrong (the hand-rolled-parse
        # failure mode this file already documents at length elsewhere).
        self.assertIn("missing_footer", window)
        self.assertIn('bump != "none"', window)

    def test_step3_original_four_type_sentence_is_preserved_verbatim(self):
        # This task WIDENS the rule; it must not reword or replace the
        # pre-existing feat/fix/perf/refactor obligation.
        self.assertIn(
            "every `feat`/`fix`/`perf`/`refactor` commit (the full "
            "harvested set step 5 rolls into the changelog, not just "
            "`feat`/`fix`)",
            self.text)

    # -- fixture: classify_window already implements the widened rule ------

    def test_unfootered_breaking_non_listed_types_are_in_missing_footer(self):
        for subject in ("chore!: rip out the vendored copy",
                         "docs!: rewrite the config contract",
                         "test!: change the harness contract",
                         "ci!: change the trigger contract"):
            with self.subTest(subject=subject):
                window = core_releaselib.classify_window(
                    [{"sha": "a" * 40, "subject": subject, "body": ""}])
                self.assertEqual(window["bump"], "major")
                self.assertEqual(len(window["missing_footer"]), 1)
                self.assertTrue(window["missing_footer"][0]["breaking"])

    def test_footered_breaking_non_listed_type_clears_the_gate(self):
        window = core_releaselib.classify_window([
            {"sha": "a" * 40, "subject": "chore!: rip out the vendored copy",
             "body": "CHANGELOG: Remove the vendored copy."}])
        self.assertEqual(window["bump"], "major")
        self.assertEqual(window["missing_footer"], [])

    def test_footer_only_breaking_change_on_a_non_listed_type_is_also_caught(self):
        # No `!` at all -- the footer-only breaking-change spelling on a
        # type with no bump of its own must be caught the same way.
        window = core_releaselib.classify_window([
            {"sha": "a" * 40, "subject": "docs: prose",
             "body": "BREAKING CHANGE: config moved"}])
        self.assertEqual(window["bump"], "major")
        self.assertEqual(len(window["missing_footer"]), 1)

    def test_original_four_types_footer_requirement_is_unchanged(self):
        # feat/fix/perf/refactor missing a footer are still caught -- this
        # task must not narrow or otherwise alter that pre-existing rule.
        for subject in ("feat: add a thing", "fix: patch a bug",
                         "perf: make it faster", "refactor: split a module"):
            with self.subTest(subject=subject):
                window = core_releaselib.classify_window(
                    [{"sha": "b" * 40, "subject": subject, "body": ""}])
                self.assertEqual(len(window["missing_footer"]), 1)

    def test_ordinary_nonbreaking_non_listed_types_stay_footer_optional(self):
        # An ordinary (non-breaking) chore/docs/test/ci is still not
        # REQUIRED to carry a footer -- only harvested by step 5 if it
        # happens to have one. This task widens the rule to breaking
        # commits only; it must not widen it further.
        for subject in ("chore: routine cleanup", "docs: update readme",
                         "test: add coverage", "ci: tweak the pipeline"):
            with self.subTest(subject=subject):
                window = core_releaselib.classify_window(
                    [{"sha": "c" * 40, "subject": subject, "body": ""}])
                self.assertEqual(window["bump"], "none")
                self.assertEqual(window["missing_footer"], [])


_RELEASEHASH_PATH = os.path.join(REPO_ROOT, "core", "pysrc", "releasehash.py")


class ReleasehashExitCodesTest(unittest.TestCase):
    """T-05, AC-04/AC-05 (spec P3): `releasehash.py`'s exit code 2 used to
    mean three distinct things -- malformed CLI usage, an unknown declared
    target, and the `NEVER_CONFIRMED` state. This splits the first two out:
    64 for malformed usage, 65 for an unknown target, while `check`'s
    never-confirmed outcome keeps 2 as its SOLE remaining meaning. The
    already-distinct outcomes 0 (confirmed/no-commands), 1 (changed), and
    3/4 (declared-file states from `_releaselib._targets_error_exit_code`)
    are proven unchanged here too, so a regression in any of the five
    can't hide behind only testing the two new codes. AC-05 requires
    confirmation authority (digest construction, markers, read-before-
    record) stay byte-identical -- proven here by asserting NO marker file
    is ever created by a malformed-usage or unknown-target invocation, and
    by a positive control proving `record` on a VALID target still creates
    one (so the negative assertions aren't vacuously true because `record`
    itself is broken).

    Invoked via REAL SUBPROCESS, not an in-process `importlib` load: this
    module's own `import _releaselib` (bare, sibling-relative) would
    otherwise resolve to this test file's already-cached CI-shim
    `_releaselib` module in `sys.modules` (the exact collision the shim's
    own module docstring calls out as M-6), which has no
    `default_targets_path` and crashes before `main()` even reaches the
    exit-code logic under test. A subprocess starts with an empty module
    cache, matching how every real caller (the release skill, a human
    operator) actually invokes this CLI."""

    APP_NO_COMMANDS_BLOCK = (
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "<!-- /release-targets -->\n"
    )

    APP_WITH_PRE_TAG_BLOCK = (
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "pre-tag: python3 checks/a.py\n"
        "<!-- /release-targets -->\n"
    )

    def _releasehash(self):
        # In-process load, used ONLY for the pure digest/marker helpers
        # (pre_tag_digest, record_confirmation, confirmation_path), which
        # never touch `_releaselib` and so never hit the collision above.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_rh_exitcodes_under_test", _RELEASEHASH_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run_cli(self, argv, root):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                    PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, _RELEASEHASH_PATH, *argv],
            cwd=tempfile.gettempdir(), env=env, capture_output=True,
            text=True, timeout=30)

    def _write_declared_file(self, root, block):
        os.makedirs(os.path.join(root, ".codearbiter"), exist_ok=True)
        with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                   "w", encoding="utf-8") as fh:
            fh.write(block)

    def _markers(self, root):
        markers_dir = os.path.join(root, ".codearbiter", ".markers")
        if not os.path.isdir(markers_dir):
            return []
        return os.listdir(markers_dir)

    def test_malformed_usage_exits_64_with_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad_argv in ([], ["nonsense"], ["check"],
                              ["digest", "app", "extra"],
                              ["badcmd", "app"]):
                proc = self._run_cli(bad_argv, tmp)
                self.assertEqual(proc.returncode, 64,
                                  f"argv={bad_argv!r}: {proc.stderr}")
                self.assertIn("usage", proc.stderr)
                self.assertEqual(self._markers(tmp), [],
                                  f"argv={bad_argv!r} must write no marker")

    def test_unknown_target_exits_65_with_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_NO_COMMANDS_BLOCK)
            for bad_argv in (["check", "doesnotexist"],
                              ["digest", "doesnotexist"],
                              ["record", "doesnotexist"]):
                proc = self._run_cli(bad_argv, tmp)
                self.assertEqual(proc.returncode, 65,
                                  f"argv={bad_argv!r}: {proc.stderr}")
                self.assertIn("unknown release target", proc.stderr)
                self.assertEqual(self._markers(tmp), [],
                                  f"argv={bad_argv!r} must write no marker")

    def test_never_confirmed_keeps_exit_2(self):
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            proc = self._run_cli(["check", "app"], tmp)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn(rh.NEVER, proc.stdout)
            self.assertIn("never been", proc.stderr)
            self.assertEqual(self._markers(tmp), [],
                              "a bare check must never write a marker")

    def test_confirmed_and_no_commands_still_exit_0(self):
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            digest = rh.pre_tag_digest(["python3 checks/a.py"])
            rh.record_confirmation(tmp, "app", digest)
            proc = self._run_cli(["check", "app"], tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(rh.CONFIRMED, proc.stdout)

        with tempfile.TemporaryDirectory() as tmp2:
            self._write_declared_file(tmp2, self.APP_NO_COMMANDS_BLOCK)
            proc = self._run_cli(["check", "app"], tmp2)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(rh.NO_COMMANDS, proc.stdout)

    def test_changed_still_exits_1(self):
        rh = self._releasehash()
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            rh.record_confirmation(tmp, "app", rh.pre_tag_digest(["stale command"]))
            proc = self._run_cli(["check", "app"], tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn(rh.CHANGED, proc.stdout)
            self.assertIn("CHANGED", proc.stderr)
            self.assertEqual(
                self._markers(tmp),
                [os.path.basename(rh.confirmation_path(tmp, "app"))],
                "a bare check must not overwrite or add a marker")

    def test_absent_declared_file_still_exits_3(self):
        # AbsentBlockError -- the targets file itself is genuinely absent,
        # never written at all (distinct from existing-but-broken, exit 4).
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".codearbiter"), exist_ok=True)
            proc = self._run_cli(["check", "app"], tmp)
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertEqual(self._markers(tmp), [])

    def test_malformed_declared_file_still_exits_4(self):
        # MalformedBlockError -- the file exists but its content violates
        # the declared-file grammar (an unbracketed line before any header).
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, "not a valid declaration line\n")
            proc = self._run_cli(["check", "app"], tmp)
            self.assertEqual(proc.returncode, 4, proc.stderr)
            self.assertEqual(self._markers(tmp), [])

    def test_record_on_a_valid_target_still_writes_a_marker(self):
        # Positive control: proves the "no marker written" assertions above
        # are not vacuous because `record` itself is broken.
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            proc = self._run_cli(["record", "app"], tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("recorded executable-command confirmation", proc.stdout)
            self.assertEqual(len(self._markers(tmp)), 1)


_RELEASE_SKILL_PATH = os.path.join(
    REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")


class ReleasehashCallersTest(unittest.TestCase):
    """T-06, AC-04/AC-05 (spec P3): proves the release skill's actual
    CALLERS of `releasehash.py check $TARGET` -- SKILL.md step 6c and the
    `resume_publish` asset-recovery lane (the sole production callers, per
    T-05's caller inventory) -- never mistake a T-05 usage/configuration
    failure (64 malformed usage, 65 unknown target) for the
    record-confirmation path, and that a legitimate first confirmation
    (record, then check) still succeeds exactly as it did before T-05.

    Both call sites share ONE literal invocation shape,
    `"$PY" ".../releasehash.py" check $TARGET` (SKILL.md step 6c and the
    resume_publish lane, `$TARGET` deliberately UNQUOTED as actually written
    in the skill), gated the same way throughout this skill: the caller
    proceeds only on exit 0, and STOPs on any non-zero exit. This exercises
    that literal shape through a REAL POSIX shell (house rule: dry-run the
    real caller's path, not a mock of the seam) mirroring
    `test_guarded_zero_tag_probe_executes_under_pipefail`'s
    positional-argument pattern, and skips only when no usable shell
    resolves -- never a silent pass.

    A malformed invocation is produced the same way the real unquoted
    `$TARGET` spelling would actually produce one: a target value containing
    whitespace word-splits into extra positional arguments at the unquoted
    `check $TARGET` call site, landing on wrong-arg-count usage (64) -- not a
    synthetic argv rigged only for this test."""

    APP_WITH_PRE_TAG_BLOCK = (
        "<!-- release-targets -->\n"
        "[app]\n"
        "prefix: v\n"
        "changelog: CHANGELOG.md\n"
        "payload: .\n"
        "pre-tag: python3 checks/a.py\n"
        "<!-- /release-targets -->\n"
    )

    CALLER_SHAPE_SCRIPT = (
        'export CLAUDE_PROJECT_DIR="$1"\n'
        'export PYTHONDONTWRITEBYTECODE=1\n'
        'PY="$2"\n'
        'HELPER="$3"\n'
        'TARGET="$4"\n'
        'if "$PY" "$HELPER" check $TARGET; then\n'
        '  echo CA_CALLER_BRANCH=CONFIRMED\n'
        'else\n'
        '  echo CA_CALLER_BRANCH=STOP\n'
        'fi\n'
    )

    def _write_declared_file(self, root, block):
        os.makedirs(os.path.join(root, ".codearbiter"), exist_ok=True)
        with open(os.path.join(root, ".codearbiter", "release-targets.md"),
                   "w", encoding="utf-8") as fh:
            fh.write(block)

    def _markers(self, root):
        markers_dir = os.path.join(root, ".codearbiter", ".markers")
        if not os.path.isdir(markers_dir):
            return []
        return os.listdir(markers_dir)

    def _run_caller_shape(self, root, target_literal):
        """Runs the exact `if check $TARGET; then ... else ... fi` shape
        both real SKILL.md callers use, and reports which branch ran."""
        bash = (core_releaselib._resolve_posix_shell()
                if os.name == "nt" else working_bash())
        if bash is None:
            self.skipTest("no working POSIX shell")
        result = subprocess.run(
            [bash, "-s", "--", Path(root).as_posix(),
             Path(sys.executable).as_posix(),
             Path(_RELEASEHASH_PATH).as_posix(), target_literal],
            input=self.CALLER_SHAPE_SCRIPT.encode("utf-8"),
            capture_output=True, timeout=60)
        return result

    def test_malformed_usage_from_the_real_unquoted_target_shape_never_reaches_the_confirmed_branch(self):
        # A target value with a space -- `$TARGET` unquoted at the real call
        # site word-splits it into two positional args -- reproduces
        # malformed usage (64) the same way the literal skill spelling
        # would, without rigging a synthetic argv.
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            result = self._run_caller_shape(tmp, "app extra")
            stdout = result.stdout.decode("utf-8", "replace")
            stderr = result.stderr.decode("utf-8", "replace")
            self.assertIn("CA_CALLER_BRANCH=STOP", stdout, stderr)
            self.assertNotIn("CA_CALLER_BRANCH=CONFIRMED", stdout)
            self.assertEqual(self._markers(tmp), [])

    def test_unknown_target_never_reaches_the_confirmed_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            result = self._run_caller_shape(tmp, "doesnotexist")
            stdout = result.stdout.decode("utf-8", "replace")
            stderr = result.stderr.decode("utf-8", "replace")
            self.assertIn("CA_CALLER_BRANCH=STOP", stdout, stderr)
            self.assertNotIn("CA_CALLER_BRANCH=CONFIRMED", stdout)
            self.assertEqual(self._markers(tmp), [])

    def test_legitimate_first_confirmation_still_succeeds_exactly_as_before(self):
        # `record`, then `check` -- the exact remedy step 6c prescribes for
        # `never-confirmed` (2) -- must still land in the CONFIRMED branch,
        # unaffected by the 64/65 split: T-05 only carved two NEW failure
        # codes out of the old overloaded 2, it did not touch 0/1/2 or the
        # record path.
        with tempfile.TemporaryDirectory() as tmp:
            self._write_declared_file(tmp, self.APP_WITH_PRE_TAG_BLOCK)
            record = subprocess.run(
                [sys.executable, _RELEASEHASH_PATH, "record", "app"],
                cwd=tempfile.gettempdir(),
                env=dict(os.environ, CLAUDE_PROJECT_DIR=tmp,
                          PYTHONDONTWRITEBYTECODE="1"),
                capture_output=True, text=True, timeout=30)
            self.assertEqual(record.returncode, 0, record.stderr)
            self.assertEqual(len(self._markers(tmp)), 1)

            result = self._run_caller_shape(tmp, "app")
            stdout = result.stdout.decode("utf-8", "replace")
            stderr = result.stderr.decode("utf-8", "replace")
            self.assertIn("CA_CALLER_BRANCH=CONFIRMED", stdout, stderr)
            self.assertNotIn("CA_CALLER_BRANCH=STOP", stdout)
            self.assertEqual(len(self._markers(tmp)), 1,
                              "a bare check must not write a second marker")

    def test_skill_step_6c_documents_the_new_exit_codes_as_distinct_from_confirmation_states(self):
        with open(_RELEASE_SKILL_PATH, encoding="utf-8") as fh:
            skill = fh.read()
        self.assertIn("Exit 64", skill)
        self.assertIn("exit 65", skill)
        self.assertIn("configuration failures, not confirmation states", skill)
        self.assertIn("read-then-record remedy above does not apply", skill)

    def test_resume_publish_lane_cites_the_same_exit_code_meaning(self):
        with open(_RELEASE_SKILL_PATH, encoding="utf-8") as fh:
            skill = fh.read()
        asset_recovery = skill.split(
            "### Asset recovery for `resume_publish`", 1)[1]
        asset_recovery = asset_recovery.split(
            "## Recovering from a bad release", 1)[0]
        self.assertIn("64/65", asset_recovery)
        self.assertIn("step 6c", asset_recovery)
        self.assertIn("never a confirmation", asset_recovery)


class ResolvePosixShellTest(unittest.TestCase):
    """#602: `_resolve_posix_shell()`'s resolution ALGORITHM, exercised with
    controlled inputs -- each branch pinned individually. This class proves
    the mechanism function's logic; it is deliberately distinct from
    `CoreCLITest.test_run_pre_tag_runs_a_dollar_PY_row_for_real` above, which
    proves the CALLER's actual path end-to-end with nothing mocked (house
    rule: dry-run the real path, don't just mock the seam)."""

    def test_returns_none_on_a_non_windows_host(self):
        # No resolution is attempted at all off Windows: `shell=True`
        # already dispatches through a POSIX shell there. Proven by making
        # EVERY resolution path available (a would-succeed which() hit) and
        # asserting the platform check alone still short-circuits to None.
        with mock.patch.object(core_releaselib.os, "name", "posix"), \
                mock.patch.object(
                    core_releaselib.shutil, "which",
                    return_value=r"C:\Program Files\Git\usr\bin\bash.exe"):
            self.assertIsNone(core_releaselib._resolve_posix_shell())

    def test_prefers_the_git_exec_path_relative_bash_when_present(self):
        # The PRIMARY strategy is deterministic, tied to the SAME git this
        # process already trusts -- proven by making the which() fallback
        # return a DIFFERENT but otherwise ACCEPTABLE (non-system32,
        # non-WindowsApps) `bash.exe` and asserting the exec-path candidate
        # wins anyway. (A which() hit under system32/WindowsApps would be
        # rejected by the WSL-stub filter regardless of priority order, so
        # it cannot distinguish "exec-path wins" from "which() was merely
        # rejected" -- this uses a which() candidate the filter would
        # otherwise ACCEPT, so only priority ordering explains the result.)
        with tempfile.TemporaryDirectory() as tmp:
            exec_path = os.path.join(tmp, "git-install", "mingw64", "libexec",
                                      "git-core")
            os.makedirs(exec_path)
            bin_dir = os.path.join(tmp, "git-install", "bin")
            os.makedirs(bin_dir)
            bash_path = os.path.join(bin_dir, "bash.exe")
            with open(bash_path, "w") as fh:
                fh.write("")
            wrong_dir = os.path.join(tmp, "some-other-bash")
            os.makedirs(wrong_dir)
            wrong_bash = os.path.join(wrong_dir, "bash.exe")
            with open(wrong_bash, "w") as fh:
                fh.write("")
            fake_proc = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=exec_path + "\n", stderr="")
            with mock.patch.object(core_releaselib.os, "name", "nt"), \
                    mock.patch.object(core_releaselib.subprocess, "run",
                                       return_value=fake_proc), \
                    mock.patch.object(
                        core_releaselib.shutil, "which",
                        return_value=wrong_bash):
                self.assertEqual(
                    core_releaselib._resolve_posix_shell(), bash_path)

    def test_falls_back_to_which_when_the_exec_path_candidate_is_absent(self):
        with mock.patch.object(core_releaselib.os, "name", "nt"), \
                mock.patch.object(
                    core_releaselib.subprocess, "run",
                    return_value=subprocess.CompletedProcess(
                        args=[], returncode=0,
                        stdout=r"C:\nonexistent\mingw64\libexec\git-core" + "\n",
                        stderr="")), \
                mock.patch.object(
                    core_releaselib.shutil, "which",
                    return_value=r"C:\Program Files\Git\usr\bin\bash.exe"):
            self.assertEqual(
                core_releaselib._resolve_posix_shell(),
                r"C:\Program Files\Git\usr\bin\bash.exe")

    def test_rejects_a_system32_which_hit_the_wsl_launcher_stub(self):
        # Windows' OWN `bash.exe` stub under system32 launches WSL -- a
        # SEPARATE Linux filesystem that cannot see a Windows `cwd` or a
        # Windows interpreter path (`PY`) the same way an MSYS2-based Git
        # Bash does -- so it is REJECTED even when it is the only which()
        # hit, rather than silently swapping one misdispatch for another.
        with mock.patch.object(core_releaselib.os, "name", "nt"), \
                mock.patch.object(
                    core_releaselib.subprocess, "run",
                    return_value=subprocess.CompletedProcess(
                        args=[], returncode=0, stdout="", stderr="")), \
                mock.patch.object(
                    core_releaselib.shutil, "which",
                    return_value=r"C:\WINDOWS\system32\bash.exe"):
            self.assertIsNone(core_releaselib._resolve_posix_shell())

    def test_rejects_a_windowsapps_which_hit(self):
        # The WSL launcher's second same-named home, under the per-user
        # WindowsApps app-execution-alias directory -- rejected for the
        # same reason as the system32 hit above.
        with mock.patch.object(core_releaselib.os, "name", "nt"), \
                mock.patch.object(
                    core_releaselib.subprocess, "run",
                    return_value=subprocess.CompletedProcess(
                        args=[], returncode=0, stdout="", stderr="")), \
                mock.patch.object(
                    core_releaselib.shutil, "which",
                    return_value=(r"C:\Users\x\AppData\Local\Microsoft"
                                  r"\WindowsApps\bash.exe")):
            self.assertIsNone(core_releaselib._resolve_posix_shell())

    def test_returns_none_when_nothing_is_found_at_all(self):
        with mock.patch.object(core_releaselib.os, "name", "nt"), \
                mock.patch.object(
                    core_releaselib.subprocess, "run",
                    return_value=subprocess.CompletedProcess(
                        args=[], returncode=0, stdout="", stderr="")), \
                mock.patch.object(core_releaselib.shutil, "which",
                                   return_value=None):
            self.assertIsNone(core_releaselib._resolve_posix_shell())

    def test_a_git_that_cannot_answer_exec_path_does_not_raise(self):
        # `git --exec-path` failing outright (a transient failure, a git
        # build with no exec-path support) degrades to the which() fallback
        # rather than raising -- matching this module's "never raise on
        # malformed input" mechanism-function convention.
        def _raise(*a, **k):
            raise OSError("no such file")
        with mock.patch.object(core_releaselib.os, "name", "nt"), \
                mock.patch.object(core_releaselib.subprocess, "run",
                                   side_effect=_raise), \
                mock.patch.object(
                    core_releaselib.shutil, "which",
                    return_value=r"C:\Program Files\Git\usr\bin\bash.exe"):
            self.assertEqual(
                core_releaselib._resolve_posix_shell(),
                r"C:\Program Files\Git\usr\bin\bash.exe")


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
        # The release lane resolves the available interpreter once. The row
        # must consume that value instead of hardcoding either platform's
        # common spelling and failing on the other supported host shape.
        self.assertEqual(row["generate"], '"$PY" tools/build-host-packages.py')

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
    # `"$PY" tools/build-host-packages.py --check`, under the repo-root
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
        # #602: every `pre-tag` entry in this repo's OWN declared file was
        # rewritten from a hardcoded `python3` to the portable `"$PY"`
        # convention (Part 3 of the #601 remediation, deferred until
        # `run-pre-tag` resolved a POSIX shell on Windows) -- the pattern
        # accepts EITHER spelling so a future row using the old
        # `python3 <script>` form (still valid, just not portable) still
        # passes, while pinning that every CURRENT row in this file uses
        # the new one (asserted separately below).
        import re as _re
        cmd_re = _re.compile(r'^(?:python3|"\$PY")\s+(\S+\.py)\b')
        for target, row in self.by_target.items():
            for command in row["pre_tag"]:
                with self.subTest(target=target, command=command):
                    match = cmd_re.match(command)
                    self.assertIsNotNone(
                        match,
                        f"{target}: pre-tag {command!r} is not a "
                        "'python3 <script>[.py] ...' or '\"$PY\" "
                        "<script>[.py] ...' command")
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

    def test_this_repo_rows_every_pre_tag_command_uses_the_dollar_PY_convention(self):
        # #602 Part 3: EVERY `pre-tag` entry in this file's `[ca]` and
        # `[ca-pi]` blocks was rewritten from a hardcoded `python3` to
        # `"$PY"` now that `run-pre-tag` resolves a POSIX shell on Windows
        # too, so the convention is portable everywhere. This pins the
        # REWRITE itself (distinct from the test above, which pins the
        # allowlisted-root/exists-on-disk shape and deliberately still
        # accepts a `python3`-spelled row as syntactically valid) --
        # reverting even ONE row back to `python3` must fail here.
        all_pre_tag = [
            command
            for row in self.rows
            for command in row["pre_tag"]
        ]
        self.assertEqual(
            [], self.by_target["ca-codex"]["pre_tag"],
            "Codex live host proof must not be a pre-tag release requirement",
        )
        self.assertEqual(
            len(all_pre_tag), 4,
            "expected exactly 4 declared pre-tag commands across all rows "
            "(3 on [ca], none on [ca-codex], 1 on [ca-pi]) -- update this count deliberately if "
            "a row's pre-tag list ever changes shape")
        for command in all_pre_tag:
            with self.subTest(command=command):
                self.assertTrue(
                    command.startswith('"$PY" '),
                    f"pre-tag {command!r} does not use the portable "
                    "\"$PY\" convention (#602 Part 3)")
                self.assertNotIn("python3", command)


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
    # Re-anchored (issue #571): "CHANGELOG:" and "auto-fill" each also occur
    # in the Phase-1 step-3 prose restating this same doctrine, so neither
    # alone could detect deletion of the Hard Rules bullet. Added the span
    # unique to that bullet -- verified `text.count(...) == 1` in the source
    # and all three rendered payloads.
    "footer BLOCK / never-auto-fill": (
        "CHANGELOG:", "auto-fill", "MUST NOT auto-fill a missing"),
    # Re-anchored (issue #571): "gh release view" occurs 3x (the isDraft
    # probe, the Phase-3 read-back, and this Hard Rules bullet) and
    # "non-draft" occurs 4x, so neither token alone is unique. Added the
    # Hard Rules bullet's own unique span.
    "publish read-back": (
        "gh release view", "non-draft",
        "MUST verify the published Release by read-back"),
    # Re-anchored (issue #571): "published tag is immutable" occurs twice
    # (once inline in Phase 2's cleanup-mode discussion, once as this
    # section's own opening hard-rule sentence), so it could not detect
    # deletion of the "Recovering from a bad release" doctrine on its own.
    # Added the sentence's own unique continuation.
    "immutable-tag hard rule": (
        "published tag is immutable", "Correction means publishing a NEW version"),
    "derive-never-guess": ("MUST NOT guess the version",),
    # Re-anchored (issue #571): "pre-tag" (x8), "non-zero exit" (x5), and
    # "BLOCK" (x11) each recur throughout the file, so their conjunction
    # could still survive deletion of this specific Hard Rules bullet as
    # long as each token happened to survive elsewhere. Added the bullet's
    # own unique span.
    "pre-tag BLOCK-on-nonzero": (
        "pre-tag", "non-zero exit", "BLOCK", "BLOCK on a non-zero exit"),
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
    # Blind exercise run 19 (agent-lane-proof.json), fixed as part of the
    # proof-refresh this run required before the next real release.
    "HIGH-1 (run 19): --dry-run does not execute rebuild/generate": (
        "not under `--dry-run`",
        "Declared `rebuild`/`generate` commands are printed by name, not run"),
    "HIGH-2 (run 19): resume_publish reconstructs notes via changelog-section": (
        "This scratch file is not required to survive across a session boundary",
        "changelog-section"),
    # Re-run of the agent-judgment exercise (2026-07-31): two more HIGH
    # findings and the six MEDIUMs it raised. Distinct key names from the
    # PRIOR round's HIGH-1..4 above -- same date, a different pass, and a
    # different set of findings; these must not collide with (or silently
    # replace) the earlier dict entries.
    "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse": (
        # Anchor follows the skill's own spelling: the placeholder
        # `MAJOR.MINOR.PATCH` was replaced by the `$VERSION` variable the
        # lane now actually assigns (blind exercise run 15 -- the literal
        # appeared in seven commands and was never defined anywhere, so the
        # tag/push/release commands were uncopyable as written).
        # Re-anchored (issue #571): `git rev-parse ${TAG_PREFIX}${VERSION}`
        # also occurs in Phase 3 step 5's provenance-recording command, so
        # it survived deletion of THIS sentence (the "never a raw rev-parse"
        # rule). Added the sentence's own unique lead-in.
        "git rev-parse", "peel-tag",
        "never from a raw tag ref lookup"),
    # Re-anchored (issue #571): "latest-eligible: true`" occurs 5x and
    # "single-target" occurs 3x across the file's other `--latest`/back-fill
    # prose, so neither alone is unique to this specific back-fill
    # detect-step sentence. Added the sentence's own mechanism-bearing
    # clause -- not the comma-heavy "is, at this moment, single-target"
    # tail, which is easy copyedit bait for the exact reason this file's
    # own header comment warns about.
    "HIGH-2 (re-run): back-fill declares latest-eligible for its one target": (
        "latest-eligible: true`", "single-target",
        "this lane can only ever propose ONE row"),
    "MEDIUM (re-run): omitted single target resolves via list-targets, not assumption": (
        "mechanically, never by assumption", "list-targets"),
    "MEDIUM (re-run): manifest bump is stated once (step 6), not twice": (
        "one action described two ways",),
    # T-10 (#570 finding BODY-03, 2026-09-21): the residual this rule used
    # to guard ("documented rather than silently accepted") is now CLOSED --
    # `verify-tag-ancestor` confirms reachability and refuses an
    # unreachable baseline instead of leaving the gap only described in
    # prose. Same two tokens as before this fix (deliberately unchanged):
    # both remain literally present in the rewritten source paragraph,
    # describing the OLD design the fix replaced, and BOTH also still
    # occur, unmodified, in the three generated host payloads
    # `GovernanceSurvivalTest` checks -- those payloads regenerate in T-19,
    # not here (T-10's scope excludes generated host copies), so a token
    # only the new source paragraph carries (e.g. `verify-tag-ancestor`
    # itself) would falsely report this rule MISSING against every
    # not-yet-regenerated payload before T-19 lands.
    "MEDIUM (re-run), closed by #570 BODY-03: last_tag_select's ancestry gap is now verified, not merely documented": (
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
        "_releaselib.py\" dates-match <Phase-1 section file> <message-file>",),
    # Run 5 (2026-07-31).
    "HIGH (run 5): the <none> sentinel is derived into a range, never substituted": (
        "is a sentinel, not a revision", "WINDOW=HEAD"),
    "MEDIUM (run 5): the possibly-empty tag_sha is quoted": (
        'Quote it', '"$TAG_SHA"'),
    "MEDIUM (runs 5+7): manifest_version is parsed by the file's own format": (
        "FORMAT'S OWN parser rather than a line-grep",),
    "LOW (run 5): the round-trip check reads the raw object, not a reconstruction": (
        'git cat-file tag "$RELEASE_TAG"',),
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
        "the expected non-zero status is on the left of `||`",),
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
        "_releaselib.py\" adoption-commit"),
    "HIGH (run 30): zero-tag manifest requires an explicit adoption classification": (
        "A zero-tag target needs an explicit adoption classification",
        "never published", "previously published without tags"),
    "A-3.6: the interpreter fallback is stated as a file-wide convention": (
        "Interpreter convention, stated once",),
    "HIGH-adjacent (run 11): window classification runs through the helper": (
        "Two operators writing two parses", "_releaselib.py\" classify-window"),
    # #565: --dry-run is a prose-only addition to this skill (no
    # `_releaselib.py` change was needed -- every CLI subcommand it invokes
    # already existed). Pinned here because a prose-only fix has no other
    # guard: nothing in `.github/scripts` or `plugins/*/hooks/tests`
    # exercises the skill's own instructions, only the library functions
    # they call. Two independently-unique anchors: the stop point after
    # Phase 1 step 4, and the pre-tag-checks-are-listed-not-run rationale.
    "#565: dry-run stops after Phase 1 step 4, before any write": (
        "Stop there, before step 5",),
    "#565: dry-run lists pre-tag checks but never runs them": (
        "listed, never executed",),
    # T-17 (issue #623, AC-13/AC-14): closing the three highest-priority gaps
    # the T-16 invariant map found with no proving test
    # (.codearbiter/reports/release-closure-invariant-map.md, section 4).
    # G2, G4-G8, G10-G12 remain open, deliberately left for T-18.
    #
    # G1 (obligation 1-E): the hosted/local execution boundary itself had no
    # guard distinct from the surrounding "STOPs before tag composition"
    # sentence (1-D, already tested). Anchored on the boundary rule plus the
    # lead-in that names what the interactive agent MAY do, so a rewrite that
    # keeps one half but drops the other is still caught.
    "G1 (T-17): the interactive agent must not execute tag composition locally": (
        "interactive agent may authorize, dispatch, or",
        "MUST NOT execute the tag-composition commands below locally"),
    # G3 (obligation 1-K): the Phase-2-side half of the Phase-2/Phase-3
    # publication boundary -- distinct from Phase 3's own STOP gate, which
    # other rules already cover. Two tokens so a partial deletion (e.g. only
    # the "MUST NOT push" clause surviving with the routing sentence gone)
    # is still caught.
    "G3 (T-17): Phase 2 must not push the tag or create the Release": (
        "MUST NOT push the tag or create the GitHub Release here",
        "Publication is Phase 3, a separate step the user authorizes after reading the report"),
    # G9 (obligation 2-17): a `gh` failure for any reason other than a
    # genuinely absent Release (no remote, no network, unauthenticated) must
    # STOP rather than silently guessing `<release_nondraft>` -- previously
    # unguarded, so a prose regression here could not be caught.
    "G9 (T-17): a gh failure other than absent-Release STOPs, never guesses": (
        "STOP and surface it rather than passing a guessed value",
        "genuinely absent Release"),
    # T-18 (issue #623, AC-13/AC-14): closing the remaining gaps the T-16
    # invariant map flagged and T-17 deliberately left open
    # (.codearbiter/reports/release-closure-invariant-map.md, section 4).
    # Every token pair below was verified byte-identical, and unique
    # (count == 1), in BOTH the new split source AND all three
    # not-yet-regenerated rendered host payloads before being added here
    # (T-19 regenerates those payloads; this sprint's own
    # `verification-boundary` note in T-17's diff explains why a rule
    # anchored on T-17's NEW substep-only prose -- a `### 2.x` heading, a
    # "per 2.6 below" cross-reference -- would report MISSING against the
    # three stale payloads and go red before T-19 lands. None of the tokens
    # below are new prose; each is carried verbatim from the pre-split
    # paragraph into its new substep, so all four texts already agree.
    #
    # G2 (obligation 1-J): the Phase-2 report's content list was untested.
    "G2 (T-18): the Phase-2 report lists all six obligations": (
        "$TARGET`, version, bump rationale, the per-commit classification",
        "the per-commit classification, the changelog section, and the tag SHA."),
    # G4 (obligation 1-L): the Phase 2 closing gate sentence was untested.
    "G4 (T-18): the Phase-2 closing gate says nothing is published yet": (
        "the hosted publisher has composed the annotated tag in its "
        "isolated checkout and delivered the report",
        "Nothing is published."),
    # G5 (obligation 2-03): "classify first, then tag" ordering rule had no
    # pinned-phrase guard of its own (the underlying code fact was true by
    # construction, but nothing pinned the PROSE against regressing to
    # writing the ref before classification).
    "G5 (T-18): classification precedes tagging, stated as an ordering rule": (
        "Do not run `git tag` yet", "classify first, then tag"),
    # G6 (obligation 2-07): the lead sentence introducing the four sourced
    # `classify` arguments had no guard distinct from its four sub-clauses.
    "G6 (T-18): the classify-arguments lead sentence names its own scope": (
        "Source the other four arguments explicitly",
        "none of them is yours to invent"),
    # G7 (obligations 2-09, 2-14): `<tag_version>` is carried verbatim, and
    # the carried-vs-re-read contrast with `<manifest_version>`, had no
    # dedicated anchor (only 2-13's re-read half was pinned).
    "G7 (T-18): tag_version is carried verbatim, manifest_version is re-read": (
        "reused verbatim and never re-parsed from a tag or a file",
        "the two arguments are sourced differently on purpose"),
    # G8 (obligation 2-16): "pass the bare literal true/false, not the raw
    # --json object" is a distinct, stronger rule than 2-15's inversion
    # rule (it guards a different failure mode: silent falsey coercion).
    "G8 (T-18): release_nondraft is passed as a bare literal, not raw JSON": (
        "Pass the bare literal `true` or `false` and nothing else",
        "silently renders `already_published` unreachable"),
    # G10 (obligation 2-19, partial): the command FORM was already pinned
    # (run 4's rule); "sole tag-creation point" and "never -m" were not.
    "G10 (T-18): git tag -a is the sole tag-creation point, never -m": (
        "never `-m` for multi-line content, never an interactive editor",
        "sole point in the whole lane at which a tag is created"),
    # G11 (obligation 2-23): "notes-match takes a path, not a pipe" had no
    # guard of its own.
    "G11 (T-18): notes-match takes a path so the check is Windows-portable": (
        "`notes-match` takes a path",
        "would not survive the move to a Windows consumer"),
    # G12 (obligation 3-E, weak/shared anchor): the Zero-tag-correction
    # paragraph's own closing warning shared its anchor with 2-04's rule
    # (both spell `git rev-parse ${TAG_PREFIX}${VERSION}`), so deleting 3-E
    # alone could not turn anything red. T-17's split kept 2-04 and 3-E
    # adjacent within the SAME substep (2.2) rather than separating them,
    # so the shared-anchor risk is unchanged from the invariant map's
    # finding -- this rule closes it with tokens unique to 3-E's own
    # sentence, distinct from the existing "HIGH-1 (re-run)" rule's tokens.
    "G12 (T-18): the deprecated rev-parse warning has its own unique anchor": (
        "Never revive the deprecated local-object spelling",
        "it returns the annotated tag object rather than the commit"),
}

# Rules whose every anchor token also occurs elsewhere in the skill, so the
# rule cannot detect deletion of the sentence it guards. Discovered while
# mutation-testing the run-4 rules (issue #571). Declared here as a ratchet
# rather than silently tolerated: the test below fails in BOTH directions,
# so a newly-weak rule is caught and a repaired one must be removed from
# this set. All six were re-anchored on a span unique to their protected
# sentence (issue #571 remediation) -- verified `text.count(...) == 1` in
# the source and all three rendered payloads -- so the set is now empty.
# New rules must be sound from the start; this set stays as the ratchet
# for whatever the next mutation-testing pass finds.
_KNOWN_WEAK_ANCHORS = set()


def _missing_governance_rules_for(text, rules):
    """The subset of `rules` names whose token set is NOT fully present in
    `text`, in declaration order. Empty when every rule survives. A pure
    function so the checker itself can be exercised against a synthetic
    fixture and an arbitrary rule set -- not only against today's real
    skill text and the live `_GOVERNANCE_RULES` dict."""
    missing = []
    for name, tokens in rules.items():
        if not all(token in text for token in tokens):
            missing.append(name)
    return missing


def _missing_governance_rules(text):
    """`_missing_governance_rules_for` against the live `_GOVERNANCE_RULES`."""
    return _missing_governance_rules_for(text, _GOVERNANCE_RULES)


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


class ProjectRootConditionalPerHostTest(unittest.TestCase):
    """R-04 (Scope-D security review finding, MEDIUM) — regression-proofs
    R-02's repo-root binding fix at the GENERATED-PAYLOAD level, not the
    unconditional template.

    `core/surface/skills/release/SKILL.md` carries `PROJECT_ROOT=` inside a
    `{{IF:claude}}` / `{{ELSE}}` conditional, so BOTH branch strings —
    `${CLAUDE_PROJECT_DIR:-$(pwd)}` and the plain `$(pwd)` fallback — exist
    simultaneously as literal substrings in the source regardless of host.
    A source-only test (e.g. `GovernanceSurvivalTest`, which asserts rule
    PRESENCE, never per-branch EXCLUSION) cannot detect a future template
    edit that wrongly reintroduces a `CLAUDE_PROJECT_DIR` reference into the
    Codex/Pi `{{ELSE}}` branch — that reference would still resolve, once
    rendered, only into the claude payload, while the source text itself
    would report both hosts' branches present either way. Only reading the
    three REAL rendered payloads and asserting a negative (zero occurrences
    of the literal `CLAUDE_PROJECT_DIR` outside the claude payload) closes
    that gap, because Codex has no such env leg at all (`security-controls.md`,
    "Repo resolution") and a leaked reference there would defeat the same
    repo-root binding R-02 exists to guarantee.

    Reuses `GovernanceSurvivalTest`'s own payload-loading mechanism
    (`build_surface.load_host_descriptors` + `build_surface._output_rel`)
    rather than a hand-maintained path list or a fresh loading approach, and
    keys the result by `descriptor.name` (the host id: "claude"/"codex"/
    "pi"), not the plugin directory string.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo = REPO_ROOT
        cls.texts = {}
        descriptors = build_surface.load_host_descriptors(cls.repo)
        for descriptor in descriptors:
            dst, _rule = build_surface._output_rel(
                "skills/release/SKILL.md", descriptor)
            if dst is None:
                continue
            path = os.path.join(cls.repo, descriptor.plugin_dir, dst)
            with open(path, encoding="utf-8") as fh:
                cls.texts[descriptor.name] = fh.read()

    def test_the_three_governance_hosts_are_all_covered(self):
        # Same vacuous-scope floor as GovernanceSurvivalTest's own sanity
        # check: if `_output_rel` ever returned nothing for one of the three
        # governance hosts, this class would silently stop checking it.
        self.assertEqual(
            set(self.texts), {"claude", "codex", "pi"},
            "expected exactly the three governance hosts' rendered "
            "skills/release/SKILL.md payloads")

    def test_claude_resolves_project_root_from_claude_project_dir(self):
        self.assertIn(
            "PROJECT_ROOT=${CLAUDE_PROJECT_DIR:-$(pwd)}",
            self.texts["claude"])

    def test_codex_resolves_project_root_from_pwd(self):
        self.assertIn("PROJECT_ROOT=$(pwd)", self.texts["codex"])

    def test_codex_never_references_claude_project_dir(self):
        # Split from the presence assertion above so a future regression
        # that leaks CLAUDE_PROJECT_DIR into the codex payload elsewhere in
        # the file (not necessarily on the PROJECT_ROOT= line itself) is
        # independently reportable, and can never be masked by the other
        # assertion failing (or passing) first -- unittest stops a method at
        # its first failed assertion, so two checks folded into one method
        # can hide one another.
        text = self.texts["codex"]
        self.assertEqual(
            text.count("CLAUDE_PROJECT_DIR"), 0,
            "ca-codex's rendered release SKILL.md must never reference "
            "CLAUDE_PROJECT_DIR -- Codex has no such env leg (R-02, "
            "security-controls.md \"Repo resolution\")")

    def test_pi_resolves_project_root_from_pwd(self):
        self.assertIn("PROJECT_ROOT=$(pwd)", self.texts["pi"])

    def test_pi_never_references_claude_project_dir(self):
        text = self.texts["pi"]
        self.assertEqual(
            text.count("CLAUDE_PROJECT_DIR"), 0,
            "ca-pi's rendered release SKILL.md must never reference "
            "CLAUDE_PROJECT_DIR -- Pi has no such env leg (R-02, "
            "security-controls.md \"Repo resolution\")")


# --------------------------------------------------------------------------- #
# Issue #571 remediation: the mutation proof itself. Each of the six rules
# GovernanceSurvivalTest used to declare in `_KNOWN_WEAK_ANCHORS` is proven
# here with a RED/GREEN pair against the REAL source skill text -- not a
# synthetic fixture -- by mutilating the WHOLE guarded sentence (never just
# the new anchor span in isolation, which would make GREEN tautological --
# any unique string added as a token catches its own deletion, and the
# ratchet test above already proves uniqueness; the property actually worth
# proving is that the anchor lives INSIDE the sentence it names) and
# checking:
#
#   RED  (the pre-#571 defect, reproduced): the OLD token tuple -- pinned
#        below exactly as it read before this fix, never read from the live
#        `_GOVERNANCE_RULES` -- stays silent. The mutilated text still
#        "passes" by the old rule's reckoning, because every one of its
#        tokens happens to also occur elsewhere in the file, outside the
#        deleted sentence.
#   GREEN (the fix): the CURRENT `_GOVERNANCE_RULES` entry for that same
#        rule name -- read live, so a future re-edit of the anchor is
#        exercised automatically -- reports the rule missing.
#
# Each guarded sentence is located by a (start, end) pair of short literal
# markers rather than hand-copied prose, so the fixture cannot silently
# drift from the file's actual em-dashes/curly quotes/backticks -- and each
# pair's own uniqueness is asserted before it is used to slice anything.
#
# A rule that regresses to weak (its anchor accidentally becomes non-unique
# again) turns this test's GREEN half red, independent of and in addition
# to `test_every_rule_has_at_least_one_uniquely_occurring_anchor` above.
# --------------------------------------------------------------------------- #

class DoctrineDeletionMutationProofTest(unittest.TestCase):
    """RED/GREEN mutation proof for the six rules re-anchored by #571."""

    # The exact anchor tuples as they read BEFORE this remediation -- the
    # defect being fixed, preserved here as a fixed historical baseline so
    # this test keeps proving the OLD shape stayed blind even after the
    # live dict above is edited again in the future.
    _PRE_571_ANCHORS = {
        "footer BLOCK / never-auto-fill": ("CHANGELOG:", "auto-fill"),
        "publish read-back": ("gh release view", "non-draft"),
        "immutable-tag hard rule": ("published tag is immutable",),
        "pre-tag BLOCK-on-nonzero": ("pre-tag", "non-zero exit", "BLOCK"),
        "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse": (
            "git rev-parse ${TAG_PREFIX}${VERSION}", "peel-tag"),
        "HIGH-2 (re-run): back-fill declares latest-eligible for its one target": (
            "latest-eligible: true`", "single-target"),
    }

    # (start marker, end marker) bounding the WHOLE sentence each rule
    # protects, each pair verified unique (count == 1) in the source below
    # before it is trusted to slice anything. The deleted span
    # `text[find(start) : find(end, from=start) + len(end)]` is the entire
    # guarded sentence, not merely the new anchor token -- so GREEN below
    # proves the anchor is actually inside the doctrine it names.
    _SENTENCE_MARKERS = {
        "footer BLOCK / never-auto-fill": (
            "MUST NOT auto-fill a missing", "and stopped."),
        "publish read-back": (
            "MUST verify the published Release by read-back",
            "is not a passing gate."),
        "immutable-tag hard rule": (
            "A published tag is immutable. Correction means publishing a "
            "NEW version",
            "deleting the old one.**"),
        "pre-tag BLOCK-on-nonzero": (
            "MUST run every declared `pre-tag` check",
            "beyond what the row declares."),
        "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse": (
            "Resolve `<tag_exists>` and `<tag_sha>` from the LOCAL ref "
            "this way",
            "needed no stopping at all."),
        "HIGH-2 (re-run): back-fill declares latest-eligible for its one target": (
            "the command prints the exact `release-targets.md` block it "
            "would write",
            "at this moment, single-target."),
    }

    # The new anchor token added to each rule's tuple by this remediation --
    # asserted below to fall INSIDE the deleted sentence, so GREEN cannot
    # pass by coincidence (e.g. a marker pair that accidentally excludes
    # the very token meant to catch the deletion).
    _NEW_ANCHOR_TOKEN = {
        "footer BLOCK / never-auto-fill": "MUST NOT auto-fill a missing",
        "publish read-back": "MUST verify the published Release by read-back",
        "immutable-tag hard rule": "Correction means publishing a NEW version",
        "pre-tag BLOCK-on-nonzero": "BLOCK on a non-zero exit",
        "HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse":
            "never from a raw tag ref lookup",
        "HIGH-2 (re-run): back-fill declares latest-eligible for its one target":
            "this lane can only ever propose ONE row",
    }

    @classmethod
    def setUpClass(cls):
        source_path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(source_path, encoding="utf-8") as fh:
            cls.source_text = fh.read()

    def test_the_six_rules_are_exactly_the_ones_pinned_here(self):
        # Guards the proof itself: if a future edit adds a seventh weak rule
        # or removes one of these six from `_GOVERNANCE_RULES` entirely,
        # this test's own bookkeeping (not a silently-vacuous mutation
        # check) is what should fail first.
        self.assertEqual(
            set(self._PRE_571_ANCHORS), set(self._SENTENCE_MARKERS))
        self.assertEqual(
            set(self._PRE_571_ANCHORS), set(self._NEW_ANCHOR_TOKEN))
        for name in self._PRE_571_ANCHORS:
            self.assertIn(name, _GOVERNANCE_RULES)

    def _mutilated_text(self, rule):
        start_m, end_m = self._SENTENCE_MARKERS[rule]
        self.assertEqual(
            self.source_text.count(start_m), 1,
            f"{rule}: sentence start marker {start_m!r} is not unique in "
            "the source -- fixture assumption broken")
        start = self.source_text.find(start_m)
        end_marker_idx = self.source_text.find(end_m, start)
        self.assertNotEqual(
            end_marker_idx, -1,
            f"{rule}: sentence end marker {end_m!r} not found after the "
            "start marker")
        end = end_marker_idx + len(end_m)
        deleted = self.source_text[start:end]
        # The new anchor token must fall INSIDE the deleted span -- proves
        # the token actually lives in the sentence it is meant to guard,
        # not merely that some unique string was picked at random.
        self.assertIn(
            self._NEW_ANCHOR_TOKEN[rule], deleted,
            f"{rule}: the new anchor token is not inside the marker-bounded "
            "sentence -- markers don't actually bound the guarded doctrine")
        return self.source_text[:start] + self.source_text[end:]

    def test_deleting_the_whole_guarded_sentence_is_red_under_the_old_anchor(self):
        for rule, old_tokens in self._PRE_571_ANCHORS.items():
            with self.subTest(rule=rule):
                mutilated = self._mutilated_text(rule)
                missing = _missing_governance_rules_for(mutilated, {
                    rule: old_tokens})
                self.assertEqual(
                    missing, [],
                    f"{rule}: the OLD anchor tuple {old_tokens!r} was "
                    "expected to stay silent (RED) against a text with the "
                    "whole guarded sentence deleted -- if it now reports "
                    "missing, the old tuple was never actually weak "
                    "against this mutation and this fixture needs "
                    "revisiting")

    def test_deleting_the_whole_guarded_sentence_is_caught_by_the_current_anchor(self):
        for rule in self._SENTENCE_MARKERS:
            with self.subTest(rule=rule):
                mutilated = self._mutilated_text(rule)
                missing = _missing_governance_rules_for(mutilated, {
                    rule: _GOVERNANCE_RULES[rule]})
                self.assertEqual(
                    missing, [rule],
                    f"{rule}: the CURRENT anchor tuple "
                    f"{_GOVERNANCE_RULES[rule]!r} was expected to catch "
                    "(GREEN) the whole guarded sentence being deleted -- "
                    "the re-anchoring regressed")


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
            "changelog_reconciliations":
                ".codearbiter/release-changelog-reconciliations.json",
            "payload": ".",
            "payload_exclude": [".codearbiter/"],
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
        self.assertEqual(
            rows[0]["changelog_reconciliations"],
            ".codearbiter/release-changelog-reconciliations.json")
        self.assertEqual(rows[0]["payload"], ".")
        self.assertEqual(rows[0]["payload_exclude"], [".codearbiter/"])
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
            self.assertEqual(
                rows[0]["changelog_reconciliations"],
                ".codearbiter/release-changelog-reconciliations.json")
            self.assertEqual(rows[0]["payload_exclude"], [".codearbiter/"])
            # HIGH-2 (adversarial review 2026-07-31): the full CLI path
            # (`backfill-detect` -> printed text -> real parser) must also
            # carry the eligibility declaration, not just the pure-function
            # call tested above.
            self.assertIs(rows[0]["latest_eligible"], True)

    def test_backfilled_root_payload_excludes_hook_governance_scratch(self):
        row = core_releaselib.detect_candidate_target(
            ["package.json"], ["CHANGELOG.md"])
        text = core_releaselib.format_release_targets_block(row)
        self.assertIn("payload: .\n", text)
        self.assertIn("payload-exclude: .codearbiter/\n", text)
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".codearbiter"))
            targets = os.path.join(tmp, ".codearbiter", "release-targets.md")
            with open(targets, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(os.path.join(tmp, ".codearbiter", "gate-events.log"),
                      "w", encoding="utf-8") as fh:
                fh.write("hook scratch\n")
            parsed = core_releaselib.load_targets(targets)[0]
            exclusions = core_releaselib.governance_scratch_exclusions(parsed)
            self.assertIn(".codearbiter/gate-events.log", exclusions)

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

    def test_validate_reconciliations_checks_the_authored_ledger_before_commit(self):
        ledger = {
            "schema_version": 1,
            "entries": [{
                "target": "app",
                "commit_sha": "a" * 40,
                "changelog": "Describe the published feature.",
                "reason": "The commit predates the changelog-footer policy.",
                "authorization": "Maintainer approved during Back-fill.",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconciliations.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(ledger, fh)
            self.assertEqual(
                core_releaselib.main(
                    ["validate-reconciliations", "app", path]),
                0)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schema_version":1,"entries":[{}]}')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    core_releaselib.main(
                        ["validate-reconciliations", "app", path]),
                    4)

    def test_validate_reconciliations_fails_closed_at_every_file_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = []
            missing = os.path.join(tmp, "missing.json")
            cases.append(("missing", missing, "regular file"))

            directory = os.path.join(tmp, "directory.json")
            os.mkdir(directory)
            cases.append(("directory", directory, "regular file"))

            oversized = os.path.join(tmp, "oversized.json")
            with open(oversized, "wb") as fh:
                fh.write(b"x" * (1024 * 1024 + 1))
            cases.append(("oversized", oversized, "1 MiB"))

            non_utf8 = os.path.join(tmp, "non-utf8.json")
            with open(non_utf8, "wb") as fh:
                fh.write(b"\xff")
            cases.append(("non-utf8", non_utf8, "not UTF-8"))

            malformed = os.path.join(tmp, "malformed.json")
            with open(malformed, "w", encoding="utf-8") as fh:
                fh.write("{")
            cases.append(("malformed", malformed, "invalid JSON"))

            for label, path, diagnostic in cases:
                with self.subTest(label=label):
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = core_releaselib.main(
                            ["validate-reconciliations", "app", path])
                    self.assertEqual(rc, 4)
                    self.assertIn(diagnostic, err.getvalue())

    def test_validate_reconciliations_rejects_a_symlink_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schema_version":1,"entries":[]}')
            with mock.patch.object(
                    core_releaselib.os.path, "islink", return_value=True):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = core_releaselib.main(
                        ["validate-reconciliations", "app", path])
            self.assertEqual(rc, 4)
            self.assertIn("regular file", err.getvalue())

    def test_validate_reconciliations_reports_size_and_read_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schema_version":1,"entries":[]}')
            probes = (
                (mock.patch.object(
                    core_releaselib.os.path, "getsize",
                    side_effect=OSError("size probe failed")),
                 "size probe failed"),
                (mock.patch("builtins.open",
                            side_effect=OSError("read failed")),
                 "read failed"),
            )
            for patcher, diagnostic in probes:
                with self.subTest(diagnostic=diagnostic), patcher:
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = core_releaselib.main(
                            ["validate-reconciliations", "app", path])
                    self.assertEqual(rc, 4)
                    self.assertIn(diagnostic, err.getvalue())

    def test_validate_reconciliations_rechecks_size_after_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schema_version":1,"entries":[]}')
            growing = mock.mock_open(read_data=b"x" * (1024 * 1024 + 1))
            with mock.patch.object(
                    core_releaselib.os.path, "getsize", return_value=1), \
                    mock.patch("builtins.open", growing):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = core_releaselib.main(
                        ["validate-reconciliations", "app", path])
            self.assertEqual(rc, 4)
            self.assertIn("1 MiB", err.getvalue())

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
        # ...and a second run reads rather than re-detecting, scoped to
        # THIS checkout/branch (AC-11, T-13) -- never claimed as an
        # irreversible project-wide fact. `release-targets.md` is a normal
        # tracked file: a branch cut before the declaration commit, or any
        # other clone/worktree that has not fetched or merged it, still
        # finds the file absent and correctly re-enters this lane.
        self.assertIn("does not re-detect", self.section)
        self.assertIn("does not run again in this exact checkout", self.section)
        self.assertNotIn("never runs again for this project", self.section)

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

    def test_backfill_declares_and_authors_the_reconciliation_ledger(self):
        self.assertIn("changelog-reconciliations", self.section)
        self.assertIn(
            ".codearbiter/release-changelog-reconciliations.json",
            self.section)
        for field in ("commit_sha", "changelog", "reason", "authorization"):
            with self.subTest(field=field):
                self.assertIn(field, self.section)
        self.assertIn("never invent", self.section.lower())
        self.assertIn("full SHA", self.section)
        self.assertIn("validate-reconciliations", self.section)

    def test_backfill_lands_declaration_before_release_reentry(self):
        self.assertIn("default branch", self.section)
        self.assertIn("published", self.section)
        self.assertIn("fresh non-default release branch", self.section)
        self.assertNotIn("then re-enter Pre-flight", self.section)


class BackfillOrderingTest(unittest.TestCase):
    """T-13, AC-11 (#570 R4-06/R4-07/R6-06, cross-referenced in
    .codearbiter/reports/release-closure-triage.md): two distinct fixes.

    (1) Branch-refusal ordering -- Back-fill used to sit before Pre-flight's
    non-default-branch check in file/step order, so an operator on `main`
    with no declared file was told to write the confirmed block and commit
    it there, and was refused only afterward (R4-06's finding; R6-06's
    sharpened restatement of the same conflict: step 3 told you to commit on
    a branch Pre-flight would then forbid). The fix composes with T-12's own
    prerequisite check rather than replacing it -- both now precede the
    marker mint and the write, in the same relative order commit-gate's own
    Pre-flight-then-Phase-2 sequence uses (prerequisite, then branch).

    (2) 'Never again' claim scoping -- `release-targets.md` is a normal
    TRACKED file, checkout/branch-scoped, not a project-global fact: a
    branch cut before the declaration commit, or any clone/worktree that
    has not fetched or merged it, still finds the file absent and correctly
    re-enters this lane. The prior 'never runs again for this project'
    wording overclaimed permanence; this asserts both the overclaim's
    removal (mutation-kill: a regression restoring the literal string must
    fail here) and the corrected, checkout-scoped wording, since
    `-k BackfillOrdering` does not select `BackfillSkillProseTest`."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.backfill = cls.text[
            cls.text.index("## Back-fill"): cls.text.index("## Pre-flight")]

    # -- (1) ordering: branch refusal composes with T-12, ahead of the write

    def test_branch_refusal_follows_the_prerequisite_check_and_precedes_the_write(self):
        existence_check = self.backfill.index("re-check existence")
        tech_stack_check = self.backfill.index(".codearbiter/tech-stack.md")
        branch_check = self.backfill.index("current branch is not `main`")
        marker_mint = self.backfill.index("mkdir -p")
        write = self.backfill.index("Write the confirmed block verbatim")
        # T-12's own checks are untouched and still precede the new one.
        self.assertLess(existence_check, tech_stack_check)
        # The new branch refusal composes after T-12's prerequisite check,
        # and both precede the marker mint and the write -- never after.
        self.assertLess(tech_stack_check, branch_check)
        self.assertLess(branch_check, marker_mint)
        self.assertLess(branch_check, write)

    def test_branch_refusal_names_the_literal_protected_branches_and_stops(self):
        idx = self.backfill.index("current branch is not `main`")
        window = self.backfill[idx:idx + 1600]
        self.assertIn("`main`", window)
        self.assertIn("`master`", window)
        self.assertIn("git branch --show-current", window)
        self.assertIn("STOP", window)
        self.assertIn("feature branch", window)

    def test_branch_refusal_does_not_invent_a_second_resolution_rule(self):
        # Mirrors T-12's own `test_never_invents_a_verification_command`:
        # the default-branch determination is the SAME mechanism Pre-flight
        # states below, not a freshly invented third rule.
        idx = self.backfill.index("current branch is not `main`")
        window = self.backfill[idx:idx + 1600]
        self.assertIn(
            "the same restriction Pre-flight's own branch check states "
            "below, resolved the same way", window)
        self.assertIn("git symbolic-ref refs/remotes/origin/HEAD", window)

    def test_branch_refusal_does_not_replace_preflights_own_check(self):
        idx = self.backfill.index("current branch is not `main`")
        window = self.backfill[idx:idx + 1600]
        self.assertIn("does not replace Pre-flight's own branch check", window)
        preflight_idx = self.text.index("## Pre-flight")
        preflight = self.text[preflight_idx:self.text.index("## Phase 1")]
        self.assertIn(
            "The current branch MUST NOT be `main`, `master`, or the "
            "default branch.", preflight)

    def test_commit_sentence_confirms_the_branch_was_already_checked(self):
        # 570-R6-06's exact quoted defect -- step 3 telling the operator to
        # commit "on the current branch" with no acknowledgement that branch
        # was ever verified safe. The bare phrase must not survive alone.
        idx = self.backfill.index("Commit it through `commit-gate` on the current branch")
        window = self.backfill[idx:idx + 200]
        self.assertIn("already confirmed above", window)

    # -- (2) wording: no project-wide "never again" overclaim survives

    def test_never_again_overclaim_is_gone(self):
        self.assertNotIn("never runs again for this project", self.text)

    def test_second_invocation_wording_is_checkout_branch_scoped(self):
        idx = self.backfill.index("A second invocation reads")
        window = self.backfill[idx:idx + 900]
        self.assertIn("this checkout", window)
        self.assertIn("this branch", window)
        self.assertIn("not an irreversible project-wide fact", window)
        self.assertIn("fetched or merged", window)
        self.assertNotIn("never runs again for this project", window)

    def test_existing_and_malformed_file_refusal_still_preceded_detection_untouched(self):
        # Preserved unchanged (task's own "existing-file/malformed-file
        # refusal preserved" verification clause) -- carried here since
        # `-k BackfillOrdering` does not select `BackfillSkillProseTest`.
        self.assertIn("AbsentBlockError", self.backfill)
        self.assertIn("however broken", self.backfill)
        targets_idx = self.text.index("## Targets")
        targets_section = self.text[targets_idx:self.text.index("## Back-fill")]
        self.assertIn("unparseable declared file", targets_section)
        self.assertIn("STOP and surface the parse error", targets_section)


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


class ReleaseAssetContractTest(unittest.TestCase):
    """AC-05/06/07/10: declared assets render and verify exactly."""

    _BASE = ("<!-- release-targets -->\n[preview]\n"
             "prefix: preview-\nchangelog: CHANGELOG.md\npayload: .\n"
             "version-policy: numeric-sequence\ninitial-version: 0.30\n")
    _ASSETS = (
        "arbiter-preview-{version}.zip",
        "arbiter-preview-{version}.zip.sha256",
        "install-{tag}.ps1",
        "install-{tag}.ps1.sha256",
        "install-{version}.sh",
        "install-{version}.sh.sha256",
    )

    def _declaration(self, build="python scripts/build.py", assets=None):
        lines = [self._BASE]
        if build is not None:
            lines.append(f"release-build: {build}\n")
        for asset in self._ASSETS if assets is None else assets:
            lines.append(f"release-asset: {asset}\n")
        lines.append("<!-- /release-targets -->\n")
        return "".join(lines)

    def test_parses_paired_build_and_repeated_asset_declarations(self):
        row = core_releaselib.parse_release_targets(self._declaration())[0]
        self.assertEqual(row["release_build"], "python scripts/build.py")
        self.assertEqual(row["release_assets"], list(self._ASSETS))

        legacy = core_releaselib.parse_release_targets(
            self._BASE + "<!-- /release-targets -->\n")[0]
        self.assertIsNone(legacy["release_build"])
        self.assertEqual(legacy["release_assets"], [])

    def test_partial_or_blank_asset_contract_is_rejected(self):
        cases = (
            self._declaration(assets=()),
            self._declaration(build=None),
            self._declaration(build=""),
            self._declaration(assets=("",)),
        )
        for declaration in cases:
            with self.subTest(declaration=declaration):
                with self.assertRaises(core_releaselib.MalformedBlockError):
                    core_releaselib.parse_release_targets(declaration)

    def test_templates_render_six_names_across_consecutive_versions(self):
        row = core_releaselib.parse_release_targets(self._declaration())[0]
        first = core_releaselib.render_release_assets(
            row["release_assets"], "0.31", "preview-0.31")
        second = core_releaselib.render_release_assets(
            row["release_assets"], "0.32", "preview-0.32")
        self.assertEqual(first, [
            "arbiter-preview-0.31.zip",
            "arbiter-preview-0.31.zip.sha256",
            "install-preview-0.31.ps1",
            "install-preview-0.31.ps1.sha256",
            "install-0.31.sh",
            "install-0.31.sh.sha256",
        ])
        self.assertEqual(second, [name.replace("0.31", "0.32")
                                  for name in first])

    def test_unsafe_unknown_or_duplicate_rendered_names_are_rejected(self):
        unsafe_sets = (
            ["../escape-{version}.zip"],
            ["nested/file-{version}.zip"],
            [r"nested\file-{version}.zip"],
            ["/absolute-{version}.zip"],
            ["C:{version}.zip"],
            ["asset {version}.zip"],
            ["asset;touch-{version}"],
            ["asset-$HOME-{version}"],
            ["asset-{unknown}.zip"],
            ["asset-{version!r}.zip"],
            [""],
            ["same-{version}.zip", "same-0.31.zip"],
            ["asset-{version}.zip", "ASSET-{version}.ZIP"],
            ["asset-{version}."],
            ["CON.zip"],
            ["AUX.txt"],
            ["Lpt9.txt"],
        )
        for templates in unsafe_sets:
            with self.subTest(templates=templates):
                self.assertIsNone(core_releaselib.render_release_assets(
                    templates, "0.31", "preview-0.31"))

    def test_parser_rejects_unsafe_and_duplicate_templates_before_build(self):
        for assets in (("../escape-{version}.zip",),
                       ("asset-{unknown}.zip",),
                       ("same-{version}.zip", "same-{version}.zip")):
            with self.subTest(assets=assets):
                with self.assertRaises(core_releaselib.MalformedBlockError):
                    core_releaselib.parse_release_targets(
                        self._declaration(assets=assets))

    def test_parser_rejects_templates_that_collide_under_the_declared_prefix(self):
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(self._declaration(assets=(
                "preview-{version}.zip", "{tag}.zip",
            )))

    def test_parser_rejects_a_declared_prefix_that_makes_tag_assets_unsafe(self):
        declaration = self._declaration(
            assets=("{tag}.zip",)).replace(
                "prefix: preview-\n", "prefix: preview/\n")
        with self.assertRaises(core_releaselib.MalformedBlockError):
            core_releaselib.parse_release_targets(declaration)

    def test_exact_inventory_accepts_only_declared_nonempty_regular_files(self):
        names = ["one-0.31.zip", "one-0.31.zip.sha256"]
        with tempfile.TemporaryDirectory() as output_dir:
            for name in names:
                with open(os.path.join(output_dir, name), "wb") as handle:
                    handle.write(b"content")
            expected = [os.path.join(os.path.abspath(output_dir), name)
                        for name in names]
            self.assertEqual(
                core_releaselib.verify_release_asset_inventory(
                    output_dir, names), expected)

    def test_inventory_rejects_windows_equivalent_declared_names(self):
        with tempfile.TemporaryDirectory() as output_dir:
            invalid_declarations = (
                ["asset.zip", "ASSET.ZIP"],
                ["asset."],
                ["CON.zip"],
                ["aux"],
                ["com1.txt"],
                ["LPT9"],
            )
            with mock.patch.object(core_releaselib.os, "scandir") as scandir:
                for names in invalid_declarations:
                    with self.subTest(names=names):
                        self.assertIsNone(
                            core_releaselib.verify_release_asset_inventory(
                                output_dir, names))
                scandir.assert_not_called()

            with open(os.path.join(output_dir, "ASSET.ZIP"), "wb") as handle:
                handle.write(b"asset")
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(
                    output_dir, ["asset.zip"]))

    def test_windows_reserved_name_neighbours_remain_valid(self):
        names = ("COM0.txt", "COM10.txt", "LPT0", "LPT10", "console.zip")
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(
                    core_releaselib.render_release_assets(
                        [name], "0.31", "preview-0.31"),
                    [name],
                )

    def test_exact_inventory_rejects_missing_extra_empty_directory_and_symlink(self):
        names = ["one.zip", "two.zip"]
        with tempfile.TemporaryDirectory() as root:
            output_dir = os.path.join(root, "assets")
            os.mkdir(output_dir)
            with open(os.path.join(output_dir, "one.zip"), "wb") as handle:
                handle.write(b"one")
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(output_dir, names))

            with open(os.path.join(output_dir, "two.zip"), "wb") as handle:
                handle.write(b"two")
            with open(os.path.join(output_dir, "extra.zip"), "wb") as handle:
                handle.write(b"extra")
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(output_dir, names))
            os.remove(os.path.join(output_dir, "extra.zip"))

            with open(os.path.join(output_dir, "two.zip"), "wb"):
                pass
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(output_dir, names))

            os.remove(os.path.join(output_dir, "two.zip"))
            os.mkdir(os.path.join(output_dir, "two.zip"))
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(output_dir, names))

            os.rmdir(os.path.join(output_dir, "two.zip"))
            try:
                os.symlink(os.path.join(output_dir, "one.zip"),
                           os.path.join(output_dir, "two.zip"))
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable on this host")
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(output_dir, names))

    def test_inventory_rejects_a_symlinked_output_directory(self):
        with tempfile.TemporaryDirectory() as root:
            real_dir = os.path.join(root, "real")
            link_dir = os.path.join(root, "link")
            os.mkdir(real_dir)
            with open(os.path.join(real_dir, "asset.zip"), "wb") as handle:
                handle.write(b"asset")
            try:
                os.symlink(real_dir, link_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlink creation unavailable on this host")
            self.assertIsNone(
                core_releaselib.verify_release_asset_inventory(
                    link_dir, ["asset.zip"]))

    def test_cli_renders_and_prints_only_a_verified_inventory(self):
        rendered = io.StringIO()
        with contextlib.redirect_stdout(rendered):
            rc = core_releaselib.main([
                "render-release-assets", "0.31", "preview-0.31",
                *self._ASSETS,
            ])
        self.assertEqual(rc, 0)
        names = rendered.getvalue().splitlines()
        self.assertEqual(len(names), 6)

        with tempfile.TemporaryDirectory() as output_dir:
            for name in names:
                with open(os.path.join(output_dir, name), "wb") as handle:
                    handle.write(b"asset")
            verified = io.StringIO()
            with contextlib.redirect_stdout(verified):
                rc = core_releaselib.main([
                    "verify-release-assets", output_dir, *names,
                ])
            self.assertEqual(rc, 0)
            self.assertEqual(
                verified.getvalue().splitlines(),
                [os.path.join(os.path.abspath(output_dir), name)
                 for name in names])

            with open(os.path.join(output_dir, "undeclared.txt"), "wb") as handle:
                handle.write(b"extra")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(core_releaselib.main([
                    "verify-release-assets", output_dir, *names,
                ]), 1)

    def test_cli_invalid_or_duplicate_templates_exit_2_without_stdout(self):
        cases = (
            ["render-release-assets", "0.31", "preview-0.31",
             "asset-{unknown}.zip"],
            ["render-release-assets", "0.31", "preview-0.31",
             "same-{version}.zip", "same-0.31.zip"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    rc = core_releaselib.main(argv)
                self.assertEqual(rc, 2, err.getvalue())
                self.assertEqual(out.getvalue(), "")

    def test_cli_invalid_or_duplicate_asset_names_exit_2_without_stdout(self):
        cases = (
            ["../escape.zip"],
            ["same.zip", "same.zip"],
        )
        with tempfile.TemporaryDirectory() as output_dir:
            for names in cases:
                with self.subTest(names=names):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), \
                            contextlib.redirect_stderr(err):
                        rc = core_releaselib.main([
                            "verify-release-assets", output_dir, *names,
                        ])
                    self.assertEqual(rc, 2, err.getvalue())
                    self.assertEqual(out.getvalue(), "")

    def test_show_row_exposes_asset_fields_in_queries_and_full_report(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".codearbiter"))
            path = os.path.join(root, ".codearbiter", "release-targets.md")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._declaration())
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": root}):
                build = io.StringIO()
                assets = io.StringIO()
                legacy = io.StringIO()
                with contextlib.redirect_stdout(build):
                    self.assertEqual(core_releaselib.main([
                        "show-row", "preview", "--field", "release-build",
                    ]), 0)
                with contextlib.redirect_stdout(assets):
                    self.assertEqual(core_releaselib.main([
                        "show-row", "preview", "--field", "release-assets",
                    ]), 0)
                with contextlib.redirect_stdout(legacy):
                    self.assertEqual(core_releaselib.main([
                        "show-row", "preview",
                    ]), 0)
        self.assertEqual(build.getvalue(), "python scripts/build.py\n")
        self.assertEqual(assets.getvalue().strip().split(","), list(self._ASSETS))
        self.assertIn("RELEASE_BUILD=", legacy.getvalue())
        self.assertIn("RELEASE_ASSETS=", legacy.getvalue())


class ReleaseSurfaceTest(unittest.TestCase):
    """AC-08 + security boundary: the release surface uses the new policy."""

    @classmethod
    def setUpClass(cls):
        def read(*parts):
            with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as fh:
                return fh.read()

        cls.skill = read("core", "surface", "skills", "release", "SKILL.md")
        cls.command = read("core", "surface", "commands", "release.md")
        cls.releaselib_source = read("core", "pysrc", "_releaselib.py")
        cls.index = read("core", "surface", "skills", "INDEX.md")
        cls.security = read(".codearbiter", "security-controls.md")
        cls.plan = read(".codearbiter", "plans", "preview-release-contract.md")

    def test_skill_reads_every_new_field_mechanically(self):
        for variable, field in (
                ("VERSION_POLICY", "version-policy"),
                ("INITIAL_VERSION", "initial-version"),
                ("RELEASE_BUILD", "release-build"),
                ("CHANGELOG_RECONCILIATIONS", "changelog-reconciliations")):
            self.assertIn(
                f'{variable}=$("$PY" "{{{{PLUGIN_ROOT}}}}/hooks/_releaselib.py" '
                f'show-row $TARGET --field {field})',
                self.skill)
        self.assertIn('list-field "$TARGET" release-assets', self.skill)
        self.assertIn('list-field "$TARGET" pre-tag', self.skill)
        dry_run = self.skill[
            self.skill.index("## Dry run") : self.skill.index("## Phase 2")]
        self.assertIn('list-field "$TARGET" pre-tag', dry_run)
        self.assertNotIn("show-row $TARGET --field pre-tag", dry_run)
        self.assertIn('VERSION_POLICY=${VERSION_POLICY:-semver}', self.skill)

    def test_reconciliation_route_binds_target_and_fresh_published_ref(self):
        self.assertIn(
            'classify-window "$TARGET" "$DEFAULT_BRANCH"', self.skill)
        # R-02 (Scope-C security review finding 2, MEDIUM) pinned this bare
        # command to the same resolved `$PROJECT_ROOT` every other bare git
        # command in this Pre-flight sequence now uses -- see
        # `AncestryRepoRootBindingTest` for the behavioral proof.
        self.assertIn(
            'git -C "$PROJECT_ROOT" fetch origin "$DEFAULT_BRANCH"',
            self.skill)
        self.assertIn("A failed fetch STOPs", self.skill)
        self.assertIn("exact lowercase full Git object ID", self.skill)
        self.assertIn("MUST NOT be added to the ledger", self.skill)
        self.assertIn("may supply changelog text only", self.skill)

    def test_hosted_candidate_reasserts_every_manifest_before_classification(self):
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        manifest_gate = (
            '"$PY" "{{PLUGIN_ROOT}}/hooks/_releaselib.py" '
            'check-manifests "$TARGET" "$VERSION"')
        self.assertIn(manifest_gate, phase2)
        self.assertLess(phase2.index(manifest_gate), phase2.index(
            '"$PY" "{{PLUGIN_ROOT}}/hooks/_releaselib.py" classify '))

    def test_hosted_candidate_requires_a_resolvable_parent(self):
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        self.assertIn(
            'HOSTED_PARENT=$(git rev-parse "$HOSTED_HEAD^1" 2>/dev/null) '
            "|| { printf 'STOP — hosted parent unavailable.", phase2)
        self.assertIn("a root commit or shallow checkout cannot qualify", phase2)

    def test_version_and_changelog_routes_are_policy_aware(self):
        for command in (
                "last-tag-for-policy", "derive-version", "version-greater",
                "notes-match", "changelog-section"):
            self.assertIn(command, self.skill)
        self.assertIn('"$VERSION_POLICY" "$INITIAL_VERSION"', self.skill)
        self.assertNotIn(
            'VERSION=$("$PY" "{{PLUGIN_ROOT}}/hooks/_releaselib.py" '
            'apply-bump', self.skill)

    def test_every_helper_runs_without_writing_bytecode(self):
        export = "PYTHONDONTWRITEBYTECODE=1; export PYTHONDONTWRITEBYTECODE"
        self.assertIn(export, self.skill)
        self.assertIn("before the first invocation", self.skill)
        self.assertIn("PYTHONUTF8=1", self.skill)
        self.assertIn("PYTHONIOENCODING=utf-8", self.skill)

    def test_phase_one_git_and_helpers_are_bound_to_project_root(self):
        self.assertIn('cd "$PROJECT_ROOT" ||', self.skill)
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Dry run")]
        for verb in ("log", "rev-parse", "merge-base", "diff", "status"):
            self.assertNotRegex(
                phase1, rf"\bgit {verb}\b",
                f"Phase 1 contains an unpinned git {verb} command")
        self.assertIn('git -C "$PROJECT_ROOT" log "$EFFECTIVE_WINDOW"', phase1)
        self.assertIn('--format=%H%x00%s%x00%b%x00', phase1)
        self.assertNotIn('--pretty=format:%H%n%s%n%b%n----', phase1)

    def test_commit_and_changelog_guards_reuse_the_resolved_project_root(self):
        self.assertIn(
            '[ ! -f "$PROJECT_ROOT/.codearbiter/tech-stack.md" ]',
            self.skill)
        self.assertIn(
            'git -C "$PROJECT_ROOT" symbolic-ref --quiet --short HEAD',
            self.skill)
        self.assertIn(
            'changelog-section "$PROJECT_ROOT" "$HOSTED_HEAD"',
            self.skill)
        self.assertIn(
            'changelog-section "$PROJECT_ROOT" "$RELEASE_TAG"',
            self.skill)

    def test_first_numeric_sequence_release_uses_the_empty_series_sentinel(self):
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Dry run")]
        self.assertIn('DERIVATION_BASE="<none>"', phase1)
        self.assertIn('derive-version "$DERIVATION_BASE"', phase1)
        self.assertIn('version-greater "$VERSION" "$COMPARISON_BASE"', phase1)

    def test_tag_identity_is_validated_once_and_quoted_everywhere(self):
        self.assertIn("safe Git tag prefix", self.skill)
        for expected in (
                'git tag -a "$RELEASE_TAG"',
                'git cat-file tag "$RELEASE_TAG"',
                'notes-match "$RELEASE_TAG"',
                'git push origin "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"',
                'gh release view "$RELEASE_TAG"'):
            self.assertIn(expected, self.skill)
        self.assertNotIn('git tag -a ${TAG_PREFIX}${VERSION}', self.skill)
        self.assertNotIn('git push origin ${TAG_PREFIX}${VERSION}', self.skill)
        self.assertNotIn('git push origin "$RELEASE_TAG"', self.skill)

    def test_executable_confirmation_precedes_rebuild_and_binds_all_inputs(self):
        preflight = self.skill[
            self.skill.index("## Pre-flight") : self.skill.index("## Phase 1")]
        confirmation = preflight.index("releasehash.py\" check $TARGET")
        rebuild = preflight.index('eval "$REBUILD"')
        self.assertLess(confirmation, rebuild)
        for field in ("pre-tag", "release-build", "rebuild", "generate"):
            self.assertIn(field, preflight[confirmation - 500:confirmation + 1000])
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Dry run")]
        self.assertIn("**6c. Re-check every declared executable", phase1)

    def test_automatic_publisher_authorization_names_the_pre_merge_report(self):
        self.assertIn("Phase 1 release-PR report", self.skill)
        self.assertIn("before that PR merged", self.skill)

    def test_preflight_clean_tree_probe_is_target_aware(self):
        self.assertIn(
            '"$PY" "{{PLUGIN_ROOT}}/hooks/_releaselib.py" '
            'clean-tree-status "$TARGET"', self.skill)
        self.assertIn("only when that path is disjoint", self.skill)
        self.assertNotIn(
            "git status --porcelain -- :/ "
            "':(exclude,top).codearbiter/gate-events.log'",
            self.skill)
        self.assertGreaterEqual(
            self.skill.count('release_require_clean_tree || exit "$?"'), 5)
        self.assertIn('if [ "$tree_status" -ne 0 ]', self.skill)
        self.assertIn('if [ -n "$tree_output" ]', self.skill)

    def test_asset_build_runs_only_in_hosted_prepublication_with_guards(self):
        checks = self.skill.index("run-pre-tag $TARGET")
        build = self.skill.index('eval "$RELEASE_BUILD"')
        push = self.skill.index(
            'git push origin "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"')
        self.assertLess(checks, build)
        self.assertLess(build, push)
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Phase 2")]
        self.assertNotIn('eval "$RELEASE_BUILD"', phase1)
        self.assertIn("do not execute that command in the interactive checkout", phase1)
        self.assertIn("new empty `RELEASE_ASSET_DIR`", self.skill)
        self.assertIn("export `VERSION RELEASE_TAG RELEASE_ASSET_DIR`", self.skill)
        self.assertIn("render-release-assets", self.skill)
        self.assertIn("verify-release-assets", self.skill)
        build_section = self.skill[build - 2500:build + 2500]
        self.assertGreaterEqual(build_section.count(
            'release_require_clean_tree || exit "$?"'), 2)
        self.assertIn("exact candidate", build_section)

    def test_publication_uploads_verified_paths_and_checks_remote_names(self):
        phase3 = self.skill[self.skill.index("## Phase 3") :]
        self.assertIn("RELEASE_ASSET_PATHS_FILE", phase3)
        self.assertIn('while IFS= read -r asset', phase3)
        self.assertIn('set -- "$@" "$asset"', phase3)
        self.assertIn('"$@"', phase3)
        self.assertIn("--json url,isDraft,tagName,assets", phase3)
        self.assertIn(".assets[].name", phase3)
        self.assertIn("cmp -s", phase3)
        self.assertIn("exactly the declared asset names", phase3)

    def test_dry_run_never_executes_the_release_build(self):
        dry_run = self.skill[
            self.skill.index("## Dry run") : self.skill.index("## Phase 2")]
        self.assertIn("$RELEASE_BUILD", dry_run)
        self.assertIn("listed", dry_run)
        self.assertIn("never executed", dry_run)

    def test_dry_run_skips_fetch_and_does_not_claim_a_suite_verdict(self):
        dry_run = self.skill[
            self.skill.index("## Dry run") : self.skill.index("## Phase 2")]
        self.assertIn("do not run either `git fetch` command", dry_run)
        self.assertIn("current local refs", dry_run)
        self.assertIn("does not execute `commit-gate`", dry_run)
        self.assertNotIn("red suite", dry_run)

    def test_first_release_adoption_floor_precedes_classification(self):
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Dry run")]
        self.assertIn("EFFECTIVE_WINDOW", phase1)
        self.assertLess(phase1.index("adoption-commit"),
                        phase1.index("then run `git -C"))
        self.assertIn('${ADOPTED}^..HEAD', phase1)
        self.assertIn("root commit", phase1)

    def test_zero_tag_probe_normalizes_only_show_ref_exit_one(self):
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        self.assertIn("SHOW_REF_STATUS", phase2)
        self.assertIn('[ "$SHOW_REF_STATUS" -ne 1 ]', phase2)
        self.assertIn("set -euo pipefail", phase2)

    def test_guarded_zero_tag_probe_executes_under_pipefail(self):
        bash = (core_releaselib._resolve_posix_shell()
                if os.name == "nt" else working_bash())
        if bash is None:
            self.skipTest("no working POSIX shell")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [core_releaselib.git_executable(), "init", "--quiet", tmp],
                check=True, capture_output=True)
            script = r'''
set -euo pipefail
cd "$1"
TAG_REFS_FILE=$(mktemp)
SHOW_REF_STATUS=0
git show-ref --tags -d > "$TAG_REFS_FILE" || SHOW_REF_STATUS=$?
if [ "$SHOW_REF_STATUS" -ne 0 ] && [ "$SHOW_REF_STATUS" -ne 1 ]; then
  rm -f -- "$TAG_REFS_FILE"
  exit "$SHOW_REF_STATUS"
fi
TAG_SHA=$("$2" "$3" peel-tag v0.1.0 < "$TAG_REFS_FILE")
rm -f -- "$TAG_REFS_FILE"
test -z "$TAG_SHA"
'''
            result = subprocess.run(
                [bash, "-s", "--", Path(tmp).as_posix(),
                 Path(sys.executable).as_posix(),
                 Path(_CORE_RELEASELIB_PATH).as_posix()],
                input=script.encode(), capture_output=True, timeout=60)
            self.assertEqual(
                result.returncode, 0,
                (result.stdout + result.stderr).decode(errors="replace"))

    def test_payload_pathspecs_are_loaded_with_argument_boundaries(self):
        targets = self.skill[
            self.skill.index("## Targets") : self.skill.index("## Back-fill")]
        self.assertIn("PAYLOAD_PATHS_FILE", targets)
        self.assertIn('while IFS= read -r pathspec', targets)
        self.assertIn('set -- "$@" "$pathspec"', targets)
        self.assertIn('"$@"', targets)
        self.assertNotIn("pass it unquoted", targets)

    def test_provenance_pair_is_derived_from_one_remote_ref_snapshot(self):
        phase3 = self.skill[
            self.skill.index("## Phase 3") :
            self.skill.index("### Asset recovery for `resume_publish`")]
        step5 = phase3[phase3.index("5. **Record the tag's provenance") :]
        self.assertIn("REMOTE_TAG_REFS", step5)
        self.assertIn("peel-tag", step5)
        self.assertNotIn("git rev-parse ${TAG_PREFIX}", step5)

    def test_phase2_reconstructs_the_section_after_the_pr_boundary(self):
        # T-17 (issue #623) named this "### 2.3 Compose the tag message and
        # verify its date" as a stable substep heading; re-anchored here
        # (T-18) onto that heading rather than the old "1. Compose the
        # annotated tag message" numbered-list marker, which survived the
        # split as a leftover artifact of the former monolithic
        # single-paragraph list and is now cosmetically stray under a
        # section that has real substep numbers of its own.
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        reconstruction = phase2.index("PHASE2_SECTION_FILE")
        composition = phase2.index(
            "### 2.3 Compose the tag message and verify its date")
        self.assertLess(reconstruction, composition)
        self.assertIn("changelog-section", phase2[reconstruction:composition])
        self.assertIn("notes-match", phase2[reconstruction:composition])
        self.assertIn("dates-match", phase2[reconstruction:composition])
        self.assertIn("exact merged commit", phase2[reconstruction:composition])

    def test_phase3_validates_deterministic_inputs_before_tag_push(self):
        phase3 = self.skill[
            self.skill.index("## Phase 3") :
            self.skill.index("### Asset recovery for `resume_publish`")]
        gate = phase3.index("Deterministic publication-input gate")
        push = phase3.index("git push origin")
        self.assertLess(gate, push)
        prepush = phase3[gate:push]
        for token in ("PUBLISH_SECTION_FILE", "changelog-section",
                      "notes-match", "dates-match", "gh auth status"):
            self.assertIn(token, prepush)

    def test_hosted_candidate_is_the_release_surface_commit(self):
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        self.assertIn("HOSTED_HEAD=$(git rev-parse HEAD)", phase2)
        self.assertIn('git log --first-parent -1 --format=%H -- "$CHANGELOG"', phase2)
        self.assertIn('git rev-parse "$HOSTED_HEAD:$SURFACE"', phase2)
        self.assertIn('git hash-object "$SURFACE"', phase2)
        self.assertIn("Do not require an unchanged manifest's last-touch commit", phase2)
        self.assertIn(
            'HOSTED_PARENT=$(git rev-parse "$HOSTED_HEAD^1" 2>/dev/null)',
            phase2)
        self.assertIn('changelog-section "$PROJECT_ROOT" "$HOSTED_PARENT"', phase2)
        self.assertIn('"$INITIAL_VERSION" --allow-absent-path', phase2)
        self.assertIn('cmp -s "$PARENT_SECTION_FILE" "$PHASE2_SECTION_FILE"', phase2)
        self.assertIn("an equal section or an unreadable comparison STOPs", phase2)
        parent_probe = phase2.index(
            'changelog-section "$PROJECT_ROOT" "$HOSTED_PARENT"')
        tag = phase2.index('git tag -a "$RELEASE_TAG"')
        self.assertLess(parent_probe, tag)
        self.assertIn("restarts Phase 1", phase2)

    def test_zero_tag_execution_order_contains_no_unguarded_pipeline(self):
        phase2 = self.skill[
            self.skill.index("## Phase 2") : self.skill.index("## Phase 3")]
        warning = phase2.index("Zero-tag execution order")
        correction = phase2.index("Zero-tag correction")
        self.assertLess(warning, correction)
        self.assertIn("MUST NOT be executed", phase2[warning:correction])
        self.assertNotIn("git show-ref --tags -d |", phase2)
        self.assertIn("SHOW_REF_STATUS=0", phase2)

    def test_asset_cleanup_names_only_minted_scratch_state(self):
        phase3 = self.skill[self.skill.index("## Phase 3") :]
        cleanup = phase3[phase3.index("Clean up declared-asset scratch state") :]
        cleanup = cleanup[:cleanup.index("\n\n")]
        self.assertIn("RELEASE_ASSET_DIR", cleanup)
        self.assertIn("RELEASE_ASSET_NAMES_FILE", cleanup)
        self.assertIn("RELEASE_ASSET_PATHS_FILE", cleanup)
        self.assertNotIn("RELEASE_ASSET_RECHECK_FILE", cleanup)

    def test_automatic_publisher_consumes_explicit_merge_authorization_once(self):
        phase3 = self.skill[self.skill.index("## Phase 3") :]
        for token in (
                "explicit user instruction to merge or complete",
                "one-cohort Phase-3 authorization",
                "CI success alone never creates authorization",
                "Do not ask the user to authorize the same cohort again"):
            self.assertIn(token, phase3)

    def test_assets_are_qualified_in_hosted_prepublication_state(self):
        phase1 = self.skill[
            self.skill.index("## Phase 1") : self.skill.index("## Phase 2")]
        phase3 = self.skill[
            self.skill.index("## Phase 3") :
            self.skill.index("### Asset recovery for `resume_publish`")]
        self.assertIn("Phase 1 never supplies a Phase-3 asset", phase1)
        self.assertIn("retained exact-head CI package cohort", phase1)
        hosted_build = phase3.index("reviewed hosted qualification path")
        push = phase3.index("git push origin")
        self.assertLess(hosted_build, push)
        prepush = phase3[hosted_build:push]
        for token in ("RELEASE_ASSET_DIR", 'eval "$RELEASE_BUILD"',
                      "retained-cohort path", 'release_require_clean_tree || exit "$?"'):
            self.assertIn(token, prepush)

    def test_release_publication_requires_merged_hosted_exact_head_evidence(self):
        normalized = " ".join(self.skill.split())
        self.assertIn(
            "The release commit must merge through a pull request before any tag is composed",
            normalized)
        self.assertIn(
            "Publication requires a hosted workflow that verifies green exact-head evidence",
            normalized)
        self.assertIn(
            "A project with no qualifying hosted publisher STOPs before tag composition",
            normalized)
        self.assertNotIn(
            "A project with no hosted workflow — every fresh consumer, until it builds one — "
            "performs the steps below locally",
            self.skill)

    def test_release_establishes_one_posix_shell_on_windows(self):
        normalized = " ".join(self.skill.split())
        self.assertIn("Execution-shell contract", normalized)
        self.assertIn("Git for Windows' own `bash.exe`", normalized)
        self.assertIn("MUST NOT paste the `sh` snippets into PowerShell", normalized)
        self.assertIn("If no POSIX-compatible shell is available, STOP", normalized)

    def test_command_index_and_security_boundary_describe_the_capability(self):
        self.assertIn("declared version policy", self.command)
        self.assertIn("exact release-asset inventory", self.command)
        self.assertIn("version-policy", self.index)
        self.assertIn("release-build", self.index)
        self.assertIn("`release-build`", self.security)
        self.assertIn("clean tracked tree before and after", self.security)
        t04 = next(line for line in self.plan.splitlines()
                   if line.startswith("| T-04 |"))
        self.assertIn("`core/pysrc/releasehash.py`", t04)

    def test_lost_asset_scratch_has_a_same_tag_resume_lane(self):
        start = self.skill.index("### Asset recovery for `resume_publish`")
        end = self.skill.index("## Recovering from a bad release")
        recovery = self.skill[start:end]
        for token in (
                "resume_publish", "git rev-parse HEAD", "^{commit}",
                "check-manifests", "changelog-section", "releasehash.py\" check",
                "run-pre-tag", 'eval "$RELEASE_BUILD"',
                "retained exact-source CI package",
                "fresh publication authorization"):
            self.assertIn(token, recovery)
        self.assertNotIn("derive-version", recovery)
        self.assertNotIn("git tag -a", recovery)
        self.assertLess(recovery.index("git rev-parse HEAD"),
                        recovery.index('eval "$RELEASE_BUILD"'))
        first_clean = recovery.index('release_require_clean_tree || exit "$?"')
        confirmation = recovery.index("releasehash.py\" check")
        pre_tag = recovery.index("run-pre-tag")
        second_clean = recovery.index('release_require_clean_tree || exit "$?"', pre_tag)
        build = recovery.index('eval "$RELEASE_BUILD"')
        self.assertLess(first_clean, confirmation)
        self.assertLess(confirmation, pre_tag)
        self.assertLess(pre_tag, second_clean)
        self.assertLess(second_clean, build)
        self.assertNotIn("Re-enter Phase 1", self.skill)

    def test_asset_cleanup_occurs_only_after_successful_remote_readback(self):
        phase3 = self.skill[self.skill.index("## Phase 3") :]
        readback = phase3.index("--json url,isDraft,tagName,assets")
        cleanup = phase3.index('rm -rf -- "$RELEASE_ASSET_DIR"')
        self.assertLess(readback, cleanup)
        self.assertIn("only after both metadata and inventory read-back pass",
                      phase3)
        self.assertIn("preserve the directory and scratch files", phase3)


# --------------------------------------------------------------------------- #
# T-18 (issue #623, AC-13/AC-14): source-only structural proof for T-17's
# twelve named Phase-2 substeps. `ReleaseSurfaceTest`/`GovernanceSurvivalTest`
# prove individual obligations SURVIVE (content); this proves the substep
# SKELETON itself is complete and correctly ordered. Deliberately scoped to
# `core/surface/skills/release/SKILL.md` alone, never the three rendered host
# payloads under `plugins/*` -- those are regenerated by T-19, not this task,
# and until then they still carry the OLD, unsplit single-paragraph form with
# none of these `### 2.x` headings. A rule or check anchored on this new
# substep-only prose would report every rendered payload as missing it and go
# red for a reason that is not an actual regression -- see the invariant
# map's own note on this at .codearbiter/reports/release-closure-invariant-
# map.md and T-17's diff comment on `_GOVERNANCE_RULES`.
#
# Each check below is factored as a pure module-level predicate over an
# arbitrary `text` argument (mirroring `_missing_governance_rules_for`'s
# pattern) precisely so it can be mutation-checked against a SCRATCH COPY of
# the real Phase-2 text without ever editing SKILL.md itself.
# --------------------------------------------------------------------------- #

_PHASE2_SUBSTEP_HEADINGS = (
    "### 2.0 Bind the hosted candidate to the release-surface commit",
    "### 2.1 Reconstruct Phase 1's section in the hosted checkout",
    "### 2.2 Resolve `<tag_exists>` and `<tag_sha>` from the guarded ref snapshot",
    "### 2.3 Compose the tag message and verify its date",
    "### 2.4 Classification precedes tagging (ordering rule)",
    "### 2.5 Source the remaining `classify` arguments",
    "### 2.6 Read `<manifest_version>` in its declared format",
    "### 2.7 Derive `<release_nondraft>` from the Release, never guessed",
    "### 2.8 Invoke `classify` with all six sourced arguments",
    "### 2.9 `publish_fresh`: create the tag — the sole tag-creation point",
    "### 2.10 Verify the stored tag round-tripped",
    "### 2.11 Handle the remaining classification outcomes",
)


def _phase2_substep_order_violations(text):
    """`(missing, out_of_order)` for `_PHASE2_SUBSTEP_HEADINGS` against
    `text`: `missing` lists any heading absent outright; `out_of_order` is
    True when every heading is present but not in the declared fixed
    sequence. A pure function of `text` -- never reads a file itself -- so
    it can be exercised against a real skill slice AND a synthetic or
    mutated fixture, the same discipline `_missing_governance_rules_for`
    uses for the pinned-phrase rules above."""
    positions = []
    missing = []
    for heading in _PHASE2_SUBSTEP_HEADINGS:
        idx = text.find(heading)
        if idx == -1:
            missing.append(heading)
        else:
            positions.append(idx)
    out_of_order = bool(positions) and positions != sorted(positions)
    return missing, out_of_order


class Phase2StructureTest(unittest.TestCase):
    """T-18 (AC-13, "no competing executable correction paragraph exists
    afterward"; AC-14, invariant-to-evidence traceability for the substep
    SKELETON itself, not only its individual obligations)."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            REPO_ROOT, "core", "surface", "skills", "release", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            cls.skill = fh.read()
        cls.phase2 = cls.skill[
            cls.skill.index("## Phase 2") : cls.skill.index("## Phase 3")]

    def test_all_twelve_substeps_present_in_fixed_order(self):
        missing, out_of_order = _phase2_substep_order_violations(self.phase2)
        self.assertEqual(missing, [])
        self.assertFalse(
            out_of_order,
            "Phase 2's named substeps are present but not in their "
            "declared 2.0..2.11 order")

    def test_a_mutated_copy_missing_one_substep_is_detected(self):
        # Mutation-check, run against a SCRATCH COPY, never SKILL.md
        # itself: delete one heading (standing in for a future edit that
        # silently drops a substep) and confirm the same predicate this
        # class trusts actually reports it missing -- proving the check is
        # not vacuously true.
        target = _PHASE2_SUBSTEP_HEADINGS[5]
        self.assertEqual(self.phase2.count(target), 1)
        mutant = self.phase2.replace(target, "", 1)
        missing, _ = _phase2_substep_order_violations(mutant)
        self.assertEqual(missing, [target])

    def test_a_mutated_copy_with_swapped_substep_order_is_detected(self):
        # Swap "2.4 Classification precedes tagging" and "2.9 ... create
        # the tag" -- a mutation that keeps every heading present but
        # silently inverts the exact ordering rule G5 (T-18) pins in prose
        # ("classify first, then tag"). Confirms the predicate catches
        # reordering, not only outright deletion.
        a, b = _PHASE2_SUBSTEP_HEADINGS[4], _PHASE2_SUBSTEP_HEADINGS[9]
        self.assertEqual(self.phase2.count(a), 1)
        self.assertEqual(self.phase2.count(b), 1)
        placeholder = "\0PHASE2_SWAP_PLACEHOLDER\0"
        mutant = (self.phase2.replace(a, placeholder)
                  .replace(b, a).replace(placeholder, b))
        missing, out_of_order = _phase2_substep_order_violations(mutant)
        self.assertEqual(missing, [])
        self.assertTrue(out_of_order)

    def test_report_authorization_handoff_and_gate_close_phase2_in_fixed_order(self):
        last_substep = self.phase2.rindex(_PHASE2_SUBSTEP_HEADINGS[-1])
        report = self.phase2.index("**Report.**")
        handoff = self.phase2.index("**Authorization handoff.**")
        gate = self.phase2.index(
            "Gate: the hosted publisher has composed the annotated tag")
        self.assertLess(last_substep, report)
        self.assertLess(report, handoff)
        self.assertLess(handoff, gate)

    def test_split_replaces_rather_than_duplicates_the_old_monolithic_item(self):
        # AC-13: "no competing executable correction paragraph exists
        # afterward." Source-only (T-17's own new lead sentence, not
        # carried into the stale rendered payloads -- see this section's
        # header comment), so this belongs here, not in
        # `_GOVERNANCE_RULES`.
        self.assertIn(
            "the former 9,324-character single item is replaced, not "
            "duplicated alongside these", self.phase2)
        # The removed monolithic paragraph no longer exists as a single
        # unbroken block: no run of non-newline characters in Phase 2
        # approaches its former length. A generous ceiling well under the
        # old 9,324 chars, so this only fires if a future edit actually
        # re-collapses several substeps back into one giant paragraph.
        longest_line = max((len(line) for line in self.phase2.splitlines()),
                            default=0)
        self.assertLess(longest_line, 4000)


class PrerequisiteRefusalSurfaceTest(unittest.TestCase):
    """T-12, AC-10/P6 (#570 R4-08/R8-05/R8-06/R10-08, cross-referenced in
    .codearbiter/reports/release-closure-triage.md): the actual routed
    `commit-gate`'s prerequisites are checked, and are checkable to fail,
    BEFORE either lane writes a single tracked file -- never after a
    changelog roll, a manifest bump, or a declared-target write already
    committed the lane to a state `commit-gate` would then refuse deep
    inside Phase 1 step 7 or Back-fill's own commit. `commit-gate`'s own
    SKILL.md Pre-flight is the source of truth for what "prerequisite"
    concretely means here -- a readable `.codearbiter/tech-stack.md`
    ("Stop if missing; do not guess") and a resolvable git repository --
    never an invented check, and never a replacement for `commit-gate`
    itself."""

    @classmethod
    def setUpClass(cls):
        def read(*parts):
            with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as fh:
                return fh.read()

        cls.skill = read("core", "surface", "skills", "release", "SKILL.md")
        cls.command = read("core", "surface", "commands", "release.md")
        cls.gate = read("core", "surface", "skills", "commit-gate", "SKILL.md")
        cls.backfill = cls.skill[
            cls.skill.index("## Back-fill"): cls.skill.index("## Pre-flight")]
        cls.preflight = cls.skill[
            cls.skill.index("## Pre-flight"): cls.skill.index("## Phase 1")]

    def test_prerequisite_derives_from_commit_gates_own_preflight(self):
        # Never an invented verification command: the exact prerequisite
        # this skill checks for must be the one `commit-gate` itself states.
        self.assertIn("Stop if missing; do not guess.", self.gate)
        self.assertIn(".codearbiter/tech-stack.md", self.gate)

    def test_backfill_checks_tech_stack_before_minting_the_marker_or_writing(self):
        check = self.backfill.index(".codearbiter/tech-stack.md")
        marker_mint = self.backfill.index("mkdir -p")
        write = self.backfill.index("Write the confirmed block verbatim")
        self.assertLess(check, marker_mint)
        self.assertLess(check, write)
        window = self.backfill[check:marker_mint]
        self.assertIn("context-creation", window)
        self.assertIn("STOP", window)
        self.assertIn("commit-gate", window)

    def test_preflight_checks_tech_stack_before_any_write(self):
        check = self.preflight.index(".codearbiter/tech-stack.md")
        rebuild = self.preflight.index('eval "$REBUILD"')
        self.assertLess(check, rebuild)
        window = self.preflight[check:check + 900]
        self.assertIn("context-creation", window)
        self.assertIn("STOP", window)
        self.assertIn("commit-gate", window)
        # And every Phase 1 write (the manifest bump, the changelog roll)
        # lives entirely after Pre-flight closes, so the check above also
        # precedes those.
        phase1 = self.skill[self.skill.index("## Phase 1"):]
        self.assertGreater(
            phase1.index("Set every path in `$MANIFEST` to the derived version"),
            0)

    def test_step7_cross_references_the_preflight_check_rather_than_repeating_it(self):
        step7 = self.skill[
            self.skill.index("7. **Commit the release edits"):
            self.skill.index("8. **Resolve declared publication assets")]
        self.assertIn("Pre-flight above already confirmed", step7)
        self.assertNotIn(".codearbiter/tech-stack.md", step7)

    def test_never_invents_a_verification_command(self):
        for lane in (self.backfill, self.preflight):
            idx = lane.index(".codearbiter/tech-stack.md")
            snippet = lane[idx:idx + 400]
            self.assertIn('[ -f "', snippet)

    def test_diagnostic_names_a_real_next_action_not_a_silent_onboarding(self):
        for lane in (self.backfill, self.preflight):
            idx = lane.index(".codearbiter/tech-stack.md")
            snippet = lane[idx:idx + 900]
            self.assertIn("context-creation", snippet)
            self.assertNotIn("automatically run", snippet)
            self.assertNotIn("silently", snippet)

    def test_check_never_claims_to_bypass_or_replace_commit_gate(self):
        for lane in (self.backfill, self.preflight):
            idx = lane.index(".codearbiter/tech-stack.md")
            snippet = lane[idx:idx + 900]
            self.assertNotIn("skip commit-gate", snippet)
            self.assertNotIn("bypass commit-gate", snippet)
            self.assertIn("commit-gate", snippet)

    def test_honesty_wording_scopes_the_skip_onboarding_claim(self):
        self.assertIn("not a guarantee that no other", self.preflight)
        self.assertNotIn(
            "that lane's entire purpose is letting a release-only consumer "
            "skip full onboarding, so its absence here is not itself a STOP",
            self.preflight)

    def test_never_described_as_a_fully_onboarding_free_release(self):
        for lane in (self.backfill, self.preflight):
            idx = lane.index(".codearbiter/tech-stack.md")
            snippet = lane[idx:idx + 900]
            self.assertIn("not a new onboarding-free", snippet)


if __name__ == "__main__":
    unittest.main()
