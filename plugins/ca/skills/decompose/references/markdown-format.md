# decompose — Markdown-format repositories

This is the procedure for a repository whose `knowledge.py format` reports
`markdown` and whose user keeps that format rather than importing it. The
greenfield sections retain the pre-HTML workflow; HTML-format repositories
follow the skill entry.

Develop the project specification before implementation. Keep actual user decisions,
planned architecture and observed repository facts distinct.

## 1. Inspect and resume

Read `.codearbiter/CONTEXT.md`. An explicit initialized brownfield
project-model request uses the acquisition section below; ordinary source drift
uses `/ca:context-check`. In an uninitialized project, meaningful
implementation source routes to `/ca:create-context`. If the scaffold is
absent, run `/ca:init` first.

Keep the interview in `.codearbiter/plans/decomposition/`: `_session.md` records the
current phase, remaining questions and actual user confirmations; each completed
layer has its own file. Read this state and resume the first unfinished step. Do not
repeat settled questions or require another approval of unchanged accepted work.
An explicit restart preserves earlier interview and decision history.

If `.codearbiter/.decompose-draft/` contains an interrupted interview, copy its session
and layer records to the durable directory before using them as source evidence.
Compare existing destinations byte-for-byte: retain identical files, and reconcile
conflicting versions without overwriting either. Temporary drafts remain until
initialization completes. Never cite a temporary file that cleanup will remove.

## Initialized brownfield acquisition

Keep the existing `<!--INITIALIZED-->` marker, CONTEXT frontmatter, human edits,
provenance, decomposition files, question and ADR history, and task identities.
Inspect those owners before writing. Use `/ca:context-check` for selected
source-backed refreshes of the existing Markdown context/provenance pairs; do
not invoke `create-context`, `--context-finalize`, or the initial interview.
If inspection is denied or incomplete, record the affected observation as
unknown instead of inferring that a capability is absent.

Maintain the existing project model under `.codearbiter/plans/`. Record
source-observed current capabilities and architecture with exact source paths
in `01-architecture-breakdown.md`; proposed target, delta and future phases in
`02-phased-build-plan.md`; and possible work in a clearly marked candidate
section of `03-task-backlog.md`. Read existing files first and update only the
affected sections, preserving earlier answers and user edits.
Link existing questions and ADRs by identity, without copying their mutable
status. Code inspection alone cannot establish deployment, passing checks,
historical rationale or an accepted choice. Ask only consequential unknowns
that affect the selected target.

Candidates are not tasks or tracker tickets. When the user selects promotion,
check the stable origin against active and archived work through the selected
work owner. Retain the returned work ID in the candidate and repair that same
link on retry. The legacy task-board writer remains the owner in an unconverted
project; do not create a parallel native work record. Report changed documents,
source scope and remaining unknowns, then return to the requested work. The
greenfield interview and initialization steps below do not run on this path.

## 2. Capture the interview

Explain briefly that you will establish scope, architecture and a build sequence.
Ask focused questions only where existing answers do not establish the needed facts
or choices. Use these six layers; record an inapplicable category with its reason.
Persist each layer before proceeding. Each record contains the question, actual
answer, relevant trade-offs and unresolved `[CONFIRM-NN]` items. Keep each source
file within 1 MiB; split a long layer into named parts. Exclude secret values.

| Layer and file | Required outcomes |
|---|---|
| 1 — `layer-1-vision.md` | Problem, primary users, demonstrable success and exclusions. |
| 2 — `layer-2-flows.md` | User journey, non-human actors, failure experience and privilege boundaries. |
| 3 — `layer-3-functional-scope.md` | Capabilities with initiators, inputs and outputs; MVP/v1/later classification; hardest user-facing risk. |
| 4 — `layer-4-tech-shape.md` | Components and ownership, entities, state/write paths, stack and other hard constraints, technical risks, copyright holder, actual architectural choices and release intent. |
| 5 — `layer-5-integrations.md` | External dependencies, available contracts/authentication, ownership, reliability, cost and fallback requirements. |
| 6 — `layer-6-risks.md` | Material risks with mitigations, unresolved questions, bounded spikes and architecture-change triggers. |

Record a user-decided architectural choice through `decision-lifecycle` at
`${CLAUDE_PLUGIN_ROOT}/skills/decision-lifecycle/SKILL.md`. It owns ADR numbering,
attribution, authoring and status transitions. Preserve draft choices as drafts
until the user actually decides; do not create an ADR merely to fill a quota.

Release intent is elicited here: capture the **tag prefix** preference and
**changelog kept** yes/no in Layer 4. No `.codearbiter/release-targets.md` row is ever written by this skill.
Greenfield runs before any manifest or tag exists. `/ca:release` or a subsequent
context refresh derives a target from the actual manifest and delivery structure.

