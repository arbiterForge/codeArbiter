#!/usr/bin/env python3
# codeArbiter - the protected-path classifiers: which repo paths are append-only
# audit logs (H-05), ADR decision files (H-11), the activation manifest, and the
# gate-marker directory.
#
# Extracted from _hooklib (issue #321, architecture-002) as slice 2. Measured the
# same way slice 1 was: the cluster referenced exactly ONE symbol from the rest
# of _hooklib (repo_rel, which moved to the _pathnorm floor because it
# references no module symbol at all and the remaining slices need it too), and
# NOTHING in the rest of _hooklib referenced the cluster. A one-way edge with no
# back-reference is what makes a slice safe to move without touching a consumer.
#
# WHY THESE BELONG TOGETHER: they answer one question - "what class of protected
# thing is this path?" - and the guards branch on the answer as a set.
# classify_protected returns EVERY class a path hits, which is load-bearing:
# #528/#529 showed that adding decision-log.md to the audit set while leaving it
# in the decisions set still blocked, because pre-write.py checks the classes
# independently. Splitting these across modules would let one classification
# move without the others and reopen exactly that.
#
# _hooklib re-exports every name below, so no consumer changed and the
# pre-existing hook suites prove parity without moving.

from __future__ import annotations

import re

from _pathnorm import norm_path, repo_rel


# Append-only audit logs (H-05) and ADR-decisions paths (H-11) — centralized
# here (architecture-004) so the three pre-* hooks import ONE definition instead
# of re-encoding the regex inline (the exact drift this module exists to
# prevent: adding sprint-log.md once meant hand-editing every copy). Same home,
# same rationale, as CRYPTO_RE/SECRET_RE/MIGRATION_DEFAULT_GLOBS.
#
# AUDIT_LOG_NAMES is the bare filename alternation; pre-bash.py composes its
# shell LOG_NAMES from it, and AUDIT_LOG_RE anchors it under .codearbiter/ for
# the Write/Edit file-path guards. DECISIONS_DIR_RE is the separator-tolerant
# decisions directory token; pre-bash.py composes its shell DECISIONS from it,
# and DECISIONS_PATH_RE extends it to a full ADR file path. `[\\/]+` matches the
# norm_path'd `/` as well as a raw backslash, so both the file-path and shell
# flanks derive from one source.
#
# gate-events.log (observability-001, #186) joins this set: it is the durable,
# mechanical BLOCK/REMIND/WARN sink block()/remind()/warn() append to below —
# an append-only audit artifact exactly like the other three, so it gets the
# SAME H-05 tool-call protection (Write/Edit + shell) for free via this one
# alternation, with no separate guard to maintain. Note this protects it only
# from Write/Edit/Bash TOOL CALLS; the hooks' own os-level `open(..., "a")`
# append (below) is plain file I/O, never a tool call, so H-05 never gates it.
#
# AUDIT_LOG_BASENAMES is the single authoritative list of bare filenames — the
# ONE place a new audit log gets added. pre-bash.py's H-05 shell guard needs
# these as plain strings too (a cheap `n in cmd` substring pre-filter before
# running the regexes below), so it imports this tuple directly instead of
# re-deriving/hand-copying the name set (the exact drift this centralization
# exists to prevent — a filter that silently skips a future audit log because
# its literal name was never added to a second, hand-maintained copy).
# AUDIT_LOG_NAMES is built FROM this tuple (re.escape'd, alternated) — behavior
# is unchanged from the prior hand-written pattern (same four literal
# filenames, same (?:...) grouping), only the source of truth moved.
AUDIT_LOG_FLAT_BASENAMES = ("overrides.log", "triage.log", "gate-events.log", "sprint-log.md")
# #528: the SMARTS arbitration log is an append-only audit artifact that happens
# to sit under decisions/ for filing reasons. It is NOT an ADR, and governing it
# as one was a live deadlock: `decision-variance` Phase 4 is REQUIRED to append
# to it, H-11 refused every write without the /adr authoring marker, and only
# decision-lifecycle arms that marker. So a SMARTS arbitration outside an /adr
# session made a decision it could not record. Its own format doc states H-05's
# rule verbatim — "strictly append-only … to supersede, append a new entry" — so
# H-05 is the correct guard: append freely, never rewrite.
#
# It is listed separately from AUDIT_LOG_BASENAMES because those are anchored
# directly under .codearbiter/ and this one is nested a level deeper. Both halves
# of the reclassification are load-bearing: adding it here WITHOUT removing it
# from the H-11 set below leaves the append blocked, because classify_protected
# reports every class a path hits and pre-write checks them independently.
DECISION_LOG_BASENAME = "decision-log.md"
DECISION_LOG_RE = re.compile(
    r"\.codearbiter[\\/]+decisions[\\/]+" + re.escape(DECISION_LOG_BASENAME) + r"$"
)
# AUDIT_LOG_BASENAMES stays the SINGLE AUTHORITATIVE BASENAME LIST, and the
# arbitration log is in it. _bashguardlib's H-05 shell check pre-filters with
# `any(n in cmd for n in AUDIT_LOG_BASENAMES)` precisely so a newly added audit
# log cannot silently skip the shell flank — adding the name only to the regex
# alternation below would sail past that pre-filter and leave the log deletable
# from the shell. (Caught by test_hook_guards.py, which the comment on that
# pre-filter predicted verbatim.)
AUDIT_LOG_BASENAMES = AUDIT_LOG_FLAT_BASENAMES + (DECISION_LOG_BASENAME,)
AUDIT_LOG_NAMES = "(?:" + "|".join(re.escape(n) for n in AUDIT_LOG_BASENAMES) + ")"
# The path anchor stays scoped to the FLAT logs — those sit directly under
# .codearbiter/, the arbitration log one level deeper — so is_audit_log() tests
# both patterns rather than loosening this one into matching any nesting.
AUDIT_LOG_RE = re.compile(
    r"\.codearbiter/" + "(?:" + "|".join(re.escape(n) for n in AUDIT_LOG_FLAT_BASENAMES) + ")" + r"$"
)
DECISIONS_DIR_RE = r"\.codearbiter[\\/]+decisions"
DECISIONS_PATH_RE = re.compile(DECISIONS_DIR_RE + r"[\\/]+.+\.md$")

