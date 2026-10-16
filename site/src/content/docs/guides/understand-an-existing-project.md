---
title: Understand an Existing Project
description: "Initialize codeArbiter from existing source, review the source-backed context, and resolve gaps without inventing a greenfield architecture."
journey:
  level: Foundation
  time: "Repository-dependent guided extraction"
  outcome: "Source-backed project context with uncertainty and verification commands made explicit."
  prerequisites:
    - A supported adapter installed and trusted
    - An existing source repository
    - Git identity configured
  proof: "Context claims resolve to source evidence, gaps are explicit, and a fresh session passes the appropriate doctor probe."
---

Brownfield initialization explains an existing codebase. It does not redesign it. This route
**does not create the greenfield three-document set** and does not invent planning documents
merely so architectural reconciliation has something to read.

## Establish the repository boundary

Open the intended repository in your coding host. In a native terminal, inspect
`git rev-parse --show-toplevel` and `git status --short`. Confirm the host is rooted at that same
checkout. Keep unrelated changes intact. Tell codeArbiter about generated directories, excluded
material and any known mismatch between the intended architecture and current implementation.
Never provide a real `.env` file as an example; use declared configuration keys without secrets.

Describe the initialization goal or use an explicit entry:

| Host | Brownfield initialization |
|---|---|
| Claude Code | `/ca:init --brownfield` |
| Codex | `$ca-init --brownfield` |
| Pi | `/ca-init --brownfield` |

`create-context` remains the compatibility entry for this strategy. If context is already
initialized, inspect it with status and the appropriate drift procedure rather than removing the
initialization marker to force a fresh extraction.

## Inspect the source in bounded scope

Initial population or explicit full refresh accounts for six logical categories: stack,
infrastructure, architecture, security posture, testing and data model. Use direct bounded
inspection or optional scoped agents; six categories do not require six children or a special
qualified profile. Scoped refresh covers the affected categories and retains prior coverage
separately. Actual host permissions and excluded source boundaries still apply.

Record citations, source identities, inspected scope and unknowns. Agent labels, report shape
and matching digests do not prove trusted containment or semantic correctness. Use independent
review where it helps resolve consequential claims, and state what was actually checked.

Review the returned boundaries. “No migration tool found” is a useful finding; silently assuming
one is not. Security findings should identify relevant sites without exposing secret values.

## Review what is written

| Output | What to check |
|---|---|
| `CONTEXT.md` | The actual project, its users, scope and exclusions, rather than a generic description |
| `tech-stack.md` | Runtimes, dependency manager and exact build/test/lint commands supported by source |
| `coding-standards.md` | Observed conventions distinguished from proposed improvements |
| `security-controls.md` | Existing trust boundaries and project-owned controls, without invented compliance claims |
| `code-map.md` and provenance records | Coarse concerns point to real paths; source-backed claims can later become stale |
| `open-questions.md` | Material user-owned questions and actual answers or deferrals; other unknowns remain visible |
| `release-targets.md`, when supported by evidence | The real manifests, changelog, tag convention and payload, not another project's release table |

These paths are under `.codearbiter/`. Scaffolding also provides the task and audit-state files.
Release-target detection may need your decision; ambiguity must not become a guessed declaration.

A useful correction is: “The deployment workflow runs the API tests from `service/`, not the
repository root. Confirm the command from source, fix the context, and show the affected claims.”
Do not approve an inferred architectural pattern as an observed fact without checking its evidence.

## Resolve the gaps

Observations need source evidence. Label indirect signals as inferences and inspect conflicting
facts where possible. Ask `[CONFIRM-NN]` questions only for material unresolved user decisions;
reuse existing answers and authorization. Answer, challenge or explicitly defer such a question. A deferred question remains visible and can
still stop later work that depends on its answer.

The safe writer previews each selected document/provenance pair and applies it only while the
source and target identities still match. Existing authorization is enough for those writes;
there is no extra approval code for each document. Preserve human content outside selected spans.
An initialized refresh retains its marker and never repeats finalization.

On completion, review the populated tree and the `<!--INITIALIZED-->` body marker in `CONTEXT.md`.
Activation, initialization and a successful live enforcement probe are different checks.
Use [the first-repository walkthrough](/getting-started/quickstart/) to prove the last one.

## Operate without rebuilding context every session

Use [Return to a project](/guides/return-to-a-project/) for ordinary work.
When a source path or configuration changes, inspect provenance with status drift and choose the
appropriate re-scout or re-baseline procedure. Do not erase the context to silence a warning.

The [context-creation reference](/reference/skills/context-creation/) owns the exact extraction
contract. Academy [U04](/academy/u04-initialize-projects/) practices the distinct greenfield and
brownfield routes after its earlier lessons; this guide does not change those prerequisites.

## Follow the complete initialization route

Open the [brownfield execution map](/guides/opt-in-a-repo/#init-brownfield-inspect-code) to follow the command, owning skill and applicable roles from entry to initialized state. The other initialization route is an alternative, not a next phase.
