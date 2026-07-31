#!/usr/bin/env python3
# codeArbiter - CI's stable entry point for the release lane's mechanical gates
# (issue #563, .codearbiter/specs/release-portable-fixture.md, "Migration
# ordering").
#
# This file is the PERMANENT shim six sites shell out to directly --
# release.yml:135,171 and .github/actions/publish-release/action.yml:125,164,
# 180,228 -- and payload_version_gate.py imports RELEASE_TAG_PREFIXES from it
# at module load. It is never deleted, only slimmed down: slice 1 (this
# change) converts it to a thin RE-EXPORT of the portable mechanism now living
# at core/pysrc/_releaselib.py, while TEMPORARILY retaining this repo's own
# data constants (RELEASE_TARGETS, RELEASE_TAG_PREFIXES, MERGE_READINESS_CHECK)
# so every existing caller keeps working unchanged. Slice 4 (T-46) removes the
# constants once payload_version_gate.py and release.yml read them from the
# declared .codearbiter/release-targets.md file instead; this shim survives
# that change too.
#
# The mechanism module is loaded from core/pysrc/ directly -- not from a
# vendored plugins/*/hooks/ copy -- because this file executes inside the
# codeArbiter repo itself (CI checks out the full repo), where core/pysrc/ is
# the canonical source `tools/sync-core.py` vendors FROM. It is located via
# this file's own __file__, never the process cwd, mirroring the
# cwd-independent REPO resolution `payload_version_gate.py` already uses
# (`Path(__file__).resolve().parents[2]`) -- so this module resolves
# correctly no matter what directory it is invoked from. Both this shim and
# the mechanism module are named `_releaselib.py`, so a plain `import
# _releaselib` from inside this file would resolve to itself via the module
# cache regardless of sys.path order; loading the mechanism by explicit file
# path under a distinct internal name (`importlib.util.spec_from_file_location`,
# the same technique `test_release_lib.py` already uses for the same reason)
# avoids that collision.
#
# KNOWN RESIDUAL (M-6, adversarial review 2026-07-31): the private module
# name above means this shim's copy of the mechanism is a DISTINCT load from
# any OTHER independent load of core/pysrc/_releaselib.py in the same
# process -- e.g. a test harness's own private-named copy, or a future
# second consumer that loads the mechanism itself rather than importing this
# shim. `shim.ReleaseTargetsError is <someone else's independently-loaded
# copy>.ReleaseTargetsError` is FALSE. An `except` clause spanning that
# boundary would miss. No caller does this today. This is documented rather
# than "fixed" by reusing a same-named entry out of `sys.modules` when one
# is present: there is no single canonical name a dynamically-loaded copy is
# guaranteed to register under (this file's own tests, `test_release_lib.py`,
# and `test_release_trace.py` each pick their own private name for their own
# reasons), so keying off `sys.modules` would make this shim's behavior
# depend on import order and on what some OTHER, unrelated test file
# happened to load first -- an import-order-dependent hazard traded for a
# documented, narrow one. The sanctioned route for a caller that needs to
# catch this shim's exceptions is to import the class from THIS shim (the
# public, re-exported surface), never to load its own separate copy of
# core/pysrc/_releaselib.py and expect the two hierarchies to unify.
#
# Design invariants (mirror the other _*lib helpers):
#   - Stdlib only; zero side effects at import beyond loading the sibling
#     mechanism module (no git, no argument parsing at import time).
#   - The wrapper functions below restore this repo's OLD default arguments
#     (ca's `v` prefix, RELEASE_TARGETS order, MERGE_READINESS_CHECK) so every
#     existing caller -- the six shell-out sites, payload_version_gate.py, and
#     this module's own CLI -- keeps working unchanged even though the
#     portable mechanism's equivalents now REQUIRE the parameter that used to
#     default (A-1.3: a repo default cannot survive in the portable module).
#
# Public API (re-exported from core/pysrc/_releaselib.py, unwrapped -- no
# repo-specific default to restore):
#   ReleaseTargetsError, AbsentBlockError, EmptyBlockError, MalformedBlockError,
#   UnknownKeyError, DuplicateKeyError, DuplicateTargetError,
#   InvalidBooleanError, MultipleBlocksError, DelimiterInValueError,
#   MissingRequiredKeyError, FileExistsNoBlockError
#   semver_key(value) -> tuple | None
#   semver_greater(current, base) -> bool
#   notes_heading_matches(notes_text, tag) -> bool
#   release_dates_consistent(changelog_section, tag_message) -> bool
#   classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
#                          manifest_version, release_is_nondraft) -> str
#   peel_tag(ls_remote_text, tag) -> str
#   parse_release_targets(text) -> list[dict]
#   load_targets(path) -> list[dict]
#   _bare_version(tag) -> str
#   NONE_SENTINEL
#
# Public API (this repo's DATA -- transitional, see module comment above):
#   RELEASE_TARGETS, RELEASE_TAG_PREFIXES, MERGE_READINESS_CHECK
#   last_tag_select(tags, prefix="v") -> str
#   select_release_target(*confirmations) -> str   (RELEASE_TARGETS order)
#   classify_merge_readiness(check_runs, head_sha, check_name=MERGE_READINESS_CHECK) -> str
#
# The last three back `.github/workflows/release.yml`'s read-only preflight and
# its tag-integrity guard (issues #378, #385, #380). The hosted publish path
# holds `contents: write` and its writes are public and irreversible, so every
# one of them degrades to the REFUSING answer on malformed input.

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_MECHANISM_PATH = os.path.join(_REPO_ROOT, "core", "pysrc", "_releaselib.py")

