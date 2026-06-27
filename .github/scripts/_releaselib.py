#!/usr/bin/env python3
# codeArbiter - pure helpers backing the `release` skill's mechanical gates.
#
# The release SKILL.md is prose the orchestrator follows; these are the small,
# git-free, synthetically-testable assertions that back its load-bearing steps so
# a model lapse can't ship a wrong or half-published release. Each maps to one
# acceptance criterion of specs/release-skill-hardening.md (findings v2.release.
# 0003-0006). The skill invokes them; CI runs their tests (test_release_lib.py).
#
# Design invariants (mirror the other _*lib helpers):
#   - Stdlib only; zero side effects at import (no git, no file I/O).
#   - Pure functions over synthetic input; never raise on malformed input -
#     degrade to the safe answer (False / the <none> sentinel), since a release
#     gate that crashes is worse than one that conservatively refuses.
#
# Public API:
#   last_tag_select(tags) -> str
#   notes_heading_matches(notes_text, tag) -> bool
#   release_dates_consistent(changelog_section, tag_message) -> bool
#   classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
#                          manifest_version, release_is_nondraft) -> str

import re

NONE_SENTINEL = "<none>"

# A `ca` release tag is exactly `vMAJOR.MINOR.PATCH` - no suffix. The anchored
# form already excludes pre-releases (`v2.6.0-beta.1`) and the namespaced
# `ca-sandbox-v*` series (no leading bare `v`); PRERELEASE_MARKERS is the
# explicit, legible second line of defense the spec names.
_CA_RELEASE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_PRERELEASE_MARKERS = ("-beta", "-rc", "-alpha")

# A changelog section heading, in either the `## vX.Y.Z - DATE` form or the
# Keep-a-Changelog `## [X.Y.Z] - DATE` form the repo actually ships (every
# released section + every prior GitHub Release body uses the bracket style).
# The capture is the bare `X.Y.Z`; the optional leading `v` and the surrounding
# brackets sit OUTSIDE the group, so heading comparison is style-agnostic. Any
# separator is allowed between version and date. Plus the annotated-tag
# `Released-at:` footer.
_HEADING_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
_CHANGELOG_DATE_RE = re.compile(
    r"^##\s+\[?v?\d+\.\d+\.\d+\]?\D+(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_RELEASED_AT_RE = re.compile(r"Released-at:\s*(\d{4}-\d{2}-\d{2})")


def _bare_version(tag):
    """`v2.6.0` / `[2.6.0]` / `2.6.0` -> `2.6.0`. Lets the heading match compare
    a `vX.Y.Z` tag against a bracket-style heading without caring about style."""
    return tag.strip().lstrip("v").strip("[]") if isinstance(tag, str) else tag


def last_tag_select(tags):
    """Return the highest `ca` SemVer tag (`vMAJOR.MINOR.PATCH`) in `tags`,
    excluding pre-releases (`-beta`/`-rc`/`-alpha`) and the `ca-sandbox-v*`
    series. Returns NONE_SENTINEL when no ca release tag is present. This is the
    single source of `LAST_TAG`, replacing the skill's inline grep one-liner -
    bare `git describe --tags` resolves to a ca-sandbox tag in this repo."""
    best = None  # ((major, minor, patch), original_tag)
    if not isinstance(tags, (list, tuple)):
        return NONE_SENTINEL
    for t in tags:
        if not isinstance(t, str):
            continue
        if any(marker in t for marker in _PRERELEASE_MARKERS):
            continue
        m = _CA_RELEASE_RE.match(t)
        if not m:
            continue
        ver = tuple(int(g) for g in m.groups())
        if best is None or ver > best[0]:
            best = (ver, t)
    return best[1] if best else NONE_SENTINEL


def notes_heading_matches(notes_text, tag):
    """True iff the FIRST changelog heading in `notes_text` (either `## vX.Y.Z`
    or the Keep-a-Changelog `## [X.Y.Z]` form) names the same version as `tag`. A
    stale notes-file (whose first section is an older version) returns False, so
    the release skill cannot publish the wrong changelog section under the right
    tag. Missing heading or non-string input -> False."""
    if not isinstance(notes_text, str) or not isinstance(tag, str):
        return False
    m = _HEADING_RE.search(notes_text)
    if not m:
        return False
    return m.group(1) == _bare_version(tag)


def release_dates_consistent(changelog_section, tag_message):
    """True iff the date in `changelog_section`'s heading (`## vX.Y.Z - DATE` or
    `## [X.Y.Z] - DATE`) equals the `Released-at: DATE` date in `tag_message`.
    Guards against the date being
    hand-typed inconsistently across surfaces. Either date absent, or non-string
    input -> False."""
    if not isinstance(changelog_section, str) or not isinstance(tag_message, str):
        return False
    cm = _CHANGELOG_DATE_RE.search(changelog_section)
    tm = _RELEASED_AT_RE.search(tag_message)
    if not cm or not tm:
        return False
    return cm.group(1) == tm.group(1)


def classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
                           manifest_version, release_is_nondraft):
    """Classify a (re)publish attempt so the skill can resume a half-finished
    publish instead of dead-ending on 'tag exists -> STOP'. Returns one of:

      publish_fresh      - no tag yet; the normal Phase 2/3 path.
      already_published  - a non-draft Release already exists on the tag.
      resume_publish     - tag is at HEAD and its version matches the manifest,
                           but no non-draft Release exists (tag pushed, Release
                           never created) -> finish Phase 3.
      abort_mismatch     - tag points at a non-HEAD commit, or its version
                           disagrees with the manifest -> STOP, never overwrite.
    """
    if not tag_exists:
        return "publish_fresh"
    if release_is_nondraft:
        return "already_published"
    if tag_sha == head_sha and tag_version == manifest_version:
        return "resume_publish"
    return "abort_mismatch"


# --------------------------------------------------------------------------- #
# Thin CLI so the release SKILL.md can shell out to the pinned logic, the same
# way it already calls check_badge_consistency.py. Pure dispatch over the
# functions above; reads tags from stdin / files from argv. Never raises.
# --------------------------------------------------------------------------- #

def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv):
    """CLI dispatch. Subcommands:
      last-tag                                 stdin=tags -> prints selected tag / <none>
      notes-match <tag> <notes_file>           exit 0 iff first heading == tag
      dates-consistent <changelog> <tagmsg>    exit 0 iff the two dates agree
      classify <tag_exists> <tag_sha> <head_sha> <tag_version> <manifest_version> <release_nondraft>
                                               prints the publish-state label (bools: true/false)
    Returns a process exit code."""
    import sys
    if not argv:
        sys.stderr.write("usage: _releaselib.py {last-tag|notes-match|dates-consistent|classify} ...\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "last-tag":
        print(last_tag_select(sys.stdin.read().split()))
        return 0
    if cmd == "notes-match" and len(rest) == 2:
        return 0 if notes_heading_matches(_read(rest[1]), rest[0]) else 1
    if cmd == "dates-consistent" and len(rest) == 2:
        return 0 if release_dates_consistent(_read(rest[0]), _read(rest[1])) else 1
    if cmd == "classify" and len(rest) == 6:
        b = lambda s: str(s).lower() == "true"
        print(classify_publish_state(
            tag_exists=b(rest[0]), tag_sha=rest[1], head_sha=rest[2],
            tag_version=rest[3], manifest_version=rest[4], release_is_nondraft=b(rest[5])))
        return 0
    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
