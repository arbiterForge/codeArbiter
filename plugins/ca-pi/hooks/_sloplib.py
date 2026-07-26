# codeArbiter v2 — anti-slop copy-law detector (advisory).
#
# A lightweight guard for the single highest-signal AI tell: the em-dash / en-dash
# used as a PROSE sentence-separator (anti-slop-design core §3.A). It backs the
# PostToolUse reminder in post-write-edit.py and is the mechanical aid #60 asks
# for, so the PR #59 regression class (user-facing docs shipping with separator
# dashes) cannot recur silently.
#
# This is a heuristic, not a parser, and it is advisory — it nudges the producer
# to run the §3.A/§3.B copy self-audit; it never blocks. It honors the §3.A
# exemptions it can detect cheaply (fenced/inline code, URLs, numeric/date ranges)
# and errs toward silence on the rest.
#
# Public API:
#   find_prose_separator_dashes(text) -> list[dict]   findings per line; each
#                                        {"line": int, "context": str}; empty when clean
#   in_antislop_doc_scope(rel_path) -> bool   True for user-facing Markdown the
#                                        anti-slop bundle governs (repo-root + docs/**)

import re

EM_DASH = "—"
EN_DASH = "–"
_DASHES = (EM_DASH, EN_DASH)

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
# Strip URLs, autolinks/HTML tags and comments, and markdown link targets so a
# dash inside any of them is never read as prose.
_URL_RE = re.compile(r"https?://\S+|<[^>]*>|\]\([^)]*\)")
# Numeric / date range: a dash flanked by digits (pp. 12–18, 2019–2024). Correct
# typography per §3.A, never a finding.
_RANGE_RE = re.compile(r"\d\s*[–—]\s*\d")
# A letter or digit (Unicode), used to confirm a dash actually joins two text
# spans rather than standing alone (e.g. a lone "—" N/A marker in a table cell).
_WORD_RE = re.compile(r"[^\W_]", re.UNICODE)
# A DEFINITION-LIST dash: `- **term** — meaning`. Structural, not a sentence
# separator, and the rule this detector enforces says "sentence separators" -
# site/VOICE.md's own Terminology anchors section is written in exactly this
# form, so flagging it would make the gate contradict the style guide it exists
# to enforce (#338). Anchored to the start of the line and to a bolded lead-in,
# so an ordinary sentence that happens to contain bold text is untouched.
#
# The TERM is captured and kept; only the dash is dropped. Blanking the whole
# lead-in was the first cut and it was a false-negative generator: on
#     - **The gate-enforcement hooks** — `a.py`, `b.py` — make zero calls.
# it removed the left-hand words, then _INLINE_CODE_RE blanked the backticks,
# and the SECOND dash - a real separator - was left with no word character on
# its left and escaped. That loosened the shared detector for docs/** and
# repo-root too, not only for site prose.
_DEFINITION_RE = re.compile(r"^(\s*(?:[-*+]\s+)?\*\*[^*]+\*\*\s*)[–—]")


def _prose_only(line):
    """Drop the spans §3.A exempts so only candidate prose remains."""
    # Only the definition DASH is dropped; the term is kept (group 1), so a
    # later separator on the same line still has its left-hand context.
    line = _DEFINITION_RE.sub(r"\1 ", line)
    line = _INLINE_CODE_RE.sub(" ", line)
    line = _URL_RE.sub(" ", line)
    line = _RANGE_RE.sub(" ", line)
    return line


def _segment_separates(seg):
    """True if `seg` contains an em/en dash with word characters on BOTH sides —
    i.e. it joins two text spans (a prose separator), not a lone filler dash."""
    for d in _DASHES:
        idx = seg.find(d)
        while idx != -1:
            if _WORD_RE.search(seg[:idx]) and _WORD_RE.search(seg[idx + 1:]):
                return True
            idx = seg.find(d, idx + 1)
    return False


def find_prose_separator_dashes(text):
    """Return a finding per line that uses an em/en dash as a prose separator.

    Each finding is {"line": <1-based int>, "context": <stripped line text>}.
    Exempt: fenced code blocks, inline code, URLs, numeric/date ranges, and a
    lone dash that joins no text (split on `|` so a table-cell N/A marker is not
    mistaken for a separator).
    """
    findings = []
    in_fence = False
    for i, raw in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = _prose_only(raw)
        if any(_segment_separates(seg) for seg in prose.split("|")):
            findings.append({"line": i, "context": raw.strip()})
    return findings


# Authored site prose (#338). site/VOICE.md has banned em-dashes as sentence
# separators since 2026-07-02, and nothing enforced it: this predicate covered
# repo-root docs and docs/**, never site/. A rule with no gate, violated in 16
# of its own 36 authored files, is worse than no rule - reviewers cite it and it
# is wrong.
#
# Scope is AUTHORED prose only. Everything under content/docs/reference/ is
# generated on every build (91 of the 128 files there), changelog.md is a
# verbatim pass-through of the repo CHANGELOG, and site/src/curated/** mirrors
# plugins/ca bodies - which are framework prose under a different register, and
# already excluded via plugins/. Flagging any of those would report a finding
# nobody wrote and nobody can fix in place.
_SITE_PROSE_ROOT = "site/src/content/docs/"
_SITE_PROSE_EXCLUDED = ("reference/", "changelog.md")


def in_antislop_doc_scope(rel_path):
    """True for user-facing Markdown the anti-slop bundle governs: repo-root
    community docs, docs/**, and AUTHORED site prose under
    site/src/content/docs/ (#338). Excludes codeArbiter's own framework bodies
    (everything under plugins/), machine-managed .codearbiter/ state, and every
    generated site page."""
    if not rel_path:
        return False
    p = rel_path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    # `.mdx` counts: the rule is about prose, not about a file extension, and
    # two authored site pages are .mdx.
    if not p.lower().endswith((".md", ".mdx")):
        return False
    if p.startswith("plugins/") or p.startswith(".codearbiter/"):
        return False
    if p.startswith(_SITE_PROSE_ROOT):
        rest = p[len(_SITE_PROSE_ROOT):]
        return not rest.startswith(_SITE_PROSE_EXCLUDED)
    if p.startswith("site/"):
        return False
    if p.startswith("docs/"):
        return True
    return "/" not in p
