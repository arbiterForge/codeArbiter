# Skill: doc-governance

## Trigger

Invoke this skill before acting in any domain listed in AGENTS.md §4 Reference
Map, and whenever a file under `.agents/projectContext/` is modified or
referenced.

Triggers:
- Agent is about to act in a gated domain (any domain listed in AGENTS.md §4)
  without having read the relevant doc in the current session
- A file under `.agents/projectContext/` is added or modified
- A `projectContext/` reference in AGENTS.md or a skill file appears stale
- A new capability is added to the project without a corresponding
  `projectContext/CONTEXT.md` entry
- The `doc-governance` skill is referenced in the routing table

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `AGENTS.md` is readable — specifically the §4 Reference Map section that
   lists gated domains and their required docs.
2. `.agents/projectContext/CONTEXT.md` is readable.

If either file is missing, surface the gap and stop.

---

## Phase 1: Pre-Read Gate

**Goal:** Confirm that every doc required for the current domain was read in the
current session before any action is taken.

**Inputs:**
- The domain the agent is about to act in (derived from the current task)
- `AGENTS.md` §4 Reference Map — the authoritative list of gated domains and
  their required documents
- Current session read history

**Actions:**

1. Identify the domain of the current task (e.g., auth/crypto, data model,
   networking, new node/adapter, audit, CI/CD).
2. Look up the domain in AGENTS.md §4 Reference Map. Record every document
   listed as required reading for that domain.
3. For each required document, confirm it was read in the current session.
   "Read in the current session" means the agent has the content of the file
   in its active context — not merely that the file exists.
4. If any required document has not been read in the current session, read it
   now before continuing. Do not act in the domain on the assumption that the
   content is remembered from a prior session.
5. If a required document listed in AGENTS.md §4 does not exist on disk, surface
   the missing document as a gap and stop. Do not act in the domain without it.

**Output:** Confirmed that all required documents for the current domain are
present in the session context.

**Gate:** BLOCK. No action in a gated domain proceeds until all required
documents are read in the current session. Memory from prior sessions does not
satisfy this gate.

---

## Phase 2: Freshness Check

**Goal:** When a `projectContext/` file is modified, identify any agent or skill
files that reference it and flag potentially stale references.

**Inputs:**
- The modified `projectContext/` file path
- All files under `.agents/agents/` (agent definitions)
- All files under `.agents/skills/*/SKILL.md` (skill definitions)

**Actions:**

1. Record the name and path of the modified `projectContext/` file.
2. Search all files under `.agents/agents/` for references to the modified
   file's name or path.
3. Search all files under `.agents/skills/*/SKILL.md` for references to the
   modified file's name or path.
4. For each reference found, determine whether the referencing file's usage of
   the document is still consistent with the modified content:
   - If the modification added, removed, or renamed a section that a skill or
     agent depends on, flag the reference as STALE.
   - If the modification was additive only (new content appended without changing
     existing structure), the reference may be marked CURRENT.
5. Report all STALE references with the referencing file path and the specific
   section or field that may be affected.

**Output:** Freshness report listing all STALE references with file path and
affected section.

**Gate:** BLOCK if any STALE reference is found. The referencing file must be
updated before the modified `projectContext/` change is committed.

---

## Phase 3: Conflict Detection

**Goal:** When a `projectContext/` change contradicts AGENTS.md or another
project-context file, surface the conflict and stop all other work.

**Inputs:**
- The modified `projectContext/` file and its content
- `AGENTS.md` — the project-level authority document
- Other `projectContext/` files that share subject matter with the modified file

**Actions:**

1. Read the modified `projectContext/` file in full.
2. Compare its content against the relevant sections of `AGENTS.md`. Check for:
   - Contradictions in policy (e.g., a `projectContext/` file permitting
     something AGENTS.md prohibits)
   - Contradictions in naming or terminology
   - Contradictions in stage-gating rules or promotion criteria
