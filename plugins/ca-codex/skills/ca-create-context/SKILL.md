---
name: ca-create-context
description: Build project context from an existing codebase through isolated scouts, resolve gaps, and preserve initialization gates.
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

For each content document, compare the document and its v2 provenance as a
pair. A missing or mismatched companion is incomplete, not usable context.
Identify the last approved preview, receipt and operation ID; inspect its
native transaction outcome before retrying an apply whose response was lost.
Use the existing engine's `recover` protocol for a pending transaction with
that same operation ID and a justified complete or rollback choice. A committed
result is read back and retained; do not repeat its write. An absent output may
be created only through a fresh typed preview and its own approval. A diverged
human file, unknown journal, stale expected identity or unresolved ownership
returns a precise conflict and leaves current bytes intact. Resume independent
valid outputs without claiming that individual replacements made the entire
set atomically visible.

Check finalization separately. An initialized marker with matching current
`CONTEXT` provenance is the committed outcome; retain it and route to normal
operation. Without that proven outcome, re-inventory all 13 required output
identities and use a fresh `finalize` preview and its own host-observed receipt.
If a prior finalization transaction is pending or its result is uncertain,
inspect or recover that operation first. Never append the marker by hand or
reuse a document approval for finalization. Initialized projects use the
existing scoped refresh lifecycle, with their marker and history retained.

## Phase 1 — Pre-flight confirmation · gate: BLOCK

Confirm the repository is a brownfield codebase safe for scout-based extraction:

1. Confirm `<!--INITIALIZED-->` is absent from `CONTEXT.md`.
2. Confirm meaningful source code is present beyond the excluded set.
3. Identify the primary source directories (`src/`, `backend/`, `frontend/`, `lib/`, `app/`, or equivalent).

State the finding to the user: existing source detected, beginning scout-based extraction.

Gate: `<!--INITIALIZED-->` absent AND meaningful source present. If the marker is present, stop and route to normal operation. If no meaningful source exists, stop and route to `decompose`. Neither condition met → do not proceed.

## Phase 2 — Scout dispatch · gate: BLOCK

A context scout reads one targeted slice of the codebase and returns a bounded
findings report — file paths, line numbers, and named values only, never raw
code excerpts. Scouts are internal to this skill; they are never invoked from a
command.

## Context-creation containment profile

BLOCK before dispatch unless the active host actually exposes a context-specific
child profile with a fresh child identity and host-enforced read-only containment.
The profile may use a read-only sandbox or a tool set limited to source read and
report delivery. A context-specific profile with Bash is eligible only when the
actual read-only OS boundary also contains the parent and every child, and a
closed guard permits exact frozen `git hash-object -- '<source path>'` reads only.
It must deny every other shell command, mutating file tool, nested Agent call,
unsandboxed retry and unknown child. A role label, an
agents capability, or a promise in the prompt does not qualify containment.
MUST NOT dispatch the existing `scout` role as this profile: its shared
frontmatter permits Bash for `decision-variance`. The current generated host
surfaces do not themselves provide a qualified context-specific restriction.
Without an explicitly prepared and observed caller profile, report
context-creation scout dispatch as unavailable and BLOCK before dispatch.
Do not invent per-dispatch tool flags, a model-tier mapping, or an inline
substitute. This restriction does not change `decision-variance` dispatch.

One candidate caller route is Claude Code's documented session-only `--agents`
inline JSON defining `context-scout` with `Read`, `Grep`, `Glob`, `Bash`, an exact
caller-selected model, and the context assignment prompt. The scoped source
preparer in `.github/scripts/test_context_host.py` provides
`--prepare-context-profile` and `--guard-context-profile` for that route. The
former requires an explicit A–F assignment-to-file map, rejects `.git`, `.env`,
other private `.env.*` paths and symlink components, then freezes each
assignment's regular files, their raw SHA-256 values, the union source-list
digest, package digest, runtime identity, model and exact Git command strings.
The caller must supply a trusted, pinned absolute Git executable and its
SHA-256 from outside the source snapshot. The preparer rejects source-root Git
and a different executable selected by `PATH` before any Git invocation; a
hash of an untrusted `PATH` candidate is not provenance.
The guard consumes a native `PreToolUse` JSON event. It admits only a bound
child's assigned file to Read or Grep; Glob requires an exact assigned filename
with no wildcard, and Bash requires an exact assigned hash command. A parent
may only dispatch the session-only `context-scout` during this phase. Active
Git clean filters are rejected before preparation can finish; the guard
rechecks the frozen Git executable, effective config, filter attributes and
relevant environment before each Bash hash. The caller must start the native
phase with a sanitized Bash and Git environment: no shell startup hooks,
exported Bash functions, dynamic-loader injection variables, Git trace output
variables, or other rejected
environment keys. The preparer and guard reject such keys, but they cannot
prove the native Bash process inherited that environment; the caller must
verify it at the OS boundary. The parent `Agent` hook check limits agent type
and observes bound-child count, but repeated calls before `SubagentStart` can
all pass. The trusted caller must atomically reserve exactly one launch per
assignment, at most six total, before dispatch and bind each resulting native
child ID; hook decisions alone never establish that bound. Protect the resulting profile and
hook command from the solver, use the host's documented hook settings, and retain the exact
settings, agent definition and installed package bytes. The preparer never
invokes a host or qualifies containment. It does not set an OS sandbox, admit
children, collect reports or grant native task authority. A caller must supply
and qualify those missing layers before any dispatch. A settings declaration
alone is not a host observation. Native Windows Bash is not an eligible OS
read-only boundary for this route; a supported Linux/WSL2 sandbox must fail if
unavailable and refuse unsandboxed retries. Unknown platform or settings
behavior leaves this route unavailable. Native file tools need their own
source-scoped permission boundary because the Bash sandbox alone does not
contain them. A caller must also retain and independently validate all six
read, hash, guard-denied write, OS-denied write and report observations with
distinct native child IDs. The preparer's supplied-observation completeness
check always returns `unverified`; it is not a native receipt.

