#!/usr/bin/env python3
# codeArbiter - protected-state registry: which project-state files are
# guarded, and under what POLICY (issue #564, workstream B1).
#
# Three consumers need materially different write semantics, so a flat
# marker-gated registry (the H-11 ADR-authoring pattern) is wrong for two of
# them. Each registry entry will carry exactly one of:
#
#   marker-gated  - a Write/Edit/shell mutation is admitted only under a
#                   fresh authoring marker (the H-11 pattern: a
#                   `<stem>-authoring` marker under .codearbiter/.markers/,
#                   minted immediately before the write and removed at lane
#                   exit). First consumer: release-targets.md.
#   helper-only   - Write, Edit, and shell naming the file are hard-blocked
#                   with NO marker path at all. The sanctioned helper's own
#                   Python file I/O is the only route - its argv never
#                   lexically names the file, so it is invisible to all three
#                   flanks by construction. Consumer: open-tasks.md via
#                   taskwrite.py.
#   append-only   - mutation is admitted only via the helper's append verb.
#                   Consumer: done-tasks.md via the archive verb.
#
# THE REGISTRY IS THE DELIVERABLE, NOT THE ENTRIES (spec B1). This module is
# generic machinery over a policy-tagged path->policy map; it enrolls NO
# consumer itself. release-targets.md, open-tasks.md, and done-tasks.md are
# registered by their own later tasks (B-13/B-14/B-15) so this module never
# special-cases its first consumer.
#
# Library design invariants (mirrors every other _*lib.py, coding-standards.md):
#   - Zero side effects at import time - no git calls, no file I/O on import.
#   - Pure functions, testable with synthetic input; filesystem access will be
#     isolated to `_hooklib.marker_fresh`, the one named reader this module
#     calls (reused rather than re-implemented, per house rule).
#
# Public API (filled in task-by-task; see history for the T-01/T-04/T-05
# slices):
#   ProtectedPolicy                    enum: MARKER_GATED / HELPER_ONLY /
#                                       APPEND_ONLY, str-valued
#                                       ("marker-gated"/"helper-only"/
#                                       "append-only"). Constructing from an
#                                       unknown value raises ValueError
#                                       (internal error, not user input).
#   REGISTRY -> dict[str, ProtectedPolicy]   the live path->policy map.
#                                       Starts EMPTY here; consumers are
#                                       registered by their own tasks, never
#                                       hardcoded in this module.
#   lookup_policy(rel_path, registry=None) -> ProtectedPolicy | None
#                                       the policy registered for a
#                                       repo-relative path. Both the query
#                                       path and every registry key are
#                                       separator-normalized before
#                                       comparison, or None if the path
#                                       carries no policy. `registry` defaults
#                                       to the module-level REGISTRY; a caller
#                                       (a test, or a future flank) may pass a
#                                       synthetic dict instead. Reached only
#                                       through `classify_protected`
#                                       (_protectedlib.py) in the wired path -
#                                       never called directly with an ad hoc
#                                       dict, which would drop the
#                                       raw-and-realpath symlink coverage that
#                                       dispatch provides.
#   resolve_registered_path(fpath, root, registry=None)
#                                       -> (rel_path, ProtectedPolicy) | (None,
#                                       None). The T-06/T-07 flank helper: once
#                                       classify_protected has already reported
#                                       "state" for `fpath`, this resolves
#                                       WHICH registered path matched and WHICH
#                                       policy it carries, trying both the raw
#                                       normalized path and its
#                                       realpath-resolved repo-relative form -
#                                       the SAME two forms classify_protected
#                                       itself tries (#162) - so the flank
#                                       resolves the identical entry
#                                       classify_protected saw rather than
#                                       re-deriving membership through an
#                                       independent check.
#   MARKER_FRESHNESS_MINUTES -> int    the H-11 marker window (30). Matches
#                                       the ADR-authoring gate's value by
#                                       convention, not a shared import - see
#                                       the constant's own comment for the
#                                       five independent declarations.
#   marker_name_for(rel_path) -> str   a marker basename for a marker-gated
#                                       path, encoding the path BELOW the
#                                       repo's .codearbiter/ project-state
#                                       root (not just the basename) so
#                                       same-named files in different
#                                       sub-directories never share a marker
#                                       (e.g. ".codearbiter/release-targets.md"
#                                       -> "release-targets-authoring", the
#                                       pinned literal for the sole current
#                                       consumer; "docs/release-targets.md"
#                                       -> "docs__release-targets-authoring").
#                                       Always a single flat, traversal-safe
#                                       filename; degenerate input (empty,
#                                       None, a bare directory) never raises
#                                       and never collides with a real path's
#                                       derived name.
#   marker_gated_write_admitted(rel_path, root,
#                                minutes=MARKER_FRESHNESS_MINUTES) -> bool
#                                       True iff a fresh `<stem>-authoring`
#                                       marker exists under
#                                       .codearbiter/.markers/ for `rel_path`.
#                                       False on an absent marker AND on a
#                                       stale one - both cases delegate
#                                       entirely to _hooklib.marker_fresh, so
#                                       there is exactly one freshness
#                                       implementation in the codebase. For
#                                       `marker-gated` only; the flank wiring
#                                       (pre-write.py, pre-edit.py,
#                                       _bashguardlib.py per-class dispatch)
#                                       is hook ID H-22 (H-21 is taken),
#                                       built in later tasks of this slice -
#                                       this function supplies the check the
#                                       flanks will share, and does not
#                                       itself call block()/remind().