# The activation file (#159) and the gate-marker store (#160). CONTEXT.md is the
# master switch every hook gates on via arbiter_active(); .markers/ holds the
# gate-pass tokens (security-gate-passed, migration-gate-passed,
# adr-authoring-active). Both were writable project state with no Write/Edit
# guard — the token strings are centralized here beside the audit-log/decisions
# sets so the pre-* hooks import ONE definition (same anti-drift rationale).
CONTEXT_MD_RE = re.compile(r"\.codearbiter/CONTEXT\.md$")
MARKERS_RE = re.compile(r"\.codearbiter/\.markers(?:/|$)")
# The two load-bearing gate-pass markers a commit gate consumes (H-09b/H-10b,
# H-14). Their bare filenames feed pre-bash.py's shell flank — these are NEVER
# legitimately shell-written (the sanctioned producers are the python
# security-pass.py / migration-pass.py helpers), unlike adr-authoring-active
# which /adr legitimately `touch`es.
GATE_MARKER_NAMES = r"(?:security-gate-passed|migration-gate-passed)"


def is_audit_log(rel):
    """True iff `rel` is one of the append-only .codearbiter audit logs
    (overrides.log, triage.log, sprint-log.md, gate-events.log) or the SMARTS
    arbitration log decisions/decision-log.md (#528) — the H-05 guard set."""
    n = norm_path(rel)
    return bool(AUDIT_LOG_RE.search(n) or DECISION_LOG_RE.search(n))


def is_tail_append(current, old, new):
    """True iff an Edit's (old_string, new_string) pair is a verifiable,
    TAIL-ANCHORED pure append against `current` (the file's REAL on-disk
    content) — the H-05 guard (reliability-003, #172).

    `new.startswith(old)` alone is not sufficient: `old` could be any interior
    line that happens to be a prefix of `new`, which inserts content BETWEEN
    existing lines rather than appending at the end. This requires TWO things:
    `current` must literally END with `old` (old_string is the file's actual
    trailing content, not just some substring elsewhere), and `new` must
    extend `old`. An empty `old` is never a valid append — every string
    "ends with" the empty string, so the tail-anchor check would trivially
    pass and reopen the migration-003 empty-old_string hole this closes.

    `old` must also occur EXACTLY ONCE in `current`: a non-unique old_string
    that happens to also match the tail is not self-evidently an append — this
    keeps the guard correct on its own terms rather than depending on the Edit
    tool's own (client-side, not re-verified here) uniqueness enforcement for
    a non-replace_all Edit."""
    if not old:
        return False
    if current.count(old) != 1:
        return False
    return current.endswith(old) and new.startswith(old)


def is_decisions_path(rel):
    """True iff `rel` is a `.md` ADR anywhere under .codearbiter/decisions/ —
    the H-11 guard set (a non-numbered draft or a nested path still counts).

    decisions/decision-log.md is the ONE exception (#528): it is the append-only
    arbitration log, not immutable ADR history, and is governed by H-05 instead.
    The carve-out is exactly one path wide and anchored — `old-decision-log.md`
    and a nested `sub/decision-log.md` remain ADRs, so a near-miss filename
    cannot launder itself out of the marker gate. (`decision-log.md.bak` is in
    NEITHER set: it does not end in `.md`, so it was never an H-11 path either.)"""
    n = norm_path(rel)
    if DECISION_LOG_RE.search(n):
        return False
    return bool(DECISIONS_PATH_RE.search(n))


def is_context_md(rel):
    """True iff `rel` is the .codearbiter/CONTEXT.md activation file (#159) —
    the master switch arbiter_active() reads. Guarded so it can't be flipped to
    `arbiter: disabled` (or corrupted) to make every enforcement hook dormant."""
    return bool(CONTEXT_MD_RE.search(norm_path(rel)))


def is_marker_path(rel):
    """True iff `rel` is anywhere under .codearbiter/.markers/ (#160) — the
    gate-pass token store. Load-bearing markers turn a BLOCK into an allow, so a
    hand-written marker must not be admitted by the Write/Edit tools."""
    return bool(MARKERS_RE.search(norm_path(rel)))


def classify_protected(fpath, root):
    """The set of protected classes a Write/Edit `fpath` targets, resolving
    symlinks (#162). Each classifier runs against BOTH the raw normalized path
    AND the realpath-resolved repo-relative form: a symlink alias whose visible
    path lacks `.codearbiter/` still realpaths back inside the repo, so an alias
    can no longer launder a write past the guard. Centralized so pre-write.py and
    pre-edit.py apply the identical symlink-safe check to every class (H-05,
    H-11, #159 CONTEXT.md, #160 markers) instead of re-encoding it twice.

    Classes: "audit", "decisions", "context", "marker". repo_rel() returns "" for
    a target outside the repo (which cannot be a `.codearbiter` path), so that
    flank is simply skipped."""
    hits = set()
    for p in (norm_path(fpath), repo_rel(fpath, root)):
        if not p:
            continue
        if is_audit_log(p):
            hits.add("audit")
        if is_decisions_path(p):
            hits.add("decisions")
        if is_context_md(p):
            hits.add("context")
        if is_marker_path(p):
            hits.add("marker")
    return hits
