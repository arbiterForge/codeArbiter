# Codex Documentation Launch Design

## Objective

Announce Codex as a first-class codeArbiter host across the repository README and documentation
site using the precise public claim **“shared enforcement and project-context parity across Claude
Code and Codex.”** Every public claim must be traceable to the verified Codex 0.144.1 / ca-codex
0.2.4 evidence, while intentional host-specific differences remain visible and unambiguous.

## Audience and outcome

The launch serves three readers:

1. A new Codex user must be able to install `ca-codex`, approve its hooks, opt a repository in, and
   verify enforcement without reading Claude-only instructions.
2. An existing Claude Code user must understand that the same checked-in `.codearbiter/` state can
   be used by Codex, including simultaneous or alternating use by two people.
3. A maintainer or evaluator must be able to inspect the evidence behind “parity” and see exactly
   which host differences are intentional rather than hidden failures.

## Claim hierarchy

Public copy uses three levels of specificity:

- **Headline:** “Shared enforcement and project-context parity across Claude Code and Codex.”
- **Short proof:** trusted SessionStart persona injection and a live `[H-03]` PreToolUse block on
  Codex 0.144.1, using ca-codex 0.2.4.
- **Evidence packet:** static adapter and guard suites, cold-install matrix, deterministic shared
  surface generation, byte-identical vendored hook core, and dual-host shared-store/concurrent audit
  tests, with links to the checked-in parity ledger and live testing procedure.

The documentation must not claim that every host UI or optional feature is identical. In
particular, Claude Code’s statusline and transcript-pruning engine remain host-specific. Those
differences do not weaken the shared enforcement and project-context claim and must be labeled as
intentional differences wherever they affect user instructions.

## Information architecture

### Repository README

The README becomes host-neutral at the top:

- hero and badges name both Claude Code and Codex;
- the opening definition describes two sibling plugins over one project-state store;
- installation presents separate Claude Code and Codex tabs/sections;
- activation and command examples show `/ca:*` for Claude and `$ca-*` for Codex;
- the architecture section explains that both hosts read and enforce the same `.codearbiter/`;
- a concise evidence callout links to the site’s canonical support page and repository parity ledger;
- Claude-only statusline copy is labeled rather than generalized.

The existing long command catalog remains primarily the Claude spelling reference, with a clear
note pointing Codex users to its generated `$ca-*` catalog rather than duplicating 37 rows.

### Documentation site

Add a curated **Claude Code + Codex** support page under Getting Started. It owns:

- the parity claim and scope;
- the tested version table;
- the live verification record;
- static and CI evidence;
- the shared-store/two-user model;
- the intentional-differences matrix;
- links to install, quickstart, compatibility, enforcement, troubleshooting, and the repository
  evidence files.

Update the following existing pages so no primary journey remains Claude-only:

- landing page and global site description;
- overview;
- install;
- quickstart;
- compatibility;
- enforcement and hooks explanation;
- repository opt-in guide;
- FAQ;
- troubleshooting;
- uninstalling;
- site changelog.

Generated command/skill/agent reference pages remain generated from their canonical sources. The
launch does not hand-edit generated reference content or pretend Codex ships Claude-only agents.

### Canonical technical evidence

`docs/parity.md` remains the detailed parity ledger and `docs/codex-parity-testing.md` remains the
reproduction procedure. The new site page summarizes and links to both. README and other site pages
link to the new page instead of copying the full evidence packet.

## Host-specific instruction rules

Every operational instruction must identify its host when syntax differs:

| Action | Claude Code | Codex |
|---|---|---|
| Install | `/plugin marketplace add arbiterForge/codeArbiter`, `/plugin install ca@codearbiter` | After publication: `codex plugin marketplace add arbiterForge/codeArbiter`, `codex plugin add ca-codex@codearbiter` |
| Command | `/ca:<name>` | `$ca-<name>` |
| Initialize | `/ca:init` | `$ca-init` |
| Verify | `/ca:doctor` | `$ca-doctor` plus `/hooks` review |
| Uninstall | `/plugin uninstall ca@codearbiter` | `codex plugin remove ca-codex@codearbiter` |

Instructions may share prose only when the actual operation is identical. The common project store
is always `.codearbiter/` at the repository root.

## Publication sequencing

The Codex GitHub-slug marketplace flow cannot pass before this branch is published: on 2026-07-12,
Codex 0.144.1 successfully cloned `arbiterForge/codeArbiter` and registered marketplace
`codearbiter`, but `codex plugin add ca-codex@codearbiter` reported that the plugin was not found
because the repository's current default branch does not yet contain the Codex marketplace entry.

Until the Codex payload reaches the public default branch:

- public pages must label the GitHub-slug commands **available after the Codex-support release**;
- development verification must use the documented local-clone marketplace flow;
- the site announcement must not be published as a currently installable release.

After the support branch is published, but before the announcement site is deployed, run the exact
GitHub-slug marketplace add, plugin add, plugin list/version inspection, plugin remove, and final
plugin-list absence sequence on Codex 0.144.1 in a clean `CODEX_HOME`. A failure blocks publication;
on success, remove the pre-release label and record the command output/date in the support page.

## Evidence presentation

The support page will distinguish:

- **Live verified:** Codex 0.144.1, ca-codex 0.2.4, Windows; trusted SessionStart injection;
  `$ca-doctor` static result of 9 OK / 0 WARN / 0 FAIL; live H-03 block with feedback surfaced.
- **CI verified:** package schema baseline; adapter tests; guard matrix; cold-install matrix;
  generator drift; shared-core byte identity; dual-host store and append-only concurrent audit test.
- **Intentional differences:** statusline, transcript pruning, no Codex Read hook, command spelling,
  and host-native plugin installation/trust flows.

Exact test counts may be presented only alongside their command or evidence source so later count
changes do not masquerade as reduced coverage. The stable claim is that the named suites pass.

## Anti-drift verification

Site tests will assert that:

- the landing page and metadata name Claude Code and Codex;
- the canonical support page exists in the Getting Started navigation;
- both installation paths and both doctor spellings are present;
- the verified Codex and plugin versions are stated;
- the support page links to the parity ledger and live-testing procedure;
- the compatibility page no longer claims Claude Code is the only supported host;
- statusline and transcript pruning are not represented as Codex-parity features.

The existing site typecheck, generator tests, build, and link audit must pass. The repository’s
Codex validator, adapter suite, guard matrix, cold-install matrix, dual-host tests, generated-surface
check, and vendored-core check remain required evidence for the launch commit.

## Scope boundaries

This documentation launch does not:

- change runtime behavior or expand the verified parity boundary;
- claim identical UI or every optional feature across hosts;
- publish the site, push the branch, or create a release without separate authorization;
- rewrite generated reference pages by hand;
- add speculative support for a third host.

## Acceptance criteria

1. A reader can identify both supported hosts from the README hero and site landing page.
2. A Codex-only reader can complete install, trust review, initialization, and doctor verification
   using only public docs.
3. A mixed Claude/Codex team can understand that both hosts share and enforce one `.codearbiter/`
   store in the same repository.
4. Every parity claim points to the canonical support page or checked-in evidence.
5. Intentional host differences are visible wherever they affect expectations or commands.
6. README, site tests, site generation/typecheck/build/link audit, and all named Codex parity suites
   pass with no generated drift.
7. Before site publication, a clean Codex 0.144.1 home completes the public GitHub-slug marketplace
   add/install/inspect/remove flow after the Codex payload is present on the public default branch.
