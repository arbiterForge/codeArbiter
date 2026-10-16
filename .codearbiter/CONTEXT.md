---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

codeArbiter is a shared orchestration framework with three governance host
adapters and one infrastructure sibling. It helps an agent maintain a working
agreement, coordinate tasks, retain honest progress and evidence, and follow
the repository's independent engineering and publication controls.

The project is maintained for a solo developer. Its stage remains 2. Version
numbers belong to the package manifests, and current test/release evidence
belongs to the relevant PR or release record; neither is inferred from this file.

## Product direction

ADR-0043 makes the state engine assistive. Already-authorized work proceeds
without a second artifact permission exchange. Task selection, progress,
in-scope plan maintenance, and resume do not require artifact approval codes,
prerequisite certification replies, or context-delivery tickets.

Observable prerequisites are checked through ordinary authorized tools.
Only the affected work waits for a real dependency, explicit stop, or
consequential unresolved decision. The agent may adjust methods while keeping
the agreed outcome and recording the reason. Use SMARTS for difficult trade-offs
when useful; a score is not permission to expand scope.

Implementation progress and evidence assessment are different. Recording
implementation complete does not claim tests passed, review occurred, or a
release shipped. New check results and presentation changes do not automatically
restart review. Refresh conclusions when relevant inputs, requirements, findings,
or results change; disclose incomplete scope.

Retain actual host permissions, explicit user denials/stops, filesystem and
sandbox protections, repository controls, and authorized publication boundaries.
Preserve stable IDs, bounded reads, safe rendering, revision checks, transactional
writes/recovery, and history. ADR-0043 supersedes only ADR-0037's duplicate
artifact authorization interpretation; it does not discard the shared file-backed
engine or independent safety controls.

## Components and ownership

- **Shared kernel:** the canonical governance kernel lives in shared source.
  `core/pysrc/` owns the stdlib Python hook and bridge code;
  `core/surface/` owns shared instructions; `core/artifacts/` owns the native
  Go artifact engine. `core/hosts.json` defines the three host projections.
  The kernel is an internal source boundary, not a separately published runtime
  package (ADR-0031).
- **Claude Code adapter:** `plugins/ca/` contains the generated governance payload,
  host manifest, and TypeScript farm dispatcher.
- **Codex adapter:** `plugins/ca-codex/` contains generated entry skills, routines,
  hooks, and resource charters for host-provided dispatch. Resource charters
  are not native Codex plugin-agent registrations.
- **Pi adapter:** `plugins/ca-pi/` adds a thin TypeScript extension and isolated-child
  adapter. Its nested manifest owns the version; the generated root
  `package.json` is the Git/npm install projection.
- **Infrastructure:** `plugins/ca-sandbox/` provides ephemeral Docker-based
  exploration of untrusted repositories. It is separate from governance.
  Docker is required for the container path; installed nixpacks is the intended
  builder where available, with the documented generated-Dockerfile fallback.
- **Documentation:** `site/` builds the static product site and consumes
  generated resources plus curated prose and the separately owned Academy
  source. Editing this repository does not authorize editing that other repo.

Shared Python and instruction payloads are generated into the host trees.
Edit canonical sources, then regenerate with the owning tools; do not
independently maintain rendered copies. See `code-map.md` for concern owners
and `tech-stack.md` for build and verification commands.

## Project state and document identity

One root-level `.codearbiter/` store serves the governance hosts and survives
plugin removal. The `arbiter: enabled` frontmatter is the activation flag.

New full-lane feature/sprint pairs use typed HTML when the installation has its
supported native payload. The embedded typed model is authoritative and the
visible HTML is its deterministic view. Existing Markdown work stays on its
selected legacy path until an explicit supported migration; small work remains
inline. Neither a capability failure nor a format change authorizes a raw rewrite.

The five project-context documents are Markdown; their safe writer and provenance
format are separate from spec/plan HTML. Task boards, questions, audit logs,
release targets, and ADR history retain their existing owners. Reading state
does not establish that it is fresh, verified, accepted, or released.

## Domain vocabulary

- **Mode:** the session-scoped posture in `_modelib.MODES`: `arbiter`,
  `dangerous`, or `ops`. `arbiter` provides normal routing; `dangerous`
  suspends orchestration for local exploration; `ops` narrows the posture
  toward operating a running system. Changing persona does not disable hooks
  or host permissions. A new session restores the default.
- **Skill:** a routed orchestration procedure. **Agent:** a dispatched author
  or reviewer. **Stage:** project maturity. **Gate:** a phase exit condition.
  **Severity:** a finding classification, separate from its gate action.
- **Artifact revision/model hash:** write-conflict identity. **Normative hash:**
  definition identity. **Reported check:** a retained command result or note,
  not automatically host-attested or named-test proof.

## Boundaries

This is not an enterprise compliance suite, a database/daemon platform, or a
general permission broker. The three governance hosts and infrastructure sibling
are the explicit decisions in ADR-0007, ADR-0011, and ADR-0013; they are not
precedent for arbitrary co-location or additional hosts. Preserve accepted ADRs
and their lifecycle history. See `security-controls.md` for current controls
and accepted residual risks.
