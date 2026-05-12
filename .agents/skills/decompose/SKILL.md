# Skill: decompose

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when ALL of the following are true:

- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` does NOT contain the `<!--INITIALIZED-->` sentinel
- No meaningful source code exists in the repository (defined as: no files outside
  `.agents/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.gitignore`, and standard
  dotfiles/tooling configs)

This is the greenfield path. When meaningful source code exists, route to the
`context-creation` skill instead.

Triggers:
- User invokes `/decompose`
- Startup protocol detects uninitialized context AND no source code
- The routing table references this skill for greenfield project setup

---

## Pre-Flight

Before Phase 1 begins, confirm in order:

1. Read `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. If the file contains `<!--INITIALIZED-->`,
   stop immediately — context already exists. Inform the user and route to normal
   operation (Phase 3 of the startup protocol).
2. Check for meaningful source code: scan the repository root for files or directories
   that are not `.agents/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.gitignore`, or
   standard tooling dotfiles (`.editorconfig`, `.prettierrc`, etc.). If any such files
   exist, stop. Do not proceed. Inform the user that source code was detected and route
   to the `context-creation` skill.
3. Confirm `${PROJECT_ROOT}/.agents/projectContext/` directory exists and is writable. If not, surface
   the gap and stop.

If all three pass silently, proceed to Phase 1.

---

## Phases

### Phase 1 — Pre-Flight Confirmation

**Goal:** Confirm the repository is genuinely greenfield and safe to begin decomposition.

**Inputs:** Repository root file listing; `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` contents.

**Actions:**

1. Run a file listing of the repository root (one level deep).
2. Confirm no source files are present beyond the excluded set.
3. Confirm `<!--INITIALIZED-->` is absent from `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`.
4. Report findings to the user: "No existing context or source code detected. Beginning
   greenfield decomposition."

**Output:** Confirmed greenfield state. Pre-flight logged.

**Gate:** BLOCK. If `<!--INITIALIZED-->` is present or source code is detected, stop and
route appropriately. Do not proceed with decomposition on a non-greenfield repository.

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

3. Ask the first Layer 1 question to begin the interview:

   > "Describe your solution vision in your own words. What problem does it solve,
   > and for whom?"

**Output:** Persona adoption announced. Rules of Engagement stated. Layer 1 begun.

**Gate:** No gate. This phase is declarative. Proceed to Phase 3 after announcing the
persona and asking the first question.

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

Every user-attributed answer that implies an architectural decision is captured
immediately as a draft ADR, to be formalized in Phase 5.

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
- Trade-off forcing for every major architectural decision. Examples:
  - Monolith vs. services: "Monolith ships faster and is simpler to operate but
    limits independent scaling and team autonomy. Services enable scale but require
    service mesh, distributed tracing, and contract testing from day one — choose."
  - Sync vs. async: "Sync gives immediate feedback but couples availability.
    Async decouples but requires at-least-once delivery guarantees, idempotency,
    and dead-letter handling — choose."
  - Every forced choice is recorded as a draft ADR.

Do not advance until: all components named, all data entities sketched, all hard
constraints recorded, and every major architectural trade-off resolved or explicitly
deferred as CONFIRM-NN.

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

**Output:** Complete interview record across all six layers. Every user-attributed
architectural decision captured as a draft ADR. Every unresolved item recorded as
a CONFIRM-NN placeholder.

**Gate:** BLOCK. All six layers must be complete. No layer may have open "we'll
figure it out later" items unless they are recorded as CONFIRM-NN. Do not proceed
to Phase 4 until all layers are solid.

---

### Phase 4 — Synthesis

**Goal:** Produce three canonical decomposition artifacts and present them for user
review before committing them to the repository.

**Inputs:**
- Complete interview record from Phase 3
- Draft ADRs captured during Phase 3

**Actions:**

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

4. Present all three artifacts to the user. Explicitly request review:
   > "These three artifacts represent my synthesis of our interview. Please review
   > each one. Tell me what is wrong, incomplete, or misrepresents your intent.
   > I will not commit these until you confirm they are correct."

