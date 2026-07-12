#!/usr/bin/env python3
# codeArbiter — read-inject helpers for file-scoped just-in-time context injection.
#
# Builds the hook response dict and (in later tasks) the file->knowledge map,
# budget assembler, and freshness gate for the PreToolUse:Read hook (pre-read.py).
# This module holds all testable pure logic; pre-read.py is the thin entry point.
#
# Design invariants (mirroring _provenancelib.py / _taskboardlib.py):
#   - Stdlib only; no third-party imports, ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O on import.
#   - Pure functions, testable with synthetic input; isolate any filesystem
#     access to explicitly-named reader functions (added in later tasks).
#   - Never raise on malformed input — degrade gracefully (this runs on the
#     PreToolUse hook path; a crash must never block a Read).
#
# Public API:
#   allow_output(additional_context) -> dict   build the hookSpecificOutput dict
#                                              that allows the Read and injects
#                                              additional_context into the model.
#                                              None is coerced to "".
#   token_estimate(s) -> int                  token proxy: ceil(len(s) / 4).
#                                              Empty string or None -> 0. Never raises.
#   assemble_context(pointers, budget=150)    assemble the additionalContext payload
#     -> str                                  from an ordered pointer list; result is
#                                              <= budget tokens; excess is truncated at
#                                              the cap with a trailing "…" marker.
#   security_pointer(path) -> dict | None     tier 1: pointer to security-controls.md
#                                              for a security-entry path (auth/middleware/
#                                              jwt token match), else None. Pure; never
#                                              raises. No provenance data consulted.
#   accepted_adr_index(root) -> list          tier 2 FS reader: scan
#                                              <root>/.codearbiter/decisions/ for
#                                              [0-9]+-.+\.md; parse frontmatter (cap 26
#                                              lines); return [{"adr", "title", "globs"}]
#                                              for ADRs with status==accepted (case-
#                                              insensitive) AND a non-empty governs: list.
#                                              Missing dir -> []. Malformed file -> skip.
#                                              Never raises. No cache.
#   adr_pointers(rel, index) -> list          tier 2 pure matcher: for each index entry
#                                              whose globs fnmatch-match rel, produce a
#                                              pointer dict {"text", "tier": "decisions"}.
#                                              [] when nothing matches, index is empty, or
#                                              input is malformed. Pure; never raises.
#   parse_spec_governs(text) -> list          tier 3 PURE: find the FIRST **Governs:**
#                                              line in a spec's text; return its comma-
#                                              separated globs (stripped, empties dropped).
#                                              No such line -> []. Case-insensitive on
#                                              "Governs". Never raises.
#   approved_spec_index(root) -> list         tier 3 FS reader: scan
#                                              <root>/.codearbiter/specs/*.md; keep specs
#                                              with non-empty Governs AND **Status:**
#                                              beginning with "approved" (case-insensitive;
#                                              e.g. "approved (2026-06-26)" qualifies,
#                                              "draft (pending approval)" does not).
#                                              Status may be inline after · separators.
#                                              Returns [{"spec": "<stem>", "globs": [...]}].
#                                              Missing dir -> []. Malformed file -> skip.
#                                              Never raises. No cache.
#   spec_pointers(rel, index) -> list         tier 3 PURE matcher: for each index entry
#                                              whose any glob fnmatch-matches rel, produce
#                                              {"text": "spec <slug> governs this file —
#                                              implement to its acceptance criteria.",
#                                              "tier": "specs"}. [] when nothing matches,
#                                              index is empty, or input is malformed.
#                                              Pure; never raises.
#   provenance_pointer(rel, provenance,       tier 4 PURE comparator: freshness-gated
#     current_hashes) -> list                 pointers from provenance entries for rel.
#                                              Does NOT call git or batch_hash — caller
#                                              supplies precomputed current_hashes so a
#                                              non-matching Read pays no git cost (AC-11).
#                                              Emits one pointer per FRESH entry (stored
#                                              hash non-null AND rel in current_hashes AND
#                                              hashes match). SUPPRESSES diverged/
#                                              unverifiable/null-hash entries. [] when
#                                              provenance is empty/{} or no path match.
#                                              Pointer: {"text": "<doc>.md notes …",
#                                              "tier": "standards"}. Never raises.
#   governing_docs(rel, index,               compose all four tiers in priority order:
#     runner=None) -> list                   security-controls > decisions > specs >
#                                              standards.  index is the prebuilt dict
#                                              {"adr":[…], "spec":[…], "provenance":{…}}.
#                                              Tier-4 (standards) applies the LAZY hashing
#                                              gate (AC-11): batch_hash is called ONCE only
#                                              when rel appears as a provenance entry path;
#                                              a non-provenance Read makes ZERO git calls.
#                                              [] on any error.  Never raises.
#   marker_path(root, session_id, rel)        dedup (AC-09): return the absolute path of
#     -> str                                  the per-(session,file) marker under
#                                              <root>/.codearbiter/.markers/.  Filename
#                                              derived from sha256(session_id+"\0"+rel)
#                                              for filesystem-safety.  PURE — no I/O.
#                                              Never raises; coerces inputs to str.
#   already_injected(root,                    dedup (AC-09): True iff the marker file
#     session_id, rel) -> bool                exists.  On ANY error returns False —
#                                              degrades toward injecting, never toward
#                                              wrongly suppressing.  Never raises.
#   record_injection(root,                    dedup (AC-09): create the marker file
#     session_id, rel) -> None                (creates .markers/ dir if needed; atomic
#                                              .tmp + os.replace write).  All errors
#                                              swallowed — a failed write must never
#                                              break the hook.  Never raises.
#   build_index(root) -> dict                 assemble the prebuilt index governing_docs
#                                              consumes: {"adr": accepted_adr_index(root),
#                                              "spec": approved_spec_index(root),
#                                              "provenance": load_provenance_dir(…)}.
#                                              Caches adr+spec in <root>/.codearbiter/
#                                              .markers/readinject-index-cache.json keyed
#                                              on max mtime of decisions/ and specs/ dirs
#                                              and their .md files; cache error degrades to
#                                              fresh build; provenance always fresh; missing
#                                              dirs → empty sub-structures.  Never raises.
#   compute_injection(root,                   end-to-end orchestrator for AC-09/10/11:
#     session_id, rel,                        self-read guard → dedup → build_index →
#     runner=None) -> str                     governing_docs → assemble_context →
#                                              record_injection.  Returns the
#                                              additionalContext string (possibly "").
#                                              A non-matching Read makes ZERO runner calls
#                                              (AC-11 cost guarantee).  Never raises.

