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
#   select_release_target(*confirmations) -> str   (RELEASE_TARGETS order)
#   classify_merge_readiness(check_runs, head_sha, check_name) -> str
#   peel_tag(ls_remote_text, tag) -> str
#
# The last three back `.github/workflows/release.yml`'s read-only preflight and
# its tag-integrity guard (issues #378, #385, #380). The hosted publish path
# holds `contents: write` and its writes are public and irreversible, so every
# one of them degrades to the REFUSING answer on malformed input.

import re

NONE_SENTINEL = "<none>"

# The `ci-passed` aggregate in .github/workflows/ci.yml — the single check run
# that means "every required job for this commit concluded green". Kept in sync
# with that job's `name:` by test_release_workflow.py.
MERGE_READINESS_CHECK = "[GATE ] | [REPO] | Merge readiness"

# A `ca` release tag is exactly `vMAJOR.MINOR.PATCH` - no suffix. The anchored
# form already excludes pre-releases (`v2.6.0-beta.1`) and the namespaced
# `ca-sandbox-v*` series (no leading bare `v`); PRERELEASE_MARKERS is the
# explicit, legible second line of defense the spec names.
_RELEASE_RE_CACHE = {}


def _release_re(prefix):
    """The anchored `<prefix>MAJOR.MINOR.PATCH` matcher for one release series."""
    rx = _RELEASE_RE_CACHE.get(prefix)
    if rx is None:
        rx = re.compile(r"^" + re.escape(prefix) + r"(\d+)\.(\d+)\.(\d+)$")
        _RELEASE_RE_CACHE[prefix] = rx
    return rx
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


# Every plugin that has a sanctioned release lane, in dispatch-input order
# (#382). The names are the labels `select_release_target` returns and the
# values release.yml's publisher `if:` conditions compare against; adding a
# plugin here without adding its publisher job turns the workflow contract
# suite red rather than resolving a target nothing can publish.
RELEASE_TARGETS = ("ca", "ca-codex", "ca-sandbox", "ca-pi")

# Each target's tag namespace. `ca` owns the bare `v*` series as the repository's
# primary release; every sibling is namespaced so it cannot collide with it. The
# ANCHORED match built from these prefixes is also what keeps one series from
# resolving another's tag as its own baseline — `^v` cannot match `ca-pi-v0.1.30`
# — so series isolation is a property of the match rather than an exclusion list
# somebody has to remember to extend. release.yml's per-lane `tag-prefix` inputs
# are asserted against this map by the workflow contract suite, so the hosted
# lane and the /ca:release command cannot disagree about a namespace.
RELEASE_TAG_PREFIXES = {
    "ca": "v",
    "ca-codex": "ca-codex-v",
    "ca-sandbox": "ca-sandbox-v",
    "ca-pi": "ca-pi-v",
}


def _bare_version(tag):
    """`v2.6.0` / `[2.6.0]` / `2.6.0` -> `2.6.0`. Lets the heading match compare
    a `vX.Y.Z` tag against a bracket-style heading without caring about style."""
    return tag.strip().lstrip("v").strip("[]") if isinstance(tag, str) else tag


