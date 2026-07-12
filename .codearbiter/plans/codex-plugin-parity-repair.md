# Codex Plugin Parity Design

**Relationship to the campaign plan:** This repair design refines the packaging, CI, and live-verification obligations in `.codearbiter/plans/codex-support.md`. It does not replace that plan or alter its locked architecture and parity decisions. Where this document is more specific, it supplies the acceptance detail for the remaining repair and beta-promotion work.

## Goal

Make `ca-codex` a valid, installable Codex plugin with behavioral parity to the Claude Code `ca` plugin. A repository may be used from Claude Code, Codex, or both, while both hosts share the same lowercase `.codearbiter/` project context, governance state, and enforcement records.

The work also makes the existing shared-source generation model an explicit architectural contract enforced by CI. Claude and Codex are the first two supported host distributions; future harnesses should be added through a new adapter and generation target rather than by copying an existing plugin.

## Current State

The branch already contains the main pieces of the intended architecture:

- shared surface sources under `core/surface/`;
- deterministic Python vendoring through `tools/sync-core.py` and surface generation through `tools/build-surface.py`;
- host abstraction in the shared Python hook implementation;
- generated Claude and Codex distributions under `plugins/ca/` and `plugins/ca-codex/`;
- adapter, cold-install, reference-graph, and generated-drift checks in CI.

The Codex implementation passes its existing runtime-oriented checks: the adapter suite reports 272 assertions with no failures, the cold-install matrix passes, generated surfaces are synchronized, and the Codex reference graph is intact.

It is not yet a valid Codex plugin package against the pinned repair baseline, Codex CLI 0.144.1. The canonical validator available with that environment reports:

- an unsupported top-level `displayName` in `.codex-plugin/plugin.json`;
- missing required Codex `interface` metadata;
- five generated skills with invalid YAML frontmatter;
- a repository marketplace entry that uses an older source shape and omits required policy and category metadata.

These packaging failures can prevent installation or discovery even though the underlying adapter tests pass.

The repair PR must attach the complete pre-fix validator output and the validator identity or version used to produce it. That evidence is the checkable baseline for the manifest and frontmatter changes; the PR may not rely only on this summary.

## Architecture

The plugin system has three layers.

### Shared source

Host-neutral governance behavior lives in shared source. This includes routines, command semantics, enforcement rules, state formats, and the meaning of files under `.codearbiter/`.

Shared source must not assume Claude- or Codex-specific tool names, manifest locations, hook payloads, cache paths, or installation commands. Where behavior genuinely depends on the host, shared code calls a host abstraction with an explicit contract.

### Host adapters

Each supported harness owns a small adapter describing only its host-specific behavior:

- plugin manifest and marketplace schema;
- hook discovery and hook payload translation;
- plugin-root and project-root discovery;
- tool vocabulary and command invocation syntax;
- supported capabilities and documented degradation paths;
- installation, caching, and update behavior.

Claude Code remains represented by `plugins/ca/`; Codex remains represented by `plugins/ca-codex/`. They version and release independently because their packaging and host capabilities can change independently.

### Generated distributions

`tools/sync-core.py` deterministically vendors the shared Python core and `tools/build-surface.py` combines shared markdown source with each host adapter. Together they produce the checked-in host distributions. Generated files are not edited directly. Fixes to generated Python, skill content, or frontmatter are made in shared source or the relevant adapter template, then regenerated.

The generated directories remain checked in so releases are inspectable, host-native packaging can refer to repository paths, and CI can prove that committed output matches its source.

## Shared Project State

Both plugins resolve the project root independently using their host adapter and then read and write the same `<project-root>/.codearbiter/` directory. The directory name and on-disk formats are host-neutral and remain lowercase.

Initialization must be idempotent. Opening a repository in the second host must reuse existing context rather than create a parallel store or overwrite established configuration.

Append-only records must remain append-only from both hosts. Writes that can be triggered by either host must use the same atomicity and locking conventions where concurrent access is possible. Host identity may be recorded as provenance, but it must not partition the shared state.

