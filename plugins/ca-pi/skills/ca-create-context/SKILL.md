---
name: ca-create-context
description: Build source-backed project context through bounded inspection, optional agents, and record-level knowledge writes.
argument-hint: (none)
---

# context-creation

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `/ca-init --brownfield` for new usage. This installed route remains
> functional under the command-route compatibility policy at <plugin-root>/includes/command-compatibility.md;
> continue with the unchanged brownfield workflow below.
<!-- catalog-compatibility-notice:end -->

Wrap an existing codebase in project state, without guessing. Routed to by `/create-context`, and by startup when `.codearbiter/CONTEXT.md` exists but carries no `<!--INITIALIZED-->` body marker and meaningful source code is present. When no meaningful source exists, this is the wrong skill — route to `decompose` instead.

This back-fills from existing source. It complements `/ca-init`, which scaffolds an empty `.codearbiter/` for a fresh project; here the context is derived from what is already on disk. Load `<plugin-root>/includes/knowledge.md` for the record vocabulary and the `knowledge.py` verbs used below.

An initialized refresh is requested through `/ca-status drift` and the
existing `context-check` owner after an explicit scoped or full selection. An
explicit initialized brownfield project-model request also uses the existing
`decompose` owner for intended target, phases, and candidate work. This
initial-population route keeps its `<!--INITIALIZED-->` lock; an initialized
repository never clears the marker or re-enters Phase 6 to refresh content.

## Pre-flight

Read these, or STOP and surface the gap — never guess project identity or a command:

- `<project-root>/.codearbiter/CONTEXT.md` — if it already carries `<!--INITIALIZED-->`, context exists. Stop and route to normal operation.
- `knowledge.py format`. A `markdown` scaffold is an older one: offer `knowledge.py convert` before writing. Read every returned Markdown section, add its meaning as records or notes, then map each section ID to its saved references (use `[]` only for `content=false`). Finish with `knowledge.py convert --finish <token> --coverage @checklist.json`. If the user keeps the Markdown format, load `<plugin-root>/routines/context-creation/references/markdown-format.md` and follow that unchanged procedure instead of this one; never convert silently.
- The repository root listing (one level deep) — the source surface this skill extracts from.

The excluded set (not "meaningful source"): `.git/`, `.codearbiter/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`, `.gitmodules`, and standard tooling dotfiles (`.editorconfig`, `.prettierrc`, etc.). Meaningful source MUST exist beyond it.

## Resume after an interrupted initial population

Inventory the actual `.codearbiter/` files first. If the scaffold stopped partway
through, rerun `init-codearbiter.py --root <exact repository root>` only while the
project is uninitialized; it creates only absent files. Never clear the directory,
reset a marker, or replace an existing task board, question board or append-only
audit record to make a retry pass.

Run `knowledge.py create-missing` and read each document's records: they are the
progress already saved. Every `knowledge.py` write is retry-safe — an identical
record is reused and a lost response replays — so continue from what is there
instead of starting over. A refused write names a changed document; read it again
before retrying.

## Phase 1 — Pre-flight confirmation · gate: BLOCK

Confirm the repository is a brownfield codebase ready for bounded source inspection:

1. Confirm `<!--INITIALIZED-->` is absent from `CONTEXT.md`.
2. Confirm meaningful source code is present beyond the excluded set.
3. Identify the primary source directories (`src/`, `backend/`, `frontend/`, `lib/`, `app/`, or equivalent).

State the finding to the user: existing source detected, beginning bounded source inspection.

Gate: `<!--INITIALIZED-->` absent AND meaningful source present. If the marker is present, stop and route to normal operation. If no meaningful source exists, stop and route to `decompose`. Neither condition met → do not proceed.

## Phase 2 — Bounded inspection

Use direct bounded inspection or optional scoped agents, whichever reduces
repeated reading for this repository. Cover six logical categories for initial
or explicitly full work; a scoped refresh inspects only the selected affected
categories and retains prior coverage separately. Six categories do not require
six agents or parallel execution. Start with paths and targeted searches, then
read only the source needed to support the current claims. Keep actual host
permissions, excluded paths and secret-handling rules in force. Do not run
repository scripts merely because a manifest declares them.

When delegation helps, give each agent a finite path/category assignment,
current source identity, output limit and stopping condition. Respect the host's
actual concurrency and tool limits. Retain failed, partial and conflicting
reports; narrow an oversized assignment instead of truncating it or repeatedly
relaunching unchanged work. Direct inspection may resolve missing coverage or
check a contested claim. A role label or a read-only instruction is not evidence
of containment or independent verification. Describe the tools and boundaries
actually observed, without claiming a trusted sandbox from an agent name.
A separately required containment policy still applies to its own scope; a
repository-only profile fixture does not impose that policy on ordinary work.