def last_tag_select(tags, prefix="v"):
    """Return the highest SemVer tag in `tags` for ONE release series, excluding
    pre-releases (`-beta`/`-rc`/`-alpha`). Returns NONE_SENTINEL when the series
    has no release tag yet.

    `prefix` selects the series and defaults to `"v"` — ca, the primary release —
    so every existing caller keeps its behaviour unchanged. Pass a value from
    RELEASE_TAG_PREFIXES for a sibling (#382, the /ca:release command half).

    This is the single source of `LAST_TAG`, replacing the skill's inline grep
    one-liner: bare `git describe --tags` returns the nearest tag by commit-graph
    ANCESTRY, which in a multi-plugin repo is routinely another plugin's tag, and
    silently bases an entire release on the wrong baseline.

    Series isolation is a property of the ANCHORED match rather than a list of
    exclusions to maintain: `^v` cannot match `ca-pi-v0.1.30`, and `^ca-pi-v`
    cannot match `v2.9.1`. A fifth plugin therefore cannot leak into an existing
    series by being forgotten in an exclusion list."""
    best = None  # ((major, minor, patch), original_tag)
    if not isinstance(tags, (list, tuple)):
        return NONE_SENTINEL
    if not isinstance(prefix, str) or not prefix:
        return NONE_SENTINEL
    matcher = _release_re(prefix)
    for t in tags:
        if not isinstance(t, str):
            continue
        if any(marker in t for marker in _PRERELEASE_MARKERS):
            continue
        m = matcher.match(t)
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
      already_published  - the tag is at HEAD and a non-draft Release exists.
      resume_publish     - tag is at HEAD and its version matches the manifest,
                           but no non-draft Release exists (tag pushed, Release
                           never created) -> finish Phase 3.
      abort_mismatch     - tag points at a non-HEAD commit, or its version
                           disagrees with the manifest -> STOP, never overwrite.

    Mismatch OUTRANKS publication state (issue #380). An existing Release used
    to short-circuit to `already_published` before the tag was compared to
    HEAD, so a resumed publish silently accepted a Release whose tag installs a
    different snapshot. The tag is what consumers actually fetch; if it does
    not name this commit, nothing about the Release makes the state safe.
    """
    if not tag_exists:
        return "publish_fresh"
    if tag_sha != head_sha or tag_version != manifest_version:
        return "abort_mismatch"
    if release_is_nondraft:
        return "already_published"
    return "resume_publish"


def select_release_target(*confirmations):
    """Resolve which single plugin a release dispatch selected. `confirmations`
    are the per-plugin version inputs, positionally aligned with
    RELEASE_TARGETS. Returns one of:

      <target>   - exactly one input was supplied; the name from RELEASE_TARGETS.
      none       - no input was supplied; there is nothing to publish.
      multiple   - more than one; the dispatch is ambiguous and MUST be refused.
      arity      - the caller passed the wrong NUMBER of inputs.

    Issue #378: the publish jobs each tested only their OWN confirmation input,
    so one dispatch supplying both started two `contents: write` publishers and
    could create two tags and two public Releases. Selection is one decision,
    made once, by a job that holds no write token. Blank-ish input (whitespace,
    non-string) counts as "not selected" so a stray space can never read as a
    second target.

    Issue #382 widened this from two plugins to four (ca, ca-codex, ca-sandbox,
    ca-pi). The count is checked rather than zipped-to-shortest on purpose: a
    caller wired for two would otherwise resolve `ca` from a dispatch that also
    selected ca-pi, silently publishing the wrong plugin. `arity` is not a
    target and matches no `case` arm in release.yml, so the workflow's
    fail-closed `*)` default refuses it - and, like every other return here,
    it is a LABEL rather than an exception, so the caller's contract of "prints
    a label and never raises" holds."""
    def _selected(value):
        return isinstance(value, str) and value.strip() != ""

    if len(confirmations) != len(RELEASE_TARGETS):
        return "arity"
    selected = [target for target, value in zip(RELEASE_TARGETS, confirmations)
                if _selected(value)]
    if len(selected) > 1:
        return "multiple"
    if selected:
        return selected[0]
    return "none"