Enforcement decisions must remain semantically equivalent across hosts. Differences caused by unavailable host capabilities must be explicit, documented, and tested rather than silently treated as parity.

## Codex Package Repair

The Codex distribution will retain `.codex-plugin/plugin.json` and the normalized name `ca-codex`. Its manifest will conform to the schema validated for Codex CLI 0.144.1:

- remove unsupported top-level presentation fields;
- provide all required `interface` fields with valid types;
- represent starter prompts as an array of short strings;
- reference only companion components and assets that actually exist;
- preserve strict semantic versioning and existing project metadata.

The repository marketplace at `.agents/plugins/marketplace.json` will remain a repository/team marketplace. Its `ca-codex` entry will use the local-source object, installation and authentication policies, and category required by the pinned Codex 0.144.1 marketplace schema. Its source path remains `./plugins/ca-codex`, relative to the marketplace root.

The repair PR must identify the pinned schema or validator rule that requires each marketplace field and attach the pre-fix validation or CLI rejection output. Marketplace fields are not added from an inferred resemblance to another host's catalog.

The five invalid skill frontmatters will be corrected in their generator inputs. Descriptions and argument hints containing YAML-significant punctuation will be encoded as valid YAML without changing the user-facing command meaning.

## Installation and Update Behavior

The supported development installation path is:

1. configure this repository as a local Codex marketplace;
2. install `ca-codex` from the configured marketplace name;
3. start a new Codex thread so skills and hooks are loaded from the installed snapshot.

Local iteration must account for Codex's plugin cache. Package changes use the supported cache-buster/reinstall flow instead of hand-editing user marketplace or Codex configuration files.

Repository documentation will distinguish Claude installation commands from Codex commands and will not imply that Claude's `/plugin` commands work in Codex.

## CI Contract

CI is the enforcement boundary for the generated multi-host architecture.

### Deterministic generation

Run both generators in check mode and fail if committed host distributions differ from regenerated output. `tools/sync-core.py --check` enforces byte identity for the `core/pysrc/` vendored copies; `tools/build-surface.py --check` enforces deterministic host-specific markdown surfaces. Generator tests cover normalization and host-specific rendering.

### Native package validation

Validate each host distribution using its native package rules. Codex validation is pinned to Codex CLI 0.144.1 for this repair and includes manifest schema, marketplace shape, referenced component existence, strict SemVer, and YAML parsing for every shipped skill. The CI job prints and records `codex --version` plus the validator identity before validation so a later Codex release cannot silently move the acceptance bar.

The plugin may continue to declare an older supported minimum only where that minimum is independently tested. The repair's schema and live-fire claims are specifically claims about 0.144.1; support for later releases requires the ADR-0011 re-verification process.

### Parity matrix

Run shared behavioral fixtures through both host adapters and compare normalized outcomes. The matrix covers at least initialization, context discovery, enforcement enablement, blocking decisions, audit/provenance writes, and update/version discovery.

### Dual-host fixture

Exercise Claude and Codex adapters sequentially against one temporary checkout. For the append-only audit logs only, also exercise controlled concurrent appends where the implementation uses honest append semantics. Assert that:

- only one `.codearbiter/` store exists;
- both hosts observe the same context and enablement state;
- initialization is idempotent;
- append-only audit-log entries are not truncated or silently overwritten;
- host provenance does not alter governance semantics;
- duplicate hook installation does not cause duplicate enforcement for a single host event.

This fixture does not assert race-free behavior for read-modify-write state such as `open-tasks.md`, nor for the repo-global dev marker. ADR-0012 records those as pre-existing same-host concurrency debt and explicitly de-scopes locking or compare-and-swap from the Codex campaign. Because ADR-0012 is currently proposed, it must be ratified before this design is used as the implementation bar; until ratification, its concurrency scope is not a settled project decision.

### Leakage and reference checks

Fail when generated Codex content contains unsupported Claude-only paths, variables, commands, or tool assumptions outside an explicit compatibility explanation. Apply the corresponding check in the other direction. Continue validating the internal reference graph of each distribution.

