---
name: ca-create-context
description: Build source-backed project context through bounded inspection, optional agents, and safe selected writes.
argument-hint: (none)
---

# context-creation

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `$ca-init --brownfield` for new usage. This installed route remains
> functional under the command-route compatibility policy at [includes/command-compatibility.md](../../includes/command-compatibility.md);
> continue with the unchanged brownfield workflow below.
<!-- catalog-compatibility-notice:end -->

Wrap an existing codebase in project state, without guessing. Routed to by `/create-context`, and by startup when `.codearbiter/CONTEXT.md` exists but carries no `<!--INITIALIZED-->` body marker and meaningful source code is present. When no meaningful source exists, this is the wrong skill — route to `decompose` instead.

This back-fills from existing source. It complements `$ca-init`, which scaffolds an empty `.codearbiter/` for a fresh project; here the docs are derived from what is already on disk.

An initialized refresh is requested through `$ca-status drift` and the
existing `context-check` owner after an explicit scoped or full selection. This
initial-population route keeps its `<!--INITIALIZED-->` lock; an initialized
repository never clears the marker or re-enters Phase 6 to refresh content.

## Pre-flight

Read these, or STOP and surface the gap — never guess project identity or a command:

- `<project-root>/.codearbiter/CONTEXT.md` — if it already carries `<!--INITIALIZED-->`, context exists. Stop and route to normal operation.
- The repository root listing (one level deep) — the source surface this skill extracts from.

The excluded set (not "meaningful source"): `.git/`, `.codearbiter/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`, `.gitmodules`, and standard tooling dotfiles (`.editorconfig`, `.prettierrc`, etc.). Meaningful source MUST exist beyond it.

## Resume after an interrupted initial population

Before continuing, inventory the actual `.codearbiter/` files and the prior
operation outcome. If the scaffold stopped partway through, rerun
`init-codearbiter.py --root <exact repository root>` only while the project is
uninitialized. It retains existing regular scaffold files and creates only
absent ones; an initialized, malformed or conflicting scaffold requires review.
Never clear the directory, reset a marker, or replace an existing task board,
question board or append-only audit record to make a retry pass.

For each content document, compare the current document and provenance pair.
Missing, v1 or mismatched provenance is incomplete evidence, not proof that the
human document is disposable. Use explicit `adopt` for supported missing/v1
pairs and `update` for managed v2 pairs; preserve existing content and history.
Inspect the previous operation ID and native transaction before retrying a write
whose response was lost. Retry the identical request and operation ID, or use
native `recover` for a pending transaction. A committed result is read back and
retained. A changed human file, unknown journal or stale expected identity
requires a fresh bounded preview; never overwrite it to make a retry pass.
Resume independent outputs without claiming all documents commit atomically.

Check finalization separately. An initialized marker with matching current
`CONTEXT` provenance is a committed outcome; retain it and route to normal
operation. Otherwise inspect all 13 required output identities and prepare the
native finalization preview. Recover an uncertain earlier finalization first.
Never append the marker by hand. Initialized projects use selected refresh,
with their marker and history retained.

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


Keep a source-bound evidence inventory: category, searched scope and predicates,
claim, path/line citation, content or membership digest and its method, and
observed/inferred/unknown status. Preserve the difference between
`git-blob-normalized-sha1` and `sha256-raw`. A source hash binds bytes; it does
not verify a claim's meaning. Never forward secret values. Negative findings
state where and how the search ran, not universal absence.

`_contextreportlib.admit_scout_attempt` and `join_scout_reports` remain useful
for bounded structured agent reports when that transport is used. They validate
report shape and declared coverage, not permission, containment or semantic
truth. A scoped join has `full_coverage: false`; do not relabel it as a full
scan. Plain evidence from direct inspection needs the same truthful scope and
source bindings, without a synthetic scout envelope or delivery ticket.

