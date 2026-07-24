---
description: Zero-onboarding, read-only dry-run of the reviewer fleet against the current uncommitted diff. Predicts reviewers, runs the state-free secret scan, writes nothing.
argument-hint: (none)
---

# {{CMD:preview}} — reviewer-fleet dry-run

See what codeArbiter would do to your real code before paying any onboarding cost. This is a
read-only dry-run against the current uncommitted diff: it predicts which reviewers the change
would dispatch, runs the checks that need no project rules, and reports. It never writes state.

It requires no `{{CMD:init}}`, no `.codearbiter/` directory, and no decompose or create-context
interview. It functions in a repo that never opted in, and it modifies nothing: not the worktree,
not the index, not `.codearbiter/`. `git status` is unchanged by a run.

## Flow

1. **Collect the diff.** Call the thin entry hook `preview.py` in `diff` mode, which wraps
   `collect_diff` from `{{PLUGIN_ROOT}}/hooks/_previewlib.py`. It unions HEAD-vs-worktree
   changes, staged changes, and untracked files (forward-slash paths). Run it from the project
   root so `_previewlib`/`_hooklib` resolve on the same `sys.path`:
   ```
   python3 "{{PLUGIN_ROOT}}/hooks/preview.py" diff || python "{{PLUGIN_ROOT}}/hooks/preview.py" diff
   ```
   If the result is empty (clean tree, or not a git repo), print a friendly **"Nothing to
   preview"** line and STOP. This is a clean exit, not an error: no stack trace, no failure.

2. **Predict reviewers by path.** Read the reviewer-to-path matrix at
   `{{PLUGIN_ROOT}}/includes/review-matrix.md`. That include is the single source of truth
   for which reviewer is dispatched when scope touches a given path: do NOT restate, fork, or
   inline a second copy of the table here. For each changed path, list the reviewers that WOULD
   dispatch and name the triggering path for each. This is the same mapping `{{CMD:review}}` uses, so
   the predicted set matches what a real review would dispatch.

3. **Run the state-free secret scan.** Call the thin entry hook `preview.py` in `secrets` mode,
   which wraps `scan_secrets` from `{{PLUGIN_ROOT}}/hooks/_previewlib.py`. It reads each
   changed file's current content and returns `SecretFinding(path, line_no, snippet)` for every
   credential line, with the secret VALUE already masked to `****` in `snippet`:
   ```
   python3 "{{PLUGIN_ROOT}}/hooks/preview.py" secrets || python "{{PLUGIN_ROOT}}/hooks/preview.py" secrets
   ```
   Report each finding by `path:line_no` with its redacted snippet. The snippet arrives already
   masked: never reconstruct or print a raw secret value.

## Report

Emit one clear report with these parts:

- **Changed files** — the reviewed-file set from step 1, each with its change kind(s) (unstaged,
  staged, untracked).
- **Predicted reviewers** — per the matrix, which reviewers would dispatch and the triggering path
  for each. These are predicted (would-dispatch), not run here.
- **Secret findings** — the results of the real scan from step 3, by `path:line_no` with the
  redacted snippet, marked as found (ran locally), at BLOCK severity. State "none found" when the
  scan is clean.
- **Onboarding nudge** — close with one line: the full gated review comes via `{{CMD:init}}` then
  `{{CMD:review}}`.

## Distinct from {{CMD:doctor}}

This reports reviewer and gate behavior on the current diff. It makes NO hook-probe claims and says
{{IF:pi}}nothing about wrapper wiring or the active-dispatch coverage gap: that is `{{CMD:doctor}}`.
{{ELSE}}nothing about whether the install's hooks fire: that is `{{CMD:doctor}}`.{{END}} Do not blend the two.

## When NOT to use

- An onboarded repo wanting the full gated verdict → `{{CMD:init}}` then `{{CMD:review}}`.
{{IF:pi}}- Inspecting wrapper wiring and the active-dispatch coverage gap → `{{CMD:doctor}}`.
{{ELSE}}- Proving the install's hooks actually fire → `{{CMD:doctor}}`.{{END}}
- A question about the code → `{{CMD:btw}}`.

## Hard gate

- Read-only. MUST NOT write, create, or modify any file, including anything under `.codearbiter/`;
  MUST NOT stage or commit. `git status` MUST be unchanged after a run.
- MUST NOT require, trigger, or error on missing `{{CMD:init}}`, `.codearbiter/` state, or the
  decompose / create-context interview.
- MUST NOT print a raw secret value: the lib returns the snippet already redacted, and the report
  carries only that masked form.
- An empty diff or a non-git directory MUST yield the "Nothing to preview" message and a clean
  exit, never a stack trace.
- MUST treat the reviewer prediction as predicted (would-dispatch) and the secret scan as found
  (ran locally): it MUST NOT attribute fabricated findings to any predicted reviewer.
