#!/usr/bin/env python3
# codeArbiter — portable release-lane MECHANISM (anchored per-series tag
# selection, semver comparison, publish-state classification, notes-heading
# matching, date consistency) plus the declared-target-file parser.
#
# This module is the PORTABLE half of the release helper split (issue #563).
# It ships from core/pysrc/ into every governance plugin's hooks/ directory
# (tools/sync-core.py, CI-enforced byte-identity) and therefore MUST carry no
# fact about this repository or its CI vocabulary — no plugin name, no path
# under this repository, no check-run name, no tag-namespace mapping. Every
# such fact is DATA, supplied by the caller (a required parameter) or read
# from an operator-declared file via load_targets(). A consuming repository
# supplies its own facts; this module supplies only the mechanism.
#
# Design invariants (mirror the other _*lib helpers):
#   - Stdlib only; zero side effects at import (no git, no file I/O, no
#     argument parsing at import time).
#   - Every mechanism function (semver_key, semver_greater, last_tag_select,
#     notes_heading_matches, release_dates_consistent, classify_publish_state,
#     select_release_target, classify_merge_readiness, peel_tag) is pure over
#     synthetic input and NEVER raises on malformed input — it degrades to the
#     safe/refusing answer, per this codebase's "never raise on malformed user
#     input" rule for hook-adjacent helpers.
#   - The declared-target-file parser (parse_release_targets / load_targets)
#     is the deliberate, documented exception to that rule: its input is not
#     arbitrary user/session data but an OPERATOR-AUTHORED configuration file
#     that a `contents: write` release lane later executes. A malformed
#     declaration is a configuration error that MUST surface loudly to the
#     operator rather than silently defaulting or partially parsing — so every
#     parser-contract violation raises its own distinguishable
#     ReleaseTargetsError subclass instead of returning a degraded value or
#     letting a bare exception escape from deep inside the parser.
#
# Public API:
#   semver_key(value) -> tuple | None
#   semver_greater(current, base) -> bool
#   last_tag_select(tags, prefix) -> str
#   notes_heading_matches(notes_text, tag) -> bool
#   release_dates_consistent(changelog_section, tag_message) -> bool
#   classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
#                          manifest_version, release_is_nondraft) -> str
#   select_release_target(*confirmations, targets) -> str
#   classify_merge_readiness(check_runs, head_sha, check_name) -> str
#   _manifest_version(path) -> str | None
#   classify_commit(subject, body) -> dict
#   classify_window(commits) -> dict
#   parse_window_log(text) -> list[dict]
#   first_release_baseline(adoption_log_text) -> str
#   peel_tag(ls_remote_text, tag) -> str
#   parse_release_targets(text) -> list[dict]
#   load_targets(path) -> list[dict]
#   default_backfill_root() -> str
#   scan_backfill_candidates(root) -> (list[str], list[str])
#   detect_candidate_target(manifest_candidates, changelog_candidates,
#                           target=..., prefix=...) -> dict
#   format_release_targets_block(row) -> str
#   default_targets_path() -> str
#   _targets_error_exit_code(exc) -> int
#   main(argv) -> int
#
# CLI (T-41f): every consuming host vendors this file byte-identically into
# its own `hooks/` directory (`tools/sync-core.py`), and that vendored copy —
# `${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py` — is what the release skill
# actually shells out to post-portability (issue #563). Before this, only the
# permanent `.github/scripts/_releaselib.py` shim (this repo's OWN CI entry
# point, never replaced by this one) carried a `__main__`; repointing the
# skill's invocations without this CLI would aim prose at a file nothing
# could run. See "CLI entry point" below the parser for the subcommands.
#
# Declared exceptions (all subclass ReleaseTargetsError):
#   AbsentBlockError        — no delimiter block present at all
#   EmptyBlockError         — the delimiter block is present but blank
#   MalformedBlockError     — bad `[target]` header grammar, a key before the
#                             first header, or an unparsable line
#   UnknownKeyError         — a key outside the declared grammar
#   DuplicateKeyError       — a scalar key repeated within one target block
#   DuplicateTargetError    — the same `[target]` header declared twice
#   InvalidBooleanError     — a boolean value that is not exactly true/false
#   MultipleBlocksError     — more than one delimiter block in the file
#   DelimiterInValueError   — a value contains the literal closing delimiter,
#                             which would otherwise truncate the block under a
#                             naive non-greedy match
#   MissingRequiredKeyError — a target block is missing prefix/changelog/payload
#   BackfillAmbiguousError  — the back-fill scan found zero, or more than one,
#                             candidate manifest or changelog file (T-49/T-50)
#   FileExistsNoBlockError  — the declared-target file EXISTS on disk but
#                             carries no delimiter block at all (HIGH-1,
#                             adversarial review 2026-07-31). Deliberately a
#                             SIBLING of AbsentBlockError, not a subclass of
#                             it: raised only by load_targets() (which knows
#                             the file was opened successfully), never by
#                             parse_release_targets() on synthetic text,
#                             and never caught by an `except
#                             AbsentBlockError:` clause written for the
#                             genuinely-missing-file case — see "Back-fill
#                             detection" below for why that distinction is
#                             load-bearing.

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys


def git_executable():
    """Git resolved through the trusted-path seam, never a bare `git`.

    Resolved LAZILY and imported inside the call rather than at module
    scope, because this module is loaded two different ways and only one of
    them has `_gitexec` importable by name: as an ordinary sibling module
    in a host's hook directory (a plain import works), and by explicit file
    path, where nothing put this directory on `sys.path`. A module-level
    import would break the second, and would also violate the documented
    invariant that importing this mechanism has no side effects beyond the
    load itself.

    `_gitexec.py` sits beside this file wherever this file lives, so the
    fallback adds only this module's own directory.
    """
    try:
        from _gitexec import git_executable as resolve
    except ImportError:                                    # loaded by path
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from _gitexec import git_executable as resolve
    return resolve()


class ReleaseTargetsError(RuntimeError):
    """Base for every declared release-targets-file parse error. Callers that
    only care that the declaration was bad, not which rule it broke, can catch
    this one type; callers that need to react differently per violation catch
    the specific subclass."""


class AbsentBlockError(ReleaseTargetsError):
    """No delimiter block is present in the file at all."""


class EmptyBlockError(ReleaseTargetsError):
    """The delimiter block is present but contains no declaration content."""


class FileExistsNoBlockError(ReleaseTargetsError):
    """The declared-target file EXISTS on disk (it opened and read
    successfully) but contains no `<!-- release-targets -->` delimiter block
    at all.

    HIGH-1 (adversarial review 2026-07-31): before this class existed,
    `load_targets` raised the SAME `AbsentBlockError` for this case as it did
    for a genuinely missing file, because it delegated straight to
    `parse_release_targets`, which cannot tell "no text at all" from "text
    with no block in it" apart from "no file" -- it only ever sees text. An
    agent implementing the release skill's Back-fill lane literally as
    written -- catch `AbsentBlockError`, enter back-fill, "write the
    confirmed block verbatim" -- would silently overwrite an operator's
    EXISTING file that merely lacks the block, discarding whatever they
    actually put there. That is exactly the outcome the skill's own prose
    says this lane must never cause.

    Deliberately a SIBLING of `AbsentBlockError` under `ReleaseTargetsError`,
    not a subclass of it: an `except AbsentBlockError:` clause written for
    "the file is genuinely absent" (the Back-fill lane's ONE sanctioned
    trigger) continues to see only that case, unchanged, and does not
    accidentally widen to catch this one. A broad `except
    ReleaseTargetsError:` clause still catches both, as it always did. Only
    `load_targets` ever raises this -- `parse_release_targets` is pure over
    text and has no way to know whether a file existed, so its own
    AbsentBlockError-on-no-block behavior against synthetic text is
    unchanged."""


class MalformedBlockError(ReleaseTargetsError):
    """A `[target]` header is malformed (empty, or carries a character outside
    `[A-Za-z0-9._-]`), a key line appears before the first header, or a line is
    neither a header nor a `key: value` pair."""


class UnknownKeyError(ReleaseTargetsError):
    """A key outside the declared grammar (e.g. a typo) was used."""


class DuplicateKeyError(ReleaseTargetsError):
    """A scalar (non-repeating) key was declared twice within one target block."""


class DuplicateTargetError(ReleaseTargetsError):
    """The same `[target]` header was declared more than once."""


class InvalidBooleanError(ReleaseTargetsError):
    """A boolean-typed value was neither exactly `true` nor exactly `false`."""


class MultipleBlocksError(ReleaseTargetsError):
    """More than one delimiter block was found in the file."""


class ValueTooLongError(ReleaseTargetsError):
    """A declared value exceeds `VALUE_MAX_CHARS` (A-2.4, ADR-0002's
    precedent). A sibling of every other declared-file error, so it exits 4
    and never 3 -- an over-long value is a malformed declaration, never the
    genuinely-absent state that triggers the Back-fill lane."""


class DelimiterInValueError(ReleaseTargetsError):
    """A declared value contains the literal closing-delimiter text, which
    would otherwise silently truncate the block under a naive non-greedy
    match rather than being treated as part of the value."""


class MissingRequiredKeyError(ReleaseTargetsError):
    """A target block is missing one of the required keys (prefix, changelog,
    payload)."""


# A `2.9.1`-style series tag is exactly `<prefix>MAJOR.MINOR.PATCH` — no
# suffix. The anchored form already excludes pre-releases (`2.6.0-beta.1`).
#
# _PRERELEASE_MARKERS is UNREACHABLE through the public API as shipped, not a
# "second line of defense" as this comment previously claimed. The `$` anchor
# below rejects every suffixed tag, so no tag can both match the regex AND
# carry a marker in its prefix-stripped version portion — verified by probe.
# It is retained as a guard that would become load-bearing if the anchor were
# ever relaxed, and is tested via a monkeypatched unanchored matcher so the
# behavior is proven rather than assumed. Whether to delete it outright or
# make it genuinely reachable is tracked as an open question; do not read its
# presence as evidence that suffixed tags are filtered twice.
_RELEASE_RE_CACHE = {}


def _release_re(prefix):
    """The anchored `<prefix>MAJOR.MINOR.PATCH` matcher for one release series."""
    rx = _RELEASE_RE_CACHE.get(prefix)
    if rx is None:
        rx = re.compile(r"^" + re.escape(prefix) + r"(\d+)\.(\d+)\.(\d+)$")
        _RELEASE_RE_CACHE[prefix] = rx
    return rx


_PRERELEASE_MARKERS = ("-beta", "-rc", "-alpha")

