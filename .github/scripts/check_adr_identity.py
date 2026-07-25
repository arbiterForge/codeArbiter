#!/usr/bin/env python3
"""Fail when an ADR identifier, or a `supersedes:` pointer, names more than one ADR (#416).

An ADR is identified by its filename STEM -- `0014-githook-shim-dropin-fail-closed`,
not `0014`. Two ADRs in this repository already carry the number 0014, and two later
ADRs supersede different ones of them, so a bare `supersedes: 0014` names two
documents at once and no consumer can tell which without reading prose.

Invariants enforced (all derived from the repository, never hand-asserted):

  1. Filename stems are unique -- the stem IS the identifier.
  2. An ADR number resolves to exactly one stem, apart from the single
     grandfathered historical collision below. A NEW file taking an already-used
     number is a violation, which is what stops the collision recurring.
  3. Every `supersedes:` value resolves to exactly one ADR. A stem always
     resolves. A bare number resolves only while it is unambiguous; the moment it
     names more than one stem it is an error, never a guess.

Run: python .github/scripts/check_adr_identity.py   (exit 1 on any violation)
"""

import os
import re
import sys

ADR_FILE_RE = re.compile(r"^(\d+)-.+\.md$")
SUPERSEDES_RE = re.compile(r"^supersedes:\s*(.*?)\s*$", re.I)

# Frontmatter scan depth, mirroring the hook-side indexers.
FRONTMATTER_SCAN_LIMIT = 26

# Spellings of "this ADR supersedes nothing".
_NO_PREDECESSOR = frozenset({"", "none", "n/a", "-"})

# The ONE historical number collision, grandfathered by the exact PAIR of stems
# rather than by the number 0014. Two ADRs were authored as 0014 independently;
# renaming either would rewrite an identifier that prose across the repository
# already cites, and the never-edit rule protects the decision record.
# Disambiguating the POINTERS that name them is the repair.
#
# Naming the stems, not the number, is what makes the collision non-recurring:
# a THIRD file numbered 0014 is not in this set, so it is rejected exactly like
# any other new duplicate. The waiver covers the two files that exist, forever,
# and nothing else.
GRANDFATHERED_DUPLICATE_STEMS = frozenset({
    "0014-githook-shim-dropin-fail-closed",
    "0014-pi-host-authentication-and-fail-closed-tool-boundary",
})


class ADRReferenceError(ValueError):
    """A `supersedes:` value does not name exactly one ADR."""


class AmbiguousADRReference(ADRReferenceError):
    """A bare ADR number names more than one document."""


class UnknownADRReference(ADRReferenceError):
    """A `supersedes:` value names no ADR at all."""


# ---- pure helpers -------------------------------------------------------------

def adr_number(stem):
    """The leading number of an ADR stem, as an int. `0014-x` -> 14."""
    return int(str(stem).split("-", 1)[0])


def resolve_supersedes(value, stems):
    """Resolve a `supersedes:` value to exactly one stem in `stems`.

    Returns the stem, or None when the ADR supersedes nothing. Raises
    AmbiguousADRReference when a bare number names more than one stem, and
    UnknownADRReference when the value names none.

    Never guesses. An ambiguous reference has no correct answer, so returning
    one -- even "the first match" -- would silently invent a decision chain.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NO_PREDECESSOR:
        return None

    known = list(stems or [])
    if text in known:
        return text

    if text.isdigit():
        wanted = int(text)
        matches = sorted(s for s in known if _leading_number(s) == wanted)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousADRReference(
                "bare ADR number %r names %d documents (%s) -- name the full "
                "filename stem instead" % (text, len(matches), ", ".join(matches))
            )

    raise UnknownADRReference(
        "supersedes: %r names no ADR under decisions/" % text)


def _leading_number(stem):
    try:
        return adr_number(stem)
    except (ValueError, IndexError):
        return None


def identity_errors(stems, supersedes_by_stem,
                    grandfathered=GRANDFATHERED_DUPLICATE_STEMS):
    """Every violation of the three clauses, as human-readable strings.

    `stems` is the list of ADR filename stems; `supersedes_by_stem` maps a stem
    to its raw `supersedes:` value. Pure -- no filesystem access.
    """
    errors = []
    stems = list(stems or [])

    # Clause 1 -- stems are unique.
    seen = set()
    for stem in stems:
        if stem in seen:
            errors.append("duplicate ADR stem %r -- the stem is the identifier "
                          "and must name exactly one decision" % stem)
        seen.add(stem)

    # Clause 2 -- a number resolves to one stem, apart from the grandfathered set.
    by_number = {}
    for stem in sorted(set(stems)):
        number = _leading_number(stem)
        if number is None:
            errors.append("ADR stem %r does not begin with a number" % stem)
            continue
        by_number.setdefault(number, []).append(stem)
    waived = set(grandfathered or ())
    for number, sharing in sorted(by_number.items()):
        if len(sharing) < 2:
            continue
        offending = [s for s in sharing if s not in waived]
        # The pair is waived only when EVERY file on that number is waived --
        # a third file joining a grandfathered number is still a violation.
        if not offending:
            continue
        errors.append(
            "ADR number %04d is used by %d files (%s) -- %s must take an unused "
            "number so `supersedes: %04d` stays unambiguous"
            % (number, len(sharing), ", ".join(sharing),
               " and ".join(offending), number))

    # Clause 3 -- every supersedes: value resolves to exactly one ADR.
    for stem in sorted(supersedes_by_stem or {}):
        try:
            resolve_supersedes(supersedes_by_stem[stem], stems)
        except ADRReferenceError as exc:
            errors.append("%s: %s" % (stem, exc))

    return errors


# ---- repository gatherers -----------------------------------------------------

def adr_stems(decisions_dir):
    """Sorted filename stems of every `NNNN-*.md` ADR in `decisions_dir`."""
    try:
        names = os.listdir(decisions_dir)
    except OSError:
        return []
    return sorted(os.path.splitext(n)[0] for n in names if ADR_FILE_RE.match(n))


def read_supersedes(path):
    """The raw `supersedes:` frontmatter value in `path`, or None if absent."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for i, line in enumerate(handle):
                if i >= FRONTMATTER_SCAN_LIMIT:
                    break
                match = SUPERSEDES_RE.match(line.strip())
                if match:
                    return match.group(1)
    except OSError:
        return None
    return None


def check(root):
    """Every ADR-identity violation in the repository at `root`."""
    ddir = os.path.join(str(root), ".codearbiter", "decisions")
    stems = adr_stems(ddir)
    supersedes = {}
    for stem in stems:
        value = read_supersedes(os.path.join(ddir, stem + ".md"))
        if value is not None:
            supersedes[stem] = value
    return identity_errors(stems, supersedes)


def main():
    here = os.path.dirname(os.path.abspath(__file__))  # <repo>/.github/scripts
    root = os.path.dirname(os.path.dirname(here))
    errors = check(root)
    if errors:
        print("::error::ADR identity/supersession is ambiguous:")
        for error in errors:
            print("  - " + error)
        return 1
    print("ADR stems unique; every supersedes: names exactly one decision")
    return 0


if __name__ == "__main__":
    sys.exit(main())
