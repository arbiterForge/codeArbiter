# Reconciliation analysis

Private reference for decision-variance Phases 1-3. Load only after that owner has
selected an actual pass and its scope. This card has no discovery frontmatter and
no independent entry. It returns evidence and recommendations to its caller.
"Write an entry" below means compose the returned report: no evidence-index file,
report file, decision-log append, question, marker, directory or artifact mutation
is authorized here. Pass that read-only boundary to any scout or grader, retaining
scout evidence as an appendix in the returned report rather than an on-disk file.

Read `{{PLUGIN_ROOT}}/includes/smarts/core.md` before Phase 3.

## Pre-flight - scope before prerequisites

Read `{{PROJECT_DIR}}/.codearbiter/CONTEXT.md` and its `stage:` value. Unreadable or
missing required context is reported as a gap, never initialized by this pass.
Read `{{PROJECT_DIR}}/.codearbiter/security-controls.md` only when a variance touches
a security boundary (auth, crypto, secrets); do not fabricate its Securable inputs.

For a **full pass**, locate all three decomposition artifacts by **exact filename**:
`01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md`.
Search `{{PROJECT_DIR}}/.codearbiter/plans/` first, then the project root, then
`docs/`, retaining the actual selected paths and any explicit user path. Do not
substitute similarly named files. These are decomposition records, not
interchangeable with HTML feature specs/plans. A missing required source prevents
a complete full pass; return the supported partial findings and ask for the
missing path only when necessary to continue, never invent a clean result.

For a **scoped pass**, resolve the named ADR, artifact or area and relevant prior
records first; do not require unrelated decomposition files. Load other source
sections only where the selected comparison or its governing decisions need them.
An ADR is identified by its full filename stem. Resolve a numeric or `ADR-NNNN`
selector against the complete filename index; zero matches is missing and multiple
matches are ambiguous. List the candidates rather than selecting the first.
This procedure compares Markdown architectural records and their cited sections.
A typed HTML feature spec/plan needs its existing typed workflow owner, not this
Markdown section-hash path. Return that format boundary to the caller; do not parse
rendered HTML, convert formats, or substitute decomposition records.
A scoped result is not a full-project clearance. If a target or cited section cannot
be resolved, preserve that limitation rather than silently changing the scope.

## Phase 1 - Locate inputs and detect stale decisions

Index selected artifacts by document and section anchor, ADRs by full filename stem,
title and stored status, the append-only
`{{PROJECT_DIR}}/.codearbiter/decisions/decision-log.md`, and relevant scaffold
manifests, dependencies, source, config and CI. Read indexes/headings first, then
relevant bodies; do not bulk-read every plan and ADR. Check governing sources beyond
the named scope where needed, but do not broaden the work or claim wider coverage.
An absent ADR directory or log means no recorded history, not an instruction to
create it. Unreadable existing history is unknown, not an empty successful index.

When a log exists, run its stale-artifact check before generating new variances.
Follow forward `Supersedes:` references to identify current decisions without
rewriting history. For relevant current entries, recompute the recorded section
SHA-256 using `{{PLUGIN_ROOT}}/includes/smarts/decision-log-format.md`: heading
inclusive to the next same-or-higher heading, HTML comments stripped, UTF-8.
`n/a` remains the schema's no-artifact-source case, not a wildcard freshness pass.
A missing or ambiguous section cannot be hashed by guessing, and a changed hash
is stale evidence, not proof that the original decision was wrong.

Surface stale IDs, cited sources and the available re-evaluate / keep / supersede
choices, then continue independent analysis. A report does not demand their
resolution before it can be returned. Re-evaluation becomes an unresolved variance;
ratification or supersession is captured only by the owner's Phase 4. An explicit
keep against the changed section uses a new attributed entry with its current
section hash and `Supersedes:`, not in-place editing. An unresolved stale choice
cannot support a downstream `ready` claim for the affected obligation.

Gate: selected inputs and coverage gaps are known, history has been checked, and
stale decisions are visible. Unknown state is not a clean clearance.

## Phase 2 - Build the evidence index

For each in-scope architectural decision, record its decision ID, artifact source
(document and section anchor), stated position, scaffold file evidence and exactly
one comparison status:

- `concur`: both have evidence and agree.
- `divergent`: both have evidence and disagree.
- `scaffold-silent`: artifact states a position, scaffold shows nothing.
- `artifact-silent`: scaffold implements it, artifact is silent.
- `both-silent`: neither has evidence; informational only.

Missing or unreadable inputs are coverage gaps, not evidence of silence. Same-level
conflicts are unresolved authority flags in addition to the comparison status,
not `both-silent`. Always include these conflicts as unresolved report items,
even when the artifact/scaffold comparison itself is `concur`. Use `category: UNKNOWN` when no established category fits; this
is not a reason to pause a report or invent a category. Surface the mapping needed
before a later decision write requires it.

Gate: every in-scope decision has one supported comparison status or an explicit
coverage gap. Every non-silent side has a concrete citation. Partial evidence
cannot establish absent behavior or complete reconciliation.

## Phase 3 — Generate the variance report · gate: BLOCK

For every `divergent`, `scaffold-silent`, or `artifact-silent` case, write one entry: the artifact
position (cited with anchor), the scaffold position (cited with file paths), why it matters (1–3
sentences), the resolution options (adopt artifact / adopt scaffold / hybrid only if a real synthesis
exists / defer with reason), a SMARTS analysis of each option, and a recommendation with a strength
label. `concur` and `both-silent` cases produce no entry — they live in the evidence index only.

The SMARTS table follows `{{PLUGIN_ROOT}}/includes/smarts/core.md` exactly: six lenses, verdict-first cells (Strong /
Adequate / Weak / Indifferent), the length cap, no hedging adverbs, evidence specificity. The
recommendation carries one strength label — strong / moderate / tied.

**Precedent row.** Before writing the tables, scan the existing decision log once: tally which
lenses prior resolutions turned on (which lens was decisive, which way ties broke) and note
decisions whose subject overlaps this variance. Under each SMARTS table, append one `Precedent:`
line citing the 1–3 most similar prior decisions by ID and the observed pattern — e.g.
`Precedent: D-014 (bundled over external, Available decisive), D-009; this log has broken 3 of 4
ties toward Maintainable.` No prior decisions, or none relevant → `Precedent: none on record` —
never invent a pattern from thin history (fewer than 3 relevant entries is "none yet established").
Precedent informs the recommendation; it never outranks the Phase 4 authority order, and it is
input to the user's choice, not a substitute for it.

For more than ~10 open variances, group by area and present area-by-area. For a large pass (more
than ~20 decision categories or ~50 scaffold files), MAY dispatch `scout`
(`{{PLUGIN_ROOT}}/agents/scout.md`) to gather evidence and `grader`
(`{{PLUGIN_ROOT}}/agents/grader.md`) to produce SMARTS analyses. Inline execution is fine for
smaller passes.

Gate: every qualifying variance has a conformant SMARTS table and a strength-labeled
recommendation. No `concur`/`both-silent` noise in the report.

## Return boundary

Return the report to decision-variance with its selected scope and mode. Analysis
does not authorize decision capture or persistence for a report-only request.