5. Iterate on artifacts based on user feedback until user explicitly approves.

**Output:** Three reviewed and approved decomposition artifacts.

**Gate:** BLOCK. User must explicitly approve all three artifacts. No unresolved
objections. Do not proceed to Phase 5 without explicit user sign-off.

---

### Phase 5 — projectContext Population

**Goal:** Derive every projectContext file from the approved artifacts and interview
record, producing a complete, populated context that enables the codeArbiter to
operate without re-interviewing.

**Inputs:**
- Approved decomposition artifacts from Phase 4
- Complete interview record from Phase 3
- Draft ADRs captured during Phase 3

**Actions:**

Write the following files using this source-to-destination mapping. Every file
must contain actual content derived from the interview — no PLACEHOLDER sentinels,
no template boilerplate left unfilled:

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
| Each Layer 4 major architectural decision | `${PROJECT_ROOT}/.agents/projectContext/decisions/000N-<title>.md` (one file per decision, ADR format) |
| Layer 6 unknowns + spike candidates | `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` (CONFIRM-NN format) |
| Phase 1 of the Phased Build Plan | `${PROJECT_ROOT}/.agents/projectContext/stage` = `1` |
| Task Backlog | `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` |
| All three artifacts | `${PROJECT_ROOT}/.agents/projectContext/decomposition/01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md` |

ADR format for each decision file:
```
# ADR-000N: <Decision Title>

**Status:** Accepted
**Date:** <today>
**Decider:** <user name or "user" if anonymous>

## Context
<What forced this decision>

## Decision
<What was decided>

## Consequences
<What is easier and harder as a result>
```

**Output:** All projectContext files written with content derived from the interview.
Every ADR written. `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` populated with all CONFIRM-NN items.

**Gate:** BLOCK. All projectContext files must be written with actual content.
No PLACEHOLDER sentinels may remain in any file where content was determined during
the interview. CONFIRM-NN items are acceptable in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` for genuinely
unresolved items. Do not proceed to Phase 6 until all files are written.

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
   - `decisions/` (at least one ADR)
   - `decomposition/01-architecture-breakdown.md`
   - `decomposition/02-phased-build-plan.md`
   - `decomposition/03-task-backlog.md`
4. Announce return to normal operation:
   > "Decomposition complete. projectContext is initialized and locked. I am returning
   > to normal codeArbiter orchestrator mode. You can now use `/tdd` to begin
   > implementation, `/onboard` to bring in team members, or any other command in the
   > skill system. Open questions are recorded in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`
   > and must be resolved before stage promotion."

**Output:** `<!--INITIALIZED-->` sentinel present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. Full file tree
displayed. Return to orchestrator mode announced.

**Gate:** BLOCK. `<!--INITIALIZED-->` sentinel must be present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`.
All files listed above must be present and non-empty. Do not close this skill without
confirming the sentinel is written.

---

## Failure Modes

| Failure | Response |
|---------|----------|
| `<!--INITIALIZED-->` already present when skill starts | Stop immediately; inform user context exists; route to normal operation |
| Source code detected in repository | Stop; inform user; route to `context-creation` skill |
| User gives vague answer and resists clarification | Restate the Rule of Engagement for vague requirements; do not advance the layer |
| "We'll figure it out later" on a blocking architectural decision | Record as CONFIRM-NN; inform user it will block stage promotion; do not advance layer until user acknowledges |
| User rejects a synthesized artifact in Phase 4 | Revise and re-present; do not proceed to Phase 5 until explicit approval |
| A projectContext file cannot be derived (insufficient interview data) | Re-open the relevant layer; ask the missing questions before writing the file |
| `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` has CONFIRM-NN items remaining | This is expected and acceptable; record them; note they block stage promotion |
| User attempts to skip a layer | Refuse; explain that skipped layers produce CONFIRM-NN items that block stage promotion |

---

## Subagents Invoked

None. This skill operates entirely within the orchestrator context. No subagents are
dispatched. The persona shift is a behavioral mode change, not a subagent invocation.