import fnmatch
import hashlib
import json
import math
import os
import re

import _provenancelib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOOK_EVENT_NAME = "PreToolUse"
_PERMISSION_ALLOW = "allow"

# ---------------------------------------------------------------------------
# Output builder (AC-03)
# ---------------------------------------------------------------------------


def allow_output(additional_context):
    """Build the hookSpecificOutput dict that always allows the Read.

    Returns exactly:
      {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                               "permissionDecision": "allow",
                               "additionalContext": <additional_context>}}

    `additional_context` is the string injected as additionalContext.  None is
    coerced to "" so the dict is always well-formed.  The Read is NEVER denied
    by this function — permissionDecision is always "allow".

    Pure; never raises.
    """
    if additional_context is None:
        additional_context = ""
    return {
        "hookSpecificOutput": {
            "hookEventName": _HOOK_EVENT_NAME,
            "permissionDecision": _PERMISSION_ALLOW,
            "additionalContext": additional_context,
        }
    }


# ---------------------------------------------------------------------------
# Token budget helpers (AC-08)
# ---------------------------------------------------------------------------

_ELLIPSIS = "…"  # U+2026 HORIZONTAL ELLIPSIS, len == 1


def token_estimate(s):
    """Token proxy: ceil(len(s) / 4).

    Returns the estimated token count for string s.  Empty string or None
    returns 0.  Any other value that has a len() uses that length; anything
    that raises returns 0.  Pure; never raises.
    """
    try:
        if not s:
            return 0
        return math.ceil(len(s) / 4)
    except Exception:
        return 0


def assemble_context(pointers, budget=150):
    """Assemble the additionalContext payload from an ordered list of pointers.

    Each pointer must be a dict with a "text" key whose value is a str.
    Pointers with a missing, None, or non-string "text" are silently skipped.
    Non-dict entries in the list are skipped.  A non-list `pointers` argument
    degrades to "".

    Pointers arrive ALREADY in priority order (caller T-07 orders them
    security-controls > decisions > specs > standards).  Order is preserved —
    pointers are included from the front.

    The returned string's token_estimate must be <= budget.  When the full
    joined text exceeds budget, whole pointers are included from the front
    while they fit, then the accumulated text is truncated at budget*4 chars
    (the proxy ceiling) and the ellipsis marker "…" is appended so the
    payload is never silently cut.

    Single-oversized-pointer edge case (T-10 fix): when even the first
    (highest-priority) pointer's text alone exceeds budget, the greedy
    whole-pointer loop accumulates nothing.  Rather than returning a bare
    "…" marker (which silently discards the governing note), the function
    truncates the first valid pointer's text to `budget*4 - len("…")` chars
    and appends the ellipsis — so real content is always preserved.  The
    result's token_estimate is still <= budget.

    Empty list or all-skipped -> "".  Pure; never raises.
    """
    try:
        if not isinstance(pointers, list):
            return ""

        # Collect valid texts in the given priority order.
        valid_texts = []
        for p in pointers:
            if not isinstance(p, dict):
                continue
            text = p.get("text")
            if not isinstance(text, str):
                continue
            valid_texts.append(text)

        if not valid_texts:
            return ""

        # Try the full join first — the common, cheap path.
        full_text = "\n".join(valid_texts)
        if token_estimate(full_text) <= budget:
            return full_text

        # Over budget: greedily include whole pointers from the front.
        accumulated = ""
        for text in valid_texts:
            candidate = text if not accumulated else accumulated + "\n" + text
            if token_estimate(candidate) <= budget:
                accumulated = candidate
            else:
                break  # stop — preserve priority order, no skipping

        # Truncate to leave room for the ellipsis marker, then append it.
        # Single-oversized-pointer edge case: when nothing fit as a whole
        # pointer (first pointer alone exceeds budget), fall back to
        # truncating the first valid pointer's text — so real content is
        # preserved and the result is never a bare ellipsis marker.  The
        # final string is at most budget*4 chars, guaranteeing
        # token_estimate(result) <= budget.
        max_text_len = budget * 4 - len(_ELLIPSIS)
        if not accumulated:
            accumulated = valid_texts[0]
        result = accumulated[:max_text_len] + _ELLIPSIS
        return result

    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Tier 1 — security-controls pointer (AC-04)
