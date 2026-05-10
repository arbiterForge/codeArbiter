# Decision Log Format

This file defines the exact format used in `projectContext/arbiter-decisions.md`. The format is non-negotiable so the log remains machine-parseable on future arbiter invocations.

## Append-Only — No Edits Permitted

The decision log is **strictly append-only**. The arbiter MUST NOT edit any prior entry. Not even small edits. Not "fixing typos." Not "cleaning up formatting." Not "improving clarity." Not adding fields to old entries.

The only operation permitted on prior entries is **reading** them.

To supersede a prior decision, the arbiter appends a new entry whose `Supersedes:` field references the prior entry. Traversal from old to new is **forward-only**: readers scan forward in the log to find any entry whose `Supersedes:` field references the entry of interest. There is no backward-pointing `Superseded by:` field maintained on the prior entry. This makes append-only literally true with no exceptions.

## File Header

The decision log file always opens with this header (created on first write if the file does not exist):

```markdown
# Arbiter — Decision Log

This file is the persistent, strictly append-only record of arbitration decisions made during reconciliation between the project's architectural artifacts and the project scaffold.

**Append-only with no exceptions.** Prior entries are never edited. To supersede a prior decision, append a new entry whose `Supersedes:` field references the prior entry. Forward traversal from old to new entries is the only supported lookup pattern.

**Maintained by:** the `arbiter` skill, in collaboration with the user.

---
```

## Decision Entry Format

Every decision is appended as a new entry. Entries are separated by a horizontal rule (`---`). Each entry uses this exact structure:

```markdown
## DECISION-<NNNN> — <Decision ID> — <One-line summary>

**Date:** YYYY-MM-DD
**Status:** accepted | superseded | deferred
**Supersedes:** DECISION-NNNN | none
**Decided by:** <user identifier> | "user during arbitration session" | "User explicitly accepted arbiter recommendation as their decision"
**Decision category:** <category from decision-categories.md>
**Artifact-section-hash:** <SHA-256 hash of the artifact section that defined the artifact position at decision time, or "n/a" if the decision did not reference an artifact section>

### Variance summary

- **Artifact position:** [one sentence]
- **Scaffold position:** [one sentence]
- **Status type:** divergent | scaffold-silent | artifact-silent | same-level-conflict-resolution | open-decision-closure

### Decision

[The choice the user made. Two to four sentences. Be specific — record what was decided, not what was discussed.]

### SMARTS rationale

[Brief justification using the SMARTS framework. Two to six sentences. Reference the lenses that drove the decision.]

### Implementation implication

[What changes as a result of this decision. Reference specific scaffold files, ADRs, or artifact sections that need to be updated.]

### Re-evaluation trigger (deferred decisions only)

[If status is `deferred`, the specific event or condition that should trigger re-evaluation. Otherwise omit this section.]

### Resolves same-level conflict between (when applicable)

[If this decision resolved a same-level conflict per the protocol in SKILL.md Stage 4, name both conflicting sources. Otherwise omit.]

---
```

## The Artifact-Section-Hash Field (Per Rule 3)

Every decision entry records the SHA-256 hash of the artifact section that defined the artifact's position at decision time. This enables stale-artifact detection on subsequent invocations.

**How to compute the hash:**
1. Identify the section of the artifact that contains the artifact position cited in the variance entry
2. Take the section content from the section heading (inclusive) to the next same-level or higher heading (exclusive)
3. Strip HTML comments (anything between `<!--` and `-->`)
4. Compute SHA-256 over the resulting bytes (UTF-8)
5. Record the full 64-character hex digest

**When the field is `n/a`:**
- Decisions that close an artifact-deferred open decision (the artifact has no position)
- Decisions for `artifact-silent` variances (the artifact has no position)
- Decisions for `META.*` categories (process decisions, not artifact-driven)

**Stale detection:** On subsequent arbiter invocations, Stage 1.5 recomputes hashes for the cited sections and flags any decision whose hash has changed.

## Decision Numbering

Entries are numbered sequentially as `DECISION-0001`, `DECISION-0002`, etc. The arbiter maintains the next number by reading the existing log. Numbers never gap and never skip.

If two arbitration sessions race to write decisions, the later session uses the next available number — there is no merge conflict semantics defined for this case (single-user assumption holds for the prototype phase).

## Status Values

- **accepted** — the decision is in force; scaffold and artifacts should reflect it
- **superseded** — a later decision replaced this one; this entry remains for audit. Forward-only lookup: search the log for any entry whose `Supersedes:` references this DECISION-NNNN.
- **deferred** — the user chose not to decide yet; re-evaluation trigger is required

A new entry is written with `Status: accepted` when it supersedes a prior entry. The new entry carries `Supersedes: DECISION-NNNN` referencing the old one. The old entry is never touched.

## Worked Example: Initial Decision

