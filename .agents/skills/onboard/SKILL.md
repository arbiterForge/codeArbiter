<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: SKILL.md
-->

# Skill: onboard

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when the user runs `/onboard` with an optional scope argument.

Two operating modes:
- **Full mode** (no argument): complete project orientation covering all areas
- **Targeted mode** (scope argument provided): deep-dive on a specific area only

Triggers:
- User invokes `/onboard`
- User invokes `/onboard "<scope>"` (e.g., `/onboard "auth"`, `/onboard "data model"`)
- A new engineer is joining and needs project orientation
- An existing contributor needs a refresher on a specific area

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` exists and is readable.
2. If `CONTEXT.md` does NOT contain `<!--INITIALIZED-->`, stop immediately and inform
   the user:
   > "The projectContext has not been initialized. Before I can onboard you, the project
   > context must be set up. If this is a new project with no source code, run `/decompose`.
   > If source code already exists, run `/create-context`."
   Do not attempt onboarding without an initialized context.
3. Detect the operating mode: if a scope argument was provided, set mode to TARGETED;
   otherwise set mode to FULL.

If pre-flight passes, proceed to Phase 1.

---

## Phases

### Phase 1 — Pre-Flight Confirmation

**Goal:** Confirm initialized context exists and operating mode is determined.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` — check for `<!--INITIALIZED-->` sentinel
- Invocation arguments — presence or absence of scope argument

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`. Confirm `<!--INITIALIZED-->` is present.
2. Note the current stage: `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.
3. Determine and record operating mode (FULL or TARGETED).
4. If TARGETED mode: record the scope argument for use in Phase 2.
5. Confirm the user's intent: "I'll give you a [full project tour / deep-dive on
   `<scope>`]. Ask me anything after the tour."

**Output:** Operating mode confirmed. Stage noted. User intent confirmed.

**Gate:** BLOCK if `<!--INITIALIZED-->` is absent. Route to `/decompose` or
`/create-context` as appropriate.

---

### Phase 2 — Content Load

**Goal:** Load the projectContext files relevant to the operating mode.

**Inputs:**
- Operating mode (FULL or TARGETED) from Phase 1
- Scope argument (TARGETED mode only)

**Actions:**