from __future__ import annotations

import os
from enum import Enum

from _hooklib import marker_fresh
from _pathnorm import norm_path, raw_repo_rel, repo_rel


class ProtectedPolicy(str, Enum):
    """The three write-admission policies a protected-state registry entry
    can carry (spec B1). str-valued so a member compares equal to its plain
    string value (`ProtectedPolicy.MARKER_GATED == "marker-gated"`) and
    round-trips through JSON without a second mapping layer.

    Interpolation caveat: use `.value`, not the member itself. `str(member)` /
    an f-string / `%s` on a bare member yields `"ProtectedPolicy.MARKER_GATED"`
    on Python 3.11+ (and the plain value on <=3.10) - the mixin does not make
    those two forms agree across interpreters. Only `.value` (or the
    already-proven `==` against a plain string) is the stable contract.

    Constructing an unknown value (`ProtectedPolicy("bogus")`) raises
    ValueError via the stdlib Enum machinery - deliberately NOT caught here.
    An unrecognized policy string reaching this constructor is a typo'd
    registry entry - an internal programming error, not malformed user
    input - so it is correct to raise rather than degrade."""

    MARKER_GATED = "marker-gated"
    HELPER_ONLY = "helper-only"
    APPEND_ONLY = "append-only"


# The live protected-state registry: repo-relative path (separator-
# normalized) -> ProtectedPolicy. Deliberately EMPTY here - B1 (this module)
# ships the registry mechanism, not entries. release-targets.md/
# open-tasks.md/done-tasks.md are added by their own later tasks
# (B-13/B-14/B-15), each a one-line entry, which is the whole point of
# building this as a registry instead of a per-file hook branch.
REGISTRY: dict[str, ProtectedPolicy] = {
    # B-13/T-33 (spec 2.6). The declared release-target file carries
    # per-row `pre-tag`, `rebuild`, and `generate` shell commands that
    # `/ca:release` executes before composing a tag, on a lane that later
    # holds `contents: write`. Planting a command in it is therefore a
    # code-execution path, which is why writing it costs a fresh authoring
    # marker rather than being an ordinary edit (ADR-0024, DECISION-0035).
    #
    # MARKER_GATED, not HELPER_ONLY: unlike `open-tasks.md` -- whose sole
    # blessed writer is `taskwrite.py`, writing through Python file I/O
    # whose argv never names the file and is therefore invisible to every
    # flank by construction -- this file has THREE sanctioned authors
    # (`context-creation`, the release skill's back-fill lane, and its
    # row-edit path), all of which mint the marker. A hard block would
    # leave them no route; the marker is the route.
    ".codearbiter/release-targets.md": ProtectedPolicy.MARKER_GATED,
}


