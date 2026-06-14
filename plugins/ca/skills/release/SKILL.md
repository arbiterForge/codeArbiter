---
name: release
description: The single permitted path to a version tag. Routed to when the user invokes /release on a non-default branch with a green suite. Derives the SemVer bump from Conventional-Commits history since the last tag, rolls the commits into CHANGELOG.md, writes an annotated tag, and on authorization publishes it as a GitHub Release with the changelog section as its notes. A release commit, if needed, routes through commit-gate; the tag and Release are never published without explicit authorization.
---

# release

The single permitted path to a version tag. Routed to when the user invokes `/release`. Derive the bump from the commit log, update the changelog, tag — nothing more.

## Pre-flight

Read these, or STOP and surface the gap — never guess:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the default-branch name and project context.
- `git status` must be clean. A dirty tree STOPs — commit or stash via `commit-gate` first.
- The current branch MUST NOT be `main`, `master`, or the default branch. Release lands through the normal branch/PR path; if HEAD is the default branch, STOP.
- `git describe --tags --abbrev=0` identifies the last tag. No tags → `LAST_TAG=<none>`, treat the full history as the window. Set the base version to `0.0.0`.
- The commit set `LAST_TAG..HEAD` must be non-empty. If empty, STOP — nothing to release.
- **farm.js build check:** if `plugins/ca/tools/farm.ts` was modified in the release window (`git log LAST_TAG..HEAD -- plugins/ca/tools/farm.ts`), verify that `plugins/ca/tools/farm.js` is up to date by rebuilding: `cd plugins/ca/tools && npm run build`. A stale `farm.js` (built from an older `farm.ts`) is a release blocker — the plugin ships `farm.js`, not `farm.ts`. If the rebuild produces changes, commit them through `commit-gate` before tagging.

## Phase 1 — Version & changelog · gate: BLOCK

Derive the bump mechanically from the commit log; do not guess it.

1. Read every commit in the window: `git log LAST_TAG..HEAD --pretty=format:%H%n%s%n%b%n----`.
2. Classify each subject by its Conventional-Commits prefix and apply the highest-precedence bump:
   - `BREAKING CHANGE:` footer or `!` after the type/scope → **major**.
   - else any `feat` → **minor**.
   - else any `fix`, `perf`, `refactor` → **patch**.
   - `test` / `docs` / `chore` / `ci` only → no bump. If the whole window is non-bumping, STOP — there is nothing to release.
3. Compute the next version and confirm it is strictly greater than `LAST_TAG`. Present the version and the per-commit classification to the user for confirmation.
4. Roll the `CHANGELOG:` footers from each `feat` / `fix` / `perf` commit into a new `## vMAJOR.MINOR.PATCH — YYYY-MM-DD` section in the repo's `CHANGELOG.md`, grouped Added / Fixed / Performance. Prior sections stay intact. Create the file with a `# Changelog` heading if absent. A `feat`/`fix` commit missing its footer is a one-line `[NEEDS-TRIAGE]` finding — surface it, do not auto-fill. The changelog is a user-facing deliverable: apply `${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/core.md` §3.A (no prose-separator em-dashes in the entry prose) and §3.B (copy self-audit), and the `medium-documents` §7.A.1 changelog guidance, to each rolled entry.
5. If the changelog edit needs to land as a commit before tagging, route it through `commit-gate`. Do not reimplement the commit path here.

Gate: version confirmed, strictly monotonic, and matching the commit log; `CHANGELOG.md` updated. BLOCK if the classification disagrees with the log or the window is non-bumping.

## Phase 2 — Tag & report · gate: BLOCK

1. Compose the annotated tag from the Phase 1 section plus a `Released-at: YYYY-MM-DD` footer. Tag with `git tag -a vMAJOR.MINOR.PATCH -F <message-file>` — never `-m` for multi-line content, never an interactive editor. If the tag already exists, STOP.
2. Report: version, bump rationale, the per-commit classification, the changelog section, and the tag SHA.
3. MUST NOT push the tag or create the GitHub Release here. Publication is Phase 3, a separate step the user authorizes after reading the report.

Gate: the annotated tag exists locally and the report is delivered. Nothing is published.

## Phase 3 — Publish · gate: STOP

The tag and the GitHub Release publish together, and only after the user explicitly authorizes publication. This phase does not run until then; absent authorization, nothing leaves the local repo.

On authorization:

1. Push the tag: `git push origin vMAJOR.MINOR.PATCH`.
2. Create the GitHub Release from the **same changelog section composed in Phase 1** — reuse it as the notes, never re-derive or hand-write them: `gh release create vMAJOR.MINOR.PATCH --title "<title>" --notes-file <Phase-1 section file> --latest --verify-tag`. The title follows the existing convention `codeArbiter MAJOR.MINOR.PATCH: <summary>`, with no em-dash separator.
3. Handle edge cases explicitly, never silently: if a Release for the tag already exists, report it and skip creation (the tag push may already have landed); if `gh` is missing, unauthenticated, or the call fails, STOP and print the exact `gh release create` command so publication can be finished by hand rather than left half-done.
4. Report the Release URL.

Gate: with authorization, the tag is pushed and the GitHub Release exists (or, on failure, the exact manual command was surfaced). Without authorization, nothing is published.

## Hard rules

- MUST NOT tag on a red suite — `commit-gate` enforces green on every commit reaching HEAD; do not re-run it, but do not tag if the last suite was red.
- MUST NOT write to `main`, `master`, or the default branch, and MUST NOT force-push. Releases land through the normal branch/PR path.
- MUST NOT push the tag or create the GitHub Release without explicit user authorization; they publish together in Phase 3, even after the local tag composes.
- MUST use the Phase-1 changelog section verbatim as the GitHub Release notes — never re-derive or hand-write them.
- MUST NOT guess the version — derive it from the commit log. A `feat` in the window cannot ship as a `patch`.
- MUST NOT auto-fill a missing `CHANGELOG:` footer — surface it as `[NEEDS-TRIAGE]`.
- MUST NOT tag a non-bumping window — `test`/`docs`/`chore`/`ci`-only sets do not release.