def classify_merge_readiness(check_runs, head_sha, check_name=MERGE_READINESS_CHECK):
    """Classify the merge-readiness evidence for ONE exact commit. `check_runs`
    is the `check_runs` array from GitHub's
    `repos/{owner}/{repo}/commits/{sha}/check-runs` response. Returns one of:

      green           - the gate ran for this commit, completed, and succeeded.
      missing         - no check run by that name is present at all.
      pending         - present but not `completed` (queued / in_progress / ...).
      sha_mismatch    - a matching run reports a different `head_sha`.
      not_successful  - completed with any conclusion other than `success`
                        (failure, cancelled, skipped, timed_out, neutral, ...).

    Issue #385: the hosted release workflow proved only that it was dispatched
    from main. Branch protection shows how a commit ENTERED main, not that
    post-merge evidence exists for the exact commit about to be tagged, and the
    release skill's hard rules say MUST NOT tag on a red suite.

    Fail-closed throughout: unparseable input is `missing`, and several runs
    share one name only when a re-run is in flight - we cannot tell which
    verdict is authoritative, so EVERY matching run must be green."""
    if not isinstance(check_runs, list):
        return "missing"
    matching = [run for run in check_runs
                if isinstance(run, dict) and run.get("name") == check_name]
    if not matching:
        return "missing"
    if any(run.get("head_sha") != head_sha for run in matching):
        return "sha_mismatch"
    if any(run.get("status") != "completed" for run in matching):
        return "pending"
    if any(run.get("conclusion") != "success" for run in matching):
        return "not_successful"
    return "green"


def peel_tag(ls_remote_text, tag):
    """Resolve the COMMIT a remote tag names, from `git ls-remote --tags`
    output. Returns "" when the tag is absent.

    An annotated tag's own object id is not the commit it points at; the
    peeled `refs/tags/<tag>^{}` line is. Issue #380: the workflow treated any
    remote hit as a resumable publish and skipped tag creation without ever
    comparing the tag to `GITHUB_SHA`, so a stale tag could be accepted as a
    successful rerun and a Release published for the wrong commit. Matching is
    exact on the ref name, so `v2.6.0` is never resolved from `v2.6.0-beta.1`."""
    if not isinstance(ls_remote_text, str) or not isinstance(tag, str):
        return ""
    direct = peeled = ""
    ref = f"refs/tags/{tag}"
    for line in ls_remote_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        if name == ref + "^{}":
            peeled = sha
        elif name == ref:
            direct = sha
    return peeled or direct


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
      select-target <ca> <ca-codex> <ca-sandbox> <ca-pi>
                                               prints one of RELEASE_TARGETS,
                                               or none | multiple | arity
      merge-readiness <head_sha> <checks_json> prints green | missing | pending |
                                               sha_mismatch | not_successful
      peel-tag <tag>                           stdin=`git ls-remote --tags` -> commit sha / ""

    The three release.yml subcommands print a LABEL and exit 0; the workflow
    cases on the label with a fail-closed `*)` arm, so an unrecognised label -
    or a crash, which yields no label at all - refuses the dispatch either way.
    Returns a process exit code."""
    import sys
    if not argv:
        sys.stderr.write(
            "usage: _releaselib.py {last-tag|notes-match|dates-consistent|classify"
            "|select-target|merge-readiness|peel-tag} ...\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "last-tag" and len(rest) <= 1:
        # No argument keeps ca's series, so the existing invocation is unchanged.
        print(last_tag_select(sys.stdin.read().split(), *(rest or ())))
        return 0
    if cmd == "tag-prefix" and len(rest) == 1:
        # One source of truth for a namespace: the release skill asks for the
        # prefix rather than restating four of them in prose.
        prefix = RELEASE_TAG_PREFIXES.get(rest[0])
        if prefix is None:
            sys.stderr.write(f"unknown release target: {rest[0]}\n")
            return 2
        print(prefix)
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
    if cmd == "select-target" and len(rest) == len(RELEASE_TARGETS):
        print(select_release_target(*rest))
        return 0
    if cmd == "merge-readiness" and len(rest) == 2:
        import json
        try:
            runs = json.loads(_read(rest[1]))
        except ValueError:
            runs = None  # unreadable/unparseable evidence is no evidence
        print(classify_merge_readiness(runs, rest[0]))
        return 0
    if cmd == "peel-tag" and len(rest) == 1:
        print(peel_tag(sys.stdin.read(), rest[0]))
        return 0
    sys.stderr.write(f"_releaselib.py: bad invocation: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
