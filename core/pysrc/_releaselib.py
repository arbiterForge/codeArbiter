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
#   git_executable() -> str    git resolved through the trusted-path seam
#   semver_key(value) -> tuple | None
#   semver_greater(current, base) -> bool
#   apply_bump(base, word) -> str | None
#   last_tag_select(tags, prefix) -> str
#   numeric_sequence_key(value, initial_version) -> tuple | None
#   version_greater(current, base, policy, initial_version) -> bool
#   derive_version(base, word, policy, initial_version) -> str | None
#   last_tag_select_for_policy(tags, prefix, policy, initial_version) -> str
#   notes_heading_matches(notes_text, tag, policy, initial_version) -> bool
#   release_dates_consistent(changelog_section, tag_message, policy,
#                            initial_version) -> bool
#   changelog_section(changelog_text, version, policy, initial_version)
#                           -> str | None
#   render_release_assets(templates, version, tag) -> list[str] | None
#   verify_release_asset_inventory(directory, asset_names)
#                           -> list[str] | None
#   classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
#                          manifest_version, release_is_nondraft) -> str
#   select_release_target_by_name(pairs, targets) -> str   name-keyed
#                           resolver (A-4.2); pairs are `name=value` strings
#   select_release_target(*confirmations, targets) -> str
#   classify_merge_readiness(check_runs, head_sha, check_name) -> str
#   row_assertions(row) -> dict   which lane steps a row's declared fields
#                           turn on (A-3.1..3.5)
#   window_excludes_payload_paths(paths, payload, payload_exclude)
#                           -> list[str]   paths filtered to payload, minus
#                           any payload-exclude entry (A-3.4)
#   provenance_trigger_paths(rows) -> list[str]   every manifest/changelog/
#                           generated_manifest/artifacts/reconciliation path a
#                           declared row references, sorted and de-duplicated
#                           (A-5.6)
#   _manifest_version(path) -> str | None
#   classify_commit(subject, body) -> dict
#   classify_window(commits, reconciliations=None, published_shas=None) -> dict
#   parse_changelog_reconciliations(text, target) -> dict[str, str]
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
#   ValueTooLongError       — a declared value exceeds VALUE_MAX_CHARS
#                             (A-2.4); a sibling declared-file error, exits 4
#   ChangelogReconciliationError — a declared reconciliation ledger is
#                             missing, unreadable, unsafe, or malformed
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
#   UnreadableTargetsFileError — the declared path EXISTS but `open()` still
#                             failed for a reason other than "not found"
#                             (permission denied, a directory, ...). A
#                             SIBLING of AbsentBlockError, not a subclass,
#                             for the same reason FileExistsNoBlockError is:
#                             "unreadable" is not "absent"
#                             ([[never-fold-unreadable-into-absent]]) and
#                             must not silently trigger the Back-fill lane's
#                             `except AbsentBlockError:` on a file that is
#                             actually there but denied to this process.

from __future__ import annotations

import hashlib
import datetime
import json
import os
import stat
import posixpath
import re
import shlex
import shutil
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


class UnreadableTargetsFileError(ReleaseTargetsError):
    """`open()` on the declared path failed for a reason OTHER than "not
    found" -- a permissions error, the path naming a directory, or any other
    `OSError` whose `errno` is not `ENOENT`. The path exists (in the
    filesystem sense) but this process could not read it.

    Deliberately a SIBLING of `AbsentBlockError`, not a subclass of it, for
    the identical reason `FileExistsNoBlockError` is one:
    [[never-fold-unreadable-into-absent]] -- "could not read" is a different
    fact than "is not there", and folding the two together means a
    permissions error on an EXISTING declared-targets file would silently
    satisfy the Back-fill lane's `except AbsentBlockError:` trigger, driving
    it to write a fresh file over one that was never actually missing, only
    denied. Only `load_targets` ever raises this -- `parse_release_targets`
    is pure over text and never touches the filesystem."""


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


class ChangelogReconciliationError(ReleaseTargetsError):
    """A declared changelog-reconciliation ledger is malformed.

    Reconciliations are release policy, not best-effort input.  A malformed
    record must therefore fail closed like the release-target declaration
    that points at it.
    """


class DelimiterInValueError(ReleaseTargetsError):
    """A declared value contains the literal closing-delimiter text, which
    would otherwise silently truncate the block under a naive non-greedy
    match rather than being treated as part of the value."""


class MissingRequiredKeyError(ReleaseTargetsError):
    """A target block is missing one of the required keys (prefix, changelog,
    payload)."""


# A `2.9.1`-style series tag is exactly `<prefix>MAJOR.MINOR.PATCH` — no
# suffix. The anchored form excludes pre-releases (`2.6.0-beta.1`) outright:
# the trailing `$` rejects any tag carrying a suffix past MAJOR.MINOR.PATCH,
# so a pre-release tag never matches this regex at all.
#
# Issue #568: this module used to also carry `_PRERELEASE_MARKERS = ("-beta",
# "-rc", "-alpha")` and a second check in `last_tag_select` re-testing the
# prefix-stripped version against it, documented as a "second line of
# defense". That check was proven UNREACHABLE through the public API as
# shipped — the anchor above already rejects every tag the marker check
# could have caught, so no tag can both match the regex and carry a marker,
# and mutating the tuple to `()` changed nothing observable. Deleted rather
# than kept as unreachable dead code or made load-bearing by relaxing the
# anchor: relaxing the anchor to admit a suffix would also newly admit
# tags like `v1.0.0+build.5` and `v1.0.0.1` that this anchor currently
# rejects wholesale, a behavior change with its own blast radius this
# bug-fix cluster does not take on. If the anchor is ever relaxed, a second
# check will need to be RE-ADDED deliberately, not un-deleted from history.
_RELEASE_RE_CACHE = {}
_SEMVER_NUMERIC_IDENTIFIER = r"(?:0|[1-9][0-9]*)"
_PLAIN_SEMVER_PATTERN = (
    _SEMVER_NUMERIC_IDENTIFIER + r"\." +
    _SEMVER_NUMERIC_IDENTIFIER + r"\." +
    _SEMVER_NUMERIC_IDENTIFIER)
_PLAIN_SEMVER_CAPTURE_PATTERN = (
    r"(" + _SEMVER_NUMERIC_IDENTIFIER + r")\." +
    r"(" + _SEMVER_NUMERIC_IDENTIFIER + r")\." +
    r"(" + _SEMVER_NUMERIC_IDENTIFIER + r")")

_RELEASE_ASSET_TEMPLATE_RE = re.compile(
    r"^(?:[A-Za-z0-9._+-]|\{version\}|\{tag\})+$")
_RELEASE_ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_WINDOWS_RESERVED_ASSET_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)})


def _safe_release_asset_name(value):
    """True only for one flat, shell-inert release filename."""
    if (not isinstance(value, str)
            or _RELEASE_ASSET_NAME_RE.fullmatch(value) is None
            or value.endswith(".")):
        return False
    basename = value.split(".", 1)[0].casefold()
    return basename not in _WINDOWS_RESERVED_ASSET_BASENAMES


def render_release_assets(templates, version, tag):
    """Render a declared asset-template sequence, or refuse with ``None``.

    The grammar is intentionally smaller than ``str.format``: only the two
    exact placeholders are recognized, all literal characters are from the
    flat filename allowlist, and the rendered names must remain unique.
    """
    if (not isinstance(templates, (list, tuple)) or not templates
            or not isinstance(version, str) or not isinstance(tag, str)):
        return None
    rendered = []
    seen = set()
    for template in templates:
        if (not isinstance(template, str)
                or _RELEASE_ASSET_TEMPLATE_RE.fullmatch(template) is None):
            return None
        name = template.replace("{version}", version).replace("{tag}", tag)
        identity = name.casefold()
        if not _safe_release_asset_name(name) or identity in seen:
            return None
        seen.add(identity)
        rendered.append(name)
    return rendered


def verify_release_asset_inventory(directory, asset_names):
    """Return declared-order absolute paths iff ``directory`` is exact.

    The directory itself may not be a symlink. Every entry must be one of the
    declared safe names and a non-symlink, non-empty regular file; missing or
    additional entries fail closed with ``None``.
    """
    if (not isinstance(directory, (str, os.PathLike))
            or not isinstance(asset_names, (list, tuple)) or not asset_names):
        return None
    names = list(asset_names)
    identities = [name.casefold() for name in names
                  if isinstance(name, str)]
    if (any(not _safe_release_asset_name(name) for name in names)
            or len(identities) != len(names)
            or len(set(identities)) != len(identities)):
        return None
    root = os.path.abspath(os.fspath(directory))
    try:
        if os.path.islink(root) or not os.path.isdir(root):
            return None
        entries = list(os.scandir(root))
    except OSError:
        return None
    entry_names = [entry.name for entry in entries]
    entry_identities = [name.casefold() for name in entry_names]
    if (len(set(entry_identities)) != len(entry_identities)
            or set(entry_identities) != set(identities)
            or set(entry_names) != set(names)):
        return None
    by_name = {entry.name: entry for entry in entries}
    try:
        for name in names:
            entry = by_name[name]
            if (entry.is_symlink()
                    or not entry.is_file(follow_symlinks=False)
                    or entry.stat(follow_symlinks=False).st_size <= 0):
                return None
    except OSError:
        return None
    return [os.path.join(root, name) for name in names]


def _release_re(prefix):
    """The anchored `<prefix>MAJOR.MINOR.PATCH` matcher for one release series."""
    rx = _RELEASE_RE_CACHE.get(prefix)
    if rx is None:
        rx = re.compile(
            r"^" + re.escape(prefix) + _PLAIN_SEMVER_CAPTURE_PATTERN + r"$")
        _RELEASE_RE_CACHE[prefix] = rx
    return rx


# H2 is the structural section boundary. A release heading is the narrower,
# exact grammar: either `## [X.Y.Z] ...`, `## vX.Y.Z ...`, or the one special
# `## [Unreleased]` marker. Tabs/spaces are admitted within ONE line; `\s` is
# deliberately absent because it also consumes newlines and used to turn
# `##\n[1.2.3]` into a release heading. The suffix, when present, must begin
# with horizontal whitespace, so `[1.2.3]garbage` cannot prefix-match.
_H2_RE = re.compile(r"^##(?:[ \t]+[^\r\n]*)?[ \t]*$", re.MULTILINE)
_HEADING_RE = re.compile(
    r"^##[ \t]+(?:\[(Unreleased|" + _PLAIN_SEMVER_PATTERN + r")\]|"
    r"v(" + _PLAIN_SEMVER_PATTERN + r"))(?:[ \t]+[^\r\n]*)?[ \t]*$",
    re.MULTILINE)
_DECLARED_HEADING_RE = re.compile(
    r"^##[ \t]+(?:\[(Unreleased|([^\]\r\n]+))\]|v([^ \t\r\n]+))"
    r"(?:[ \t]+[^\r\n]*)?[ \t]*$",
    re.MULTILINE)
_LEGACY_DATE_H2_RE = re.compile(
    r"^##[ \t]+\[[0-9]{4}-[0-9]{2}-[0-9]{2}\]"
    r"(?:[ \t]+[^\r\n]*)?[ \t]*$")
_CHANGELOG_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ \t]*$")
_RELEASED_AT_RE = re.compile(
    r"^Released-at:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*$", re.MULTILINE)
_BARE_RELEASE_VERSION_RE = re.compile(r"^" + _PLAIN_SEMVER_PATTERN + r"$")

_SECTION_OK = "ok"
_SECTION_ABSENT = "absent"
_SECTION_INVALID = "invalid"
_SECTION_DUPLICATE = "duplicate"


def _version_matches_policy(value, policy="semver", initial_version=None):
    """True when `value` has the exact shape declared by `policy`."""
    if policy == "semver" and initial_version is None:
        return (isinstance(value, str)
                and _BARE_RELEASE_VERSION_RE.fullmatch(value) is not None)
    if policy == "numeric-sequence":
        return numeric_sequence_key(value, initial_version) is not None
    return False


def _policy_declaration_valid(policy="semver", initial_version=None):
    """True for one complete, supported version-policy declaration."""
    if policy == "semver":
        return initial_version is None
    return (policy == "numeric-sequence"
            and numeric_sequence_key(
                initial_version, initial_version) is not None)


def _heading_version(line, policy="semver", initial_version=None):
    """Bare version / `Unreleased` for one exact heading line, else None."""
    if policy == "semver" and initial_version is None:
        match = _HEADING_RE.fullmatch(line)
        if match is None:
            return None
        return match.group(1) or match.group(2)

    match = _DECLARED_HEADING_RE.fullmatch(line)
    if match is None:
        return None
    if match.group(1) == "Unreleased":
        return "Unreleased"
    version = match.group(2) or match.group(3)
    return version if _version_matches_policy(
        version, policy, initial_version) else None