# ---------------------------------------------------------------------------

# Concise pointer text for tier 1.  Kept well under the 150-token budget so it
# leaves headroom for tiers 2–4 when assembled by governing_docs (T-07).
_SECURITY_CONTROLS_TEXT = (
    "security-controls.md governs this file — consult it for auth, crypto,"
    " and secret-handling constraints."
)


def security_pointer(path):
    """Return a pointer dict for a security-entry path (tier 1), or None.

    Fires ONLY for security-entry paths — files whose tokenised, lowercased
    normalised path contains an exact member of _provenancelib._SECURITY_ENTRY_TOKENS
    ({"auth", "middleware", "jwt"}).  Manifests (package.json), CI yaml, and
    migration files are NOT security-entry paths and return None here even though
    classify_source() returns True for them.

    Reuses _provenancelib._SECURITY_ENTRY_TOKENS and _SECURITY_TOKEN_SPLIT_RE
    directly so this predicate stays in lockstep with the shipped classifier —
    a change to either constant propagates here automatically.

    Pointer dict shape (STABLE — must match the assembler T-07):
      {"text": <concise ≤1-sentence string naming security-controls.md>,
       "tier": "security-controls"}

    Pure; never raises.  None or garbage path → None.  No provenance data is
    consulted; no git calls are made (tier 1 is provenance-free).
    """
    try:
        if not path:
            return None
        norm = str(path).replace("\\", "/")
        # Apply the same whole-token rule as classify_source's security-entry
        # branch: split on separators + camelCase boundaries, lowercase, then
        # test for exact membership in _SECURITY_ENTRY_TOKENS.  This prevents
        # substring false-positives such as "author" (contains "auth") or
        # "AuthorCard" (camelCase token "Author").
        path_tokens = [
            t.lower()
            for t in _provenancelib._SECURITY_TOKEN_SPLIT_RE.split(norm)
            if t
        ]
        if not _provenancelib._SECURITY_ENTRY_TOKENS.intersection(path_tokens):
            return None
        return {
            "text": _SECURITY_CONTROLS_TEXT,
            "tier": "security-controls",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 2 — accepted-ADR index + pointer (AC-05)
# ---------------------------------------------------------------------------

_ADR_FILE_RE = re.compile(r"^[0-9]+-.+\.md$")
_ADR_GOVERNS_RE = re.compile(r"^governs:\s*(.+)$", re.I)
_ADR_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.I)
_ADR_STATUS_RE = re.compile(r"^status:\s*(.+)$", re.I)

# Maximum number of file lines to scan for frontmatter (mirrors post-write-edit.py).
_ADR_SCAN_LIMIT = 26  # i > 25 breaks → lines 0-25 inclusive


