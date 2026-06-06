<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: SKILL.md
-->

# Skill: decompose

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when ALL of the following are true:

- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` does NOT contain the `<!--INITIALIZED-->` sentinel
- No meaningful source code exists in the repository (defined as: no files outside
  `.git/`, `.agents/`, `.claude/`, the vendored framework tree if any (e.g.
  `vendor/codearbiter/`), `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`,
  `.gitignore`, `.gitmodules`, and standard dotfiles/tooling configs)

This is the greenfield path. When meaningful source code exists, route to the
`context-creation` skill instead.

Triggers:
- User invokes `/decompose`
- Startup protocol detects uninitialized context AND no source code
- The routing table references this skill for greenfield project setup

---

## Pre-Flight

Before Phase 1 begins, run these ordered checks. Each either passes silently or
hard-stops with a specific routing action:

1. Read `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. If the file contains
   `<!--INITIALIZED-->` on its own line (matching the H-08 hook regex
   `^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$`), stop immediately — context
   already exists. Route to normal operation (Phase 3 of the startup protocol).
2. Check for meaningful source code: scan the repository root for files or directories
   that are not `.git/`, `.agents/`, `.claude/`, the vendored framework tree if any
   (e.g. `vendor/codearbiter/`), `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`,
   `.gitignore`, `.gitmodules`, or standard tooling dotfiles (`.editorconfig`,
   `.prettierrc`, etc.). If any such files exist, stop and route to the
   `context-creation` skill.
3. Confirm `${PROJECT_ROOT}/.agents/projectContext/` directory exists and is writable.
   If not, surface the gap and stop.

If all three pass silently, proceed to Phase 1. Phase 1 does NOT re-run these checks —
it consumes Pre-Flight's pass-status and announces the result.

---

## Phases

### Phase 1 — Greenfield Confirmation

**Goal:** Acknowledge Pre-Flight pass, log entry into decomposition, and announce
the role to the user. No re-checking of Pre-Flight's three conditions — that is
Pre-Flight's job.

**Inputs:** Pre-Flight pass-status (implicit; if Pre-Flight failed, this phase
never runs).

**Actions:**

1. Report findings to the user: "No existing context or source code detected.
   Beginning greenfield decomposition."
2. Log entry into the decompose skill (timestamp + invoking identity) to working
   memory; this will be persisted to `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/_session.md`
   when Phase 2.5 initializes the draft directory.

**Output:** Entry-into-decompose announced. Pre-Flight outcome carried forward.

**Gate:** BLOCK only if Pre-Flight did not pass. In normal operation this gate is a
no-op (Pre-Flight already stopped the skill on failure). The gate exists for defense
in depth: any caller that bypasses Pre-Flight and enters Phase 1 directly is rejected.

---

### Phase 2 — Persona Adoption

**Goal:** Shift codeArbiter out of orchestrator mode and into the decomposition partner
persona for the duration of this skill.

**Inputs:** None. This is a behavioral mode change.

**Actions:**

1. Announce the role switch to the user using this exact wording:

   > "Switching to decomposition mode. For this session the orchestrator operates
   > as a senior software architect and technical lead, decomposing your project
   > vision into a complete, unambiguous specification before any code is written.
   > Vague language will be challenged, hidden complexity surfaced, and trade-offs
   > forced. Orchestrator mode resumes when this decomposition is complete and the
   > projectContext files are written."

2. State the Rules of Engagement verbatim:

   > **Rules of Engagement**
   >
   > - **Pacing:** ONE LAYER AT A TIME. One focused question at a time within a layer
   >   (cluster only when tightly coupled). Never advance to the next layer until the
   >   current layer is solid. "Solid" means: no hand-wavy answers, no deferred
   >   decisions, no unchallenged vague language.
   >
   > - **Three lenses always active on every answer:**
   >   1. **Vague requirements** — Challenge hand-wavy language. Force concrete numbers
   >      and verbs. "Manage" is not a verb — it means create, edit, delete, export,
   >      share, archive, or some combination. "We'll figure that out later" is not
   >      acceptable. Every "later" becomes a CONFIRM-NN placeholder that blocks stage
   >      promotion.
   >   2. **Hidden complexity** — After each layer, surface what the user is assuming
   >      will be easy but is actually hard: state management, real-time sync, edge
   >      cases, data migration, multi-tenancy, role matrices, offline behavior, failure
   >      modes, anything that grows non-linearly with scale. Name it explicitly. Do not
   >      let it slip through.
   >   3. **Trade-off forcing** — When a real architectural or product decision exists,
   >      frame it explicitly: "X gives you A but costs B; Y gives you C but costs D —
   >      choose." Do not let the user have it both ways unless they justify the
   >      justification with evidence. Record every forced choice as a draft ADR.
   >
   > - **Integration suggestions calibrated to confidence:**
   >   - **HIGH** (clear best practice for this context): Recommend one option with a
   >     one-line justification.
   >   - **MEDIUM** (2–3 viable options with real trade-offs): Present options with
   >     pros/cons and ask the deciding question.
   >   - **LOW** (gap exists but the right answer depends on unknowns): Flag the gap,
   >     explain why it matters, ask the unlocking question.
   >   - Never silently skip a gap. Never suggest an integration without stating why.

