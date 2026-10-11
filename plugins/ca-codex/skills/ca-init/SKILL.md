---
name: ca-init
description: Opt this repo into codeArbiter — scaffold the root-level .codearbiter/ state store.
argument-hint: "[--stage N] [--greenfield|--brownfield] | --check"
---

# $ca-init — first-run scaffold

Stand up the root-level `.codearbiter/` project-state store that opts a repo into arbiter
management. This is the v2 replacement for vendoring/`init-vendor`: no symlinks, no shims, no dual
root. It writes the activation flag and the empty state files, then hands off to the populator.

`.codearbiter/CONTEXT.md` frontmatter `arbiter: enabled` is the single activation flag — it gates
the SessionStart persona injection. The scaffolded
`CONTEXT.md` is a **stub** (no initialization sentinel), so after scaffolding the project still needs
populating before normal operation.

<!-- catalog-command-modes:start -->
## Explicit population strategies

<!-- command-mode:--greenfield legacy-route:decompose -->
`--greenfield` selects the exact [skills/ca-decompose/SKILL.md](../ca-decompose/SKILL.md) workflow.

<!-- command-mode:--brownfield legacy-route:create-context -->
`--brownfield` selects the exact [skills/ca-create-context/SKILL.md](../ca-create-context/SKILL.md) workflow.
An initialized refresh is routed through `$ca-status drift` and the existing
`context-check` owner after an explicit scoped or full selection; `--brownfield`
keeps its initial-population lock.

### Brownfield host prerequisites

Scaffolding enables governance and may install Git hooks before population.
It does not qualify the host for context extraction. Before selecting
`--brownfield` or automatically routing existing source to brownfield
population, inspect the installed
context-creation containment profile in
[routines/context-creation/SKILL.md](../../routines/context-creation/SKILL.md), under that exact heading.
The active host needs an observed context-specific child profile with enforced
read-only containment and report delivery, plus the existing native context
writer and approval support. Ordinary unrestricted collaboration agents on
Codex desktop/Windows do not satisfy that requirement. The repository-only
Claude preparation fixture is neither a shipped consumer route nor proof of
a qualified host.

When these prerequisites are unavailable or unknown, report the missing
capability before invoking the scaffolder. Keep a fresh repository unactivated
and retain every byte of any existing partial state. Name the loaded package,
actual host limitation, selected population route and next missing prerequisite
in the handoff; leave unobserved qualification and prior operation identities
unknown. Resume on a host only after fresh containment and writer qualification,
using the existing interrupted-population recovery procedure. No supported
destination is implied by this guidance.

This is a workflow preflight. The low-level scaffolder has no native scout
capability attestation input and does not enforce or prove this assessment.
Its successful exit, `--check` inventory or enabled stub never establishes
population readiness. Do not fabricate a profile, receipt, context document
or initialization sentinel to pass the later gates.

The two flags are mutually exclusive and neither may combine with `--check`. `--stage N` may
accompany one only while `.codearbiter/CONTEXT.md` is absent: scaffold at that stage, then enter the
selected workflow. When an uninitialized stub already exists, skip the refusing scaffolder and enter
the selected workflow directly. An initialized marker or source-shape mismatch retains the selected
legacy workflow's BLOCK. Without an explicit strategy, continue with the unchanged auto-detection
procedure below.
<!-- catalog-command-modes:end -->

## Procedure

Before opening an active host session in an unfamiliar repository, a trusted
external process may inspect an explicit directory with
`python "${PLUGIN_ROOT}/hooks/init-codearbiter.py" --check --passive --root PATH`.
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
   python "${PLUGIN_ROOT}/hooks/init-codearbiter.py"
   ```

   It is idempotent and refuses if `.codearbiter/CONTEXT.md` already exists — it never overwrites
   state. Pass `--stage N` to set the initial maturity value (default `1`). Use `--check` to report
   state without creating anything.

2. It creates `.codearbiter/` with: `CONTEXT.md` (`arbiter: enabled`, `stage: N`, stub body),
   `open-tasks.md`, `open-questions.md`, `overrides.log` (audit header), and `last-checkpoint` (`0`).

3. **Then route to the populator** — the stub is not yet usable:
   - **Source code already exists** in the repo → route to `$ca-create-context` (brownfield: scouts
     read the codebase and synthesize the full context, writing the initialization sentinel).
   - **Greenfield** (no meaningful source) → route to `$ca-decompose` (layered interview).

   The populator is **mandatory, not optional**: it authors `tech-stack.md`, `coding-standards.md`,
   and `security-controls.md` (and writes the initialization sentinel). The pipeline gates BLOCK on
   reading those files — `writing-plans` and `tdd` need `tech-stack.md`, the security gates need
   `security-controls.md` — so `$ca-feature` run on a freshly-scaffolded stub will STOP at pre-flight
   until the populator has run. `session-start` surfaces this as `NOT INITIALIZED` every session.

4. Report what was created and which populator you are routing to.

## When NOT to use

- `.codearbiter/` already scaffolded → the scaffolder refuses; run `$ca-create-context` or
  `$ca-decompose` to populate, or `$ca-status` to see state.
- You only want to re-check detection state → run the scaffolder with `--check`.

## Hard gate

MUST NOT hand-author `.codearbiter/CONTEXT.md` frontmatter — the scaffolder is the sanctioned path so
the activation flag and state-file shapes match what the hook parses. MUST NOT mark a
stub initialized; only the populator writes the initialization sentinel.
