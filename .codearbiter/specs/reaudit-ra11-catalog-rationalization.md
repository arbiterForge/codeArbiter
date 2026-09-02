# Spec: RA-11 catalog rationalization

**Status:** APPROVED 2026-09-02 by the user's `checkpoint-009-ra11-catalog-rationalization` campaign instruction
**Lane:** `/ca:sprint` executing the `/ca:feature` compatibility-migration pipeline
**Slug:** `reaudit-ra11-catalog-rationalization`
**Authorized base:** `origin/main` at `4561dc219818032369f0985c787f7fccd8030770`
**Governs:** canonical command route metadata, command routing prose, deterministic host projections, public command discovery, compatibility policy, and their tests

## Problem

CodeArbiter ships one policy core to three host adapters, but its 38 command files are exposed with
nearly equal weight. Core work lanes, advanced operations, orchestrator protocols, compatibility
routes, and a retiring question shortcut are counted and marketed as one flat public catalog. The
source model cannot express those distinctions, generated host catalogs cannot project them,
and the documentation site still contains a stale hard-coded `40 commands` claim alongside the
actual 38-file inventory.

The defect is not that 38 route files exist. Compatibility routes are useful and must continue to
work. The defect is that users and generators cannot distinguish the supported day-to-day model
from advanced, internal, aliased, or deprecated surface area.

## Current-source rulings

The imported RA-11 ledger is claim data, not authority over current source. Reverification fixes the
following boundaries for this implementation:

1. ADR-0023 keeps third-party dependency governance at `add-dep`; this work does not invent a
   `dependency` top-level command or mislabel `add-dep` as an alias to a route that does not exist.
2. The campaign freezes new top-level public commands. Proposed `evidence`, `config`, `extend`, and
   `help` umbrellas therefore remain future product decisions, not synthetic replacement targets.
3. Task-archive ownership is unresolved in current project state. This work does not add archive
   behavior while rationalizing discovery.
4. Existing command files remain installed on every host where they are currently supported. A
   visibility change never means an implementation or route silently disappears.
5. The canonical advertised surface in this compatibility wave is 31 supported routes: 18 core
   lanes and 13 advanced operations. Five additional files become compatibility aliases, one is an
   internal protocol, and one remains available while deprecated.

## Metadata contract

`core/surface/command-routes.json` is the single canonical registry. It has one entry for every
command template under `core/surface/commands/`, keyed by the exact route slug. Each entry carries:

- `visibility`: exactly one of `core`, `advanced`, `internal`, `alias`, or `deprecated`.
- `workflow`: exactly one of `evaluate`, `initialize`, `change`, `review`, `decide`, `ship`,
  `operate`, `extend`, or `help`.
- `canonical`: the canonical top-level route slug. It equals the filename for `core`, `advanced`,
  and `internal` entries. For an `alias`, it names the existing canonical command that handles the
  route. A deprecated route without a command replacement may omit it.

Every alias additionally carries `replacement`, the full host-neutral route after the command
prefix, including its mode or option. The generator validates that the first token is an installed,
non-alias canonical command on every host that ships the alias. A canonical entry's `legacyRoutes` field
is a sorted inline list of the alias filenames that point to it; forward and reverse mappings must
close exactly. A canonical entry with aliases also carries a sorted `modes` inline list, and the
suffix of every replacement must equal one declared mode. The command body documents and executes
the same declared mode; metadata and prose cannot silently name different routes.

The deprecated `btw` route carries `replacement: ask the question directly`. Deprecated
replacements are explicit user guidance and are not falsely validated as command slugs.

Command templates keep their existing loader-facing frontmatter. Catalog-only fields never enter
executable Claude commands or Codex/Pi skills. Each host instead receives a generated
`generated/command-catalog.json` sidecar carrying metadata for the routes it installs. Human host
catalogs group the installed surface by visibility and workflow and report separate canonical,
alias, internal, and deprecated counts.