An unresolved consequential choice blocks its dependent output. Record other gaps
as questions; a user's explicit deferral remains unresolved and is not permission.

## 3. Synthesize and confirm

Re-read the retained layer records and relevant ADRs. Write these three artifacts
under `.codearbiter/plans/`, using the recorded evidence:

- `01-architecture-breakdown.md`: components, responsibilities, connections,
  integration boundaries and remaining architectural questions.
- `02-phased-build-plan.md`: MVP and subsequent phases, scope, risks, deferrals and
  measurable completion criteria.
- `03-task-backlog.md`: prioritized, bounded tasks with roles, dependencies and
  time-boxed spikes.

Present the files for review. Apply corrections and record the user's actual
confirmation in `_session.md`; existing confirmation covers unchanged artifacts.
Proceed when the artifacts accurately represent the user's choices and each gap is
resolved or explicitly retained on the question board.

## 4. Populate context

Re-read the approved artifacts and retained interview sources. Prepare UTF-8 drafts
outside the five target paths, each at most 128 KiB. Use only relevant retained
sources for each document; planned choices must not be described as implemented facts.
Use the matching document title: `# Project: <name>`, `# Tech stack`,
`# Coding standards`, `# Security controls` or `# Code map`.
Preserve existing CONTEXT frontmatter exactly; the scaffold owns activation and stage.

| Document ID | Content |
|---|---|
| `CONTEXT` | Identity, purpose, users, scope and exclusions; frontmatter `arbiter: enabled` and one `stage:` number. |
| `tech-stack` | Intended runtime, frameworks, tooling and confirmed conventions. Mark commands without a real manifest as planned, not verified executable commands. |
| `coding-standards` | Confirmed structural/style conventions and copyright holder. |
| `security-controls` | Actual trust boundaries, authentication requirements, secret handling and prohibited primitives. |
| `code-map` | Planned concerns and ownership. Distinguish proposed paths from existing paths; state when no implementation paths exist yet. |

For each of the five documents, invoke the installed writer:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "${CLAUDE_PROJECT_DIR}" --context-draft "<draft.md>" --document "<document-id>" --source ".codearbiter/plans/decomposition/<layer-file.md>"
```

Repeat `--source` for each relevant retained source, up to 64 per document. Inspect
the returned preview, exact preimage and source bindings, then apply that preview
under the existing authorization:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "${CLAUDE_PROJECT_DIR}" --context-apply "<preview_ref>" --preview-sha256 "<preview_sha256>"
```

The writer commits each document and its v2 provenance record together. Do not write
those protected pairs directly. A digest records inspected bytes; it does not certify
semantic review or user authority. If source or output bytes change, inspect the
changed input and prepare a fresh preview. Reuse the same retained preview after an
uncertain response; recovery determines whether its transaction committed.

Populate the other records through their owners:

- Add each approved backlog item with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/taskwrite.py" add "<task>"`.
  Compare the existing board before retrying so resumed population does not duplicate
  tasks. Never write task rows directly or mark planned work done.
- Record unresolved questions in `open-questions.md`, retaining the scaffold and
  actual resolution or deferral history. An empty question board is valid.
- Preserve `overrides.log`, `last-checkpoint` and all ADR history. The scaffold owns
  their creation; initialization does not invent audit events or acceptance evidence.

Verify all five v2 pairs, the task/question boards and audit header are present.
Do not scaffold cut documents listed in `${CLAUDE_PLUGIN_ROOT}/includes/cut-docs.md`.

## 5. Finalize and return to work

Preview initialization against the exact five document/provenance pairs and the
three independent board/audit outputs:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "${CLAUDE_PROJECT_DIR}" --context-finalize
```

Inspect the result and apply its `preview_ref` and `preview_sha256` with
`--context-apply`. The writer validates current outputs and source evidence, then
commits the standalone `<!--INITIALIZED-->` marker and matching CONTEXT provenance
together. Missing, stale or malformed input names the repair needed; never append
the marker manually. Recover an uncertain transaction before preparing another.

Read back the committed result and all required outputs. Keep
`.codearbiter/plans/decomposition/`, approved plans and decision history. Remove only
this run's temporary drafts after confirming no provenance source refers to them.
Record completion in `_session.md`. Report the populated context, unresolved choices
and actual checks, then continue authorized work. Initialization records population;
it does not certify host enforcement, semantic review or passing tests.

When source and manifests arrive, `/ca:context-check` refreshes the selected
context against those files. Use `_provenancelib.assess_context_provenance` to inspect
current evidence. An existing `first_input_pending` result names the bounded refresh;
otherwise select the documents affected by the new source. Preserve interview
history and the initialized marker while reconciling intended and implemented facts.
