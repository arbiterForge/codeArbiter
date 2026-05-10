---
name: arbiter
description: Reconcile project architectural artifacts (Architecture Breakdown, Phased Build Plan, Task Backlog) against the existing project scaffold and codebase. Use this skill whenever the user mentions architectural reconciliation, variance review, ingesting decomposition documents, comparing architectural decisions to existing code, syncing artifacts with scaffold state, or asks to "arbitrate," "reconcile," "merge," or "consolidate" architectural context with the project. Also use when the user asks what architectural artifacts can be produced from current project state, requests a variance report, mentions ADR conflicts, or wants to track outstanding architectural decisions. Do NOT use for routine git merges, code review consolidation, or general architectural discussions unrelated to the current project's artifacts. This skill never makes arbitration decisions alone — it presents SMARTS analyses for the user to decide. It treats the artifacts as authoritative-by-default but does not blindly adopt them.
---

# Arbiter Skill

A skill for systematically reconciling a project's three architectural artifacts (Architecture Breakdown, Phased Build Plan, Task Backlog) against the existing project scaffold, codebase, and prior decisions — without making arbitration decisions unilaterally.

## Three Foundational Rules (Read These First)

These rules govern everything else in this skill. Other instructions defer to these.

### Rule 1 — Never decide alone

The arbiter MUST NOT make arbitration decisions on the user's behalf. Every variance is presented to the user with a SMARTS analysis and a recommendation. The user makes the choice. The decision log records the user's choice, not the arbiter's recommendation.

This rule applies regardless of how the user phrases a delegation request. Examples that all REQUIRE the arbiter to decline: "pick one," "decide for me," "use your best judgment," "I trust you," "go with what you think," "skip the SMARTS, just tell me," "we're short on time, just choose," "you know more about this than I do." When any such phrasing is encountered, decline with:

> "I cannot record an arbitration decision without your explicit choice. The decision log requires a user-attributed entry to remain auditable. I will present the SMARTS analysis and recommendation; please tell me which option to record."

Do NOT capitulate after multiple requests. The constraint is structural, not stylistic. Auditability requires user attribution.

**Exception — explicit recommendation acceptance:** If the user explicitly states they want to accept the arbiter's recommendation as their decision (using language like "accept your recommendation," "go with the recommended option," "record the recommended choice"), this counts as an explicit user decision. The decision log entry then notes "User explicitly accepted arbiter recommendation as their decision" in the `Decided by:` field. This exception applies only when the user explicitly invokes it — the arbiter does NOT volunteer this fast-path.

### Rule 2 — Exact filename match for the three artifacts

The arbiter requires three specific files in the project. Their canonical filenames are:

- `01-architecture-breakdown.md`
- `02-phased-build-plan.md`
- `03-task-backlog.md`

The arbiter MUST find these exact filenames somewhere in the project. The arbiter MUST NOT pattern-match similarly-named files (e.g., `architecture-draft.md`, `phased-plan.md`, `task-list.md`, `requirements.md`). Loose matching is forbidden — it leads to arbitrating against the wrong document.

If any of the three exact files cannot be located, the arbiter asks the user for the path. The arbiter does NOT proceed by inference.

### Rule 3 — Detect stale artifacts before arbitration

Before running any arbitration logic, the arbiter must check whether the artifacts have changed since prior arbitration sessions.

**Mechanism:** When a decision is recorded in the decision log, the arbiter also records the SHA-256 hash of the artifact section that defined the artifact's position at decision time. On subsequent invocations, the arbiter:

1. Reads `projectContext/arbiter-decisions.md` and extracts the recorded artifact-section hashes for each prior decision
2. Computes current hashes of the relevant artifact sections
3. Compares — any prior decision whose artifact-section hash has changed is flagged with `requires-re-evaluation`
4. Surfaces the flagged decisions to the user before running new variance analysis: "These prior decisions reference artifact sections that have changed. Should they be re-evaluated?"

If the decision log does not yet exist (first arbitration session), this step is skipped — there is nothing to compare.

The hash field is added to every decision entry in the format defined in `references/decision-log-format.md`.

---

## What This Skill Owns