The exact inert preparation CLI is `python <pinned-source>/test_context_host.py
--prepare-context-profile <repo-root> <assignment-map.json>
<union-source-list-sha256> <installed-package-sha256> <runtime-id>
<exact-model> <trusted-git-absolute-path> <trusted-git-sha256>
<protected-profile.json>`. It creates that profile and its
`<protected-profile.json>.settings.json` template only at absent paths. Pass
the profile's `agents` object as inline JSON to the documented session-only
`--agents` flag; the caller installs and verifies the protected settings and
OS read-only phase separately. On each real `SubagentStart`, the trusted caller
binds its native `agent_id` to the predeclared assignment with
`bind_context_child` before the child's first tool. Unknown or extra children
are denied, and the caller retains each bound input/result/denial/report rather
than inserting synthetic answers into the report. The CLI's guard mode is
`python <pinned-source>/test_context_host.py --guard-context-profile
<protected-profile.json>` with the native hook event on stdin. These source
helpers ship as a caller preparation interface; they do not make any installed
plugin host qualified by themselves.

Before treating a newly supported host profile as qualified, observe distinct
child identities for all six assignments, a successful source read and a
bounded report from each child, and a benign write attempt denied by the
actual host boundary. Check that the attempted write left the target bytes unchanged. A
missing or inconclusive observation leaves the profile unavailable. If source
hashes cannot be obtained through the qualified exact-command Bash route or
another trusted deterministic read-only collector, the profile remains
unavailable. Verify that each cited command actually ran against the frozen
source and retain its result; the preparer's source-list digest is not a scout
report digest. Keep `git-blob-normalized-sha1` and `sha256-raw` method identities
distinct in `_contextreportlib`.
The orchestrator receives only reports after Phase 1, preserving report-only synthesis.
Never count a failed or missing report as completed coverage.

When the profile is actually qualified, create one full run with six root
assignments, one for each logical category below. Queue launches within the
host's qualified concurrency limit; simultaneous execution is not required.
For an affected-scope refresh, create only the affected root assignments and
retain the extent of prior coverage separately. A scoped run cannot assert a
new full scan. Fix the run's source snapshot, deadline and host-specific time,
token and tool budgets before any authorized dispatch. If a mandatory budget
or qualified profile is unavailable, block before dispatch.

Use `_contextreportlib.admit_scout_attempt` before each launch and retain every
admitted assignment/attempt pair in the same run ledger, including failed,
oversize, retry and child attempts. The aggregate limit is 24 launches, one
retry per unchanged assignment, subdivision depth 3 and fanout 4. Subdivision
keeps the parent assignment ID and uses a finite set of preflight coverage
paths: the children's union must equal the parent's set. Name any intentional
overlap in the child assignments, then reconcile the returned observations;
unexplained overlap or contradictory overlap blocks. No renamed child or retry
starts a new run budget or deadline. A failed parent is still counted when its
work is subdivided. A parent that completed cannot be silently replaced by
children.

Each report must pass the versioned closed `_contextreportlib` decoder with
its exact assignment, attempt, snapshot and scope binding; the
legacy `decision-variance` Markdown report does not satisfy this transport.
No inline fallback is allowed: this skill's report-only
synthesis boundary depends on the orchestrator never loading the scouts' raw
source into its own context.
Each reads only its assigned slice:

- **Scout A — Tech stack.** Read `package.json`, lockfiles, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`, `*.gemspec`, `Gemfile`. Report languages, runtime versions, frameworks, key dependencies, the dependency manager, license fields. Additionally report, at the repository root only: which of `package.json` / `pyproject.toml` / `Cargo.toml` / `composer.json` carry a version field (candidate release manifests), which of `CHANGELOG.md` / `CHANGES.md` / `HISTORY.md` are present (candidate changelogs), and any existing tag naming convention visible in the repo (e.g. a `v*` tag) — the inputs Phase 3/5 use to draft `.codearbiter/release-targets.md`.
- **Scout B — Infrastructure.** Read CI/CD config (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`), `Dockerfile*`, `docker-compose*.yml`, `Makefile`, `*.tf`, IaC. Report CI/CD platform, build/test/lint commands, deployment targets, environment names, containerization, IaC tool.
- **Scout C — Architecture.** Read the source tree (names and structure only), entry points (`main.ts`, `index.ts`, `app.py`, `server.go`), and imports in entry points only. Report component list, entry points, module boundaries, architectural pattern, public interfaces.
- **Scout D — Security posture.** Read auth files (`auth*`, `middleware*`, `guard*`, `jwt*`, `session*`, `oauth*`), crypto import lines, secret-loading sites (`process.env`, `os.environ`, vault/KMS call sites — paths and line numbers only, never values), `.env.example` (never `.env`). Report auth mechanism, crypto libraries, secret-loading patterns (paths + lines, no values), vault/KMS integration, hardcoded-secret risk files (paths only).
- **Scout E — Testing.** Read test files and test config (`vitest.config.*`, `jest.config.*`, `pytest.ini`, Makefile test flags), coverage config. Report test framework, runner command, coverage tool, coverage thresholds in config, naming convention, approximate test count by type, fixtures.
- **Scout F — Data model.** Read migration files (`migrations/`, `drizzle/`, `alembic/`, `db/migrate/`), schema definitions (`schema.ts`, `*.prisma`, `*.sql`, `models/`), ORM config, DB connection config (keys only, never credentials). Report database type, ORM/query builder, entity names, migration tool, approximate entity count, multi-tenancy patterns.

The orchestrator reads only the scout reports in later phases — never the raw source — to preserve working context. A scout that finds nothing returns an explicit "not found" report, never silence.

**Content hashes:** Each cited file needs a digest and method accepted by the
closed report decoder. The legacy scout's `git hash-object <path>` instruction
belongs to `decision-variance`; context-creation needs a trusted read-only
collector with the decoder's declared method and shape. No raw content is
forwarded to the orchestrator.

Before synthesis call `_contextreportlib.join_scout_reports` with the unchanged
run, complete attempt ledger and every returned transport payload. The join
requires six complete logical categories for an initial or explicitly full
run, or exactly the declared affected categories for a scoped refresh.
Complete ambiguous, not-inspected, failed or oversize category outcomes enter
gap handling; a missing, failed or oversize **report transport** blocks the
join. The normalized joined input is capped at 48 KiB; overflow is a named
scope/report-size blocker, never truncation or quiet omission. Recheck the
source snapshot at join through the source-snapshot owner before relying on
retained evidence. These pure helpers do not supply dispatch, containment,
freshness, authorization or live qualification.

Gate: an observed containment boundary and complete transports for every
declared logical assignment, including all six on a full run.
MUST NOT proceed to Phase 3 on an unavailable profile, failed or missing report,
or an unobserved read/write/report boundary. Re-dispatch a failing scout only
through the qualified profile after its failure is understood.

## Phase 3 — Synthesis · gate: BLOCK

Draft every surviving project-state doc from the admitted joined reports,
working only from those reports. For initial or explicitly full onboarding,
the join covers all six logical domains; a scoped refresh changes only its
declared affected domains and makes no new full-coverage claim. Map source to
destination:

| Scout source | Destination |
|---|---|
| Stack, infrastructure/commands, tests/verification | `tech-stack.md` |
| Architecture/source ownership, tests/structure | `coding-standards.md` |
| Security boundaries | `security-controls.md` (thin) |
| Stack/release candidates | `.codearbiter/release-targets.md` when supported |
| All applicable domains | `CONTEXT.md` (project identity, purpose, scope, NOT-building) |

For each retained claim, name its purpose, owning source and actual consumer
(or a specific retention reason), with the report citation and source snapshot.
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

Distinguish report transport from category outcome. A complete transport with
`observed`, `not_applicable`, `not_found_in_scope`, `not_inspected` or
`ambiguous` still counts as a returned report; a missing, failed or oversized
transport blocks Phase 3. A justified `not_applicable` records why the domain
does not apply. A `not_found_in_scope` records its searched scope and predicates;
it does not prove universal absence. In a small static project with known tests
and justified no-storage evidence, ask no database question for a scoped test
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
domain with no scout signal has its coverage and uncertainty represented in the
relevant draft; it does not force an irrelevant interview or an empty file.