# A changelog section heading, in either the `## vX.Y.Z - DATE` form or the
# Keep-a-Changelog `## [X.Y.Z] - DATE` bracket form. The capture is the bare
# `X.Y.Z`; the optional leading `v` and the surrounding brackets sit OUTSIDE
# the group, so heading comparison is style-agnostic. Any separator is
# allowed between version and date. Plus the annotated-tag `Released-at:`
# footer.
_HEADING_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
_CHANGELOG_DATE_RE = re.compile(
    r"^##\s+\[?v?\d+\.\d+\.\d+\]?\D+(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_RELEASED_AT_RE = re.compile(r"Released-at:\s*(\d{4}-\d{2}-\d{2})")

# Full SemVer, including the pre-release and build-metadata tails a release
# tag never carries but a version MANIFEST can. The anchored `_release_re`
# above deliberately rejects those, because it selects a published release
# series; this one parses a version for ORDERING, which is a different
# question and needs the tail.
# A-2.4 / ADR-0002 precedent. Named rather than inlined so the parser, the
# error message, and the tests all read the same number, and so raising it
# is one edit rather than three.
VALUE_MAX_CHARS = 1024

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def semver_key(value):
    """`"2.9.1"` -> a sortable key; `None` when `value` is not valid SemVer.

    Non-raising per this module's mechanism-function invariant. Build
    metadata is parsed and discarded: SemVer §10 says it is not part of
    precedence, so `1.0.0+a` and `1.0.0+b` compare equal.
    """
    if not isinstance(value, str):
        return None
    match = SEMVER.fullmatch(value)
    if match is None:
        return None
    prerelease = match.group(4)
    if prerelease is None:
        pre_key = None
    else:
        pre_key = tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in prerelease.split(".")
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), pre_key


def semver_greater(current, base):
    """True iff `current` is a STRICT SemVer advance over `base`.

    The single definition of "advance" every payload-version gate shares.
    Degrades to False when either side is unparseable, which refuses the
    gate rather than passing it. Pre-release ordering follows SemVer §11: a
    pre-release is LOWER than its release (`1.0.0-beta` < `1.0.0`), numeric
    identifiers compare numerically and rank below alphanumeric ones.
    """
    current_key = semver_key(current)
    base_key = semver_key(base)
    if current_key is None or base_key is None:
        return False
    if current_key[:3] != base_key[:3]:
        return current_key[:3] > base_key[:3]
    current_pre, base_pre = current_key[3], base_key[3]
    if current_pre is None:
        return base_pre is not None
    if base_pre is None:
        return False
    return current_pre > base_pre


def _bare_version(tag):
    """`v2.6.0` / `[2.6.0]` / `2.6.0` / `myapp-v0.1.31` -> the bare SemVer.

    Lets the heading match compare a tag against a bracket-style changelog
    heading without caring about either spelling.

    Anchored on the SemVer at the END rather than by stripping a known
    prefix, so a namespaced series' tag (`<prefix>vMAJOR.MINOR.PATCH`) works
    without the prefix being known here — stripping only a LEADING "v" is
    right for a bare `v2.9.1` and wrong for any namespaced series, since
    `"myapp-v0.1.31".lstrip("v")` is unchanged and never equals the `0.1.31`
    parsed out of the heading."""
    if not isinstance(tag, str):
        return tag
    text = tag.strip().strip("[]")
    match = re.search(r"(\d+\.\d+\.\d+.*)$", text)
    return match.group(1) if match else text.lstrip("v")


def last_tag_select(tags, prefix):
    """Return the highest SemVer tag in `tags` for ONE release series,
    excluding pre-releases (`-beta`/`-rc`/`-alpha`). Returns NONE_SENTINEL
    when the series has no release tag yet.

    `prefix` selects the series and is REQUIRED — this repository's default
    was a repo-specific fact (which series is "the" release) and could not
    survive as a module default without smuggling that fact back in. The
    caller supplies the prefix for the series it means, typically a value
    loaded from a declared row (see `load_targets`).

    This is the single source of `LAST_TAG`, replacing an inline grep
    one-liner: bare `git describe --tags` returns the nearest tag by commit-
    graph ANCESTRY, which in a multi-series repo is routinely another
    series' tag, and silently bases an entire release on the wrong baseline.

    Series isolation is a property of the ANCHORED match rather than a list
    of exclusions to maintain: `^v` cannot match `myapp-v0.1.30`, and
    `^myapp-v` cannot match `v2.9.1`. A new series therefore cannot leak into
    an existing one by being forgotten in an exclusion list."""
    best = None  # ((major, minor, patch), original_tag)
    if not isinstance(tags, (list, tuple)):
        return NONE_SENTINEL
    if not isinstance(prefix, str) or not prefix:
        return NONE_SENTINEL
    matcher = _release_re(prefix)
    for t in tags:
        if not isinstance(t, str):
            continue
        m = matcher.match(t)
        if not m:
            continue
        # Tested against the VERSION portion only, after the prefix is
        # stripped — never the whole tag. A consumer's own prefix can
        # legitimately contain one of these substrings (`web-beta-v`,
        # `api-rc-v`); testing the whole tag would reject every one of that
        # series' real releases, reading `<none>` as "never released" for a
        # series that has releases.
        if any(marker in t[len(prefix):] for marker in _PRERELEASE_MARKERS):
            continue
        ver = tuple(int(g) for g in m.groups())
        if best is None or ver > best[0]:
            best = (ver, t)
    return best[1] if best else NONE_SENTINEL


NONE_SENTINEL = "<none>"


def notes_heading_matches(notes_text, tag):
    """True iff the FIRST changelog heading in `notes_text` (either `## vX.Y.Z`
    or the Keep-a-Changelog `## [X.Y.Z]` form) names the same version as
    `tag`. A stale notes-file (whose first section is an older version)
    returns False, so a release lane cannot publish the wrong changelog
    section under the right tag. Missing heading or non-string input ->
    False."""
    if not isinstance(notes_text, str) or not isinstance(tag, str):
        return False
    m = _HEADING_RE.search(notes_text)
    if not m:
        return False
    return m.group(1) == _bare_version(tag)


def release_dates_consistent(changelog_section, tag_message):
    """True iff the date in `changelog_section`'s heading (`## vX.Y.Z - DATE`
    or `## [X.Y.Z] - DATE`) equals the `Released-at: DATE` date in
    `tag_message`. Guards against the date being hand-typed inconsistently
    across surfaces. Either date absent, or non-string input -> False."""
    if not isinstance(changelog_section, str) or not isinstance(tag_message, str):
        return False
    cm = _CHANGELOG_DATE_RE.search(changelog_section)
    tm = _RELEASED_AT_RE.search(tag_message)
    if not cm or not tm:
        return False
    return cm.group(1) == tm.group(1)


def classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
                           manifest_version, release_is_nondraft):
    """Classify a (re)publish attempt so a release lane can resume a
    half-finished publish instead of dead-ending on 'tag exists -> STOP'.
    Returns one of:

      publish_fresh      - no tag yet; the normal path.
      already_published  - the tag is at HEAD and a non-draft release exists.
      resume_publish     - tag is at HEAD and its version matches the
                           manifest, but no non-draft release exists (tag
                           pushed, release never created) -> finish publish.
      abort_mismatch     - tag points at a non-HEAD commit, or its version
                           disagrees with the manifest -> STOP, never overwrite.

    Mismatch OUTRANKS publication state. An existing release used to
    short-circuit to `already_published` before the tag was compared to
    HEAD, so a resumed publish could silently accept a release whose tag
    installs a different snapshot. The tag is what consumers actually fetch;
    if it does not name this commit, nothing about the release makes the
    state safe.
    """
    if not tag_exists:
        return "publish_fresh"
    if tag_sha != head_sha or tag_version != manifest_version:
        return "abort_mismatch"
    if release_is_nondraft:
        return "already_published"
    return "resume_publish"


def select_release_target_by_name(pairs, targets):
    """Resolve a release dispatch from NAME-KEYED inputs (A-4.2).

    `pairs` are `name=value` strings — one per confirmation input, each
    carrying the target it belongs to. `targets` is the declared register.
    Returns the same label vocabulary as the positional resolver:

      <target>   exactly one non-blank value; that target
      none       nothing supplied; nothing to publish
      multiple   more than one; ambiguous, MUST be refused
      unknown    a pair names a target the declared file does not contain

    WHY NAME-KEYED. The positional form aligns confirmations to `targets`
    by INDEX, so it is correct only while the workflow's input order and
    the declared file's row order agree. Nothing enforced that. Insert a
    row in the middle of the declared file, or reorder the workflow's
    inputs, and every confirmation shifts by one — a dispatch meaning to
    publish the second declared target publishes the first instead, with a
    `contents: write` token, and every downstream check passes because the
    wrong release is internally consistent. Order was load-bearing and
    invisible.

    `unknown` is deliberately a LABEL, not an exception, matching this
    module's "prints a label and never raises" contract for the release
    lane. It is also deliberately not `none`: a caller's fail-closed
    default arm refuses both, but only one of them means "somebody named a
    target that does not exist", which is a declaration/workflow
    disagreement worth reporting rather than a quiet no-op.

    Blank-ish values count as not-selected, exactly as in the positional
    form, so a stray space cannot read as a second target. A pair with no
    `=` at all is ignored rather than fatal — an empty workflow input can
    arrive as a bare name — but a pair whose NAME is unknown is reported,
    because that is a real mismatch rather than an empty slot.

    Pure and non-raising over synthetic input.
    """
    known = [t for t in targets if isinstance(t, str)] if isinstance(
        targets, (list, tuple)) else []
    selected = []
    for pair in (pairs if isinstance(pairs, (list, tuple)) else []):
        if not isinstance(pair, str) or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        if name and name not in known:
            return "unknown"
        if value.strip():
            selected.append(name)
    if not selected:
        return "none"
    if len(set(selected)) > 1 or len(selected) > 1:
        return "multiple"
    return selected[0]


def select_release_target(*confirmations, targets):
    """Resolve which single target a release dispatch selected.
    `confirmations` are the per-target version inputs, positionally aligned
    with `targets`. `targets` is REQUIRED — the register of releasable names
    is a repo-specific fact and cannot survive as a module default. Returns
    one of:

      <target>   - exactly one input was supplied; the matching name from
                   `targets`.
      none       - no input was supplied; there is nothing to publish.
      multiple   - more than one; the dispatch is ambiguous and MUST be
                   refused.
      arity      - `confirmations` and `targets` are not the same length.

    Selection is one decision, made once, by a caller that holds no write
    token of its own, so a dispatch that supplies more than one confirmation
    can never start two `contents: write` publishers. Blank-ish input
    (whitespace, non-string) counts as "not selected" so a stray space can
    never read as a second target.

    The count is checked against `targets` rather than zipped-to-shortest on
    purpose: a caller wired for fewer targets than were actually supplied
    would otherwise silently resolve the wrong one. `arity` is not a target
    and is meant to match no dispatch case, so a caller's fail-closed default
    arm refuses it - and, like every other return here, it is a LABEL rather
    than an exception, so a caller's contract of "prints a label and never
    raises" holds."""
    def _selected(value):
        return isinstance(value, str) and value.strip() != ""

    if not isinstance(targets, (list, tuple)):
        return "arity"
    if len(confirmations) != len(targets):
        return "arity"
    selected = [target for target, value in zip(targets, confirmations)
                if _selected(value)]
    if len(selected) > 1:
        return "multiple"
    if selected:
        return selected[0]
    return "none"