The `visibility: alias` value describes lifecycle/discovery compatibility. The reverse field is
named `legacyRoutes` so it cannot be confused with the existing same-slug host spelling aliases.

## Canonical discovery model

### Core lanes (18)

| Workflow | Commands |
|---|---|
| Evaluate | `preview` |
| Initialize | `init` |
| Change | `feature`, `sprint`, `fix`, `refactor`, `chore`, `spike`, `add-dep` |
| Review | `review` |
| Decide | `adr` |
| Ship | `commit`, `pr`, `release` |
| Operate | `status`, `task`, `doctor`, `override` |

### Advanced operations (13)

| Workflow | Commands |
|---|---|
| Change | `debug` |
| Review | `checkpoint`, `threat-model`, `tribunal` |
| Decide | `adr-status`, `reconcile` |
| Operate | `standup`, `audit`, `metrics`, `statusline`, `prune` |
| Extend | `new-skill` |
| Help | `commands` |

### Compatibility aliases (5)

| Existing route | Canonical replacement |
|---|---|
| `watch` | `pr --watch` |
| `cleanup` | `pr --cleanup` |
| `decompose` | `init --greenfield` |
| `create-context` | `init --brownfield` |
| `context-check` | `status drift` |

The `conflict` command is `internal`: direct intent may still route to it, but it is not marketed as
a user work lane. `btw` is `deprecated`: its installed route remains read-only and functional while
discovery tells users to ask the question directly.

## Compatibility behavior

Canonical wrappers add only the five named modes above. A legacy wrapper emits one concise migration
notice naming the canonical form, then continues to execute its own existing body with its original
arguments, owning skill, gates, output, and side effects intact. It does not invoke another host
command, recurse through a second wrapper, or substitute the new canonical-mode prose for its legacy
contract. The canonical mode independently routes to the same underlying workflow.

`pr --watch [target]` and `pr --cleanup` use flags so an existing optional PR title named `watch` or
`cleanup` still round-trips through the default PR path. The two flags are mutually exclusive;
`--cleanup` accepts no target or title. `init --greenfield` and `init --brownfield` are mutually
exclusive and cannot combine with `--check`; `--stage N` may accompany one only when scaffolding is
still absent. When a scaffolded-but-uninitialized stub already exists, the explicit strategy skips
the refusing scaffolder and enters the same old population workflow. An initialized marker or
source-shape mismatch retains the legacy strategy's BLOCK. Default `init` keeps its current
auto-detection behavior. Default `status` remains a no-skill, read-only snapshot; only explicit
`status drift` enters the old context-check workflow, whose re-scout/re-baseline writes still require
the user's explicit selection.

Published releases ca `2.16.0`, ca-codex `0.8.0`, and ca-pi `0.9.0` point to the pre-registry
baseline and do not contain this metadata. The clock begins only when each payload's first later
containing release is actually published; current source does not start it. The stable ca payload
retains every legacy route for the rest of the `2.x` major line and cannot remove one before `3.0.0`.
The pre-1.0 adapters
retain the routes for every later pre-1.0 release after the first containing release. ca-codex
therefore retains them through `0.8.x`, `0.9.x`, `0.10.x`, and later 0.x lines, with no removal
before `1.0.0`; ca-pi does the same from `0.9.x` through `0.10.x`, `0.11.x`, and later 0.x lines,
with no removal before `1.0.0`. Passing the floor never authorizes removal by itself: a future
removal still requires an explicit product decision, migration evidence, and its own governed change.

## Public discovery

- README keeps its role as a proof and routing surface. It shows the 18 core lanes grouped by user
  workflow, links to the complete generated reference, and does not duplicate a 38-row operator
  manual or use the raw route-file count as the product headline.
- The canonical and generated host catalogs retain every installed route but visually separate core,
  advanced, compatibility, internal, and deprecated entries. Alias rows name their replacement.