_mechanism_spec = importlib.util.spec_from_file_location(
    "_release_mechanism", _MECHANISM_PATH)
_mechanism = importlib.util.module_from_spec(_mechanism_spec)
# Registered in sys.modules so introspection (inspect.getsourcefile, etc.)
# resolves the loaded module's real file rather than reading it back as a
# "built-in class" with no source at all.
sys.modules[_mechanism_spec.name] = _mechanism
_mechanism_spec.loader.exec_module(_mechanism)

# --------------------------------------------------------------------------- #
# Re-exported mechanism -- unwrapped, no repo-specific default to restore.
# --------------------------------------------------------------------------- #

ReleaseTargetsError = _mechanism.ReleaseTargetsError
AbsentBlockError = _mechanism.AbsentBlockError
EmptyBlockError = _mechanism.EmptyBlockError
MalformedBlockError = _mechanism.MalformedBlockError
UnknownKeyError = _mechanism.UnknownKeyError
DuplicateKeyError = _mechanism.DuplicateKeyError
DuplicateTargetError = _mechanism.DuplicateTargetError
InvalidBooleanError = _mechanism.InvalidBooleanError
MultipleBlocksError = _mechanism.MultipleBlocksError
DelimiterInValueError = _mechanism.DelimiterInValueError
MissingRequiredKeyError = _mechanism.MissingRequiredKeyError
FileExistsNoBlockError = _mechanism.FileExistsNoBlockError

# SEMVER is re-exported because `tools/build-host-packages.py:22` imports it.
# The first shim conversion dropped it while re-exporting its two neighbours,
# and nothing failed: no TEST imports SEMVER, so the re-export surface was
# covered for the names the tests use rather than the names consumers use.
# `test_shim_reexports_every_name_any_consumer_imports` now derives the
# required set from the repo rather than restating it here.
SEMVER = _mechanism.SEMVER
semver_key = _mechanism.semver_key
semver_greater = _mechanism.semver_greater
notes_heading_matches = _mechanism.notes_heading_matches
release_dates_consistent = _mechanism.release_dates_consistent
classify_publish_state = _mechanism.classify_publish_state
peel_tag = _mechanism.peel_tag
parse_release_targets = _mechanism.parse_release_targets
load_targets = _mechanism.load_targets
_bare_version = _mechanism._bare_version
NONE_SENTINEL = _mechanism.NONE_SENTINEL

