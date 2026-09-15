---
status: accepted
date: 2026-08-22
title: Use the internal generated kernel, host-native roots, and Codex resource charters
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0011-multi-host-codex-plugin-shared-core
governs: core/*, tools/sync-core.py, tools/build-surface.py, tools/host_descriptors.py, plugins/ca/*, plugins/ca-codex/*, plugins/ca-pi/*, .github/scripts/check-plugin-refs.py, .github/scripts/check_routing_index_parity.py, .github/scripts/check_skill_portability.py, .github/scripts/check_codex_host.py, .github/scripts/payload_*.py, .github/workflows/ci.yml, .github/workflows/release.yml, docs/parity.md
---

# ADR-0031 - Use the internal generated kernel, host-native roots, and Codex resource charters

## Status
Accepted - ratified by SUaDtL@users.noreply.github.com on 2026-08-22 after the exact proposed record
passed local validation and independent review. The repository user's instruction was: "Ratify
ADR-0031: transition it from proposed to accepted with its content unchanged." Decision content is
unchanged from the reviewed proposal.

## Context

Issues #699 and #706 exposed one architectural defect through multiple routes: a generated Codex
workflow can name a canonical reviewer charter that is absent from the installed `ca-codex` package.
Repairing one missing file would leave direct and generic routes structurally unresolved. The package
must instead close every shipped route against one canonical governance source.

The repository already implements the shared kernel selected by ADR-0011. Host-neutral Python lives
in `core/pysrc/`, host-neutral surfaces in `core/surface/`, and host behavior in `core/hosts.json`.
`tools/sync-core.py` and `tools/build-surface.py` deterministically materialize independently
versioned host payloads. Runtime cross-plugin imports, symlinks, and shared installation roots were
rejected because they couple correctness to host marketplace layouts.

The prerequisite characterization is complete. CLI 0.143.0 and 0.145.0 plus app-server 0.143.0 and
0.145.0 passed the same tracked fixture in isolated homes. Each exposed the selected entry skill's
absolute installed path and completed exactly the three required contained reads without cache
search, glob fallback, network access, or mutable policy. The durable report records fixture SHA-256
`a7cb361b93992a3d1d64f87d77650db82847f8a8dc931a1bba01094a63068ec1` and evidence-contract
SHA-256 `d7fee53403b48b14ffc5dcf86acaebbff72944ecb25bd0ffbdf4aac11db1d302`.
This is backend evidence only: `desktop_shell_proven` remains false and release still requires exact
candidate proof in the real Windows desktop shell.

## Decision

**1. The existing generated source tree is the internal `ca-core` boundary.** `core/pysrc/`,
`core/surface/`, `core/hosts.json`, and their deterministic generators remain the single canonical
source of governance behavior. Claude and Codex are separate, independently versioned public adapter
packages generated from that source. No separately published or runtime `ca-core` package is
created. Pi may consume the same source for compatibility, but remains Forge-only rather than a peer
public release target under this campaign.

**2. `ARBITER_PLUGIN_ROOT` names a validated product abstraction, not a promised host variable.**
Canonical code, diagnostics, and product prose use `ARBITER_PLUGIN_ROOT` or `plugin_root()` for the
validated installed adapter root. Canonical Markdown continues to use `{{PLUGIN_ROOT}}`, which
`core/hosts.json` renders into host-native syntax. No adapter assumes that a host injects or
interpolates `ARBITER_PLUGIN_ROOT`.

Executable code derives its root from the executing file or module and treats ambient values only as
corroboration. Every signal is realpath-normalized and validated for containment, exact adapter
name/version, and the expected manifest or anchor. A mismatch fails closed and reports both paths;
an ambient value can never redirect execution into another valid-looking package tree.

The host contracts are:

- Claude content retains native `${CLAUDE_PLUGIN_ROOT}` interpolation. Claude hook subprocesses
  derive from `__file__` and require any native root value to match.
- Codex hooks render `${PLUGIN_ROOT}`, derive from `__file__`, and accept legacy
  `${CLAUDE_PLUGIN_ROOT}` only as a matching corroborating value.
- Codex ordinary skills use the absolute selected-entry `SKILL.md` path supplied by the skill loader,
  walk upward to the nearest `.codex-plugin/plugin.json` naming `ca-codex`, and resolve nested
  resources relative to the Markdown file that references them. They do not inspect hook-only
  environment state or search the plugin cache.
- Pi derives its package root from `import.meta.url` or the executing Python file. Any explicit
  adapter argument must realpath-match that root; Pi has no injected plugin-root contract.

**3. Codex ships all canonical agent charters as resources and dispatches through host-native
threads.** `tools/build-surface.py` generates `plugins/ca-codex/agents/INDEX.md` and all 18 canonical
charters from `core/surface/agents/`. Generated links are POSIX-style Markdown paths relative to the
output file containing the reference. The files are versioned resources, not native Codex custom
agent registrations, and `.codex-plugin/plugin.json` gains no unsupported `agents` key.

At dispatch, the workflow reads the named packaged charter, combines it with the concrete
assignment, creates a host-provided agent thread, and retains the thread identifier or receipt when
isolated evidence is required. Rendering removes Claude/Pi-only executable frontmatter while
preserving the charter body and host-neutral classification metadata.

Dispatch policy is generated, explicit, and fail-closed:

- Author roles use a write-capable worker only inside the assigned worktree and scope; required
  isolation blocks when unavailable.
- Reviewer and extractor roles are read-only, prefer an explorer-type thread where supported, and
  use host-enforced read-only containment when available. A workflow that requires isolated evidence
  blocks rather than silently falling back inline.
- Bounded writers and aggregators may write only their charter-declared output. All other mutation
  remains prohibited.
- Host type and model preferences are not permission boundaries. Unsupported Claude model labels are
  not translated into invented Codex tiers; an approved mapping is used or host-default degradation
  is recorded. Mandatory isolation and write containment cannot degrade to prompt-only guidance.

Every direct literal route, generic role route, template route, and generated index entry must resolve
inside the installed adapter. A missing charter, traversal, symlink escape, mismatched root, absent
manifest, contradictory command representation, or stale generated payload fails the relevant gate.

**4. Compatibility is bounded and removal is evidence-gated.** Codex's legacy
`CLAUDE_PLUGIN_ROOT` alias remains corroborating input through the next `ca-codex` minor release line.
It is never authoritative and is removed only in a separately announced later release after pinned
and advisory host evidence proves no supported host requires it. Claude's native token remains until
Claude publishes a replacement.

**5. Release evidence remains host-specific.** Backend characterization does not prove the Windows
desktop shell. The exact `ca-codex` candidate must pass an installed live-path desktop cell before
release, including package-root discovery, relative resource loading, and host dispatch. For this
campaign, authentication uses ChatGPT browser/device authorization within the user's included access;
API-key use, API-billed substitution, secret creation/export, or purchased infrastructure is not
authorized. If supported authentication, runner provenance, isolation, or the candidate itself is
unavailable, `ca-codex` release blocks rather than relabeling backend evidence as desktop proof.

**6. ADR-0011 is partially superseded, forward-only.** This ADR replaces only ADR-0011 Decision 5's
fallback that `ca-init` scaffold generated `.codex/agents/*.toml` plus doctor staleness checks when a
host cannot ship subagents. Codex instead receives packaged Markdown charters and host-native thread
dispatch under the policy above. ADR-0011's shared-core, build-time generation, independent SemVer,
parity-ledger, and no-runtime-coupling decisions remain in force.

## Alternatives considered

- **Publish a separate `ca-core` package** - rejected. It adds a fourth versioned release unit and
  cross-package coordination without closing a host route that the existing canonical source plus
  deterministic generators cannot close. A runtime package recreates the installation-layout
  coupling ADR-0011 rejected.
- **Scaffold `.codex/agents/*.toml` into every governed project** - rejected for this migration. It
  writes outside `.codearbiter/`, conflicts with user-owned agents, and creates upgrade, uninstall,
  provenance, and staleness obligations disconnected from plugin releases.
- **Translate each role into a hidden Codex skill** - rejected. Skills are not agent identities, the
  translation obscures internal routes, and dispatch policy is still required.
- **Package only the charter named by issue #699 or #706** - rejected. It repairs one symptom while
  leaving the generated package structurally open under other direct and generic routes.
- **Continue using Codex's Claude-named compatibility alias as the product root** - rejected as a
  permanent contract. Ordinary skill tool calls cannot rely on hook environment inheritance and a
  compatibility name cannot be the cross-host abstraction.
- **Require desktop-shell proof before this ADR** - rejected in favor of the completed backend-first
  branch. The separation is explicit: backend proof gates this decision; exact-candidate desktop
  proof gates release.

## Consequences

One canonical source continues to define governance behavior while Claude and Codex retain native
installation, syntax, packaging, SemVer, and release gates. The word `ca-core` can describe that
internal architectural boundary, but it does not become an installable or public package.

Codex gains complete packaged charter coverage without mutating governed repositories or claiming
native Markdown-agent registration. Generated relative links and a generated dispatch-policy index
become load-bearing outputs, so canonical source and generated payload must land atomically and both
generator `--check` gates remain required.

Host differences become explicit contracts instead of string substitutions. This increases the
number of matrix tests and release receipts, but makes root mismatches, unsupported isolation, model
degradation, and route gaps visible and fail-closed.

Pi may continue to reuse the internal source and its existing native package pipeline, but this
campaign does not promote Pi to the Claude/Codex public-release boundary.

## Risks

Codex may change selected-skill path or thread-dispatch behavior after the pinned backend versions.
Pinned minimum/known cells plus advisory-latest evidence must classify drift without coercing a new
failure into a pass.

Relative links can be correct in canonical source yet wrong after host-specific relocation. Generator
tests must validate every rendered output directory and installed-package route, not just source text.

Host-provided agent types and model defaults may not enforce every canonical role property. Any loss
of mandatory isolation or write containment blocks parity; optional model differences remain recorded
degradations rather than invented equivalence.

The internal kernel can still accumulate host conditionals until it ceases to be neutral. This
decision is proven wrong if adding or changing a host routinely requires runtime cross-package
coupling, duplicated governance behavior, or non-deterministic generation. That evidence reopens the
kernel boundary; preference for a separately named package does not.
