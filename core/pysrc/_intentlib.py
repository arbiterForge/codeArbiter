#!/usr/bin/env python3
# codeArbiter -- spec-intent coverage backstop (#566).
#
# `writing-plans` Phase 4 proves BIJECTION between a plan's tasks and its
# `AC-NN` ledger: every criterion has a task, every task has a criterion.
# That proves the two AGREE with each other -- it says nothing about
# whether the ledger itself is COMPLETE relative to what the spec (and its
# linked issue) actually asked for. A criterion missed by BOTH sides --
# never drafted in `brainstorming`, so never assigned a task in
# `writing-plans` either -- passes bijection cleanly while the deliverable
# it would have named goes unbuilt. Observed twice in one sprint: the
# `release-portable-fixture` spec's own central artifact (a scope bullet
# no criterion cited), and #563's end-to-end portability property (an
# issue acceptance checkbox that never became a criterion at all).
#
# This module is the MECHANICAL half of the fix, not the whole of it -- a
# citation check, never a completeness proof. It flags an in-scope bullet
# or an issue acceptance checkbox that no acceptance criterion's text
# CITES (shares a distinctive word with). It cannot catch a bullet that IS
# cited but only PARTIALLY satisfied by the criteria that cite it -- a
# scope bullet reading "fix all three contaminated skills" against
# criteria for two of the three passes this check, because the bullet IS
# cited. That half is judgment: the skill asks it explicitly as "if every
# criterion passed and nothing else changed, what would still be broken?"
# and this module has no part in answering it.
#
# Stdlib only (ADR-0004). Every function below is pure -- no filesystem,
# no git, no network -- so the whole surface is fixture-testable with
# synthetic spec/issue text. The CLI wrapper at the bottom is the only I/O,
# reading two already-resolved files so the skill never pipes untrusted
# text through a shell substitution.
#
# Public API:
#   uncovered_intent(spec_text, issue_body=None) -> list[str]
#       Every in-scope bullet / issue acceptance checkbox no criterion
#       cites, each prefixed by its kind (`[UNCOVERED-SCOPE]` /
#       `[UNCOVERED-CHECKBOX]`), in source order. Empty when everything
#       found is cited, including when there is nothing to check (no
#       `## Scope` section, no issue body).
#
# CLI:
#   _intentlib.py uncovered-intent <spec-file> [--issue-body <file>]
#       exit 0 -- empty (nothing uncovered); 1 -- one or more findings,
#       printed one per line to stdout; 2 -- bad invocation or an unreadable
#       file.

import re
import sys

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "being", "this",
    "that", "these", "those", "it", "its", "as", "at", "by", "from",
    "into", "than", "then", "so", "not", "no", "never", "always",
    "when", "while", "if", "each", "every", "any", "all", "one", "two",
    "will", "shall", "should", "would", "can", "could", "may", "might",
    "must", "have", "has", "had", "do", "does", "did", "done", "also",
    "only", "just", "still", "yet", "over", "under", "out", "up",
    "down", "about", "after", "before", "between", "through", "per",
    "your", "you", "we", "our", "their", "them", "which", "what",
    "where", "there", "here", "such", "some", "more", "most", "own",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.*\S)\s*$")
_OUT_OF_SCOPE_RE = re.compile(r"out.of.scope|out.scope|not\s+build(?:ing)?", re.IGNORECASE)

MIN_TOKEN_LEN = 4


def _tokens(text):
    """Distinctive lowercase words in `text`: stdlib-tokenized, short words
    and a small stopword set dropped, order-preserving and de-duplicated.
    A word carrying no distinctive token (e.g. "Fast." alone) yields []."""
    seen = []
    for word in _TOKEN_RE.findall(text.lower()):
        if len(word) < MIN_TOKEN_LEN or word in _STOPWORDS:
            continue
        if word not in seen:
            seen.append(word)
    return seen


def _section(text, heading_pattern):
    """Lines of the FIRST heading whose text matches `heading_pattern`
    (case-insensitive, anywhere in the heading text), up to the next
    heading at the same or a shallower level. [] when no such heading
    exists -- an absent section names nothing to check, not an error."""
    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        this_level = len(m.group(1))
        if start is None:
            if re.search(heading_pattern, m.group(2), re.IGNORECASE):
                start, level = i + 1, this_level
            continue
        if this_level <= level:
            return lines[start:i]
    return lines[start:] if start is not None else []