Proceed with supported claims and explicit gaps. A full run accounts for all
six logical categories, including justified inapplicability and named unknowns;
failed or missing work never counts as inspected coverage. Recheck changed
sources before a dependent write. Independent work can continue while a
material unresolved fact or actual decision is addressed.

## Phase 3 — Synthesis · gate: BLOCK

Draft the five content documents from current inspection evidence and any
agent reports. For initial or explicitly full onboarding, account for all six
logical domains; a scoped refresh changes only its
declared affected domains and makes no new full-coverage claim. Map source to
destination:

| Evidence category | Destination |
|---|---|
| Stack, infrastructure/commands, tests/verification | `tech-stack.md` |
| Architecture/source ownership, tests/structure | `coding-standards.md` and `code-map.md` |
| Security boundaries | `security-controls.md` (thin) |
| Stack/release candidates | `.codearbiter/release-targets.md` when supported |
| All applicable domains | `CONTEXT.md` (project identity, purpose, scope, NOT-building) |

For each retained claim, name its purpose, owning source and actual consumer
(or a specific retention reason), with its citation and source snapshot.
Separate observed, inferred, proposed and approved content. Keep command
declarations inert, with their actual cwd and declared/verified state: never convert a package script into a passed verification. Keep unsupported fields
unknown; make no blanket security claim from absence. Confidence describes
evidence strength, not governance: confidence never grants normative authority.
A HIGH observation may support a source-bound fact, but it cannot approve a
rule, permission, scope change or publication. Mark indirect inferences as
inferences with their signal and recheck need.

Preserve existing effective local instructions at their native precedence and
human ownership, subject to governing session/platform rules. Cite an AGENTS
or equivalent file without copying it into a new local rule or requiring a new
approval for unchanged use. Treat an upstream instruction, README convention or
accepted upstream ADR as source-scoped evidence; use a source-bound ADR reference
without manufacturing a local decision. If an upstream rule conflicts with a
local constraint, keep both citations for Phase 4 and do not silently displace
either. There is no new task or ADR from an observed pattern.

Distinguish evidence availability from category outcome. Record `observed`,
`not_applicable`, `not_found_in_scope`, `not_inspected` or `ambiguous` with its
scope and reason; failed or oversized reports are gaps, not evidence of absence.
A `not_found_in_scope` records its searched scope and predicates; it does not
prove universal absence. In a small static project with known tests and
justified no-storage evidence, ask no database question for a scoped test
change. Keep partial-domain uncertainty visible, but ask the user only if a
missing decision affects the current output or selected task.

Use `[CONFIRM-NN]` only for a material user-owned decision that evidence cannot
settle. Give each a sequential ID, the missing choice, why it matters now and
what would resolve it; align IDs with `open-questions.md`. Other unknowns stay
explicitly unknown or become a bounded evidence reinspection, not an automatic
interview. Do not synthesize a user deferral.

**`.codearbiter/release-targets.md` is a candidate only when the stack report found exactly one candidate manifest and exactly one candidate changelog at the repository root.** Draft the row then, in the grammar [hooks/_releaselib.py](../../hooks/_releaselib.py)'s module docstring declares — a single-target project needs only `prefix`, `manifest`, `changelog`, `payload`:

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

Gate: every surviving doc drafted with supported claims and explicit material
unknowns. No silent omission, invented approval or invented verification. A
domain with no observed evidence has its coverage and uncertainty represented in the
relevant draft; it does not force an irrelevant interview or an empty file.

## Phase 4 — Gap interview · gate: BLOCK

First reconcile contradictory reports without picking the highest confidence:
retain both conflicting citations and request the smallest independent reinspection
of the disputed source, predicate and snapshot using direct inspection or an
independent agent when useful. A changed or missing source snapshot requires
fresh evidence. If the conflict survives, expose both claims and the precise
choice requiring a user ruling; do not overwrite either source.

