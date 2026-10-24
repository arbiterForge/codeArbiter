# Context and decomposition — HTML implementation handoff

**Status:** planning documents only; implementation and migration have not begun.
The [native HTML specification](../../../.codearbiter/specs/context-decomposition.html)
and [linked HTML implementation plan](../../../.codearbiter/plans/context-decomposition.html)
are the canonical working documents. They use the existing codeArbiter renderer
and embedded typed models, not an HTML restyling of Markdown.

## For the implementing agent

Read the specification first (`SPEC-CONTEXT-DECOMPOSITION`), then the plan
(`PLAN-CONTEXT-DECOMPOSITION`). Use the installed, manifest-pinned
`ca-artifact` bridge for `identity`, `outline`, and exact symbol `read`.
A fresh checkout without a local artifact store may first need the existing
native `init-store` operation. It only initializes local store metadata/locks;
it does **not** approve, validate or complete any work. Do not commit that
local operational metadata with these planning files.
Start with `AC-001` and `T-001`; continue via task dependencies.
Do not hand-edit the generated HTML or invent verified outcomes.

Supporting evidence: [83-path owner and consumer inventory](modification-map.json)
and [native document-validation record](validation.json). The specification
and the plan passed structural and readiness validation as **draft planning
artifacts**; the two JSON files are records, not validated artifacts. That is
not implementation, release, installed-host, or migration proof.
Revalidated using the native binary built from this PR base
(`main@3d806a1575b4c21d787d7cbbc8dcd2b36c186395`, Windows/amd64,
SHA-256 `94c2db08108ec7aeecbe495210e5f7567e94676c803551a085ad9c0f8711e542`):
`identity`, structural/ready `validate`, exact reads `AC-001`/`T-003`, and
advisory `eligible` all passed in a **separate scratch repository**.
`eligible` reported `T-001`; evidence remained unassessed. No conversion
implementation, model-backed host, or package was verified.

**Suggested first vertical slice:** one tech-stack command record, the native
HTML source, one bounded task-context read and its TDD consumer, including
one relevant security constraint and one unrelated unresolved question.

## Operating boundaries

- Context and decomposition are **information**, not authorization. No
  context-admission verdict, proof-of-reading ticket, context approval code,
  mandatory reviewer fleet, policy mirror, or new control-plane service.
- Preserve the minimal activation/configuration `CONTEXT.md` and the existing
  operative path-scope declarations in `security-controls.md`. Their
  descriptive narrative belongs to HTML, not another editable policy source.
- Source/CAS/transaction validity, actual user stops, real host permissions,
  and Git/release authorization remain independent. Incomplete drafts can
  be saved; a missing unrelated fact is not a task-wide blocker.
- Reuse the existing task, question and ADR owners. A promoted candidate
  work item must not create a duplicate if its original item was finished
  or archived. Migrate deliberately and preserve later writes on retry.
- Keep generated Claude, Codex and Pi projections consistent. Do not
  infer distribution or installed-model behavior from source or document checks.

## Source currency and revalidation

Reviewed planning baseline:
`arbiterForge/codeArbiter@0badb588dc1179b06e13db1ca5322590962b586a`.
This PR was branched from `main@3d806a1575b4c21d787d7cbbc8dcd2b36c186395`.
The inventory is a **commit-bound map**, not proof that all 83 paths remain
unchanged or that no new readers have been introduced.

Since that review baseline, 7 of its 83 listed paths changed:
- `core/artifacts/internal/operations/protocol.go`
- `core/pysrc/_artifactauthoritylib.py`
- `core/pysrc/_bashguardlib.py`
- `core/pysrc/_replylib.py`
- `core/pysrc/hostapi.py`
- `site/scripts/execution-maps/atlas-data/assistive-update.json`
- `tools/build-artifacts.py`

Reinspect those paths and scan for any newly introduced consumers before
implementation. The earlier map also recorded PR #1016 while it was open;
that hook cleanup is now on `main` (merge commit `ddb07a3a`). Reuse the
current implementation and its restrictions rather than reopening the
approval-capture design.

The rendered pair, map and validation report retain their **original bytes**.
This README explains the later main-branch delta without silently rewriting
the reviewed artifacts.