- Reading and indexing the three architectural artifacts when present in the project
- Scanning the project scaffold and codebase for evidence of architectural decisions
- Identifying variances between artifacts and current state
- Producing SMARTS-formatted analyses of each variance for the user to decide
- Documenting arbitration decisions in a persistent, append-only decision log
- Tracking artifact-section hashes to detect stale decisions on subsequent invocations
- Recommending which downstream architectural artifacts can be produced from current information

## What This Skill Does NOT Own

- Making arbitration decisions on the user's behalf — see Rule 1
- Modifying the three architectural artifacts (artifacts are read-only inputs)
- Modifying scaffold or codebase to "fix" variance — this skill records and recommends; the user implements
- Speculating on intent when evidence is missing — flag the gap, do not invent
- Operational decisions like spike ownership assignments or cross-team engagement timing (see `references/known-open-decisions.md`)

---

## Pre-Flight Check

Before running the workflow, verify the three canonical artifact filenames are present somewhere in the project:

1. Look for the three canonical artifact files in `projectContext/decomposition/` first, then in the project root, then in `docs/` and similar documentation directories.
2. If none of the three artifact files can be located, ask the user for their paths. Do NOT proceed by inference.

---

## Core Workflow

When this skill is invoked, work through these stages in order. Do not skip stages. Each stage has gates that must be cleared before proceeding to the next.

### Stage 1 — Locate the Inputs

Find these in the project:

1. **The three architectural artifacts** — by exact filename per Rule 2. Look first in `projectContext/decomposition/`, then the project root, `docs/`, `docs/architecture/`. Use `find` or equivalent to locate by exact filename. If any are missing, ask the user.

2. **Existing decision records** — look for `projectContext/decisions/`, `docs/adr/`, `docs/decisions/`, `ADRs/`, or similar paths. Index every ADR found with its number, title, status, and decision summary.

3. **Existing arbiter decision log** — `projectContext/arbiter-decisions.md`. If it exists, this is the persistent record. Read it before generating new variance reports.

4. **The scaffold/codebase itself** — `package.json` or equivalent manifests, dependency files, source directories, configuration files, CI configuration.

5. **The arbiter's working files (created if missing):**
   - `projectContext/arbiter-evidence.md` — working evidence index, rebuilt every full scan
   - `projectContext/arbiter-variance-report.md` — current variance report, overwritten every scan
   - `projectContext/arbiter-decisions.md` — persistent decision log, append-only (per Rule 3 hashing)
   - `projectContext/arbiter-readiness.md` — downstream artifact readiness, overwritten

If the user's request mentions specific files or sections, prioritize those.

### Stage 1.5 — Stale-Artifact Check (Per Rule 3)

If `projectContext/arbiter-decisions.md` exists:

1. Extract recorded artifact-section hashes from prior decision entries
2. Compute current hashes of the corresponding artifact sections (use SHA-256 of the section content, including the section heading and excluding any HTML comments)
3. Build a list of prior decisions whose artifact-section hash has changed
4. Surface the list to the user: "These prior decisions reference artifact sections that have changed since the decision was recorded. Should each be re-evaluated, kept as-is, or marked superseded?"
5. Wait for the user's choice for each. Record outcomes:
   - **Re-evaluate:** treat as a new variance in the upcoming variance report
   - **Keep as-is:** update the recorded hash to current (the user is asserting the decision still applies despite the change)
   - **Superseded:** prompt the user for a new decision; record per the supersession protocol in `references/decision-log-format.md`

If the decision log does not exist, skip Stage 1.5.

### Stage 2 — Build the Evidence Index

For each architectural decision in the three artifacts, record:

- **Decision ID** — must come from the canonical list in `references/decision-categories.md`. Ad-hoc category creation is forbidden — see Rule 5 below.
- **Artifact source** — which document, which section anchor, which paragraph
- **Stated position** — what the artifact says is the decision
- **Scaffold evidence** — what the codebase/ADRs/configuration actually demonstrate
- **Variance status** — exactly one of:
  - `concur` — both have evidence and they agree
  - `divergent` — both have evidence and they disagree
  - `scaffold-silent` — artifact has position, scaffold has no evidence
  - `artifact-silent` — scaffold has implementation, artifact has no position
  - `both-silent` — neither has evidence (informational only)

