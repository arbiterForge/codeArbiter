# Skill: skill-author

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when the user runs `/new-skill "<gap description>"`.

Triggers:
- User invokes `/new-skill "<gap description>"`
- The routing table references this skill for new skill authoring
- A gap in the skill system has been identified and needs to be formalized

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. The user has provided a gap description argument. If `/new-skill` was invoked
   with no argument, stop and ask: "Please describe the gap this skill would fill.
   What situation or trigger does not have a skill today?"
2. `.agents/projectContext/CONTEXT.md` exists and contains `<!--INITIALIZED-->`. If
   not, inform the user that projectContext must be initialized before new skills can
   be authored (they may need project-specific paths). Do not block if the skill is
   clearly generic and requires no project-specific context.
3. Read `.agents/skills/` directory listing to understand what skills already exist.
   If an existing skill already covers the described gap, stop and inform the user:
   > "This gap appears to already be covered by the `<skill-name>` skill. Please
   > review that skill before requesting a new one."

If all checks pass, proceed to Phase 1.

---

## Phases

### Phase 1 — Gap Challenge

**Goal:** Validate that the described gap is real, recurring, and worth the cost
of a new skill before writing a single line.

**Inputs:**
- Gap description argument from the user invocation
- Existing skill listing from Pre-Flight

**Actions:**

1. Read the gap description. Restate it back to the user in one sentence to confirm
   shared understanding.

2. Challenge the gap with this exact prompt:
   > "Before I author this skill, I need to confirm the gap is real. Please give me
   > one of the following:
   >
   > - **Option A:** Three specific cases where this gap blocked you or your team.
   >   For each case, describe: what you were trying to do, what happened without this
   >   skill, and what the cost was (time lost, decision made incorrectly, rule violated).
   >
   > - **Option B:** One high-impact case with documented evidence — a PR that was
   >   blocked, a bug that was introduced, a compliance finding, or a repeated failure
   >   pattern that can be pointed to.
   >
   > If you cannot provide one of these, I will not write the skill."

3. Evaluate the user's response:
   - **Sufficient (proceed):** Three specific recurring cases are provided, OR one
     high-impact case with traceable evidence is provided.
   - **Insufficient (stop):** Fewer than three cases, no traceable evidence, or the
     cases described are hypothetical rather than actual occurrences.

4. If insufficient: explain why the skill will not be written.
   > "I'm not seeing sufficient evidence that this gap is real and recurring. A new
   > skill adds maintenance overhead and cognitive load to the skill system. Without
   > clear evidence of actual recurring impact, the cost outweighs the benefit. If
   > this gap does materialize in practice, bring it back with evidence and I'll
   > author it."
   Stop. Do not proceed to Phase 2.

5. Determine gap type from the user's description and cases:
   - **Project-specific**: The gap only makes sense in the context of this specific
     project (references project-specific paths, domain concepts, integrations, or
     compliance requirements that are not universal).
   - **Generic**: The gap applies to any project using codeArbiter, regardless of
     what the project is about.

6. Record the gap type determination for use in Phase 2.

**Output:** Gap confirmed as real. Gap type determined (project-specific or generic).

**Gate:** BLOCK. If the user cannot provide sufficient evidence of a real gap, stop
here and do not author the skill. Gap type must be determined before Phase 2.

---

### Phase 2 — Scope Decision

**Goal:** Confirm the skill's scope, placement, and whether a new command is needed,
with explicit user agreement before authoring begins.

**Inputs:**
- Confirmed gap and gap type from Phase 1
- Existing skill and command listings

**Actions:**

1. Present the scope decision to the user:

   > **Scope question 1: Generic or project-specific?**
   >
   > Based on the cases you described, this gap appears to be [generic / project-specific].
   >
   > - **Generic skill** (`skills/<name>/SKILL.md`): Applies to any project using
   >   codeArbiter. Lives in `.agents/skills/`. Referenced in the routing table.
   >   Any project using codeArbiter benefits from it. Paths reference
   >   `projectContext/` files generically, not hardcoded project paths.
   >
   > - **Project plugin** (`projectContext/plugins/<name>/SKILL.md`): Specific to
   >   this project only. Lives in `.agents/projectContext/plugins/`. Not part of
   >   the shared skill system. Can reference hardcoded paths and project-specific
   >   concepts.
   >
   > Which is correct for this gap?