def _looks_like_changelog_heading(line):
    """True when an H2 claims changelog-heading syntax but is malformed."""
    # This repository's pre-SemVer history used exact bracketed ISO dates,
    # sometimes more than once for one day. They remain ordinary structural
    # H2 boundaries, not release versions and not malformed SemVer claims.
    if _LEGACY_DATE_H2_RE.fullmatch(line) is not None:
        return False
    body = line[2:].lstrip(" \t")
    return body.startswith("[") or body.startswith("v")


def _changelog_section_result(changelog_text, version, policy="semver",
                              initial_version=None):
    """Return `(section, status)` without raising on malformed changelogs."""
    if (not isinstance(changelog_text, str)
            or not isinstance(version, str)
            or not _version_matches_policy(version, policy, initial_version)):
        return None, _SECTION_INVALID

    boundaries = list(_H2_RE.finditer(changelog_text))
    target_indexes = []
    released_seen = False
    unreleased_seen = False

    for index, boundary in enumerate(boundaries):
        line = boundary.group(0)
        heading_version = _heading_version(line, policy, initial_version)
        if heading_version is None:
            if _looks_like_changelog_heading(line):
                return None, _SECTION_INVALID
            continue
        if heading_version == "Unreleased":
            # Repository-derived Keep-a-Changelog compatibility: exactly one
            # Unreleased marker is valid only before every released section.
            if unreleased_seen or released_seen:
                return None, _SECTION_INVALID
            unreleased_seen = True
            continue
        released_seen = True
        if heading_version == version:
            target_indexes.append(index)

    if not target_indexes:
        return None, _SECTION_ABSENT
    if len(target_indexes) != 1:
        return None, _SECTION_DUPLICATE

    index = target_indexes[0]
    start = boundaries[index].start()
    end = (boundaries[index + 1].start()
           if index + 1 < len(boundaries) else len(changelog_text))
    section = changelog_text[start:end].rstrip("\r\n") + "\n"
    return section, _SECTION_OK

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
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
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


def _bare_version(tag, policy="semver", initial_version=None):
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
    if policy != "semver" or initial_version is not None:
        initial = _numeric_sequence_components(initial_version)
        if policy != "numeric-sequence" or initial is None:
            return None
        component = r"(?:0|[1-9][0-9]*)"
        pattern = r"(?<![0-9.])(" + r"\.".join(
            [component] * len(initial)) + r")$"
        match = re.search(pattern, text)
        if match is None:
            return None
        candidate = match.group(1)
        return candidate if numeric_sequence_key(
            candidate, initial_version) is not None else None
    match = re.search(
        r"(?<![0-9])(" + _PLAIN_SEMVER_PATTERN + r".*)$", text)
    return match.group(1) if match else text.lstrip("v")


