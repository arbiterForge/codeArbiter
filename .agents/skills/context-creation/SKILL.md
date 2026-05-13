# Skill: context-creation

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when ALL of the following are true:

- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` does NOT contain the `<!--INITIALIZED-->` sentinel
- Meaningful source code DOES exist in the repository (defined as: files outside
  `.agents/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.gitignore`, and standard
  dotfiles/tooling configs)

This is the brownfield path. When no meaningful source code exists, route to the
`decompose` skill instead.

Triggers:
- User invokes `/create-context`
- Startup protocol detects uninitialized context AND meaningful source code is present
- The routing table references this skill for existing-codebase context initialization

---

## Pre-Flight

Before Phase 1 begins, confirm in order:

1. Read `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. If the file contains `<!--INITIALIZED-->`,
   stop immediately — context already exists. Inform the user and route to normal
   operation (Phase 3 of the startup protocol).
2. Check for meaningful source code: scan the repository root for files or directories
   that are not `.agents/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.gitignore`, or
   standard tooling dotfiles (`.editorconfig`, `.prettierrc`, etc.). Meaningful source
   code MUST be present. If none is found, stop and route to the `decompose` skill.
3. Confirm `${PROJECT_ROOT}/.agents/projectContext/` directory exists and is writable. If not, surface
   the gap and stop.

If all three pass silently, proceed to Phase 1.

---

## Phases

### Phase 1 — Pre-Flight Confirmation

**Goal:** Confirm meaningful source code exists and the repository is safe for
scout-based context extraction.

**Inputs:** Repository root file listing; `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` contents.

**Actions:**

1. Run a file listing of the repository root (one level deep).
2. Confirm meaningful source code is present beyond the excluded set.
3. Confirm `<!--INITIALIZED-->` is absent from `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`.
4. Identify the project root and primary source directories (e.g., `src/`, `backend/`,
   `frontend/`, `lib/`, `app/`, or equivalent).
5. Report findings to the user: "Existing source code detected. Beginning scout-based
   context extraction."

**Output:** Confirmed brownfield state. Primary source directories identified.
Pre-flight logged.

**Gate:** BLOCK. If `<!--INITIALIZED-->` is present, stop and route to normal operation.
If no meaningful source code exists, stop and route to `decompose` skill. Do not proceed
if neither condition is met.

---

### Phase 2 — Scout Dispatch

> **Definition — scout.** A `general-purpose` agent dispatched in parallel from
> this skill to read a targeted codebase slice and return a structured findings
> report with file paths, line numbers, and named values — never raw code
> excerpts. Scouts are internal to this skill and `decision-variance`; they
> MUST NOT be invoked from a slash command.

**Goal:** Dispatch six scout subagents in parallel to read targeted slices of the
codebase and return structured findings without loading raw source into the
orchestrator context.

**Inputs:**
- Primary source directories identified in Phase 1
- Repository root path

**Actions:**

Dispatch all six scouts simultaneously. Each scout reads only its assigned slice
and returns a structured findings report. Scouts MUST NOT include raw code excerpts
in their reports — only file paths, line numbers, and structured findings.

**Scout A — Tech Stack and Dependencies**
- Read: `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`,
  `pyproject.toml`, `requirements.txt`, `go.mod`, `go.sum`, `Cargo.toml`,
  `Cargo.lock`, `*.gemspec`, `Gemfile`, `Gemfile.lock`
- Report: programming languages, runtime versions, primary frameworks, key
  dependencies, dependency manager in use, license fields found

