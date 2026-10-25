---
description: Opt this repo into codeArbiter — scaffold the root-level .codearbiter/ state store.
argument-hint: "[--stage N] [--greenfield|--brownfield] | --check"
---

# {{CMD:init}} — first-run scaffold

Stand up the root-level `.codearbiter/` project-state store that opts a repo into arbiter
management. This is the v2 replacement for vendoring/`init-vendor`: no symlinks, no shims, no dual
root. It writes the activation flag and the empty state files, then hands off to the populator.

`.codearbiter/CONTEXT.md` frontmatter `arbiter: enabled` is the single activation flag — it gates
{{IF:claude}}both the SessionStart persona injection and the arbiter statusline segments{{ELSE}}the SessionStart persona injection{{END}}. The scaffolded
`CONTEXT.md` is a **stub** (no initialization sentinel), so after scaffolding the project still needs
populating before normal operation.

<!-- catalog-command-modes:start -->
## Explicit population strategies

<!-- command-mode:--greenfield legacy-route:decompose -->
`--greenfield` selects the exact `{{PLUGIN_ROOT}}/commands/decompose.md` workflow.

<!-- command-mode:--brownfield legacy-route:create-context -->
`--brownfield` selects the exact `{{PLUGIN_ROOT}}/commands/create-context.md` workflow.
An initialized refresh is routed through `{{CMD:status}} drift` and the existing
`context-check` owner after an explicit scoped or full selection; `--brownfield`
keeps its initial-population lock.

### Brownfield preparation

Confirm the intended repository, existing state, selected outcome and actual
host permissions before activation. Scaffolding enables governance and may
install Git hooks; it does not prove context correctness or host enforcement.
For existing source, use bounded inspection and the safe installed context
writer in `{{PLUGIN_ROOT}}/skills/context-creation/SKILL.md`. Scoped agents are
optional. Ordinary native Windows work does not require a special scout sandbox,
profile attestation or per-document artifact approval.

If a real host permission or the installed safe writer is unavailable, report
the exact operation and retain current state. Continue independent authorized
inspection; do not fabricate a profile, receipt, context document or initialized
marker. Successful scaffold or `--check` output is inventory, not evidence that
population or a live host probe completed.

The two flags are mutually exclusive and neither may combine with `--check`. `--stage N` may
accompany one only while `.codearbiter/CONTEXT.md` is absent: after checking the repository and host permissions,
scaffold at that stage, then enter the
selected workflow. When an uninitialized stub already exists, skip the refusing scaffolder and enter
the selected workflow directly. An initialized marker or source-shape mismatch retains the selected
legacy workflow's BLOCK. Without an explicit strategy, continue with the unchanged auto-detection
procedure below under the same repository and host permissions.
<!-- catalog-command-modes:end -->

## Procedure

Before opening an active host session in an unfamiliar repository, a trusted
external process may inspect an explicit directory with
`python "{{PLUGIN_ROOT}}/hooks/init-codearbiter.py" --check --passive --root PATH`.
This bounded read checks only that directory's `.codearbiter/CONTEXT.md` activation
marker and prints a JSON inventory for Git hooks/exclusions, background Git fetch,
update refresh, and inference transport. Every effect is `performed: false`, with
capability `unverified` and authorization `not_established`. The root is caller
supplied and unverified; no Git command, repository script, network request,
global setting edit, or model source read occurs. Sensitive/excluded source paths
must be inventoried separately before any model read. If an active host session
has already started, this inspection cannot undo its earlier startup effects.

Activation is a separate step under the applicable host, network, repository-write,
and inference permissions. The normal scaffold and active SessionStart behavior
below remain in force for repositories that already opted in.

1. Run the scaffolder against the repo's git toplevel (resolved by the script):

   ```
   python "{{PLUGIN_ROOT}}/hooks/init-codearbiter.py"
   ```

   It is idempotent and refuses if `.codearbiter/CONTEXT.md` already exists — it never overwrites
   state. Pass `--stage N` to set the initial maturity value (default `1`). Use `--check` to report
   state without creating anything.

2. It creates `.codearbiter/` with: `CONTEXT.md` (`arbiter: enabled`, `stage: N`,
   `context-format: html`, stub body), `open-tasks.md`, `done-tasks.md`, `open-questions.md`,
   `overrides.log` (audit header), `last-checkpoint` (`0`) and a `.gitattributes` that keeps Git
   from converting the line endings of native HTML artifacts. Narrative context is HTML knowledge
   under `.codearbiter/context/` (see `{{PLUGIN_ROOT}}/includes/knowledge.md`); `--format markdown`
   scaffolds the legacy Markdown documents instead.

3. **Then route to the populator** — the stub is not yet usable:
   - **Source code already exists** in the repo → route to `{{CMD:create-context}}` (brownfield: bounded inspection and optional agents
     read the codebase and synthesize the full context, writing the initialization sentinel).
   - **Greenfield** (no meaningful source) → route to `{{CMD:decompose}}` (resumable interview).

   The populator is **mandatory, not optional**: it authors `tech-stack.md`, `coding-standards.md`,
   and `security-controls.md`, or their HTML knowledge documents (and writes the initialization
   sentinel). The pipeline reads that context — `writing-plans` and `tdd` need `tech-stack.md`, the
   security gates need `security-controls.md` — so `{{CMD:feature}}` run on a
   freshly-scaffolded stub will STOP at pre-flight until the populator has run. Unknown facts may
   stay unknown; population does not need every question answered. `session-start` surfaces this
   as `NOT INITIALIZED` every session.

4. Report what was created and which populator you are routing to.

## When NOT to use

- `.codearbiter/` already scaffolded → the scaffolder refuses; run `{{CMD:create-context}}` or
  `{{CMD:decompose}}` to populate, or `{{CMD:status}}` to see state.
- You only want to re-check detection state → run the scaffolder with `--check`.

## Hard gate

MUST NOT hand-author `.codearbiter/CONTEXT.md` frontmatter — the scaffolder is the sanctioned path so
the activation flag and state-file shapes match what the hook{{IF:claude}} and statusline{{END}} parse{{IF:claude}}{{ELSE}}s{{END}}. MUST NOT mark a
stub initialized; only the populator writes the initialization sentinel.