## Phase 4 — Gap interview · gate: BLOCK

First reconcile contradictory reports without picking the highest confidence:
retain both conflicting citations and request the smallest independent reinspection
of the disputed source, predicate and snapshot through the
qualified read-only profile. A changed or missing source snapshot requires
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

Prepare the five surviving content documents with the installed context writer's typed preview, actual source evidence and file-specific provenance. Review and approve each exact preview through its native `approve-context` reply before receipt-only apply; an approval for one document does not approve another or the final marker. Preserve existing human content and ownership. Every doc carries actual content — no unresolved placeholder may remain where a value was determined:

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

Skip both commands entirely when this run is not writing `release-targets.md` — a marker minted for a write that never happens is a 30-minute window nothing needed. No other file in the table above is enrolled, so none of them take a marker.

If scouts found existing decision records (`docs/decisions/`, `adr/`), summarize them as entries under `.codearbiter/decisions/` in the standard ADR format. If a record cannot be fully parsed, summarize what is known, flag the uncertainty, and note the source path for review.

**Provenance and code-map:**

- The installed context writer commits each selected document and its v2 `.codearbiter/.provenance/<doc>.json` record together. Bind each claim to current content or membership evidence, its source, owner and actual consumer. An identity acknowledgement does not stand in for semantic review or approval. Never write either side of this pair directly.
- Synthesize `.codearbiter/code-map.md` (concern → path → ≤1-line role) from architecture evidence. Use concern headings (`## <concern>`) and column-0 bullets (`- \`path\` — role`). Keep it coarse — module/concern granularity only, no full file listing.

Do NOT scaffold any cut doc — see [includes/cut-docs.md](../../includes/cut-docs.md) for the canonical never-scaffold list. Maturity lives in the `stage:` frontmatter of `CONTEXT.md`, not a separate file.

Gate: all five content documents and their matching v2 provenance pairs are present; `CONTEXT.md` frontmatter carries `arbiter: enabled` and `stage:`; no resolved value is left as a placeholder. The task/question boards and audit file are present through their owning paths. Valid empty boards and a zero-event audit header pass. Deferred `[CONFIRM-NN]` items are recorded in `open-questions.md`.

## Phase 6 — Initialization lock · gate: BLOCK

Lock the project state as initialized and return to normal orchestration:

1. Gather exact SHA-256 identities for the five content documents, their five v2 provenance records, and `open-tasks.md`, `open-questions.md`, `overrides.log`. Submit the closed `finalize` preview through `init-codearbiter.py --context-request FILE` with those 13 path identities. The installed native writer validates each file by its own contract, checks all current source evidence and addressed/deferred questions, and previews the marker plus updated `CONTEXT` provenance. A missing, malformed or changed file blocks without reporting completion.
2. Review the exact finalization preview and capture its own host-observed `approve-context` reply. Apply only that receipt through the same request bridge. The writer rechecks all relevant identities under its lock and commits `<!--INITIALIZED-->` in the body of `CONTEXT.md` with the new full-document provenance digest as one transaction. Do not append the marker directly or reuse a content-write receipt.
3. List `.codearbiter/` and confirm the committed result and current provenance. State the return to normal operation: extraction complete, project state initialized and locked, `$ca-feature` available to begin work. Deferred questions live in `open-questions.md`.

Gate: the qualified native transaction reports committed, `arbiter: enabled` and the standalone body marker are present, and all required outputs remain valid. Header-only empty boards, justified inapplicable domains and a zero-event audit header satisfy their real contracts. Existing initialized repositories use refresh; never remove their marker to repeat onboarding.

## Hard rules

- MUST NOT finalize while any `[CONFIRM-NN]` is unaddressed — every gap must be resolved or explicitly deferred to `open-questions.md` first.
- MUST NOT resolve a `[CONFIRM-NN]` by guessing — surface the question to the user or defer it.
- MUST NOT proceed past Phase 2 without all six complete logical reports for
  initial or explicitly full onboarding; a scoped refresh needs its declared
  affected assignments and must not claim new full coverage.
- MUST NOT use a writable role with Bash as a context scout or infer read-only containment from an `agents` capability.
- MUST NOT run Phase 2 inline — isolated scout subagents are required for the report-only synthesis boundary.
- MUST NOT load raw source into the orchestrator context after Phase 1 — synthesize from scout reports only.
- MUST NOT record a scout finding that exposes a secret value — paths and line numbers only.
- MUST NOT scaffold a cut doc — see [includes/cut-docs.md](../../includes/cut-docs.md) for the canonical never-scaffold list. Maturity is the `stage:` frontmatter number in `CONTEXT.md`.
- MUST NOT run when `CONTEXT.md` already carries `<!--INITIALIZED-->` — stop and route to normal operation.