def accepted_adr_index(root):
    """Tier-2 filesystem reader.  Scan <root>/.codearbiter/decisions/ for ADR files.

    Returns a list of {"adr": "<numeric id>", "title": "<title>", "globs": [<glob>, …]}
    for every ADR that satisfies BOTH conditions:
      - governs: is present and non-empty (one or more comma-separated globs).
      - status: is exactly "accepted" (case-insensitive).

    STRICT status filter: "superseded", "rejected", "draft", "proposed", missing,
    or any other value are ALL excluded.  This is intentionally stricter than
    post-write-edit.py's governs_index which keeps anything not in
    {superseded, rejected}.

    Missing decisions dir → [].  Malformed / unreadable file → skip, never raise.
    No mtime cache; each call re-scans (correctness over speed; caching is optional
    per spec and deferred until benchmarked).

    Pure filesystem access is isolated here; adr_pointers is the pure matcher.
    Never raises.
    """
    try:
        ddir = os.path.join(str(root), ".codearbiter", "decisions")
        if not os.path.isdir(ddir):
            return []
        files = [f for f in os.listdir(ddir) if _ADR_FILE_RE.match(f)]
        if not files:
            return []
        index = []
        for fn in files:
            title, status, globs = fn, "", []
            try:
                with open(
                    os.path.join(ddir, fn), encoding="utf-8", errors="replace"
                ) as fh:
                    for i, ln in enumerate(fh):
                        if i >= _ADR_SCAN_LIMIT:
                            break
                        stripped = ln.strip()
                        m = _ADR_GOVERNS_RE.match(stripped)
                        if m:
                            globs = [
                                g.strip()
                                for g in m.group(1).split(",")
                                if g.strip()
                            ]
                            continue
                        m = _ADR_TITLE_RE.match(stripped)
                        if m:
                            title = m.group(1).strip()
                            continue
                        m = _ADR_STATUS_RE.match(stripped)
                        if m:
                            status = m.group(1).strip().lower()
            except Exception:  # noqa: BLE001 — skip unreadable/malformed files
                continue
            # ACCEPTED ONLY — stricter than post-write-edit.py governs_index.
            if globs and status == "accepted":
                adr = fn.split("-")[0]
                index.append({"adr": adr, "title": title, "globs": globs})
        return index
    except Exception:  # noqa: BLE001
        return []


def adr_pointers(rel, index):
    """Tier-2 pure matcher.  Return pointer dicts for accepted ADRs governing `rel`.

    `rel` is a repo-relative path string.  `index` is the output of
    accepted_adr_index.  For each index entry whose any glob fnmatch-matches
    `rel`, produce:
      {"text": "ADR-<id> (<title>) governs this file — do not contradict it;
                route changes via /ca:reconcile or /ca:adr.",
       "tier": "decisions"}

    The text stays well under the 150-token budget.  Returns [] when nothing
    matches, when index is empty, or when either argument is malformed/None.
    Pure; no filesystem access; never raises.
    """
    try:
        if not rel or not isinstance(index, list):
            return []
        result = []
        for entry in index:
            try:
                globs = entry.get("globs", [])
                if any(fnmatch.fnmatch(rel, g) for g in globs):
                    adr_id = entry.get("adr", "")
                    title = entry.get("title", "")
                    text = (
                        "ADR-{} ({}) governs this file"
                        " — do not contradict it;"
                        " route changes via /ca:reconcile or /ca:adr.".format(
                            adr_id, title
                        )
                    )
                    result.append({"text": text, "tier": "decisions"})
            except Exception:  # noqa: BLE001 — skip malformed entry
                continue
        return result
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Tier 3 — approved-spec index + pointer (AC-06, AC-13)
# ---------------------------------------------------------------------------

# U+00B7 MIDDLE DOT — the · separator between inline header fields in spec files.
# e.g. **Slug:** `x` · **Lane:** full · **Status:** approved (2026-06-26)
_SPEC_SEPARATOR = "·"

# Match the first **Governs:** line (case-insensitive on the word); capture the
# rest of the line as the comma-separated glob list.
_SPEC_GOVERNS_RE = re.compile(r"\*\*governs:\*\*\s*(.+)", re.I)

# Match **Status:** anywhere on a line (inline support); capture everything up
# to the next · separator or end-of-line.  The separator character is embedded
# via string concatenation so that · is expanded by Python, while the raw
# string keeps the regex metacharacter escapes intact.
_SPEC_STATUS_RE = re.compile(
    r"\*\*status:\*\*\s*([^" + _SPEC_SEPARATOR + r"\n]+)", re.I
)


def parse_spec_governs(text):
    """Return the glob list from the FIRST **Governs:** line in `text`.

    Scans `text` line by line; returns a list of stripped, non-empty glob
    strings from the first matching line.  No such line → [].  Non-string
    input → [].  Case-insensitive on "Governs".  Pure; never raises.
    """
    try:
        if not isinstance(text, str):
            return []
        for line in text.splitlines():
            m = _SPEC_GOVERNS_RE.search(line)
            if m:
                raw = m.group(1)
                return [g.strip() for g in raw.split(",") if g.strip()]
        return []
    except Exception:  # noqa: BLE001
        return []