def classify_merge_readiness(check_runs, head_sha, check_name):
    """Classify the merge-readiness evidence for ONE exact commit. `check_runs`
    is the `check_runs` array from a commit's check-runs API response.
    `check_name` — the single aggregate check that means "every required job
    for this commit concluded green" — is REQUIRED: its exact text is a
    repo-specific fact (this codebase's own CI vocabulary) and cannot survive
    as a module default. Returns one of:

      green           - the gate ran for this commit, completed, and succeeded.
      missing         - no check run by that name is present at all.
      pending         - present but not `completed` (queued / in_progress / ...).
      sha_mismatch    - a matching run reports a different `head_sha`.
      not_successful  - completed with any conclusion other than `success`
                        (failure, cancelled, skipped, timed_out, neutral, ...).

    A hosted release workflow that only proves it was dispatched from a
    protected branch shows how a commit ENTERED that branch, not that
    post-merge evidence exists for the exact commit about to be tagged.

    Fail-closed throughout: unparseable input is `missing`, and several runs
    share one name only when a re-run is in flight - we cannot tell which
    verdict is authoritative, so EVERY matching run must be green."""
    if not isinstance(check_runs, list):
        return "missing"
    matching = [run for run in check_runs
                if isinstance(run, dict) and run.get("name") == check_name]
    if not matching:
        return "missing"
    if any(run.get("head_sha") != head_sha for run in matching):
        return "sha_mismatch"
    if any(run.get("status") != "completed" for run in matching):
        return "pending"
    if any(run.get("conclusion") != "success" for run in matching):
        return "not_successful"
    return "green"


# Conventional-Commits subject grammar: `type(optional-scope)!: subject`.
# The `!` sits AFTER the closing paren when a scope is present and directly
# after the type when it is not -- both spellings mark a breaking change,
# and a hand-rolled `split(':')[0]` that strips `!` before checking for it
# loses the marker entirely.
_CC_SUBJECT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s")

# `BREAKING CHANGE:` (and the hyphenated spelling the spec also permits) as
# a FOOTER -- at the start of its own line, never mid-sentence, so prose
# that merely discusses a breaking change does not silently bump a major.
_BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_CHANGELOG_FOOTER_RE = re.compile(r"^CHANGELOG:", re.MULTILINE)

# Which types bump, and to what. `refactor` bumps patch and IS harvested
# (see the changelog-grouping rule); `docs`/`chore`/`test`/`ci` bump
# nothing but may still carry a harvested footer.
_BUMPING_TYPES = {"feat": "minor", "fix": "patch", "perf": "patch",
                  "refactor": "patch"}
_BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def row_assertions(row):
    """Which release-lane steps a row's DECLARED FIELDS turn on (A-3.1..3.5).

    Returns a dict:

      version_source        "manifest" | "tag"
      assert_manifest_equal bool   -- A-3.1/3.2
      manifests             list   -- every declared manifest path
      rebuild               str|None
      artifacts             list   -- asserted clean after `rebuild` (A-3.3)
      payload_exclude       list   -- removed from the window (A-3.4)
      record_provenance     bool   -- A-3.5
      skipped               list   -- steps that do NOT apply, each with a
                                      reason, so the report can say a step
                                      was SKIPPED rather than leaving the
                                      reader to infer it from silence

    The five criteria are not independent: "declares no manifest" IS "the
    tag is the version source". Deriving them together makes the two
    answers structurally incapable of disagreeing, which two separate
    checks could not promise.

    `skipped` exists because the skill's own rule is that a skipped step
    and a forgotten step must never look alike. An optional field's absence
    is a decision the operator made; reporting it explicitly is what makes
    the difference visible in the release report.

    This REPORTS what applies; it performs none of it. `check-manifests`
    does the equality comparison and `run-pre-tag` runs the commands.
    Folding execution in here would make one function both planner and
    actor, and this lane's history is that the planner/actor seam is
    exactly where its defects have lived.

    Pure and non-raising: a non-dict yields the all-absent shape.
    """
    if not isinstance(row, dict):
        row = {}

    def _list(key):
        value = row.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str) and v.strip()]
        return [value] if isinstance(value, str) and value.strip() else []

    manifests = _list("manifest")
    artifacts = _list("artifacts")
    excludes = _list("payload_exclude")
    rebuild = row.get("rebuild") if isinstance(row.get("rebuild"), str) else None
    provenance = row.get("provenance_manifest")
    provenance = provenance if isinstance(provenance, str) and provenance.strip() else None

    skipped = []
    if not manifests:
        skipped.append(("manifest-equality",
                        "the row declares no manifest, so the derived tag is "
                        "the version source and there is nothing to compare"))
    if rebuild is None:
        skipped.append(("rebuild",
                        "the row declares no rebuild command"))
    if not artifacts:
        skipped.append(("artifacts-clean",
                        "the row declares no artifacts to assert clean"))
    if not excludes:
        skipped.append(("payload-exclude",
                        "the row excludes nothing from its payload"))
    if provenance is None:
        skipped.append(("provenance-recording",
                        "the row declares no provenance-manifest"))

    return {
        "version_source": "manifest" if manifests else "tag",
        "assert_manifest_equal": bool(manifests),
        "manifests": manifests,
        "rebuild": rebuild,
        "artifacts": artifacts,
        "payload_exclude": excludes,
        "record_provenance": provenance is not None,
        "provenance_manifest": provenance,
        "skipped": skipped,
    }


def window_excludes_payload_paths(paths, payload, payload_exclude):
    """`paths` filtered to `payload`, minus anything under an exclude (A-3.4).

    Directory-prefix semantics on normalized separators, so `tools` never
    matches `toolsmith/` — a substring test would silently drop a sibling
    directory whose name merely starts the same way.

    Pure over synthetic input; non-raising.
    """
    def _norm(value):
        return str(value).replace("\\", "/").strip().strip("/") if value else ""

    scope = _norm(payload)
    excludes = [_norm(e) for e in (payload_exclude or []) if _norm(e)]
    kept = []
    for path in (paths or []):
        rel = _norm(path)
        if not rel:
            continue
        if scope and scope != "." and not (rel == scope or rel.startswith(scope + "/")):
            continue
        if any(rel == ex or rel.startswith(ex + "/") for ex in excludes):
            continue
        kept.append(path)
    return kept


def provenance_trigger_paths(rows):
    """Every path a declared row REFERENCES, sorted and de-duplicated:
    each `manifest`, each `changelog`, and each `artifacts` entry (A-5.6).

    These are the drift triggers for `.codearbiter/.provenance/release-
    targets.json`. The point is that the declaration and the files it names
    move together: if a manifest path is renamed and the row is not
    updated, the row now points at nothing, and the release lane resolves
    it to a missing file at the worst possible moment.

    Deliberately NOT a CONTEXT.md-Scope trigger. `compute_drift` compares
    whole-file git oids with no section-level machinery, so a Scope trigger
    would fire on an unrelated `stage:` flip AND stay silent on the thing
    that matters -- a manifest path moving. Wrong in both directions.

    `payload` and `payload-exclude` are excluded on purpose: they are
    directory scopes, not files, and hashing a directory path is not
    something `batch_hash` can do. `pre-tag`/`rebuild`/`generate` are
    excluded too -- they are commands, not paths, and a command string is
    not a file whose oid can drift.

    Routine per-release version bumps WILL trip these triggers, by design:
    a release edits its manifest, which is the point of watching it.
    `heal_worklist` re-baselines them in the same release commit. That is
    recorded here so a later maintainer reads it as intended behaviour
    rather than deleting the triggers to quiet the noise.

    Pure and non-raising over synthetic input.
    """
    paths = set()
    if not isinstance(rows, (list, tuple)):
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("manifest", "changelog", "artifacts", "generated_manifest"):
            value = row.get(key)
            for item in (value if isinstance(value, list) else [value]):
                if isinstance(item, str) and item.strip():
                    paths.add(item.strip())
    return sorted(paths)


def _manifest_version(path):
    """The `version` a manifest declares, or `None` when it cannot be read
    or parsed. Dispatches on EXTENSION, because the declared-file grammar
    permits any format and one reader cannot serve them all -- applying a
    JSON parser to a `pyproject.toml` raises rather than answering.

    `None` means "no comparison happened", which callers MUST keep
    distinct from "the versions differ". Non-raising, per this module's
    mechanism invariant.
    """
    lower = str(path).lower()
    try:
        if lower.endswith(".json"):
            import json
            with open(path, encoding="utf-8") as fh:
                value = json.load(fh).get("version")
        elif lower.endswith(".toml"):
            try:
                import tomllib
            except ImportError:  # pragma: no cover - Python < 3.11
                return None
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
            value = data.get("project", {}).get("version")
            if value is None:
                value = data.get("tool", {}).get("poetry", {}).get("version")
        else:
            return None
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return value if isinstance(value, str) else None


def classify_commit(subject, body=""):
    """One commit -> `{type, scope, breaking, bump, has_changelog_footer}`.

    Pure and non-raising over synthetic input, per this module's mechanism
    invariant: a subject that is not Conventional-Commits at all yields
    `type=""`, `bump="none"` -- an unparseable subject cannot bump, which
    is the safe direction.

    Exists because this was the last mechanical step in the release lane
    with no helper behind it, on the check the hard rules mark MUST-level
    (adversarial review run 11). An exercising agent wrote
    `subject.split('(')[0].split(':')[0].rstrip('!')` as its own reading;
    that strips the `!` BEFORE anything checks for it, so `feat!:` and
    `feat(api)!:` both classify as an ordinary `feat` and a major release
    silently becomes a minor one. Two operators writing two parses produce
    two different gates on the check that decides whether a release may
    proceed.
    """
    if not isinstance(subject, str):
        subject = ""
    if not isinstance(body, str):
        body = ""
    match = _CC_SUBJECT_RE.match(subject)
    if match is None:
        return {"type": "", "scope": "", "breaking": False, "bump": "none",
                "has_changelog_footer": bool(_CHANGELOG_FOOTER_RE.search(body))}
    ctype = match.group("type").lower()
    breaking = bool(match.group("bang")) or bool(_BREAKING_FOOTER_RE.search(body))
    if breaking:
        bump = "major"
    else:
        bump = _BUMPING_TYPES.get(ctype, "none")
    return {
        "type": ctype,
        "scope": match.group("scope") or "",
        "breaking": breaking,
        "bump": bump,
        "has_changelog_footer": bool(_CHANGELOG_FOOTER_RE.search(body)),
    }


def classify_window(commits):
    """`[{sha, subject, body}, ...]` -> the whole window's verdict:
    `{bump, commits: [...], missing_footer: [...]}`.

    `bump` is the highest precedence across the window (`major` > `minor`
    > `patch` > `none`). `missing_footer` lists every BUMPING commit with
    no `CHANGELOG:` footer -- the exact set Phase 1 step 3 turns into
    `[NEEDS-TRIAGE]` lines, in window order, so the report's shape is not
    re-derived per release either.

    A breaking commit bumps major regardless of type, so a `chore!:` is
    reported as bumping and IS subject to the footer rule -- a hand-rolled
    type-list check misses that, because `chore` is not in the bumping
    list.
    """
    rows = []
    if not isinstance(commits, (list, tuple)):
        commits = []
    for entry in commits:
        if not isinstance(entry, dict):
            continue
        verdict = classify_commit(entry.get("subject", ""), entry.get("body", ""))
        verdict["sha"] = str(entry.get("sha", ""))
        verdict["subject"] = str(entry.get("subject", ""))
        rows.append(verdict)
    bump = "none"
    for row in rows:
        if _BUMP_RANK[row["bump"]] > _BUMP_RANK[bump]:
            bump = row["bump"]
    missing = [r for r in rows
               if r["bump"] != "none" and not r["has_changelog_footer"]]
    return {"bump": bump, "commits": rows, "missing_footer": missing}