2. After user answers scope question 1, present scope question 2:

   > **Scope question 2: New command or internal invocation?**
   >
   > Does this skill need a new slash command that users invoke directly (e.g.,
   > `/new-skill`, `/onboard`, `/commit`)? Or is it invoked internally by another
   > skill as part of a larger workflow?
   >
   > - **New command needed**: A user will type `/<command-name>` to trigger this
   >   skill directly. This requires creating `.agents/commands/<name>.md` and the
   >   `.claude/commands/<name>.md` shim, and updating `COMMANDS.md`.
   >
   > - **Internal invocation only**: This skill is called from within another skill
   >   or agent. No new slash command is needed.
   >
   > Which applies here?

3. Wait for explicit user answers to both questions before proceeding.

4. Confirm the agreed scope:
   > "Agreed. I will write a [generic skill / project plugin] at
   > [`.agents/skills/<name>/SKILL.md` / `.agents/projectContext/plugins/<name>/SKILL.md`].
   > [A new `/<command-name>` command will be created. / No new command will be created.]
   > Proceeding to authoring."

**Output:** Skill placement path confirmed. Command decision confirmed. Explicit user
agreement recorded.

**Gate:** BLOCK. Must have explicit user agreement on both questions before Phase 3.
Do not begin authoring on assumed answers.

---

### Phase 3 — Skill Authoring

**Goal:** Write a complete, standards-compliant `SKILL.md` file and self-review it
before presenting to the user.

**Inputs:**
- Gap description and confirmed cases from Phase 1
- Scope and placement decisions from Phase 2
- Existing skills in `.agents/skills/` as structural examples
- Skill Structure Standard (from `AGENTS.md`)

**Actions:**

1. Read the Skill Structure Standard from `AGENTS.md` in full before writing.

2. Read 2–3 existing skill files from `.agents/skills/` as structural examples.
   Prefer skills with similar characteristics to the one being authored (e.g., if
   authoring a multi-phase skill with subagents, read a skill that uses subagents).

3. Write the `SKILL.md` file at the agreed path, following the Skill Structure Standard:

   ```
   # Skill: <skill-name>

   ## Trigger
   When this skill runs. Include all named triggers.

   ## Pre-Flight
   Ordered checks before Phase 1. Each either passes silently or hard-stops
   with a specific error message.

   ## Phases

   ### Phase N — <Name>
   **Goal:** One sentence.
   **Inputs:** What the skill reads/receives.
   **Actions:** What the skill does, step by step.
   **Output:** What artifact or state change results.
   **Gate:** Hard stop condition (BLOCK if...).

   ## Failure Modes
   Table of failure scenarios and responses.

   ## Subagents Invoked
   List of subagents, or "None."
   ```

4. Authoring rules:
   - Every phase must have a Gate. "No gate" is only acceptable for purely declarative
     phases with no output that could be wrong.
   - All project-specific paths MUST reference `projectContext/` files, not hardcoded
     values. Example: "Read `.agents/projectContext/tech-stack.md`" not
     "Read `backend/package.json`".
   - All subagents must be declared in the Subagents Invoked section with: type,
     purpose, constraints, and return format.
   - Hard rules and must-not statements belong in a "Hard Rules" subsection if there
     are more than three of them.
   - Gates must be unambiguous — "looks good" and "seems correct" are not gates.

5. **Self-review:** After writing the skill, re-read it against the Skill Structure
   Standard and check for:
   - Missing sections (Trigger, Pre-Flight, Phases, Failure Modes, Subagents Invoked)
   - Phases with missing Gate declarations
   - Subagents mentioned in actions but not declared in Subagents Invoked
   - Hardcoded project-specific paths that should reference `projectContext/`
   - Ambiguous gates ("if it looks wrong", "if something is off")
   - Triggers that do not clearly specify when to invoke vs. when not to invoke
   - Failure modes that block without a recovery path

6. Compile the self-review findings into a list. Present to the user:
   > "I've written the skill and completed a self-review. Here are the findings:
   >
   > [list of findings with proposed fixes]
   >
   > Which improvements should I implement?"

7. Implement all approved improvements before proceeding to Phase 4.

**Output:** `SKILL.md` written at the agreed path. Self-review complete. All approved
improvements implemented.

**Gate:** BLOCK. `SKILL.md` must be written before Phase 4. Self-review must be
complete. All approved improvements must be implemented. Do not proceed with an
improvement the user approved but that has not yet been written.

---

### Phase 4 — Routing Integration