def last_tag_select(tags, prefix):
    """Return the highest SemVer tag in `tags` for ONE release series,
    excluding pre-releases (`-beta`/`-rc`/`-alpha`) via the anchored
    `_release_re` match alone (issue #568) — no separate marker check.
    Returns NONE_SENTINEL when the series has no release tag yet.

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
        ver = tuple(int(g) for g in m.groups())
        if best is None or ver > best[0]:
            best = (ver, t)
    return best[1] if best else NONE_SENTINEL


NONE_SENTINEL = "<none>"


_NUMERIC_SEQUENCE_COMPONENT_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")


def _numeric_sequence_components(value):
    """Canonical dotted numeric components, or None for malformed input."""
    if not isinstance(value, str):
        return None
    parts = value.split(".")
    if len(parts) < 2 or any(
            _NUMERIC_SEQUENCE_COMPONENT_RE.fullmatch(part) is None
            for part in parts):
        return None
    try:
        return tuple(int(part) for part in parts)
    except (ValueError, TypeError):
        return None


def numeric_sequence_key(value, initial_version):
    """Sortable fixed-shape numeric identity, or None when incompatible.

    `initial_version` declares the component count for the series. Both the
    initial identity and candidate use canonical decimal spelling: no signs,
    empty components, leading zeroes, or non-ASCII digits.
    """
    initial = _numeric_sequence_components(initial_version)
    candidate = _numeric_sequence_components(value)
    if initial is None or candidate is None or len(candidate) != len(initial):
        return None
    return candidate


def version_greater(current, base, policy="semver", initial_version=None):
    """True iff `current` strictly advances `base` under `policy`."""
    if policy == "semver" and initial_version is None:
        return semver_greater(current, base)
    if policy != "numeric-sequence":
        return False
    current_key = numeric_sequence_key(current, initial_version)
    initial_key = numeric_sequence_key(initial_version, initial_version)
    if current_key is None or initial_key is None:
        return False
    if base == NONE_SENTINEL:
        return current_key >= initial_key
    base_key = numeric_sequence_key(base, initial_version)
    if base_key is None:
        return False
    return current_key >= initial_key and current_key > base_key


def last_tag_select_for_policy(tags, prefix, policy="semver", initial_version=None):
    """Highest tag in one series under a declared version policy."""
    if policy == "semver" and initial_version is None:
        return last_tag_select(tags, prefix)
    if (policy != "numeric-sequence" or not isinstance(tags, (list, tuple))
            or not isinstance(prefix, str) or not prefix
            or numeric_sequence_key(initial_version, initial_version) is None):
        return NONE_SENTINEL

    best = None
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        key = numeric_sequence_key(tag[len(prefix):], initial_version)
        if key is None:
            continue
        if best is None or key > best[0]:
            best = (key, tag)
    return best[1] if best else NONE_SENTINEL


_ANCESTRY_ZERO_TAG = "zero-tag"
_ANCESTRY_ANCESTOR = "ancestor"
_ANCESTRY_NOT_ANCESTOR = "not-ancestor"
_ANCESTRY_UNRESOLVABLE = "unresolvable"


def verify_tag_ancestor(tag, project_root, candidate="HEAD"):
    """Classify whether `tag` resolves to a commit reachable from `candidate`
    (issue #570, finding BODY-03).

    `last_tag_select`/`last_tag_select_for_policy` choose a series' highest
    SemVer (or `numeric-sequence`) tag by VALUE alone -- pure functions with
    no git access, per this module's design invariants -- so neither can
    know whether that tag's commit is even in `candidate`'s own commit-graph
    history. A tag pushed once from a sibling branch that diverged from
    `candidate` before the newest tag, an abandoned branch's stray push, or
    an unrelated orphan history that happens to carry a same-prefixed tag
    can still win the highest-SemVer scan even though `candidate` never
    descends from it -- silently anchoring `$BASE_VERSION` (and everything
    derived from it) to history this release does not actually contain.

    Returns one of four labels, never raises:
      `"zero-tag"`     -- `tag` is `NONE_SENTINEL`. There is nothing to
                          verify; the zero-tag first-release path is a
                          DISTINCT code path from tag selection and stays
                          completely unaffected by this check (P5).
      `"ancestor"`     -- `git merge-base --is-ancestor <tag> <candidate>`
                          resolved both revisions and confirmed reachability
                          -- today's behavior for every genuine ancestor,
                          unchanged, including one reached only through a
                          merge commit and both annotated and lightweight
                          tag forms (git peels either transparently).
      `"not-ancestor"` -- both revisions resolved, but `tag` is NOT an
                          ancestor of `candidate` -- the exact gap this
                          function exists to catch (a sibling/decoy/orphan
                          tag that numerically outranks every real release).
      `"unresolvable"` -- `tag` or `candidate` does not resolve to a commit
                          at all, the probe could not run (`OSError`), or it
                          exceeded this module's standard `timeout=30`
                          (#627 precedent) -- distinct from `"not-ancestor"`
                          because no verdict about reachability was actually
                          reached.

    Bounded with `timeout=30`, matching this module's other internal
    Git-probe call sites. This function only classifies; it never chooses a
    different (older) tag, never implements maintenance-branch allocation,
    and never mutates anything -- refusal is the caller's job (P5).

    Both `tag` and `candidate` are validated with the same
    `startswith("-")` / `"\\0" in` predicate `_committed_changelog_text`
    already applies to a revision reaching this module's own argv, before
    either reaches `git` as a bare argv element -- a name beginning with
    `-` could otherwise be parsed as an option by the downstream `git
    merge-base` subcommand. An explicit end-of-options `--` is also placed
    ahead of the two revisions as defense-in-depth, matching this module's
    existing `--` precedent elsewhere.

    **Caller contract -- repo-root binding (R-02, Scope-C security review
    finding 2, MEDIUM).** `project_root` is trusted verbatim; this function
    does not independently discover a project directory. Whatever OTHER
    command a caller used to SELECT `tag` (this module's own
    `last_tag_select`/`last_tag_select_for_policy`, or SKILL.md's `git tag
    -l`) MUST resolve against the IDENTICAL root passed here -- never
    merely "whatever the invoking shell's cwd happens to be" -- or a tag
    selected from one checkout's history can be verified against a
    completely different checkout's `HEAD`. A linked worktree, or any
    other checkout whose actual shell cwd diverges from the harness-
    designated project root, is a real, constructible instance of this,
    not a hypothetical one. `main`'s `verify-tag-ancestor` CLI dispatch
    keeps its legacy 1-argument env-first-else-cwd resolution
    (`CLAUDE_PROJECT_DIR` first, falling back to `os.getcwd()` -- the
    identical precedence `default_targets_path`/`default_backfill_root`
    apply) for backward compatibility only; SKILL.md's Pre-flight
    sequence instead resolves ONE `$PROJECT_ROOT` value up front and
    threads it explicitly -- both as the optional SECOND CLI argument
    here (so this function's own `project_root` is never re-derived by a
    second, independent environment read) and via `-C` on its own bare
    `git tag -l`/`git fetch --tags origin`/`git fetch origin
    "$DEFAULT_BRANCH"`/`git branch --show-current` calls -- so every
    consumer of "the project root" in that sequence reads the SAME
    resolved value, never two reads that merely usually agree."""
    if tag == NONE_SENTINEL:
        return _ANCESTRY_ZERO_TAG
    if (not isinstance(tag, str) or not tag
            or tag.startswith("-") or "\0" in tag):
        return _ANCESTRY_UNRESOLVABLE
    if (not isinstance(candidate, str) or not candidate
            or candidate.startswith("-") or "\0" in candidate):
        return _ANCESTRY_UNRESOLVABLE
    try:
        probe = subprocess.run(
            [git_executable(), "merge-base", "--is-ancestor", "--",
             tag, candidate],
            cwd=project_root, capture_output=True, text=True, timeout=30,
            env=_sanitized_git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return _ANCESTRY_UNRESOLVABLE
    if probe.returncode == 0:
        return _ANCESTRY_ANCESTOR
    if probe.returncode == 1:
        return _ANCESTRY_NOT_ANCESTOR
    return _ANCESTRY_UNRESOLVABLE


def notes_heading_matches(notes_text, tag, policy="semver", initial_version=None):
    """True iff the FIRST changelog heading names `tag` under `policy`.

    Both `## vVERSION` and Keep-a-Changelog `## [VERSION]` spellings are
    accepted. A stale notes-file returns False, so a release lane cannot
    publish the wrong changelog section under the right tag. Missing heading,
    malformed policy input, or non-string input -> False.
    """
    if not isinstance(notes_text, str) or not isinstance(tag, str):
        return False
    headings = list(_H2_RE.finditer(notes_text))
    if not headings:
        return False
    version = _bare_version(tag, policy, initial_version)
    first_version = _heading_version(
        headings[0].group(0), policy, initial_version)
    if first_version != version or first_version == "Unreleased":
        return False
    _section, status = _changelog_section_result(
        notes_text, version, policy, initial_version)
    return status == _SECTION_OK


def release_dates_consistent(changelog_section, tag_message, policy="semver",
                             initial_version=None):
    """True iff the changelog and `Released-at` dates agree under `policy`.

    Guards against the date being hand-typed inconsistently across surfaces.
    Either date absent, malformed policy input, or non-string input -> False.
    """
    if not isinstance(changelog_section, str) or not isinstance(tag_message, str):
        return False
    heading = _H2_RE.match(changelog_section)
    if (heading is None or heading.start() != 0
            or _heading_version(
                heading.group(0), policy, initial_version) in (None, "Unreleased")):
        return False
    cm = _CHANGELOG_DATE_RE.search(heading.group(0))
    released_at = list(_RELEASED_AT_RE.finditer(tag_message))
    trimmed_message = tag_message.rstrip("\r\n")
    if (not cm or len(released_at) != 1
            or released_at[0].end() != len(trimmed_message)):
        return False
    changelog_date = cm.group(1)
    tag_date = released_at[0].group(1)
    try:
        datetime.date.fromisoformat(changelog_date)
        datetime.date.fromisoformat(tag_date)
    except ValueError:
        return False
    return changelog_date == tag_date


def changelog_section(changelog_text, version, policy="semver",
                      initial_version=None):
    """Extract the declared-policy `VERSION` section verbatim.

    The section starts at `## [VERSION] ...` (or `## vVERSION ...`) and ends
    before the next `##` heading, or at end of text. Returns it with exactly
    one trailing newline, or `None` when no valid heading names `version`
    exactly. Non-string or malformed policy input -> `None`.

    This is the mechanical replacement for hand-copying a changelog section:
    Phase 3's `resume_publish` path needs the SAME text Phase 1 composed,
    but Phase 1's own scratch copy is explicitly discardable and routinely
    gone by the time a resumed publish runs. Reading it back out of the
    COMMITTED `$CHANGELOG` -- which Phase 1 step 7 commits before any tag
    exists -- is reading the one permanent home of that text, not
    re-deriving or hand-writing new notes (blind exercise run 19, HIGH-2)."""
    section, status = _changelog_section_result(
        changelog_text, version, policy, initial_version)
    return section if status == _SECTION_OK else None


def _normalize_git_tree_path(path):
    """Normalize portable separators; reject paths outside a Git tree."""
    if not isinstance(path, str) or not path or "\0" in path:
        return None
    normalized = path.replace("\\", "/")
    if (normalized.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized)
            or ":" in normalized):
        return None
    parts = normalized.split("/")
    if any(part in ("", "..") for part in parts):
        return None
    parts = [part for part in parts if part != "."]
    return "/".join(parts) if parts else None


_GIT_REPOSITORY_ENV = {
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


def _sanitized_git_environment():
    """Return a Git environment that cannot redirect repository/object reads."""
    environment = os.environ.copy()
    for name in _GIT_REPOSITORY_ENV:
        environment.pop(name, None)
    # Command-scoped config injected through GIT_CONFIG_COUNT can redefine
    # repository paths without using the better-known GIT_DIR variables.
    environment.pop("GIT_CONFIG_COUNT", None)
    for name in tuple(environment):
        if re.fullmatch(r"GIT_CONFIG_(?:KEY|VALUE)_\d+", name):
            environment.pop(name, None)
    # Replacement refs rewrite the commit/tree/blob Git presents for a known
    # object id. Release notes must reflect the tag's stored objects exactly.
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _committed_changelog_text(repo_root, revision, changelog_path):
    """Return `(text, error)` from one exact regular-file blob at revision."""
    if (not isinstance(repo_root, str) or not repo_root
            or not isinstance(revision, str) or not revision
            or revision.startswith("-") or "\0" in revision):
        return None, "invalid repository root or revision"
    tree_path = _normalize_git_tree_path(changelog_path)
    if tree_path is None:
        return None, "changelog path is not a repository-relative Git path"

    try:
        git = git_executable()
        git_environment = _sanitized_git_environment()
        root_probe = subprocess.run(
            [git, "-C", repo_root, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, env=git_environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return None, f"cannot resolve repository root: {exc}"
    if root_probe.returncode != 0:
        return None, "cannot resolve repository root"
    actual_root = root_probe.stdout.strip()
    supplied_root = os.path.realpath(os.path.abspath(repo_root))
    resolved_root = os.path.realpath(os.path.abspath(actual_root))
    if os.path.normcase(supplied_root) != os.path.normcase(resolved_root):
        return None, "supplied path is not the repository root"

    # Hosted qualification runs before the tag exists and therefore binds the
    # changelog blob by the exact candidate commit object. Recovery/read-back
    # uses the immutable tag ref. Admit only those two explicit shapes: never
    # let an arbitrary revision expression cross this trust boundary.
    exact_object_id = re.fullmatch(r"[0-9a-fA-F]{40,64}", revision) is not None
    if exact_object_id:
        revision_ref = revision
    else:
        revision_ref = f"refs/tags/{revision}"
        try:
            tag_probe = subprocess.run(
                [git, "check-ref-format", revision_ref],
                capture_output=True, timeout=30, env=git_environment)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return None, f"cannot validate release tag: {exc}"
        if tag_probe.returncode != 0:
            return None, "release tag name is invalid"

    try:
        commit_probe = subprocess.run(
            [git, "-C", actual_root, "rev-parse", "--verify",
             f"{revision_ref}^{{commit}}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, env=git_environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return None, f"cannot resolve committed revision: {exc}"
    if commit_probe.returncode != 0:
        return None, "cannot resolve committed revision"
    commit = commit_probe.stdout.strip()
    if exact_object_id and revision.lower() != commit.lower():
        # Reject abbreviated SHA-256 object names and raw annotated-tag object
        # IDs. Hosted qualification promises the exact commit object itself,
        # not merely a spelling Git can peel or prefix-expand to that commit.
        return None, "candidate object is not the exact full commit id"

    try:
        entry_probe = subprocess.run(
            [git, "-C", actual_root, "ls-tree", "-z", commit, "--", tree_path],
            capture_output=True, timeout=30, env=git_environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return None, f"cannot resolve committed changelog: {exc}"
    records = [record for record in entry_probe.stdout.split(b"\0") if record]
    if entry_probe.returncode != 0:
        return None, "committed changelog tree inspection failed"
    if not records:
        return None, "committed changelog path is absent"
    if len(records) != 1:
        return None, "committed changelog path is ambiguous"
    try:
        metadata, encoded_path = records[0].split(b"\t", 1)
        mode, object_type, oid = metadata.split(b" ", 2)
        found_path = encoded_path.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None, "committed changelog tree entry is malformed"
    if (found_path != tree_path or object_type != b"blob"
            or mode not in (b"100644", b"100755")):
        return None, "committed changelog is not an exact regular-file path"

    try:
        blob = subprocess.run(
            [git, "-C", actual_root, "cat-file", "blob", oid.decode("ascii")],
            capture_output=True, timeout=30, env=git_environment)
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeDecodeError) as exc:
        return None, f"cannot read committed changelog: {exc}"
    if blob.returncode != 0:
        return None, "cannot read committed changelog"
    try:
        text = blob.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None, "committed changelog is not UTF-8"
    return text.replace("\r\n", "\n").replace("\r", "\n"), None


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
    `=` at all, or whose NAME is blank (e.g. `"=1.2.3"`), is ignored rather
    than fatal — an empty workflow input can arrive as a bare name or a
    stray leading `=` — but a pair whose NAME is non-blank and unknown is
    reported, because that is a real mismatch rather than an empty slot.

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
        if not name:
            # A blank name (e.g. "=1.2.3") identifies no target -- ignore
            # it exactly like a pair with no "=" at all, rather than
            # falling through and selecting "" as if it were a target.
            continue
        if name not in known:
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
_CHANGELOG_FOOTER_RE = re.compile(
    r"^CHANGELOG:[ \t]*(.*?)[ \t]*$", re.MULTILINE)

# Which types bump, and to what. `refactor` bumps patch and IS harvested
# (see the changelog-grouping rule); `docs`/`chore`/`test`/`ci` bump
# nothing but may still carry a harvested footer.
_BUMPING_TYPES = {"feat": "minor", "fix": "patch", "perf": "patch",
                  "refactor": "patch"}
_BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def _terminal_footer_text(body):
    """Return only the final commit-message paragraph eligible as footers."""
    if not isinstance(body, str):
        return ""
    paragraphs = re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", body.rstrip())
    return paragraphs[-1] if paragraphs else ""


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
    rebuild = row.get("rebuild")
    rebuild = rebuild if isinstance(rebuild, str) and rebuild.strip() else None
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
    each `manifest`, each `changelog`, each `artifacts`, and each
    `generated_manifest` entry (A-5.6).

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
        for key in ("manifest", "changelog", "artifacts", "generated_manifest",
                    "changelog_reconciliations"):
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
            if os.path.basename(lower) == "cargo.toml":
                value = data.get("package", {}).get("version")
            else:
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
    footer_text = _terminal_footer_text(body)
    changelog_matches = list(_CHANGELOG_FOOTER_RE.finditer(footer_text))
    changelog = (changelog_matches[0].group(1).strip()
                 if len(changelog_matches) == 1 else "")
    has_changelog_footer = bool(changelog)
    match = _CC_SUBJECT_RE.match(subject)
    if match is None:
        return {"type": "", "scope": "", "breaking": False, "bump": "none",
                "has_changelog_footer": has_changelog_footer,
                "changelog": changelog}
    ctype = match.group("type").lower()
    breaking = bool(match.group("bang")) or bool(
        _BREAKING_FOOTER_RE.search(footer_text))
    if breaking:
        bump = "major"
    else:
        bump = _BUMPING_TYPES.get(ctype, "none")
    return {
        "type": ctype,
        "scope": match.group("scope") or "",
        "breaking": breaking,
        "bump": bump,
        "has_changelog_footer": has_changelog_footer,
        "changelog": changelog,
    }


def classify_window(commits, reconciliations=None, published_shas=None):
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
    list.  ``reconciliations`` may supply exact-SHA changelog text only for
    SHAs independently present in ``published_shas``.  It never changes the
    commit classification or bump.

    Each row in `commits` carries `classify_commit`'s full per-commit
    verdict -- including `breaking` -- unchanged and in the input list's
    own order (never reordered or recomputed here). SKILL.md's Phase 1
    step 5 changelog composition and its `<summary>` headline rule rely on
    exactly that: reusing `breaking` to route a commit into its own
    `### Breaking` group, and scanning `commits` in this same order to find
    the first breaking entry for a major-bump title.
    """
    rows = []
    reconciliations = reconciliations if isinstance(reconciliations, dict) else {}
    published_shas = published_shas if isinstance(published_shas, (set, frozenset)) else set()
    if not isinstance(commits, (list, tuple)):
        commits = []
    for entry in commits:
        if not isinstance(entry, dict):
            continue
        verdict = classify_commit(entry.get("subject", ""), entry.get("body", ""))
        verdict["sha"] = str(entry.get("sha", ""))
        verdict["subject"] = str(entry.get("subject", ""))
        sha = verdict["sha"]
        reconciled = (
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha) is not None
            and not verdict["has_changelog_footer"]
            and sha in published_shas
            and isinstance(reconciliations.get(sha), str)
            and bool(reconciliations[sha].strip())
            and "\n" not in reconciliations[sha]
            and "\r" not in reconciliations[sha]
        )
        verdict["footer_reconciled"] = reconciled
        if reconciled:
            verdict["changelog"] = reconciliations[sha].strip()
        rows.append(verdict)
    bump = "none"
    for row in rows:
        if _BUMP_RANK[row["bump"]] > _BUMP_RANK[bump]:
            bump = row["bump"]
    missing = [r for r in rows
               if (r["bump"] != "none"
                   and not r["has_changelog_footer"]
                   and not r["footer_reconciled"])]
    return {"bump": bump, "commits": rows, "missing_footer": missing}


def parse_changelog_reconciliations(text, target):
    """Parse a strict SHA-bound changelog-reconciliation ledger.

    Returns only the entries for ``target`` as ``{full_sha: changelog}``, but
    validates every entry first so an unrelated malformed row cannot be
    hidden by target filtering.  The ledger is deliberately narrow: it can
    supply one single-line changelog entry for an exact published commit; it
    cannot change commit classification, version policy, or release scope.
    """
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ChangelogReconciliationError(
                    f"duplicate JSON member {key!r}")
            result[key] = value
        return result

    try:
        data = json.loads(text, object_pairs_hook=unique_object)
    except (TypeError, ValueError) as exc:
        raise ChangelogReconciliationError(
            f"invalid JSON: {exc}") from None
    if not isinstance(data, dict) or set(data) != {"schema_version", "entries"}:
        raise ChangelogReconciliationError(
            "top level must contain exactly schema_version and entries")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ChangelogReconciliationError("schema_version must be integer 1")
    if not isinstance(data["entries"], list):
        raise ChangelogReconciliationError("entries must be a list")
    if len(data["entries"]) > 1024:
        raise ChangelogReconciliationError("entries exceeds the 1024-record limit")

    required = {"target", "commit_sha", "changelog", "reason", "authorization"}
    seen = set()
    selected = {}
    for index, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict) or set(entry) != required:
            raise ChangelogReconciliationError(
                f"entry {index} must contain exactly {', '.join(sorted(required))}")
        values = {}
        for key in required:
            value = entry[key]
            if (not isinstance(value, str) or value != value.strip()
                    or not value or len(value) > 4096
                    or "\r" in value or "\n" in value):
                raise ChangelogReconciliationError(
                    f"entry {index} field {key!r} must be a non-empty "
                    "single-line string of at most 4096 characters")
            values[key] = value
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*",
                        values["target"]) is None:
            raise ChangelogReconciliationError(
                f"entry {index} target is not a valid release target name")
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
                        values["commit_sha"]) is None:
            raise ChangelogReconciliationError(
                f"entry {index} commit_sha must be a full lowercase Git SHA")
        identity = (values["target"], values["commit_sha"])
        if identity in seen:
            raise ChangelogReconciliationError(
                f"duplicate reconciliation for {values['target']} "
                f"{values['commit_sha']}")
        seen.add(identity)
        if values["target"] == target:
            selected[values["commit_sha"]] = values["changelog"]
    return selected