**Full mode — load and summarize:**
1. Read `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` — project identity, purpose, scope, NOT-building
2. Read `${PROJECT_ROOT}/.agents/projectContext/stage` — current stage value
3. Read `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` — architecture, components, zone topology
4. Read `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — languages, frameworks, tools, commands
5. Read `${PROJECT_ROOT}/.agents/projectContext/decisions/` directory — list all ADR files, read the
   5 most recently dated ones in full
6. Read `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` — all CONFIRM-NN items
7. Read `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` — in-flight and pending tasks
8. Read `${FRAMEWORK_ROOT}/.agents/skills/` directory listing — enumerate available skills and commands

**Targeted mode — load only files relevant to scope:**
Determine which projectContext files are relevant to the provided scope argument.
Examples:
- Scope "auth" or "security": load `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`, `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`,
  `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`, relevant ADRs with auth/crypto/secrets in title
- Scope "data model" or "database": load `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`, relevant ADRs, Scout F
  findings if available
- Scope "tech stack" or "dependencies": load `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`, `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md`
- Scope "architecture": load `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`, `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md`, relevant ADRs
- Scope "tasks" or "backlog": load `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md`, `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`
- Scope "decisions" or "ADRs": load all files in `${PROJECT_ROOT}/.agents/projectContext/decisions/`
- Scope "skills" or "commands": enumerate `${FRAMEWORK_ROOT}/.agents/skills/` and `${FRAMEWORK_ROOT}/.agents/commands/`

If the scope does not map to a clear set of files, load `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` as a base and
ask the user to clarify before proceeding to Phase 3.

**Output:** Relevant projectContext files loaded and ready for presentation.

**Gate:** No hard gate. If a referenced file is missing or empty, note the gap to
the user during Phase 3 rather than blocking.

---

### Phase 3 — Tour Delivery

**Goal:** Present the project orientation in a clear, structured format appropriate
to the operating mode.

**Inputs:**
- Loaded projectContext content from Phase 2

**Actions:**

**Full mode tour — present in this order:**

1. **Project identity and purpose**
   - What this project is, what problem it solves, and for whom
   - Source: `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` (Identity, Purpose sections)

2. **What it is NOT**
   - Explicit scope exclusions — the things this project deliberately does not do
   - Source: `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` (NOT This Project section)
   - Why it matters: scope clarity prevents wasted work and misaligned PRs

3. **Current stage and what that means**
   - Current stage number and name
   - What the stage allows and restricts (user count, external access, compliance posture)
   - What the promotion criteria are for the next stage
   - Source: `${PROJECT_ROOT}/.agents/projectContext/stage` file, stage table in `AGENTS.md` or `CLAUDE.md`

4. **Architecture overview**
   - Trust zones and their relationships
   - Component list and responsibilities
   - Key integration points
   - Source: `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`

5. **Tech stack**
   - Languages and runtimes in use
   - Primary frameworks
   - Test runner and how to run tests locally
   - Key make/npm/etc. commands for daily development
   - Source: `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`

6. **Key ADRs**
   - Present the 5 most recent accepted decisions
   - For each: decision title, what was decided, and the primary consequence
   - Note any decisions that are still in PROPOSED or SUPERSEDED status
   - Source: `${PROJECT_ROOT}/.agents/projectContext/decisions/` directory

7. **Open questions**
   - All CONFIRM-NN items currently unresolved
   - For each: what is unknown and why it matters
   - Which ones block stage promotion
   - Source: `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`

8. **In-flight tasks**
   - Summary of current open tasks
   - Any tasks flagged as blocked
   - Source: `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md`

9. **The codeArbiter skill system**
   - How to start a new feature: `/tdd "<description>"`
   - How to commit: tell codeArbiter to commit (commit-gate skill runs automatically)
   - How to open a PR: `/pr-ready`
   - How to add a dependency: `/add-dep "<package>"`
   - How to run a checkpoint review: `/checkpoint-review`
   - How to promote stage: `/promote-stage <n>`
   - How to surface a conflict: `/surface-conflict`
   - How to get a full command list: ask codeArbiter "what commands are available"

**Targeted mode — present with depth:**
Focus entirely on the specified scope. Use the loaded content from Phase 2. Cover:
- What the scope area is and why it matters to this project
- The current state as captured in projectContext
- Key decisions that shaped this area (relevant ADRs)
- Open questions in this area (relevant CONFIRM-NN items)
- How to work in this area correctly (relevant skills, commands, gates)
- Known risks or gotchas specific to this area

**Output:** Complete tour delivered (full mode) or scoped deep-dive delivered
(targeted mode). User explicitly invited to ask follow-up questions.

**Gate:** No hard gate. If content is missing for a section, note the gap and
continue. Do not block tour delivery on missing optional sections.

---

### Phase 4 — Conversational Mode

**Goal:** Remain available for follow-up questions after the tour, answering from
projectContext knowledge without making decisions or overstepping into implementation.

**Inputs:**
- Loaded projectContext content from Phase 2 (already in context)
- User follow-up questions

**Actions:**

1. After delivering the tour, announce conversational mode:
   > "I'm ready for questions. Ask me anything about the project — architecture,
   > decisions, commands, open questions, how to work in a specific area. When you're
   > ready to start working, just use a command and I'll return to normal operation."

2. For each follow-up question:
   - Answer from projectContext files loaded in Phase 2
   - If the answer requires reading a file not loaded in Phase 2, read it now
   - If the answer is not knowable from projectContext, say so explicitly — do not
     invent or infer beyond what is documented
   - If the question implies a decision needs to be made, redirect:
     > "That's a decision that should go through the proper channel. Use
     > `/surface-conflict` if there's a conflict, or raise it as a CONFIRM-NN in
     > `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`."
   - If the question implies implementation work, redirect:
     > "When you're ready to implement that, start with `/tdd '<description>'` and
     > I'll walk you through the TDD process."

3. MUST NOT invoke other skills in response to follow-up questions. MUST NOT make
   architectural decisions, write code, or commit anything while in conversational mode.

4. MUST NOT block on tool invocations during conversational mode — keep answers
   conversational and quick.

**Exit conditions:**
- User starts a new `/command` → exit conversational mode; route to the appropriate skill
- User says "done", "exit", "thanks", "I'm good", or an equivalent closing phrase →
  acknowledge and exit cleanly
- User explicitly starts implementation discussion → remind them to use `/tdd`

**Output:** Follow-up questions answered from projectContext. User redirected to
appropriate commands for decisions and implementation.

**Gate:** No hard gate. This phase is conversational and exits on user signal.

---

## Failure Modes

| Failure | Response |
|---|---|
| `<!--INITIALIZED-->` missing from `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` | Stop; inform user; direct to `/decompose` or `/create-context` |
| A projectContext file is missing or empty | Note the gap during the relevant tour section; do not block entire tour |
| `${PROJECT_ROOT}/.agents/projectContext/decisions/` directory is empty or has no ADRs | Note that no decisions have been recorded yet; proceed with tour |
| Scope argument not recognized in targeted mode | Load `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` as base; ask user to clarify the scope before proceeding |
| User asks a question that implies a decision | Redirect to appropriate command; do not decide on their behalf |
| User asks for implementation guidance | Redirect to `/tdd`; do not write code during onboard |
| `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` is empty or stub | Note it during the in-flight tasks section; direct user to populate it |

---

## Subagents Invoked

None. This skill operates entirely within the orchestrator context. All content is
read from projectContext files — no subagents are dispatched for onboarding.