**Output:** Persona adoption announced. Rules of Engagement stated. No questions
asked yet — the Layer 1 question is asked at the end of Phase 2.5, after draft
persistence is initialized, so that the first user answer is captured to disk.

**Gate:** BLOCK. Phase 2 advances to Phase 2.5, never directly to Phase 3. Phase
2.5 is the only place the Layer 1 question is asked. This ordering guarantees
that no Q/A is ever held in conversation context without a corresponding draft
file backing it.

---

### Phase 2.5 — Draft Directory Initialization (or Resume)

**Goal:** Establish persistent draft state on disk so the layered interview can survive
auto-compaction or session interruption. Detect and offer to resume a prior interrupted
decomposition before any new Q/A is captured.

**Why this phase exists:** The Phase 3 layered interview accumulates 60–110 Q/A turns
across six layers. Without per-layer disk persistence, an auto-compaction event between
Layer 1 and Phase 5 silently destroys earlier layer reasoning and any draft ADRs. Phase
2.5 + the per-layer write rule in Phase 3 + the Phase 4 disk-rehydrate rule together
make the skill compaction-resilient: every layer is durable the moment its gate passes.

**Inputs:** Either nothing (fresh start) OR an existing
`${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/` directory from a prior interrupted session.

**Actions:**

1. Check for existing draft directory at `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/`.

2. **If draft directory exists with `_session.md` and one or more `layer-N-*.md` files
   — enter Resume mode:**
   - Read `_session.md` and every `layer-*.md` present.
   - Read every `${PROJECT_ROOT}/.agents/projectContext/decisions/*.md` with `Status: DRAFT` (these are
     prior-session draft ADRs that must be carried forward).
   - Present a numbered summary to the user: prior session timestamp, captured layers
     by name, count of draft ADRs found.
   - Ask the user:
     > "I found a prior decomposition draft from <timestamp>. The following layers
     > were captured: [list]. Draft ADRs found: [count]. Choose:
     > (a) **Resume** — continue from the next unfinished layer, treating captured
     > layers as solid.
     > (b) **Restart** — discard the draft directory and all DRAFT ADRs; begin fresh.
     > (c) **Abort** — exit the skill, leave draft directory and DRAFT ADRs intact
     > for later resumption."
   - On **Resume**: re-establish each captured layer as solid in conversation, then
     proceed to Phase 3 starting at the next unfinished layer.
   - On **Restart**: delete `.decompose-draft/` and every `Status: DRAFT` ADR file,
     then continue with fresh-start init below.
   - On **Abort**: exit the skill cleanly. Draft directory and DRAFT ADRs preserved.

3. **If no draft directory exists (or after Restart) — fresh-start init:**
   - Create `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/`.
   - Write `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/_session.md` containing:
     ```
     # Decompose Draft Session
     Started: <ISO-8601 timestamp>
     Invoked by: <identity per /override identity detection sequence>
     Status: in-progress

     This directory is SESSION STATE. It is auto-deleted on Phase 6 completion.
     If the skill is interrupted (compaction, session end, user abort), re-invoke
     `/decompose` to enter Resume mode. Per-layer drafts are written here as each
     Layer 1–6 gate passes; immediate DRAFT ADRs are written to
     `${PROJECT_ROOT}/.agents/projectContext/decisions/` during Layer 4.
     ```
   - Ensure `.decompose-draft/` is gitignored: append `.agents/projectContext/.decompose-draft/`
     to `${PROJECT_ROOT}/.gitignore` if the entry is not already present.