def _canon(rel_path):
    """Canonical comparison form of a repo-relative path: separator-
    normalized (`norm_path`), then whitespace-stripped, `./`-prefix-
    stripped (repeatable — "././x" too), doubled-slash-collapsed,
    trailing-slash-stripped, and finally case-folded.

    Applied to BOTH sides of every `lookup_policy` comparison (the query
    path AND every registry key) so a spelling difference on either side
    degrades to "still matches" rather than "silently matches nothing" —
    the same "a malformed key degrades the way a malformed query path does"
    principle `lookup_policy`'s own docstring states, extended to cover the
    specific spellings its docstring already promised but the OLD
    norm_path-only comparison silently missed (#564 follow-up, finding F2):
    a leading `./`, a trailing slash, a doubled slash, and a leading space.

    Case-folded — not merely separator-normalized — for a second,
    independent reason (finding F1): `_bashguardlib.py`'s H-22 shell-flank
    regexes compile with `re.I` (`_state_write_res`), so a case-sensitive
    equality check here would let the two flanks disagree on whether a
    differently-cased spelling of a registered path is protected. On a
    case-preserving-but-insensitive filesystem (default macOS/APFS,
    Windows/NTFS) that disagreement is a live fail-open: `_protectedlib.
    classify_protected` resolves through `os.path.realpath`, which does
    NOT canonicalize case for an EXISTING path on a case-insensitive mount
    (posixpath.realpath never folds case at all; even `nt.realpath`, which
    does resolve an existing file's on-disk case, cannot help a NOT-YET-
    created file — exactly the Write that creates a protected-state file
    for the first time) — so `Write(".codearbiter/Open-Tasks.md")` could
    reach this equality check with a case that never gets folded away
    before comparison. This module deliberately picks ONE fixed rule,
    case-INSENSITIVE, GLOBALLY, rather than "whatever this host's
    filesystem happens to do": matching host behavior is not obviously
    right either (it varies per platform AND per volume on the same
    platform), and a fixed global rule is the only option `_bashguardlib.py`
    can mirror without itself inspecting the filesystem. Choosing
    case-INSENSITIVE (not case-sensitive) only WIDENS what H-22 protects —
    consistent with this codebase's "ambiguity resolves CLOSED" stance
    (module comment, `_bashguardlib.py`) — at the cost of a same-directory
    file whose name differs from a registered path ONLY by case (e.g. a
    genuinely different `OPEN-TASKS.MD`) being treated as protected too; a
    registry entry choosing a name that collides with a real sibling file
    under a case change is expected to be rare enough that this is judged
    the right trade."""
    p = norm_path(rel_path).strip()
    while p.startswith("./"):
        p = p[2:]
    while "//" in p:
        p = p.replace("//", "/")
    p = p.rstrip("/")
    return p.lower()


def lookup_policy(rel_path, registry=None):
    """The ProtectedPolicy registered for `rel_path`, or None if it carries
    no policy. Both `rel_path` and every registry key are canonicalized
    (`_canon`, above) before comparison — separator-normalized, `./`/
    doubled-slash/trailing-slash/leading-space tolerant, and
    case-INSENSITIVE (deliberately, globally — see `_canon`'s docstring for
    why) — so a Windows backslash path, a `./`-prefixed or trailing-slash
    query, or a differently-cased spelling all match a registry entry, AND
    a registry entry that was itself typo'd any of those ways still matches
    rather than silently protecting nothing - a malformed *key* degrades the
    same way a malformed query path does; only a malformed *policy* (see
    ProtectedPolicy) is an internal error worth raising on.

    `registry` defaults to the module-level REGISTRY; a test (or a future
    caller) may pass a synthetic dict instead, which is what keeps this
    function generic machinery rather than something wired to a specific
    consumer set. This module must be reached through `classify_protected`
    (`_protectedlib.py`), which runs every classifier against both the raw
    and realpath-resolved forms of a path - a flank that calls
    `lookup_policy` directly with its own ad hoc dict re-opens the symlink
    alias this module does not itself guard against."""
    if registry is None:
        registry = REGISTRY
    normalized = _canon(rel_path)
    for key, policy in registry.items():
        if _canon(key) == normalized:
            return policy
    return None


def resolve_registered_path(fpath, root, registry=None):
    """The `(rel_path, policy)` pair a Write/Edit/shell target resolves to,
    once `_protectedlib.classify_protected` has already reported "state" for
    it - or `(None, None)` if it turns out to carry no registry entry after
    all (a caller that checks this before ever consulting
    classify_protected, or a stale class set).

    Tries BOTH the raw (symlink-unresolved) repo-relative form
    (`raw_repo_rel`) and the realpath-resolved repo-relative form
    (`repo_rel`), in that order - the SAME two-form symlink-safety property
    (#162) classify_protected's four legacy classes get automatically from
    running a regex `.search()` over the raw normalized path text.

    That automatic coverage does NOT transfer for free to this module's
    EQUALITY-based lookup (finding F3, #564 follow-up): `norm_path(fpath)` -
    almost always an ABSOLUTE path, since every host sends one - is never
    equal to a repo-relative registry key, so trying it as the "raw" leg was
    inert (it could never match anything). Worse, it made symlink coverage
    the WRONG WAY ROUND versus the other four classes: when the REGISTERED
    PATH ITSELF is a symlink pointing somewhere unregistered,
    `os.path.realpath` resolves the ONLY spelling a host actually sends
    (the absolute path) straight through the symlink to that unregistered
    target, and the dead raw leg supplied no alternative route back to the
    registered name — so the write was silently ADMITTED, the opposite of
    the legacy classes' behavior in the equivalent scenario (a regex
    `.search()` still matches the raw path text regardless of where it
    realpaths to). `raw_repo_rel` fixes this: computed by pure lexical
    arithmetic against `root` (no `os.path.realpath` call), it still names
    the registered entry syntactically even when the path is a symlink, so
    that spelling now resolves correctly too - restoring the SAME
    "protected either way you spell it" guarantee the legacy classes
    already had; the realpath leg still exists for the mirror-image case
    (a symlinked DIRECTORY whose visible path lacks the registered prefix
    but resolves into it).

    So a flank reaching this function resolves the IDENTICAL entry
    classify_protected saw, rather than re-deriving membership through an
    independent check. That independent-check shape is exactly what #564's
    design forbids ("no second, parallel lookup") - this function only ever
    RESOLVES what classify_protected already decided; it never decides
    membership on its own account.

    `registry` defaults to the module-level REGISTRY, matching
    `lookup_policy`'s own parameter shape, for the same reason: a test (or a
    future caller) may pass a synthetic dict."""
    for p in (raw_repo_rel(fpath, root), repo_rel(fpath, root)):
        if not p:
            continue
        policy = lookup_policy(p, registry)
        if policy is not None:
            return p, policy
    return None, None


