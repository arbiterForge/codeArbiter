# Cross-host identity and packaging migration implementation plan

> Planning artifact only. This document does not authorize implementation, release, or changes to existing historical records.

**Date:** 2026-08-21

**Planning baseline:** `origin/main` at `cacdb7899c83e8d8ff2a49f3e0e918e56f3a0d1a` (refreshed 2026-08-21 after PR #700)

**Primary defect:** [Issue #699 — Codex packaging: `ca-add-dep` routes to missing `dependency-reviewer` agent](https://github.com/arbiterForge/codeArbiter/issues/699)

**Scope:** `ca` (Claude Code), `ca-codex` (Codex desktop/CLI), and `ca-pi` (Pi)

**Non-goals:** weakening H-01/H-09/H-10/H-14 or any other enforcement rule; changing host-native command spellings; adding Academy-only behavior; rewriting released changelogs, prior plans, audit evidence, or release records.

## Executive diagnosis

This is one architectural inconsistency with two visible symptoms, not an isolated missing file.

1. The canonical surface uses `CLAUDE_PLUGIN_ROOT` as if it were a product-wide runtime contract. It is not. Claude Code natively interpolates `${CLAUDE_PLUGIN_ROOT}`; Codex injects `PLUGIN_ROOT` into plugin hook processes and currently provides `CLAUDE_PLUGIN_ROOT` only as a compatibility alias; Pi does not expose a plugin-root environment contract and derives package location from the loaded extension or hook file. A global textual rename to `${ARBITER_PLUGIN_ROOT}` would therefore break executable paths on at least Claude and would not make ordinary Codex skill tool calls or Pi resolve anything.
2. The Codex package intentionally omits `plugins/ca-codex/agents/`, while refreshed `origin/main` contains 20 direct `${CLAUDE_PLUGIN_ROOT}/agents/<name>.md` occurrences on 19 matching lines across 11 generated files and generic routing that can name every one of the 18 canonical charters. Existing tests codify the omission or allow unresolved agent paths. The installed `ca-codex` 0.7.2 cache reproduced the failure at investigation start; its historical snapshot contained 26 occurrences on 25 lines across 13 files and later acquired a one-file local repair (`dependency-reviewer.md`). That mutation is evidence, not source or a package-level fix. A later read-only check of the currently installed 0.7.3 package independently found no `agents/` directory and the same 20 literal references naming 10 absent charters as current source.

The recommended fix is to introduce a host-neutral root-resolution abstraction in canonical source, render host-native syntax only at host boundaries, continue accepting the old Codex compatibility alias, and ship all 18 canonical agent charters in `ca-codex` as generated resource files. Codex should read a charter and pass it to a host-provided agent thread; the Markdown file must not be represented as a natively registered Codex custom agent.

## Evidence baseline

- Initial inspection used `origin/main` at `b52be330a72b850a96595c993fb02949d9e1dc42`. The current refreshed baseline is `cacdb7899c83e8d8ff2a49f3e0e918e56f3a0d1a`; the intervening PR #698 hook/version work and PR #700 Academy lesson-control work do not alter plugin-root vocabulary or Codex charter packaging.
- The investigation fetched `origin/main` before inspection. The local working branch and the installed 0.7.2 cache were used only as reproducibility evidence, not as the source baseline.
- Installed Codex evidence at `C:\Users\brenn\.codex\plugins\cache\codearbiter\ca-codex\0.7.2`:
  - historical initial 0.7.2 snapshot: package directories `.codex-plugin`, `hooks`, `includes`, `routines`, `skills`; `agents/` absent; 26 direct `${CLAUDE_PLUGIN_ROOT}/agents/<name>.md` occurrences on 25 matching lines across 13 files;
  - final read: a locally created `agents/dependency-reviewer.md` exists, but `agents/INDEX.md` and 17 canonical charters remain absent;
  - conclusion: the missing-artifact defect was reproduced, and a cache-local one-file repair neither represents `origin/main` nor closes the shipped route graph.
- Current installed-package corroboration at `C:\Users\brenn\.codex\plugins\cache\codearbiter\ca-codex\0.7.3`, inspected read-only on 2026-08-21: `agents/` and `agents/dependency-reviewer.md` are absent; 20 literal `${CLAUDE_PLUGIN_ROOT}/agents/<name>.md` occurrences name 10 distinct missing charters. This cache is corroborating installed-artifact evidence only; `origin/main` remains the planning source baseline.
- `origin/main` inventory:
  - `CLAUDE_PLUGIN_ROOT`: 664 string occurrences on 628 matching lines in 219 files;
  - `ARBITER_PLUGIN_ROOT`: zero occurrences;
  - canonical source/templates: 4 matching lines in 3 files;
  - canonical Python runtime/hook code: 13 matching lines in 8 files;
  - generated plugin payloads: 494 matching lines in 175 files;
  - tests, fixtures, and CI: 57 matching lines in 11 files;
  - active docs/site content: 8 matching lines in 5 files;
  - historical/governance records: 20 matching lines in 9 files;
  - sandbox and build tooling: 32 matching lines in 8 files.
- Host contracts were checked against current primary documentation:
  - [Claude Code plugin reference](https://code.claude.com/docs/en/plugins-reference): `${CLAUDE_PLUGIN_ROOT}` is a host-native substitution and subprocess environment variable; plugin `agents/` are first-class components.
  - [Codex hooks](https://learn.chatgpt.com/codex/hooks): plugin hook commands receive `PLUGIN_ROOT`/`PLUGIN_DATA`; `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA` are compatibility aliases.
  - [Build Codex plugins](https://learn.chatgpt.com/codex/build-plugins): plugin components are skills, hooks, and MCP configuration; plugin Markdown agents are not a documented component. For development, the supported path is a local marketplace, followed by refreshing ChatGPT or Codex, installing from that source, and testing in a new conversation.
  - [Codex subagents](https://learn.chatgpt.com/codex/agent-configuration/subagents): native custom agents are TOML files in user or project `.codex/agents/`, not plugin `agents/*.md` files.
  - [Codex environment variables](https://learn.chatgpt.com/docs/config-file/environment-variables#core-locations): `CODEX_HOME` is the documented root for the CLI, IDE extension, app-server, and installers; the directory must already exist. The table does not claim that the ChatGPT desktop shell itself can be repointed independently.
  - [ChatGPT desktop app for Windows](https://learn.chatgpt.com/docs/windows/windows-app): the native desktop app uses `%USERPROFILE%\.codex`; the current Store product ID is `9PLM9XGG6VKS`. The page documents Windows-native/WSL agent selection but no independent desktop-profile or desktop `CODEX_HOME` switch.
  - [OpenAI authentication](https://learn.chatgpt.com/docs/auth): the ChatGPT desktop app supports ChatGPT browser-flow sign-in and API-key sign-in. API-key use is usage-billed and can have reduced ChatGPT workspace/cloud feature availability, although local Codex and supported plugin workflows are available. Codex access tokens are documented for trusted non-interactive local workflows, but the desktop UI instructions document only ChatGPT browser flow and API-key entry.
  - [OpenAI service accounts](https://learn.chatgpt.com/docs/enterprise/service-accounts): ChatGPT workspace service-account access tokens are for headless Codex automation and require a pay-as-you-go workspace; they are not a documented desktop-shell login mechanism. Do not reuse them as desktop credentials.
  - [ChatGPT desktop settings](https://learn.chatgpt.com/docs/reference/settings): the UI's “Profile” section manages account/profile details and activity insights, not an isolated execution-state profile. No documented app test-profile selector exists there. Signing the disposable Windows user into the same ChatGPT account can still change server-side task, usage, and activity state.
  - [Codex native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox): this isolates agent commands through lower-privilege sandbox users, ACL/firewall boundaries, and a private desktop. It does not create a second ChatGPT application profile or a second `%USERPROFILE%\.codex`, so it cannot satisfy the desktop-shell profile-isolation cell by itself.
  - [Microsoft MSIX deployment architecture](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/deployment-architecture) and [MSIX containerization](https://learn.microsoft.com/en-us/windows/msix/msix-containerization-overview): package staging is per-machine, while registration and runtime data are per-user. Because the inspected ChatGPT package is full trust, MSIX separation is not by itself a security boundary; the distinct Windows account/SID plus verified profile ACL denial supplies the local-state boundary.
  - [Codex app-server API overview](https://learn.chatgpt.com/docs/app-server#api-overview): the supported protocol exposes `initialize`, `skills/list`, `thread/start`, and `turn/start`; the characterization harness uses those protocol surfaces rather than inferring desktop behavior from process environment.
  - [Codex sandbox defaults](https://learn.chatgpt.com/docs/sandboxing#configure-defaults): read-only permits inspection but does not permit command execution without approval; `approval_policy = "never"` does not prompt. A current fail-closed command rejection is policy evidence, not proof that the selected resource path is invalid.
  - [Codex rules](https://learn.chatgpt.com/docs/agent-configuration/rules): prefix rules are experimental, are loaded beside active configuration layers, and can authorize outside-sandbox commands. `codex execpolicy check` validates rule matching but does not substitute for an end-to-end executor receipt.
  - [Codex 0.149.0 release](https://github.com/openai/codex/releases/tag/rust-v0.149.0): the release contains multiple exec-policy hardening changes. Without code-level attribution, the plan treats the observed behavior as version drift and does not assign it to one change.
  - [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations) and [verification guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/increase-security-rating): GitHub OIDC/Sigstore attestations bind artifact digests to repository, workflow, environment, commit, and run provenance; `gh attestation verify` can require the expected repository and signer workflow. A JSON file committed by itself is not proof that the Windows job ran.
  - [Pi coding agent repository](https://github.com/earendil-works/pi): package resources are relative to the installed package; the documented environment variables do not include a plugin-root variable or arbitrary skill-text interpolation.

### Pre-implementation characterization snapshot

- Issue #699 remains open; open PRs #694 and #682 do not supersede this work; merged PR #700 is Academy-only; refreshed `origin/main` still has no `plugins/ca-codex/agents/` tree.
- Disposable fixture v0.0.2 used three distinct nonces and two contained relative links; its deterministic SHA-256 is `8bc64e341ed9103139a8223bfd642097a296e0a666fa0c0742952bf9500d5cea`.
- Clean-home Codex CLI 0.143.0 and 0.145.0 cells passed in a read-only sandbox. Each exposed the selected skill's absolute installed path and performed exactly three direct reads for `SKILL.md`, `../../routines/nested.md`, and `../agents/probe.md`, with no search, glob, or cache discovery.
- Isolated Codex app-server 0.143.0 and 0.145.0 cells also passed against one shared disposable v0.0.4 fixture (`940a96d0b24384d0a241adb370c152b1fe885498558d53e05c543c7f9b5a6125`). Both returned the exact isolated `CODEX_HOME`, selected the namespaced skill at its absolute installed path, preserved that path in typed skill input, performed exactly the three expected direct contained reads, returned all nonces, made no server requests, used no search/glob fallback, completed with all command exits zero, and emitted zero stderr. Source-to-installed SHA-256 comparison matched for all four fixture files in both homes. The harness then terminates the long-lived app-server process, which yields process exit 1 on Windows after a successfully completed turn; the harness itself exits zero and treats only the protocol assertions as the cell verdict.
- Advisory-latest CLI 0.149.0 rejected the same exact `Get-Content` reads before emitting a command item under `--sandbox read-only` with `approval_policy = "never"`; CLI 0.145.0 passed the byte-identical fixture under the same contract. The 0.149.0 rejection remained with `disk-full-read-access`, exact rules that `codex execpolicy check` classified as `allow`, `cmd.exe type`, `workspace-write`, and `--disable unified_exec`. This is a reproducible fail-closed policy boundary, not a path-resolution failure or evidence that one named upstream change is causal. The earlier separate full-access diagnostic remains path-compatibility evidence, not a passing read-only support cell. Future advisory checking must classify policy rejection explicitly and preserve stderr/receipt hashes without weakening required support cells.
- A disposable app-server protocol probe using Codex runtime 0.147.0-alpha.6.6 and a pre-created isolated `CODEX_HOME` passed in an effective read-only sandbox. `initialize` returned that isolated home; `skills/list` returned the namespaced selected skill and its absolute installed `SKILL.md` path; `turn/start` carried the same explicit skill path; the task made exactly three successful direct reads for the entry skill, nested routine, and agent charter, returned all three nonces, used no search/glob, completed successfully, and emitted zero stderr. Fixture v0.0.3 hash: `6891cc1f08ac9755b5080890a2157352838c8dd2c2dbf84ff0683c0c8d08adfd`; event hash: `c462bc287596ba35cd0d30ae751d24bcea0b8fe162ef683d1cbbf809fcf885c9`.
- That receipt proves an isolatable app-server/backend contract, not the ChatGPT desktop UI shell or its access-controlled bundled runtime. The installed Windows app build is 26.803.10989.0, whose active ChatGPT child runs a separate bundled `app/resources/codex.exe`; direct launch of that binary was denied by Windows package ACLs. Under approved Branch B, desktop-shell behavior remains explicitly unproven at ADR time and becomes a hard `ca-codex` candidate-release gate. Do not infer desktop support from Docker, app-server, or CLI receipts, bypass package ACLs, or mutate the user's live plugin profile.
- Read-only Branch A isolation characterization found the current app as Store-signed MSIX `OpenAI.Codex_26.803.10989.0_x64__2p2nqsd0c76g0`, family `OpenAI.Codex_2p2nqsd0c76g0`, with full-trust entry point `app/ChatGPT.exe`. Official OpenAI documentation makes its Codex home `%USERPROFILE%\.codex`, while the stable `CODEX_HOME` table omits the desktop shell. Those facts are retained as evidence explaining why a container cannot satisfy the desktop cell. Branch B requires the eventual candidate proof to run on an actual ephemeral Windows desktop runner or VM with an isolated Windows profile and ChatGPT browser/device authorization within the repository user's included access; a Linux or Windows container may test CLI/app-server behavior but is not a desktop-shell substitute.
- ChatGPT account-side state remains a separate release boundary. Authentication is an explicit user-consent gate: surface the official browser URL and device code visibly, wait for the user to authorize, and never copy, export, automate, or persist credentials, callbacks, codes, cookies, or tokens. If no supported ChatGPT browser/device flow can authenticate the actual desktop shell within included access, `ca-codex` release remains blocked while implementation may proceed.
- Attempts to enumerate all-user app registration and query the Windows Sandbox optional feature were denied without elevation. Those failures are retained as framework/setup evidence; they were not bypassed and do not change the local-user recommendation.
- Consequently, the tracked Stage 1 four-cell CLI/app-server characterization is complete, and the repository user explicitly ratified ADR-0031 as `accepted` on 2026-08-22 with its decision content unchanged. Desktop exact-candidate proof remains a later release gate, and planning still does not itself authorize product implementation.

## Recommended architecture decision

ADR-0031 is accepted at `.codearbiter/decisions/0031-cross-host-plugin-root-and-agent-charter-resolution.md` after the Codex skill-source/relative-reference characterization passed and before implementation. ADR-0031 explicitly **partially supersedes ADR-0011** where ADR-0011 selected `ca-init` scaffolding of `.codex/agents/*.toml` plus doctor staleness checks for hosts that cannot ship subagents. The forward supersession is appended to `.codearbiter/decisions/decision-log.md`; never rewrite ADR-0011.

### Decision A — `ARBITER_PLUGIN_ROOT` is the product abstraction, not a promised host variable

Canonical Python/TypeScript identifiers, diagnostics, and product prose use `ARBITER_PLUGIN_ROOT` or the existing `plugin_root()` API to mean “the validated root of the installed codeArbiter adapter.” Canonical Markdown continues to use `{{PLUGIN_ROOT}}`; `core/hosts.json` renders that token into the syntax the target host can actually resolve.

`ARBITER_PLUGIN_ROOT` is not assumed to be injected or interpolated by Claude Code, Codex, or Pi. A codeArbiter-owned launcher may export it to a child process after resolving and validating the root, but it is not a substitute for a host-native variable in host-parsed configuration or skill prose.

### Decision B — host-specific root inputs and precedence

Each adapter validates all available root signals by real path, containment, exact adapter name/version, and an expected manifest or anchor file. When executing code, the root derived from the executing file/module is authoritative; environment values corroborate it and must never redirect it to another valid-looking package tree. Never concatenate an unvalidated ambient value into an executable path.

| Execution context | Authoritative resolution and corroboration | Rendered/config syntax | Compatibility obligation |
|---|---|---|---|
| Claude plugin content | Claude performs native substitution | `${CLAUDE_PLUGIN_ROOT}` where Claude performs interpolation | Keep the native token indefinitely unless Claude publishes a replacement. Do not render `${ARBITER_PLUGIN_ROOT}` into Claude content. |
| Claude hook subprocess | derive from the executing hook’s `__file__`; require native `CLAUDE_PLUGIN_ROOT`, when present, to resolve to the same adapter root | `${CLAUDE_PLUGIN_ROOT}` locates the initial hook command | Preserve native interpolation and fail closed on a root mismatch. |
| Codex hook subprocess | derive from the executing hook’s `__file__`; require native `PLUGIN_ROOT` to resolve to the same root; accept legacy `CLAUDE_PLUGIN_ROOT` only when it also matches | `${PLUGIN_ROOT}` in `hooks.json` | Keep the legacy alias as corroborating input for the approved compatibility window, never as authority. |
| Codex ordinary skill/routine tool calls | obtain the absolute selected-entry `SKILL.md` source path from Codex’s skill loader; walk upward to the nearest `.codex-plugin/plugin.json` whose name is `ca-codex`; resolve every nested resource from the Markdown file that references it | normalized relative Markdown links for resources; the validated absolute root retained as the workflow-local `ARBITER_PLUGIN_ROOT` value for executable paths | Do not read hook-process environment or search/glob the plugin cache. This mechanism must pass the pre-ADR clean-home characterization below before approval. |
| Pi extension/runner | derive from `import.meta.url`; any explicit adapter argument must realpath-match the `@arbiterforge/ca-pi` package root | package-relative paths or `<plugin-root>` instructions expanded by the adapter | Preserve module-relative derivation. Pi does not inject a root variable. |
| Pi Python hook bridge | derive from the executing hook’s `__file__`; any explicit adapter argument must match that package root | no host interpolation dependency | Preserve file-relative derivation and fail closed if the expected package boundary is absent. |

`ARBITER_PLUGIN_ROOT` is therefore an output of validated resolution, not an ambient input with precedence. A named codeArbiter-owned launcher may pass it as an explicit child-process argument or environment value only after deriving it by the rules above. The callee validates exact realpath equality before use. “Explicit trusted argument” means only this named launcher boundary; user-shell ambient state does not qualify.

Where a host/environment value and a file/module-derived root disagree, diagnostics report both and fail closed for executable payloads. The resolver must not silently select a path outside the installed package.

### Decision C — Codex ships resource charters, then uses host-native dispatch

Generate `plugins/ca-codex/agents/INDEX.md` and all 18 canonical `plugins/ca-codex/agents/*.md` files from `core/surface/agents/`. Treat these files as versioned plugin resources, not native registrations.

For every Codex output file, `tools/build-surface.py` computes the POSIX-style relative path from that output file’s directory to its target resource. Render a Markdown link, not a shell-relative path. Examples:

- `plugins/ca-codex/skills/ca-add-dep/SKILL.md` links `[dependency-reviewer](../../agents/dependency-reviewer.md)`;
- `plugins/ca-codex/routines/commit-gate/SKILL.md` links `[migration-reviewer](../../agents/migration-reviewer.md)`;
- `plugins/ca-codex/routines/skill-author/references/skill-template.md` links `[agent charter](../../../agents/<name>.md)` only as an authoring template, while concrete shipped routes name concrete files.

At skill invocation, the orchestrator takes the absolute source path supplied for the selected entry `SKILL.md`, walks upward to the validated `ca-codex` manifest, retains that absolute directory as the workflow-local root, and resolves each relative link against the Markdown file containing it. Nested routines link to their resources from their own directory. Executable hook/helper commands use the retained validated absolute root; they never depend on the process working directory, hook-only environment, or a cache glob.

This design is conditional on one pre-ADR characterization: supported Codex app-server and CLI versions must expose a stable absolute selected-skill source path and allow the loaded skill to follow relative local Markdown references. Official documentation establishes `CODEX_HOME` as the app-server state root; the exploratory receipt—not the documentation—proves that one standalone binary can be isolated and given an explicit selected-skill path. Docker or another isolated process environment may host these backend cells. Neither establishes the desktop-shell contract. A required CLI/app-server failure stops ADR authoring rather than permitting a guessed path; desktop-shell proof is deferred to the exact `ca-codex` candidate before release.

Once that precondition passes, the Codex host note instructs a workflow to:

1. resolve and read the named packaged charter;
2. create a host-provided generic agent thread with the charter body and the concrete assignment;
3. preserve the returned thread ID/receipt where the workflow requires isolated evidence;
4. block where isolation is mandatory and unavailable, exactly as today; never skip a required review.

Codex rendering strips Claude/Pi-only executable frontmatter so the resource does not falsely claim that Codex registered its `tools`, `model`, or Pi skill metadata. It preserves host-neutral `name`, `description`, and classification metadata and generates a dispatch-policy index from the canonical frontmatter. The charter body, including read/write prohibitions, remains intact.

The dispatch policy is explicit rather than inferred at runtime:

| Policy class | Canonical roles | Codex type preference | Permission/write contract | Isolation and fallback | Model behavior |
|---|---|---|---|---|---|
| author | `backend-author`, `frontend-author`, `infra-author` | `worker` | write-enabled only inside the assigned worktree/scope; all writes still pass codeArbiter hooks | fresh isolated worktree/thread required; block if the workflow requires isolation and the host cannot provide it | host-supported configured model if an approved mapping exists; otherwise host default and record parity degradation |
| read-only reviewer/extractor | `architecture-drift-reviewer`, `auth-crypto-reviewer`, `coverage-auditor`, `decision-challenger`, `dependency-reviewer`, `design-quality-reviewer`, `finding-triage`, `grader`, `map-deps`, `map-structure`, `migration-reviewer`, `scout`, `security-reviewer` | `explorer` when available, otherwise `default` | no file mutation; use a host-enforced read-only sandbox when available | fresh thread; `scout`, map roles, and any workflow declaring isolated evidence block if isolation is unavailable; inline fallback only where the existing canonical workflow explicitly permits it | do not translate Claude `haiku`/`sonnet` names into invented Codex tiers; use an approved host mapping or record host-default degradation |
| bounded writer/aggregator | `checkpoint-aggregator`, `tribunal-lens-reviewer` | `worker` | writes limited to the charter-declared checkpoint/finding output path; all other writes prohibited and hooks remain active | fresh thread; no inline fallback where an exact per-agent receipt is required | approved host mapping or documented host-default degradation |

Codex built-in type preference is not a permission boundary by itself. Before calling this parity-supported, the implementation must prove the requested read-only/write/sandbox controls on every supported Codex version. Any control the host cannot enforce is recorded as a `docs/parity.md` degradation and requires explicit user approval; mandatory isolation or write-containment may not silently degrade to prompt-only guidance.

Do not add an unsupported `agents` key to `.codex-plugin/plugin.json` and do not describe these Markdown resources as native Codex custom agents.

### Alternatives and tradeoffs

| Alternative | Benefit | Cost/risk | Decision |
|---|---|---|---|
| Scaffold `.codex/agents/*.toml` into every governed project | Native named Codex agent types and native per-role configuration | Writes outside `.codearbiter/`; may overwrite or conflict with user agents; requires lifecycle, upgrade, uninstall, and provenance rules; changes `ca-init`; plugin updates cannot directly refresh project files | Reject for this migration. Reconsider only through a separate ADR and explicit user approval. |
| Translate each role into a hidden Codex skill | Plugin-native resource discovery | Skills are not agent identities; risks surfacing internal roles and still needs a thread-dispatch contract | Reject. |
| Package only `dependency-reviewer.md` | Smallest patch for issue #699 | Leaves other direct and generic routes unresolved; preserves a structurally broken package | Reject. |
| Continue resolving Codex paths through the compatibility alias | Minimal churn | Makes a Claude-named compatibility alias the product contract and remains unavailable to ordinary tool calls | Temporary fallback only. |
| Branch A: require an isolated desktop fixture before ADR authoring | Strongest early evidence | Requires interactive Store/MSIX and ChatGPT authentication before the backend contract is known and makes the user part of the early characterization harness | Rejected by the repository user on 2026-08-21 in favor of backend-first Branch B. |
| Branch B: prove CLI/app-server in containers or isolated homes before ADR; prove the exact candidate in an isolated Windows desktop lane before release | Unblocks architecture and implementation without claiming Docker proves the desktop shell | Desktop incompatibility may be discovered later; requires verifiable runner provenance plus an explicit ChatGPT browser/device authorization gate within included access; `ca-codex` release blocks if either is unavailable | Approved. |

### Approved user/ADR decisions before implementation

1. **Branch B approved:** require tracked clean-home/containerized CLI and app-server evidence before ADR authoring, then require actual current-build Windows desktop-shell proof against the exact `ca-codex` candidate before release. Docker is acceptable for backend resource-resolution cells but never stands in for Store/MSIX registration, full-trust desktop execution, per-user Windows state, or desktop authentication. Use an isolated Windows runner/profile and ChatGPT browser/device authorization within the repository user's included access. Authentication is an explicit consent gate: open the official authorization page visibly, present any device code in a copyable block, and wait for the user. API-key use, API-billed substitution, secret creation/export, copied sessions, and purchased infrastructure are prohibited. If the runner or supported ChatGPT authorization is unavailable, block `ca-codex` release rather than reuse credentials or infer desktop compatibility.
2. The resource-charter architecture is approved only after tracked clean-home receipts prove that CLI 0.143.0 and 0.145.0 plus app-server 0.143.0 and 0.145.0 expose the selected skill's absolute source path and follow relative local Markdown references. The exploratory 0.147.0-alpha.6.6 app-server receipt establishes feasibility only; it is not a substitute for the tracked fixture and required matrix. If either property fails in a required backend cell, stop before ADR authoring. Desktop failure later blocks `ca-codex` release and returns the architecture for review without weakening the gate.
3. **Approved:** resource charters plus host-provided dispatch are the Codex model, and ADR-0031 partially supersedes ADR-0011. Project-scaffolded native TOML is rejected for this migration because of its lifecycle/conflict surface.
4. **Approved:** use the per-policy dispatch mapping and record every difference from canonical Claude tool/model/isolation semantics. Mandatory isolation and write containment remain blockers, not degradations.
5. **Approved:** `ARBITER_PLUGIN_ROOT` is an internal normalized output rather than a public promise that every host injects the variable. If a public child-process environment contract is later required, name the codeArbiter-owned launcher and callees; it still cannot replace Claude’s native interpolation token.
6. **Approved:** retain the corroborating Codex legacy `CLAUDE_PLUGIN_ROOT` alias for the next `ca-codex` minor line and remove it only after pinned and advisory host evidence shows no supported host needs it.

**User decisions recorded 2026-08-21 and 2026-08-22:** the repository user approved all six recommended outcomes, replaced Branch A with backend-first Branch B, prohibited API-key/API-billed substitution, approved the existing `core/` plus deterministic generators as the internal `ca-core` boundary, and explicitly ratified ADR-0031 as `accepted` with its decision content unchanged. The tracked four-cell CLI/app-server prerequisite passes. Actual Windows desktop-shell behavior remains unproven and is a separate, mandatory candidate-release gate for `ca-codex`, using an isolated runner/profile and explicit ChatGPT browser/device authorization within included access. Container evidence remains backend-only. A desktop runner, authentication, provenance, or candidate failure blocks `ca-codex` release; none authorizes bypassing ACLs, copying credentials, fabricating evidence, or weakening a gate.

**Remaining prerequisites:** ADR-0031 lifecycle ratification is complete. Before `ca-codex` release, an infrastructure preflight must prove that the actual Store/MSIX desktop can complete ChatGPT browser/device authorization within included access, install the local fixture/candidate plugin, and exercise the required resource routes from an isolated Windows profile. Operations must designate the Windows runner/image, profile lifecycle, authorization handoff, attestation issuer/verifier, and teardown. Durable evidence records only non-secret authentication mode and event hashes; it never records the device code, callback, cookies, tokens, auth files, screenshots, or raw login output. This plan authorizes no API-key use, API billing, purchase, subscription change, account/key creation, secret export, or infrastructure provisioning. If any prerequisite is unavailable, implementation may continue but `ca-codex` cannot be released.

## File inventory by responsibility

### Canonical descriptors and surface templates — edit these, then regenerate

- `core/hosts.json` — host tokens, capabilities, surface rules, managed subtrees, package metadata.
- `core/surface/includes/codex-host-notes.md` — Codex dispatch and root-resolution behavior.
- `core/surface/README.md` — active generator contract; its “Codex agents are not rendered” row must change with the descriptor.
- `core/surface/skills/subagent-driven-development/SKILL.md` — one direct Claude-root conditional.
- `core/surface/skills/tribunal/SKILL.md` — one direct Claude-root conditional.
- `core/surface/agents/INDEX.md` and the 18 canonical charter files — sole charter source of truth.
- `tools/host_descriptors.py` — descriptor parsing/validation if the schema gains resource-vs-native-agent metadata.
- `tools/build-surface.py` — host rendering, Codex charter transformation, managed output calculation.

### Canonical runtime/hook code — edit canonical copies only

- `core/pysrc/hostapi.py`
- `core/pysrc/_durabilitylib.py`
- `core/pysrc/_releaselib.py`
- `core/pysrc/_updatelib.py`
- `core/pysrc/doctor.py`
- `core/pysrc/session-start.py`
- `core/pysrc/statusline.py`
- `core/pysrc/wire-statusline.py`
- `plugins/ca/hooks/_host.py`, `plugins/ca-codex/hooks/_host.py`, `plugins/ca-pi/hooks/_host.py` — host-specific seams, not `sync-core` outputs.
- `plugins/ca-pi/tools/src/extension.ts` and `plugins/ca-pi/tools/src/runner.ts` — Pi package-root derivation.

### Generated plugin payloads — never hand-edit

`tools/build-surface.py` owns the managed Markdown outputs declared in `core/hosts.json`:

- `plugins/ca/commands/`, `plugins/ca/skills/`, `plugins/ca/includes/`, `plugins/ca/agents/`, `plugins/ca/COMMANDS.md`, `plugins/ca/SPRINT.md`, `plugins/ca/arbiter.md`, `plugins/ca/ORCHESTRATOR.md`;
- `plugins/ca-codex/skills/`, `plugins/ca-codex/routines/`, `plugins/ca-codex/includes/`, the proposed `plugins/ca-codex/agents/`, `plugins/ca-codex/COMMANDS.md`, `plugins/ca-codex/SPRINT.md`, `plugins/ca-codex/arbiter.md`, `plugins/ca-codex/ORCHESTRATOR.md`;
- `plugins/ca-pi/skills/`, `plugins/ca-pi/routines/`, `plugins/ca-pi/includes/`, `plugins/ca-pi/agents/`, `plugins/ca-pi/COMMANDS.md`, `plugins/ca-pi/SPRINT.md`, `plugins/ca-pi/arbiter.md`, `plugins/ca-pi/ORCHESTRATOR.md`, `plugins/ca-pi/generated/`.

`tools/sync-core.py` owns every host-neutral Python file copied from `core/pysrc/` into `plugins/ca/hooks/`, `plugins/ca-codex/hooks/`, and `plugins/ca-pi/hooks/`. Do not edit those copies directly. `tools/build-host-packages.py` owns the repository-root `package.json` derived from `plugins/ca-pi/package.json`; never edit the root manifest directly.

Host-owned registrations and manifests are not generated by those two tools:

- `plugins/ca/hooks/hooks.json`
- `plugins/ca-codex/hooks/hooks.json`
- `plugins/ca/.claude-plugin/plugin.json`
- `plugins/ca-codex/.codex-plugin/plugin.json`
- `plugins/ca-pi/package.json`

### Tests, fixtures, and CI that encode the current contract

- `.github/scripts/check-plugin-refs.py` — remove the Codex `agents/` pending-prefix exemption after resources ship.
- `.github/scripts/check_routing_index_parity.py` — change Codex from `has_agents=False` to resource-charter parity.
- `.github/scripts/test_check_routing_index_parity.py`
- `.github/scripts/test_build_surface.py` — replace the Codex Claude-token expectation; add all-charter rendering/frontmatter tests.
- `.github/scripts/test_recorded_intent_surface.py` — remove the assertion that the Codex grader charter must be absent; add it to copy/parity coverage.
- `.github/scripts/test_codex_adapter.py` — resolver precedence, mismatch, containment, and legacy-alias tests.
- `.github/scripts/test_hooks_cold_install.py` — cold-install root behavior across supported interpreters/OS paths.
- `.github/scripts/test_consumer_smoke.py` — packaged route closure and released consumer view.
- `.github/scripts/check_codex_host.py` — real-host installed-resource readback and manifest/root verification.
- `.github/scripts/payload_version_gate.py` and `.github/scripts/test_payload_version_gate.py` — require `ca`/`ca-codex` payload versions to advance in the same PR.
- `.github/scripts/payload_scope.py` and `.github/scripts/test_payload_scope.py` — define which package files trigger those version gates.
- `.github/scripts/test_skill_portability.py` and `.github/scripts/check_skill_portability.py` — host-neutral vocabulary and allowed native exceptions.
- `.github/scripts/test_release_lib.py` — release-root compatibility where `_releaselib.py` changes.
- `.github/workflows/ci.yml` — impact filters and required lanes for the new `agents/` payload and resolver files.
- `.github/workflows/release.yml` — inspect/update only if package contents or pre-tag gates are enumerated there.

### Sandbox surface — migrate terminology only if it shares the product abstraction

- `plugins/ca-sandbox/COMMANDS.md`
- `plugins/ca-sandbox/commands/sandbox.md`
- `plugins/ca-sandbox/commands/sandbox-cp.md`
- `plugins/ca-sandbox/commands/sandbox-destroy.md`
- `plugins/ca-sandbox/commands/sandbox-exec.md`
- `plugins/ca-sandbox/commands/sandbox-shell.md`
- `plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md`
- `tools/build-surface.py`

The sandbox is a Claude companion package, not a fourth governance host. Keep native Claude interpolation where executable, but stop presenting the Claude variable name as a codeArbiter-wide identity.

### Active product identity and documentation — update claims, not history

- `.codearbiter/CONTEXT.md`
  - keep its three-host/four-package topology;
  - identify `core/` as the governance kernel and `plugins/ca/` as the Claude adapter;
  - remove the stale “Codex beta until live verification” claim;
  - state that Codex charters are packaged resources, not native agent registrations;
  - describe host-specific status surfaces instead of implying one global statusline.
- `.codearbiter/tech-stack.md` — replace the Claude-only hook/plugin framing with shared-core plus three-adapter build/test ownership; preserve host-specific version floors.
- No `.codearbiter/code-map.md` exists on `origin/main`. Do not invent one solely for this migration. If a later context refresh creates it through the governed context workflow, apply the same product identity there.
- `.codearbiter/.provenance/release-targets.json` — this currently tracks the sources of the `release-targets` context document, not `CONTEXT.md`. Manifest/version edits will make that provenance stale; handle it through `$ca-context-check` and the governed re-baseline path, never by fabricating hashes.
- `README.md` — already leads with three hosts; update only root vocabulary and exact Codex charter-resolution claims.
- `plugins/ca/README.md` — the only authored package README under the three governance payloads; keep its Claude-specific install surface but remove any claim that makes the Claude adapter the whole product.
- `CONTRIBUTING.md` — replace “a Claude Code plugin,” three-host setup omissions, and “both plugins” language.
- `SECURITY.md` — describe shared enforcement across three adapters, host-specific status/diagnostics, and report fields for host plus adapter version.
- `docs/architecture.md`
- `docs/parity.md` — remove the unresolved Codex-agent exception only after resource closure is tested.
- `docs/patterns/lazy-load-bundles.md`
- `docs/codex-parity-testing.md` — add installed-charter and live-dispatch evidence without rewriting older recorded baselines.
- `site/src/content/docs/getting-started/choose-your-host.md`
- `site/src/content/docs/getting-started/install.md`
- `site/src/content/docs/getting-started/quickstart.md`
- `site/src/content/docs/getting-started/pi.md`
- `site/src/content/docs/enforcement.md` — opening currently says “both plugins” before later mentioning Pi.
- `site/src/curated/commands/statusline.md` — keep Claude-native syntax and label it Claude-specific.
- `site/scripts/generator/render-lens-page.ts`
- `site/scripts/generator/render-reference-lead.ts`
- `site/test/generator/render-hooks-reference.test.ts`
- `site/src/curated/commands/tribunal.md` and tests pinning its charter-dispatch claim.
- `plugins/ca-codex/.codex-plugin/plugin.json` — describe the shared three-host product and resource-charter behavior; do not add unsupported manifest fields.
- `plugins/ca/.claude-plugin/plugin.json` — its host-specific Claude description may remain host-specific.
- `plugins/ca-pi/package.json` and generated root `package.json` — add or align description only through the Pi manifest generator contract.

`site/src/content/docs/getting-started/claude-code-and-codex.md` and deliberate two-host comparison documents may continue saying “both” when their scope is explicitly Claude plus Codex.

### Historical and released evidence — immutable

Do not bulk-rewrite old terminology in:

- `CHANGELOG.md`
- `plugins/ca-codex/CHANGELOG.md`
- `plugins/ca-pi/CHANGELOG.md`
- `.codearbiter/open-tasks.md` entries that record completed historical work
- `.codearbiter/plans/codex-support.md`
- `.codearbiter/plans/codex-surface-m3.md`
- `.codearbiter/plans/portable-release-and-protected-state.md`
- `.codearbiter/plans/session-hygiene.md`
- `.codearbiter/reports/2026-07-09-codex-support-branch/findings/observability/observability-001.json`
- `.codearbiter/specs/release-portable-fixture.md`
- `.codearbiter/spikes/codex-extension-surface.md`
- release receipts, published tags, audit logs, checkpoint reports, and artifact evidence.

New releases append new changelog entries. They do not edit old entries to make the past appear multi-host or root-neutral.

## Codex agent-route closure

### Direct shipped references

At refreshed baseline `cacdb7899c83e8d8ff2a49f3e0e918e56f3a0d1a`, the 20 direct route occurrences appear on 19 matching lines in these 11 generated files (the `security-architecture` line contains two paths):

- `plugins/ca-codex/routines/commit-gate/SKILL.md`
- `plugins/ca-codex/routines/crypto-compliance/SKILL.md`
- `plugins/ca-codex/routines/decision-lifecycle/SKILL.md`
- `plugins/ca-codex/routines/decision-variance/SKILL.md`
- `plugins/ca-codex/routines/dispatching-parallel-agents/SKILL.md`
- `plugins/ca-codex/routines/secret-handling/SKILL.md`
- `plugins/ca-codex/routines/security-architecture/SKILL.md`
- `plugins/ca-codex/routines/subagent-driven-development/SKILL.md`
- `plugins/ca-codex/routines/tdd/SKILL.md`
- `plugins/ca-codex/skills/ca-add-dep/SKILL.md`
- `plugins/ca-codex/skills/ca-reconcile/SKILL.md`

Their exact canonical sources are:

- `core/surface/skills/commit-gate/SKILL.md`
- `core/surface/skills/crypto-compliance/SKILL.md`
- `core/surface/skills/decision-lifecycle/SKILL.md`
- `core/surface/skills/decision-variance/SKILL.md`
- `core/surface/skills/dispatching-parallel-agents/SKILL.md`
- `core/surface/skills/secret-handling/SKILL.md`
- `core/surface/skills/security-architecture/SKILL.md`
- `core/surface/skills/subagent-driven-development/SKILL.md`
- `core/surface/skills/tdd/SKILL.md`
- `core/surface/commands/add-dep.md`
- `core/surface/commands/reconcile.md`

The ten directly literal names are `migration-reviewer`, `security-reviewer`, `auth-crypto-reviewer`, `decision-challenger`, `scout`, `grader`, `finding-triage`, `checkpoint-aggregator`, `dependency-reviewer`, and `coverage-auditor`.

### Complete required charter set

Generic author, reviewer, mapping, tribunal, and routing-table paths make all 18 canonical names reachable. The Codex payload must contain this exact set plus `agents/INDEX.md`:

1. `architecture-drift-reviewer`
2. `auth-crypto-reviewer`
3. `backend-author`
4. `checkpoint-aggregator`
5. `coverage-auditor`
6. `decision-challenger`
7. `dependency-reviewer`
8. `design-quality-reviewer`
9. `finding-triage`
10. `frontend-author`
11. `grader`
12. `infra-author`
13. `map-deps`
14. `map-structure`
15. `migration-reviewer`
16. `scout`
17. `security-reviewer`
18. `tribunal-lens-reviewer`

The closure test must discover names from the shipped surface; it must not hard-code only this list or only issue #699. For every literal or generic agent route, the test resolves the installed resource, verifies it remains inside the package, and verifies its name/index entry. That makes future additions fail closed until packaging and routing move together.

## Ordered implementation plan and atomic PR boundaries

Generated source and its generated output must land in the same PR. A “regeneration-only” PR would either hide its source or knowingly break drift gates and is not an acceptable atomic boundary.

### PR 1 — characterize Codex resource resolution and approve the contract

**Current Stage 1 evidence matrix**

| Cell | Obligation | Status on 2026-08-21 | Evidence |
|---|---|---|---|
| CLI 0.143.0 | required minimum | Exploratory pass in read-only sandbox | Thread `01a02566-2b51-7f73-ab63-59e0d1d211d7`; receipt `a7b35f09f8bd5709286b09dd3b44373b22acdfffbee00b2bbd59210425d10ea1`; events `8867116adfe545b1eaac2b7650d01b39a8e29e60041c512fca0db4f67b352db1` |
| CLI 0.145.0 | required pinned | Exploratory pass in read-only sandbox | Thread `01a02563-8a6c-7bb3-9989-469ed9947415`; receipt `31e52d64b2aa78b4232ff34b09e9252e7a90139e29ef7b91b8189acf21895f90`; events `9dce6bd5b794782b7552c06ab8a70ed40d1f320d0310e236688309ff41f0f17e` |
| App-server 0.143.0 | required minimum backend | Exploratory pass in isolated `CODEX_HOME`, effective read-only sandbox | Fixture v0.0.4 `940a96d0b24384d0a241adb370c152b1fe885498558d53e05c543c7f9b5a6125`; thread `01a02598-85c4-7360-8e08-de82a7e6967e`; events `3a42e21bc6f8e37a213d326c70b4060570261592d6cf95352b24958d4682cfdf`; summary `eb4db397e00370604f6991ecd9e836e139212459622719e8d093d607516392db`; stderr empty. npm integrity `sha512-6h53sNtESIYncWVwU7zEjdVajwcad/0H94MOrgGqhwBMa9RRUDVG6DU9E9euC7yRdtrsKDAkJkz/m5moZ6MU3A==`; native executable SHA-256 `5728e3ddf1480103bad235560e95cf7764ea3069f06029f9b2f39eb74a8066f6` |
| App-server 0.145.0 | required pinned backend | Exploratory pass in isolated `CODEX_HOME`, effective read-only sandbox | Fixture v0.0.4 `940a96d0b24384d0a241adb370c152b1fe885498558d53e05c543c7f9b5a6125`; thread `01a0259a-2b41-7f90-993d-a54f6ba8a47c`; events `4df3c2af1046a0f172e996beb6e97860d03acd816bc53b07f15c77aee1b0c842`; summary `fb849e7da3a7f8ffce7d1708b4d5cc4bb73686610e0f8c7817c09e6547b5a6ad`; stderr empty. npm integrity `sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ==`; native executable SHA-256 `83751f15cb6a0a7b97df67752c001e3fe1c20e18ffbfec3ff63567296205eb6c` |
| App-server 0.147.0-alpha.6.6 | exploratory backend | Pass in isolated `CODEX_HOME`, requested/effective read-only sandbox | Thread `01a0257c-1aa9-7ec1-b840-29e79600a223`; fixture v0.0.3 `6891cc1f08ac9755b5080890a2157352838c8dd2c2dbf84ff0683c0c8d08adfd`; events `c462bc287596ba35cd0d30ae751d24bcea0b8fe162ef683d1cbbf809fcf885c9`; stderr empty (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |
| Desktop current build 26.803.10989.0 | Branch B: deferred mandatory candidate-release cell | Unproven; isolated Windows runner/profile, explicit ChatGPT browser/device authorization within included access, and signed provenance are release prerequisites | Current Store-signed full-trust MSIX is `OpenAI.Codex_26.803.10989.0_x64__2p2nqsd0c76g0`; official Store product ID `9PLM9XGG6VKS`; app home `%USERPROFILE%\.codex`. This cell must exercise the actual desktop shell against the exact candidate. Docker/app-server evidence is not accepted as a substitute. API-key/API-billed substitution is prohibited. |
| CLI 0.149.0 | advisory latest | Reproducible fail-closed policy rejection under read-only/never; same bytes pass on 0.145.0 | Fixture v0.0.4-equivalent bytes `cf148e30495e3f8efffde812f36c741cf1a5963ede2a3d260b44910743f50790`; 0.145.0 pass thread `01a025a6-6c80-7cf0-abd6-3c8a28ba6f34`, events `805e92e1f9fc9b12b0c4eb6c767a9399e2277d1ae849012ac055f9b8f0206613`; 0.149.0 rejection thread `01a025a7-4215-76b3-bf24-ff02823392fd`, events `57061f2208f53e9ac3c27b026b20c33a4ddae383eba3b2b4200acf28fe8c5060`, stderr `81fe0b0d6003a76dd0157a7b9e22c9858dc8ca6d7d27d7a27b6a4b3913a8c165`; npm integrity `sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ==`; executable SHA-256 `14b7e6b2356e82d1d9275579eaa588757b4e0a501b65dcc19fccdf77bd83dc00`. Controls with exact allow rules, `disk-full-read-access`, `cmd.exe type`, `workspace-write`, and disabled `unified_exec` also failed closed. The earlier full-access resource-hop diagnostic remains separately labeled path-compatibility evidence, never a read-only pass. |

The required CLI and app-server versions now all pass exploratory characterization, but they do not yet constitute durable ADR evidence: the CLI cells used disposable fixture v0.0.2, the two required app-server cells used shared disposable fixture v0.0.4, and the additional alpha app-server cell used v0.0.3. PR 1 must materialize one tracked fixture, record its deterministic hash, and rerun every required cell against exactly those bytes into durable report artifacts. If the tracked fixture hash differs, none of the exploratory receipts carries forward. The tracked report must preserve the validated receipts or durable artifact references and their hashes; ignored `campaign.html` is operational memory, not the sole ADR evidence.

**Files**

- Create `.github/fixtures/codex-skill-resources/.codex-plugin/plugin.json`.
- Create `.github/fixtures/codex-skill-resources/skills/probe/SKILL.md`.
- Create `.github/fixtures/codex-skill-resources/routines/nested.md`.
- Create `.github/fixtures/codex-skill-resources/agents/probe.md`.
- Create `.github/fixtures/codex-skill-resources/matrix.json` with the four unconditional required cells (CLI/app-server 0.143.0 and 0.145.0), package provenance/integrity, expected reported versions, and the Decision 1 desktop classification. No unversioned `latest` entry is required.
- Create `.github/scripts/check_codex_skill_resources.py` with `--fixtures-only`, `--live`, `--surface cli|app-server|desktop`, `--codex-version`, `--codex-binary`, `--desktop-build`, `--import-receipt`, `--candidate-package`, `--candidate-source-commit`, `--candidate-tree`, `--advisory`, and `--json` interfaces.
- Create `.github/scripts/test_codex_skill_resources.py` for fixture/path/receipt failure modes.
- Create `.github/workflows/codex-desktop-candidate.yml` in PR 1 so its trusted default-branch definition exists before the payload PR; pin third-party actions by full commit SHA and require only `contents: read`, `id-token: write`, and `attestations: write` plus the narrowly scoped protected environment secret.
- Update `.github/workflows/ci.yml` so a required lane runs `test_codex_skill_resources.py` and `check_codex_skill_resources.py --fixtures-only` when the fixture, checker, test, report binding, or workflow changes.
- Update `.github/scripts/test_ci_impact.py` to assert that PR 1's fixture/checker/test paths select that required lane and that the exact commands are present.
- Create `docs/reports/codex-skill-resource-resolution.md` as the source-backed characterization receipt; record exact Codex app-server/CLI versions, container or isolated-home environment, OS, fixture hash, selected `SKILL.md` absolute path, relative nested-resource reads, and failure output. State explicitly that it is not desktop-shell evidence.
- Add `.codearbiter/decisions/0031-cross-host-plugin-root-and-agent-charter-resolution.md` through `$ca-adr` only after the live characterization passes.
- Append the ADR-0031 entry and partial supersession of ADR-0011 to `.codearbiter/decisions/decision-log.md` through the governed ADR workflow.

**Tasks**

- [ ] Build a disposable plugin fixture whose entry skill must report its own absolute source path, follow `../../routines/nested.md`, and from that file follow `../agents/probe.md`; the expected nonce is different in each file so an inline or guessed response cannot pass.
- [ ] Make fixture-only mode validate manifest shape, relative-link containment, nonce uniqueness, and expected paths without requiring a model credential.
- [ ] Make fixture-only mode recompute the tracked fixture hash, validate every required matrix entry's exact version and non-empty provenance/integrity, and verify the durable report/receipt binding names the same hash.
- [ ] Make live mode install the fixture into an isolated Codex home, start a fresh task, invoke only the probe skill, and emit a JSON receipt. It fails unless the reported entry path is absolute, both nested nonces are returned, every resolved path stays inside the installed plugin, no cache search/glob appears in the transcript, and the receipt records the requested and effective sandbox modes.
- [ ] For app-server cells, pre-create an isolated `CODEX_HOME`, start the exact requested binary over stdio, assert `initialize.codexHome`, enumerate the namespaced selected skill and its absolute path through `skills/list`, pass that exact path as a typed skill input, and validate requested/effective approval and sandbox modes plus the three direct reads.
- [ ] Run the four required backend cells in reproducible containers or equivalently isolated clean homes. Pin the exact Codex package version, package integrity, native executable hash, base image/OS identity, fixture hash, sandbox/approval modes, and network policy. Keep CLI and app-server receipts separate even when they share a container image.
- [ ] Make every backend receipt state `surface: cli` or `surface: app-server` and `desktop_shell_proven: false`. Reject a receipt that labels container, CLI, or app-server output as desktop evidence.
- [ ] Rerun the exact tracked fixture on CLI 0.143.0 and 0.145.0 plus app-server 0.143.0 and 0.145.0 before ADR authoring. The advisory-latest run records drift but does not rewrite the supported contract.
- [ ] Define and unit-test the future desktop candidate-receipt schema and import validation in PR 1, but do not require or fabricate a desktop receipt for ADR approval. The schema must bind an exact candidate digest/source commit, actual Windows desktop package/build/runtime, ephemeral runner image and Windows account identity, isolated profile root, `chatgpt-device` authentication mode, selected resource paths/relative reads, no-search/no-glob evidence, workflow/run/environment identity, and non-secret event hashes. Receipt validation also requires a GitHub/Sigstore provenance attestation over the receipt artifact digest from the protected Windows signer workflow.
- [ ] Record CLI 0.149.0's read-only blocked-read result as advisory drift. Do not convert the passing full-access diagnostic into a passing no-write cell or weaken required-cell sandbox assertions to make latest green.
- [ ] If a required CLI/app-server cell fails, retain the failure as first-class framework evidence, stop before ADR authoring, and return the architecture choice for review. Do not reinterpret a blocker as permission to bypass policy. A later desktop failure is classified separately and blocks `ca-codex` release.
- [ ] If all required cells pass, record Decisions A–C, the dispatch-policy differences, compatibility window, validation/fail-closed rules, and ADR-0011 partial supersession.
- [ ] Capture the approving user identity/date and resolve every new `CONFIRM-NN` before dependent PRs.

**Approved Branch B Windows release contract**

Branch B deliberately separates backend architecture evidence from desktop release evidence. Containers or isolated homes establish the pre-ADR CLI/app-server contract. The exact `ca-codex` candidate later runs in an ephemeral Windows desktop environment that can install and launch the real Store/MSIX application. Authentication uses ChatGPT browser/device authorization within the repository user's included access and is an explicit user-consent checkpoint, not an unattended credential injection step. API keys, API billing, workspace service-account access tokens, personal access tokens, and copied ChatGPT sessions are prohibited. The runner must not mount, copy, inspect, or reuse the repository user's profile, `.codex` tree, Store session, ChatGPT session, cookies, tokens, or credential-store material.

- Land a protected default-branch Windows candidate workflow in PR 1 before PR 2 exists. PR 2 invokes that trusted workflow with commit C and expected archive digest. The trusted workflow independently checks that C belongs to the target pull request, checks out exact C, rebuilds/verifies the archive, runs the desktop cell, and emits a receipt artifact. Do not execute a signer workflow definition supplied by the payload PR.
- Provision the Windows image/VM through an approved external automation boundary, start the documented ChatGPT browser/device flow, surface the official authorization page and device code visibly to the repository user, and wait for explicit consent. Disable command echo, screenshots, traces, crash dumps, and raw UI logs around authentication. Durable logs and receipts record only `authentication_mode: chatgpt-device` plus non-secret runner/build identity, never the code, callback, cookies, tokens, auth files, screenshots, raw login output, or derivative hashes. After the run, sign out/clear the ephemeral profile and destroy the runner.
- Before PR 2, run an infrastructure preflight against the actual Store/MSIX build to prove ChatGPT browser/device sign-in within included access, local marketplace/plugin installation, new-conversation invocation, and the fixture's exact contained reads. If the preflight fails or authentication changes the tested routes, stop before PR 2 and return the desktop contract to ADR review.
- Install the deterministic archive built from commit C, verify its digest after transfer and installation, refresh/install the plugin through the documented desktop flow, start a new conversation, and exercise every candidate resource route selected by the release test.
- Record the exact trusted workflow commit/path, GitHub run ID/environment, Windows image, desktop package/build, bundled/runtime version, ephemeral Windows account/profile root, authentication mode, candidate commit/archive/resource-manifest digests, selected skill and charter paths, contained reads, no-search/no-glob assertions, task/thread identifier, and non-secret event hashes. Use `actions/attest` pinned to the current reviewed full commit SHA at implementation time to generate GitHub OIDC/Sigstore provenance whose subject is the exact receipt JSON digest. The attestation must bind repository, signer workflow, protected environment, commit C, run ID, and receipt digest.
- Required PR CI verifies the attestation with `gh attestation verify` constrained to `arbiterForge/codeArbiter` and the protected signer workflow, then checks the attested subject digest against commit R's receipt artifact and every receipt/candidate binding. `release.yml` repeats attestation verification and retains the existing squash-safe final-`main` payload digest/metadata comparison before tagging.
- Receipt/attestation validation fails closed on missing/unverifiable provenance, untrusted signer workflow/environment, missing or mismatched run/commit/artifact/candidate binding, wrong desktop build/runtime, non-ephemeral or user-profile paths, any API-key/API-billed or non-ChatGPT authentication mode, credential reuse, search/glob fallback, path escape, unresolved route, secret-bearing output, or any claimed PASS with blockers.
- If documented ChatGPT browser/device authorization within included access cannot exercise the actual desktop shell and local plugin flow, record that limitation and stop `ca-codex` release. Do not substitute an API key, workspace service-account token, Docker, CLI, app-server, copied session, or synthetic command for the desktop cell. Any Windows runner, attestation, or other operational cost requires its own approval outside this planning artifact; this plan authorizes none.

**Verification**

```powershell
python .github/scripts/test_codex_skill_resources.py
python .github/scripts/check_codex_skill_resources.py --fixtures-only
$env:CA_REQUIRE_CODEX_RESOURCE_DISPATCH = '1'
python .github/scripts/check_codex_skill_resources.py --live --surface cli --codex-version 0.143.0 --json
python .github/scripts/check_codex_skill_resources.py --live --surface cli --codex-version 0.145.0 --json
python .github/scripts/check_codex_skill_resources.py --live --surface app-server --codex-version 0.143.0 --json
python .github/scripts/check_codex_skill_resources.py --live --surface app-server --codex-version 0.145.0 --json
python .github/scripts/check_codex_skill_resources.py --live --surface cli --codex-version latest --advisory --json
Remove-Item Env:CA_REQUIRE_CODEX_RESOURCE_DISPATCH
python .github/scripts/check_adr_identity.py
python .github/scripts/test_adr_identity.py
git diff --check
```

The script interfaces above are implementation-owned test helpers, not public codeArbiter commands. The four versioned CLI/app-server commands are unconditional and are the Branch B ADR precondition. Do not claim a supported Codex contract from fixture-only mode, and do not claim desktop support from any of these commands. The candidate-bound desktop import appears in PR 2's pre-release verification only.

### PR 2 — ship root normalization and complete Codex charter resolution atomically

This is the only payload-changing implementation PR. It combines root migration and Codex charter packaging so `ca-codex` advances once, and it carries every changed package’s version/changelog metadata required by CI.

**Files**

- Canonical resolver/runtime files listed above under `core/pysrc/`.
- `plugins/ca/hooks/_host.py`, `plugins/ca-codex/hooks/_host.py`, `plugins/ca-pi/hooks/_host.py`, `plugins/ca-pi/tools/src/extension.ts`, and `plugins/ca-pi/tools/src/runner.ts`.
- `core/hosts.json`, `tools/host_descriptors.py`, `tools/build-surface.py`, `core/surface/README.md`, `core/surface/includes/codex-host-notes.md`, and the 11 canonical route-source files enumerated above.
- Generated Python copies under all three `plugins/*/hooks/` trees and all descriptor-affected generated Markdown outputs.
- Generated `plugins/ca-codex/agents/` with 18 charters, `INDEX.md`, and the generated dispatch-policy table/index.
- `plugins/ca-codex/hooks/hooks.json`, `.github/scripts/check_codex_host.py`, and all resolver/generator/routing/consumer tests listed in the inventory.
- `.github/scripts/check-plugin-refs.py`, `.github/scripts/check_routing_index_parity.py`, `.github/scripts/test_check_routing_index_parity.py`, `.github/scripts/test_recorded_intent_surface.py`, and `.github/workflows/ci.yml`.
- `docs/reports/codex-desktop-candidate-resolution.json` as the commit-R attestation for the exact commit-C candidate package.
- `.github/workflows/codex-desktop-candidate.yml` as the trusted default-branch Windows desktop runner/attestation workflow, introduced in PR 1 and invoked by PR 2 without accepting a PR-supplied signer definition.
- `.github/workflows/release.yml` and `.github/scripts/test_release_workflow.py` so the candidate attestation is revalidated before any automatic `ca-codex` tag is created.
- `plugins/ca/README.md` and current plugin manifest descriptions where package-local identity claims change.
- `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`, `plugins/ca-pi/package.json`, generated root `package.json`, and new changelog sections for every changed package.

**Version rule**

- Re-read versions from the PR’s actual base; do not copy stale numbers from this plan if `origin/main` has advanced.
- At the refreshed planning baseline, manifests are already `ca` 2.15.3, `ca-codex` 0.7.3, and `ca-pi` 0.8.3. The payload PR must compute the next valid SemVer for every changed adapter from its actual merge base; this plan intentionally does not preassign those future versions.
- If the final diff proves one adapter’s shipped payload is byte-identical, omit that adapter’s bump/changelog. Otherwise the bump and exact changelog heading are mandatory in this PR.
- Keep `plugins/ca-pi/package.json` and generated root `package.json` synchronized through `tools/build-host-packages.py`.

**Tasks**

- [ ] Implement file/module-authoritative root resolution and exact-root corroboration. Reject mismatch, traversal, symlink escape, wrong adapter name/version, missing anchor, and paths outside the installed adapter.
- [ ] Immediately before creating the implementation worktree, fetch `origin/main`, rerun the root/reference inventory, and re-audit issue #699 plus open pull requests. Stop or rebase the plan if upstream work supersedes any premise.
- [ ] Render `${CLAUDE_PLUGIN_ROOT}` only for Claude-native interpolation and `${PLUGIN_ROOT}` only in Codex hook configuration. Update `check_codex_host.py` in this same PR to recognize/require the native Codex token while accepting the legacy token only in compatibility fixtures.
- [ ] Render per-file relative Markdown resource links using the characterization-proven algorithm; retain the validated entry-skill-derived absolute root for executable helpers.
- [ ] Add the Codex `agents/` rule/managed subtree, render all 18 charters/index, and generate the approved dispatch-policy mapping without claiming native registration.
- [ ] Remove the `agents/` pending-prefix exemption and absence assertions; validate Codex routing against its installed resource set.
- [ ] Add dynamic route closure over literal and generic role references, counting both matching lines and string occurrences.
- [ ] Test author, read-only reviewer, bounded writer/aggregator, and isolation-required policies. Record any approved host limitation in `docs/parity.md`; block mandatory isolation/write-containment loss.
- [ ] Preserve the legacy Codex alias only as matching corroboration and emit a non-disruptive deprecation diagnostic.
- [ ] Run `sync-core`, `build-surface`, and `build-host-packages`; review their diffs and never hand-edit generated outputs.
- [ ] Append package changelog entries and advance all changed package manifests before opening the PR so payload-version gates are green on the PR and merge queue.
- [ ] Classify every remaining active `CLAUDE_PLUGIN_ROOT` line as Claude-native syntax, legacy Codex fixture/input, or immutable history in an executable CI inventory.
- [ ] Use a two-commit candidate attestation. **Commit C** contains the complete payload, generator inputs/outputs, tests, CI/release wiring, versions, and changelogs. Build a deterministic `ca-codex` candidate archive from exactly C and record its SHA-256. Invoke the protected default-branch Windows workflow with C and that digest. It independently verifies the PR/C relationship, checks out exact C, runs the actual Store/MSIX desktop after the explicit ChatGPT browser/device authorization checkpoint, exercises candidate routes, and emits the receipt artifact plus GitHub OIDC/Sigstore provenance. If the preflight, runner, supported ChatGPT flow, user consent, or attestation is unavailable, stop before `ca-codex` release; Docker/CLI/app-server output cannot satisfy this gate.
- [ ] Make **commit R** attestation-only: it adds `docs/reports/codex-desktop-candidate-resolution.json` and its detached non-secret attestation bundle/reference, with no payload, generator, workflow, checker, test, manifest, or changelog change. The receipt binds C's full commit ID, candidate archive digest, trusted workflow commit/path and run ID, protected environment, Windows image/runner identity, desktop package/build/runtime identity, isolated profile root, `chatgpt-device` mode, fixture/resource hashes, exact selected paths/relative reads, approval/sandbox modes, no-search/no-glob evidence, and non-secret transcript/event hashes.
- [ ] Make required **PR CI**, while the PR commit graph is available, verify GitHub/Sigstore provenance with `gh attestation verify` constrained to repository `arbiterForge/codeArbiter` and the protected signer workflow; verify the attested artifact digest matches commit R; verify C is an ancestor of R; verify `git diff C..R` contains only the allowed receipt/attestation paths; rebuild C's archive; and verify the synthesized PR merge tree reproduces the same candidate payload digest and metadata. Fail closed if provenance is absent/unverifiable or the merge tree changes any candidate-owned source, generator input/output, manifest, or payload byte after C.
- [ ] Account explicitly for the repository's squash-merge behavior: C and R need not remain ancestors of the resulting `main` commit. Update `release.yml` so its `ca-codex` path re-verifies the trusted-workflow attestation, rebuilds the final `main` payload before tag creation, and compares its digest, adapter/version, route/resource manifest, desktop build/runtime/auth-mode binding, and receipt schema to the PR-validated attestation **without requiring C to be fetchable or ancestral on `main`**. Update `test_release_workflow.py`/`test_ci_impact.py` to prove attestation verification plus the digest/metadata gate are required and ordered before automatic tagging. In PR CI, missing/stale/non-ancestor C or R is fatal; after squash, missing/unverifiable attestation or stale/digest-mismatched/wrong-version/wrong-build/wrong-auth-mode metadata is fatal, while absent C ancestry is expected.

**Verification**

```powershell
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_build_surface.py
python .github/scripts/test_codex_adapter.py
python .github/scripts/test_hooks_cold_install.py
python .github/scripts/test_release_lib.py
python .github/scripts/test_skill_portability.py
python .github/scripts/check-plugin-refs.py ca-codex
python .github/scripts/check_routing_index_parity.py
python .github/scripts/test_check_routing_index_parity.py
python .github/scripts/test_recorded_intent_surface.py
python .github/scripts/test_consumer_smoke.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/payload_version_gate.py --plugin plugins/ca --base origin/main
python .github/scripts/payload_version_gate.py --plugin plugins/ca-codex --base origin/main
python tools/build-host-packages.py --check --release-guard-base origin/main
python .github/scripts/test_ci_impact.py
python .github/scripts/test_release_workflow.py
$desktopCandidateReceipt = 'docs/reports/codex-desktop-candidate-resolution.json'
$desktopReceipt = Get-Content $desktopCandidateReceipt -Raw | ConvertFrom-Json
gh attestation verify $desktopCandidateReceipt --repo arbiterForge/codeArbiter --signer-workflow arbiterForge/codeArbiter/.github/workflows/codex-desktop-candidate.yml
python .github/scripts/check_codex_skill_resources.py --surface desktop --desktop-build $desktopReceipt.desktop_build --import-receipt $desktopCandidateReceipt --candidate-package plugins/ca-codex --candidate-source-commit $desktopReceipt.candidate_source_commit --candidate-tree HEAD --json
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test
npm --prefix plugins/ca-pi/tools run build
$env:CA_REQUIRE_CODEX = '1'
python .github/scripts/check_codex_host.py
Remove-Item Env:CA_REQUIRE_CODEX
git diff --check
```

Existing H-01/H-09/H-10/H-14 fixtures must produce equivalent allow/block outcomes before and after root resolution. Real-host evidence installs the candidate into an isolated Codex home and exercises dependency review (`ca-add-dep` with no install), one author, one read-only reviewer, one scout/context route, and one tribunal/checkpoint writer. Record resource paths, hashes, host version, sandbox/permission evidence, thread receipts, and outcomes.

### PR 3 — correct active product identity and project context

This PR contains active, non-payload product/context documentation only. Package-local README and manifest edits belong in PR 2 so they cannot bypass payload versioning.

**Files**

- `.codearbiter/CONTEXT.md` and `.codearbiter/tech-stack.md` through the sanctioned context path.
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, active `docs/**`, active `site/**`, and their tests listed in the inventory.
- `.codearbiter/.provenance/release-targets.json` only through `$ca-context-check` if PR 2’s manifest edits make its declared sources stale.
- No historical plans, ADR bodies, changelog history, release receipts, or audit records.

**Tasks**

- [ ] Describe one governance product with shared `core/` and three host adapters; do not call `plugins/ca/` the kernel.
- [ ] Correct `.codearbiter/tech-stack.md` so shared Python/core ownership and all three adapter stacks/tests are explicit.
- [ ] Explain native root inputs and the normalized Arbiter output without telling users to set a fake environment variable.
- [ ] Label `${CLAUDE_PLUGIN_ROOT}` examples as Claude-specific and use neutral prose in cross-host pages.
- [ ] Describe Codex charters as packaged resources with characterized relative resolution and host dispatch, not native plugin-agent discovery.
- [ ] Keep intentionally two-host pages scoped and preserve every released/historical record.
- [ ] Reconcile release-target provenance separately through `$ca-context-check`; do not hide pre-existing drift in hand-written hashes.

**Verification**

```powershell
python .github/scripts/test_public_codex_docs.py
python .github/scripts/test_public_pi_docs.py
python .github/scripts/test_consumer_smoke.py
python .github/scripts/test_mode_surface.py
python .github/scripts/check_skill_portability.py
npm --prefix site run typecheck
npm --prefix site test
npm --prefix site run build
npm --prefix site run link-audit
git diff --check
```

Inspect rendered HTML for the host chooser, architecture, enforcement, statusline, and tribunal pages after the build. A source grep alone is insufficient.

### Release gating and post-merge rollout — not a metadata-fix PR

PR 2 already contains every required package version and new changelog section. `release.yml` automatically creates each changed target's independent tag after successful `main` CI, so every pre-tag contract must be satisfied before PR 2 merges and must be revalidated by the auto-tag job. Branch B makes the four tracked CLI/app-server cells the earlier ADR prerequisite and separately requires the commit-C candidate-package desktop receipt plus verified provenance added by receipt/attestation-only commit R before any `ca-codex` tag. Post-merge work verifies the resulting tags/artifacts and captures install/live evidence; it does not repair payload metadata or a missing pre-tag gate.

**Tasks**

- [ ] Tell Codex 0.7.2 users to update, start a fresh task, re-trust changed hooks if prompted, and verify with `$ca-doctor`; a one-file cache copy is not a supported repair.
- [ ] State the legacy alias window and removal criterion in new release notes.
- [ ] Before PR 2 merge, run each changed target's sanctioned release dry-run and verify the candidate artifact. For `ca-codex`, complete the protected-workflow commit-C Windows desktop candidate run after the explicit ChatGPT browser/device authorization checkpoint, add only its bound receipt/attestation evidence in commit R, and prove required PR CI plus the automatic-release job verify provenance and rebuild the same digest from the final/merge tree. If the actual desktop run cannot complete with supported included-access authorization, block `ca-codex` release; do not substitute container/backend evidence.
- [ ] After merge, verify the workflow-created independent tags: `v*` for `ca`, `ca-codex-v*` for `ca-codex`, and `ca-pi-v*` for `ca-pi`; only `ca` remains latest-eligible.
- [ ] Verify clean install and immediate-previous-version upgrade on Windows and POSIX, then capture live Claude, Codex, and Pi receipts.

**Verification**

```powershell
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/check_badge_consistency.py
python .github/scripts/check_command_catalog.py
python .github/scripts/check_skill_proof_fresh.py
python .github/scripts/test_consumer_smoke.py
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.5
python .github/scripts/test_pi_platform_contract.py --pi-version 0.84.1
$env:CA_REQUIRE_CODEX = '1'
python .github/scripts/check_codex_host.py
Remove-Item Env:CA_REQUIRE_CODEX
git diff --check
```

Do not describe any target as released until its tag, published artifact, installed readback, and live-path proof all exist. A merged PR or green CI run is not release proof.

## Inventory and regression gates to add

Add a small stdlib-only CI checker, owned under `.github/scripts/`, that emits the categorized active inventory and fails on unclassified root tokens. Its policy should:

- allow `${CLAUDE_PLUGIN_ROOT}` in generated Claude content and explicit compatibility fixtures;
- allow historical records without rewriting them;
- reject new canonical product prose or runtime logic that treats the Claude alias as universal;
- reject `${ARBITER_PLUGIN_ROOT}` in host-parsed configuration; allow it only at a named, tested codeArbiter child-process boundary after authoritative derivation;
- report matching lines and string occurrences separately, and separate canonical source from generated copies so 494 generated matching lines are not mistaken for 494 independent edits.

Reproduce the baseline and review every exception with commands equivalent to:

```powershell
git grep -n -I 'CLAUDE_PLUGIN_ROOT' origin/main -- core tools plugins .github docs site README.md CONTRIBUTING.md SECURITY.md .codearbiter
git grep -n -I 'ARBITER_PLUGIN_ROOT' origin/main -- core tools plugins .github docs site README.md CONTRIBUTING.md SECURITY.md .codearbiter
git grep -n -I -E '\$\{[^}]*PLUGIN_ROOT[^}]*\}/agents/[A-Za-z0-9_-]+\.md' -- plugins/ca-codex
```

The final tree is not required to contain zero `CLAUDE_PLUGIN_ROOT` strings. It is required to contain zero unclassified or incorrectly portable uses.

## Risks and compatibility notes

- **False portability:** replacing text without understanding interpolation produces paths that look neutral but never resolve. Prevent with host-render tests and real installed readback.
- **Exploratory-only Codex skill-source evidence:** the two required CLI versions and matching app-server versions pass the preferred absolute selected-skill/contained-relative-resource behavior, but they used disposable fixtures and receipts outside the tracked source tree. Treat tracked reruns of those four backend cells as ADR prerequisites. Desktop-shell behavior remains unproven until the exact-candidate Windows release lane passes; never promote container evidence into a desktop claim.
- **Untrusted root input:** every environment variable is process input. Derive authority from the executing file/module, resolve symlinks, enforce containment, verify exact adapter name/version, and fail closed on disagreement.
- **Generated-source drift:** changes to generated payloads without canonical source will be overwritten. Keep generator source and outputs in the same PR and require both `--check` gates.
- **Codex agent semantics:** Markdown resources do not apply native TOML agent configuration. Prove the dispatch-policy controls, record host-default model differences, and block mandatory isolation/write-containment loss rather than relying on prompt prose.
- **Payload-version atomicity:** `ca`, `ca-codex`, and Pi gates require changed shipped payloads to advance their metadata on the same PR. Never defer a manifest/changelog correction to a later release PR.
- **Partial charter shipment:** a one-file repair moves the failure. Dynamic closure must cover all direct and generic routes.
- **Cache/upgrade behavior:** installed plugin roots are versioned and ephemeral. Never persist project state inside them; use `.codearbiter/` and the host’s plugin-data location where appropriate.
- **Hook trust changes:** modified hook commands or hashes can require user re-trust and a fresh task. Put that in release notes and live testing.
- **Host-version drift:** Codex compatibility aliases are explicitly compatibility behavior, not the long-term API. Test pinned minimum/known versions plus advisory latest; keep Pi’s pinned contract versions and advisory latest lane.
- **False Docker equivalence:** containers can prove CLI/app-server packaging and resource resolution, but not the Microsoft Store/MSIX full-trust desktop shell, per-user Windows application state, plugin UI refresh/install, or desktop authentication. The checker must reject any backend receipt labeled as desktop evidence.
- **Authentication boundary:** the desktop cell uses ChatGPT browser/device authorization within included access because that is the user population and billing boundary being released. API-key/API-billed evidence, workspace service-account tokens, copied sessions, and headless credentials cannot be relabeled as desktop proof.
- **Untrusted receipt:** a committed JSON receipt can be fabricated. Require GitHub OIDC/Sigstore provenance from the protected default-branch Windows workflow, verify its signer workflow/repository/subject digest in PR CI and again before tagging, and retain squash-safe final-tree payload comparison.
- **Credential and runner leakage:** candidate transfer, receipts, authentication handoff, logs, and teardown can expose authentication material. Redact logs by default, persist only non-secret mode/build/event identity, and destroy the ephemeral runner after receipt export. Never include device codes, callbacks, credentials, cookies, tokens, auth files, credential-store contents, authentication screenshots, raw login output, or derivative secret hashes.
- **Identity overcorrection:** host-specific docs should still name their host. The goal is accurate hierarchy, not erasing Claude, Codex, or Pi terminology.
- **Historical integrity:** old changelogs, plans, issue evidence, and release artifacts must remain accurate to their date even when they use the old vocabulary.
- **Pre-existing context drift:** the planning checkout already reports stale provenance unrelated to this plan. Resolve or explicitly separate that state before an implementation PR; do not conceal it inside migration-generated hashes.
- **Gate regression:** root resolution is upstream of hooks. Preserve exact allow/block decisions and audit writes for H-01, H-09, H-10, H-14 and the rest of the enforcement suite; no permissive fallback on resolution failure.

## Rollout and upgrade sequence

1. In PR 1's isolated worktree, materialize the tracked fixture, matrix, checker/tests, required CI wiring, and draft durable report; run the four required CLI/app-server cells against those exact bytes.
2. Run the four required backend cells in pinned containers or equivalently isolated clean homes. Preserve package/image provenance and receipts, explicitly label `desktop_shell_proven: false`, and stop ADR authoring if any required backend cell fails.
3. After the tracked backend matrix passes, author ADR-0031 through `$ca-adr` with the user-approved Decisions 1–6 and Branch B, append the ADR-0011 partial supersession to the decision log, resolve every new `CONFIRM-NN`, and obtain explicit lifecycle acceptance before committing/opening/landing PR 1. This gate completed on 2026-08-22 when the repository user ratified ADR-0031 as `accepted` with its decision content unchanged.
4. Develop the single payload-changing PR 2 with runtime normalization, complete Codex charters/policies, generated outputs, host-checker changes, package versions, and new changelog sections together.
5. Before PR 2 merges, cut and verify candidate artifacts independently for `ca`, `ca-codex`, and `ca-pi`. For `ca-codex`, run the exact commit-C archive through the protected default-branch Windows workflow after explicit ChatGPT browser/device authorization within included access, generate GitHub OIDC/Sigstore provenance over the receipt, then make commit R receipt/attestation-only. PR CI verifies signer/repository/subject binding, C-to-R ancestry/scope, and merge-tree digest equality while those commits are fetchable. Runner, supported ChatGPT authorization, user consent, or attestation unavailability blocks `ca-codex` release without blocking implementation.
6. Merge PR 2 only after every pre-tag gate passes. Squash merge may discard C/R ancestry, so `release.yml` must validate the final `main` payload against the receipt's digest and bound version/build/resource metadata without requiring C ancestry, then create the independent tags after successful `main` CI. Verify the tagged commit rebuilds the attested candidate digest.
7. Land the non-payload identity/context PR 3 after shipped behavior exists, so public claims never lead reality.
8. Verify clean installs and upgrades from the immediately previous released version on Windows and a POSIX runner.
9. Capture live Claude, Codex, and Pi receipts; only then describe artifacts as installed/live-path verified and append release evidence.
10. Keep the legacy Codex alias during the ADR-approved window. Remove it in a later separately announced release only after supported-host evidence shows it is unused.

## Done when

- [ ] The tracked Codex characterization proves absolute selected-skill source paths and contained relative resource loading on CLI 0.143.0/0.145.0 and app-server 0.143.0/0.145.0, with exact package/image integrity, executable hashes, backend receipts, and explicit `desktop_shell_proven: false`. These four cells—not a synthetic desktop claim—gate ADR-0031.
- [ ] Before `ca-codex` release, the exact commit-C candidate passes on an ephemeral actual-Windows desktop runner after explicit ChatGPT browser/device authorization within included access. The bound receipt records the Windows image/profile, desktop build/runtime, candidate/resource digests, exact direct reads, no search/glob, and non-secret event hashes. GitHub OIDC/Sigstore provenance from the protected signer workflow verifies repository/workflow/run/commit/subject binding. Docker, CLI, app-server, API keys, API-billed evidence, workspace service-account tokens, copied sessions, or synthetic authentication cannot satisfy this cell.
- [ ] No device code, callback, credential, cookie, token, auth file, credential-manager material, authentication screenshot, raw login output, or derivative secret hash appears in durable evidence. If the supported ChatGPT browser/device flow or explicit user consent is unavailable, the `ca-codex` release remains blocked and the receipt is not fabricated.
- [ ] ADR-0031 records the approved root contract, dispatch-policy model, fallback window, alternatives, and partial supersession of ADR-0011’s `.codex/agents` scaffolding clause.
- [ ] Canonical product vocabulary uses the Arbiter abstraction; every remaining Claude-root string is classified as native Claude syntax, Codex compatibility, fixture, or immutable history.
- [ ] Claude executable content still uses host-native `${CLAUDE_PLUGIN_ROOT}` and passes live install/root proof.
- [ ] Codex hook configuration uses native `${PLUGIN_ROOT}`; ordinary skill/resource paths use the characterized selected-skill root plus per-file relative links and never depend on hook-only environment inheritance or cache search.
- [ ] Pi continues deriving package root from module/file location and passes both pinned platform contracts.
- [ ] Root mismatch, traversal, symlink escape, absent manifest, and bad fallback cases fail closed.
- [ ] `plugins/ca-codex/agents/` contains exactly the canonical 18 resource charters plus `INDEX.md`.
- [ ] Every literal and generic shipped Codex agent route resolves inside the installed package.
- [ ] Codex dispatch evidence proves charters are read and supplied to host agent threads and verifies author, read-only reviewer, bounded writer, and isolation-required policies; no docs or manifests claim native Markdown-agent registration.
- [ ] The installed 0.7.2 missing-package failure and subsequent one-file cache repair are captured as before evidence; an isolated, unmodified candidate install supplies the package-level passing after case.
- [ ] `check-plugin-refs.py`, routing-index parity, consumer smoke, real-host install, and generated-surface tests reject future partial packaging.
- [ ] H-01/H-09/H-10/H-14 and all other enforcement outcomes remain unchanged; no gate becomes warn-only or fail-open.
- [ ] `.codearbiter/CONTEXT.md`, `.codearbiter/tech-stack.md`, `core/surface/README.md`, package/root READMEs, contributing/security guidance, active docs/site pages, and current manifests describe one shared product with three host adapters.
- [ ] No historical changelog, old plan/spec/spike, report, release receipt, published tag, or audit record was rewritten.
- [ ] `sync-core --check`, `build-surface --check`, `build-host-packages --check`, focused Python suites, Pi TypeScript suites, docs build/link audit, and every required supported-host cell are green; advisory latest was executed and its verdict/drift recorded without coercing it into a pass.
- [ ] Each changed package’s version/changelog advanced in the same PR as its payload, and each installed candidate artifact reads back that version and complete resource set.
- [ ] Release claims distinguish merged, tagged, published, installed, and live-path verified states.
