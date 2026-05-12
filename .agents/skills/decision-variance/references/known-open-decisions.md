# Known Open Decisions

The architectural artifacts deliberately leave certain decisions open. This skill MUST NOT treat these as variances during arbitration — they are open by design.

This file enumerates each open decision and divides them into two scopes:

- **Arbiter-scope open decisions** — closeable through the arbitration process; standardized handling rules apply
- **Out-of-scope open decisions** — not arbitrated by this skill; surfaced for awareness only

## Standardized Handling Table (Arbiter-Scope Open Decisions)

For every arbiter-scope open decision, this skill applies this exact rule table:

| Scaffold state | Action |
|---|---|
| Implements artifact direction (the artifact's stated default or recommended path) | Note as consistent with deferral; no variance |
| Implements an artifact-listed alternative | Surface as `open-decision-closure` in the variance report; check whether closure was authorized in the decision log |
| Silent — no implementation yet | Note as consistent with deferral; no variance |
| Implements something not listed in the artifact's options | Surface as scope creep; verify with user before treating as a closure |

If the user decides to close the open decision during the arbitration session, the closure is recorded in `${PROJECT_ROOT}/.agents/projectContext/arbiter-decisions.md` with `Status type: open-decision-closure` per the format in `${FRAMEWORK_ROOT}/.agents/skills/decision-variance/references/decision-log-format.md`.

---

## Arbiter-Scope Open Decisions

This section is populated from the project's `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` and the open decisions explicitly documented in the three architectural artifacts. The entries below are template examples showing the format — replace with the actual open decisions from the current project's artifacts.

### Open Decision Template

**Where the artifacts say it is open:**
- [Artifact name] [§section reference]

**What is open:**
[Description of what has not been decided]

**Artifact-listed options:**
1. [Option 1]
2. [Option 2]
3. [Option N]

**What would close it:**
- [Condition or event that resolves the decision]

**Apply standardized handling table to this decision.**

---

## Out-of-Scope Open Decisions (Not Arbitrated by This Skill)

This skill explicitly does NOT arbitrate operational, political, or strategic decisions. If the user asks about them, this skill redirects to the appropriate resolution mechanism.

### Out-of-Scope: Personnel and Ownership Assignments

**Why out-of-scope:** Operational personnel decisions cannot be arbitrated by SMARTS analysis.

**Resolution mechanism:** Project team and management conversation.

---

### Out-of-Scope: External Stakeholder Engagement Timing

**Why out-of-scope:** Strategic relationship decision, not architectural. When to engage external parties is a leadership call.

**Resolution mechanism:** Leadership and project sponsor conversation.

---

## Anti-Pattern: Treating Open Decisions as Variances

If this skill is generating a variance entry for any item that is explicitly open in the artifacts, that is a bug in this skill's logic. Open decisions go in the readiness assessment file, not the variance report.

The distinction:
- **Variance** = artifacts and scaffold disagree on something the artifacts have a position on
- **Arbiter-scope open decision** = artifacts deliberately have no position; awaiting input; can be closed during arbitration via standardized handling
- **Out-of-scope open decision** = not architectural; not arbitrated by this skill at all

This skill must articulate the difference for any item it surfaces.

## Closing an Open Decision Mid-Arbitration

For arbiter-scope open decisions, if the user wants to close one during the arbitration session:

1. Confirm with the user that they want to close an artifact-deferred decision
2. Apply the SMARTS framework to the artifact-listed options
3. Record the decision in `${PROJECT_ROOT}/.agents/projectContext/arbiter-decisions.md` with `Status type: open-decision-closure` and a note that this closes an artifact-deferred decision
4. Update the readiness assessment to reflect the now-closed decision

For out-of-scope open decisions, this skill declines: "This is operational/strategic, not architectural — outside this skill's scope. The resolution mechanism is <X>."

## Populating This File for a New Project

When this skill first runs on a project, it should:

1. Read the three architectural artifacts for any sections explicitly labeled as open, deferred, or TBD
2. Read `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` for items explicitly flagged as unresolved
3. Add each identified open decision to this file in the arbiter-scope or out-of-scope section as appropriate
4. Present the populated list to the user for confirmation before proceeding with variance analysis

This ensures this skill does not generate false variance entries for decisions the artifacts deliberately left open.
