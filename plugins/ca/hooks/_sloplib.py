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
    return _separating_dash_in(seg)


# Block openers: a line matching any of these starts a new markdown block, so
# the line before it is NOT soft-wrapped into it (#484 AC-2). Joining across one
# of these would invent findings a reader never sees as a single sentence.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")
_THEMATIC_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
# A range split BY the wrap: `12–` / `18`. _RANGE_RE only sees one line, so the
# same-line exemption cannot reach it and it has to be re-checked on the join.
_RANGE_LEFT_RE = re.compile(r"\d\s*$")
_RANGE_RIGHT_RE = re.compile(r"^\s*\d")


def _starts_new_block(raw):
    """True if `raw` opens a new markdown block rather than continuing the
    previous line's paragraph. A `|` anywhere makes a line un-joinable: table
    rows are scanned cell-by-cell, and joining one to its neighbour would give a
    lone N/A marker the word context the cell split exists to deny it."""
    return bool(not raw.strip()
                or "|" in raw
                or _FENCE_RE.match(raw)
                or _HEADING_RE.match(raw)
                or _LIST_ITEM_RE.match(raw)
                or _THEMATIC_RE.match(raw)
                or _BLOCKQUOTE_RE.match(raw))


def _separating_dash_in(head, *, words_before=False, words_after=False,
                        tail_before="", head_after=""):
    """True if a dash INSIDE `head` joins two text spans, where its left context
    may reach back into the preceding lines of its paragraph and its right
    context forward into the following ones.

    #484: `_segment_separates` required word characters on both sides of the
    dash on the SAME line, so a separator at a soft-wrap boundary scored zero —
    in both directions. `…three states —` / `listed below.` has its right-hand
    span on the next line; `A tribunal is the heavyweight audit` / `— checkpoints
    are the lean sweep.` has its left-hand span on the previous one. Both were
    real, unreported VOICE.md violations in the site's own pages.

    Only dashes inside `head` are considered, so attribution stays on the line
    that actually holds the dash (AC-1) no matter how wide the paragraph is.

    The surrounding context arrives PRE-REDUCED rather than as joined text:
    `words_before`/`words_after` are booleans the caller accumulates once per
    paragraph, and `tail_before`/`head_after` are only the nearest neighbours,
    which is all the numeric-range adjacency check can see. Building the joined
    strings here instead was quadratic in paragraph length - 14x slower at 3000
    lines, measured - and this runs on every write and edit through H-13."""
    for d in _DASHES:
        idx = head.find(d)
        while idx != -1:
            left, right = head[:idx], head[idx + 1:]
            if ((words_before or _WORD_RE.search(left))
                    and (_WORD_RE.search(right) or words_after)):
                # A range split BY the wrap: the digit adjacency lives on the
                # neighbouring line, so fall back to it only when this line
                # contributes nothing on that side.
                near_left = left if left.strip() else tail_before
                near_right = right if right.strip() else head_after
                if not (_RANGE_LEFT_RE.search(near_left)
                        and _RANGE_RIGHT_RE.search(near_right)):
                    return True
            idx = head.find(d, idx + 1)
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
    lines = text.splitlines()
    # Each paragraph is scanned as a unit so a separator that lands at a
    # soft-wrap boundary is visible (#484), while every finding is still
    # attributed to the line holding its dash. `_prose_only` runs PER LINE and
    # before the join, so inline code, URLs, ranges and the definition-list
    # lead-in are stripped exactly as they were.
    index = 0
    while index < len(lines):
        raw = lines[index]
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        # The paragraph: this line, plus every following line that continues it.
        group = [index]
        following = index + 1
        while following < len(lines) and not _starts_new_block(lines[following]):
            group.append(following)
            following += 1
        prose = [_prose_only(lines[i]) for i in group]
        # Reduce the paragraph's context to what the dash test actually needs,
        # in one pass each direction. `word_before[k]` is "some EARLIER line in
        # this paragraph has a word character", `word_after[k]` the same looking
        # forward. It has to accumulate over the whole group rather than peek at
        # the neighbour: a line that is entirely inline code strips to
        # whitespace, so the real continuation can sit two lines from the dash.
        word_before = [False] * len(prose)
        for k in range(1, len(prose)):
            word_before[k] = word_before[k - 1] or bool(_WORD_RE.search(prose[k - 1]))
        word_after = [False] * len(prose)
        for k in range(len(prose) - 2, -1, -1):
            word_after[k] = word_after[k + 1] or bool(_WORD_RE.search(prose[k + 1]))
        for position, i in enumerate(group):
            head = prose[position]
            if "|" in lines[i]:
                # A table row: keep the cell-by-cell scan, and never let a
                # neighbouring row lend it context.
                hit = any(_segment_separates(cell) for cell in head.split("|"))
            else:
                hit = _separating_dash_in(
                    head,
                    words_before=word_before[position],
                    words_after=word_after[position],
                    tail_before=prose[position - 1] if position else "",
                    head_after=(prose[position + 1]
                                if position + 1 < len(prose) else ""),
                )
            if hit:
                findings.append({"line": i + 1, "context": lines[i].strip()})
        index = following
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