def approved_spec_index(root):
    """Tier-3 filesystem reader.  Scan <root>/.codearbiter/specs/ for approved specs.

    For each *.md file: reads its text, extracts globs via parse_spec_governs,
    and extracts the status by searching for **Status:** anywhere in the text
    (inline · separator support) then capturing the value until the next ·
    or end-of-line, lowercased+stripped.

    Keeps a spec ONLY when BOTH conditions hold:
      - non-empty globs (has a **Governs:** line), AND
      - status begins with "approved" (case-insensitive) — e.g.
        "approved (2026-06-26)" qualifies; "draft (pending approval)" does NOT.

    Returns [{"spec": "<filename stem>", "globs": [<glob>, ...]}, ...].
    Missing specs dir → [].  Malformed/unreadable file → skip, never raise.
    No mtime cache; each call re-scans.  Never raises.
    """
    try:
        sdir = os.path.join(str(root), ".codearbiter", "specs")
        if not os.path.isdir(sdir):
            return []
        files = [f for f in os.listdir(sdir) if f.endswith(".md")]
        if not files:
            return []
        index = []
        for fn in files:
            try:
                with open(
                    os.path.join(sdir, fn), encoding="utf-8", errors="replace"
                ) as fh:
                    text = fh.read()
                globs = parse_spec_governs(text)
                if not globs:
                    continue
                m = _SPEC_STATUS_RE.search(text)
                if not m:
                    continue
                status = m.group(1).strip().lower()
                if not status.startswith("approved"):
                    continue
                stem = os.path.splitext(fn)[0]
                index.append({"spec": stem, "globs": globs})
            except Exception:  # noqa: BLE001 — skip malformed/unreadable files
                continue
        return index
    except Exception:  # noqa: BLE001
        return []


def spec_pointers(rel, index):
    """Tier-3 pure matcher.  Return pointer dicts for approved specs governing `rel`.

    `rel` is a repo-relative path string.  `index` is the output of
    approved_spec_index.  For each index entry whose any glob fnmatch-matches
    `rel`, produce:
      {"text": "spec <slug> governs this file — implement to its acceptance criteria.",
       "tier": "specs"}

    The text stays well under the 150-token budget.  Returns [] when nothing
    matches, when index is empty, or when either argument is malformed/None.
    Pure; no filesystem access; never raises.
    """
    try:
        if not rel or not isinstance(index, list):
            return []
        result = []
        for entry in index:
            try:
                globs = entry.get("globs", [])
                if any(fnmatch.fnmatch(rel, g) for g in globs):
                    slug = entry.get("spec", "")
                    text = (
                        "spec {} governs this file"
                        " — implement to its acceptance criteria.".format(slug)
                    )
                    result.append({"text": text, "tier": "specs"})
            except Exception:  # noqa: BLE001 — skip malformed entry
                continue
        return result
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Tier 4 — provenance freshness-gated pointer (AC-07)
# ---------------------------------------------------------------------------


def provenance_pointer(rel, provenance, current_hashes):
    """Tier-4 pure comparator.  Freshness-gated pointers from provenance entries.

    PURE — does NOT call git or batch_hash.  The caller (a later task) computes
    current_hashes via _provenancelib.batch_hash ONLY for matched paths, so that
    a non-matching Read pays zero git cost (AC-11).  This function just consumes
    the precomputed hashes.

    rel             — repo-relative path being read.
    provenance      — {doc_name: record} map (same shape _provenancelib produces).
                      May be {} — tier 4 is dormant until a re-scout backfills
                      .provenance/ (the live state of this repo today).
                      Non-dict → [].
    current_hashes  — {path: git_oid} for paths the caller already hashed.
                      Non-dict → [].

    FRESHNESS GATE (the heart of AC-07):
      - Find every entry across all docs whose path == rel.
      - For each such entry: emit a pointer ONLY when ALL THREE hold:
          (a) entry["hash"] is non-null, AND
          (b) rel is present in current_hashes, AND
          (c) current_hashes[rel] == entry["hash"]  (FRESH)
      - SUPPRESS (emit nothing for that entry) when:
          - stored hash is None/null  (unverifiable by design)
          - rel absent from current_hashes  (caller chose not to hash this path)
          - current_hashes[rel] != stored hash  (DIVERGED — stale note is worse
            than none; drift system already nudges separately)

    Pointer shape (stable contract):
      {"text": "<doc>.md notes (lines L-M): <claim>", "tier": "standards"}
      If the first claim has no "lines" key:
      {"text": "<doc>.md notes: <claim>", "tier": "standards"}
      Uses the FIRST claim in entry["claims"].  Long texts are truncated at the
      150-token budget (same proxy as token_estimate: ceil(len/4)) with a
      trailing "…" marker so the payload is never silently cut.

    Returns [] when provenance is empty/malformed, no entry's path matches rel,
    or all matching entries are suppressed.  Malformed record/entry/None → skip
    it, never raise.  Non-dict inputs → [].  Pure; never raises.
    """
    try:
        if not isinstance(provenance, dict) or not isinstance(current_hashes, dict):
            return []
        if not rel or not provenance:
            return []

        result = []
        for doc_name, record in provenance.items():
            try:
                if not isinstance(record, dict):
                    continue
                entries = record.get("entries")
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    try:
                        if not isinstance(entry, dict):
                            continue
                        if entry.get("path") != rel:
                            continue

                        stored_hash = entry.get("hash")
                        # SUPPRESS: null stored hash — cannot verify.
                        if stored_hash is None:
                            continue
                        # SUPPRESS: rel absent from current_hashes — unverifiable.
                        if rel not in current_hashes:
                            continue
                        # SUPPRESS: hash diverged — stale note is worse than none.
                        if current_hashes[rel] != stored_hash:
                            continue

                        # FRESH — build pointer from the first claim.
                        claims = entry.get("claims")
                        if not isinstance(claims, list) or not claims:
                            continue
                        first_claim = claims[0]
                        if not isinstance(first_claim, dict):
                            continue
                        claim_text = first_claim.get("claim", "")
                        if not isinstance(claim_text, str):
                            try:
                                claim_text = str(claim_text)
                            except Exception:
                                claim_text = ""
                        lines_range = first_claim.get("lines")

                        # Assemble pointer text; include lines range when present.
                        doc_part = "{}.md".format(doc_name)
                        if lines_range:
                            text = "{} notes (lines {}): {}".format(
                                doc_part, lines_range, claim_text
                            )
                        else:
                            text = "{} notes: {}".format(doc_part, claim_text)

                        # Enforce the 150-token budget; truncate with ellipsis marker
                        # so the payload is never silently cut (mirrors assemble_context).
                        if token_estimate(text) > 150:
                            max_text_len = 150 * 4 - len(_ELLIPSIS)
                            text = text[:max_text_len] + _ELLIPSIS

                        result.append({"text": text, "tier": "standards"})
                    except Exception:  # noqa: BLE001 — skip malformed entry
                        continue
            except Exception:  # noqa: BLE001 — skip malformed record
                continue

        return result
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Four-tier composer (T-07 / AC-04/05/06/08/11)
# ---------------------------------------------------------------------------