### Release integrity

When a generated distribution changes, require the appropriate independent plugin version update according to the repository's release policy. Packaging tests run before release artifacts or tags are created.

## Error Handling and Degraded Capabilities

Package-schema errors are hard CI failures. Missing required interpreters or denied hook trust must produce actionable diagnostics rather than silently disabling enforcement.

When one host cannot implement a capability available in the other, the adapter must declare the degradation in host notes, expose it through diagnostics where relevant, and include it in the parity ledger. A degraded capability is not presented as full parity until a real host test proves it.

Shared-state corruption, conflicting project-root resolution, or non-idempotent initialization are release blockers because they endanger repositories used by both hosts.

## Verification

Completion requires fresh evidence from:

- canonical Codex plugin validation with the pinned Codex CLI 0.144.1 and validator identity recorded;
- validation of every generated skill's YAML frontmatter;
- marketplace schema validation;
- `tools/sync-core.py --check` and `tools/build-surface.py --check`;
- existing Codex adapter, cold-install, hook, and reference suites;
- dual-host shared-state tests;
- an actual local marketplace add and `ca-codex` install using the available Codex CLI;
- inspection of the installed snapshot to confirm skills and hooks were packaged;
- a clean live Codex session demonstrating that Codex discovers the installed skills and initializes or reads the shared `.codearbiter/` context;
- live SessionStart stdout persona injection into Codex context;
- the Codex hook trust-review and approval flow, including confirmation that doctor detects the untrusted state and recognizes the approved state;
- a live blocking hook returning exit 2 with non-empty stderr, with the block and diagnostic surfaced to the Codex model.

The last three checks are ADR-0011's beta-promotion gate. When all three pass on the pinned Codex baseline and the remaining acceptance criteria are green, the same repair changes the `ca-codex` Feature Forge status and user-facing documentation from beta/preview to the repository's promoted status. If any live check fails, `ca-codex` remains beta and the result is recorded in `docs/parity.md`; successful installation alone does not promote it.

The live installation test must not alter a user's unrelated marketplace configuration. Test setup and cleanup are limited to the codeArbiter marketplace and plugin entries created for this verification.

## Scope Boundaries

This work does not rewrite the governance model, add a speculative third harness, merge Claude and Codex into one package, or claim parity for capabilities that the current Codex host cannot support.

It does document and enforce the adapter boundary needed for future harnesses. A future host becomes a separate project: implement the adapter contract, add a deterministic generation target, add native package validation, and extend the parity matrix.

## Acceptance Criteria

The design is complete when:

1. `plugins/ca-codex` passes the canonical validator used with the pinned Codex CLI 0.144.1 baseline, with both tool identities recorded in CI output.
2. The repository marketplace is accepted by Codex CLI 0.144.1 and exposes `ca-codex`.
3. `ca-codex` installs from that marketplace; its skills and hooks are present in the installed snapshot; and a live 0.144.1 session proves stdout persona injection, trust review/approval with doctor detection, and exit-2 plus non-empty-stderr blocking surfaced to the model.
4. All generated skill frontmatters parse as valid YAML.
5. `tools/sync-core.py --check` and `tools/build-surface.py --check` both pass and regeneration produces no uncommitted diff.
6. Existing adapter, cold-install, reference, and hook suites remain green.
7. After ADR-0012 is ratified, CI proves both adapters can share one `.codearbiter/` store without divergent context or duplicated enforcement, and proves concurrent append semantics only for append-only audit logs; known RMW and dev-marker races remain explicitly out of scope.
8. Shared sources and host adapters are documented clearly enough that another harness can be added without copying an existing generated distribution.
9. The repair PR attaches the pre-fix validator evidence and identifies the pinned manifest and marketplace validation rules used for the repair.
10. Any changed `plugins/ca-codex/` payload carries the required independent `ca-codex` SemVer bump and changelog entry under the repository release policy.
11. Passing the three ADR-0011 live-fire checks removes the beta/Feature Forge preview label in the same repair; otherwise the label remains and the failed evidence is ledgered.
