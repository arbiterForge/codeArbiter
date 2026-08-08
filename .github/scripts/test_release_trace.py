#!/usr/bin/env python3
"""codeArbiter — the A-1.11 resolution trace (issue #563, T-27a..d).

The migration split `.github/scripts/_releaselib.py`'s repo-specific facts and
mechanism into `core/pysrc/_releaselib.py` plus a declared
`.codearbiter/release-targets.md` file. This module is the proof that the
split changed NOTHING about what a release lane resolves, built in four
steps (`.codearbiter/plans/portable-release-and-protected-state.md`,
T-27a..d; spec A-1.11):

  FixtureShapeTest    T-27a — a frozen, synthetic fixture (tag list, manifest
                      files, a small commit graph, the four target rows)
                      under `.github/scripts/fixtures/release-trace/`.
  OldLaneLoadsTest    T-27b — the PRE-CHANGE `_releaselib.py` loaded from git
                      history, never from the live working tree.
  OldLaneLiveTest     T-27c — the pinned old lane, run against THIS repo's
                      real tags, resolves `ca`'s actual last release tag.
                      Per the plan: a divergence here is new evidence about
                      the pre-change lane, not a fixup target — the test
                      would fail and this file's docstring / the sprint log
                      is where that gets reported, never silently patched.
  TraceMatchesTest    T-27d — the NEW lane (core/pysrc/_releaselib.py plus
                      the declared-row loader) reproduces the OLD lane's
                      resolved-variable dict for BOTH `ca` and `ca-pi` over
                      the frozen fixture — `ca` alone would exercise neither
                      `payload-exclude`, multiple manifests, nor the
                      two-manifest ca-pi shape, the three behaviors most
                      likely to drift in a migration.

Pre-change SHA (T-27b): `469c2fb8` — the parent of `8ee5fe11` (the squash
merge that performed the mechanism split), i.e. the last reachable main
commit at which `.github/scripts/_releaselib.py` was still the ORIGINAL
self-contained module. Its module blob is byte-identical to the abandoned
feature-branch parent originally used here. Chosen over "origin/main's copy"
because origin/main moves and a SHA does not; pinning to the reachable
pre-merge commit is the tightest fresh-clone-safe reference the spec's
`git show <pre-change-sha>:...` instruction asks for.

Honest limit (stated once here, per the spec's own wording, rather than
repeated at every call site): `.github/scripts/_releaselib.py` at the
pre-change SHA had no declared-row schema at all — its target register
(`RELEASE_TARGETS`, `RELEASE_TAG_PREFIXES`) was a Python constant, and each
target's manifest path(s) and artifact list existed ONLY as prose in
`plugins/ca/skills/release/SKILL.md`'s Targets table. Reproducing "the old
lane's resolved variables" for a manifest path or artifact list therefore
means TRANSCRIBING that prose into this test file (`_OLD_LANE_TRANSCRIBED`
below) exactly as a maintainer authoring this migration would have read it
off the table by hand. This narrows the oracle problem — a genuine
transcription error would still show up as a self-consistent mismatch — but
does not eliminate it: nothing here can catch a fact the Targets table
itself had wrong before this migration began.

A second, separate honest limit, specific to `WINDOW_COMMITS`: window
derivation (`git log <LAST_TAG>..HEAD`) has never lived inside
`_releaselib.py` in either its pre-change or portable form — it is release
SKILL prose, not a mechanism function the split touched — so both lanes
below compute it with the SAME shared `_window_commits` walk over the SAME
frozen graph, differing only in which `LAST_TAG` (and therefore which
`last_tag_sha`) each lane resolves. `WINDOW_COMMITS` therefore carries no
INDEPENDENT discriminating power of its own: it can only diverge between the
two lanes if `LAST_TAG` has already diverged, which the dict asserts
separately. It is still recorded, because A-1.11 names "window commit set"
as one of the five resolved variables to trace, and its frozen value is a
real baseline for slice 3 (`payload-exclude`, A-3.4) to diverge from once
window derivation actually changes — but a passing `trace_matches` test is
NOT independent evidence that window derivation itself is correct or
unchanged, only that `LAST_TAG` agrees. The fixture's commit graph does
include one merge commit (`b1` merged into `c6`) specifically so an
all-parents graph walk is exercised over a first-parent-only one within
`WINDOW_COMMITS` itself (see `WindowCommitsTest`), which is a genuine,
narrower property `WINDOW_COMMITS` alone can still fail on.

`ThisRepoStillReleasesTest` (T-77, spec A-6.7) — the same two lanes, extended
from the frozen fixture to LIVE-repo HEAD: real tags (`git tag --list`), the
real `.codearbiter/release-targets.md` declared rows (the NEW lane) against
a hand-transcribed set of the same facts (the OLD lane, exactly as
`_OLD_LANE_TRANSCRIBED` above does for the fixture), real manifests, real
CHANGELOGs, and a composed tag **message file** — with `notes-match` and
`dates-consistent` run against it, the same guards Phase 3 applies before
publishing. It creates **zero refs**: no `git tag`, no branch, nothing
committed to this repository. The message file is a plain OS temp file
outside the repository, read back and diffed against the in-memory string
to prove the round trip is lossless, then removed.

Four honest limits carry over, restated for the live-HEAD case:

1. The transcription problem is the same as `_OLD_LANE_TRANSCRIBED`'s: the
   OLD lane's manifest/changelog/payload facts for each live target exist
   only as prose (this repo's `release/SKILL.md` Targets table), so they
   enter this test by hand-transcription rather than being read from
   anywhere the pre-change lane could read them. A transcription error would
   surface as a self-consistent mismatch, but nothing here can catch a fact
   the Targets table itself had wrong.
2. `WINDOW_COMMITS`' "no independent discriminating power" limit applies
   here unchanged, now over a REAL `git log` walk instead of a frozen graph:
   both lanes share one subprocess call, differing only in which `LAST_TAG`
   each resolves.
3. `last_tag_select`'s marker-scope divergence (AC-1.12) is intentional and
   is not re-asserted here — `PrereleaseMarkerScopeDivergenceTest` above
   already covers it against the frozen fixture; none of this repo's four
   real prefixes carry a marker substring, so live HEAD cannot exercise it.
4. **New for T-77**: the tag-message COMPOSITION rule itself (Phase-1
   section text plus a `Released-at: DATE` footer) is release-SKILL prose,
   not a `_releaselib` function in either lane — there is no
   `compose_tag_message` in the pre-change module or the portable one. Both
   lanes below therefore share ONE test-local composer, exactly the same
   shared-helper pattern as `_window_commits`, and differ only in which
   CHANGELOG TEXT and which MANIFEST VERSION each lane resolved — the
   composition arithmetic itself carries no independent discriminating
   power and a bug in `_compose_tag_message` would pass on both lanes
   identically. What genuinely discriminates is covered by direct,
   single-lane assertions (`assertTrue`/`assertFalse` against one lane's
   real return value), never only by comparing the two lanes' shared-helper
   output to each other.

**Manifest/changelog reconciliation is asserted, not assumed, for every
live target this class checks.** A plugin's manifest version bumps on
every merged feat/fix PR (this campaign's own per-PR version-gate
convention); its CHANGELOG section is written by hand as part of
publishing, on a separate, slower cadence. The two mechanisms can
therefore run apart between merges — `plugin.json` ahead of the newest
`## [X.Y.Z]` CHANGELOG heading — and `/release`'s Phase 1 BLOCKS exactly
when they do. `NEXT_VERSION` is read from the MANIFEST throughout (Phase 1
step 3's own contract: derive the version, then assert it EQUALS the
manifest), never redefined as "whichever version the changelog's newest
heading already names" merely to make a mismatch disappear — so this test
asserts the two agree for `ca` and `ca-pi` alike, the same live guard
`/release` itself applies, rather than branching on whichever state
happens to hold when the suite runs and reporting green either way. A
future failure here means the mechanism has diverged again: the fix is to
add the missing CHANGELOG section, never to relax this assertion.

Stdlib only. No side effects at import beyond loading the two `_releaselib`
copies, which is dynamic module loading, not a mutation.
`ThisRepoStillReleasesTest` reads real repo files (no side effect:
read-only) and writes one plain temp file OUTSIDE this repository, via
`tempfile`, removed in `tearDown`.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURE_DIR = os.path.join(HERE, "fixtures", "release-trace")

# T-27b: the parent of 8ee5fe11 (the mechanism-split squash merge) — see
# the module docstring for why this reachable SHA was chosen.
PRE_CHANGE_SHA = "469c2fb82555346a739ab72a0f7284f22874aa3e"

CORE_RELEASELIB_PATH = os.path.join(REPO_ROOT, "core", "pysrc", "_releaselib.py")
SHIM_RELEASELIB_PATH = os.path.join(REPO_ROOT, ".github", "scripts", "_releaselib.py")


def setUpModule():
    """Preflight (HIGH-2, adversarial review 2026-07-31): this whole module
    needs FULL git history (`OldLaneLoadsTest`/`TraceMatchesTest` `git show`
    a specific historical commit) AND the complete tag set
    (`OldLaneLiveTest`'s real-repo cross-check). A shallow, tag-less
    checkout -- `actions/checkout`'s default -- fails both, but silently and
    confusingly downstream: `git show <sha>:...` raises a bare "invalid
    object name", and an empty tag list makes `OldLaneLiveTest` report "the
    live repo has no bare v*.*.* tag", neither of which names the actual
    cause or the fix. This raises loudly and names both, rather than
    letting either symptom stand as its own diagnosis -- and it is a hard
    failure, never a skip: a skip here would recreate exactly the "a green
    job can measure nothing" failure mode this suite exists to avoid."""
    has_commit = subprocess.run(
        ["git", "cat-file", "-e", f"{PRE_CHANGE_SHA}^{{commit}}"],
        cwd=REPO_ROOT, capture_output=True, timeout=30).returncode == 0
    tags = subprocess.run(
        ["git", "tag", "--list"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    has_tags = bool(tags.stdout.strip())
    if not has_commit or not has_tags:
        missing = []
        if not has_commit:
            missing.append(f"commit {PRE_CHANGE_SHA} is unreachable from this checkout")
        if not has_tags:
            missing.append("no tags are present")
        raise RuntimeError(
            "test_release_trace.py needs full git history AND all tags to "
            "run (" + "; ".join(missing) + "). The checkout step invoking "
            "this suite must set `fetch-depth: 0` and `fetch-tags: true` -- "
            "a default `actions/checkout` shallow clone satisfies neither.")

# T-27d's transcription of facts that existed ONLY as prose in the pre-change
# lane (see the module docstring's "Honest limit"). These mirror the SAME
# paths declared in fixtures/release-trace/release-targets.md's [ca] and
# [ca-pi] blocks, transcribed by hand rather than read from that file, since
# the pre-change lane had no file to read them from.
_OLD_LANE_TRANSCRIBED = {
    "ca": {
        "manifests": ["manifests/ca-plugin.json"],
        "artifacts": ["ca/tools/farm.js"],
    },
    "ca-pi": {
        "manifests": ["manifests/ca-pi-package.json",
                      "manifests/ca-pi-root-package.json"],
        "artifacts": ["ca-pi/extensions/codearbiter.js",
                      "ca-pi/extensions/codearbiter-child.js"],
    },
}


def _load_core_lane():
    """Load core/pysrc/_releaselib.py (the portable mechanism) under a
    private module name, registered in sys.modules so introspection works."""
    spec = importlib.util.spec_from_file_location(
        "_trace_core_releaselib", CORE_RELEASELIB_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_old_lane(sha=PRE_CHANGE_SHA):
    """Load `.github/scripts/_releaselib.py` AS IT STOOD at `sha`, via `git
    show <sha>:.github/scripts/_releaselib.py` — never the live working
    tree, so this reference is immune to any future edit of the shim
    (including the one this very migration makes)."""
    result = subprocess.run(
        ["git", "show", f"{sha}:.github/scripts/_releaselib.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"could not load the pre-change _releaselib.py at {sha!r}: "
            f"{result.stderr}")
    module = types.ModuleType("_trace_old_releaselib")
    module.__file__ = f"git-show:{sha}:.github/scripts/_releaselib.py"
    sys.modules[module.__name__] = module
    exec(compile(result.stdout, module.__file__, "exec"), module.__dict__)
    return module


def _read_manifest_version(rel_path, base=FIXTURE_DIR):
    with open(os.path.join(base, rel_path), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def _ancestors_inclusive(commit_graph, sha):
    """Every commit reachable from `sha` by following `parents`, `sha`
    included. Pure graph walk — this is `git log <ref>` restricted to
    ancestry, transcribed once and shared by BOTH lanes below, since window
    derivation has never lived inside `_releaselib.py` in either its
    pre-change or portable form (it is release-skill PROSE, `git log
    <LAST_TAG>..HEAD`) and so is not something the migration could have
    changed."""
    parents = {c["sha"]: c["parents"] for c in commit_graph["commits"]}
    seen = set()
    stack = [sha]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(parents.get(cur, []))
    return seen


def _window_commits(commit_graph, last_tag_sha, head_sha):
    """The `git log <LAST_TAG>..HEAD` window: ancestors of `head_sha` minus
    ancestors-or-self of `last_tag_sha`. `last_tag_sha` of `None` (no prior
    release — the NONE_SENTINEL case) excludes nothing, matching a
    first-release baseline."""
    excluded = _ancestors_inclusive(commit_graph, last_tag_sha) if last_tag_sha else set()
    included = _ancestors_inclusive(commit_graph, head_sha)
    return included - excluded


def _load_fixture():
    with open(os.path.join(FIXTURE_DIR, "tags.txt"), encoding="utf-8") as fh:
        tags = [line.strip() for line in fh if line.strip()]
    with open(os.path.join(FIXTURE_DIR, "commit-graph.json"), encoding="utf-8") as fh:
        commit_graph = json.load(fh)
    return tags, commit_graph


def _old_lane_dict(old_lane, tags, commit_graph, target):
    prefix = old_lane.RELEASE_TAG_PREFIXES[target]
    last_tag = old_lane.last_tag_select(tags, prefix)
    last_tag_sha = commit_graph["tag_refs"].get(last_tag)
    window = _window_commits(commit_graph, last_tag_sha, commit_graph["head"])
    facts = _OLD_LANE_TRANSCRIBED[target]
    return {
        "TAG_PREFIX": prefix,
        "LAST_TAG": last_tag,
        "WINDOW_COMMITS": sorted(window),
        "MANIFEST_VERSIONS": [_read_manifest_version(p) for p in facts["manifests"]],
        "ARTIFACTS": list(facts["artifacts"]),
    }


def _new_lane_dict(core_lane, rows_by_target, tags, commit_graph, target):
    row = rows_by_target[target]
    prefix = row["prefix"]
    last_tag = core_lane.last_tag_select(tags, prefix)
    last_tag_sha = commit_graph["tag_refs"].get(last_tag)
    window = _window_commits(commit_graph, last_tag_sha, commit_graph["head"])
    return {
        "TAG_PREFIX": prefix,
        "LAST_TAG": last_tag,
        "WINDOW_COMMITS": sorted(window),
        "MANIFEST_VERSIONS": [_read_manifest_version(p) for p in row["manifest"]],
        "ARTIFACTS": list(row["artifacts"]),
    }


def _first_parent_only_ancestors(commit_graph, sha):
    """A DELIBERATELY WRONG walk — follows only each commit's FIRST parent,
    the plausible bug `_ancestors_inclusive` above must not have. Used only
    by WindowCommitsTest to prove the fixture's merge commit (`b1`) gives
    WINDOW_COMMITS genuine discriminating power, per the module docstring's
    WINDOW_COMMITS honest limit."""
    parents = {c["sha"]: c["parents"] for c in commit_graph["commits"]}
    seen = set()
    cur = sha
    while cur is not None and cur not in seen:
        seen.add(cur)
        cur = parents.get(cur, [None])[0] if parents.get(cur) else None
    return seen


class WindowCommitsTest(unittest.TestCase):
    """Not one of the four named T-27a..d verifications, but load-bearing for
    the WINDOW_COMMITS honest limit recorded in the module docstring: proves
    the fixture's merge commit (`b1`) actually gives `_window_commits`
    something to fail on, rather than the straight-line graph a first-parent-
    only walk would pass unnoticed."""

    @classmethod
    def setUpClass(cls):
        _, cls.commit_graph = _load_fixture()

    def test_window_commits_includes_the_merged_branch_commit(self):
        # ca's window: LAST_TAG=v1.1.0 at c4, HEAD=c6. b1 branches off c4 and
        # merges into c6 alongside c5, so a correct all-parents walk must
        # include it.
        window = _window_commits(self.commit_graph, "c4", "c6")
        self.assertIn("b1", window)
        self.assertEqual(window, {"c5", "b1", "c6"})

    def test_a_first_parent_only_walk_would_silently_drop_it(self):
        # The property WINDOW_COMMITS actually has independent power to
        # catch: a first-parent-only ancestor walk over the SAME fixture
        # produces a DIFFERENT (wrong) window, because it never visits `b1`
        # (c6's second parent) at all.
        correct = _ancestors_inclusive(self.commit_graph, "c6") - \
            _ancestors_inclusive(self.commit_graph, "c4")
        broken = _first_parent_only_ancestors(self.commit_graph, "c6") - \
            _first_parent_only_ancestors(self.commit_graph, "c4")
        self.assertNotEqual(correct, broken)
        self.assertIn("b1", correct)
        self.assertNotIn("b1", broken)


class FixtureShapeTest(unittest.TestCase):
    """T-27a: the frozen fixture carries a tag list, manifest files, a small
    commit graph, and the four target rows, and they agree with each
    other."""

    @classmethod
    def setUpClass(cls):
        cls.tags, cls.commit_graph = _load_fixture()
        cls.core_lane = _load_core_lane()
        cls.rows = cls.core_lane.load_targets(
            os.path.join(FIXTURE_DIR, "release-targets.md"))
        cls.rows_by_target = {row["target"]: row for row in cls.rows}

    def test_fixture_shape_tag_list_matches_the_commit_graphs_tag_refs(self):
        self.assertEqual(set(self.tags), set(self.commit_graph["tag_refs"]))

    def test_fixture_shape_commit_graph_is_well_formed(self):
        shas = {c["sha"] for c in self.commit_graph["commits"]}
        self.assertIn(self.commit_graph["head"], shas)
        for commit in self.commit_graph["commits"]:
            for parent in commit["parents"]:
                with self.subTest(commit=commit["sha"], parent=parent):
                    self.assertIn(parent, shas)
        for tag, sha in self.commit_graph["tag_refs"].items():
            with self.subTest(tag=tag):
                self.assertIn(sha, shas)

    def test_fixture_shape_four_rows_present(self):
        self.assertEqual(
            set(self.rows_by_target), {"ca", "ca-codex", "ca-sandbox", "ca-pi"})

    def test_fixture_shape_manifest_files_exist_and_parse(self):
        for target, row in self.rows_by_target.items():
            for rel in row["manifest"]:
                with self.subTest(target=target, path=rel):
                    version = _read_manifest_version(rel)
                    self.assertIsInstance(version, str)
                    self.assertTrue(version)

    def test_fixture_shape_ca_pi_has_two_manifests_and_a_payload_exclude(self):
        row = self.rows_by_target["ca-pi"]
        self.assertEqual(len(row["manifest"]), 2)
        self.assertEqual(row["payload_exclude"], ["ca-pi/tools/"])

    def test_fixture_shape_only_ca_is_latest_eligible(self):
        for target, row in self.rows_by_target.items():
            with self.subTest(target=target):
                self.assertEqual(row["latest_eligible"], target == "ca")


class OldLaneLoadsTest(unittest.TestCase):
    """T-27b: the pre-change `_releaselib.py`, loaded from git history at
    the pinned SHA, never from the live working tree."""

    @classmethod
    def setUpClass(cls):
        cls.old_lane = _load_old_lane()

    def test_old_lane_loads_the_pinned_pre_change_module(self):
        self.assertEqual(
            self.old_lane.RELEASE_TARGETS,
            ("ca", "ca-codex", "ca-sandbox", "ca-pi"))
        self.assertEqual(
            self.old_lane.RELEASE_TAG_PREFIXES,
            {"ca": "v", "ca-codex": "ca-codex-v",
             "ca-sandbox": "ca-sandbox-v", "ca-pi": "ca-pi-v"})
        self.assertTrue(callable(self.old_lane.last_tag_select))

    def test_pinned_pre_change_commit_is_reachable_from_head(self):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", PRE_CHANGE_SHA, "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(
            result.returncode, 0,
            f"{PRE_CHANGE_SHA} is not reachable from HEAD; a fresh full-history "
            "checkout cannot load the pinned pre-change module")

    def test_old_lane_loads_a_genuinely_historical_snapshot(self):
        # Proves this is really pinned to git history and not accidentally
        # reading the live (now-converted) shim: the pre-change source must
        # differ from the current shim's source (T-25 rewrote it), and the
        # loaded module must carry no reference to the portable mechanism
        # module the live shim now re-exports from.
        with open(SHIM_RELEASELIB_PATH, encoding="utf-8") as fh:
            live_shim_text = fh.read()
        result = subprocess.run(
            ["git", "show", f"{PRE_CHANGE_SHA}:.github/scripts/_releaselib.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout, live_shim_text)
        self.assertNotIn("core/pysrc", result.stdout)
        self.assertFalse(hasattr(self.old_lane, "load_targets"))


class OldLaneLiveTest(unittest.TestCase):
    """T-27c: the pinned old lane, run against THIS repo's REAL tags,
    resolves `ca`'s actual last release tag. Per the plan, a divergence here
    is new evidence about the pre-change lane, not a fixup target for this
    test — it is left to fail loudly rather than adjusted to match."""

    @classmethod
    def setUpClass(cls):
        cls.old_lane = _load_old_lane()
        result = subprocess.run(
            ["git", "tag", "--list"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"could not list live repo tags: {result.stderr}")
        cls.live_tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    @staticmethod
    def _independent_last_ca_tag(tags):
        # A deliberately SEPARATE oracle: its own regex, its own max logic,
        # sharing no code with _releaselib.py (old or new) — so agreement
        # with the pinned old lane is real cross-validation, not comparing
        # the thing against a copy of itself.
        import re
        rx = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
        best = None
        for tag in tags:
            match = rx.match(tag)
            if not match:
                continue
            version = tuple(int(part) for part in match.groups())
            if best is None or version > best[0]:
                best = (version, tag)
        return best[1] if best else None

    def test_old_lane_live_resolves_cas_real_last_tag(self):
        resolved = self.old_lane.last_tag_select(self.live_tags, "v")
        expected = self._independent_last_ca_tag(self.live_tags)
        self.assertIsNotNone(
            expected, "the live repo has no bare v*.*.* tag to validate against")
        self.assertEqual(
            resolved, expected,
            "the pinned pre-change _releaselib.py disagrees with an "
            "independently-computed oracle over this repo's REAL tags — "
            "per the plan (T-27c) this is a STOP: investigate the "
            "transcription or the pre-change lane, do not adjust this test "
            "to match.")

    def test_old_lane_live_prerelease_exclusion_is_actually_exercised(self):
        # This repo's real tags alone do not exercise the anchored
        # `$`-suffix's exclusion of a HIGHER pre-release (today's highest
        # bare release, v2.8.13, already outranks every real v*-beta.* tag,
        # so a mutant that widened the anchor to admit a pre-release would
        # pass test_old_lane_live_resolves_cas_real_last_tag by accident).
        # Injecting one synthetic higher pre-release into BOTH the pinned
        # old lane and the independent oracle, over the same real tag list,
        # makes the exclusion property genuinely load-bearing rather than
        # accidentally true. Per T-27c, a disagreement here is the same STOP
        # condition as the test above, on real information rather than a
        # coincidence of today's tag history.
        injected = self.live_tags + ["v9.9.9-beta.1"]
        resolved = self.old_lane.last_tag_select(injected, "v")
        expected = self._independent_last_ca_tag(injected)
        self.assertEqual(
            resolved, expected,
            "the pinned pre-change _releaselib.py disagrees with the "
            "independent oracle once a higher pre-release tag is present — "
            "a STOP per T-27c, not a test to adjust.")
        self.assertNotEqual(
            resolved, "v9.9.9-beta.1",
            "the injected pre-release must be EXCLUDED, not selected as the "
            "new highest tag")


class TraceMatchesTest(unittest.TestCase):
    """T-27d: the NEW lane (core/pysrc/_releaselib.py + the declared-row
    loader) reproduces the OLD lane's resolved-variable dict, over the
    frozen fixture, for BOTH `ca` and `ca-pi`."""

    @classmethod
    def setUpClass(cls):
        cls.tags, cls.commit_graph = _load_fixture()
        cls.old_lane = _load_old_lane()
        cls.core_lane = _load_core_lane()
        cls.rows_by_target = {
            row["target"]: row
            for row in cls.core_lane.load_targets(
                os.path.join(FIXTURE_DIR, "release-targets.md"))
        }

    def _assert_trace_matches(self, target):
        old = _old_lane_dict(self.old_lane, self.tags, self.commit_graph, target)
        new = _new_lane_dict(
            self.core_lane, self.rows_by_target, self.tags, self.commit_graph, target)
        self.assertEqual(old, new, f"{target}: old-lane and new-lane traces diverge")

    def test_trace_matches_ca(self):
        self._assert_trace_matches("ca")

    def test_trace_matches_ca_pi(self):
        self._assert_trace_matches("ca-pi")

    def test_trace_matches_ca_pi_exercises_two_manifests_and_payload_exclude(self):
        # Non-vacuous check: prove the ca-pi trace actually EXERCISES the two
        # behaviors A-1.11 calls out (multiple manifests, payload-exclude),
        # rather than merely happening to pass on a fixture that does not
        # touch them.
        row = self.rows_by_target["ca-pi"]
        self.assertEqual(len(row["manifest"]), 2)
        self.assertEqual(row["payload_exclude"], ["ca-pi/tools/"])
        old = _old_lane_dict(self.old_lane, self.tags, self.commit_graph, "ca-pi")
        self.assertEqual(len(old["MANIFEST_VERSIONS"]), 2)
        # M-4 (adversarial review, 2026-07-31): the two fixture manifests
        # used to carry the SAME version ("0.1.2" twice), so MANIFEST_VERSIONS
        # order was undiscriminated -- a mutant swapping the declared manifest
        # order (or `_OLD_LANE_TRANSCRIBED`'s) would still pass, since
        # ["0.1.2", "0.1.2"] == ["0.1.2", "0.1.2"] either way. The two fixture
        # files now carry DISTINCT versions ("0.1.2" / "0.1.3"), so this
        # asserts the exact, order-sensitive list rather than just its length.
        self.assertEqual(old["MANIFEST_VERSIONS"], ["0.1.2", "0.1.3"])
        new = _new_lane_dict(
            self.core_lane, self.rows_by_target, self.tags, self.commit_graph, "ca-pi")
        self.assertEqual(new["MANIFEST_VERSIONS"], ["0.1.2", "0.1.3"])

    def test_trace_matches_ca_and_ca_pi_windows_are_not_trivially_equal(self):
        # Guards against a degenerate fixture where every target resolves
        # the same window regardless of prefix, which would let a broken
        # per-series LAST_TAG resolution pass unnoticed.
        ca = _new_lane_dict(
            self.core_lane, self.rows_by_target, self.tags, self.commit_graph, "ca")
        pi = _new_lane_dict(
            self.core_lane, self.rows_by_target, self.tags, self.commit_graph, "ca-pi")
        self.assertNotEqual(ca["LAST_TAG"], pi["LAST_TAG"])
        self.assertNotEqual(ca["WINDOW_COMMITS"], pi["WINDOW_COMMITS"])


class PrereleaseMarkerScopeDivergenceTest(unittest.TestCase):
    """AC-1.12 (spec rev 4.6, `.codearbiter/specs/release-portable-fixture.md`):
    `last_tag_select` was deliberately changed during this campaign — the
    pre-release marker test moved from the WHOLE tag (old lane) to the
    prefix-STRIPPED version portion (new lane), so a consumer prefix
    containing `-beta`/`-rc`/`-alpha` no longer loses its entire series. A
    trace asserting "nothing changed" across that would be asserting
    something false; it reads as true only because none of the four real
    prefixes this repo ships (`v`, `ca-codex-v`, `ca-sandbox-v`, `ca-pi-v`)
    contains a marker substring.

    Rather than adding a fifth `release-targets.md` row (and its own
    manifest/changelog/artifact fixture files) for a series this repo does
    not ship — which would also break `FixtureShapeTest`'s four-row/
    latest-eligible assertions for no added discriminating power — the
    divergence lives entirely inside `last_tag_select`'s own marker check,
    so the narrowest fixture change that still exercises the two REAL,
    pinned lanes (T-27b's old lane loaded from git history; T-27a's core
    lane) is one marker-bearing tag declared in `tags.txt`/
    `commit-graph.json`'s `tag_refs` alongside the four real rows, plus a
    direct call to each lane's `last_tag_select`."""

    PREFIX = "web-beta-v"
    TAG = "web-beta-v1.0.0"

    @classmethod
    def setUpClass(cls):
        cls.tags, cls.commit_graph = _load_fixture()
        cls.old_lane = _load_old_lane()
        cls.core_lane = _load_core_lane()

    def test_marker_bearing_tag_is_present_in_the_frozen_fixture(self):
        self.assertIn(self.TAG, self.tags)
        self.assertIn(self.TAG, self.commit_graph["tag_refs"])

    def test_old_lane_treats_a_marker_bearing_prefix_as_never_released(self):
        # The old lane's marker check runs over the WHOLE tag: "web-beta-
        # v1.0.0" contains the literal substring "-beta", so EVERY tag in
        # this series is excluded and the series reads as never released,
        # even though a real release tag exists.
        self.assertEqual(
            self.old_lane.last_tag_select(self.tags, self.PREFIX),
            self.old_lane.NONE_SENTINEL)

    def test_new_lane_resolves_the_same_tag_the_old_lane_could_never_see(self):
        # The new lane's marker check runs over the prefix-STRIPPED version
        # portion only ("1.0.0" — no marker substring), so it correctly
        # resolves the real release tag the old lane could never surface for
        # this series. This is the INTENDED divergence AC-1.12 asks the
        # trace to state explicitly, not a regression.
        self.assertEqual(
            self.core_lane.last_tag_select(self.tags, self.PREFIX), self.TAG)


# --------------------------------------------------------------------------- #
# T-77 (spec A-6.7) — the trace apparatus extended to LIVE-repo HEAD.
# See the module docstring for the full design and its four honest limits.
# --------------------------------------------------------------------------- #

LIVE_RELEASE_TARGETS_PATH = os.path.join(REPO_ROOT, ".codearbiter", "release-targets.md")

_ANY_MD_HEADING_RE = re.compile(r"^## .*$", re.MULTILINE)
_VERSION_MD_HEADING_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?")
_HEADING_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _git(args):
    """A single, read-only `git` invocation against THIS repository's real
    working tree. Every call site below passes a read-only subcommand
    (`rev-parse`, `tag --list`, `log`, `rev-list`, `show-ref`, `status
    --porcelain`) — never `tag`, `branch`, `commit`, or `checkout` — which is
    what `ThisRepoStillReleasesTest.test_this_repo_still_releases_creates_
    zero_refs` verifies mechanically rather than asserting by code review
    alone."""
    result = subprocess.run(
        ["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def _independent_last_tag(tags, prefix):
    """A second, separate LAST_TAG oracle sharing no code with either
    `_releaselib` lane — generalizes `OldLaneLiveTest._independent_last_ca_tag`
    to an arbitrary prefix so the same real cross-validation covers ca-pi's
    `ca-pi-v` series too, not only ca's bare `v`."""
    rx = re.compile(r"^" + re.escape(prefix) + r"(\d+)\.(\d+)\.(\d+)$")
    best = None
    for tag in tags:
        m = rx.match(tag)
        if not m:
            continue
        version = tuple(int(g) for g in m.groups())
        if best is None or version > best[0]:
            best = (version, tag)
    return best[1] if best else None


def _window_pathspecs(payload, payload_exclude):
    """The pathspec list a release lane's window derivation actually walks:
    the payload itself, plus one `:(exclude)`-prefixed pathspec per declared
    `payload-exclude` entry (adversarial review 2026-07-31, HIGH-3). Without
    this, `ca-pi`'s window would include commits touching
    `plugins/ca-pi/tools/` — a path the declared row explicitly excludes
    from the release payload (it ships neither generated policy nor a built
    runtime artifact) — driving a different SemVer bump than the real
    lane. Shared by both callers below so the pathspec shape can only drift
    once, not twice."""
    return [payload] + [":(exclude)" + p for p in payload_exclude]


def _live_window_shas(last_tag, head_sha, payload, payload_exclude=()):
    """`git log <last_tag>..<head_sha> -- <payload> [:(exclude)<p> ...]`, a
    REAL subprocess call against live HEAD, for one already-resolved
    (non-sentinel) LAST_TAG. Both of T-77's live targets (`ca`, `ca-pi`)
    carry a real release tag, so the NONE_SENTINEL "no prior release"
    branch `_window_commits` (the fixture-based walk above) handles does
    not arise here."""
    out = _git(["log", "--format=%H", f"{last_tag}..{head_sha}", "--"] +
               _window_pathspecs(payload, payload_exclude))
    return [line.strip() for line in out.splitlines() if line.strip()]


def _independent_window_count(last_tag, head_sha, payload, payload_exclude=()):
    """A SEPARATE git subcommand (`rev-list --count`, not `log` parsed line
    by line) computing the same window's size, so agreement with
    `_live_window_shas` is genuine cross-validation of its line-parsing
    rather than the same command compared against itself."""
    out = _git(["rev-list", "--count", f"{last_tag}..{head_sha}", "--"] +
               _window_pathspecs(payload, payload_exclude))
    return int(out.strip())


def _first_release_section(changelog_text):
    """The first (topmost) CHANGELOG section whose heading names a real
    MAJOR.MINOR.PATCH version — skips any number of leading `## [Unreleased]`
    headings (this repo's `ca-codex`/`ca-pi` CHANGELOGs each carry several
    stacked blank ones). Returns `(version, section_text, date)` for the
    first match, `section_text` spanning from that heading up to (not
    including) the next `## ` heading or end of file; `(None, None, None)` if
    no versioned heading exists at all."""
    headings = list(_ANY_MD_HEADING_RE.finditer(changelog_text))
    for i, h in enumerate(headings):
        m = _VERSION_MD_HEADING_RE.match(h.group(0))
        if not m:
            continue
        start = h.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(changelog_text)
        section_text = changelog_text[start:end]
        date_match = _HEADING_DATE_RE.search(h.group(0))
        date = date_match.group(1) if date_match else None
        return m.group(1), section_text, date
    return None, None, None


def _compose_tag_message(section_text, released_at_date):
    """Phase 2 step 1's composition rule (`release/SKILL.md`), transcribed
    ONCE and shared by both lanes below — see the module docstring's fourth
    honest limit: the Phase-1 changelog section plus a `Released-at: DATE`
    footer. Neither the pre-change nor the portable `_releaselib.py`
    implements this; it is release-SKILL prose, not a mechanism function
    either lane owns, so this composition carries no independent
    discriminating power of its own between the two lanes."""
    return section_text.rstrip("\n") + f"\nReleased-at: {released_at_date}\n"


class ThisRepoStillReleasesTest(unittest.TestCase):
    """T-77 (spec A-6.7): the T-27 trace apparatus extended from the frozen
    fixture to LIVE-repo HEAD. See the module docstring for the full design,
    its four honest limits, and why manifest/changelog reconciliation is
    asserted — rather than assumed, or branched on and quietly tolerated
    either way — for every target this class checks.

    Creates ZERO refs. Every git call this class makes is read-only
    (`rev-parse`, `tag --list`, `log`, `rev-list`, `show-ref`, `status
    --porcelain`) — nothing here runs `git tag`, `git branch`, `git commit`,
    or `git checkout`, and `test_this_repo_still_releases_creates_zero_refs`
    verifies that mechanically rather than resting on code review alone. The
    composed tag "message file" is a plain OS temp file OUTSIDE this
    repository (never a git ref, never written under REPO_ROOT), removed in
    the same test that creates it."""

    # The OLD lane's facts, transcribed by hand from this repo's release
    # skill Targets table (`core/surface/skills/release/SKILL.md`) — the
    # pre-change module has no declared file to read them from, the same
    # transcription pattern `_OLD_LANE_TRANSCRIBED` above uses for the
    # fixture. Narrows the oracle problem; does not eliminate it (honest
    # limit 1 in the module docstring).
    _LIVE_OLD_LANE_FACTS = {
        "ca": {
            "prefix": "v",
            "manifests": ["plugins/ca/.claude-plugin/plugin.json"],
            "changelog": "CHANGELOG.md",
            "payload": "plugins/ca/",
            "payload_exclude": [],
        },
        "ca-pi": {
            "prefix": "ca-pi-v",
            "manifests": ["plugins/ca-pi/package.json", "package.json"],
            "changelog": "plugins/ca-pi/CHANGELOG.md",
            "payload": "plugins/ca-pi/",
            "payload_exclude": ["plugins/ca-pi/tools/"],
        },
    }

    @classmethod
    def setUpClass(cls):
        cls.old_lane = _load_old_lane()
        cls.core_lane = _load_core_lane()
        cls.rows_by_target = {
            row["target"]: row
            for row in cls.core_lane.load_targets(LIVE_RELEASE_TARGETS_PATH)
        }
        cls.head_sha = _git(["rev-parse", "HEAD"]).strip()
        cls.live_tags = [t.strip() for t in _git(["tag", "--list"]).splitlines() if t.strip()]
        # Zero-refs baseline — re-checked bit-for-bit in
        # test_this_repo_still_releases_creates_zero_refs. Every OTHER test
        # method in this class only reads (git log/rev-list/tag --list and
        # plain file opens), so this snapshot is valid regardless of test
        # execution order.
        cls._refs_before = _git(["show-ref"])
        cls._status_before = _git(["status", "--porcelain"])

    def _read_repo_file(self, rel_path):
        with open(os.path.join(REPO_ROOT, rel_path), encoding="utf-8") as fh:
            return fh.read()

    def _manifest_version(self, rel_path):
        return json.loads(self._read_repo_file(rel_path))["version"]

    def test_this_repo_still_releases_declared_row_facts_agree_with_the_transcribed_old_lane(self):
        # Row-shape agreement at LIVE HEAD — T-26 restated as this class's
        # own precondition rather than assumed.
        for target, facts in self._LIVE_OLD_LANE_FACTS.items():
            with self.subTest(target=target):
                row = self.rows_by_target[target]
                self.assertEqual(row["prefix"], facts["prefix"])
                self.assertEqual(row["manifest"], facts["manifests"])
                self.assertEqual(row["changelog"], facts["changelog"])
                self.assertEqual(row["payload"], facts["payload"])
                self.assertEqual(row["payload_exclude"], facts["payload_exclude"])

    def test_this_repo_still_releases_last_tag_agrees_across_lanes_and_an_independent_oracle(self):
        for target, facts in self._LIVE_OLD_LANE_FACTS.items():
            with self.subTest(target=target):
                row = self.rows_by_target[target]
                old_last_tag = self.old_lane.last_tag_select(self.live_tags, facts["prefix"])
                new_last_tag = self.core_lane.last_tag_select(self.live_tags, row["prefix"])
                oracle = _independent_last_tag(self.live_tags, facts["prefix"])
                self.assertIsNotNone(
                    oracle,
                    f"{target}: no real {facts['prefix']}MAJOR.MINOR.PATCH tag "
                    "found in this repo to validate against")
                self.assertEqual(old_last_tag, oracle)
                self.assertEqual(new_last_tag, oracle)
                self.assertEqual(old_last_tag, new_last_tag)

    def test_this_repo_still_releases_manifest_versions_agree_across_lanes(self):
        for target, facts in self._LIVE_OLD_LANE_FACTS.items():
            with self.subTest(target=target):
                row = self.rows_by_target[target]
                old_versions = [self._manifest_version(p) for p in facts["manifests"]]
                new_versions = [self._manifest_version(p) for p in row["manifest"]]
                self.assertEqual(old_versions, new_versions)

    def test_this_repo_still_releases_ca_pi_dual_manifest_agrees(self):
        # ca-pi's own two-manifest invariant (Phase 1 step 3: "for ca-pi,
        # both manifests count"), live — the property T-27d's fixture
        # exercises, exercised here against the REAL generated repo-root
        # package.json build artifact rather than a synthetic copy.
        row = self.rows_by_target["ca-pi"]
        versions = [self._manifest_version(p) for p in row["manifest"]]
        self.assertEqual(len(versions), 2)
        self.assertEqual(
            versions[0], versions[1],
            "ca-pi's plugin manifest and the generated repo-root package.json "
            "disagree — tools/build-host-packages.py has not been re-run "
            "since the last manifest bump")

    def test_this_repo_still_releases_ca_pi_commit_window_matches_between_lanes(self):
        facts = self._LIVE_OLD_LANE_FACTS["ca-pi"]
        row = self.rows_by_target["ca-pi"]
        last_tag = self.core_lane.last_tag_select(self.live_tags, row["prefix"])
        self.assertNotEqual(last_tag, self.core_lane.NONE_SENTINEL)

        old_window = _live_window_shas(
            last_tag, self.head_sha, facts["payload"], facts["payload_exclude"])
        new_window = _live_window_shas(
            last_tag, self.head_sha, row["payload"], row["payload_exclude"])
        # Honest limit 2 (module docstring): this equality has no independent
        # discriminating power of its own — both lanes share ONE `last_tag`
        # and ONE (identical, for ca-pi) payload string AND ONE identical
        # payload-exclude list, so it can only diverge if LAST_TAG, the
        # payload path, or the exclude list had already diverged, which the
        # tests above (including the payload_exclude row-facts check) assert
        # separately.
        self.assertEqual(old_window, new_window)
        if not new_window:
            # SKIP, not fail. An empty window is the correct and expected
            # state immediately after a ca-pi release (its tag is at HEAD),
            # so asserting non-empty makes this suite go red for a reason
            # that is release state rather than a defect. The equality above
            # -- the thing this test exists to prove -- has already been
            # checked and holds for an empty window too.
            self.skipTest("ca-pi has no commits since its last tag at live "
                          "HEAD, so there is no window to trace; this is "
                          "normal immediately after a ca-pi release")

        independent_count = _independent_window_count(
            last_tag, self.head_sha, row["payload"], row["payload_exclude"])
        self.assertEqual(len(new_window), independent_count)

    def test_this_repo_still_releases_ca_pi_payload_exclude_actually_narrows_the_window(self):
        # AC-1.11 names payload-exclude as one of the three behaviors ca-pi
        # exists in this trace to exercise (adversarial review 2026-07-31,
        # HIGH-3). A direct, single-lane check that it is doing something
        # real, not just declared: the excluded window must be a STRICT
        # subset of the unexcluded window, both computed fresh against live
        # HEAD (never a hand-written commit count, which would go stale on
        # the very next merge).
        row = self.rows_by_target["ca-pi"]
        last_tag = self.core_lane.last_tag_select(self.live_tags, row["prefix"])
        self.assertNotEqual(last_tag, self.core_lane.NONE_SENTINEL)
        self.assertTrue(
            row["payload_exclude"],
            "ca-pi's declared row lost its payload-exclude entry — the "
            "release window would then drive a different SemVer bump than "
            "the real lane (a commit touching only plugins/ca-pi/tools/ "
            "would count)")

        excluded_window = set(_live_window_shas(
            last_tag, self.head_sha, row["payload"], row["payload_exclude"]))
        unexcluded_window = set(_live_window_shas(
            last_tag, self.head_sha, row["payload"], []))
        if not unexcluded_window:
            # Same reasoning as the window test above: with no commits in
            # the payload at all, the exclude pathspec has nothing to narrow
            # and "it removed no commits" is arithmetic, not a finding.
            self.skipTest("ca-pi's payload has no commits since its last tag "
                          "at live HEAD, so payload-exclude has nothing to "
                          "narrow; normal immediately after a ca-pi release")
        self.assertTrue(
            excluded_window < unexcluded_window,
            "ca-pi's payload-exclude removed no commits from the release "
            "window at live HEAD — the exclude pathspec is not being "
            "applied")

    def test_this_repo_still_releases_ca_pi_composed_message_passes_notes_match_and_dates_consistent(self):
        facts = self._LIVE_OLD_LANE_FACTS["ca-pi"]
        row = self.rows_by_target["ca-pi"]
        old_text = self._read_repo_file(facts["changelog"])
        new_text = self._read_repo_file(row["changelog"])
        self.assertEqual(old_text, new_text)  # same real file, two path spellings

        next_version = self._manifest_version(row["manifest"][0])
        section_version, section_text, date = _first_release_section(new_text)
        self.assertEqual(
            section_version, next_version,
            "ca-pi's manifest and CHANGELOG must be reconciled — this is "
            "T-77's end-to-end lane; per the module docstring, the two can "
            "diverge between merges (manifest bumps per-PR, CHANGELOG lands "
            "on a slower hand-written cadence), which would BLOCK /release "
            "at Phase 1")
        self.assertIsNotNone(date)
        # A direct boundary check on the shared section-extraction helper
        # itself (honest limit 4): comparing old-vs-new lane output alone
        # cannot catch an off-by-one in _first_release_section, since both
        # lanes call the SAME helper on the SAME text and would shift
        # together. section_text must contain its OWN heading and no
        # other — never bleed into the NEXT section.
        self.assertEqual(
            len(_ANY_MD_HEADING_RE.findall(section_text)), 1,
            "the extracted section spans more than one CHANGELOG heading — "
            "_first_release_section's end boundary is wrong")

        last_tag = self.core_lane.last_tag_select(self.live_tags, row["prefix"])
        # >=, not a strict advance: once the tag has caught up to the
        # manifest (the tag-per-merge automation's steady state), equality
        # is the expected, correct condition — nothing new to release. Only
        # the tag running AHEAD of the manifest is a genuine regression.
        self.assertGreaterEqual(
            self.core_lane.semver_key(next_version),
            self.core_lane.semver_key(self.core_lane._bare_version(last_tag)),
            f"ca-pi's manifest version {next_version!r} is behind its last "
            f"tag {last_tag!r} — the tag has run ahead of the manifest")

        message = _compose_tag_message(section_text, date)
        tag = row["prefix"] + next_version

        for lane, label in ((self.old_lane, "old"), (self.core_lane, "new")):
            with self.subTest(lane=label):
                self.assertTrue(
                    lane.notes_heading_matches(message, tag),
                    f"{label} lane: notes_heading_matches rejected a message "
                    "composed from ca-pi's own reconciled CHANGELOG section")
                self.assertTrue(
                    lane.release_dates_consistent(section_text, message),
                    f"{label} lane: release_dates_consistent rejected the "
                    "composed message's own Released-at footer")

        # The "message file": a plain OS temp file OUTSIDE this repository —
        # zero refs, nothing committed — round-tripped to prove the write is
        # lossless. Windows text-mode open() flips LF to CRLF on rewrite, so
        # newline="\n" on write and newline="" on read-back throughout.
        fd, path = tempfile.mkstemp(prefix="release-trace-t77-", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(message)
            with open(path, encoding="utf-8", newline="") as fh:
                roundtripped = fh.read()
            self.assertEqual(roundtripped, message)
        finally:
            os.remove(path)

    def test_this_repo_still_releases_ca_manifest_and_changelog_are_reconciled(self):
        # ca's manifest bumps on every merged feat/fix PR (this campaign's
        # own per-PR version-gate convention); CHANGELOG.md lands on a
        # separate, slower, hand-written cadence. NEXT_VERSION is read from
        # the MANIFEST throughout (Phase 1 step 3's own contract: derive the
        # version, then assert it EQUALS the manifest), never redefined as
        # "whichever version the changelog's newest heading already names"
        # merely to dodge a mismatch — so this asserts the two agree, the
        # same live guard `/release ca` Phase 1 applies, rather than
        # branching on whichever state happens to hold when the suite runs
        # and reporting green either way (adversarial review 2026-07-31,
        # HIGH-2: the prior if/else's drift arm asserted only a tautology
        # that a corrupted NEXT_VERSION could select without failing
        # anything). A failure here means ca's manifest has run ahead of
        # CHANGELOG.md again — add the missing `## [X.Y.Z]` section; do not
        # relax this assertion to tolerate the gap.
        row = self.rows_by_target["ca"]
        changelog_text = self._read_repo_file(row["changelog"])
        next_version = self._manifest_version(row["manifest"][0])
        section_version, section_text, date = _first_release_section(changelog_text)
        self.assertEqual(
            section_version, next_version,
            f"ca's CHANGELOG top section ({section_version!r}) does not "
            f"match the manifest version ({next_version!r}) — /release ca "
            "would BLOCK at Phase 1 in this state")
        self.assertIsNotNone(date)
        # A direct boundary check on the shared section-extraction helper
        # itself (honest limit 4): section_text must contain its OWN
        # heading and no other — never bleed into the NEXT section.
        self.assertEqual(
            len(_ANY_MD_HEADING_RE.findall(section_text)), 1,
            "the extracted section spans more than one CHANGELOG heading — "
            "_first_release_section's end boundary is wrong")

        last_tag = self.core_lane.last_tag_select(self.live_tags, row["prefix"])
        self.assertTrue(
            self.core_lane.semver_greater(next_version, self.core_lane._bare_version(last_tag)),
            f"ca's manifest version {next_version!r} is not a strict SemVer "
            f"advance over its last tag {last_tag!r}")

        message = _compose_tag_message(section_text, date)
        tag = row["prefix"] + next_version
        for lane, label in ((self.old_lane, "old"), (self.core_lane, "new")):
            with self.subTest(lane=label):
                self.assertTrue(
                    lane.notes_heading_matches(message, tag),
                    f"{label} lane: notes_heading_matches rejected a message "
                    "composed from ca's own reconciled CHANGELOG section")
                self.assertTrue(
                    lane.release_dates_consistent(section_text, message),
                    f"{label} lane: release_dates_consistent rejected the "
                    "composed message's own Released-at footer")

    def test_this_repo_still_releases_creates_zero_refs(self):
        # Every git call this class makes is read-only (rev-parse, tag
        # --list, log, rev-list, show-ref, status --porcelain) — no `git
        # tag`, `git branch`, `git commit`, or `git checkout` anywhere in
        # this class. This is the mechanical proof of that invariant, rather
        # than an assertion resting on code review alone.
        refs_after = _git(["show-ref"])
        status_after = _git(["status", "--porcelain"])
        head_after = _git(["rev-parse", "HEAD"]).strip()
        self.assertEqual(
            refs_after, self._refs_before,
            "a ref (tag/branch) was created or moved while this trace ran")
        self.assertEqual(
            status_after, self._status_before,
            "the working tree changed while this trace ran — this class "
            "must never write inside this repository")
        self.assertEqual(head_after, self.head_sha, "HEAD moved while this trace ran")


if __name__ == "__main__":
    unittest.main()