# The H-11 authoring-marker freshness window, matching the existing
# ADR-authoring gate's value by convention, NOT by a shared import:
# pre-write.py, pre-edit.py, _bashguardlib.py, and git-enforce.py each
# independently hardcode `30` for the same marker shape, and this is a fifth,
# equally independent, declaration. Widening this constant does not widen
# theirs, and widening theirs does not widen this one - there is no single
# source of truth for the window's value across those five sites today.
MARKER_FRESHNESS_MINUTES = 30


def marker_name_for(rel_path):
    """The `<...>-authoring` marker basename for a marker-gated `rel_path`
    (e.g. "release-targets.md" -> "release-targets-authoring") - the pattern
    named in the sprint's pre-run dispositions for every future marker-gated
    consumer, not just the first.

    Encodes the normalized relative path below the repo's single
    `.codearbiter/` project-state root, not just the basename, so two
    registry entries that merely share a filename in different
    sub-directories (".codearbiter/release-targets.md" vs
    ".codearbiter/nested/release-targets.md", or "a/x.md" vs "b/x.yml") mint
    two distinct markers rather than one shared one - minting the marker for
    one would otherwise admit a write to the other. A single leading
    `.codearbiter` segment is dropped before encoding rather than treated as
    disambiguating structure: every registry entry lives there by
    construction (this module's whole domain), so keeping it out of the
    encoding is what leaves the pinned literal for the sole current
    marker-gated consumer unchanged (`.codearbiter/release-targets.md` ->
    `release-targets-authoring`) while still telling apart two DIFFERENT
    sub-directories. A literal `-` inside a directory segment is escaped
    (doubled) before segments are joined with `-`, so a raw `-` in the
    encoded name always marks a genuine directory boundary - this closes the
    same-string collision a naive join would allow between, e.g., a
    "prefix-name" directory and a "prefix"/"name" nested pair. `.`, `..`, and
    empty segments are dropped before encoding (not merely trusted to
    `os.path.basename`), so a stray `./` prefix, a trailing slash, or a
    crafted `../` segment can never reach the returned name; the result is
    always a single flat filename, never a path, so it stays contained under
    .codearbiter/.markers/. Never raises: an empty/None `rel_path`, or one
    with no real path segment (".", "..", "/"), has no directory or file to
    encode and degrades to the fixed sentinel "-authoring" - a name no real
    (non-empty) rel_path can ever produce, since a real segment always
    contributes a non-empty stem.

    Residual (accepted): the escaping above closes hyphen/segment-boundary
    ambiguity but is not a fully bijective encoding against adversarially
    crafted underscore runs (e.g. a directory literally named "a_" holding
    "_b.md" can alias "a" holding "__b.md"). The registry's entries are a
    small, curated, human-authored set (spec B1/B2), not attacker-chosen
    directory names, so this is judged out of proportion to close fully
    here."""
    parts = [p for p in norm_path(rel_path).split("/") if p not in ("", ".", "..")]
    if not parts:
        return "-authoring"
    if parts[0] == ".codearbiter" and len(parts) > 1:
        parts = parts[1:]
    stem = os.path.splitext(parts[-1])[0]
    dir_tag = "-".join(p.replace("-", "--") for p in parts[:-1])
    encoded = f"{dir_tag}__{stem}" if dir_tag else stem
    return f"{encoded}-authoring"


def marker_gated_write_admitted(rel_path, root, minutes=MARKER_FRESHNESS_MINUTES):
    """True iff a Write/Edit/shell mutation of a `marker-gated` `rel_path` is
    admitted: a `<stem>-authoring` marker exists under
    .codearbiter/.markers/ and was touched within `minutes` (the H-11
    pattern). False on an absent marker AND on a stale one - both cases
    delegate entirely to _hooklib.marker_fresh (the one filesystem reader
    this module calls), so there is exactly one freshness implementation in
    the codebase."""
    marker = os.path.join(root, ".codearbiter", ".markers", marker_name_for(rel_path))
    return marker_fresh(marker, minutes)