def parse_window_log(text):
    """`git log --format=%H%x00%s%x00%b%x00` output -> the
    `[{sha, subject, body}]` shape `classify_window` consumes.

    Git commit messages cannot contain NUL, so the three-field framing cannot
    be forged by a subject or body line. A printable separator is unsafe here:
    a body can contain any such line and silently turn a breaking footer into
    a phantom record.
    """
    if not isinstance(text, str):
        return None
    fields = text.split("\0")
    if fields and not fields[-1].strip():
        fields.pop()
    if not fields or len(fields) % 3:
        return None
    entries = []
    for index in range(0, len(fields), 3):
        sha = fields[index].strip()
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha) is None:
            return None
        subject = fields[index + 1]
        body = fields[index + 2]
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


_PLAIN_SEMVER_RE = re.compile(
    r"^" + _PLAIN_SEMVER_CAPTURE_PATTERN + r"$")
_BUMP_WORDS = ("major", "minor", "patch")


def apply_bump(base, word):
    """Apply a classify-window bump `word` to `base`, a PLAIN SemVer string
    (`MAJOR.MINOR.PATCH`, no pre-release or build metadata), and return the
    bumped SemVer string. `major`: `X+1.0.0`. `minor`: `X.Y+1.0`. `patch`:
    `X.Y.Z+1`.

    Returns `None` -- never raises, per this module's mechanism-function
    invariant -- when `base` is not plain SemVer (reusing the same
    no-leading-zero grammar `SEMVER` anchors its own major/minor/patch
    groups with) or `word` is not exactly one of the three bumping words.
    This deliberately EXCLUDES `word == "none"`: a caller must never apply a
    non-bump, and passing `none` here is refused rather than echoing `base`
    back unchanged, which would silently look like a successful (if inert)
    bump.

    #585 MEDIUM-3: the bump arithmetic was the single unmechanized judgment
    left in the release lane -- step 4 had the operator "apply the step-2
    bump to `$BASE_VERSION`" by hand, and nothing downstream re-derived it,
    so the hard rule "a `feat` in the window cannot ship as a `patch`" had
    no enforcement anywhere. `apply-bump` (the CLI subcommand below) is the
    sanctioned way to do this arithmetic instead of by eye.
    """
    if not isinstance(base, str) or not isinstance(word, str):
        return None
    match = _PLAIN_SEMVER_RE.fullmatch(base.strip())
    if match is None or word not in _BUMP_WORDS:
        return None
    major, minor, patch = (int(g) for g in match.groups())
    if word == "major":
        return f"{major + 1}.0.0"
    if word == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def derive_version(base, word, policy="semver", initial_version=None):
    """Derive one release identity under `policy`, or None on invalid input.

    Existing SemVer arithmetic delegates unchanged to `apply_bump`. A numeric
    sequence emits its declared initial identity for an empty series and then
    increments only the final fixed-shape component for every bumping
    Conventional Commit classification. `none` is refused for both policies.
    """
    if policy == "semver" and initial_version is None:
        return apply_bump(base, word)
    if policy != "numeric-sequence" or word not in _BUMP_WORDS:
        return None
    initial_key = numeric_sequence_key(initial_version, initial_version)
    if initial_key is None:
        return None
    if base == NONE_SENTINEL:
        return initial_version
    base_key = numeric_sequence_key(base, initial_version)
    if base_key is None or base_key < initial_key:
        return None
    next_key = base_key[:-1] + (base_key[-1] + 1,)
    return ".".join(str(part) for part in next_key)


# Exit codes a POSIX shell uses to report that a command's INTERPRETER OR
# PROGRAM ITSELF could not be located or executed, as distinct from the
# program running and reporting a failure: 127 is POSIX "command not
# found", 126 is POSIX "found but not executable" (e.g. missing execute
# bit, or a script with a shebang naming an interpreter that itself is
# missing), and 9009 is the code Windows' `cmd.exe` is documented to report
# for an unresolvable command in several invocation shapes (batch-file/npm
# wrapper contexts). #585 MEDIUM-2 / #584 MEDIUM-1: this is a BEST-EFFORT,
# POSIX-reliable signal -- a bare `subprocess.run(cmd, shell=True)` "is not
# recognized" error under a raw `cmd.exe /c` was measured on a Windows 11
# host to return 1, indistinguishable there from an ordinary command
# failure, so this set does not catch every Windows "not found" shape. It
# reliably catches the POSIX shape this campaign's issues were filed
# against (a row hardcoding `python3` on a host that has only `python`),
# and any Windows invocation that does surface 9009.
_COULD_NOT_RUN_CODES = frozenset({126, 127, 9009})


def _could_not_run(returncode):
    """True iff `returncode` is one of the exit codes above that means the
    declared command's interpreter or program itself was never located --
    "could not run", never "ran and disagreed" (house rule: the two must
    never be folded together)."""
    return returncode in _COULD_NOT_RUN_CODES


# #602: `run-pre-tag` dispatches every declared `pre-tag` row with
# `subprocess.run(command, shell=True, …)`. On POSIX that already runs
# through a POSIX shell (`/bin/sh`), so a row spelled `"$PY"` (the #601
# convention) already expands there. On WINDOWS, `shell=True` unconditionally
# dispatches through `cmd.exe` -- a CPython `subprocess` behavior, not host
# configuration -- and `cmd.exe` performs no `$VAR` expansion, so `"$PY"`
# passes through as the literal, unrecognized token and fails with an exit
# code outside the could-not-run set, misdiagnosed as drift (exit 5). This
# was MEASURED, not hypothesized (issue #602).
#
# `_resolve_posix_shell()` finds a POSIX-compatible shell (Git for Windows'
# own `bash.exe`, an MSYS2 build that runs Windows-native binaries directly
# -- NOT WSL's `bash.exe`, which runs inside a separate Linux filesystem and
# cannot see a Windows path like `cwd=project_root` or a Windows `PY`
# interpreter path the same way) so the caller can dispatch a declared row
# through it instead of `cmd.exe`.
def _resolve_posix_shell():
    """Resolve an absolute path to a POSIX-compatible shell for dispatching
    declared `pre-tag` rows, or None if none could be found.

    Returns None unconditionally on a non-Windows host: `shell=True` already
    dispatches through a POSIX shell there (`/bin/sh`), so no resolution is
    needed and the caller keeps its existing `shell=True` dispatch unchanged.

    On Windows, resolution order:
      1. Relative to `git --exec-path` (via the trusted `git_executable()`
         seam). Git for Windows ships its own `bash.exe` at a fixed position
         relative to the install root -- `<root>/bin/bash.exe` -- and
         `git --exec-path` reports a path under
         `<root>/mingw64/libexec/git-core`, so `../../../bin/bash.exe`
         relative to that finds it deterministically, tied to the SAME git
         install this process already trusts, even when bash was never
         added to PATH (Git for Windows' installer does not add it by
         default). This is the PRIMARY strategy because it cannot resolve
         to a different program entirely the way a PATH search can.
      2. `shutil.which("bash")`, as a fallback for a non-standard Git for
         Windows layout -- but a hit under `system32` or `WindowsApps` is
         rejected: both are where Windows' own WSL launcher stub installs a
         same-named `bash.exe` that runs inside a separate Linux
         filesystem, not a POSIX-on-Windows shell, and accepting it would
         swap one silent misdispatch for another.

    Never raises: any resolution failure (git not found, `--exec-path`
    failing, a filesystem error) is treated as "not found", matching every
    other mechanism function in this module's "never raise on malformed
    input" convention -- the CALLER decides what a None means (here: report
    a distinct could-not-run exit rather than silently falling back to
    `cmd.exe`, the exact misdiagnosis this fix closes).
    """
    if os.name != "nt":
        return None
    try:
        exec_path = subprocess.run(
            [git_executable(), "--exec-path"],
            capture_output=True, text=True).stdout.strip()
    except OSError:
        exec_path = ""
    if exec_path:
        candidate = os.path.normpath(
            os.path.join(exec_path, "..", "..", "..", "bin", "bash.exe"))
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("bash")
    if found:
        normalized = os.path.normpath(found).lower()
        if "\\system32\\" not in normalized and "\\windowsapps\\" not in normalized:
            return found
    return None


# --------------------------------------------------------------------------- #
# Declared-target-file parser. Grammar: per-target `[name]` sub-blocks of
# `key: value` lines inside the HTML-comment delimiter convention this
# codebase's path-scope reader (`_scopelib.py`) already uses — reused here
# rather than inventing a second delimiter syntax.
# --------------------------------------------------------------------------- #

_OPEN_RE = re.compile(r"<!--\s*release-targets\s*-->")
_CLOSE_RE = re.compile(r"<!--\s*/release-targets\s*-->")
_HEADER_RE = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9._-]*)\]$")