**Scout B — Infrastructure and Environments**
- Read: CI/CD config files (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`,
  `.circleci/config.yml`), `Dockerfile*`, `docker-compose*.yml`, `Makefile`,
  `*.tf`, `*.toml` (IaC), `k8s/`, `helm/`, `ansible/`, deployment manifests
- Report: CI/CD platform, build steps, test commands, lint commands, deployment
  targets, environment names (dev/staging/prod), containerization approach, IaC
  tool in use

**Scout C — Architecture and Components**
- Read: source directory tree (file names and directory structure only, not file
  contents), entry point files (e.g., `main.ts`, `index.ts`, `app.py`, `server.go`),
  top-level module structure, import/require statements in entry points only
- Report: component list (directories and their apparent purpose), entry points,
  module boundaries, apparent architectural pattern (monolith, services, layered,
  etc.), public-facing interfaces detected

**Scout D — Security Posture**
- Read: auth-related files (patterns: `auth*`, `middleware*`, `guard*`, `jwt*`,
  `session*`, `oauth*`), crypto import usage (file names and import lines only),
  secret loading patterns (`process.env`, `os.environ`, config loading, vault/KMS
  call sites — file paths and line numbers only, not values), `.env.example` (not
  `.env`)
- Report: authentication mechanism in use, crypto libraries referenced, secret
  loading patterns found (file paths + line numbers, no values), vault/KMS
  integration detected, hardcoded secret risk files flagged (paths only)

**Scout E — Testing Conventions**
- Read: test files (`*.test.ts`, `*.spec.ts`, `*.test.py`, `*_test.go`, etc.),
  test configuration files (`vitest.config.*`, `jest.config.*`, `pytest.ini`,
  `go test` flags in Makefile), coverage configuration
- Report: test framework, test runner command, coverage tool, coverage thresholds
  found in config, test file naming convention, approximate test count by type
  (unit/integration/e2e), test helpers or fixtures detected

**Scout F — Data Model**
- Read: migration files (`migrations/`, `drizzle/`, `alembic/`, `db/migrate/`),
  schema definition files (`schema.ts`, `schema.py`, `*.prisma`, `*.sql`,
  `models/`), ORM configuration, database connection config files (paths and
  config keys only, not credentials)
- Report: database type (relational/document/graph), ORM or query builder in use,
  entity names found in schema/migration files, migration tool, approximate entity
  count, any multi-tenancy patterns detected

**Output:** Six scout reports, each in structured format covering the assigned domain.
Every finding references specific file paths and line numbers. No raw code excerpts.

**Gate:** BLOCK. All six scouts must return reports before Phase 3 begins. A missing
scout report is a blocking gap — do not proceed with an incomplete picture. If a scout
finds no relevant files (e.g., no migrations exist), it returns an explicit "not found"
report rather than no report.

---

### Phase 3 — Synthesis

**Goal:** Produce a complete draft of every projectContext file from the six scout
reports, flagging low-confidence inferences as CONFIRM-NN placeholders.

**Inputs:**
- Six scout reports from Phase 2
- Repository structure from Phase 1

**Actions:**

The orchestrator reads ONLY the scout reports — not the raw source files. Synthesizing
from the reports preserves working context.

For each projectContext file, derive content from the scout reports using this mapping:

| Scout Source | Destination File |
|---|---|
| Scout A (tech stack) | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` |
| Scout B (infra) | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` (test/lint/build commands) |
| Scout C (architecture) | `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` |
| Scout D (security) | `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`, `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` |
| Scout E (testing) | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` (test runner section) |
| Scout F (data model) | `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` (state-change entities) |
| All scouts combined | `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` (project identity, purpose, scope) |
| Scout A + B | `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md` |
| Scout C + D | `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` (structural patterns observed; the `## File Header Requirements` copyright holder name CANNOT be inferred from scouts — write `[CONFIRM-NN: Copyright holder name — the individual name, team, company, or username to appear in the copyright line of every new file]` in that section) |

Confidence rules:
- **HIGH confidence**: Finding is directly and unambiguously present in scout report
  (e.g., `"jest"` in `package.json` devDependencies). Write it as fact.
- **MEDIUM confidence**: Finding is inferred from indirect signals (e.g., directory
  structure suggests layered architecture but no explicit config confirms it). Write
  it with a note: "Inferred from [signal]. Verify before relying on this."
- **LOW confidence**: Scout found no relevant signal or multiple conflicting signals.
  Write a `[CONFIRM-NN]` placeholder with a description of what is needed.

Every CONFIRM-NN placeholder must include:
- A sequential ID (`CONFIRM-01`, `CONFIRM-02`, etc.)
- A one-sentence description of what is unknown
- Why it matters (what decision or behavior depends on it)
- What information would resolve it

**Output:** Draft of every projectContext file. All low-confidence inferences marked
as `[CONFIRM-NN]`. List of all CONFIRM-NN items with their IDs and descriptions.

**Gate:** BLOCK. All projectContext files must be drafted before Phase 4. Every
low-confidence inference must carry a CONFIRM-NN placeholder — silent omissions are
not permitted. Do not write a file with no content; if scouts returned no signal for
a file's domain, write the file with a CONFIRM-NN for the entire section.

---

### Phase 4 — Gap Interview

**Goal:** Resolve CONFIRM-NN items through targeted user questions. Ask only what
scouts could not answer with high confidence.

**Inputs:**
- Draft projectContext files from Phase 3
- CONFIRM-NN list from Phase 3

**Actions:**

1. Present the list of CONFIRM-NN items to the user grouped by category (not
   by scout). Explain that these are gaps the automated scan could not resolve
   with confidence.
2. For each CONFIRM-NN item, ask ONE targeted question. Do not ask compound
   questions. Do not re-ask questions already answered with high confidence by
   scouts.
3. For each user answer:
   - If the answer resolves the gap: remove the `[CONFIRM-NN]` placeholder and
     write the actual content into the appropriate projectContext file draft.
   - If the user explicitly defers the answer: keep the `[CONFIRM-NN]` placeholder,
     mark it as "Deferred by user on [date]", and record it in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`.
   - If the user's answer is vague: apply the decompose skill's vague-requirements
     lens — challenge the vagueness and ask for a concrete answer before moving on.
4. After all CONFIRM-NN items have been addressed (resolved or explicitly deferred),
   confirm with the user that no additional context is needed.

**Output:** Updated projectContext file drafts with resolved CONFIRM-NN items filled in.
Deferred CONFIRM-NN items recorded in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`.

**Gate:** BLOCK. Every CONFIRM-NN item must have one of two outcomes: resolved (replaced
with content) or explicitly deferred (marked as deferred and recorded in
`${PROJECT_ROOT}/.agents/projectContext/open-questions.md`). No CONFIRM-NN item may be silently dropped. Do not proceed to
Phase 5 with unacknowledged gaps.

---

### Phase 5 — projectContext Write

**Goal:** Write all finalized projectContext files to disk with content derived from
scouts and the gap interview.

**Inputs:**
- Finalized projectContext file drafts from Phase 4
- Deferred CONFIRM-NN items for `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`

**Actions:**

Write the following files. Every file must contain actual content — no PLACEHOLDER
sentinels may remain in files where content was determined:

| File | Content Source |
|---|---|
| `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` | Project identity, purpose, scope, primary users, NOT-building (from scouts + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` | Components, trust boundaries, zone topology (from Scout C + Scout D + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` | Languages, frameworks, test runner, lint command, build command, coverage command (from Scout A + B + E) |
| `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` | Auth mechanism, crypto patterns, compliance requirements (from Scout D + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` | State-change actions, auditable events, sink routing (from Scout F + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` | Telemetry-relevant findings across scouts B (infrastructure/CI/CD), C (architecture/components), and E (testing conventions). Instantiate from template `${FRAMEWORK_ROOT}/.agents/skills/observability-emit/templates/observability-spec.md.tmpl`; populate signal categories, naming conventions, required labels, cardinality budgets, canonical emit module paths, alert rule storage location, SLO definitions per the existing codebase's telemetry conventions. Flag low-confidence inferences as [CONFIRM-NN]. <!-- Future enhancement: dedicated observability scout. --> |
| `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` | Structural patterns, naming conventions, style rules (from Scout C + E + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` | Secret-bearing integrations, vault/KMS usage, loading patterns (from Scout D + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md` | Dependency strategy, license stance, audit approach (from Scout A + B + gap interview) |
| `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` | All deferred CONFIRM-NN items in `CONFIRM-NN: <description>` format |
| `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` | Stub if no task backlog found by scouts; note: "Populated by user — no backlog source detected." |
| `${PROJECT_ROOT}/.agents/projectContext/stage` | `1` (default; user may override if project is further along) |

If scouts identified existing ADRs or decision records in the codebase (e.g., `docs/decisions/`, `adr/`), summarize them as entries in `${PROJECT_ROOT}/.agents/projectContext/decisions/` using the standard ADR format.

If no task backlog was found by scouts, write `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` as a stub with a note
directing the user to populate it.

**Output:** All projectContext files written with content derived from the interview and
scout reports. `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` populated with all deferred CONFIRM-NN items.

**Gate:** BLOCK. All projectContext files must be written. No PLACEHOLDER sentinels
may remain in any file where content was determined. Deferred CONFIRM-NN items are
acceptable in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`. Do not proceed to Phase 6 until all files are written.

---

### Phase 6 — Initialization Lock

**Goal:** Lock the projectContext as initialized, confirm all files are present,
and return codeArbiter to normal orchestrator operation.

**Inputs:**
- All projectContext files written in Phase 5
- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`

**Actions:**

1. Write the `<!--INITIALIZED-->` sentinel as the final line of
   `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`.
2. Run a directory listing of `${PROJECT_ROOT}/.agents/projectContext/` and display the full
   populated tree to the user.
3. Confirm each required file is present and non-empty:
   - `CONTEXT.md` (with `<!--INITIALIZED-->`)
   - `trust-zones.md`
   - `tech-stack.md`
   - `security-controls.md`
   - `audit-spec.md`
   - `observability-spec.md`
   - `coding-standards.md`
   - `secrets-policy.md`
   - `dependency-policy.md`
   - `open-questions.md`
   - `open-tasks.md`
   - `stage`
4. Announce return to normal operation:
   > "Context extraction complete. projectContext is initialized and locked. I am
   > returning to normal codeArbiter orchestrator mode. You can now use `/tdd` to
   > begin implementation, `/onboard` to bring in team members, or any other command
   > in the skill system. Deferred questions are recorded in
   > `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` and must be resolved before stage
   > promotion."

**Output:** `<!--INITIALIZED-->` sentinel present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. Full file tree
displayed. Return to orchestrator mode announced.

**Gate:** BLOCK. `<!--INITIALIZED-->` sentinel must be present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`.
All files listed above must be present and non-empty. Do not close this skill without
confirming the sentinel is written.

---

## Failure Modes

| Failure | Response |
|---|---|
| `<!--INITIALIZED-->` already present when skill starts | Stop immediately; inform user context exists; route to normal operation |
| No meaningful source code detected | Stop; inform user; route to `decompose` skill |
| A scout finds no relevant files | Scout returns explicit "not found" report; orchestrator writes CONFIRM-NN for that domain |
| A scout fails to return a report | Re-dispatch the failing scout before proceeding to Phase 3 |
| Multiple scouts return conflicting signals about the same domain | Record the conflict as CONFIRM-NN; ask the user in Phase 4 |
| User gives a vague answer in Phase 4 | Apply vague-requirements lens; challenge the answer; do not record vague content |
| A CONFIRM-NN item cannot be resolved (user does not know) | Mark as deferred; record in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`; do not block initialization |
| A projectContext file cannot be derived from scouts or gap interview | Write file with CONFIRM-NN for the entire section; record in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` |
| Existing ADRs found in codebase but cannot be fully parsed | Summarize what is known; flag uncertainty; note file path for user review |

---

## Subagents Invoked

- **Scout subagent** (6 parallel instances)
  - Type: `general-purpose`
  - Purpose: Read a targeted slice of the codebase and return structured findings
  - Constraint: MUST NOT include raw code excerpts in reports — only file paths,
    line numbers, and structured findings
  - Constraint: MUST NOT load full file contents of large files — read targeted
    sections (imports, exports, config keys, entity names) only
  - Returns: Structured findings report for assigned domain
  - Invoked in: Phase 2