def governing_docs(rel, index, runner=None):
    """Return an ordered list of pointer dicts for rel — four-tier composition.

    Composes the four knowledge tiers in the PRIORITY ORDER the budget assembler
    relies on (security-controls > decisions > specs > standards):

      1. security_pointer(rel)                         tier "security-controls"
      2. adr_pointers(rel, index["adr"])               tier "decisions"
      3. spec_pointers(rel, index["spec"])             tier "specs"
      4. provenance_pointer(rel, …, current_hashes)    tier "standards"
         — ONLY when rel appears as a provenance entry path (AC-11 lazy gate).

    Parameters
    ----------
    rel     : repo-relative path string being read.
    index   : prebuilt dict with the STABLE shape produced by T-09:
                {"adr":       [{adr, title, globs}, …],
                 "spec":      [{spec, globs}, …],
                 "provenance": {doc_name: record, …}}
              Missing sub-keys degrade to their empty defaults.
    runner  : injectable git runner for batch_hash; contract:
                runner(args, stdin_text) -> str
              Default None (batch_hash uses _default_hash_runner).

    Tier-4 LAZY hashing gate (AC-11)
    ---------------------------------
    Before calling batch_hash, a cheap dict/list walk collects all 'path' values
    from every provenance record's 'entries' list into a set.  If rel is NOT in
    that set, tier 4 is SKIPPED ENTIRELY — no batch_hash call, zero git calls.
    If rel IS in that set, batch_hash([rel], runner) is called ONCE to obtain
    current_hashes, then provenance_pointer applies the freshness gate.

    Returns
    -------
    list of pointer dicts (each has 'text': str and 'tier': str), in priority
    order.  [] when nothing matches.  [] on any error.  Never raises.
    """
    try:
        result = []

        # Tier 1: security-controls — pure; never raises.
        sec = security_pointer(rel)
        if sec is not None:
            result.append(sec)

        # Safely extract index sub-maps; degrade on missing/wrong-type values.
        if isinstance(index, dict):
            adr_index = index.get("adr") or []
            spec_index = index.get("spec") or []
            provenance = index.get("provenance") or {}
        else:
            adr_index = []
            spec_index = []
            provenance = {}

        # Tier 2: decisions (accepted ADRs) — pure; never raises.
        result.extend(adr_pointers(rel, adr_index))

        # Tier 3: specs (approved specs) — pure; never raises.
        result.extend(spec_pointers(rel, spec_index))

        # Tier 4: standards (provenance freshness gate) — lazy hashing (AC-11).
        #
        # Step A: cheap dict/list walk to build the set of all provenance entry
        # paths.  This is git-free.  A non-provenance Read exits here with zero
        # git calls.
        entry_paths = set()
        if isinstance(provenance, dict):
            for record in provenance.values():
                try:
                    if not isinstance(record, dict):
                        continue
                    entries = record.get("entries")
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        try:
                            if isinstance(entry, dict):
                                p = entry.get("path")
                                if p:
                                    entry_paths.add(p)
                        except Exception:  # noqa: BLE001
                            continue
                except Exception:  # noqa: BLE001
                    continue

        # Step B: only call batch_hash when rel is a known provenance entry path.
        # Absence from entry_paths → SKIP; zero git calls.
        if rel and rel in entry_paths:
            current_hashes = _provenancelib.batch_hash([rel], runner)
            result.extend(provenance_pointer(rel, provenance, current_hashes))

        return result

    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Dedup gate — per-(session, file) marker (AC-09)