Build a bounded relevant question set for the current output and selected task.
Use one concise interview to batch independent user-owned decisions by category;
ask each as one targeted choice with its evidence and consequence. Ask only
missing user-owned decisions, not facts already established by reports or
existing effective instructions. In particular, do not re-ask an unchanged
local test convention. A database gap unrelated to a documentation or test
change remains visible without blocking that work.

For each answer, record the actual outcome under the existing question owner:
resolution with its user authority, or, if the user explicitly defers, a
deferral with date in
`open-questions.md`. If unclear, retain the question and ask a focused follow-up;
no synthesized deferral. An explicitly deferred question is still unresolved:
never treat a deferral as approval. An unresolved permission, security, scope or
approval prerequisite blocks dependent work and names the missing authority.
Unrelated uncertainty does not block an expected-success task that has its
bounded relevant question set answered.

Gate: each material user-owned question has a recorded resolution or actual
explicit deferral; unresolved prerequisites still stop their dependent work.
No question or conflicting citation is silently dropped, and independent
solvable work is not held by an irrelevant domain interview.

## Phase 5 — Project-state write · gate: BLOCK

Prepare the five content documents with the installed writer's `context-preview`, actual source evidence and file-specific provenance. Inspect the proposed diff and source bindings, then use `context-apply` with `preview_ref` and `preview_sha256` under the existing authorization. No document approval receipt or qualified agent profile is required. Preserve existing human content and ownership; review uncertain or consequential claims independently when useful, without treating a review label as proof. Every doc carries actual content — no unresolved placeholder may remain where a value was determined:

| File | Content |
|---|---|
| `CONTEXT.md` | Project identity, purpose, scope, primary users, NOT-building. Frontmatter MUST include `arbiter: enabled` (the activation flag the SessionStart hook keys on) and `stage:` set to a single maturity number (default `1`; the user may raise it if the project is further along). |
| `tech-stack.md` | Languages, frameworks, test runner, lint command, build command, coverage command, issue-tracker command (e.g. `gh issue create`). |
| `coding-standards.md` | Structural patterns, naming conventions, style rules. |
| `security-controls.md` | Thin: auth mechanism, banned crypto primitives, secret-loading stance. Only what a security boundary actually requires. |
| `code-map.md` | A coarse concern-to-path map from supported architecture evidence. A known inapplicable domain is explained in its relevant content document rather than given a fabricated map entry. |
| `open-questions.md` | Every deferred `[CONFIRM-NN]` in `CONFIRM-NN: <description>` form. A valid empty question board remains empty. |
| `open-tasks.md` | Preserve the existing scaffold and task history. **Every new task goes in through the board helper, one call per item — `python3 "${PLUGIN_ROOT}/hooks/taskwrite.py" add "<task>"` — never by writing entries into the file directly** (B-18). The helper owns the board schema the SessionStart hook and statusline parse. If scouts found no backlog, leave a valid empty board intact; do not invent a task. |
| `overrides.log` | Preserve its append-only audit header and every existing event. A zero-event header is valid; do not fabricate an override to make it non-empty. |
| `release-targets.md` | Conditional, unlike every other row above: written ONLY when Phase 3 drafted it at HIGH confidence (exactly one candidate manifest, exactly one candidate changelog) or Phase 4 resolved its `[CONFIRM-NN]` to a concrete row. Left unwritten otherwise — `/release`'s own back-fill lane (or a later `context-creation` run, once the ambiguity resolves) is the sanctioned way to create it, never a guess made here. **This file is marker-gated protected state; it needs the authoring marker below, unlike every other row in this table.** |