def _in_scope_bullets(spec_text):
    """Bullet lines under the first `## Scope`-ish heading, stopping at an
    "out of scope" marker line (the line NAMING the boundary, not a bullet
    beneath it). Best-effort: a spec that never separates in- from
    out-of-scope this way is scanned in full, which can over-flag rather
    than under-flag -- the skill's negative-judgment question is the
    backstop for what this heuristic gets wrong, not a reason to drop it."""
    section = _section(spec_text, r"scope")
    bullets = []
    for line in section:
        m = _BULLET_RE.match(line)
        if m is None and _OUT_OF_SCOPE_RE.search(line):
            break
        if m:
            bullets.append(m.group(1))
    return bullets


def _criteria_texts(spec_text):
    """Every numbered or bulleted criterion line under the first
    "acceptance criteria"-ish heading. A non-list line (closing prose, a
    reviewer's note, anything after the numbered list that isn't itself a
    criterion) is NOT a criterion and contributes no citation tokens --
    counting it would let an unrelated sentence's vocabulary falsely
    "cite" a scope bullet or checkbox it never actually addresses."""
    section = _section(spec_text, r"acceptance criteria")
    out = []
    for line in section:
        m = _BULLET_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def _checkboxes(issue_body):
    if not issue_body:
        return []
    out = []
    for line in issue_body.splitlines():
        m = _CHECKBOX_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def _cited(item_text, criteria_tokens):
    """True when `item_text` shares a distinctive token with the criteria
    set, OR when `item_text` carries no distinctive token of its own to
    check (nothing extractable is never flagged as missing)."""
    tokens = _tokens(item_text)
    if not tokens:
        return True
    return any(t in criteria_tokens for t in tokens)


def uncovered_intent(spec_text, issue_body=None):
    """Every in-scope bullet / issue acceptance checkbox that no
    acceptance criterion's text cites, each prefixed by its kind, scope
    bullets first then checkboxes, both in source order.

    A CITATION check, not a completeness proof -- see the module
    docstring for what it cannot catch."""
    if not isinstance(spec_text, str):
        spec_text = ""
    criteria_tokens = set()
    for criterion in _criteria_texts(spec_text):
        criteria_tokens.update(_tokens(criterion))

    findings = []
    for bullet in _in_scope_bullets(spec_text):
        if not _cited(bullet, criteria_tokens):
            findings.append(f"[UNCOVERED-SCOPE] {bullet}")
    for box in _checkboxes(issue_body):
        if not _cited(box, criteria_tokens):
            findings.append(f"[UNCOVERED-CHECKBOX] {box}")
    return findings


def main(argv):
    """CLI dispatch.

      uncovered-intent <spec-file> [--issue-body <file>]
                                  prints one finding per line (see
                                  `uncovered_intent`'s docstring for the
                                  two prefixes). exit 0 nothing uncovered -
                                  1 one or more findings - 2 bad invocation
                                  or an unreadable file.
    """
    if not argv or argv[0] != "uncovered-intent":
        sys.stderr.write(
            "usage: _intentlib.py uncovered-intent <spec-file> [--issue-body <file>]\n")
        return 2

    rest = argv[1:]
    issue_body_path = None
    positional = []
    i = 0
    while i < len(rest):
        if rest[i] == "--issue-body":
            if i + 1 >= len(rest):
                sys.stderr.write("_intentlib.py: --issue-body requires a path\n")
                return 2
            issue_body_path = rest[i + 1]
            i += 2
            continue
        positional.append(rest[i])
        i += 1
    if len(positional) != 1:
        sys.stderr.write(
            "usage: _intentlib.py uncovered-intent <spec-file> [--issue-body <file>]\n")
        return 2

    try:
        with open(positional[0], encoding="utf-8") as fh:
            spec_text = fh.read()
    except OSError as exc:
        sys.stderr.write(f"_intentlib.py: cannot read {positional[0]}: {exc}\n")
        return 2

    issue_body = None
    if issue_body_path is not None:
        try:
            with open(issue_body_path, encoding="utf-8") as fh:
                issue_body = fh.read()
        except OSError as exc:
            sys.stderr.write(f"_intentlib.py: cannot read {issue_body_path}: {exc}\n")
            return 2

    findings = uncovered_intent(spec_text, issue_body)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