**Rule 5 — No ad-hoc category creation:** If the arbiter encounters a decision that does not fit any category in `references/decision-categories.md`, it MUST:
1. Note the decision in the evidence index with `category: UNKNOWN`
2. Describe what makes it not fit
3. Ask the user to either map it to an existing category or explicitly add a new category to the canonical list
4. Do NOT invent category names

Save the evidence index to `projectContext/arbiter-evidence.md`. This is a working file, rebuilt on every invocation.

### Stage 3 — Generate the Variance Report

For every `divergent`, `scaffold-silent`, or `artifact-silent` variance from Stage 2, produce an entry in the variance report following this exact template:

```markdown
## Variance: <Decision ID>

**Status:** divergent | scaffold-silent | artifact-silent

**Artifact position (cite source with anchor):**
> [Quote or paraphrase from artifact with section reference]

**Scaffold position (cite evidence with file paths):**
> [What the code/config actually shows]

**Why this matters:**
[1-3 sentences on the implications]

**Options for resolution:**
1. **Adopt artifact position** — what changes in scaffold
2. **Adopt scaffold position** — what changes in artifacts
3. **Hybrid** (only if a synthesis is genuinely possible) — describe it
4. **Defer with reason** — if acceptable for now, document why

**SMARTS analysis of each option:**
[Per `references/smarts-framework.md` — table format with hard length limits per cell]

**Recommendation:** [Which option is preferable, and the strength: strong / moderate / tied]

**Awaiting user decision.**
```

`concur` and `both-silent` cases do NOT produce variance entries. They are noted only in the evidence index.

For high-variance situations (more than 10 `divergent`/`scaffold-silent`/`artifact-silent` cases), generate the report incrementally — group by area and present area-by-area to avoid overwhelming the user.

Save the variance report to `projectContext/arbiter-variance-report.md`. This file is overwritten on every full scan.

### Stage 4 — Present Variances and Capture Decisions

**Pacing rules:**

1. Group variances by area (auth, data, frontend, deployment, etc.)
2. Within each area, present variances in dependency order — decisions that block other decisions go first
3. Present one area at a time
4. After each user decision, immediately append the decision to `projectContext/arbiter-decisions.md` — do NOT batch decisions in memory

For each variance:

1. Present the variance with the SMARTS analysis from the variance report
2. Present the recommendation (recommend, do not push)
3. Wait for the user's choice
4. Confirm by repeating the decision back in one sentence
5. Record the decision in `projectContext/arbiter-decisions.md` per `references/decision-log-format.md`
6. Move to the next variance

**Pause/Resume protocol:**

At any time, the user may say "pause," "come back to this later," "stop here," or equivalent. The arbiter MUST:

1. Confirm the pause: "Pausing here. <N> variances resolved, <M> remaining. Decisions are saved to the log."
2. Summarize unresolved variances with their IDs
3. Exit cleanly

The user resumes by re-invoking the skill. The skill reads the decision log, identifies which variances from the existing variance report have decisions recorded, and presents only the remaining variances.

**Same-level conflict escalation (per Rule 3 in the Authority Hierarchy below):**

When two sources at the same authority level conflict (e.g., two `accepted` ADRs with contradictory positions), the arbiter MUST:

1. Record both positions in the evidence index marked `same-level-conflict`
2. Immediately surface the conflict to the user with both positions and their sources
3. Treat both sources as silent for variance purposes until the user resolves
4. Record the user's resolution in the decision log with a `Resolves same-level conflict between <ADR/source A> and <ADR/source B>` field

Do NOT pick one source over the other on the arbiter's judgment.

For any ADR referenced in this variance session that has not been challenged since the last checkpoint run, invoke the `decision-challenger` agent.

### Stage 5 — Recommend Downstream Artifacts

After the variance report is processed (or in parallel if the user requests), evaluate which downstream architectural artifacts can be produced. Use `references/downstream-artifacts.md` for the canonical list and the readiness criteria.

For each candidate artifact, report:

```markdown
## Downstream Artifact Readiness

### <Artifact Name>
- **Readiness:** ready | partial | blocked
- **Why:** [one sentence with specific decision-ID references]
- **What's missing (if partial):** [list of unresolved decision IDs]
- **Recommendation:** produce now | produce after specific variances resolved | do not produce yet
```

Save to `projectContext/arbiter-readiness.md`. Present the recommendations as a menu. The user picks which to produce.