# --------------------------------------------------------------------------- #
# DATA -- this repo's own facts. TRANSITIONAL (A-1.9): removed in slice 4
# (T-46) once payload_version_gate.py and release.yml read
# .codearbiter/release-targets.md instead. Until then, no commit may leave
# RELEASE_TAG_PREFIXES unimportable from this module.
# --------------------------------------------------------------------------- #

# The `ci-passed` aggregate in .github/workflows/ci.yml - the single check run
# that means "every required job for this commit concluded green". Kept in sync
# with that job's `name:` by test_release_workflow.py.
MERGE_READINESS_CHECK = "[GATE ] | [REPO] | Merge readiness"

# Every plugin that has a sanctioned release lane, in dispatch-input order
# (#382). The names are the labels `select_release_target` returns and the
# values release.yml's publisher `if:` conditions compare against; adding a
# plugin here without adding its publisher job turns the workflow contract
# suite red rather than resolving a target nothing can publish.
RELEASE_TARGETS = ("ca", "ca-codex", "ca-sandbox", "ca-pi")

# Each target's tag namespace. `ca` owns the bare `v*` series as the repository's
# primary release; every sibling is namespaced so it cannot collide with it. The
# ANCHORED match built from these prefixes is also what keeps one series from
# resolving another's tag as its own baseline - `^v` cannot match `ca-pi-v0.1.30`
# - so series isolation is a property of the match rather than an exclusion list
# somebody has to remember to extend. release.yml's per-lane `tag-prefix` inputs
# are asserted against this map by the workflow contract suite, so the hosted
# lane and the /ca:release command cannot disagree about a namespace.
RELEASE_TAG_PREFIXES = {
    "ca": "v",
    "ca-codex": "ca-codex-v",
    "ca-sandbox": "ca-sandbox-v",
    "ca-pi": "ca-pi-v",
}


def last_tag_select(tags, prefix="v"):
    """Return the highest SemVer tag in `tags` for ONE release series, excluding
    pre-releases (`-beta`/`-rc`/`-alpha`). Returns NONE_SENTINEL when the series
    has no release tag yet.

    `prefix` defaults to `"v"` - ca, the primary release - so every existing
    caller (the CLI's bare `last-tag` invocation, this repo's tooling) keeps its
    behaviour unchanged even though the portable mechanism's own
    `last_tag_select` now REQUIRES the prefix (A-1.3). Pass a value from
    RELEASE_TAG_PREFIXES for a sibling (#382)."""
    return _mechanism.last_tag_select(tags, prefix)


def select_release_target(*confirmations):
    """Resolve which single plugin a release dispatch selected. `confirmations`
    are the per-plugin version inputs, positionally aligned with
    RELEASE_TARGETS. Returns one of:

      <target>   - exactly one input was supplied; the name from RELEASE_TARGETS.
      none       - no input was supplied; there is nothing to publish.
      multiple   - more than one; the dispatch is ambiguous and MUST be refused.
      arity      - the caller passed the wrong NUMBER of inputs.

    Delegates to the portable mechanism's `select_release_target`, supplying
    this repo's RELEASE_TARGETS register - which the portable module now
    REQUIRES rather than assumes (A-1.3)."""
    return _mechanism.select_release_target(*confirmations, targets=RELEASE_TARGETS)


