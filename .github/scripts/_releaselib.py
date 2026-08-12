#!/usr/bin/env python3
# codeArbiter - CI's stable entry point for the release lane's mechanical gates
# (issue #563, .codearbiter/specs/release-portable-fixture.md, "Migration
# ordering").
#
# This file is the PERMANENT shim six sites shell out to directly --
# release.yml:135,171 and .github/actions/publish-release/action.yml:125,164,
# 180,228. It is never deleted, only slimmed down: it is a thin RE-EXPORT of
# the portable mechanism at core/pysrc/_releaselib.py, plus the small amount
# of THIS repo's data that CI needs.
#
# As of A-4.4/T-46 that data is DERIVED, not declared here: RELEASE_TARGETS
# reads .codearbiter/release-targets.md, and RELEASE_TAG_PREFIXES is gone
# entirely (payload_version_gate.py derives its own map per A-4.1, and nothing
# else consumed it). Only MERGE_READINESS_CHECK remains a literal, because it
# is a CI check-run name rather than a release-target fact and the declared
# file has no field for it.
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
#     (ca's `v` prefix, the declared target order, MERGE_READINESS_CHECK) so every
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
# Public API (this repo's DATA -- RELEASE_TARGETS derived from the declared
# file; see the module comment above):
#   RELEASE_TARGETS, MERGE_READINESS_CHECK
#   last_tag_select(tags, prefix="v") -> str
#   select_release_target(*confirmations) -> str   (declared order)
#   select_release_target_by_name(pairs) -> str    (A-4.2, order-independent)
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
# DATA -- DERIVED, not declared here (A-4.4/T-46).
#
# This block used to carry three literals: RELEASE_TARGETS,
# RELEASE_TAG_PREFIXES, and MERGE_READINESS_CHECK. The first two were a
# SECOND source of truth for facts `.codearbiter/release-targets.md` already
# declares, and nothing compared them: a target declared under one prefix and
# listed here under another would be gated in one namespace and released in
# the other. Adding a fifth plugin meant editing two files, and forgetting
# this one produced a KeyError at release time rather than a diagnosis.
#
# RELEASE_TARGETS is now read from the declared file, in DECLARATION order.
# RELEASE_TAG_PREFIXES is gone entirely -- payload_version_gate.py derives its
# own map (A-4.1), and nothing else consumed it.
# --------------------------------------------------------------------------- #

# The `ci-passed` aggregate in .github/workflows/ci.yml - the single check run
# that means "every required job for this commit concluded green". Kept in sync
# with that job's `name:` by test_release_workflow.py.
#
# NOT removed with the other two, deliberately: this is a CI check-run NAME,
# not a release-target fact, and `.codearbiter/release-targets.md` declares no
# such field. Deriving it would mean inventing a declaration source for it;
# leaving it here, named and tested against the workflow, is honest. A-4.4's
# "data constants" are the two that duplicated the declared file.
MERGE_READINESS_CHECK = "[GATE ] | [REPO] | Merge readiness"

DECLARED_TARGETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(_HERE)), ".codearbiter", "release-targets.md")


def _declared_target_names():
    """Every declared target name, in DECLARATION order.

    Order still matters to the positional `select-target` subcommand this
    module keeps for its own tests; the workflow itself moved to the
    name-keyed form (A-4.2) precisely so a release can no longer depend on
    it. Reading the order from the declaration rather than a literal means
    the two cannot drift even while both forms exist.

    Raises rather than defaulting: this module is THIS repository's CI
    entry point, the declared file is committed beside it, and a silent
    empty register would make `select-target` resolve nothing while
    looking healthy.
    """
    return tuple(row["target"] for row in _mechanism.load_targets(
        DECLARED_TARGETS_PATH))