# ---------------------------------------------------------------------------


def marker_path(root, session_id, rel):
    """Return the absolute path of the dedup marker for (session_id, rel).

    The marker lives under <root>/.codearbiter/.markers/ with a filename
    derived from sha256(str(session_id) + "\\0" + str(rel)).hexdigest().  The
    null-byte separator ensures ('ab', 'c') and ('a', 'bc') hash to different
    filenames.

    PURE — no filesystem access of any kind.  Inputs are coerced to str so any
    type is accepted.  Never raises; on the (essentially impossible) error path,
    returns a fallback path whose last segment is 'readinject-error.marker'
    which will not match any normally-written marker.
    """
    try:
        digest = hashlib.sha256(
            (str(session_id) + "\0" + str(rel)).encode("utf-8")
        ).hexdigest()
        return os.path.join(
            str(root),
            ".codearbiter",
            ".markers",
            "readinject-{}.marker".format(digest),
        )
    except Exception:  # noqa: BLE001
        return os.path.join(
            str(root), ".codearbiter", ".markers", "readinject-error.marker"
        )


def already_injected(root, session_id, rel):
    """Return True iff the dedup marker for (session_id, rel) exists on disk.

    On ANY error (bad path, permission error, FS error) returns False —
    degrades toward injecting again, never toward wrongly suppressing an
    injection.  Never raises.
    """
    try:
        return os.path.isfile(marker_path(root, session_id, rel))
    except Exception:  # noqa: BLE001
        return False


def record_injection(root, session_id, rel):
    """Create the dedup marker for (session_id, rel), making .markers/ if needed.

    Uses an atomic .tmp + os.replace write: a crash between the open() and the
    rename never leaves a half-written marker at the target path.  The marker
    content is an empty string; only its existence is tested by already_injected.

    All errors are silently swallowed — a failed marker write must never break
    the hook.  Worst case: the marker is absent and the same (session, file)
    pair is injected again on the next Read.  Never raises.
    """
    try:
        path = marker_path(root, session_id, rel)
        marker_dir = os.path.dirname(path)
        os.makedirs(marker_dir, exist_ok=True)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("")
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            try:
                os.remove(tmp)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Index builder with mtime caching (T-09 / AC-11)
# ---------------------------------------------------------------------------

_INDEX_CACHE_FILENAME = "readinject-index-cache.json"


def _index_stamp(root):
    """Compute a max-mtime float stamp covering decisions/ and specs/ dirs + .md files.

    Includes the directory mtime (changes on file add/remove) AND the mtime of
    every .md file inside each directory (changes on file edits).  This catches
    all three mutation kinds: add, remove, and modify.

    Returns 0.0 when neither directory exists (absence sentinel — a cache keyed
    on 0.0 is safe to reuse while neither dir is present).  Never raises.
    """
    mtimes = []
    try:
        for subdir in ("decisions", "specs"):
            ddir = os.path.join(str(root), ".codearbiter", subdir)
            try:
                if not os.path.isdir(ddir):
                    continue
                try:
                    mtimes.append(os.path.getmtime(ddir))
                except Exception:  # noqa: BLE001
                    pass
                try:
                    for fname in os.listdir(ddir):
                        if fname.endswith(".md"):
                            try:
                                mtimes.append(
                                    os.path.getmtime(os.path.join(ddir, fname))
                                )
                            except Exception:  # noqa: BLE001
                                pass
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return max(mtimes) if mtimes else 0.0