4. Ask the first Layer 1 question to begin the interview:

   > "Describe your solution vision in your own words. What problem does it solve,
   > and for whom?"

**Output:** Either a fresh `.decompose-draft/` directory ready for per-layer writes
(with `_session.md` and gitignore entry in place), or a resumed decomposition with
prior layers and DRAFT ADRs replayed into context.

**Gate:** BLOCK. Phase 3 MUST NOT begin until either (a) the draft directory exists
with `_session.md` and is otherwise empty (fresh start) or (b) prior layers have been
replayed and the user has explicitly chosen Resume.

---

### Phase 3 — Layered Interview (Layers 1–6)

**Goal:** Conduct a complete structured interview across six layers to produce a
fully-specified, unambiguous understanding of the project before any artifacts are written.

**Inputs:** User answers to each layer's questions. Prior layer answers inform subsequent
layers. Three lenses (vague requirements, hidden complexity, trade-off forcing) applied
throughout.

**Actions:**

Run the six layers in strict sequence. Never skip a layer. Never advance to the next
layer until the current layer is solid (no open "we'll figure it out later" items,
no unchallenged vague language, no forced trade-off left unresolved).

**Per-layer disk persistence (compaction-resilience contract):** When each layer's
"do not advance until" checklist is satisfied, BEFORE asking the first question of
the next layer, write the completed layer's full Q/A record to disk:

