# Code map — codeArbiter

Concern-level source orientation. Edit canonical sources and regenerate host
copies. Read versions and command membership from their owning manifests and
catalogs; source inspection is not live-host or publication qualification.

## Shared source and generation

- `core/pysrc/` — Canonical stdlib Python hook entry points, host seams, integrity guards, state helpers, and native artifact bridge.
- `core/surface/` — Canonical commands, routines, agents, includes, and persona instructions; its README defines projection conventions.
- `core/hosts.json` — Host capabilities, command forms, tool classes, permission policies, and surface projections for Claude, Codex, and Pi.
- `tools/host_descriptors.py` — Strict loader for immutable host descriptors.
- `tools/sync-core.py` — Byte-identical shared Python projection into governance plugin hooks.
- `tools/build-surface.py` — Host-specific instruction projection and generated catalogs.
- `tools/build-host-packages.py` — Generated root Pi manifest and verified native-payload package cohorts.

## Native artifact engine

- `core/artifacts/cmd/ca-artifact/` — Native CLI accepting bounded JSON requests and returning protocol envelopes.
- `core/artifacts/internal/operations/` — Closed reads and mutations, advisory eligibility, task context, reported checks, progress, migration, context-document operations, and selected native work lifecycle and provider-effect operations.
- `core/artifacts/internal/model/` — Validated artifact records, stable IDs, canonical identities, scoped definitions, and distinct progress/evidence fields.
- `core/artifacts/schemas/` — Versioned JSON contracts for typed artifacts and operations.
- `core/artifacts/internal/kind/` — Closed representation registry for spec/plan, knowledge/decomposition, and work HTML, plus project-context Markdown.
- `core/artifacts/internal/read/` — Exact/contextual/batch reads, bounded pages, and explicit incomplete scope.
- `core/artifacts/internal/symbol/` — Stable symbol references and resolution.
- `core/artifacts/internal/evidence/` — Evidence assessment and retained review/verification history; ordinary execution is not receipt-gated.
- `core/artifacts/internal/render/` — Deterministic offline HTML for artifacts and work with stable anchors, safe escaping, and separate progress/evidence labels.
- `core/artifacts/internal/store/` — Platform filesystem boundaries, revision checks, locks, journals, before-images, replay, and recovery.
- `core/artifacts/internal/contextdocument/` — Five-document Markdown ownership, bounded typed content, preview/apply, provenance contracts, and Markdown-to-HTML knowledge conversion.
- `tools/build-artifacts.py` — Pinned-toolchain native payload build and qualification metadata.
- `tools/generate-artifact-types.py` — Generated schema and typed-view consistency.
- `tools/test-artifact-mixed-schema.py` — Disposable old/current-client compatibility, retained stops, replay, complete-store restore, and forward export.

## Python runtime and compatibility

- `core/pysrc/_artifactlib.py` — Installation-pinned native bridge, request bounds, payload validation, and exact-format routing; no runtime PATH lookup or download.
- `core/pysrc/_modelib.py` — Per-session arbiter, dangerous, and ops mode state; dangerous suspends persona orchestration, not enforcement.
- `core/pysrc/_reconciliationlib.py` — Legacy reconciliation history and captured-reply recovery preserving original observations, operation IDs, and revision bindings.
- `core/pysrc/_contextsnapshotlib.py` — Bounded repository-context acquisition and source identity.
- `core/pysrc/_provenancelib.py` — Document provenance, source drift, and bounded code-map validation.
- `core/pysrc/_taskboardlib.py` — Legacy board schema and counters; taskwrite.py owns its mutations and archival.
- `core/pysrc/_worklib.py`, `work.py`, and `_workgithub.py` — Selected legacy-board adapter, native work CLI, and fixed GitHub Issues transport; stable work IDs select lifecycle and context operations.
- `core/pysrc/knowledge.py` — Knowledge and decomposition records CLI over the native engine; `_knowledgelib.py` resolves format and paths without it.
- `core/pysrc/_releaselib.py` — Declared release targets, preflight, publication helpers, and recovery diagnostics.

Hook coverage is host-specific. Loaded instructions and named tools alone do not
prove enforcement; the cooperative-agent and MCP boundaries remain documented
in security-controls.md. Compatibility producers retain historical evidence
without restoring an extra permission layer for already-authorized work.

## Host and infrastructure adapters

- `plugins/ca/` — Claude manifest, generated governance resources, hooks, and TypeScript farm dispatcher with built farm.js.
- `plugins/ca-codex/` — Codex manifest, generated entry skills/routines/hooks, and resource charters; no native plugin-agent registration.
- `plugins/ca-pi/tools/src/` — Trusted-runtime extension, project-trust checks, Python bridge, tool wrapping, isolated child runner, and parent inference broker.
- `plugins/ca-pi/extensions/` — Built parent and child extensions shipped to Pi.
- `plugins/ca-pi/helpers/` — Packaged native helpers including the Windows supervisor.
- `plugins/ca-sandbox/tools/` — Docker lifecycle, mount/network isolation, installed-nixpacks detection, and generated-Dockerfile fallback.

## Documentation and Academy

- `site/src/curated/` — Maintained Astro/Starlight product prose.
- `site/scripts/` — Site and diagram generation, Academy consumption, link/applicability auditing, and fixture capture.
- `site/test/` — Site unit, generated-content, browser, and offline artifact-view checks.
- `.gitmodules` — Separately owned arbiter-academy source declaration; the gitlink selects its revision, while local population is checkout state.

## Project records

- `.codearbiter/` — Five context documents, provenance, specs/plans, native work, open decisions, protected release declarations, legacy task boards, and audit records.
- `.codearbiter/work/` and `.codearbiter/work/project.json` — Portable native work items, project identity, and finite provider binding in repositories that select the native owner.
- `.codearbiter/open-tasks.md` — Legacy work owner when present; helper-only mutable board with done-tasks.md as append-only archived history.
- `.codearbiter/decisions/` — Accepted ADR bodies and append-only lifecycle/decision history, including ADR-0043's assistive contract.
- `.codearbiter/release-targets.md` — Four protected executable target declarations with pre-tag/build/generation ownership.

## Tests, CI, and publication

- `plugins/ca/hooks/tests/` — Shared hook unit tests; tests here are maintained source, not generated hook copies.
- `.github/scripts/` — Python contracts, lifecycle, packaging, provenance, platform tests, and hosted check helpers.
- `.github/workflows/ci.yml` — Impact routing, native/platform matrices, package/cold-install checks, coverage, and merge readiness.
- `.github/workflows/release.yml` — Qualified cohort publication and called workflow ownership; publication is separate from ordinary progress.
- `.github/workflows/docs.yml` — Site validation and deployment.
- `.github/RELEASE-PROVENANCE.md` — Original-publication evidence and immutable-tag obligations, including legacy evidence grades.

Go tests live beside their packages. Vitest projects live in the three tool
packages and site; manifests own runnable commands. Local source checks,
hosted candidate qualification, published packages, and installed-host behavior
are separate claims.