```markdown
## DECISION-0001 — STACK.AUTH.AUTHORIZATION — Authorization engine selected: OPA bundled

**Date:** 2026-05-10
**Status:** accepted
**Supersedes:** none
**Decided by:** user during arbitration session
**Decision category:** STACK.AUTH.AUTHORIZATION
**Artifact-section-hash:** 7a3b9c2e5f8d1a4b6c9e2d5f8a1b4c7d0e3f6a9b2c5d8e1f4a7b0c3d6e9f2a5b

### Variance summary

- **Artifact position:** OPA bundled, owns all authorization; identity provider owns only authentication (Architecture Breakdown §3.5–3.6)
- **Scaffold position:** silent — no authorization engine integration in scaffold yet
- **Status type:** scaffold-silent

### Decision

Adopt the artifact position. OPA will be bundled in the deployment package and own all authorization decisions. The identity provider handles only identity verification. The OPA policy bundle will be sourced from the project's policy repository.

### SMARTS rationale

Maintainability and Securability dominate. Separating authentication from authorization keeps authorization logic portable across identity providers and centralizes authorization decisions for audit and policy review. Self-contained packaging is preserved.

### Implementation implication

Create task to bundle OPA in the deployment chart. Define initial policies for MVP role-based access. A policy bundle structure spike is required before policy expansion.

---
```

## Worked Example: Superseding Decision

```markdown
## DECISION-0042 — STACK.AUTH.AUTHORIZATION — Replace OPA with Cedar

**Date:** 2026-08-15
**Status:** accepted
**Supersedes:** DECISION-0001
**Decided by:** user during arbitration session
**Decision category:** STACK.AUTH.AUTHORIZATION
**Artifact-section-hash:** 9f2e5b8c1a4d7e0f3a6b9c2e5f8d1a4b7c0e3f6a9b2c5d8e1f4a7b0c3d6e9f2a

### Variance summary

- **Artifact position:** OPA bundled, owns all authorization (Architecture Breakdown §3.6, current)
- **Scaffold position:** Cedar policies in `policies/cedar/` directory; OPA removed from deployment chart
- **Status type:** divergent

### Decision

Adopt the scaffold position. Replace OPA with Cedar based on operational experience during MVP: Cedar's strict typing produced fewer runtime policy errors than OPA's permissive Rego.

### SMARTS rationale

Reliability dominated this revision. OPA Rego policies failed open in two MVP incidents due to typos in policy attribute names; Cedar's compile-time validation prevents this class of error. Maintainability remains roughly equivalent. Securability improves due to the typing.

### Implementation implication

Architecture Breakdown §3.6 requires update to reflect Cedar. Any ADR capturing the OPA choice requires a superseding ADR. Update enforcement to validate Cedar instead of OPA bundles.

---
```

To find that DECISION-0001 was superseded, a reader scans forward and finds DECISION-0042 with `Supersedes: DECISION-0001`. The original DECISION-0001 is unchanged.

## Anti-Patterns to Avoid

- **Editing prior entries.** The log is append-only. Period. There is no exception.
- **Compressing multiple decisions into one entry.** Each variance gets its own decision entry. If a single user response covers multiple variances, write multiple entries.
- **Recording "no decision needed."** If artifacts and scaffold concur, no decision entry is written. The decision log records actual arbitrations.
- **Omitting the SMARTS rationale.** The rationale is what makes the decision auditable later. "User decided" without rationale is insufficient.
- **Generating decisions without explicit user input.** The arbiter never writes a decision entry on its own initiative. Every entry is the record of an explicit user choice.
- **Omitting the artifact-section-hash field.** The hash is required for stale-artifact detection. If the field is genuinely `n/a`, write `n/a` — do not omit the field.
- **Maintaining backward `Superseded by:` links on prior entries.** Forward-only links from new entries. No exceptions.

## Reading the Log on Future Invocations

When the arbiter starts a new session, it reads `projectContext/arbiter-decisions.md` from top to bottom and indexes:

- Every entry by its `DECISION-NNNN` ID
- For each entry, its current `Status` and any `Supersedes` reference
- The recorded `Artifact-section-hash` for each entry

For each `accepted` entry, the arbiter checks whether a later entry supersedes it (forward scan). If yes, the later entry is authoritative. If no, the entry remains in force.

For each `accepted` or `deferred` entry whose `Artifact-section-hash` is not `n/a`, the arbiter recomputes the current hash of the referenced section. If the hash has changed, the entry is flagged for re-evaluation per Stage 1.5 of the workflow.

For each variance discovered in Stage 2, the arbiter checks whether a prior decision exists for that Decision ID:

- If `accepted` and not flagged stale: the variance is already resolved; do not re-arbitrate unless the user explicitly asks
- If `accepted` and flagged stale: surface to the user during Stage 1.5 for re-evaluation
- If `deferred`: check the re-evaluation trigger; if met, surface the variance again; if not, leave deferred
- If superseded by a later entry: treat the superseding entry as authoritative

This is how the log creates persistent, stale-aware arbitration state across sessions.