# A key not in _LIST_KEYS is scalar: exactly one value per target block, a
# second occurrence of the same key within one block is a DuplicateKeyError.
# List keys repeat by design and preserve declaration order.
_LIST_KEYS = frozenset({
    "manifest", "artifacts", "pre-tag", "payload-exclude", "generated-manifest",
    "release-asset",
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
    "version-policy": "version_policy",
    "initial-version": "initial_version",
    "release-build": "release_build",
    "release-asset": "release_assets",
    "changelog-reconciliations": "changelog_reconciliations",
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
        "version_policy": "semver",
        "initial_version": None,
        "release_build": None,
        "release_assets": [],
        "changelog_reconciliations": None,
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
    prefix = row["prefix"]
    forbidden = " ~^:?*[\\"
    unsafe_prefix = (
        prefix.startswith(("-", "/", ".", "refs/"))
        or prefix.endswith(("/", "."))
        or ".." in prefix
        or "@{" in prefix
        or "//" in prefix
        or any(ord(char) < 32 or ord(char) == 127 or char in forbidden
               for char in prefix)
        or any(not part or part.startswith(".") or part.endswith(".lock")
               for part in prefix.split("/"))
    )
    if unsafe_prefix:
        raise MalformedBlockError(
            f"target {row['target']!r} prefix is not a safe Git tag prefix")
    policy = row["version_policy"]
    initial_version = row["initial_version"]
    if policy not in ("semver", "numeric-sequence"):
        raise MalformedBlockError(
            f"target {row['target']!r} declares unknown version-policy "
            f"{policy!r}")
    if policy == "semver" and initial_version is not None:
        raise MalformedBlockError(
            f"target {row['target']!r} declares initial-version for the "
            "semver policy")
    if (policy == "numeric-sequence"
            and numeric_sequence_key(initial_version, initial_version) is None):
        raise MalformedBlockError(
            f"target {row['target']!r} numeric-sequence policy requires an "
            "initial-version of two or more canonical dotted numeric components")
    writable_surfaces = [row["changelog"], row["provenance_manifest"]]
    for field in ("manifest", "generated_manifest", "artifacts"):
        writable_surfaces.extend(row[field])
    # Literal spaces are valid file names; overlap checks below retain their
    # conservative default so uncertain paths cannot hide governance scratch.
    if any(_normalised_release_path(path, allow_internal_spaces=True) in (None, ".")
           for path in writable_surfaces if path is not None):
        raise MalformedBlockError(
            f"target {row['target']!r} declares a writable release surface "
            "outside the repository or at its root")
    payload_surfaces = [row["payload"], *row["payload_exclude"]]
    if any(not isinstance(path, str)
           or any(ord(char) < 32 or ord(char) == 127 for char in path)
           for path in payload_surfaces):
        raise MalformedBlockError(
            f"target {row['target']!r} declares a payload path containing "
            "a control byte")
    build_declared = row["release_build"] is not None
    assets_declared = bool(row["release_assets"])
    if build_declared != assets_declared:
        raise MalformedBlockError(
            f"target {row['target']!r} must declare release-build and one "
            "or more release-asset values together")
    if build_declared:
        if not row["release_build"].strip():
            raise MalformedBlockError(
                f"target {row['target']!r} declares a blank release-build")
        representative_version = (
            initial_version if policy == "numeric-sequence" else "1.2.3")
        representative_tag = row["prefix"] + representative_version
        if render_release_assets(
                row["release_assets"], representative_version,
                representative_tag) is None:
            raise MalformedBlockError(
                f"target {row['target']!r} declares an unsafe, malformed, "
                "or duplicate release-asset template")
    reconciliations = row["changelog_reconciliations"]
    if (reconciliations is not None
            and _normalised_release_path(reconciliations) in (None, ".")):
        raise MalformedBlockError(
            f"target {row['target']!r} changelog-reconciliations must name "
            "one repository-relative file")


_GOVERNANCE_SCRATCH_PATHS = (
    ".codearbiter/gate-events.log",
    ".codearbiter/.markers",
)


def _normalised_release_path(value, *, allow_internal_spaces=False):
    """Return a conservative repository-relative path, or None on ambiguity.

    A path that cannot be compared safely must prevent a scratch exclusion;
    uncertainty may make a clean-tree gate noisier, never blind it.
    """
    if not isinstance(value, str):
        return None
    if (value != value.strip()
            or any((char.isspace() and (not allow_internal_spaces or char != " "))
                   or ord(char) < 32 or ord(char) == 127
                   for char in value)):
        return None
    raw = value.replace("\\", "/")
    if (not raw or raw.startswith(('/', ':'))
            or any(char in raw for char in "*?[]")
            or re.match(r"^[A-Za-z]:", raw)):
        return None
    components = raw.split("/")
    if (raw != "."
            and any(component.endswith((".", " "))
                    or re.search(r"~\d", component)
                    for component in components)):
        return None
    normalised = posixpath.normpath(raw)
    if normalised == ".." or normalised.startswith("../"):
        return None
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return (normalised or ".").casefold()


def _release_paths_overlap(left, right):
    if left is None or right is None:
        return True
    if left == "." or right == ".":
        return True
    return (left == right
            or left.startswith(right.rstrip("/") + "/")
            or right.startswith(left.rstrip("/") + "/"))


def _release_path_contains(container, path):
    if container is None or path is None:
        return False
    return container == "." or path == container or path.startswith(
        container.rstrip("/") + "/")


def governance_scratch_exclusions(row):
    """Return scratch paths safe to exclude for this declared target.

    Governance-owned scratch is normally outside a target, but an operator
    may deliberately declare it (or the whole repository) as a payload,
    manifest, changelog, generated manifest, provenance manifest, artifact,
    or release asset. Such a declaration wins: the path remains visible to
    clean-tree and pre-tag mutation gates.
    """
    surfaces = [row.get("changelog"), row.get("provenance_manifest"),
                row.get("changelog_reconciliations")]
    for field in ("manifest", "generated_manifest", "artifacts",
                  "release_assets"):
        surfaces.extend(row.get(field) or [])

    normalised_surfaces = [
        _normalised_release_path(value)
        for value in surfaces
        if value is not None and (not isinstance(value, str) or value.strip())
    ]

    payload = _normalised_release_path(row.get("payload"))
    payload_excludes = [
        _normalised_release_path(value)
        for value in (row.get("payload_exclude") or [])
    ]

    def overlaps(scratch):
        scratch_path = _normalised_release_path(scratch)
        for surface in normalised_surfaces:
            if _release_paths_overlap(surface, scratch_path):
                return True
        if payload is None:
            return True
        if _release_paths_overlap(payload, scratch_path):
            if not any(_release_path_contains(exclusion, scratch_path)
                       for exclusion in payload_excludes):
                return True
        return False

    return [path for path in _GOVERNANCE_SCRATCH_PATHS if not overlaps(path)]


def release_tree_status(row, project_root, nul=False):
    """Run the target-aware repository-wide clean-tree probe.

    Bounded with `timeout=30`, matching every other internal Git-probe call
    site in this module (#627 Finding 1). A hang (index lock, network-mounted
    repo, credential-helper prompt) must not hang the release lane forever
    with no diagnostic: `subprocess.TimeoutExpired` is caught and converted
    into a synthetic failed `CompletedProcess`, which every existing caller
    already treats as a probe failure (`clean-tree-status` returns
    `probe.returncode` directly; `run-pre-tag`'s `_tree_state()` treats a
    nonzero returncode as "the probe itself failed", never as a detected
    mutation) — no caller-side change is required.
    """
    scratch_pathspecs = [
        f":(exclude,top){path}"
        for path in governance_scratch_exclusions(row)
    ]
    args = [git_executable(), "status", "--porcelain", *(["-z"] if nul else []),
            "--", ":/",
            *scratch_pathspecs]
    try:
        status_probe = subprocess.run(
            args, capture_output=True, text=not nul, cwd=project_root,
            timeout=30, env=_sanitized_git_environment())
        if status_probe.returncode != 0:
            return status_probe
        flags_probe = subprocess.run(
            [git_executable(), "ls-files", "-v", "-z", "--", ":/",
             *scratch_pathspecs],
            capture_output=True, cwd=project_root, timeout=30,
            env=_sanitized_git_environment())
        if flags_probe.returncode != 0:
            return subprocess.CompletedProcess(
                args, flags_probe.returncode,
                b"" if nul else "",
                (flags_probe.stderr if nul else
                 flags_probe.stderr.decode("utf-8", errors="replace")))
        hidden = []
        for record in flags_probe.stdout.split(b"\0"):
            if not record:
                continue
            marker = record[:1]
            if marker == b"S" or marker.islower():
                try:
                    rel = record[2:].decode("utf-8")
                except UnicodeDecodeError:
                    rel = "<non-UTF-8-path>"
                hidden.append(f"!! hidden-index-state {rel}")
        if hidden:
            if nul:
                extra = b"\0".join(
                    line.encode("utf-8") for line in hidden) + b"\0"
                status_probe.stdout += extra
            else:
                status_probe.stdout += "".join(line + "\n" for line in hidden)
        return status_probe
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args, 1, b"" if nul else "",
            (b"git status probe timed out after 30 seconds" if nul else
             "git status probe timed out after 30 seconds"))


def parse_release_targets(text):
    """Parse the declared-target-file GRAMMAR from `text` (already-read file
    content) into a list of row dicts, one per `[target]` block, each
    carrying: target, prefix, manifest (list), changelog, payload,
    payload_exclude (list), rebuild, artifacts (list), provenance_manifest,
    pre_tag (list), latest_eligible (bool), generated_manifest (list),
    generate, display_name, version_policy, initial_version, release_build,
    release_assets.

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
            if key != "pre-tag" and "," in value:
                raise MalformedBlockError(
                    f"list-valued key {key!r} in target "
                    f"{row['target']!r} cannot contain a literal comma; "
                    "comma is the declared show-row field separator")
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

    for index, declared in enumerate(rows):
        prefix = declared["prefix"]
        for other in rows[:index]:
            other_prefix = other["prefix"]
            if (prefix.startswith(other_prefix)
                    or other_prefix.startswith(prefix)):
                raise MalformedBlockError(
                    f"targets {other['target']!r} and {declared['target']!r} "
                    f"declare overlapping tag prefixes {other_prefix!r} "
                    f"and {prefix!r}")
    latest_targets = [declared["target"] for declared in rows
                      if declared["latest_eligible"]]
    if len(latest_targets) > 1:
        raise MalformedBlockError(
            "latest-eligible may be true for at most one release target; "
            "declared by " + ", ".join(repr(name) for name in latest_targets))

    return rows


def load_targets(path):
    """Read `path` and parse it via `parse_release_targets`. The one function
    in this module that touches the filesystem — opened with `newline=""` so
    a `\\r\\n` line ending survives into the parser exactly as it is on disk,
    rather than being silently normalised away by Python's own text-mode
    universal-newline translation before this module's own CRLF handling
    ever runs.

    A genuinely MISSING path (`FileNotFoundError`, i.e. `errno == ENOENT`)
    raises `AbsentBlockError` rather than a bare `OSError` — the same
    declared-error contract `parse_release_targets` gives every other
    violation, so a `contents: write` caller can catch one exception type
    instead of one type for content problems and another for I/O ones. There
    is, in the end, no block to find at a path with nothing on it.

    Any OTHER `OSError` (permission denied, the path naming a directory, a
    transient I/O failure, ...) means the path exists in some form but this
    process could not read it, and raises `UnreadableTargetsFileError`
    instead — NOT `AbsentBlockError` — because "unreadable" and "absent" are
    different facts about the project ([[never-fold-unreadable-into-absent]]):
    the Back-fill lane's sanctioned trigger is `except AbsentBlockError:`,
    and a permissions error on an existing declared file must STOP there,
    never be folded into "nothing here, safe to write a fresh one."

    An EXISTING, readable file that simply carries no delimiter block is a
    THIRD, different failure (HIGH-1, adversarial review 2026-07-31) and
    raises `FileExistsNoBlockError` instead — see that class's docstring.
    This function is the only place any of these three distinctions can be
    made, since it is the only one that knows whether `open()` actually
    succeeded and, if not, why."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except FileNotFoundError as exc:
        raise AbsentBlockError(
            f"could not read release-targets file {path!r}: {exc}") from exc
    except OSError as exc:
        raise UnreadableTargetsFileError(
            f"could not read release-targets file {path!r}: {exc}") from exc
    except UnicodeError as exc:
        raise UnreadableTargetsFileError(
            f"release-targets file {path!r} is not UTF-8: {exc}") from exc
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
    `changelog`, `changelog_reconciliations`, `payload`, `payload_exclude`,
    `latest_eligible`) ONLY when exactly one manifest candidate and exactly
    one changelog candidate were found. Raises
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
        # A first release may have real, already-published history from
        # before CHANGELOG footers were required. Back-fill must declare the
        # existing exact-SHA reconciliation mechanism up front so that the
        # adoption commit can land the operator-authored ledger on the
        # default branch before the release lane widens its first window.
        "changelog_reconciliations":
            ".codearbiter/release-changelog-reconciliations.json",
        "payload": ".",
        # Back-fill is the release-only adoption lane. Its own hooks create
        # governance scratch under .codearbiter/, so a root payload without
        # this exclusion can never become clean after ordinary hook use.
        "payload_exclude": [".codearbiter/"],
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

    Emits a `changelog-reconciliations` line when `row` declares one, and a
    `latest-eligible` line when `row` declares one (HIGH-2,
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
    if row.get("changelog_reconciliations") is not None:
        lines.append(
            "changelog-reconciliations: "
            f"{row['changelog_reconciliations']}")
    lines.append(f"payload: {row['payload']}")
    for excluded in row.get("payload_exclude", []):
        lines.append(f"payload-exclude: {excluded}")
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


def _load_declared_changelog_reconciliations(
        row, target, project_root, published_commit):
    """Load one target's ledger from the fetched default-branch commit."""
    declared = row.get("changelog_reconciliations")
    if declared is None:
        return {}
    tree_path = _normalize_git_tree_path(declared)
    if tree_path is None or _normalised_release_path(declared) == ".":
        raise ChangelogReconciliationError(
            "changelog-reconciliations must name one repository-relative file")
    root = os.path.realpath(os.path.abspath(project_root))
    try:
        git = git_executable()
        environment = _sanitized_git_environment()
        root_probe = subprocess.run(
            [git, "rev-parse", "--show-toplevel"], cwd=root,
            capture_output=True, text=True, timeout=30, env=environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ChangelogReconciliationError(
            f"could not verify repository root: {exc}") from None
    if (root_probe.returncode != 0
            or os.path.normcase(os.path.realpath(os.path.abspath(
                root_probe.stdout.strip()))) != os.path.normcase(root)):
        raise ChangelogReconciliationError(
            "could not bind changelog-reconciliations to the repository root")

    try:
        entry_probe = subprocess.run(
            [git, "ls-tree", "-z", published_commit, "--", tree_path], cwd=root,
            capture_output=True, timeout=30, env=environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ChangelogReconciliationError(
            f"could not inspect committed ledger: {exc}") from None
    entries = [entry for entry in entry_probe.stdout.split(b"\0") if entry]
    if entry_probe.returncode != 0 or len(entries) != 1:
        raise ChangelogReconciliationError(
            "changelog-reconciliations must be one regular file committed on "
            "the fetched default branch")
    match = re.fullmatch(
        rb"(100644|100755) blob ([0-9a-f]{40}|[0-9a-f]{64})\t(.+)",
        entries[0])
    if match is None:
        raise ChangelogReconciliationError(
            "changelog-reconciliations must be a committed regular blob")
    try:
        found_path = match.group(3).decode("utf-8")
    except UnicodeError as exc:
        raise ChangelogReconciliationError(
            f"committed ledger path is not UTF-8: {exc}") from None
    if found_path != tree_path:
        raise ChangelogReconciliationError(
            "committed ledger path does not match the declaration exactly")
    object_sha = match.group(2).decode("ascii")
    try:
        size_probe = subprocess.run(
            [git, "cat-file", "-s", object_sha], cwd=root,
            capture_output=True, text=True, timeout=30, env=environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ChangelogReconciliationError(
            f"could not inspect committed ledger size: {exc}") from None
    if size_probe.returncode != 0 or not size_probe.stdout.strip().isdigit():
        raise ChangelogReconciliationError(
            "could not verify committed ledger size")
    if int(size_probe.stdout.strip()) > 1024 * 1024:
        raise ChangelogReconciliationError("ledger exceeds the 1 MiB limit")
    try:
        blob_probe = subprocess.run(
            [git, "cat-file", "blob", object_sha], cwd=root,
            capture_output=True, timeout=30, env=environment)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ChangelogReconciliationError(
            f"could not read committed ledger: {exc}") from None
    if blob_probe.returncode != 0:
        raise ChangelogReconciliationError("could not read committed ledger")
    try:
        text = blob_probe.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise ChangelogReconciliationError(
            f"committed ledger is not UTF-8: {exc}") from None
    return parse_changelog_reconciliations(text, target)


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
           (`FileExistsNoBlockError`), one this process could not read for
           any other reason such as a permissions error
           (`UnreadableTargetsFileError`), or is empty, malformed, or
           otherwise unparseable. All of these STOP outright per the
           skill's "Targets" section and must never be mistaken for
           "safe to back-fill".

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
      last-tag-for-policy <prefix> <policy> <initial_version>
                                  stdin = tags -> prints the selected tag or
                                  <none>, under a declared version policy
                                  (`semver` or `numeric-sequence`).
      verify-tag-ancestor <tag> [<project_root>]
                                  refuses an ambiguous release baseline
                                  before it is used for anything (#570
                                  finding BODY-03). `last-tag`/`last-tag-
                                  for-policy` select the highest tag by
                                  VALUE alone, with no git access; this
                                  confirms the SELECTED tag actually
                                  resolves to a commit reachable from HEAD.
                                  `<project_root>`, when given, is used
                                  VERBATIM and no environment read happens
                                  at all -- the caller's own single already-
                                  resolved root, threaded through explicitly
                                  rather than re-derived here a second time
                                  (R-02, Scope-C security review finding 2,
                                  MEDIUM: two independent env-first-else-cwd
                                  reads, taken at two different times, are
                                  "usually agree", never a guarantee).
                                  Omitted, this falls back to the prior
                                  1-argument behavior -- `CLAUDE_PROJECT_DIR`
                                  first, else this process's own cwd --
                                  unchanged, for backward compatibility.
                                  exit 0 -- `<tag>` is `<none>` (the
                                  zero-tag first-release path, unaffected)
                                  or a confirmed ancestor of HEAD -- 1 --
                                  `<tag>` resolves but is NOT an ancestor of
                                  HEAD, printing the tag and the cause; the
                                  caller MUST stop, never silently fall
                                  back to an older tag, reuse the tag
                                  namespace, or move/delete the tag -- 2 --
                                  `<tag>` or HEAD could not be resolved at
                                  all (an unresolvable ref, a probe error,
                                  or a `timeout=30` expiry). Never chooses a
                                  different baseline and never implements
                                  maintenance-branch allocation policy; it
                                  only detects and refuses ambiguity (P5).
      notes-match <tag> <notes_file>
                                  exit 0 iff the notes file's first heading
                                  names the same version as `tag`.
      changelog-section <repo_root> <revision> <changelog_path> <version>
                                  prints the `## [<version>] ...` section of
                                  the exact regular-file blob at
                                  `<revision>:<changelog_path>`, bound to the
                                  supplied repository root, from its heading
                                  up to the next H2 heading or EOF.
                                  exit 0 with the section on stdout - 1 no
                                  heading names `<version>` - 3 source/root/
                                  path/revision cannot be read safely - 4 the
                                  changelog is malformed or ambiguous. The
                                  sanctioned way for
                                  Phase 3's `resume_publish` path to
                                  reconstruct release notes when Phase 1's
                                  own scratch file did not survive to a
                                  later session (blind exercise run 19,
                                  HIGH-2).
      check-manifests <target> <version>
                                  asserts EVERY declared `manifest` in the row
                                  equals <version>. exit 0 all match - 1 at
                                  least one disagrees (each named) - 2 bad
                                  invocation or a manifest that cannot be
                                  parsed. The lane's only runnable all-paths
                                  equality guard: `classify` short-circuits on
                                  a fresh publish and never reaches its own
                                  version comparison (run 12).
      classify-window [<target> <default-branch>]
                                  stdin = `git log $WINDOW --pretty=format:
                                  %H%x00%s%x00%b%x00 -- $PAYLOAD` -> prints the
                                  derived bump, then accepted `[RECONCILED]`
                                  rows and one
                                  `[NEEDS-TRIAGE] <sha> <subject>` line per
                                  BUMPING commit missing a CHANGELOG: footer.
                                  exit 0 clean - 1 a footer is missing (the
                                  step-3 BLOCK) - 2 the window is non-bumping
                                  - 4 a declared reconciliation ledger or
                                  exact default-branch proof failed closed.
                                  The no-argument form remains the strict
                                  legacy classifier and accepts no ledger.
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
                                  fixer). Each declared command's environment
                                  carries `PY=<this process's own
                                  interpreter>`, so a row may portably spell
                                  `"$PY"` instead of a hardcoded interpreter
                                  on every platform (#583 MEDIUM-2 / #584
                                  MEDIUM-3): on Windows this dispatch resolves
                                  a POSIX-compatible shell (Git for Windows'
                                  own `bash.exe`) rather than falling through
                                  to `shell=True`'s default `cmd.exe`, which
                                  cannot expand `$VAR` (#602). exit 0 all
                                  passed - 5 a command RAN and reported drift
                                  - 6 a command exited 0 but MUTATED the tree
                                  (or the tree was already dirty on a probe
                                  failure path that predates this fix) - 7 a
                                  command's interpreter or program itself
                                  could not be located/executed at all --
                                  NOT drift, no release-edit discard needed
                                  (#585 MEDIUM-2 / #584 MEDIUM-1) - 8 the
                                  tree-state PROBE itself failed, so no
                                  verdict about the declared commands exists
                                  (distinct from 6, which names a command as
                                  the fault) - 9 no POSIX-compatible shell
                                  could be resolved to dispatch a declared
                                  row on Windows, so NO command ran at all --
                                  NOT drift, distinct from 7 (#602) - 2 bad
                                  invocation / unknown target - 3/4
                                  declared-file states.
      semver-greater <candidate> <floor>
                                  exit 0 iff `candidate` is STRICTLY greater
                                  than `floor`; 1 when equal or lesser; 2 when
                                  either is unparseable. The sanctioned way to
                                  run the lane's strictly-greater assertions,
                                  including the manifest FLOOR check -- both
                                  were hand-done against a hard rule saying
                                  the version MUST NOT be guessed.
      apply-bump <base> <word>   prints the SemVer `base` bumped by `word`
                                  (`major`/`minor`/`patch`; `none` and any
                                  other value are refused). exit 0 with the
                                  bumped version on stdout - 2 when `base` is
                                  not plain SemVer or `word` is not one of
                                  the three bumping words. The sanctioned way
                                  to apply the bump `classify-window`
                                  derived, instead of by eye (#585 MEDIUM-3).
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
      validate-reconciliations <target> <ledger-file>
                                  validates a Back-fill ledger with the same
                                  strict parser the published release path
                                  uses. exit 0 valid - 4 missing, unreadable,
                                  non-UTF-8, oversized, or malformed. It does
                                  not claim the file is published; the later
                                  `classify-window` ancestry proof owns that.
      show-row <target> [--field NAME]
                                  prints every field the row declares, one
                                  shell-quoted `NAME=value` line each
                                  (multi-valued fields comma-separated), or
                                  just NAME's raw
                                  value with `--field`. Reads via
                                  `default_targets_path()` only, no
                                  `--targets-file` override.
      list-field <target> <field> prints one exact item per line for a
                                  declared multi-valued field. The accepted
                                  field names are manifest,
                                  generated-manifest, artifacts, pre-tag,
                                  payload-exclude, and release-assets. This
                                  is the argument-preserving interface for
                                  values such as shell commands containing
                                  commas.
      payload-pathspec <target>  prints the row's `payload`, minus its
                                  `payload-exclude` entries, as verbatim git
                                  pathspec arguments (`:(exclude)` forms
                                  included) — the sanctioned way to spell a
                                  window subtraction plain `git log --
                                  <path>` cannot express. Same declared-file
                                  resolution as `show-row`.
      clean-tree-status <target> runs repository-wide `git status
                                  --porcelain` while excluding governance
                                  scratch only when it does not overlap any
                                  surface declared by the target. Prints the
                                  porcelain result; exit 0 on a successful
                                  probe even when dirty, 2 for bad invocation
                                  or unknown target, 3/4 for declared-file
                                  states, and git's non-zero status on probe
                                  failure.

    `--targets-file PATH` overrides `default_targets_path()` for `tag-prefix`
    and `list-targets` only; `show-row`, `list-field`, `payload-pathspec`, and
    `clean-tree-status` always resolve the declared file through
    `default_targets_path()` with no override, and every remaining subcommand
    needs no declared file at all. `tag-prefix`, `list-targets`, `show-row`,
    `list-field`, `payload-pathspec`, and `clean-tree-status` all exit 3 when the declared
    file is genuinely absent and 4 for every other declared-file error
    (HIGH-1, `_targets_error_exit_code`); every other subcommand
    prints a value/label and exits 0, or writes a short cause to stderr and
    exits non-zero — never a bare traceback, so a caller shelling out to
    this file gets a diagnosable failure either way. Returns a process exit
    code."""
    if not argv:
        sys.stderr.write(
            "usage: _releaselib.py {tag-prefix|list-targets|show-row|list-field|"
            "payload-pathspec|clean-tree-status|last-tag|last-tag-for-policy|"
            "verify-tag-ancestor|notes-match|"
            "changelog-section|dates-match|semver-greater|version-greater|"
            "apply-bump|derive-version|render-release-assets|"
            "verify-release-assets|classify|peel-tag|"
            "run-pre-tag|adoption-commit|classify-window|check-manifests|"
            "backfill-detect|validate-reconciliations} ...\n")
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

    if cmd in ("show-row", "payload-pathspec", "list-field"):
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
        list_field = None
        if cmd == "list-field":
            if len(rest) != 2:
                sys.stderr.write(
                    "list-field requires exactly <target> <field>\n")
                return 2
            list_field = rest[1]
            rest = rest[:1]
        elif "--field" in rest:
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
            # One record per line preserves a pathspec containing spaces.
            # The release skill loads these records into quoted positional
            # parameters; shell words cannot represent this boundary safely.
            print("\n".join(parts))
            return 0

        if cmd == "list-field":
            list_fields = {
                "manifest": "manifest",
                "generated-manifest": "generated_manifest",
                "artifacts": "artifacts",
                "pre-tag": "pre_tag",
                "payload-exclude": "payload_exclude",
                "release-assets": "release_assets",
            }
            row_field = list_fields.get(list_field)
            if row_field is None:
                sys.stderr.write(
                    f"unknown list-valued release field: {list_field}\n")
                return 2
            for item in row.get(row_field, []):
                print(str(item))
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
                  ("CHANGELOG_RECONCILIATIONS", "changelog_reconciliations"),
                  ("DISPLAY_NAME", "display_name")]
        fields += [
            ("VERSION_POLICY", "version_policy"),
            ("INITIAL_VERSION", "initial_version"),
            ("RELEASE_BUILD", "release_build"),
            ("RELEASE_ASSETS", "release_assets"),
        ]
        query_fields = fields

        def _flatten(value):
            if isinstance(value, (list, tuple)):
                return ",".join(str(v) for v in value)
            if isinstance(value, bool):
                return "true" if value else "false"
            return "" if value is None else str(value)

        if field is not None:
            wanted = field.strip().lower().replace("-", "_")
            by_key = {key: name for name, key in query_fields}
            if wanted not in by_key:
                sys.stderr.write(
                    f"unknown field {field!r}; declared fields are: "
                    + ", ".join(key for _n, key in query_fields) + "\n")
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

    if cmd == "last-tag-for-policy" and len(rest) == 3:
        prefix, policy, initial_version = rest
        initial = initial_version or None
        if (policy not in ("semver", "numeric-sequence")
                or (policy == "semver" and initial is not None)
                or (policy == "numeric-sequence"
                    and numeric_sequence_key(initial, initial) is None)):
            sys.stderr.write("last-tag-for-policy: invalid policy declaration\n")
            return 2
        print(last_tag_select_for_policy(
            sys.stdin.read().split(), prefix, policy, initial))
        return 0

    if cmd == "verify-tag-ancestor" and len(rest) in (1, 2):
        tag = rest[0]
        # R-02 (Scope-C security review finding 2, MEDIUM): an explicit
        # SECOND argument, when given, is the caller's own already-resolved
        # project root and wins outright -- no environment read happens at
        # all. Without this, this dispatch's own env-first-else-cwd
        # resolution and SKILL.md's shell-side `$PROJECT_ROOT` resolution
        # are two INDEPENDENT reads of "the project root", taken at two
        # different times (the shell's at bullet-time, this process's at
        # invocation-time) -- they agree only when `CLAUDE_PROJECT_DIR` is
        # set (trusted-harness input under Claude Code) and neither call's
        # own cwd has moved since. On a host with no such env var at all
        # (Codex, Pi) or in any degraded case, both legs independently fall
        # back to `os.getcwd()`/`$(pwd)`, which is "usually agree", not a
        # guarantee. Passing the value explicitly collapses this to ONE
        # resolution, computed once, consumed everywhere -- the 1-argument
        # form is kept for backward compatibility (any other caller of this
        # CLI, and this module's own test suite) and still resolves exactly
        # as before.
        if len(rest) == 2:
            project_root = rest[1]
        else:
            project_root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        verdict = verify_tag_ancestor(tag, project_root)
        if verdict in (_ANCESTRY_ZERO_TAG, _ANCESTRY_ANCESTOR):
            return 0
        if verdict == _ANCESTRY_NOT_ANCESTOR:
            sys.stderr.write(
                f"verify-tag-ancestor: refusing {tag!r} as the release "
                "baseline -- it does not resolve to a commit reachable "
                "from HEAD. A sibling branch that diverged before this "
                "tag, an abandoned branch's stray push, or an unrelated "
                "orphan history sharing this series' prefix can still win "
                "the highest-SemVer scan even though this release's own "
                "history never contains it. This is never resolved by "
                "silently falling back to an older tag, reusing the tag "
                "namespace, or moving/deleting the tag -- remove the "
                "stray tag by hand (never retarget or delete a PUBLISHED "
                "one; see \"Recovering from a bad release\") or confirm "
                "the correct baseline before re-entering Pre-flight.\n")
            return 1
        sys.stderr.write(
            f"verify-tag-ancestor: could not resolve {tag!r} or HEAD to "
            "verify ancestry -- refusing rather than trusting an "
            "unverified baseline.\n")
        return 2

    if cmd == "notes-match" and len(rest) in (2, 4):
        tag, notes_path = rest[:2]
        policy, initial = (rest[2], rest[3] or None) if len(rest) == 4 else (
            "semver", None)
        if not _policy_declaration_valid(policy, initial):
            sys.stderr.write("notes-match: invalid policy declaration\n")
            return 2
        try:
            with open(notes_path, encoding="utf-8") as fh:
                notes_text = fh.read()
        except OSError:
            notes_text = ""
        except UnicodeError:
            sys.stderr.write("notes-match: notes file is not UTF-8\n")
            return 4
        return 0 if notes_heading_matches(
            notes_text, tag, policy, initial) else 1

    if cmd == "changelog-section" and len(rest) in (4, 6, 7):
        # Mechanical reconstruction of Phase 1's composed section, for
        # `resume_publish` -- see `changelog_section`'s docstring. Exit 0
        # with the section on stdout - 1 the changelog has no heading for
        # `<version>` (drift between $CHANGELOG and the tag, not a
        # bad-invocation) - 3 the repository/revision/path/blob cannot be
        # read safely - 4 a malformed/duplicate/invalidly-ordered changelog.
        # `revision` is resolved to a commit hash before the blob read, so a
        # current HEAD move or dirty/deleted working file cannot change the
        # notes selected for an already-composed tag.
        repo_root, revision, changelog_path, version = rest[:4]
        allow_absent_path = len(rest) == 7 and rest[6] == "--allow-absent-path"
        if len(rest) == 7 and not allow_absent_path:
            sys.stderr.write("changelog-section: invalid optional flag\n")
            return 2
        policy, initial = (rest[4], rest[5] or None) if len(rest) >= 6 else (
            "semver", None)
        if not _policy_declaration_valid(policy, initial):
            sys.stderr.write(
                "changelog-section: invalid policy declaration\n")
            return 2
        changelog_text, source_error = _committed_changelog_text(
            repo_root, revision, changelog_path)
        if source_error is not None:
            if (allow_absent_path
                    and source_error == "committed changelog path is absent"):
                sys.stderr.write(
                    f"changelog-section: no committed {changelog_path!r} "
                    "exists at the exact revision\n")
                return 1
            sys.stderr.write(
                f"changelog-section: cannot read committed "
                f"{changelog_path!r}: {source_error}\n")
            return 3
        section, status = _changelog_section_result(
            changelog_text, version, policy, initial)
        if status == _SECTION_ABSENT:
            sys.stderr.write(
                f"changelog-section: no '## [{version}]' heading in "
                f"committed {changelog_path!r}\n")
            return 1
        if status != _SECTION_OK:
            sys.stderr.write(
                f"changelog-section: committed {changelog_path!r} is "
                f"{status}; refusing ambiguous release notes\n")
            return 4
        # `sys.stdout.write` is text-mode: on Windows with no
        # PYTHONIOENCODING/PYTHONUTF8 set it encodes using the ambient
        # console codepage (cp1252, not UTF-8) AND translates `\n` to
        # `\r\n`. A changelog section legitimately contains an em-dash in
        # every heading (`## [X.Y.Z] — DATE`), so unlike backfill-detect's
        # deliberately-ASCII-only block (see its own comment on this exact
        # failure), this output cannot dodge the problem by staying ASCII.
        # Writing UTF-8 bytes straight to the binary buffer bypasses both
        # the codepage transcoding and the newline translation. `.buffer`
        # is absent on an `io.StringIO` (what a direct, in-process
        # `main(argv)` call under test redirects to) -- that caller already
        # gets the exact string back with no encoding step in between, so
        # falling back to plain `.write()` there is not a weaker code path,
        # it is the correct one for an object that was never bytes.
        out_buffer = getattr(sys.stdout, "buffer", None)
        if out_buffer is not None:
            out_buffer.write(section.encode("utf-8"))
        else:
            sys.stdout.write(section)
        return 0

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

    if cmd == "classify-window" and len(rest) in (0, 2):
        # stdin = `git log $WINDOW --format=%H%x00%s%x00%b%x00 --
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
        try:
            window_text = sys.stdin.read()
        except UnicodeDecodeError:
            sys.stderr.write(
                "classify-window: git log input is not UTF-8\n")
            return 4
        commits = parse_window_log(window_text)
        if commits is None:
            sys.stderr.write(
                "classify-window: malformed NUL-framed git log input\n")
            return 4
        reconciliations = {}
        published_shas = set()
        if rest:
            target, default_branch = rest
            targets_file = default_targets_path()
            project_root = os.path.dirname(os.path.dirname(targets_file))
            try:
                row = _resolve_target_row(target, targets_file)
                if row is None:
                    sys.stderr.write(f"unknown release target: {target}\n")
                    return 2
            except ReleaseTargetsError as exc:
                sys.stderr.write(
                    f"{type(exc).__name__}: could not load changelog "
                    f"reconciliations: {exc}\n")
                return _targets_error_exit_code(exc)

            if row.get("changelog_reconciliations") is not None:
                try:
                    branch_probe = subprocess.run(
                        [git_executable(), "check-ref-format", "--branch",
                         default_branch], cwd=project_root, capture_output=True,
                        text=True, timeout=30,
                        env=_sanitized_git_environment())
                except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                    sys.stderr.write(
                        f"classify-window: could not validate default branch: "
                        f"{exc}\n")
                    return 4
                if branch_probe.returncode != 0:
                    sys.stderr.write(
                        f"classify-window: invalid default branch "
                        f"{default_branch!r}\n")
                    return 4
                published_ref = f"refs/remotes/origin/{default_branch}"
                try:
                    published_probe = subprocess.run(
                        [git_executable(), "rev-parse", "--verify",
                         f"{published_ref}^{{commit}}"], cwd=project_root,
                        capture_output=True, text=True, timeout=30,
                        env=_sanitized_git_environment())
                except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                    sys.stderr.write(
                        f"classify-window: could not resolve published default "
                        f"branch: {exc}\n")
                    return 4
                published_commit = published_probe.stdout.strip()
                if (published_probe.returncode != 0
                        or re.fullmatch(
                            r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
                            published_commit) is None):
                    sys.stderr.write(
                        f"classify-window: could not resolve exact published "
                        f"ref {published_ref!r}\n")
                    return 4
                try:
                    reconciliations = _load_declared_changelog_reconciliations(
                        row, target, project_root, published_commit)
                except ReleaseTargetsError as exc:
                    sys.stderr.write(
                        f"{type(exc).__name__}: could not load changelog "
                        f"reconciliations: {exc}\n")
                    return _targets_error_exit_code(exc)

                window_shas = {
                    entry.get("sha") for entry in commits
                    if isinstance(entry, dict)
                }
                for sha in sorted(set(reconciliations).intersection(window_shas)):
                    try:
                        ancestor = subprocess.run(
                            [git_executable(), "merge-base", "--is-ancestor",
                             sha, published_commit],
                            cwd=project_root, capture_output=True, text=True,
                            timeout=30, env=_sanitized_git_environment())
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        sys.stderr.write(
                            f"classify-window: could not verify published "
                            f"commit {sha}: {exc}\n")
                        return 4
                    if ancestor.returncode == 0:
                        published_shas.add(sha)
                    elif ancestor.returncode != 1:
                        sys.stderr.write(
                            f"classify-window: could not verify {sha} against "
                            f"published ref {published_ref!r}: "
                            f"{ancestor.stderr.strip()}\n")
                        return 4

        window = classify_window(
            commits,
            reconciliations=reconciliations,
            published_shas=published_shas)
        print(window["bump"])
        for row in window["commits"]:
            print("[CLASSIFIED] " + json.dumps({
                "sha": row["sha"],
                "subject": row["subject"],
                "type": row["type"],
                "scope": row["scope"],
                "breaking": row["breaking"],
                "bump": row["bump"],
                "changelog": row["changelog"],
                "footer_reconciled": row["footer_reconciled"],
            }, sort_keys=True, separators=(",", ":")))
        for row in window["commits"]:
            if row["footer_reconciled"]:
                print(
                    f"[RECONCILED] {row['sha'][:7]} {row['subject']} :: "
                    f"{row['changelog']}")
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

    if cmd == "clean-tree-status" and len(rest) == 1:
        target = rest[0]
        try:
            rows = load_targets(default_targets_path())
        except ReleaseTargetsError as exc:
            sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            return _targets_error_exit_code(exc)
        row = next((item for item in rows if item["target"] == target), None)
        if row is None:
            sys.stderr.write(f"unknown release target: {target}\n")
            return 2
        project_root = os.path.dirname(
            os.path.dirname(default_targets_path())) or "."
        probe = release_tree_status(row, project_root)
        sys.stdout.write(probe.stdout)
        sys.stderr.write(probe.stderr)
        return probe.returncode

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
        # Exit codes: 0 all passed - 5 a command RAN and reported drift
        # (non-zero, not one of the could-not-run codes below) - 6 a
        # command exited 0 but MUTATED the tree - 7 a command's interpreter
        # or program itself could not be located/executed at all (#585
        # MEDIUM-2 / #584 MEDIUM-1: "could not run" is never "ran and
        # disagreed") - 8 the tree-state PROBE itself failed, so no verdict
        # about the declared commands exists at all (distinct from 6, which
        # means a command mutated the tree -- a probe failure means this
        # subcommand never got far enough to know) - 9 no POSIX-compatible
        # shell could be resolved to dispatch a declared row on Windows, so
        # NO declared command ran at all (#602: distinct from 7, which names
        # a specific command's own interpreter as unresolvable -- 9 means
        # the DISPATCH MECHANISM itself is unavailable, before any command
        # is even attempted) - 2 bad invocation or unknown target - 3/4 the
        # declared-file states, unchanged.
        #
        # PY env-var contract: every declared command below runs with
        # `PY` set in its environment to THIS process's own interpreter
        # (`sys.executable`), so a row may portably spell `"$PY"` instead
        # of a hardcoded `python3`/`python` (#583 MEDIUM-2 / #584 MEDIUM-3).
        # This convention now holds on Windows too (#602): the dispatch
        # below resolves a POSIX-compatible shell there instead of falling
        # through to `subprocess.run(shell=True)`'s default `cmd.exe`.
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

        # #602: resolve the POSIX-shell dispatch ONCE, before any declared
        # command runs (and before the tree-state baseline below, which a
        # row with no `pre-tag` commands at all does not even need this
        # resolution to reach). `_resolve_posix_shell()` itself returns None
        # unconditionally on a non-Windows host, so `posix_shell` stays None
        # and the dispatch below is byte-identical to the pre-#602 behavior
        # there. A row declaring no `pre-tag` commands never needs a shell
        # at all, so resolution -- and its failure mode -- is skipped
        # entirely rather than blocking a target that never runs anything.
        pre_tag_commands = row.get("pre_tag") or []
        posix_shell = (
            _resolve_posix_shell() if (os.name == "nt" and pre_tag_commands) else None)
        if os.name == "nt" and pre_tag_commands and posix_shell is None:
            # Exit 9, never 7 (which names a specific command's own
            # interpreter as unresolvable): this is the DISPATCH MECHANISM
            # itself being unavailable, before any declared command was even
            # attempted -- "could not run" one level up, the same way exit 8
            # is "the probe could not run" one level up from exit 6.
            sys.stderr.write(
                "run-pre-tag: COULD NOT RUN -- no POSIX-compatible shell "
                "could be resolved on this Windows host.\n"
                "  This is NOT drift. No declared command has run, so "
                "nothing was checked -- do not reconcile it as a check "
                "failure.\n"
                "  `subprocess.run(shell=True)` dispatches via `cmd.exe` on "
                "Windows, which cannot expand a row's `\"$PY\"` / `$VAR` "
                "syntax (#602), so this subcommand requires a POSIX shell "
                "to dispatch declared rows portably.\n"
                "  Remedy: install Git for Windows "
                "(https://git-scm.com/download/win), which ships "
                "`bash.exe`, or put an existing Git-for-Windows `bash.exe` "
                "on PATH. Then re-run. No release-edit discard is needed: "
                "nothing was checked, so there is nothing to undo.\n")
            return 9

        def _tree_state():
            """Snapshot tracked/untracked paths and index state without
            following links. Hash content so edits to already-dirty files
            and skip-worktree paths remain visible.
            """
            # Exclude only local governance scratch, not release payloads.
            scratch_pathspecs = [
                f":(exclude,top){path}"
                for path in governance_scratch_exclusions(row)
            ]
            git = git_executable()
            env = _sanitized_git_environment()
            try:
                probe = subprocess.run(
                    [git, "ls-files", "-z", "--cached",
                     "--others", "--exclude-standard", "--", ":/",
                     *scratch_pathspecs],
                    cwd=project_root, capture_output=True, timeout=30,
                    env=env)
                index_probe = subprocess.run(
                    [git, "ls-files", "-v", "--stage", "-z", "--", ":/",
                     *scratch_pathspecs],
                    cwd=project_root, capture_output=True, timeout=30,
                    env=env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return None, f"git file inventory failed: {exc}"
            if probe.returncode != 0:
                stderr = probe.stderr.decode("utf-8", errors="replace").strip()
                return None, (stderr or "git file inventory failed")
            if index_probe.returncode != 0:
                stderr = index_probe.stderr.decode("utf-8", errors="replace").strip()
                return None, (stderr or "git index inspection failed")
            index_state = {}
            for record in index_probe.stdout.split(b"\0"):
                if not record:
                    continue
                header, separator, raw_rel = record.partition(b"\t")
                if not separator:
                    return None, "git index inspection returned a malformed record"
                try:
                    rel = raw_rel.decode("utf-8")
                except UnicodeDecodeError:
                    return None, "git index inspection returned a non-UTF-8 path"
                index_state.setdefault(rel, []).append(header)
            state = {}
            for raw_rel in probe.stdout.split(b"\0"):
                if not raw_rel:
                    continue
                try:
                    rel = raw_rel.decode("utf-8")
                except UnicodeDecodeError:
                    return None, "git file inventory returned a non-UTF-8 path"
                absolute = os.path.join(project_root, *rel.split("/"))
                try:
                    mode = os.lstat(absolute).st_mode
                    if stat.S_ISLNK(mode):
                        digest = ("link", os.readlink(absolute))
                    elif stat.S_ISREG(mode):
                        hasher = hashlib.sha256()
                        with open(absolute, "rb") as fh:
                            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                                hasher.update(chunk)
                        digest = ("file", hasher.hexdigest())
                    else:
                        digest = ("other", stat.S_IFMT(mode))
                except OSError:
                    digest = ("absent-or-unreadable",)
                state[rel] = (digest, tuple(index_state.get(rel, ())))
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
            # Exit 8, never 6 (#584 residual / house rule: "could not run"
            # is never folded into "ran and disagreed", and the same holds
            # one level up for a PROBE that could not run at all). Exit 6
            # is a specific, actionable diagnosis -- "a command mutated the
            # tree" -- and this is not that: the probe failed before any
            # declared command even ran, so there is no verdict about the
            # commands to report at all, and exit 6's "fix the declaration"
            # remedy would misdirect an operator at the wrong problem.
            sys.stderr.write(
                f"run-pre-tag: the tree-state PROBE itself failed: {failure}\n"
                "  This is not a verdict about any declared command -- no "
                "command has run yet, so nothing has been checked or "
                    "mutated. Investigate why Git could not inventory this tree "
                "(not a git repository, no readable .git, etc.) before "
                "re-running.\n")
            return 8

        for command in pre_tag_commands:
            # flush=True: the subprocess writes to the same fds directly and
            # is not buffered, so without this the label lands AFTER the
            # output it labels and the log misattributes which command
            # produced what -- actively misleading in the one report an
            # operator reads to decide whether a release is safe.
            print(f"pre-tag: {command}", flush=True)
            # `PY` exported to the child's environment (#583 MEDIUM-2 / #584
            # MEDIUM-3): the interpreter-resolution convention the release
            # skill establishes for its OWN invocations stopped at the
            # skill's own commands -- a declared row is operator shell this
            # lane EXECUTES exactly like any other step, so a row hardcoding
            # `python3` fails on exactly the host the convention exists for.
            # `sys.executable` is THIS process's own resolved interpreter,
            # so a row may portably spell `"$PY"` instead.
            if posix_shell is not None:
                # #602: dispatch via the resolved POSIX shell's OWN `-c`
                # argv form (`shell=False`), never
                # `shell=True, executable=posix_shell`. CPython's Windows
                # `shell=True` path unconditionally builds
                # `<executable> /c "<command>"` -- cmd.exe-flag syntax --
                # regardless of what `executable` names, so passing
                # `executable=<bash.exe>` there would invoke
                # `bash.exe /c "command"`; `/c` is not a bash option (bash
                # options start with `-`), so bash would try to run a
                # nonexistent file literally named `/c` and fail with exit
                # 127 -- misdiagnosing EVERY row as could-not-run regardless
                # of whether the row itself is valid. Building the argv
                # ourselves is the only correct way to dispatch a
                # POSIX-syntax command string through a specific non-default
                # shell on Windows.
                proc = subprocess.run(
                    [posix_shell, "-c", command], shell=False, cwd=project_root,
                    env={**os.environ, "PY": sys.executable})
            else:
                proc = subprocess.run(
                    command, shell=True, cwd=project_root,
                    env={**os.environ, "PY": sys.executable})
            if _could_not_run(proc.returncode):
                # Exit 7, never 5 (#585 MEDIUM-2 / #584 MEDIUM-1): a command
                # whose interpreter or program itself could not be located
                # was never actually RUN, so nothing was checked and there
                # is no drift to reconcile -- the exit-5 remedy below is the
                # wrong diagnosis for this case and its "discard this run's
                # uncommitted release edits" step is unnecessary busywork,
                # since nothing the row asserts was ever evaluated.
                sys.stderr.write(
                    f"run-pre-tag: COULD NOT RUN -- {command!r} exited "
                    f"{proc.returncode} (interpreter or command not "
                    "found).\n"
                    "  This is NOT drift. The command's interpreter or "
                    "program itself could not be located, so it never ran "
                    "and nothing was checked -- do not reconcile it as a "
                    "check failure.\n"
                    "  Remedy: fix the interpreter this row names for THIS "
                    "host (a common cause is a row hardcoding a specific "
                    "interpreter, e.g. `python3`, on a host that has only "
                    "`python`) -- `\"$PY\"` (#601/#602) is the portable "
                    "spelling on every platform this dispatch supports. "
                    "Then re-run. No release-edit discard is needed: "
                    "nothing was checked, so there is nothing to undo.\n")
                return 7
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
                sys.stderr.write(
                    f"run-pre-tag: the tree-state PROBE itself failed after "
                    f"{command!r} ran: {failure}\n"
                    "  This is not a verdict about the command that just "
                    "ran -- the probe that would confirm or refute a "
                    "mutation could not complete, so no verdict about it "
                    "exists.\n")
                return 8
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

    if cmd == "version-greater" and len(rest) == 4:
        candidate, floor, policy, initial_version = rest
        initial = initial_version or None
        if policy == "semver" and initial is None:
            if semver_key(candidate) is None or semver_key(floor) is None:
                sys.stderr.write("version-greater: invalid semver comparison\n")
                return 2
        elif policy == "numeric-sequence":
            candidate_key = numeric_sequence_key(candidate, initial)
            initial_key = numeric_sequence_key(initial, initial)
            floor_key = (None if floor == NONE_SENTINEL
                         else numeric_sequence_key(floor, initial))
            if (candidate_key is None or initial_key is None
                    or (floor != NONE_SENTINEL and floor_key is None)
                    or candidate_key < initial_key):
                sys.stderr.write(
                    "version-greater: invalid numeric-sequence comparison\n")
                return 2
        else:
            sys.stderr.write("version-greater: invalid policy declaration\n")
            return 2
        return 0 if version_greater(candidate, floor, policy, initial) else 1

    if cmd == "apply-bump" and len(rest) == 2:
        # #585 MEDIUM-3: the one number that mattered was the only step
        # left to the eye. Step 4 had the operator "apply the step-2 bump
        # to `$BASE_VERSION`" by hand -- none of the other fifteen
        # subcommands does this arithmetic, and nothing downstream
        # re-derives it (a minor window mis-applied as a patch still passes
        # `semver-greater` and `check-manifests`, because both compare
        # against the same wrong value this step just wrote). This is the
        # sanctioned way to do it instead: exit 0 with the bumped version
        # on stdout, or exit 2 with nothing to stdout when `base` is not
        # plain SemVer or `word` is not exactly one of `major`/`minor`/
        # `patch` -- `none` included, deliberately: a caller must never
        # apply a non-bump, and this refuses rather than echoing `base`
        # back unchanged.
        base, word = rest
        result = apply_bump(base, word)
        if result is None:
            sys.stderr.write(
                f"apply-bump: cannot apply bump {word!r} to base {base!r}. "
                "`base` must be plain MAJOR.MINOR.PATCH SemVer (no "
                "pre-release or build metadata) and `word` must be exactly "
                "'major', 'minor', or 'patch' -- 'none' is deliberately "
                "refused here, since a caller must never apply a non-bump.\n")
            return 2
        print(result)
        return 0

    if cmd == "derive-version" and len(rest) == 4:
        base, word, policy, initial_version = rest
        result = derive_version(base, word, policy, initial_version or None)
        if result is None:
            sys.stderr.write(
                f"derive-version: cannot derive from {base!r} under policy "
                f"{policy!r} with initial-version {initial_version!r}\n")
            return 2
        print(result)
        return 0

    if cmd == "render-release-assets" and len(rest) >= 3:
        version, tag = rest[:2]
        rendered = render_release_assets(rest[2:], version, tag)
        if rendered is None:
            sys.stderr.write(
                "render-release-assets: invalid or duplicate asset template\n")
            return 2
        for name in rendered:
            print(name)
        return 0

    if cmd == "verify-release-assets" and len(rest) >= 2:
        directory, names = rest[0], rest[1:]
        if (any(not _safe_release_asset_name(name) for name in names)
                or len(set(names)) != len(names)):
            sys.stderr.write(
                "verify-release-assets: invalid or duplicate asset name\n")
            return 2
        verified = verify_release_asset_inventory(directory, names)
        if verified is None:
            sys.stderr.write(
                "verify-release-assets: local inventory does not exactly "
                "match the declared non-empty regular files\n")
            return 1
        for path in verified:
            print(path)
        return 0

    if cmd == "dates-match" and len(rest) in (2, 4):
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
        paths = rest[:2]
        policy, initial = (rest[2], rest[3] or None) if len(rest) == 4 else (
            "semver", None)
        if not _policy_declaration_valid(policy, initial):
            sys.stderr.write("dates-match: invalid policy declaration\n")
            return 2
        texts = []
        for path in paths:
            try:
                with open(path, encoding="utf-8") as fh:
                    texts.append(fh.read())
            except OSError:
                texts.append("")
            except UnicodeError:
                sys.stderr.write(
                    f"dates-match: input file {path!r} is not UTF-8\n")
                return 4
        return 0 if release_dates_consistent(
            texts[0], texts[1], policy, initial) else 1

    if cmd == "classify" and len(rest) == 6:
        if rest[0] not in ("true", "false") or rest[5] not in (
                "true", "false"):
            sys.stderr.write(
                "classify: boolean evidence must be exact lowercase "
                "true or false\n")
            return 2
        as_bool = lambda s: s == "true"
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

    if cmd == "validate-reconciliations" and len(rest) == 2:
        target, ledger_path = rest
        try:
            if os.path.islink(ledger_path) or not os.path.isfile(ledger_path):
                raise ChangelogReconciliationError(
                    "ledger must be one regular file")
            if os.path.getsize(ledger_path) > 1024 * 1024:
                raise ChangelogReconciliationError(
                    "ledger exceeds the 1 MiB limit")
            with open(ledger_path, "rb") as handle:
                raw = handle.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ChangelogReconciliationError(
                    "ledger exceeds the 1 MiB limit")
            try:
                text = raw.decode("utf-8")
            except UnicodeError as exc:
                raise ChangelogReconciliationError(
                    f"ledger is not UTF-8: {exc}") from None
            parse_changelog_reconciliations(text, target)
        except (OSError, ChangelogReconciliationError) as exc:
            sys.stderr.write(
                f"ChangelogReconciliationError: could not validate "
                f"{ledger_path!r}: {exc}\n")
            return 4
        return 0

    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    # This CLI is consumed as a line-record protocol by POSIX shells on every
    # supported host.  Native Windows text stdout otherwise translates each
    # ``\n`` to ``\r\n``; Git Bash's ``read -r`` removes the newline but keeps
    # the carriage return, corrupting pathspecs, target names, and asset paths.
    # Force the wire format to LF once at the executable boundary.  Imported
    # library calls retain their caller-owned stream configuration.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
    sys.exit(main(sys.argv[1:]))