def build_index(root):
    """Assemble the prebuilt index dict that governing_docs consumes.

    Returns:
      {"adr":        accepted_adr_index(root),
       "spec":       approved_spec_index(root),
       "provenance": load_provenance_dir(<root>/.codearbiter/.provenance)}

    CACHING (batch-2 review finding): the hook fires on every PreToolUse:Read,
    so this function MUST NOT re-scan decisions/ + specs/ from disk on every
    call.  The 'adr' and 'spec' index lists are cached in:
      <root>/.codearbiter/.markers/readinject-index-cache.json
    keyed on a stamp = max mtime of the decisions/ and specs/ directories and
    their .md files (same technique governs_index uses in post-write-edit.py).
    On a cache hit (stamp unchanged) the cached lists are reused; on a miss the
    lists are rebuilt and the cache is rewritten atomically (.tmp + os.replace).

    Any cache read/write error degrades to a fresh uncached build — MUST NOT
    raise and MUST NOT prevent correct results.  Cache is an optimization only.

    'provenance' is always loaded fresh each call (it is small; no cache needed).

    Missing directories → empty sub-lists/maps.  Never raises.
    """
    try:
        stamp = _index_stamp(root)
        cache_path = os.path.join(
            str(root), ".codearbiter", ".markers", _INDEX_CACHE_FILENAME
        )

        # --- Cache hit path ---
        try:
            with open(cache_path, encoding="utf-8") as _fh:
                _cached = json.load(_fh)
            if _cached.get("stamp") == stamp:
                _adr = _cached.get("adr", [])
                _spec = _cached.get("spec", [])
                _prov_dir = os.path.join(
                    str(root), ".codearbiter", ".provenance"
                )
                _provenance = _provenancelib.load_provenance_dir(_prov_dir)
                return {"adr": _adr, "spec": _spec, "provenance": _provenance}
        except Exception:  # noqa: BLE001 — absent / corrupt cache; rebuild
            pass

        # --- Cache miss: rebuild both indexes ---
        adr = accepted_adr_index(root)
        spec_list = approved_spec_index(root)

        # Write the cache atomically (.tmp + os.replace).
        # Guard: only write when cache_path is absolute — prevents creating
        # directories relative to the CWD when root is a garbage/relative value.
        # Any failure is swallowed — cache is an optimization, never required.
        if os.path.isabs(cache_path):
            try:
                _cache_dir = os.path.dirname(cache_path)
                os.makedirs(_cache_dir, exist_ok=True)
                _tmp = cache_path + ".tmp"
                with open(_tmp, "w", encoding="utf-8") as _fh:
                    json.dump({"stamp": stamp, "adr": adr, "spec": spec_list}, _fh)
                os.replace(_tmp, cache_path)
            except Exception:  # noqa: BLE001 — cache write failure is acceptable
                pass

        prov_dir = os.path.join(str(root), ".codearbiter", ".provenance")
        provenance = _provenancelib.load_provenance_dir(prov_dir)
        return {"adr": adr, "spec": spec_list, "provenance": provenance}
    except Exception:  # noqa: BLE001
        return {"adr": [], "spec": [], "provenance": {}}


# ---------------------------------------------------------------------------
# End-to-end orchestrator (T-09 / AC-09/10/11)
# ---------------------------------------------------------------------------


def compute_injection(root, session_id, rel, runner=None):
    """End-to-end orchestrator for file-scoped JIT context injection.

    Returns the additionalContext string (possibly "") that the hook sets as
    hookSpecificOutput.additionalContext.  Steps in order:

    1. Self-read guard (AC-10): if rel's first path segment is '.codearbiter'
       (after backslash → forward-slash normalisation), return "" immediately —
       NO index build, NO git call, NO marker written.
    2. Dedup (AC-09): if already_injected(root, session_id, rel), return "".
    3. Build the index via build_index(root); compose pointers via
       governing_docs(rel, index, runner).
    4. No-match fast-path (AC-11): if pointers is empty, return "" WITHOUT
       recording a marker — markers are only written for injecting reads.
    5. assemble_context(pointers, budget=150).  If ctx is non-empty →
       record_injection(root, session_id, rel) then return ctx.
       If somehow empty → return "" without recording.

    COST GUARANTEE (AC-11): a non-matching Read makes ZERO runner calls.
      • The self-read guard exits before build_index is called.
      • build_index makes no git calls (reads dirs + provenance JSON only).
      • governing_docs gates batch_hash on provenance entry-path membership:
        a path absent from all provenance entries never calls the runner.
    Passing runner straight through to governing_docs preserves this property.

    Never raises.
    """
    try:
        # Step 1: Self-read guard (AC-10) — exit before any I/O or git call.
        if rel is not None:
            try:
                _norm = str(rel).replace("\\", "/")
                _parts = [_p for _p in _norm.split("/") if _p]
                if _parts and _parts[0] == ".codearbiter":
                    return ""
            except Exception:  # noqa: BLE001
                pass  # Malformed rel; fall through — won't match anything below.

        # Step 2: Per-(session, file) dedup (AC-09).
        if already_injected(root, session_id, rel):
            return ""

        # Step 3: Build the index (cached) and compose the four-tier pointer list.
        index = build_index(root)
        pointers = governing_docs(rel, index, runner)

        # Step 4: No-match fast-path — do NOT record a marker on a miss (AC-11).
        if not pointers:
            return ""

        # Step 5: Assemble the context payload and deliver.
        ctx = assemble_context(pointers, budget=150)
        if ctx:
            record_injection(root, session_id, rel)
            return ctx
        return ""
    except Exception:  # noqa: BLE001
        return ""