3. Compare its content against other `projectContext/` files in the same domain.
   Check for:
   - Contradictions in architecture or zone definitions
   - Contradictions in classification rules or required fields
   - Contradictions in approved tool or library lists
4. If any contradiction is found, immediately invoke `/surface-conflict`.
   STOP all other work. Do not attempt to reconcile the contradiction silently.
5. If no contradiction is found, record that conflict detection passed.

**Output:** Conflict detection result — CLEAR or CONFLICT-FOUND with the
specific contradiction described.

**Gate:** BLOCK on any contradiction. Invoke `/surface-conflict` and stop. No
further work in the domain proceeds until the conflict is resolved by the user.

---

## Phase 4: Coverage Gap

**Goal:** Confirm that newly added capabilities are reflected in
`projectContext/CONTEXT.md`.

**Inputs:**
- Description of the new capability just added to the project
- `.agents/projectContext/CONTEXT.md` — the project context index

**Actions:**

1. Read `.agents/projectContext/CONTEXT.md`.
2. Search for an entry corresponding to the new capability. An entry should
   describe what the capability is, what domain it belongs to, and any relevant
   cross-references to other `projectContext/` files.
3. If no entry exists for the new capability, flag this as a MEDIUM finding:
   COVERAGE-GAP.
4. A COVERAGE-GAP finding does not block the current task but must be surfaced
   to the user with a recommendation to add the entry before the next
   checkpoint review.
5. If the new capability touches an area already documented in
   `projectContext/CONTEXT.md`, verify the existing entry is still accurate
   after the change.

**Output:** Coverage gap finding (COVERAGE-GAP or COVERED) for the new
capability.

**Gate:** MEDIUM finding (not a hard block). Surface COVERAGE-GAP to the user.
A COVERAGE-GAP that persists through a checkpoint review is upgraded to a
BLOCK for stage promotion.

---

## Decision Gates Summary

| Gate         | Condition                                                    | Action if blocked                          |
|--------------|--------------------------------------------------------------|--------------------------------------------|
| Phase 1 exit | Required doc not read in current session                     | Read the doc now; then proceed             |
| Phase 1 exit | Required doc does not exist on disk                          | Surface missing doc as gap; stop           |
| Phase 2 exit | STALE reference found in agent or skill file                 | Update referencing file before committing  |
| Phase 3 exit | Contradiction found between `projectContext/` and AGENTS.md  | Invoke `/surface-conflict`; stop all work  |
| Phase 4 exit | New capability has no `CONTEXT.md` entry (COVERAGE-GAP)      | Surface to user; recommend adding entry    |

---

## Hard Rules

- MUST read every required document for the current domain before acting.
  Prior session memory does not substitute for a current-session read.
- MUST NOT act in a gated domain without reading the gated doc, even if the
  domain appears familiar.
- MUST NOT silently reconcile a contradiction between a `projectContext/` file
  and AGENTS.md. Invoke `/surface-conflict` and stop.
- MUST NOT allow a STALE reference to be committed. Update the referencing
  file first.
- MUST NOT ignore a COVERAGE-GAP finding. Surface it to the user every time
  it is detected.
- MUST NOT guess at the content of a required document that has not been read.
  Read the file.

---

## Failure Modes

| Failure                                              | Response                                                              |
|------------------------------------------------------|-----------------------------------------------------------------------|
| `AGENTS.md` missing or §4 Reference Map absent       | Stop; surface gap; cannot determine which docs are required           |
| Required `projectContext/` doc does not exist        | Stop; surface missing doc; do not act in the domain without it        |
| `projectContext/CONTEXT.md` missing                  | Surface gap; Phase 4 cannot run; recommend creating the file          |
| Contradiction found between `projectContext/` files  | Invoke `/surface-conflict`; stop all other work immediately           |
| STALE reference found but referencing file is locked | Surface the staleness finding; do not commit until resolved           |
| COVERAGE-GAP persists through checkpoint review      | Upgrade to BLOCK for stage promotion; surface to user                 |