The categories are:

- **A — Tech stack.** Read `package.json`, lockfiles, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`, `*.gemspec`, `Gemfile`. Report languages, runtime versions, frameworks, key dependencies, the dependency manager, license fields. Additionally report, at the repository root only: which of `package.json` / `pyproject.toml` / `Cargo.toml` / `composer.json` carry a version field (candidate release manifests), which of `CHANGELOG.md` / `CHANGES.md` / `HISTORY.md` are present (candidate changelogs), and any existing tag naming convention visible in the repo (e.g. a `v*` tag) — the inputs Phase 3/5 use to draft `.codearbiter/release-targets.md`.
- **B — Infrastructure.** Read CI/CD config (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`), `Dockerfile*`, `docker-compose*.yml`, `Makefile`, `*.tf`, IaC. Report CI/CD platform, build/test/lint commands, deployment targets, environment names, containerization, IaC tool.
- **C — Architecture.** Read the source tree (names and structure only), entry points (`main.ts`, `index.ts`, `app.py`, `server.go`), and imports in entry points only. Report component list, entry points, module boundaries, architectural pattern, public interfaces.
- **D — Security posture.** Read auth files (`auth*`, `middleware*`, `guard*`, `jwt*`, `session*`, `oauth*`), crypto import lines, secret-loading sites (`process.env`, `os.environ`, vault/KMS call sites — paths and line numbers only, never values), `.env.example` (never `.env`). Report auth mechanism, crypto libraries, secret-loading patterns (paths + lines, no values), vault/KMS integration, hardcoded-secret risk files (paths only).
- **E — Testing.** Read test files and test config (`vitest.config.*`, `jest.config.*`, `pytest.ini`, Makefile test flags), coverage config. Report test framework, runner command, coverage tool, coverage thresholds in config, naming convention, approximate test count by type, fixtures.
- **F — Data model.** Read migration files (`migrations/`, `drizzle/`, `alembic/`, `db/migrate/`), schema definitions (`schema.ts`, `*.prisma`, `*.sql`, `models/`), ORM config, DB connection config (keys only, never credentials). Report database type, ORM/query builder, entity names, migration tool, approximate entity count, multi-tenancy patterns.

Keep a source-bound evidence inventory: each claim tied to its category,
searched scope, path and line, and whether it was observed, inferred or unknown.
A record's `source_refs` and the document baseline commit bind it to the source
as it was; like any source hash binds bytes, that does not verify a claim's
meaning. Never forward secret values. Negative findings state where and how the search ran, not universal
absence.

`_contextreportlib.admit_scout_attempt` and `join_scout_reports` remain useful
for bounded structured agent reports when that transport is used. They validate
report shape and declared coverage, not permission, containment or semantic
truth. A scoped join has `full_coverage: false`; do not relabel it as a full
scan. Plain evidence from direct inspection needs the same truthful scope,
without a synthetic scout envelope or delivery ticket.

Proceed with supported claims and explicit gaps. A full run accounts for all
six logical categories, including justified inapplicability and named unknowns;
failed or missing work never counts as inspected coverage. Recheck changed
sources before a dependent write. Independent work can continue while a
material unresolved fact or actual decision is addressed.

## Phase 3 — Synthesis · gate: BLOCK

Turn the evidence into source-bound records across the five content documents.
For initial or explicitly full onboarding, account for all six logical domains; a
scoped refresh changes only its declared affected domains and makes no new full-coverage claim. Map source to destination:

| Evidence category | Destination document and record types |
|---|---|
| Stack, infrastructure, tests | `tech-stack`: `fact`, `dependency`, `command` |
| Architecture, source ownership | `code-map`: `component`, `interface`; `coding-standards`: `convention` |
| Security boundaries | `security-controls`: `constraint`, `observation` |
| Stack/release candidates | `.codearbiter/release-targets.md` when supported |
| All applicable domains | `project`: `identity`, `goal`, `scope`, `exclusion` |