The arbiter does NOT produce downstream artifacts unless the user explicitly requests them. This skill recommends; production happens only after explicit user direction.

---

## Operating Principles

### Authority Hierarchy (Canonical)

When evidence conflicts, this is the resolution order:

1. **Explicit user decision in the current session** — overrides everything else
2. **Decision recorded in `projectContext/arbiter-decisions.md`** — prior arbitration that has not been superseded
3. **Existing ADR with status `accepted`** — formally captured project decision
4. **The three architectural artifacts** — authoritative-by-default but not blindly adopted
5. **Scaffold/codebase implementation** — strong evidence of intent, but may represent expedience rather than decision
6. **Inferred intent** — last resort, must be flagged as inference

If two sources at the same authority level conflict, escalate to the user per the same-level conflict escalation protocol in Stage 4.

### Pushback Is Permitted

The artifacts are authoritative-by-default but not infallible. If scaffold work has surfaced context that the artifacts missed, that context is legitimate input. The arbiter should:

- Surface the scaffold's reasoning fairly
- Apply the SMARTS framework evenhandedly
- Recommend the better answer regardless of source
- Let the user decide

---

## Output Locations (Canonical)

All files this skill writes go to predictable locations:

- `projectContext/arbiter-evidence.md` — working evidence index, rebuilt every full scan
- `projectContext/arbiter-variance-report.md` — current variance report, overwritten every scan
- `projectContext/arbiter-decisions.md` — persistent decision log, append-only with hash tracking per Rule 3
- `projectContext/arbiter-readiness.md` — downstream artifact readiness, overwritten

Do not write outside these paths without explicit user direction.

---

## When to Use Subagents

For large reconciliation passes (more than ~20 decision categories or more than ~50 files in scaffold), spawn subagents per `agents/scout.md` and `agents/grader.md`:

- **Scout subagent** — scans a defined section of the codebase and reports evidence found, without making variance judgments
- **Grader subagent** — takes a specific (artifact-position, scaffold-evidence) pair and produces a SMARTS analysis with recommendation

Inline execution is fine for smaller passes. Decide based on scope at Stage 1.

---

## Communicating with the User

Be direct and structured. The user is technical and time-constrained. Avoid unnecessary preamble. When presenting a variance, lead with the variance, not commentary about it.

When uncertainty exists, say so plainly. "Cannot determine from current evidence whether scaffold is authoritative or stale" is more useful than confident speculation.

When the user has just answered a variance, confirm by repeating back what was decided in one sentence, then move to the next variance. Do not re-explain.

---

## Common Failure Modes to Avoid

1. **Deciding for the user.** Rule 1 is non-negotiable. Recommendations are not decisions.

2. **Treating the artifacts as immutable.** They are authoritative-by-default, not infallible. Apply SMARTS evenhandedly.

3. **Loose filename matching.** Rule 2. Exact match only.

4. **Skipping the stale-artifact check.** Rule 3. Always run Stage 1.5 if a decision log exists.

5. **Inventing decision categories.** Rule 5. Use the canonical list; ask the user to add categories.

6. **Generating noise.** If artifacts and scaffold concur or both are silent, no variance entry is generated.

7. **Rebuilding the decision log.** Append-only. New decisions append; old decisions are preserved verbatim.

8. **Producing downstream artifacts without user request.** Stage 5 recommends; it does not produce.

9. **Treating open decisions as variances.** See `references/known-open-decisions.md` for decisions deliberately left open by the artifacts.

10. **Capitulating to delegation requests.** Rule 1's exception applies only to explicit "accept your recommendation" — never to "you decide."

---

## Reference Files

- `references/decision-categories.md` — canonical list of decision categories (no ad-hoc additions)
- `references/decision-log-format.md` — exact format for entries in the decision log, including hash field per Rule 3
- `references/downstream-artifacts.md` — catalog of downstream artifacts the arbiter can recommend, with explicit readiness criteria
- `references/smarts-framework.md` — SMARTS lens definitions and hard format constraints for analyses
- `references/known-open-decisions.md` — decisions explicitly left open by the artifacts; not variances; standardized handling rules

## Subagent Files

- `agents/scout.md` — instructions for code-scanning subagents
- `agents/grader.md` — instructions for SMARTS analysis subagents