**Authoring marker — required for `release-targets.md` only.** That path is enrolled in the protected-state registry as `marker-gated` (hook `H-22`), so a Write against it is refused unless a fresh authoring marker exists. This lane is a sanctioned author of it, so it mints one immediately before the write and removes it immediately after — the same one-pass shape `/release`'s back-fill lane uses:

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.codearbiter/.markers"
touch "$(git rev-parse --show-toplevel)/.codearbiter/.markers/release-targets-authoring"
```

Write the file, then:

```bash
rm -f "$(git rev-parse --show-toplevel)/.codearbiter/.markers/release-targets-authoring"
```

Skip both commands when this run is not writing `release-targets.md`. No other
table entry uses this release-target marker; content documents use the native
paired writer, and task/question/audit history retains its existing owners.

If inspection finds existing decision records (`docs/decisions/`, `adr/`), reference their source and actual status. Do not create local ADRs or infer acceptance from their existence. Keep an unparseable record as a cited uncertainty; a new local decision belongs to its actual owner.

**Provenance and code-map:**

- The installed context writer commits each selected document and its v2 `.codearbiter/.provenance/<doc>.json` record together. Bind each claim to current content or membership evidence, its source, owner and actual consumer. An identity acknowledgement does not stand in for semantic review or an actual user decision. Never write either side of this pair directly.
- Synthesize `.codearbiter/code-map.md` (concern → path → ≤1-line role) from architecture evidence. Use concern headings (`## <concern>`) and column-0 bullets (`- \`path\` — role`). Keep it coarse — module/concern granularity only, no full file listing.

Do NOT scaffold any cut doc — see [includes/cut-docs.md](../../includes/cut-docs.md) for the canonical never-scaffold list. Maturity lives in the `stage:` frontmatter of `CONTEXT.md`, not a separate file.

Gate: all five content documents and their matching v2 provenance pairs are present; `CONTEXT.md` frontmatter carries `arbiter: enabled` and `stage:`; no resolved value is left as a placeholder. The task/question boards and audit file are present through their owning paths. Valid empty boards and a zero-event audit header pass. Deferred `[CONFIRM-NN]` items are recorded in `open-questions.md`.

## Phase 6 — Initialization lock · gate: BLOCK

Lock the project state as initialized and return to normal orchestration:

1. Run `python3 "${PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "<project-root>" --context-finalize`.
   The bridge binds the five content documents, their five v2 provenance records,
   and `open-tasks.md`, `open-questions.md`, `overrides.log` to their exact identities.
   Native `context-finalize-preview` validates those 13 outputs and their current
   source bindings before proposing the marker and updated provenance.
2. Inspect that preview and apply its `preview_ref` and `preview_sha256` through
   the same bridge. The writer rechecks current identities under its lock and
   commits the marker and matching `CONTEXT` provenance together. No separate
   approval reply is needed. A stale, malformed or missing input remains a
   precise refusal; do not append the marker or bypass the writer.
3. Read back the committed files. Report which categories were inspected,
   remaining unknowns, documents changed and actual checks. The marker records
   completed population; it is not a certification of semantic truth, host
   enforcement or test success. Return to normal authorized work.

Completion: the native transaction reports committed, the activation flag and
standalone body marker are present, and the required outputs remain valid.
Valid empty boards and a zero-event audit header satisfy their real contracts.
Existing initialized repositories use refresh; never remove their marker to
repeat onboarding.

## Hard rules

- MUST NOT finalize while any `[CONFIRM-NN]` is unaddressed — every gap must be resolved or explicitly deferred to `open-questions.md` first.
- MUST NOT resolve a `[CONFIRM-NN]` by guessing — surface the question to the user or defer it.
- Account for all six logical categories on initial or explicitly full work;
  scoped refresh covers its selected categories without claiming a new full scan.
- Do not claim host containment, independent review or verified semantics from
  an agent label, report shape, source digest or artifact write.
- MUST NOT record a scout finding that exposes a secret value — paths and line numbers only.
- MUST NOT scaffold a cut doc — see [includes/cut-docs.md](../../includes/cut-docs.md) for the canonical never-scaffold list. Maturity is the `stage:` frontmatter number in `CONTEXT.md`.
- MUST NOT run when `CONTEXT.md` already carries `<!--INITIALIZED-->` — stop and route to normal operation.
