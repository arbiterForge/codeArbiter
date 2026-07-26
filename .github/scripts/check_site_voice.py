#!/usr/bin/env python3
"""Issue #338 - site/VOICE.md's punctuation rule, finally enforced.

`site/VOICE.md` has said this since 2026-07-02:

    Em-dashes are not used as sentence separators in site prose. Restructure
    with a period, a comma, a colon, or parentheses instead.

Nothing enforced it. `_sloplib.in_antislop_doc_scope` governed repo-root docs
and `docs/**` and had never covered `site/`, so the rule was prose asking
politely - and 16 of the 36 authored pages violated it, for 24 days, while
reviewers cited it at contributors.

A rule with no gate is worse than no rule. It is not merely unenforced: people
learn that the style docs are advisory, which is the same failure mode as a
teardown report that over-counts its failures. So this is the gate.

SCOPE IS AUTHORED PROSE, and the exclusions are load-bearing rather than
convenient:

  * `site/src/content/docs/reference/**` - 91 of the 128 pages there are
    generated on every build. Flagging them would report findings nobody wrote
    and nobody can fix in place.
  * `site/src/content/docs/changelog.md` - a verbatim pass-through of the repo
    CHANGELOG, which is payload prose under a different register.
  * `site/src/curated/**` - mirrors of `plugins/ca` bodies. Framework prose,
    already excluded via `plugins/`; mirroring it into the site must not smuggle
    it back into scope.

The file set comes from `git ls-files`, so a generated page cannot drift into
scope by being written into a tracked directory: if it is not committed, it is
not audited.

KNOWN GAP, stated rather than discovered later. The detector is line-based: it
requires word characters on both sides of the dash ON THE SAME LINE. A separator
dash that lands at a line-wrap boundary -
    ...it holds in one of three states —
    listed below.
- is therefore invisible to it, and three such dashes were found by hand in
`codearbiter-directory.md` while fixing the flagged ones. They were fixed too,
but the gate did not catch them and would not catch a new one. Closing that
needs paragraph-level analysis rather than a per-line scan, which is a larger
change than this gate; it is filed separately rather than implied to be handled.

Usage:
    python .github/scripts/check_site_voice.py           # audit, exit 1 on findings
    python .github/scripts/check_site_voice.py --list    # paths only, exit 0
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "plugins" / "ca" / "hooks"))

from _sloplib import find_prose_separator_dashes, in_antislop_doc_scope  # noqa: E402

SITE_PROSE = "site/src/content/docs"


def audited_paths() -> list[str]:
    """Every git-TRACKED page under the authored site-prose root that the shared
    scope predicate governs. One source of truth for scope: this script does not
    re-implement the exclusions, it asks `in_antislop_doc_scope`."""
    tracked = subprocess.run(
        ["git", "ls-files", SITE_PROSE],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.split()
    return sorted(p for p in tracked if in_antislop_doc_scope(p))


def audit() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rel in audited_paths():
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        hits = find_prose_separator_dashes(text)
        if hits:
            out[rel] = hits
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the audited paths and exit 0")
    arguments = parser.parse_args(argv)

    paths = audited_paths()
    if arguments.list:
        for rel in paths:
            print(rel)
        return 0

    if not paths:
        print("::error::no authored site prose found to audit - the scope predicate has drifted",
              file=sys.stderr)
        return 1

    findings = audit()
    total = sum(len(v) for v in findings.values())
    if not findings:
        print(f"site voice: {len(paths)} authored page(s) clean of prose separator dashes")
        return 0

    print(f"::error::site/VOICE.md forbids the em-dash as a sentence separator in site prose; "
          f"{total} line(s) across {len(findings)} file(s) still use one. Restructure with a "
          f"period, a comma, a colon, or parentheses.", file=sys.stderr)
    for rel, hits in findings.items():
        for hit in hits:
            print(f"  {rel}:{hit['line']}: {hit['context'][:160]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