- The generated site reference uses the same canonical registry to group commands by visibility
  and workflow. Every installed command still has exactly one reference page and remains searchable.
- The landing trust row reports canonical lanes rather than raw command files, and the homepage's
  route card uses source-derived language instead of a hard-coded count.
- Existing authored guides may mention an old route while it is supported, but directly relevant
  discovery pages point to the canonical form and explain the compatibility alias where useful.

## Acceptance criteria

1. The route registry covers every command template exactly once with valid `visibility`, `workflow`,
   and applicable canonical/alias fields; malformed values, missing/extra routes, dangling targets,
   alias chains, and asymmetric alias lists fail the real surface generator with a path-specific error.
2. The verified taxonomy is exact: 18 core, 13 advanced, 5 aliases, 1 internal, and 1 deprecated
   command in the Claude source inventory. Host exclusions change installed totals, never the
   classification of a route.
3. Each of the five legacy aliases remains installed on every host that shipped it, preserves its
   existing body, argument contract, governing workflow, gates, output, and side effects, and emits
   one concise migration notice naming the host-native canonical form without cross-invoking it.
4. `pr --watch`, `pr --cleanup`, `init --greenfield`, `init --brownfield`, and `status drift` are
   additive executable modes of
   their canonical wrappers; each independently routes to the old route's owning workflow without
   making the compatibility route depend on cross-command dispatch.
5. `add-dep` remains a canonical core route in conformance with ADR-0023. No new top-level
   `dependency`, `evidence`, `config`, `extend`, or `help` command is added.
6. Claude, Codex, and Pi human catalogs agree with their installed command files and display separate
   visibility counts and workflow groups. Codex/Pi intentional exclusions remain unchanged.
7. Claude, Codex, and Pi generated command JSON sidecars carry the canonical metadata needed for
   host-native discovery, while executable command/skill frontmatter remains on its prior
   loader-facing schema; generator tests prove both contracts rather than grepping source text.
8. README exposes only the grouped core-lane chooser, retains host-difference links, removes the
   full raw command table and count-first badge/message, and routes advanced/compatibility lookup to
   the complete reference.
9. The generated site reference groups command discovery by visibility and workflow, includes every
   command exactly once, shows replacement guidance on alias/deprecated pages, and preserves command
   host-availability badges.
10. The landing page contains no hard-coded `38` or `40` command claim. Its trust signal derives the
    18 core-lane count from the canonical registry, and a malformed or duplicate taxonomy fails closed.
11. A committed compatibility policy declares the per-host retention floors and removal windows
    above, and states that only publication starts a window; no route is removed, release is cut, tag
    is created, package is published, or deployment is performed in this leg.
12. `build-surface --check`, core parity, host-package parity, command/reference checks, focused
    generator/site/Pi tests, and the repository's applicable whole-surface suites pass from the
    isolated worktree. Generated outputs are idempotent and the final branch is clean.
13. An independent architecture/compatibility review and an independent final diff review report no
    unresolved CRITICAL/HIGH findings; secrets, provenance, documentation, and anti-slop checks pass.

## Out of scope

- New top-level commands or speculative umbrellas.
- Task archive semantics, skill/agent renames, agent-role consolidation, or security-reviewer role
  overlap.
- Unrelated RA findings, backlog items, release notes for a release not being cut, or tracker edits.
- Removing any command file or host route.
- Push, pull request creation, merge, release, tag, publication, installation, deployment, or live
  production proof.

## Negative-space check

If every criterion passes and nothing else changes, no RA-11 user-visible defect remains in this
authorized compatibility wave: the supported model is discoverable, old routes work, projections
agree, and removal is governed. The imported proposals for additional umbrellas and task archive
behavior remain deliberately unimplemented because current source either rejects them or requires a
separate product decision.

## Open questions

None blocking. Future alias removal and any new umbrella command require a new approved spec; this
document does not pre-authorize them.
