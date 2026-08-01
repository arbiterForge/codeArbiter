#!/usr/bin/env python3
"""Fail when a shipped skill names a THIS-REPO path it executes or reads
(A-6.1, T-68a/b).

A skill under `core/surface/skills/**` renders into every governance
plugin and ships to consumers who do not have this repository. A line
telling such a consumer to run `.github/scripts/something.py`, or to
dispatch `tools/farm.js`, names a file that exists here and nowhere in
their install — so the instruction is unfollowable, and it fails at the
moment somebody tries to follow it rather than at review.

THE MATCHING RULE, stated here because A-6.1 requires the guard to state
it in its own docstring:

  FLAGGED — a repo-relative path to an EXECUTABLE or READABLE artifact,
  appearing inside backticks, whose first segment is one of the known
  repo roots below (`.github/`, `tools/`, `core/`, `plugins/`, `site/`)
  and which is not prefixed by a host-resolved variable.

  PERMITTED —
    * `${CLAUDE_PLUGIN_ROOT}/...` and `${CLAUDE_PROJECT_DIR}/...`, plus
      their `{{PLUGIN_ROOT}}` / `{{PROJECT_DIR}}` template spellings:
      these resolve in the consumer's install, which is the whole point.
    * A repo-path PATTERN inside a scan-target list. A scout that says
      "look under `src/`, `lib/`, `tools/`" is describing where to search
      in the CONSUMER'S repo, not naming a file to run. Distinguished by
      the surrounding line naming a scan/scout/search, not by the path.
    * A path named as PROSE about this repository's own CI, when the line
      marks it as such (see `_is_conditional_ci_reference`) — a skill may
      truthfully say "CI enforces this too" without instructing anyone to
      run it.

  The distinction is EXECUTES-OR-READS versus MENTIONS. A guard that
  flagged every occurrence of a repo path would forbid a skill from
  explaining its own governance, which is not the failure being closed.

Run: python .github/scripts/check_skill_portability.py   (exit 1 on a finding)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "core" / "surface" / "skills"

# First path segments that only exist in THIS repository's layout.
REPO_ROOTS = (".github/", "tools/", "core/", "plugins/", "site/")

# Host-resolved prefixes: these are the sanctioned way to name something a
# consumer actually has.
RESOLVED_PREFIXES = ("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}",
                     "{{PLUGIN_ROOT}}", "{{PROJECT_DIR}}")

# Extensions that make a path an artifact to RUN or READ rather than a
# directory being described.
ARTIFACT_SUFFIXES = (".py", ".js", ".mjs", ".ts", ".sh", ".json", ".yml", ".yaml")

_BACKTICKED = re.compile(r"`([^`]+)`")

# A line describing where to SEARCH, not what to run.
_SCAN_CONTEXT = re.compile(
    r"\b(scan|scout|search|glob|look under|candidate|inventory|walk)\b", re.I)

# A line presenting a path as this repo's own CI, not as an instruction.
_CI_CONTEXT = re.compile(
    r"\b(in CI|CI[- ]only|CI enforces|this repository'?s own|when run inside "
    r"this repo|not shipped)\b", re.I)


def _is_conditional_ci_reference(line):
    """True when the line frames the path as this repo's CI rather than as
    something the reader should execute."""
    return bool(_CI_CONTEXT.search(line))


def _is_scan_target(line):
    return bool(_SCAN_CONTEXT.search(line))


def _candidate_paths(span):
    """Repo-rooted artifact paths inside one backticked span."""
    found = []
    for token in re.split(r"[\s(),;|]+", span.strip()):
        token = token.strip("`'\"<>[]")
        if not token:
            continue
        if any(token.startswith(prefix) for prefix in RESOLVED_PREFIXES):
            continue
        if any(prefix in token for prefix in RESOLVED_PREFIXES):
            # e.g. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/x.py` — resolved.
            continue
        if not token.startswith(REPO_ROOTS):
            continue
        if not token.endswith(ARTIFACT_SUFFIXES):
            continue
        found.append(token)
    return found


def scan_file(path, text=None):
    """Findings for one skill file: `[(lineno, path, line)]`."""
    if text is None:
        text = Path(path).read_text(encoding="utf-8")
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if _is_scan_target(line) or _is_conditional_ci_reference(line):
            continue
        for span in _BACKTICKED.findall(line):
            for candidate in _candidate_paths(span):
                findings.append((number, candidate, line.strip()))
    return findings


def scan(root=SKILLS):
    findings = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            full = Path(dirpath) / name
            hits = scan_file(full)
            if not hits:
                continue
            # Display path relative to the repo when the file is inside it,
            # and relative to the scan root otherwise. `relative_to(REPO)`
            # alone RAISES for any root outside this tree, which made the
            # function unusable against a synthetic fixture -- i.e. against
            # the one test that proves the guard can still fail.
            try:
                shown = full.relative_to(REPO)
            except ValueError:
                shown = full.relative_to(root)
            findings[str(shown).replace("\\", "/")] = hits
    return findings


def main():
    findings = scan()
    if not findings:
        print("skill portability: no shipped skill names a this-repo path "
              "it executes or reads")
        return 0
    print("::error::a shipped skill names a THIS-REPO path a consumer will "
          "not have:")
    for relative, hits in sorted(findings.items()):
        for number, candidate, line in hits:
            print(f"  {relative}:{number}: {candidate}")
            print(f"      {line[:140]}")
    print("  Fix by resolving it under ${CLAUDE_PLUGIN_ROOT}/ or "
          "${CLAUDE_PROJECT_DIR}/, or by rewording it as a statement about "
          "this repository's CI rather than an instruction.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