def __getattr__(name):
    """Lazy module attributes (PEP 562).

    `RELEASE_TARGETS` is DERIVED from the declared file, and deriving it
    at import time would give this module a side effect at import -- which
    its own design invariants forbid, and which broke every harness that
    imports the shim from a tree containing the scripts but not
    `.codearbiter/release-targets.md`. Resolving on first ACCESS keeps
    every existing `_releaselib.RELEASE_TARGETS` caller working while an
    import that never touches the name stays pure.
    """
    if name == "RELEASE_TARGETS":
        return _declared_target_names()
    # NOTE: PEP 562 module __getattr__ serves EXTERNAL attribute access
    # only. Code INSIDE this module must call `_declared_target_names()`
    # directly -- a bare `RELEASE_TARGETS` here raises NameError, which is
    # exactly how this was found.
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def release_tag_prefixes():
    """`{target: tag prefix}`, read from the declared file (A-4.4).

    Replaces the RELEASE_TAG_PREFIXES literal this module used to carry.
    That literal was a second source of truth for a fact the declared file
    already states, and nothing compared them -- a target declared under
    one prefix and listed here under another would be gated in one
    namespace and released in the other.

    A FUNCTION rather than a module constant on purpose: a constant would
    freeze the declared file's contents at import time, so a test that
    writes a fixture declaration and re-reads it would keep seeing the
    first load. Callers that want the snapshot can bind it themselves.
    """
    return {row["target"]: row["prefix"]
            for row in _mechanism.load_targets(DECLARED_TARGETS_PATH)}


def last_tag_select(tags, prefix="v"):
    """Return the highest SemVer tag in `tags` for ONE release series, excluding
    pre-releases (`-beta`/`-rc`/`-alpha`). Returns NONE_SENTINEL when the series
    has no release tag yet.

    `prefix` defaults to `"v"` - ca, the primary release - so every existing
    caller (the CLI's bare `last-tag` invocation, this repo's tooling) keeps its
    behaviour unchanged even though the portable mechanism's own
    `last_tag_select` now REQUIRES the prefix (A-1.3). Pass a value from
    the declared prefix for a sibling (#382)."""
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
    return _mechanism.select_release_target(
        *confirmations, targets=_declared_target_names())


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
      auto-eligible <manifest_version> <prefix>
                                               stdin=tags -> true | false. True iff no
                                               tag exists yet for this series (first
                                               introduction) or manifest_version is a
                                               strict SemVer advance over the series'
                                               last tag — i.e. there is untagged work
                                               to publish. Backs the auto-tag-on-merge
                                               preflight (push-triggered, no dispatch
                                               input): the same "is this genuinely new"
                                               question payload_version_gate.py asks
                                               per-PR, asked again at tag time so a push
                                               that did not advance a target's manifest
                                               is silently skipped rather than re-tagging
                                               or erroring.

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
        prefix = release_tag_prefixes().get(rest[0])
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
    if cmd == "select-target" and len(rest) == len(_declared_target_names()):
        print(select_release_target(*rest))
        return 0
    if cmd == "select-target-named" and rest:
        # A-4.2/T-44b. Each argument is `name=value`, so selection never
        # depends on the ORDER the workflow happens to pass its inputs in.
        # The positional form above aligns by index against
        # RELEASE_TARGETS: correct only while the workflow's input order
        # and the declared row order agree, which nothing enforced. A row
        # inserted at the front shifts every confirmation by one and the
        # dispatch publishes the wrong plugin, holding a contents:write
        # token, with every downstream check passing because the wrong
        # release is internally consistent.
        print(_mechanism.select_release_target_by_name(
            list(rest), _declared_target_names()))
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
    if cmd == "auto-eligible" and len(rest) == 2:
        manifest_version, prefix = rest
        last_tag = last_tag_select(sys.stdin.read().split(), prefix)
        if last_tag == NONE_SENTINEL:
            print("true")  # first introduction for this series - always eligible
            return 0
        print("true" if semver_greater(manifest_version, _bare_version(last_tag))
              else "false")
        return 0
    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