| Layer | Draft file path |
|---|---|
| Layer 1 — Vision and Problem | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-1-vision.md` |
| Layer 2 — Users and Flows | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-2-flows.md` |
| Layer 3 — Functional Scope | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-3-functional-scope.md` |
| Layer 4 — Technical Shape | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-4-tech-shape.md` |
| Layer 5 — Integrations and Infrastructure | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-5-integrations.md` |
| Layer 6 — Risks and Unknowns | `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-6-risks.md` |

Each layer-N file MUST contain: every question asked, the user's verbatim answer
(or a faithful paraphrase if the user spoke conversationally), every challenge made
under the three lenses, every CONFIRM-NN raised, and every draft-ADR title generated.
Treat these files as the authoritative record — Phase 4 reads from them, not from
conversation context.

**Per-layer write gate:** The next layer MUST NOT begin until the prior layer's
draft file exists on disk and is non-empty. If a write fails, surface the error and
do not advance.

**Layer 4 immediate ADR drafts:** Each forced architectural choice in Layer 4 is
written immediately as `${PROJECT_ROOT}/.agents/projectContext/decisions/000N-<slug>.md` with
`Status: DRAFT`. Numbering is sequential across the existing decisions/ directory.
Do not batch ADR writes — write each one at the moment the choice is made. Phase 5
promotes each `Status: DRAFT` to `Status: Accepted` once the user signs off in Phase 4.

**Layer 1 — Vision and Problem**

Unlock and confirm:
- The specific problem being solved and the evidence it is real (not assumed).
- The primary user and any conflicting user types (if multiple user types have
  competing needs, name the conflict explicitly and resolve it or flag it).
- The demo-to-a-skeptic definition of "working" — what would a skeptic see in a
  five-minute demo that would convince them the core problem is solved.
- What this project explicitly is NOT building. Force the boundary. Vague scope
  boundaries become scope creep.

Do not advance until: problem is concrete, primary user is named, "working" is
demonstrable, and NOT-building list is explicit.

**Layer 2 — Users and Flows**

Unlock and confirm:
- The core user journey from first touch to value delivered (specific steps, no
  hand-waving at "the user logs in and does their thing").
- Non-human actors: scheduled jobs, webhooks, callbacks, external triggers. Name
  every one that will exist at MVP.
- Failure-mode UX: what does the user see when something goes wrong? Force concrete
  answers, not "we'll show an error message."
- Admin, ops, and internal users: who can see what, who can do what, how is
  privilege managed.

Do not advance until: end-to-end journey is specific, non-human actors are named,
failure UX is defined, and privilege model is sketched.

**Layer 3 — Functional Scope**

Unlock and confirm:
- Every capability the product must have. Challenge each one individually. For each:
  what exactly does it do (concrete verbs), who triggers it, what are the inputs
  and outputs.
- Classify each capability: MVP (launch blocker), v1 (first release after MVP),
  or later (explicitly deferred).
- The hardest user-facing problem — the one that, if it is wrong, invalidates the
  whole product.
- Every "we'll figure it out later" item: force to closure now or explicitly record
  as a CONFIRM-NN blocker.

Do not advance until: capability list is complete and every item is classified.
No unresolved "we'll figure it out later" items unless recorded as CONFIRM-NN.

**Layer 4 — Technical Shape**

Unlock and confirm:
- Components and ownership: what are the distinct technical components, what does
  each own, where are the boundaries.
- Core data entities and relationships: name every entity, sketch the relationships,
  identify cardinality.
- Where state lives and how it changes: what is stateful, where is that state stored,
  what are the write paths.
- The hardest technical problem — the one that could blow up the timeline.
- Hard constraints: stack (language, framework, runtime), cloud provider,
  compliance requirements (data residency, HIPAA, FedRAMP, etc.), budget ceiling,
  team size and skill set, existing systems to integrate with.
- Copyright holder: who or what entity owns the copyright on this codebase
  (individual name, company name, team name, or username). Recorded in
  `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` File Header Requirements and applied
  to every new file. If unknown or undecided, record as CONFIRM-NN.
- Trade-off forcing for every major architectural decision. Examples:
  - Monolith vs. services: "Monolith ships faster and is simpler to operate but
    limits independent scaling and team autonomy. Services enable scale but require
    service mesh, distributed tracing, and contract testing from day one — choose."
  - Sync vs. async: "Sync gives immediate feedback but couples availability.
    Async decouples but requires at-least-once delivery guarantees, idempotency,
    and dead-letter handling — choose."
  - Every forced choice is written immediately to disk as a `Status: DRAFT` ADR
    per the "Layer 4 immediate ADR drafts" rule at the top of Phase 3. Do not
    defer the write to Phase 5 — write at the moment the choice is made.

Do not advance until: all components named, all data entities sketched, all hard
constraints recorded, every major architectural trade-off resolved or explicitly
deferred as CONFIRM-NN, AND `layer-4-tech-shape.md` written to disk with one
`Status: DRAFT` ADR per forced choice.

**Layer 5 — Integrations and Infrastructure**

Unlock and confirm:
- Every external dependency (APIs, services, data sources, auth providers, payment
  processors, notification services, etc.). Name each one.
- Commodity vs. differentiator classification for each: is this integration
  table-stakes (use the standard provider) or a source of competitive advantage
  (worth owning).
- Existing system integration contracts: for any system being integrated with, what
  are the actual API contracts, data formats, and authentication mechanisms.
- Integration risks for each dependency:
  - Rate limits and how they are handled
  - Reliability expectations and fallback behavior
  - Data ownership and portability (can we export/migrate away from this)
  - Cost model and scale implications

Do not advance until: all external dependencies named, commodity/differentiator
classified, and integration risks surfaced for each.

**Layer 6 — Risks and Unknowns**

Unlock and confirm:
- The top three build-killing risks: the things that, if they materialize, require
  a major course correction. For each: probability, impact, and mitigation.
- The lowest-confidence areas: where is the uncertainty highest.
- What needs to be spiked or prototyped before committing to the architecture.
  For each spike: what question it answers, what the cost of being wrong is, and
  how long the spike should take.
- What would force a major architecture change after the build starts: name the
  signals, name the decision points.

Do not advance until: top three risks named with mitigations, spike candidates
identified, and architecture change triggers named.

**Output:** Complete interview record across all six layers, persisted to
`${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-1-*.md` through `layer-6-*.md`.
Every user-attributed architectural decision written as a `Status: DRAFT` ADR file in
`${PROJECT_ROOT}/.agents/projectContext/decisions/`. Every unresolved item recorded as a CONFIRM-NN
placeholder.

**Gate:** BLOCK. All of:
- All six layers must be complete (no layer may have open "we'll figure it out later"
  items unless they are recorded as CONFIRM-NN).
- All six `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-*-*.md` files MUST exist
  on disk and be non-empty.
- At least one `Status: DRAFT` ADR MUST exist in `${PROJECT_ROOT}/.agents/projectContext/decisions/`
  if any architectural trade-off was forced in Layer 4 (the typical case — a Layer 4
  with zero forced trade-offs is suspicious and should be re-examined before advancing).

Do not proceed to Phase 4 until all layers are solid AND all draft files are on disk.

---

### Phase 4 — Synthesis

**Goal:** Produce three canonical decomposition artifacts and present them for user
review before committing them to the repository.

**Inputs (read from disk, not from conversation context):**
- All six `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-*-*.md` files written in
  Phase 3
- All `Status: DRAFT` ADRs in `${PROJECT_ROOT}/.agents/projectContext/decisions/` written during Layer 4

**Compaction-recovery clause:** Phase 4 MUST begin by re-reading every layer draft
file and every DRAFT ADR from disk. Do NOT rely on conversation context for layer
content — by the time Phase 4 runs, an auto-compaction may have erased the original
Q/A turns. The on-disk drafts are the authoritative record. This re-read makes Phase
4 idempotent: it can be re-run after compaction or session restart without data loss.

**Actions:**

0. Read every `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-*-*.md` and every
   `${PROJECT_ROOT}/.agents/projectContext/decisions/*.md` with `Status: DRAFT` into working memory.
   If any expected layer file is missing, BLOCK and surface the gap rather than
   synthesizing from incomplete context.

1. Produce `01-architecture-breakdown.md` containing:
   - Every component with its responsibility and connections to other components
   - A simple ASCII or text diagram of the system (no external tools required)
   - Every integration named, with its type (sync/async), protocol, and owner
   - Every open architectural decision flagged with `[CONFIRM-NN]` markers (numbered sequentially with open-questions.md)
   - Trust zone mapping (if compliance requirements were named in Layer 4)

2. Produce `02-phased-build-plan.md` containing:
   - Phase breakdown: MVP → v1 → v2 (and beyond if needed)
   - For each phase:
     - One-sentence goal (what "done" means for this phase)
     - What is included (capability list, specific features)
     - What is deferred and why (explicit rationale, not just "later")
     - Key risks for this phase
     - Definition of done (measurable, not "it works")

3. Produce `03-task-backlog.md` containing:
   - Flat prioritized list of tasks
   - Each task is specific enough to estimate (1–5 days max for any single task)
   - Each task is assignable to one role (frontend, backend, infra, design, etc.)
   - Tasks are phase-grouped (MVP tasks first, then v1, etc.)
   - Dependencies flagged (task B requires task A to be complete)
   - Spikes identified with a time-box

4. Write all three artifacts to disk at their canonical paths BEFORE asking for
   user review:
   - `${PROJECT_ROOT}/.agents/projectContext/decomposition/01-architecture-breakdown.md`
   - `${PROJECT_ROOT}/.agents/projectContext/decomposition/02-phased-build-plan.md`
   - `${PROJECT_ROOT}/.agents/projectContext/decomposition/03-task-backlog.md`

   Writing first means the user reviews from disk (which they can re-open between
   sessions, share, or diff) rather than from chat output. Revisions in step 6
   edit these files in place.

5. Present all three artifacts to the user. Explicitly request review:
   > "These three artifacts have been written to `${PROJECT_ROOT}/.agents/projectContext/decomposition/`.
   > Please open and review each one. Tell me what is wrong, incomplete, or
   > misrepresents your intent. The files are on disk now so they survive a
   > session restart, but Phase 5 will not run until you confirm they are correct."

6. Iterate on artifacts based on user feedback, editing the on-disk files in place,
   until user explicitly approves.

**Output:** Three reviewed and approved decomposition artifacts on disk at
`${PROJECT_ROOT}/.agents/projectContext/decomposition/`.

**Gate:** BLOCK. All three artifact files MUST exist on disk AND user MUST explicitly
approve all three. No unresolved objections. Do not proceed to Phase 5 without
explicit user sign-off.

---

### Phase 5 — projectContext Population

**Goal:** Derive every projectContext file from the approved artifacts and interview
record, producing a complete, populated context that enables the codeArbiter to
operate without re-interviewing.

**Inputs (read from disk, not from conversation context):**
- Approved decomposition artifacts at `${PROJECT_ROOT}/.agents/projectContext/decomposition/`
  (written in Phase 4)
- All six `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-*-*.md` files
- All `Status: DRAFT` ADRs in `${PROJECT_ROOT}/.agents/projectContext/decisions/`

**Compaction-recovery clause:** Like Phase 4, Phase 5 MUST read its inputs from disk.
This makes the projectContext-population step idempotent across compaction. A user
could approve Phase 4 artifacts, suffer a session compaction, then re-enter Phase 5
in a fresh session by re-invoking `/decompose` (Phase 2.5 detects the draft directory
and enters Resume mode, replaying captured layers and DRAFT ADRs; Phase 4 sees its
artifacts already on disk and already approved; Phase 5 proceeds from disk).

**Actions:**

1. Re-read every input file from disk into working memory.
2. Promote each `Status: DRAFT` ADR in `${PROJECT_ROOT}/.agents/projectContext/decisions/` to
   `Status: Accepted` (in-place edit of the existing file — do not duplicate or
   rewrite the ADR body).
3. Write the remaining projectContext files using the source-to-destination mapping
   below. Every file must contain actual content derived from the interview — no
   PLACEHOLDER sentinels, no template boilerplate left unfilled:

| Source | Destination |
|--------|-------------|
| Layer 1 problem + users + NOT-building list | `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` |
| Layer 4 components + trust boundaries | `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` |
| Layer 4 stack + hard constraints | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` |
| Layer 4 compliance + crypto requirements | `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` |
| Layer 4 state-change actions + write paths | `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` |
| Layers 1–6 observability-relevant decisions (signals, naming, labels, cardinality budgets, emit modules, alert rule storage, SLOs) | `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — instantiate `${FRAMEWORK_ROOT}/.agents/skills/observability-emit/templates/observability-spec.md.tmpl`; populate signal categories, naming conventions, required labels, cardinality budgets, canonical emit module paths, alert rule storage location, SLO definitions per the decomposed project's needs. |
| Layer 4 lint, format, naming decisions | `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` |
| Layer 5 secret-bearing integrations | `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` |
| Layer 5 dependency strategy + license stance | `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md` |
| Each Layer 4 major architectural decision | `${PROJECT_ROOT}/.agents/projectContext/decisions/000N-<title>.md` — file already written during Layer 4 with `Status: DRAFT`; Phase 5 only promotes status to `Accepted` (Action 2 above). Do not rewrite. |
| Layer 6 unknowns + spike candidates | `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` (CONFIRM-NN format) |
| Phase 1 of the Phased Build Plan | `${PROJECT_ROOT}/.agents/projectContext/stage` = `1` |
| Task Backlog | `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` |
| All three artifacts | `${PROJECT_ROOT}/.agents/projectContext/decomposition/01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md` — files already written during Phase 4 and approved by user; Phase 5 only verifies they exist. Do not rewrite. |

ADR format. Layer 4 writes each forced choice with `Status: DRAFT`; Phase 5 Action
2 promotes the same file in place by editing the Status line to `Accepted`.

Layer 4 writes:

```
# ADR-000N: <Decision Title>

**Status:** DRAFT
**Date:** <today>
**Decider:** <user name or "user" if anonymous>

## Context
<What forced this decision>

## Decision
<What was decided>

## Consequences
<What is easier and harder as a result>
```

Phase 5 Action 2 edits the file so the same fields read:

```
**Status:** Accepted
```

(Status is the only field that changes between Layer 4 and Phase 5. Do not
duplicate or rewrite any other section.)

**Output:** All projectContext files written with content derived from the interview.
Every Layer 4 DRAFT ADR promoted to Accepted. `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`
populated with all CONFIRM-NN items.

**Gate:** BLOCK. All projectContext files must be written with actual content.
No PLACEHOLDER sentinels may remain in any file where content was determined during
the interview. No `Status: DRAFT` ADRs may remain in `${PROJECT_ROOT}/.agents/projectContext/decisions/`
(promotion to Accepted is mandatory in Phase 5). CONFIRM-NN items are acceptable in
`${PROJECT_ROOT}/.agents/projectContext/open-questions.md` for genuinely unresolved items. Do not proceed
to Phase 6 until all files are written and all DRAFT ADRs are promoted.

---

### Phase 6 — Initialization Lock and Draft Cleanup

**Goal:** Lock the projectContext as initialized, confirm all files are present,
delete the draft directory, and return codeArbiter to normal orchestrator operation.

**Inputs:**
- All projectContext files written in Phase 5
- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`
- `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/` (to be removed)

**Actions:**

1. Write the `<!--INITIALIZED-->` sentinel as the final line of
   `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. The sentinel MUST be on its own line,
   matching the regex `^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$` used by the
   `session-start.sh` hook. Sentinels embedded in template instruction comments
   do not satisfy the gate.
2. Run a directory listing of `${PROJECT_ROOT}/.agents/projectContext/` and display the full
   populated tree to the user.
3. Confirm each required file is present and non-empty:
   - `CONTEXT.md` (with `<!--INITIALIZED-->` on its own line)
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
   - `decisions/` (at least one ADR, all `Status: Accepted`, no remaining DRAFT)
   - `decomposition/01-architecture-breakdown.md`
   - `decomposition/02-phased-build-plan.md`
   - `decomposition/03-task-backlog.md`
4. **Delete the draft directory.** Remove
   `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/` and all its contents (`_session.md`
   and `layer-*-*.md` files). This is mandatory — leaving the draft directory in
   place signals a still-in-progress decomposition to Phase 2.5 of any future
   `/decompose` invocation, and BLOCKs stage promotion to Stage 1 elsewhere
   in the framework.
5. Announce return to normal operation:
   > "Decomposition complete. projectContext is initialized and locked. Draft
   > directory removed. I am returning to normal codeArbiter orchestrator mode.
   > You can now use `/tdd` to begin implementation, `/onboard` to bring in team
   > members, or any other command in the skill system. Open questions are
   > recorded in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` and must be resolved
   > before stage promotion."

**Output:** `<!--INITIALIZED-->` sentinel present on its own line in
`${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. `.decompose-draft/` deleted. Full file tree
displayed. Return to orchestrator mode announced.

**Gate:** BLOCK. All of:
- `<!--INITIALIZED-->` sentinel present on its own line in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`
  (must satisfy the H-08 hook regex `^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$`).
- All required files listed above present and non-empty.
- No `Status: DRAFT` ADRs remaining in `${PROJECT_ROOT}/.agents/projectContext/decisions/`.
- `${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/` deleted (does not exist on disk).

Do not close this skill without confirming all four conditions. The presence of
`.decompose-draft/` after Phase 6 close is a permanent skill-author bug — it means
a previous interview was abandoned mid-stream and the recovery path was never run;
the only safe responses are `/decompose` (re-enters Resume mode) or `/decompose --restart`.

---

## Failure Modes

| Failure | Response |
|---------|----------|
| `<!--INITIALIZED-->` already present when skill starts | Stop immediately; inform user context exists; route to normal operation |
| Source code detected in repository | Stop; inform user; route to `context-creation` skill |
| User gives vague answer and resists clarification | Restate the Rule of Engagement for vague requirements; do not advance the layer |
| "We'll figure it out later" on a blocking architectural decision | Record as CONFIRM-NN; inform user it will block stage promotion; do not advance layer until user acknowledges |
| User rejects a synthesized artifact in Phase 4 | Revise on-disk artifact in place and re-present; do not proceed to Phase 5 until explicit approval |
| A projectContext file cannot be derived (insufficient interview data) | Re-open the relevant layer; ask the missing questions before writing the file |
| `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` has CONFIRM-NN items remaining | This is expected and acceptable; record them; note they block stage promotion |
| User attempts to skip a layer | Refuse; explain that skipped layers produce CONFIRM-NN items that block stage promotion |
| Auto-compaction or session interruption mid-Phase-3 | Re-invoke `/decompose`; Phase 2.5 detects `.decompose-draft/` and offers Resume / Restart / Abort. No data loss for completed layers. |
| `.decompose-draft/` directory exists at skill start | Phase 2.5 enters Resume mode; user chooses Resume / Restart / Abort. Never silently delete. |
| Per-layer disk write fails | Surface the error; do not advance to the next layer. Investigate write permissions, disk space, or path resolution before retry. |
| Layer 4 produces zero DRAFT ADRs | Suspicious — Layer 4 should force at least one architectural trade-off. Re-examine the layer for missed forcing opportunities before advancing to Layer 5. |
| `Status: DRAFT` ADRs remain after Phase 5 | Promotion is mandatory. Re-run Phase 5 Action 2 (in-place status edit). Do not advance to Phase 6 with DRAFT ADRs present. |
| `.decompose-draft/` exists at Phase 6 close | Mandatory delete failed or was skipped. Surface error; investigate (likely a write-permission or skill-author bug); do not announce return to orchestrator mode until the directory is gone. |

---

## Subagents Invoked

None. This skill operates entirely within the orchestrator context. No subagents are
dispatched. The persona shift is a behavioral mode change, not a subagent invocation.