Give each record its actual `basis`. A record read from the repository is
`source-observed` and cites its source in `source_refs` (add the file to the
document's sources). Mark reasoned conclusions `inferred`. Scope a record to the
paths it governs in `scope.paths`, so a task touching those paths receives it;
leave repository-wide records unscoped. For each retained record, name its
purpose, owning source and actual consumer (or a specific retention reason).
Keep observed, inferred, proposed and approved content separate through `basis`;
nothing a record says is approved unless the user decided it. Commands are
`command` records with
their real `cwd`, `run_state: unrun`, and the purpose (`test`, `lint`,
`typecheck`, `build`, `format`, `secrets-scan`, `run`, `other`):
never convert a package script into a passed verification. Keep unsupported fields `unknown`;
make no blanket security claim from absence. Confidence describes evidence
strength, not governance: confidence never grants normative authority. A
well-supported observation may back a source-bound fact, but it cannot approve a
rule, permission, scope change or publication. Mark indirect inferences
`inferred`, naming their signal and recheck need.

Preserve existing effective local instructions at their native precedence and
human ownership. Cite an AGENTS or equivalent file without copying it into a new
local rule. Treat an upstream instruction, README convention or accepted
upstream ADR as source-scoped evidence; use a source-bound ADR reference in
`related_refs` without manufacturing a local decision. If an upstream rule
conflicts with a local constraint, keep both citations for Phase 4 and do not
silently displace either. There is no new task or ADR from an observed pattern.

Distinguish evidence availability from category outcome. Record each category
as `observed`, `not_applicable`, `not_found_in_scope`, `not_inspected` or
`ambiguous` with its scope and reason (an `observation` record for outcomes
other than `observed`); failed or oversized reports are gaps, not evidence of
absence. A `not_found_in_scope` records its searched scope and predicates; it
does not prove universal absence. In a small static project with known tests and
justified no-storage evidence, ask no database question for a scoped test
change. Keep partial-domain uncertainty visible, but ask the user only if a
missing decision affects the current output or selected task.

Use `[CONFIRM-NN]` only for a material user-owned decision that evidence cannot
settle. Give each a sequential ID, the missing choice, why it matters now and
what would resolve it; align IDs with `open-questions.md`. Other unknowns stay
`unknown` records or become a bounded evidence reinspection, not an automatic
interview. Do not synthesize a user deferral.

**`.codearbiter/release-targets.md` is a candidate only when the stack report found exactly one candidate manifest and exactly one candidate changelog at the repository root.** Draft the row then, in the grammar `<plugin-root>/hooks/_releaselib.py`'s module docstring declares — a single-target project needs only `prefix`, `manifest`, `changelog`, `payload`:

```text
<!-- release-targets -->
[app]
prefix: v
manifest: package.json
changelog: CHANGELOG.md
payload: .
latest-eligible: true
<!-- /release-targets -->
```

(`prefix` defaults to `v` unless the report found a different existing tag convention; `payload` is `.` for a single-package repository.) Zero, or more than one, candidate manifest or changelog cannot produce a guessed row. Record the evidence gap; ask about a release target only when that choice is needed now. Otherwise leave this conditional draft absent.

**`latest-eligible: true` is not cosmetic.** `/release`'s own back-fill detector (`detect_candidate_target`) emits it for this exact single-target shape, so a project drafted here and one back-filled through `/release` must agree — omitting it here would default the row's Phase-3 publish to `--latest=false`, and the same project would get different release behavior depending on which lane happened to declare it first.

Gate: every supported claim drafted as a record with its basis, and material
unknowns kept as `unknown` records. No silent omission, invented approval or
invented verification.

## Phase 4 — Gap interview

First reconcile contradictory reports without picking the highest confidence:
retain both conflicting citations and request the smallest independent reinspection
of the disputed source, predicate and snapshot using direct inspection or an
independent agent when useful. A changed or missing source requires fresh
evidence. If the conflict survives, expose both claims and the precise choice
requiring a user ruling; do not overwrite either source.

Build a bounded relevant question set for the current output and selected task.
Use one concise interview to batch independent user-owned decisions by category;
ask each as one targeted choice with its evidence and consequence. Ask only
missing user-owned decisions, not facts already established by records or
existing effective instructions. In particular, do not re-ask an unchanged
local test convention. A database gap unrelated to a documentation or test
change remains visible without blocking that work.

Record each answer as a `user-reported` record with the user's actual
resolution. If the user explicitly defers, keep the question as an open entry on
`open-questions.md` (as `CONFIRM-NN: <description>`, with its date and history).
If unclear, retain the question and ask a focused follow-up;
no synthesized deferral. An explicitly deferred question is still unresolved:
never treat a deferral as approval. An unresolved permission, security, scope or approval
prerequisite blocks dependent work and names the missing authority. Unrelated
uncertainty does not block an expected-success task that has its bounded
relevant question set answered.

## Phase 5 — Project-state write

Write the records with `knowledge.py add` (and `update` for corrections), one
document at a time. Each write is checked and journaled by the native engine.
No document approval receipt or agent profile is required. Preserve existing human
content: an imported note stays until a record replaces it, and is retired with a
reason when it does.

| Owner | Content |
|---|---|
| `project` | Project identity, purpose, scope, primary users, NOT-building. `CONTEXT.md` frontmatter keeps `arbiter: enabled` and one `stage:` number (default `1`); never edit it by hand. |
| `tech-stack` | Languages, frameworks, and `command` records for test, lint, build, coverage and the issue-tracker command (e.g. `gh issue create`). |
| `coding-standards` | Structural patterns, naming conventions, style rules. |
| `security-controls` | Auth mechanism, banned crypto primitives, secret-loading stance. Operative scope blocks stay in `security-controls.md`. |
| `code-map` | Coarse concern-to-path `component` records from supported architecture evidence, scoped by path. |
| `open-questions.md` | Every deferred `CONFIRM-NN: <description>`. A valid empty question board remains empty. |
| Work owner | Preserve existing work IDs, board bytes and history. Keep newly discovered gaps as decomposition `work_item` candidates until the user selects promotion. Then select the work owner through installed `hooks/work.py list --limit 1`, check the candidate origin against active and archived work, and promote to that owner once. Native projects use the stable Work ID returned by `knowledge.py promote`; legacy projects use the board helper through that same promotion route. Never write task rows directly or treat an observed source gap as approval to publish it. If inspection found no backlog, leave the selected owner empty. |
| `overrides.log` | Preserve its append-only audit header and every existing event. A zero-event header is valid; do not fabricate an override. |
| `release-targets.md` | Conditional: written ONLY when Phase 3 drafted it (exactly one candidate manifest, exactly one candidate changelog) or Phase 4 resolved it to a concrete row. **This file is marker-gated protected state; it needs the authoring marker below, unlike every other row in this table.** |

**Authoring marker — required for `release-targets.md` only.** That path is enrolled in the protected-state registry as `marker-gated` (hook `H-22`), so a Write against it is refused unless a fresh authoring marker exists. This lane is a sanctioned author of it, so it mints one immediately before the write and removes it immediately after — the same one-pass shape `/release`'s back-fill lane uses:

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.codearbiter/.markers"
touch "$(git rev-parse --show-toplevel)/.codearbiter/.markers/release-targets-authoring"
```

Write the file, then:

```bash
rm -f "$(git rev-parse --show-toplevel)/.codearbiter/.markers/release-targets-authoring"
```

Skip both commands when this run is not writing `release-targets.md`.

If inspection finds existing decision records (`docs/decisions/`, `adr/`), reference their source and actual status. Do not create local ADRs or infer acceptance from their existence.

Do NOT scaffold any cut doc — see `<plugin-root>/includes/cut-docs.md` for the canonical never-scaffold list. Maturity lives in the `stage:` frontmatter of `CONTEXT.md`, not a separate file.

## Phase 6 — Initialization lock · gate: BLOCK

Run `knowledge.py initialize`. The engine checks that all five knowledge
documents exist and parse and that the task board is well formed, then adds the
standalone `<!--INITIALIZED-->` marker to `CONTEXT.md` in one journaled step.
Unknown records and open questions do not prevent it. A refusal names the
document or board to repair; never append the marker by hand.

Report which categories were inspected, remaining unknowns, documents changed
and actual checks. The marker records completed population; it is not a
certification of semantic truth, host enforcement or test success. Return to
normal authorized work. Existing initialized repositories use refresh; never
remove their marker to repeat onboarding.

## Hard rules

- MUST NOT resolve a user-owned question by guessing — ask it, or keep it open.
- Account for all six logical categories on initial or explicitly full work;
  scoped refresh covers its selected categories without claiming a new full scan.
- Do not claim host containment, independent review or verified semantics from
  an agent label, report shape, source digest or artifact write.
- MUST NOT record a finding that exposes a secret value — paths and line numbers only.
- MUST NOT edit knowledge HTML or `CONTEXT.md` frontmatter by hand.
- MUST NOT scaffold a cut doc — see `<plugin-root>/includes/cut-docs.md` for the canonical never-scaffold list. Maturity is the `stage:` frontmatter number in `CONTEXT.md`.
- MUST NOT run when `CONTEXT.md` already carries `<!--INITIALIZED-->` — stop and route to normal operation.