def parse_window_log(text):
    """`git log --pretty=format:%H%n%s%n%b%n----` output -> the
    `[{sha, subject, body}]` shape `classify_window` consumes.

    The separator is the one the release skill already prescribes, so the
    prose and this parser cannot drift apart into two different readings
    of the same command's output.
    """
    if not isinstance(text, str):
        return []
    entries = []
    for chunk in text.split("\n----"):
        lines = [ln for ln in chunk.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines or not lines[0].strip():
            continue
        sha = lines[0].strip()
        subject = lines[1] if len(lines) > 1 else ""
        body = "\n".join(lines[2:])
        entries.append({"sha": sha, "subject": subject, "body": body})
    return entries


def first_release_baseline(adoption_log_text):
    """The commit sha that ADOPTED codeArbiter -- the one that added
    `.codearbiter/CONTEXT.md` -- from `git log --diff-filter=A
    --format=%H -- .codearbiter/CONTEXT.md` output. `""` when the file was
    never added (no adoption commit, or a repo that never onboarded).

    A-5.5. On a project's FIRST release the tag series is empty, so
    `LAST_TAG` is `<none>` and the window is the entire history. Every
    pre-adoption `feat`/`fix`/`perf`/`refactor` commit therefore enters
    the footer-completeness check -- and none of them carries a
    `CHANGELOG:` footer, because they predate the convention entirely. The
    lane would emit one `[NEEDS-TRIAGE]` line per such commit and STOP: a
    repository adopting at its 500th commit gets a 500-line block on a
    release where nothing is actually wrong. That is a hard block on a
    legitimate release, and it lands on precisely the population the
    Back-fill lane exists to serve.

    The adoption commit is the honest boundary: commits before it were
    authored under no changelog convention and cannot retroactively
    acquire footers, while commits after it were authored under one and
    SHOULD be held to it.

    Non-raising and pure over text, per this module's mechanism-function
    invariant. Takes the LAST line when several are present: `git log`
    prints newest-first, so the last line is the EARLIEST addition, which
    is the real adoption. (A file added, deleted, and re-added produces
    two entries -- taking the newest would silently treat a re-adoption as
    the boundary and drop every commit between the two, which is the same
    class of quiet history loss this function exists to prevent.)
    """
    if not isinstance(adoption_log_text, str):
        return ""
    shas = [line.strip().split()[0] for line in adoption_log_text.splitlines()
            if line.strip()]
    if not shas:
        return ""
    candidate = shas[-1]
    return candidate if re.fullmatch(r"[0-9a-fA-F]{7,64}", candidate) else ""


def peel_tag(ls_remote_text, tag):
    """Resolve the COMMIT a remote tag names, from `git ls-remote --tags`
    output. Returns "" when the tag is absent.

    An annotated tag's own object id is not the commit it points at; the
    peeled `refs/tags/<tag>^{}` line is. A workflow that treats any remote
    hit as a resumable publish without comparing the tag to the current
    commit can accept a stale tag as a successful rerun and publish for the
    wrong commit. Matching is exact on the ref name, so `v2.6.0` is never
    resolved from `v2.6.0-beta.1`."""
    if not isinstance(ls_remote_text, str) or not isinstance(tag, str):
        return ""
    direct = peeled = ""
    ref = f"refs/tags/{tag}"
    for line in ls_remote_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        if name == ref + "^{}":
            peeled = sha
        elif name == ref:
            direct = sha
    return peeled or direct


# --------------------------------------------------------------------------- #
# Declared-target-file parser. Grammar: per-target `[name]` sub-blocks of
# `key: value` lines inside the HTML-comment delimiter convention this
# codebase's path-scope reader (`_scopelib.py`) already uses — reused here
# rather than inventing a second delimiter syntax.
# --------------------------------------------------------------------------- #

_OPEN_RE = re.compile(r"<!--\s*release-targets\s*-->")
_CLOSE_RE = re.compile(r"<!--\s*/release-targets\s*-->")
_HEADER_RE = re.compile(r"^\[([A-Za-z0-9._-]+)\]$")

# A key not in _LIST_KEYS is scalar: exactly one value per target block, a
# second occurrence of the same key within one block is a DuplicateKeyError.
# List keys repeat by design and preserve declaration order.
_LIST_KEYS = frozenset({
    "manifest", "artifacts", "pre-tag", "payload-exclude", "generated-manifest",
})
_BOOLEAN_KEYS = frozenset({"latest-eligible"})
_REQUIRED_KEYS = ("prefix", "changelog", "payload")

# Grammar key -> row field name (rows use `_` throughout, the grammar uses
# `-`, matching this codebase's `key: value` / `snake_case` convention split).
_KEY_FIELD = {
    "prefix": "prefix",
    "changelog": "changelog",
    "payload": "payload",
    "rebuild": "rebuild",
    "provenance-manifest": "provenance_manifest",
    "latest-eligible": "latest_eligible",
    "manifest": "manifest",
    "artifacts": "artifacts",
    "pre-tag": "pre_tag",
    "payload-exclude": "payload_exclude",
    # HIGH-3 (adversarial review 2026-07-31): a `manifest` path that is
    # GENERATED output (regenerated by a build/packaging step, never
    # hand-written) is otherwise indistinguishable from an ordinary
    # hand-edited manifest, so nothing stops the generic "update every
    # manifest path to the derived version" instruction from hand-editing
    # generated output. `generated-manifest` names the subset of `manifest`
    # entries that are generated.
    #
    # This is TWO keys, not the one-key "marker on the manifest entry" the
    # finding also offered as an option. `rebuild` already exists as an
    # operator-authored, mutating command this lane runs, so pairing
    # `generated-manifest` with its own `generate` command (mirroring the
    # existing `rebuild`/`artifacts` shape) creates no NEW trust class on
    # this file — it reuses one already present. `rebuild` itself cannot be
    # reused for this: its contract is "run it, then `git diff --quiet` the
    # result" (nothing should have changed beyond what was already
    # committed), whereas regenerating a version manifest legitimately
    # CHANGES the file on every release. Folding a version-bump
    # regeneration into `rebuild`'s clean-tree contract would make every
    # release's own `generate` step look like build drift. A single-key
    # marker form (e.g. a `[generated]` suffix on the `manifest:` value
    # itself) would need its own value-shape parsing distinct from every
    # other list key's plain-path values for no offsetting benefit, since a
    # command is exactly what a caller needs to run anyway.
    #
    # `generate` widens this file's own executable-input surface by one key
    # while the H-22 protected-state enrolment of this file (T-33) and its
    # security-controls.md boundary entry (T-32) are both still PENDING on
    # this repo's own plan — declared here, not smuggled: see
    # `.codearbiter/release-targets.md`'s own header note.
    #
    # Declarative only — this module does not cross-validate that a
    # `generated-manifest` entry also appears in `manifest`, the same way it
    # does not validate `payload-exclude` against `payload`; the release
    # skill is what acts on the relationship.
    "generated-manifest": "generated_manifest",
    "generate": "generate",
    # M-1 (adversarial review 2026-07-31): the Phase-3 Release title names a
    # "display name" no grammar key ever supplied, so a consumer had no way
    # to declare one and this repo's own next release would silently title
    # itself from `$TARGET` (`ca`) rather than its established display name
    # (`codeArbiter`). Optional; the skill falls back to `$TARGET` itself
    # when a row declares none.
    "display-name": "display_name",
}


def _new_row(name):
    return {
        "target": name,
        "prefix": None,
        "manifest": [],
        "changelog": None,
        "payload": None,
        "payload_exclude": [],
        "rebuild": None,
        "artifacts": [],
        "provenance_manifest": None,
        "pre_tag": [],
        "latest_eligible": False,
        "generated_manifest": [],
        "generate": None,
        "display_name": None,
    }


def _finish_row(row):
    # A parsed key line always assigns a string (`.strip()`-ed at read time),
    # so `prefix:` with no value yields `''`, never `None` — an `is None`
    # check alone lets that empty declaration pass as "present". Treat a
    # blank or whitespace-only value as missing too, so a typo'd required key
    # cannot silently become a first-release baseline downstream (`''` fed to
    # `last_tag_select` resolves the NONE_SENTINEL).
    missing = [key for key in _REQUIRED_KEYS
               if (row[_KEY_FIELD[key]] or "").strip() == ""]
    if missing:
        raise MissingRequiredKeyError(
            f"target {row['target']!r} is missing required key(s): "
            + ", ".join(missing)
        )


def parse_release_targets(text):
    """Parse the declared-target-file GRAMMAR from `text` (already-read file
    content) into a list of row dicts, one per `[target]` block, each
    carrying: target, prefix, manifest (list), changelog, payload,
    payload_exclude (list), rebuild, artifacts (list), provenance_manifest,
    pre_tag (list), latest_eligible (bool), generated_manifest (list),
    generate, display_name.

    Pure — no file I/O — so it is testable with synthetic input; `load_targets`
    is the one function that touches the filesystem.

    Every parser-contract violation raises its own ReleaseTargetsError
    subclass; never a silent default, never a partial parse. See the module
    docstring for the full list of declared exceptions.

    Cross-platform LF/CRLF editing drift means a value like
    `latest-eligible: true\\r` must parse as the boolean `true`, not as an
    unrecognised value that would otherwise silently drop a feature — the
    exact silent-default failure this module's loud-failure contract
    forbids. There is no dedicated CRLF-stripping pass: every line is
    `.strip()`-ed on extraction from the block (`raw_line.strip()` below)
    and every key/value pair is independently `.strip()`-ed again off the
    split — Python's `str.strip()` with no argument removes `\\r` along with
    every other whitespace character, so a trailing `\\r` never survives to
    a comparison regardless of which layer runs first."""
    if not isinstance(text, str):
        # Every declared parser-contract violation raises a ReleaseTargetsError
        # subclass so a caller can catch one type (see module docstring); a
        # non-string input must not be the one escape hatch that raises a bare
        # TypeError instead. There is no block to find in non-text input, so
        # this is the same declared answer as an absent block.
        raise AbsentBlockError(
            "no <!-- release-targets --> block found (input is not text)")
    normalized = text

    opens = list(_OPEN_RE.finditer(normalized))
    if not opens:
        raise AbsentBlockError("no <!-- release-targets --> block found")
    if len(opens) > 1:
        raise MultipleBlocksError(
            f"found {len(opens)} <!-- release-targets --> opening delimiters; "
            "exactly one is allowed")

    after_open = normalized[opens[0].end():]
    closes = list(_CLOSE_RE.finditer(after_open))
    if not closes:
        raise MalformedBlockError(
            "<!-- release-targets --> block is never closed")

    # The GENUINE closing delimiter is the first match that sits ALONE on its
    # line (only whitespace precedes it since the last newline). A match that
    # is preceded by other content on the same line is embedded inside a
    # declared value (e.g. `rebuild: echo <!-- /release-targets -->`) and
    # must error rather than silently become the block boundary — otherwise a
    # value's embedded delimiter truncates the block and, for a REQUIRED key,
    # can silently empty it (`payload: <!-- /release-targets -->` would parse
    # with `payload == ''`). A close match that occurs entirely AFTER the
    # genuine terminator — a legitimate stray mention of the delimiter text in
    # prose following the block — is not inspected at all, so it can never be
    # misdiagnosed as a value violation.
    genuine = None
    for m in closes:
        line_start = after_open.rfind("\n", 0, m.start()) + 1
        prefix = after_open[line_start:m.start()]
        if prefix.strip() == "":
            genuine = m
            break
        raise DelimiterInValueError(
            "a declared value contains the literal closing delimiter "
            "'<!-- /release-targets -->', which would truncate the block "
            "under a naive parse instead of being treated as part of the value")

    block = after_open[:genuine.start()]
    if not block.strip():
        raise EmptyBlockError("<!-- release-targets --> block is empty")

    rows = []
    row = None
    seen_keys = None
    seen_names = set()

    for raw_line in block.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("["):
            m = _HEADER_RE.match(line)
            if not m:
                raise MalformedBlockError(
                    f"malformed target header: {raw_line!r}")
            name = m.group(1)
            if name in seen_names:
                raise DuplicateTargetError(f"duplicate target block: {name!r}")
            seen_names.add(name)
            if row is not None:
                _finish_row(row)
                rows.append(row)
            row = _new_row(name)
            seen_keys = set()
            continue

        if row is None:
            raise MalformedBlockError(
                f"key line before the first [target] header: {raw_line!r}")

        idx = line.find(":")
        if idx == -1:
            raise MalformedBlockError(
                f"malformed line (expected 'key: value'): {raw_line!r}")
        key = line[:idx].strip()
        value = line[idx + 1:].strip()

        if key not in _KEY_FIELD:
            raise UnknownKeyError(
                f"unknown key {key!r} in target {row['target']!r}")
        field = _KEY_FIELD[key]

        # A-2.4: a declared value longer than VALUE_MAX_CHARS is rejected,
        # on ADR-0002's precedent. Checked for EVERY key, not only
        # `pre-tag`: the cap exists because these values are operator-
        # authored input a `contents: write` lane later executes or
        # interpolates, and `rebuild`/`generate` are executed exactly like
        # `pre-tag` is. Capping only the key that motivated the rule would
        # leave the same exposure one field over.
        if len(value) > VALUE_MAX_CHARS:
            raise ValueTooLongError(
                f"key {key!r} in target {row['target']!r} declares a value "
                f"of {len(value)} characters, over the {VALUE_MAX_CHARS}-"
                "character limit. A declared value this long is far more "
                "likely to be a smuggled command line than a path or a "
                "build invocation")

        if key in _LIST_KEYS:
            row[field].append(value)
            continue

        if key in seen_keys:
            raise DuplicateKeyError(
                f"duplicate key {key!r} in target {row['target']!r}")
        seen_keys.add(key)

        if key in _BOOLEAN_KEYS:
            if value == "true":
                row[field] = True
            elif value == "false":
                row[field] = False
            else:
                raise InvalidBooleanError(
                    f"key {key!r} in target {row['target']!r} must be "
                    f"exactly 'true' or 'false', got {value!r}")
        else:
            row[field] = value

    if row is not None:
        _finish_row(row)
        rows.append(row)

    return rows


def load_targets(path):
    """Read `path` and parse it via `parse_release_targets`. The one function
    in this module that touches the filesystem — opened with `newline=""` so
    a `\\r\\n` line ending survives into the parser exactly as it is on disk,
    rather than being silently normalised away by Python's own text-mode
    universal-newline translation before this module's own CRLF handling
    ever runs.

    An unreadable path (missing file, permission error, a directory, ...)
    raises `AbsentBlockError` rather than a bare `OSError` — the same
    declared-error contract `parse_release_targets` gives every other
    violation, so a `contents: write` caller can catch one exception type
    instead of one type for content problems and another for I/O ones. There
    is, in the end, no block to find at an unreadable path either.

    An EXISTING, readable file that simply carries no delimiter block is a
    DIFFERENT failure (HIGH-1, adversarial review 2026-07-31) and raises
    `FileExistsNoBlockError` instead — see that class's docstring. This
    function is the only place that distinction can be made, since it is the
    only one that knows whether `open()` actually succeeded."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise AbsentBlockError(
            f"could not read release-targets file {path!r}: {exc}") from exc
    try:
        return parse_release_targets(text)
    except AbsentBlockError as exc:
        # The open() above already succeeded, so this is NOT "no file" -- it
        # is "a file that exists and contains no block". Re-raised under the
        # sibling class so a caller's `except AbsentBlockError:` (the
        # Back-fill lane's trigger) never mistakes the two states for one
        # another.
        raise FileExistsNoBlockError(
            f"{path!r} exists but contains no <!-- release-targets --> "
            f"block: {exc}") from exc


# --------------------------------------------------------------------------- #
# Back-fill detection (T-49/T-50, issue #563, spec AC-5.3/5.4). Fires only
# when a caller has already observed `load_targets` raise `AbsentBlockError`
# — a genuinely MISSING declared file. `load_targets` itself is unchanged and
# keeps raising on absence; nothing here is a silent default inside the
# parser. An unparseable EXISTING file (any other ReleaseTargetsError
# subclass) is a different failure and is never routed through this — the
# release skill's own "Targets" prose still STOPs outright on that case.
#
# Detection is honest about ambiguity by construction: it never returns a
# single guess unless the scan found EXACTLY one candidate manifest and
# EXACTLY one candidate changelog. Zero of either (nothing plausible) or more
# than one of either (several plausible candidates, no signal for which one)
# both raise `BackfillAmbiguousError` — the caller (the release skill's
# back-fill lane) surfaces that as "cannot propose a row, route to full
# elicitation instead" rather than inventing a target from a guess.
# --------------------------------------------------------------------------- #

# Generic, ecosystem-level manifest/changelog filenames — not a fact about
# any one consuming repository, so these stay clear of the module denylist
# (A-1.2) the same way the shared grammar keys already do.
BACKFILL_MANIFEST_CANDIDATES = (
    "package.json", "pyproject.toml", "Cargo.toml", "composer.json",
)
BACKFILL_CHANGELOG_CANDIDATES = (
    "CHANGELOG.md", "CHANGES.md", "HISTORY.md",
)

# The generic single-target example name/prefix this module's own docstring
# and the release-portable-fixture spec's grammar section both use for a
# one-target consumer (`[app]` / `prefix: v`) — reused here as the back-fill
# lane's default rather than restated as a second, drifting copy.
_BACKFILL_DEFAULT_TARGET = "app"
_BACKFILL_DEFAULT_PREFIX = "v"


class BackfillAmbiguousError(ReleaseTargetsError):
    """Raised by `detect_candidate_target` when the scan found zero, or more
    than one, candidate manifest or changelog file. A repo with several
    plausible manifests (or none) must not receive a confidently-wrong
    proposal — the never-guess posture this whole module's parser already
    applies to a malformed declaration applies here too, to an AMBIGUOUS
    absence rather than a malformed one."""


def scan_backfill_candidates(root):
    """The one filesystem reader for back-fill detection: lists `root`'s
    top-level entries and returns `(manifest_candidates, changelog_candidates)`
    — the repo-relative names present from `BACKFILL_MANIFEST_CANDIDATES` and
    `BACKFILL_CHANGELOG_CANDIDATES`, each sorted for determinism. Deliberately
    a TOP-LEVEL-ONLY scan: this is a first-pass detection that gets PRESENTED
    to the user for explicit confirmation, never a silent multi-directory
    guess. An unreadable `root` degrades to "nothing found" (both lists
    empty) rather than raising — the caller's own ambiguity handling already
    treats "zero candidates" as a case to surface, so a missing/unreadable
    root reaches the same honest "cannot propose one" outcome instead of a
    bare `OSError` escaping a detection helper."""
    try:
        entries = set(os.listdir(root))
    except OSError:
        entries = set()
    manifests = sorted(name for name in BACKFILL_MANIFEST_CANDIDATES
                        if name in entries)
    changelogs = sorted(name for name in BACKFILL_CHANGELOG_CANDIDATES
                         if name in entries)
    return manifests, changelogs


def detect_candidate_target(manifest_candidates, changelog_candidates,
                             target=_BACKFILL_DEFAULT_TARGET,
                             prefix=_BACKFILL_DEFAULT_PREFIX):
    """Pure detection logic over an ALREADY-SCANNED set of candidate names
    (`scan_backfill_candidates` is the one filesystem reader, kept separate
    per this module's read-isolation convention). Returns a row dict shaped
    like one `load_targets` entry (`target`, `prefix`, `manifest`,
    `changelog`, `payload`, `latest_eligible`) ONLY when exactly one manifest
    candidate and exactly one changelog candidate were found. Raises
    `BackfillAmbiguousError` for every other case — zero or multiple of
    either — naming which side was ambiguous and what was found, so a caller
    surfacing the error has something concrete to show the user.

    HIGH-2 (adversarial review 2026-07-31): the returned row declares
    `latest_eligible: True`. This detector can only ever propose ONE row —
    it fires on a SINGLE candidate manifest and a SINGLE candidate
    changelog, which is what "back-fill a consumer with no declared file
    yet" means by construction — so the project it is proposing a row for
    is, at the moment of detection, a single-target project. The release
    skill's hard rule ("at most one declared target may set
    `latest-eligible: true`, and every other target's Phase-3 publish MUST
    pass `--latest=false` EXPLICITLY") was written to stop one of several
    SIBLING series stealing the "Latest" badge from another in a
    multi-target repository; applied unconditionally to a single-target
    project's own first-ever release, the same rule demoted the one release
    that exists out of the position every visitor sees, with nothing in the
    lane prompting the operator to notice or correct it. Declaring the key
    explicitly here — rather than leaving the rule to somehow infer
    "solo project" from a file that names only one target — is also the
    more honest choice for a project that later adds a SECOND target: the
    Back-fill lane's own "Present, and require explicit confirmation"
    step already shows this exact printed block to the operator verbatim
    before anything is written, so `latest-eligible: true` is a line they
    read and can strike, not a behavior that silently changes the day a
    second row is declared by hand."""
    # Plain ASCII throughout this message, deliberately: unlike every
    # DOCSTRING/comment in this module, this text is actually written to a
    # CLI's stdout/stderr and captured by a real subprocess call. A child
    # Python process with no PYTHONIOENCODING/PYTHONUTF8 set encodes its
    # stdout/stderr using the ambient console codepage on Windows (not
    # UTF-8), so a non-ASCII character here (an em-dash raised this exact
    # failure, verified) can produce bytes a UTF-8-decoding parent
    # (`subprocess.run(..., encoding="utf-8")`) cannot decode at all.
    if len(manifest_candidates) != 1:
        raise BackfillAmbiguousError(
            f"found {len(manifest_candidates)} candidate manifest file(s) "
            f"({', '.join(manifest_candidates) or 'none'}) - cannot propose "
            "a single release-targets.md row without asking which one")
    if len(changelog_candidates) != 1:
        raise BackfillAmbiguousError(
            f"found {len(changelog_candidates)} candidate changelog file(s) "
            f"({', '.join(changelog_candidates) or 'none'}) - cannot propose "
            "a single release-targets.md row without asking which one")
    return {
        "target": target,
        "prefix": prefix,
        "manifest": [manifest_candidates[0]],
        "changelog": changelog_candidates[0],
        "payload": ".",
        "latest_eligible": True,
    }


def format_release_targets_block(row):
    """Render one `load_targets`-loadable file body from a row dict shaped
    like `detect_candidate_target`'s return value (or any dict carrying at
    least `target`, `prefix`, `changelog`, `payload`, and a `manifest` list).
    Round-trips through `parse_release_targets` — this is the one function
    that turns a detected/confirmed candidate into the exact text the
    back-fill lane persists, so a caller never hand-assembles the delimiter
    grammar itself.

    Emits a `latest-eligible` line when `row` declares one (HIGH-2,
    adversarial review 2026-07-31) — `detect_candidate_target` always does,
    since it can only ever propose a single-target row — rendered as the
    grammar's own `true`/`false` literal, never a bare Python truthiness
    string, so the round-trip through `parse_release_targets` parses it back
    as the same boolean rather than an `InvalidBooleanError`."""
    lines = ["<!-- release-targets -->", f"[{row['target']}]",
              f"prefix: {row['prefix']}"]
    for manifest in row.get("manifest", []):
        lines.append(f"manifest: {manifest}")
    lines.append(f"changelog: {row['changelog']}")
    lines.append(f"payload: {row['payload']}")
    if "latest_eligible" in row:
        lines.append(f"latest-eligible: {'true' if row['latest_eligible'] else 'false'}")
    lines.append("<!-- /release-targets -->")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI entry point (T-41f, issue #563). Gated behind `if __name__ ==
# "__main__":` at the bottom of this file, so nothing here touches the
# zero-side-effects-at-import invariant every other section of this module
# states — importing this module never parses argv, resolves a path, or
# reads a file; only running it as a script does.
#
# This is the CLI the release skill's helper invocations resolve against
# once repointed under `${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py` (T-41b).
# It is intentionally NOT the same surface as `.github/scripts/_releaselib.py`
# (this repo's permanent CI shim, which additionally carries this repo's own
# data constants and CI-only subcommands like `select-target` and
# `merge-readiness` — those stay CI-internal and are not part of a portable
# skill's vocabulary). This CLI supports only the subcommands a release
# skill actually needs to shell out to: resolving a target's declared
# prefix, selecting the last tag in a series, checking a notes file's
# heading, classifying a (re)publish attempt, and peeling a tag to the
# commit it names (`peel-tag`, HIGH-1, adversarial review 2026-07-31 — added
# here because the CI shim already had it and a consumer had no equivalent).
# --------------------------------------------------------------------------- #


def default_targets_path():
    """The declared-target file's default location: `.codearbiter/release-
    targets.md` under the project root. `CLAUDE_PROJECT_DIR` is read first —
    the same env-first signal every hook in this codebase trusts as the
    harness's own authoritative project-root pointer (a subprocess is not
    guaranteed to start with the project directory as its cwd) — falling
    back to the process's current working directory when the variable is
    unset (a bare script invocation outside a governed session, e.g. this
    module's own tests). Deliberately reimplemented here rather than
    importing `_activationlib.project_root`: this file must stay loadable
    standalone via `importlib.util.spec_from_file_location` with no sibling
    module on `sys.path` (the CI shim, and every test that loads this module
    under a private name, does exactly that), so it cannot depend on another
    `core/pysrc/` file being importable by plain `import` at CLI time."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(root, ".codearbiter", "release-targets.md")


def default_backfill_root():
    """The back-fill scan's default root, mirroring `default_targets_path`'s
    own env-first precedence exactly: `CLAUDE_PROJECT_DIR` when set, else the
    process's current working directory. Without this, `backfill-detect`
    invoked with no positional root (the shape the release skill's own
    prose uses) would scan whatever directory the CALLER happens to be
    running in rather than the project root — the same T-41f defect class
    this module's CLI already guards against for `tag-prefix`."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _resolve_target_row(target, targets_file):
    """The declared row named `target` in `targets_file`, or `None` if no
    row of that name is declared. Raises `ReleaseTargetsError` (any
    subclass) exactly as `load_targets` does when the file itself is
    absent, empty, or malformed — a caller distinguishes "no such target"
    from "the declaration is broken" by catching the exception type."""
    rows = load_targets(targets_file)
    for row in rows:
        if row["target"] == target:
            return row
    return None


def _targets_error_exit_code(exc):
    """The CLI's exit-code discriminator for any `ReleaseTargetsError`
    surfaced from `load_targets` (HIGH-1, adversarial review 2026-07-31):

      3  - a genuinely ABSENT declared file (`AbsentBlockError`, and nothing
           else) -- nothing on disk at all. This is the release skill's
           Back-fill lane's ONE sanctioned trigger.
      4  - every other case: an EXISTING file that has no block
           (`FileExistsNoBlockError`), or is empty, malformed, or otherwise
           unparseable. All of these STOP outright per the skill's "Targets"
           section and must never be mistaken for "safe to back-fill".

    Exit code 2 is deliberately NOT reused for either state here: it already
    means "bad CLI invocation" or "unrecognised target name" elsewhere in
    this dispatcher, neither of which is a statement about the declared
    file's own state -- collapsing them together is exactly how the
    original defect made "absent" and "exists but broken" indistinguishable
    from the CLI."""
    return 3 if isinstance(exc, AbsentBlockError) else 4


def main(argv):
    """CLI dispatch. Subcommands:

      tag-prefix <target> [--targets-file PATH]
                                  prints the target's declared `prefix`.
      list-targets [--targets-file PATH]
                                  prints every declared target's name, one
                                  per line, in declaration order -- the
                                  sanctioned way to enumerate targets without
                                  hand-parsing the file (never guaranteed to
                                  be a single name; a multi-target file names
                                  more than one).
      last-tag <prefix>          stdin = tags (whitespace/newline separated)
                                  -> prints the selected tag or <none>.
      notes-match <tag> <notes_file>
                                  exit 0 iff the notes file's first heading
                                  names the same version as `tag`.
      check-manifests <target> <version>
                                  asserts EVERY declared `manifest` in the row
                                  equals <version>. exit 0 all match - 1 at
                                  least one disagrees (each named) - 2 bad
                                  invocation or a manifest that cannot be
                                  parsed. The lane's only runnable all-paths
                                  equality guard: `classify` short-circuits on
                                  a fresh publish and never reaches its own
                                  version comparison (run 12).
      classify-window            stdin = `git log $WINDOW --pretty=format:
                                  %H%n%s%n%b%n---- -- $PAYLOAD` -> prints the
                                  derived bump, then one
                                  `[NEEDS-TRIAGE] <sha> <subject>` line per
                                  BUMPING commit missing a CHANGELOG: footer.
                                  exit 0 clean - 1 a footer is missing (the
                                  step-3 BLOCK) - 2 the window is non-bumping
                                  (the step-2 STOP). Classifies and reports;
                                  the skill keeps the decision.
      adoption-commit            stdin = `git log --diff-filter=A --format=%H
                                  -- .codearbiter/CONTEXT.md` -> prints the
                                  commit that ADOPTED codeArbiter, or nothing
                                  when there is none. The honest window floor
                                  for a project's FIRST release: without it,
                                  every pre-adoption commit enters the
                                  footer check and none can pass, blocking a
                                  legitimate release once per commit (A-5.5).
      run-pre-tag <target>       runs the row's declared `pre-tag` commands in
                                  DECLARED ORDER, stopping at the first
                                  non-zero exit, and asserts a clean tree after
                                  each (DECISION-0034: check-only, never a
                                  fixer). exit 0 all passed - 5 a command
                                  failed - 6 a command mutated the tree (or the
                                  tree was already dirty) - 2 bad invocation /
                                  unknown target - 3/4 declared-file states.
      semver-greater <candidate> <floor>
                                  exit 0 iff `candidate` is STRICTLY greater
                                  than `floor`; 1 when equal or lesser; 2 when
                                  either is unparseable. The sanctioned way to
                                  run the lane's strictly-greater assertions,
                                  including the manifest FLOOR check -- both
                                  were hand-done against a hard rule saying
                                  the version MUST NOT be guessed.
      dates-match <changelog_section_file> <tag_message_file>
                                  exit 0 iff the changelog section's heading
                                  date equals the `Released-at:` date in the
                                  tag message. The prose has always REQUIRED
                                  this check; until run 4 it had no CLI
                                  entry point, so no operator following the
                                  skill could actually run it.
      classify <tag_exists> <tag_sha> <head_sha> <tag_version>
               <manifest_version> <release_nondraft>
                                  prints the publish-state label. Bools are
                                  the bare literals `true`/`false` -- NOT
                                  `gh`'s JSON. Note `release_nondraft` is
                                  the NEGATION of `gh`'s `isDraft`.
      peel-tag <tag>             stdin = `<sha> <ref>` lines in either
                                  `git ls-remote --tags` or `git show-ref
                                  --tags -d` format -> prints the COMMIT
                                  `tag` names (peeled through its `^{}`
                                  line when annotated), or "" when `tag`
                                  is absent from stdin (HIGH-1, adversarial
                                  review 2026-07-31). This is the one
                                  sanctioned way to produce `<tag_sha>` for
                                  `classify` below: a bare `git rev-parse
                                  <tag>` returns an ANNOTATED tag's own
                                  object id, not the commit it points at,
                                  which would feed `classify` a value that
                                  can never equal `<head_sha>` and
                                  misclassify a healthy tag as
                                  `abort_mismatch`.
      backfill-detect [root]     scans `root` (default: `default_backfill_
                                  root()`, i.e. `CLAUDE_PROJECT_DIR` then
                                  cwd) for exactly one candidate manifest and
                                  one candidate changelog (T-49/T-50); on a
                                  single unambiguous candidate of each,
                                  prints the exact `release-targets.md`
                                  block text and exits 0; on zero or multiple
                                  of either, writes the ambiguity to stderr
                                  and exits 1 — it never prints a guess.

    `--targets-file PATH` overrides `default_targets_path()` for `tag-prefix`
    and `list-targets` only; every other subcommand needs no declared file
    at all. `tag-prefix` and `list-targets` exit 3 when the declared file is
    genuinely absent and 4 for every other declared-file error (HIGH-1,
    `_targets_error_exit_code`); every other subcommand prints a value/label
    and exits 0, or writes a short cause to stderr and exits non-zero —
    never a bare traceback, so a caller shelling out to this file gets a
    diagnosable failure either way. Returns a process exit code."""
    if not argv:
        sys.stderr.write(
            "usage: _releaselib.py {tag-prefix|list-targets|show-row|"
            "payload-pathspec|last-tag|notes-match|dates-match|"
            "semver-greater|classify|peel-tag|run-pre-tag|adoption-commit|"
            "classify-window|check-manifests|backfill-detect} ...\n")
        return 2

    cmd, rest = argv[0], list(argv[1:])

    if cmd == "tag-prefix":
        # `--targets-file` is stripped HERE, inside the one subcommand that
        # reads it, rather than unconditionally over every subcommand's
        # `rest` — `classify`'s six positional arguments are caller-supplied
        # data (a sha, a version string, a bool) and must never have a
        # literal substring lexically special-cased out from under them.
        targets_file = default_targets_path()
        if "--targets-file" in rest:
            idx = rest.index("--targets-file")
            if idx + 1 >= len(rest):
                sys.stderr.write("--targets-file requires a value\n")
                return 2
            targets_file = rest[idx + 1]
            rest = rest[:idx] + rest[idx + 2:]
        if len(rest) != 1:
            sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
            return 2
        target = rest[0]
        try:
            row = _resolve_target_row(target, targets_file)
        except ReleaseTargetsError as exc:
            sys.stderr.write(
                f"{type(exc).__name__}: could not read declared release "
                f"targets from {targets_file!r}: {exc}\n")
            return _targets_error_exit_code(exc)
        if row is None:
            sys.stderr.write(f"unknown release target: {target}\n")
            return 2
        print(row["prefix"])
        return 0

    if cmd in ("show-row", "payload-pathspec"):
        # Blind-exercise HIGH (run 14). The lane's own rule is that the
        # declared file must be read "through the same tested grammar", not
        # "by-eye scan of the delimiter block" -- but only `prefix` and the
        # target names had readers. Nine fields (`manifest`,
        # `generated-manifest`, `generate`, `changelog`, `payload`,
        # `payload-exclude`, `artifacts`, `pre-tag`, `provenance-manifest`,
        # `latest-eligible`) had none, so following the lane REQUIRED doing
        # the thing it forbids. An exercising agent read all nine by eye and
        # said so.
        #
        # `payload-pathspec` exists separately because `$PAYLOAD` is
        # documented as "payload, minus payload-exclude" and plain
        # `git log -- <path>` cannot express subtraction. The exclusion was
        # therefore unspellable from the prose, and silently absent from any
        # window for a row that declares one. This prints the pathspec
        # arguments to pass verbatim, `:(exclude)` forms included.
        field = None
        if "--field" in rest:
            idx = rest.index("--field")
            if idx + 1 >= len(rest):
                sys.stderr.write("--field requires a value\n")
                return 2
            field = rest[idx + 1]
            rest = rest[:idx] + rest[idx + 2:]
        if len(rest) != 1:
            sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
            return 2
        target = rest[0]
        targets_file = default_targets_path()
        try:
            row = _resolve_target_row(target, targets_file)
        except ReleaseTargetsError as exc:
            sys.stderr.write(
                f"{type(exc).__name__}: could not read declared release "
                f"targets from {targets_file!r}: {exc}\n")
            return _targets_error_exit_code(exc)
        if row is None:
            sys.stderr.write(f"unknown release target: {target}\n")
            return 2

        if cmd == "payload-pathspec":
            payload = row.get("payload") or "."
            parts = [payload] + [f":(exclude){p}"
                                 for p in (row.get("payload_exclude") or [])]
            print(" ".join(parts))
            return 0

        # Emitted as SHELL-QUOTED `NAME='value'` pairs, and named for the
        # variables the release skill actually spells (`TAG_PREFIX`, not
        # `PREFIX`). Both halves are load-bearing, and blind exercise run 15
        # found the cost of getting either wrong:
        #
        #   * UNQUOTED output made the documented `eval "$(… show-row …)"`
        #     EXECUTE declared field values. `rebuild: cd x && npm run build`
        #     parsed as the assignment `REBUILD=cd` followed by the command
        #     `x`, with `&& npm run build` next in line -- it was one
        #     successful exit away from running a build nobody asked for, and
        #     `eval` still reported 0 because plain assignments followed. A
        #     declared file's values are operator-authored shell that this
        #     lane executes only AFTER `releasehash` confirms a human read
        #     them; executing a fragment of that at row-read time runs it
        #     BEFORE the gate that exists for it. `shlex.quote` closes it.
        #   * MISNAMED keys silently left `TAG_PREFIX`, `REBUILD` and
        #     `PRE_TAG` unset after the eval -- the three the lane leans on
        #     hardest -- so the mandated reader delivered 10 of 13 fields and
        #     the operator had to read the rest by eye, which is the exact
        #     thing this subcommand was added to prevent.
        #
        # `--field NAME` prints ONE raw value with no quoting and no `NAME=`,
        # for `X=$(… --field payload)` command substitution. That form needs
        # no `eval` at all and is what the skill now uses.
        fields = [("TARGET", "target"), ("TAG_PREFIX", "prefix"),
                  ("MANIFEST", "manifest"),
                  ("GENERATED_MANIFEST", "generated_manifest"),
                  ("GENERATE", "generate"), ("CHANGELOG", "changelog"),
                  ("PAYLOAD", "payload"),
                  ("PAYLOAD_EXCLUDE", "payload_exclude"),
                  ("ARTIFACTS", "artifacts"), ("REBUILD", "rebuild"),
                  ("PRE_TAG", "pre_tag"),
                  ("PROVENANCE_MANIFEST", "provenance_manifest"),
                  ("LATEST_ELIGIBLE", "latest_eligible"),
                  ("DISPLAY_NAME", "display_name")]

        def _flatten(value):
            if isinstance(value, (list, tuple)):
                return ",".join(str(v) for v in value)
            if isinstance(value, bool):
                return "true" if value else "false"
            return "" if value is None else str(value)

        if field is not None:
            wanted = field.strip().lower().replace("-", "_")
            by_key = {key: name for name, key in fields}
            if wanted not in by_key:
                sys.stderr.write(
                    f"unknown field {field!r}; declared fields are: "
                    + ", ".join(key for _n, key in fields) + "\n")
                return 2
            print(_flatten(row.get(wanted)))
            return 0

        for name, key in fields:
            print(f"{name}={shlex.quote(_flatten(row.get(key)))}")
        return 0

    if cmd == "list-targets":
        # MEDIUM (adversarial review 2026-07-31): the single-target rule
        # requires knowing a target's name, but `tag-prefix` takes the name
        # as INPUT and, before this subcommand existed, nothing enumerated
        # the declared names -- an agent had no sanctioned way to answer
        # "what targets exist?" except hand-parsing the file, exactly the
        # grammar this module exists to be the one tested parser for.
        targets_file = default_targets_path()
        if "--targets-file" in rest:
            idx = rest.index("--targets-file")
            if idx + 1 >= len(rest):
                sys.stderr.write("--targets-file requires a value\n")
                return 2
            targets_file = rest[idx + 1]
            rest = rest[:idx] + rest[idx + 2:]
        if rest:
            sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
            return 2
        try:
            rows = load_targets(targets_file)
        except ReleaseTargetsError as exc:
            sys.stderr.write(
                f"{type(exc).__name__}: could not read declared release "
                f"targets from {targets_file!r}: {exc}\n")
            return _targets_error_exit_code(exc)
        for row in rows:
            print(row["target"])
        return 0

    if cmd == "last-tag" and len(rest) == 1:
        print(last_tag_select(sys.stdin.read().split(), rest[0]))
        return 0

    if cmd == "notes-match" and len(rest) == 2:
        try:
            with open(rest[1], encoding="utf-8") as fh:
                notes_text = fh.read()
        except OSError:
            notes_text = ""
        return 0 if notes_heading_matches(notes_text, rest[0]) else 1

    if cmd == "check-manifests" and len(rest) == 2:
        # HIGH (adversarial review 2026-07-31, run 12). A row MAY declare
        # several manifests, and Phase 1 must bump every one to the derived
        # version -- but nothing mechanical asserted it. The skill claimed
        # `classify` would catch a partial bump; it does not on the path
        # that matters. `classify_publish_state` short-circuits on
        # `if not tag_exists: return "publish_fresh"` BEFORE comparing
        # versions, so the catch fires only when a tag already exists (the
        # resume path). On a FRESH publish -- every ordinary release, and
        # every first release -- a lagging secondary manifest sails
        # through, and the Traps section's own named consequence lands: a
        # tag that installs a version string the tag does not name.
        #
        # Exit 0 every declared manifest equals <version> - 1 at least one
        # disagrees (each named) - 2 bad invocation, unknown target, or a
        # manifest that cannot be read or parsed. Unparseable is NEVER
        # folded into "disagrees": one is "I compared and they differ", the
        # other is "I could not compare", and this lane has already had to
        # separate those twice.
        target, expected = rest
        try:
            rows = load_targets(default_targets_path())
        except ReleaseTargetsError as exc:
            sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            return _targets_error_exit_code(exc)
        row = next((r for r in rows if r["target"] == target), None)
        if row is None:
            sys.stderr.write(f"unknown release target: {target}\n")
            return 2
        root = os.path.dirname(os.path.dirname(default_targets_path())) or "."
        mismatched, unreadable = [], []
        for rel in (row.get("manifest") or []):
            path = os.path.join(root, *rel.split("/"))
            found = _manifest_version(path)
            if found is None:
                unreadable.append(rel)
            elif found != expected:
                mismatched.append((rel, found))
        for rel in unreadable:
            sys.stderr.write(
                f"check-manifests: cannot read a version from {rel!r} -- this "
                "is NOT the same answer as 'disagrees' (exit 1); no "
                "comparison happened\n")
        for rel, found in mismatched:
            sys.stderr.write(
                f"check-manifests: {rel} declares {found!r}, expected "
                f"{expected!r}\n")
        if unreadable:
            return 2
        return 1 if mismatched else 0

    if cmd == "classify-window" and not rest:
        # stdin = `git log $WINDOW --pretty=format:%H%n%s%n%b%n---- --
        # $PAYLOAD`. Prints the derived bump on the first line, then one
        # `[NEEDS-TRIAGE] <short-sha> <subject>` line per BUMPING commit
        # with no CHANGELOG: footer -- the exact report shape Phase 1
        # step 3 specifies, so it is not re-derived per release.
        #
        # Exit 0 = classified, no missing footers. Exit 1 = at least one
        # bumping commit lacks a footer (the step-3 BLOCK). Exit 2 = the
        # window is non-bumping, which is the step-2 STOP.
        #
        # It CLASSIFIES and REPORTS; it does not decide the release. The
        # skill keeps the BLOCK. A helper returning proceed/stop would put
        # a governance decision inside a library, which is the wrong side
        # of ADR-0010's cooperative-agent line.
        window = classify_window(parse_window_log(sys.stdin.read()))
        print(window["bump"])
        for row in window["missing_footer"]:
            print(f"[NEEDS-TRIAGE] {row['sha'][:7]} {row['subject']}")
        if window["missing_footer"]:
            return 1
        return 2 if window["bump"] == "none" else 0

    if cmd == "adoption-commit" and not rest:
        # A-5.5. stdin = `git log --diff-filter=A --format=%H --
        # .codearbiter/CONTEXT.md`. Prints the adoption commit, or nothing
        # at all when the project has no adoption commit.
        #
        # Exit 0 either way, deliberately: "this project has no adoption
        # commit" is a normal answer for a repo that never onboarded, not
        # an error, and the caller distinguishes the two by empty output
        # exactly as it already does for `peel-tag`. A non-zero exit here
        # would break a `set -e` lane on the ordinary path.
        baseline = first_release_baseline(sys.stdin.read())
        if baseline:
            print(baseline)
        return 0

    if cmd == "run-pre-tag" and len(rest) == 1:
        # A-2.1/2.2/2.3 (DECISION-0034). Runs the row's declared `pre-tag`
        # commands IN DECLARED ORDER, stops at the first non-zero exit, and
        # asserts a clean tree after each one.
        #
        # This is a subcommand rather than four prose rules because
        # operator-declared shell commands are exactly where an
        # agent-followed procedure is least trustworthy: the clean-tree
        # assertion is what surfaces a rogue command's writes before
        # tagging, and an assertion an agent has to remember is one it can
        # skip. Logged as a SMARTS decision in .codearbiter/sprint-log.md
        # (2026-07-31), Scalable weighted heavily per the standing steer.
        #
        # The clean-tree check runs BEFORE any `rebuild` (2.3): this
        # subcommand never invokes rebuild at all, so a rebuild's
        # legitimate bundle rewrite can never be attributed to a pre-tag
        # command. Ordering the lane correctly is the caller's job; making
        # it impossible to conflate the two is this command's.
        #
        # Exit codes: 0 all passed - 5 a command exited non-zero - 6 a
        # command left the tree dirty - 2 bad invocation or unknown target
        # - 3/4 the declared-file states, unchanged.
        try:
            rows = load_targets(default_targets_path())
        except ReleaseTargetsError as exc:
            sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            return _targets_error_exit_code(exc)
        row = next((r for r in rows if r["target"] == rest[0]), None)
        if row is None:
            sys.stderr.write(f"unknown release target: {rest[0]}\n")
            return 2

        # Run the declared commands in the PROJECT root, not whatever cwd
        # this process inherited (MEDIUM, run 9). The declaration is
        # resolved from CLAUDE_PROJECT_DIR while the commands and the tree
        # probe used to run wherever the caller happened to be -- so a
        # declared check could pass having inspected a DIFFERENT
        # repository's files, and the clean-tree probe could report an
        # unrelated repo's dirt. Both directions were demonstrated.
        project_root = os.path.dirname(os.path.dirname(default_targets_path())) or "."

        def _tree_state():
            """(paths -> content digest, failure). Content, not just the
            porcelain LINE (HIGH, adversarial review run 10).

            A porcelain-line set alone cannot see a command that mutates a
            file which was ALREADY modified: the line is byte-identical
            (` M CHANGELOG.md` before and after), so the change falls out
            of the set difference and the command exits 0. That blind spot
            covered exactly `$CHANGELOG` and `$MANIFEST` -- the two files
            Phase 1 touches immediately before this step, and the two an
            injected line would actually damage, since both ship: one into
            the tag message and the Release notes, the other as the
            version the tag claims. Demonstrated with a changed sha256 and
            an `INJECTED` line surviving to exit 0.

            Digesting every path git reports as changed closes it. Paths
            git lists but that do not exist (a deletion, or a rename's old
            side) get a sentinel rather than being skipped, so a delete is
            a state change like any other.
            """
            # `git_executable()`, not a bare "git": Pi-reachable modules
            # must resolve git through the trusted-path seam, because a
            # host that has no `git` on PATH (or a PATH an attacker can
            # prepend to) would otherwise silently run the wrong binary or
            # none at all. Enforced by test_pi_package's
            # `test_shared_python_contains_no_direct_bare_git_subprocess`.
            probe = subprocess.run(
                [git_executable(), "status", "--porcelain"],
                capture_output=True, text=True, cwd=project_root)
            if probe.returncode != 0:
                return None, (probe.stderr.strip() or "git status failed")
            state = {}
            for line in probe.stdout.splitlines():
                # Porcelain v1: XY then a space then the path. A rename
                # carries `old -> new`; take the destination, which is the
                # path that exists on disk.
                rel = line[3:].strip().strip('"')
                if " -> " in rel:
                    rel = rel.split(" -> ", 1)[1].strip().strip('"')
                if not rel:
                    continue
                absolute = os.path.join(project_root, *rel.split("/"))
                try:
                    with open(absolute, "rb") as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()
                except OSError:
                    digest = "<absent-or-unreadable>"
                state[rel] = digest
            return state, None

        # The assertion is "this command changed NOTHING NEW", not "the
        # tree is pristine" (HIGH, run 9). The first form is what this
        # command is for; the second form BLOCKS EVERY RELEASE, because
        # Phase 1 rolls the changelog and bumps the manifest BEFORE this
        # step runs -- and it must, since a badge or catalog check compares
        # a surface against the NEW version and would pass vacuously
        # against the old one. Requiring a pristine tree here made the lane
        # exit 6 even for a row declaring no commands at all.
        #
        # Snapshotting instead keeps the property that matters: any path a
        # declared command touches appears as a NEW entry and is reported,
        # while the operator's own in-flight release edits are carried
        # through untouched.
        baseline, failure = _tree_state()
        if failure is not None:
            sys.stderr.write(f"run-pre-tag: cannot read the tree state: {failure}\n")
            return 6

        for command in (row.get("pre_tag") or []):
            # flush=True: the subprocess writes to the same fds directly and
            # is not buffered, so without this the label lands AFTER the
            # output it labels and the log misattributes which command
            # produced what -- actively misleading in the one report an
            # operator reads to decide whether a release is safe.
            print(f"pre-tag: {command}", flush=True)
            proc = subprocess.run(command, shell=True, cwd=project_root)
            if proc.returncode != 0:
                sys.stderr.write(
                    f"run-pre-tag: BLOCK -- {command!r} exited "
                    f"{proc.returncode}.\n"
                    "  A pre-tag command is a check, never a fixer "
                    "(DECISION-0034), so reconcile the drift it reports.\n"
                    "  Then DISCARD this run's uncommitted release edits "
                    "(the manifest bump and the composed changelog section) "
                    "before starting over: leaving the bump in place makes "
                    "it the NEXT run's version floor, so the restart derives "
                    "a HIGHER version and strands the section this run "
                    "already wrote for a version that was never tagged "
                    "(HIGH, adversarial review run 9). Commit the "
                    "reconciliation alone, then re-run the release from "
                    "Pre-flight.\n")
                return 5
            current, failure = _tree_state()
            if failure is not None:
                sys.stderr.write(f"run-pre-tag: cannot read the tree state: {failure}\n")
                return 6
            # The UNION of both key sets, not `current` alone. A path git
            # reported as changed at baseline and no longer reports has been
            # REVERTED by the command -- which is a mutation of the tree in
            # exactly the sense this gate exists to catch, and the most
            # dangerous one: a pre-tag command that quietly undoes the
            # lane's own manifest bump or changelog section leaves a release
            # that tags a version the payload never claims. Walking
            # `current.items()` could not see it, because a reverted path
            # simply stops appearing.
            changed = sorted(
                rel for rel in set(baseline) | set(current)
                if baseline.get(rel) != current.get(rel))
            if changed:
                sys.stderr.write(
                    f"run-pre-tag: BLOCK -- {command!r} exited 0 but MUTATED "
                    "the tree. Declared pre-tag commands are check-only "
                    "(DECISION-0034); reconciliation is a separate action "
                    "the operator commits before releasing.\n"
                    "  Changed by this command (added, edited, or reverted):"
                    "\n    "
                    + "\n    ".join(changed) + "\n"
                    "  FIX THE DECLARATION -- do not simply re-run. This "
                    "command mutates the tree every time it is invoked, so "
                    "reverting and re-running cannot converge; make it "
                    "check-only (assert and exit non-zero on drift) or "
                    "remove the row entry. Only then restart the release "
                    "from Pre-flight.\n"
                    "  This run's edits can be discarded wholesale, because "
                    "nothing has been committed or tagged yet: `git "
                    "checkout -- <tracked paths>` for files that existed "
                    "before, and `rm` for any the lane CREATED (a first "
                    "release composes $CHANGELOG from nothing, and `git "
                    "checkout --` errors on a path git has never seen).\n")
                return 6
        return 0

    if cmd == "semver-greater" and len(rest) == 2:
        # MEDIUM (adversarial review 2026-07-31, run 6): the hard rules say
        # "MUST NOT guess the version", and every other mechanical step in
        # the lane got a tested helper -- but the bump arithmetic and the
        # strictly-greater assertion were both hand-done, because
        # `semver_greater` was public API reachable only by import. This
        # is also the mechanism the manifest-floor check needs (HIGH, run
        # 6: a never-tagged project whose manifest already reads 1.4.2 was
        # released as 0.1.0, walking its own version backward, because the
        # only greater-than check compared against a `<none>` sentinel).
        # Exit 0 iff `candidate` is STRICTLY greater than `floor`; 1
        # otherwise -- including equal, which is the case that matters.
        # Parseability is checked SEPARATELY and reported as exit 2, never
        # folded into the exit-1 "not greater" answer. `semver_greater` is
        # non-raising by this module's mechanism-function invariant, so an
        # unparseable version returns False -- which is fail-CLOSED for the
        # floor check (a garbage version cannot clear the floor) but is
        # indistinguishable from a genuine "not greater". Conflating "I
        # compared them and the answer is no" with "I could not compare
        # them" is the exact defect class this lane's exit-3-vs-4 work
        # already fixed once; it is not reintroduced here.
        for value in rest:
            if semver_key(value) is None:
                sys.stderr.write(
                    f"semver-greater: not valid SemVer: {value!r} -- this is "
                    "NOT the same answer as 'not greater' (exit 1); the "
                    "comparison did not happen\n")
                return 2
        return 0 if semver_greater(rest[0], rest[1]) else 1

    if cmd == "dates-match" and len(rest) == 2:
        # MEDIUM (adversarial review 2026-07-31, run 4): Phase 1 step 5 and
        # Phase 2 step 1 both name `release_dates_consistent`, and Phase 2
        # says it "must pass" -- but this CLI exposed no way to run it, so
        # an operator following the prose could not perform a check the
        # prose demanded. The exercising agent could only reach it by
        # importing the module, which the skill never tells anyone to do.
        # Same read-and-compare shape as `notes-match` above, including its
        # unreadable-file-is-empty-text behaviour (an unreadable file has
        # no date, so the comparison is False, so the exit code is 1 --
        # never a traceback).
        texts = []
        for path in rest:
            try:
                with open(path, encoding="utf-8") as fh:
                    texts.append(fh.read())
            except OSError:
                texts.append("")
        return 0 if release_dates_consistent(texts[0], texts[1]) else 1

    if cmd == "classify" and len(rest) == 6:
        as_bool = lambda s: str(s).lower() == "true"
        print(classify_publish_state(
            tag_exists=as_bool(rest[0]), tag_sha=rest[1], head_sha=rest[2],
            tag_version=rest[3], manifest_version=rest[4],
            release_is_nondraft=as_bool(rest[5])))
        return 0

    if cmd == "peel-tag" and len(rest) == 1:
        # HIGH-1 (adversarial review 2026-07-31): this subcommand did not
        # exist in this module's own CLI before this fix, even though
        # `peel_tag` was already public API and `.github/scripts/
        # _releaselib.py` (this repo's OWN, non-portable CI shim) already
        # exposed it. A consumer shelling out to the VENDORED copy of THIS
        # file had no sanctioned way to peel an annotated tag to its commit
        # at all, which left `git rev-parse <tag>` as the only thing a
        # reader would reach for -- exactly the value that misclassifies a
        # healthy tag (see the docstring above and the release skill's
        # Phase 2 step 1).
        print(peel_tag(sys.stdin.read(), rest[0]))
        return 0

    if cmd == "backfill-detect" and len(rest) <= 1:
        root = rest[0] if rest else default_backfill_root()
        manifests, changelogs = scan_backfill_candidates(root)
        try:
            row = detect_candidate_target(manifests, changelogs)
        except BackfillAmbiguousError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        sys.stdout.write(format_release_targets_block(row))
        return 0

    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