def classify_merge_readiness(check_runs, head_sha, check_name=MERGE_READINESS_CHECK):
    """Classify the merge-readiness evidence for ONE exact commit. `check_runs`
    is the `check_runs` array from GitHub's
    `repos/{owner}/{repo}/commits/{sha}/check-runs` response. Returns one of:

      green           - the gate ran for this commit, completed, and succeeded.
      missing         - no check run by that name is present at all.
      pending         - present but not `completed` (queued / in_progress / ...).
      sha_mismatch    - a matching run reports a different `head_sha`.
      not_successful  - completed with any conclusion other than `success`
                        (failure, cancelled, skipped, timed_out, neutral, ...).

    `check_name` defaults to MERGE_READINESS_CHECK so every existing caller
    keeps its behaviour unchanged even though the portable mechanism's own
    `classify_merge_readiness` now REQUIRES it (A-1.3)."""
    return _mechanism.classify_merge_readiness(check_runs, head_sha, check_name)


# --------------------------------------------------------------------------- #
# Thin CLI so release.yml / publish-release/action.yml can shell out to the
# pinned logic, the same way they already call check_badge_consistency.py.
# Pure dispatch over the functions above; reads tags from stdin / files from
# argv. Never raises.
# --------------------------------------------------------------------------- #

def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv):
    """CLI dispatch. Subcommands:
      last-tag                                 stdin=tags -> prints selected tag / <none>
      notes-match <tag> <notes_file>           exit 0 iff first heading == tag
      dates-consistent <changelog> <tagmsg>    exit 0 iff the two dates agree
      classify <tag_exists> <tag_sha> <head_sha> <tag_version> <manifest_version> <release_nondraft>
                                               prints the publish-state label (bools: true/false)
      select-target <ca> <ca-codex> <ca-sandbox> <ca-pi>
                                               prints one of RELEASE_TARGETS,
                                               or none | multiple | arity
      merge-readiness <head_sha> <checks_json> prints green | missing | pending |
                                               sha_mismatch | not_successful
      peel-tag <tag>                           stdin=`git ls-remote --tags` -> commit sha / ""

    The three release.yml subcommands print a LABEL and exit 0; the workflow
    cases on the label with a fail-closed `*)` arm, so an unrecognised label -
    or a crash, which yields no label at all - refuses the dispatch either way.
    Returns a process exit code."""
    import sys
    if not argv:
        sys.stderr.write(
            "usage: _releaselib.py {last-tag|notes-match|dates-consistent|classify"
            "|select-target|merge-readiness|peel-tag} ...\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "last-tag" and len(rest) <= 1:
        # No argument keeps ca's series, so the existing invocation is unchanged.
        print(last_tag_select(sys.stdin.read().split(), *(rest or ())))
        return 0
    if cmd == "tag-prefix" and len(rest) == 1:
        # One source of truth for a namespace: the release skill asks for the
        # prefix rather than restating four of them in prose.
        prefix = RELEASE_TAG_PREFIXES.get(rest[0])
        if prefix is None:
            sys.stderr.write(f"unknown release target: {rest[0]}\n")
            return 2
        print(prefix)
        return 0
    if cmd == "notes-match" and len(rest) == 2:
        return 0 if notes_heading_matches(_read(rest[1]), rest[0]) else 1
    if cmd == "dates-consistent" and len(rest) == 2:
        return 0 if release_dates_consistent(_read(rest[0]), _read(rest[1])) else 1
    if cmd == "classify" and len(rest) == 6:
        b = lambda s: str(s).lower() == "true"
        print(classify_publish_state(
            tag_exists=b(rest[0]), tag_sha=rest[1], head_sha=rest[2],
            tag_version=rest[3], manifest_version=rest[4], release_is_nondraft=b(rest[5])))
        return 0
    if cmd == "select-target" and len(rest) == len(RELEASE_TARGETS):
        print(select_release_target(*rest))
        return 0
    if cmd == "merge-readiness" and len(rest) == 2:
        import json
        try:
            runs = json.loads(_read(rest[1]))
        except ValueError:
            runs = None  # unreadable/unparseable evidence is no evidence
        print(classify_merge_readiness(runs, rest[0]))
        return 0
    if cmd == "peel-tag" and len(rest) == 1:
        print(peel_tag(sys.stdin.read(), rest[0]))
        return 0
    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