**Goal:** Wire the new skill into the skill system so it is reachable from the
correct triggers and discoverable by contributors.

**Inputs:**
- Scope and command decisions from Phase 2
- Path of written `SKILL.md` from Phase 3

**Actions:**

**If a new command was agreed in Phase 2:**

1. Write `.agents/commands/<name>.md`:
   - One-paragraph description of when to invoke the command
   - Arguments (name, type, required/optional, description)
   - What the command does (brief)
   - Example invocations

2. Write `.claude/commands/<name>.md` shim:
   ```
   @.agents/commands/<name>.md
   ```
   This single line delegates to the agents command file. No other content.

3. Update `AGENTS.md`:
   - Add a row to Section 4 (Reference Map) if the skill covers a new domain
   - Add a row to Section 5 (Routing Table) with:
     - Trigger pattern (what user action routes to it)
     - Primary route (`skill-name` skill)
     - Also Invoke (any co-invoked skills or agents)
     - Hard Gate (the blocking condition)

4. Update `COMMANDS.md`:
   - Add a row to the Quick Reference table: command name, one-line description,
     required arguments
   - Add a detail section below the table: full argument list, example invocations,
     notes on when to use vs. when not to use

**If the skill is internal (no new command):**

1. Identify the parent skill or agent that will invoke this skill.
2. Update the parent skill's `Subagents Invoked` section or `Actions` to reference
   the new skill by name.
3. If the skill is private to a specific agent, write it to
   `.agents/skills/subagents/<agent-name>/<skill-name>.md` instead of
   `.agents/skills/<name>/SKILL.md`.
4. Update the parent agent's definition to reference the new skill.

**Output:** All routing integration points updated. No broken references. New skill
is reachable from its declared triggers.

**Gate:** BLOCK. If a new command was agreed, all four integration steps must be
complete before Phase 5. If the skill is internal, the parent must reference it.
Do not present the skill for final confirmation with broken routing.

---

### Phase 5 — Validation

**Goal:** Present the complete skill and all routing changes to the user for final
confirmation, then initiate commit via the commit-gate skill.

**Inputs:**
- `SKILL.md` from Phase 3
- Routing changes from Phase 4

**Actions:**

1. Present a summary of everything written:
   - Path and first 10 lines of `SKILL.md`
   - List of all other files modified or created (commands, shims, AGENTS.md rows,
     COMMANDS.md rows)

2. Ask for explicit confirmation:
   > "Please review the skill and routing changes above. Is everything correct and
   > ready to commit? (yes / no, and if no, what needs to change)"

3. If the user requests changes: implement them, then re-present and re-ask.

4. If the user confirms with "yes" or equivalent:
   - Announce: "Confirmed. Initiating commit via the commit-gate skill."
   - Invoke the commit-gate skill (do NOT run `git commit` directly — the commit-gate
     skill is the only permitted commit path)

5. MUST NOT commit directly. MUST NOT bypass the commit-gate skill.

**Output:** User has explicitly confirmed the skill is correct. Commit initiated via
commit-gate skill.

**Gate:** BLOCK. User must explicitly confirm (not just "looks good" — must be a
clear "yes" or "confirmed" or equivalent positive affirmation) before commit is
initiated. Commit MUST go through the commit-gate skill, never directly.

---

## Failure Modes

| Failure | Response |
|---|---|
| No gap description provided | Ask for the description; do not proceed without it |
| Gap description matches an existing skill | Stop; point the user to the existing skill |
| User cannot provide sufficient gap evidence | Decline to write the skill; explain why; invite them to return with evidence |
| User provides hypothetical cases only | Treat as insufficient; explain that hypotheticals do not demonstrate a real gap |
| User does not answer scope questions explicitly | Re-ask; do not assume an answer |
| Self-review finds a missing section | Add the section before presenting to user |
| Self-review finds hardcoded paths | Replace with projectContext/ references before presenting |
| Routing integration file (AGENTS.md, COMMANDS.md) is missing | Surface the gap; note what file is missing; ask user how to proceed |
| User requests a change in Phase 5 | Implement the change; re-present; re-confirm before committing |
| User says "commit it" without explicit skill confirmation | Stop; re-ask for explicit skill confirmation first; then invoke commit-gate |

---

## Subagents Invoked

None. This skill operates entirely within the orchestrator context. The commit is
delegated to the commit-gate skill (not a subagent invocation — it is a skill
handoff at Phase 5).
