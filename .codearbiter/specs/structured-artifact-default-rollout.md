# Structured-artifact default rollout

## Problem

The specs/plans structured-artifact engine is merged but remains an explicit
pilot, so ordinary feature and sprint work still creates Markdown authorities
and normal release packages do not provide the verified native payload needed
to make typed HTML reliable by default.

The callers are codeArbiter users starting or resuming feature and sprint work
through the Claude, Codex, and Pi governance hosts. Done means a normal released
installation creates and operates on a typed HTML specification/plan pair by
default, while legacy repositories remain safe and usable.

## Approach

Complete the original rollout checkpoint rather than flipping its documentation
or inventory booleans early. Close the actual consumer, authority, packaging,
release, browser/accessibility, resume, and rollback paths under the existing
engine contract in one PR. The default change is the final implementation slice
of that PR and cannot land without its package payloads and exact-head
qualification. Exact published-package read-back necessarily follows merge; it
is a release-completion gate, and full rollout readiness is not asserted until
all three published packages pass it.

The rejected shortcut is changing the default guidance before qualified payloads
ship and before every authoritative consumer understands HTML. That would turn
missing integration into user-visible workflow failures and would contradict
ADR-0037's rollout precondition.

## Scope

In scope:

- Make typed HTML the default canonical representation for newly created feature
  and sprint specification/plan pairs on all three governance hosts.
- Ship installation-owned, provenance-bound native engine payloads through every
  normal release channel that enables the default.
- Close every live default-path consumer: producer, reader, discovery,
  diagnostic, commit, execution, finalization, worktree, resume, and acceptance.
- Qualify host authority mapping, cold install, upgrade, interruption/resume,
  selected production-repository use, rollback, native browser rendering, and
  accessibility before activation.
- Keep legacy Markdown pairs readable and authoritative until an explicit,
  reviewed pair migration succeeds.

Out of scope:

- Enabling or promoting the `--farm` backend; CONFIRM-05 and its fresh-model
  qualification remain separate.
- Automatic or repository-wide conversion of existing Markdown artifacts.
- Migrating task boards, tickets, decomposition documents, ADRs, or any other
  future ADR-0037 artifact kind.
- Adding a public command, agent, persistent tool, top-level skill, runtime
  plugin loader, database, or eagerly loaded schema surface.
- Claiming support for network filesystems, physical-power-loss behavior, or any
  platform cell not explicitly qualified and advertised.

## Decided parameters

- “Default enabled” means new feature/sprint pairs are HTML; it does not rewrite
  existing Markdown pairs.
- A repository with an existing authoritative pair resumes that pair's format.
- A missing, mismatched, or unqualified payload blocks new HTML work with an
  actionable capability error; it never silently creates Markdown instead.
- Legacy-only work that does not require a new HTML artifact remains usable on a
  partial installation.
- Payload packaging, consumer closure, qualification, and default activation
  ship in one PR and one declared Claude/Codex/Pi release cohort. Before merge,
  the exact PR head must assemble and cold-install the package bytes for every
  host/platform from native-qualified candidates. After merge, each exact
  published package must be installed and read back before the rollout is
  called complete. This post-merge evidence ordering is an explicit deviation
  from ADR-0037's requirement that release obligations be qualified before a
  supported kind becomes default-enabled, and from the stronger payload-first
  two-release design. The user approved this bounded ordering to avoid another
  long-lived conflict-prone branch; it does not permit a readiness claim before
  the published-package read-back receipts pass.
- Independent package publications cannot be transactional. A mixed-version
  host fails closed on HTML work instead of silently changing its authority
  format, and a failed publication/read-back triggers the documented rollout
  stop and rollback path rather than a readiness claim.
- Release-generated native bytes cannot be present in repository-directory or
  Git-tag installs without committing platform binaries. Because committed
  native binaries are outside this contract, the qualified Claude and Codex
  channels are immutable, source-commit-bound release package archives consumed
  through each host's supported local-package installation path; their existing
  repository-directory installs remain supported partial installations and fail
  closed for HTML work. Pi's qualified channel is the exact preassembled npm
  tarball. This channel distinction records an implementation constraint; it
  does not weaken the requirement that every channel advertised as qualified
  contain and read back the exact promoted payload. This is an explicit
  deviation from ADR-0029's same-repo-root-package invariant for the pinned Git
  and npm Pi channels: the Git-tag package remains a supported partial install,
  while the preassembled npm tarball is the qualified Pi package.
- The supported native matrix is descriptor- and evidence-owned, not inferred
  from cross-compilation or from every filename the builder can produce.
- HTML farm projection remains guarded and disabled independently of ordinary
  premium-path HTML authoring and execution.
- Canonical shared sources remain under `core/`; generated host copies are never
  hand-edited.

## One-PR delivery boundary

The PR is ordered so consumer/package work and its tests land before the default
selection change. Its exact head must prove assembled-package cold install,
installed-host workflow, native browser/accessibility behavior, the selected
production pilot, rollback, generated parity, and required CI. Branch artifacts
are not represented as published evidence.

Merge authorizes the release cohort, not a claim that publication succeeded.
The release workflow must retain immutable per-host publication/read-back
receipts. Until all three receipts pass, the disposition is “merged; rollout
qualification incomplete.” A failure stops further publication or dispatch as
applicable and invokes the rollback procedure.

## Acceptance criteria

1. **Default pair creation.** Given a clean initialized repository and a normal
   qualified installation of any governance host, starting a new feature or
   sprint creates a validated `.codearbiter/specs/<slug>.html` and
   `.codearbiter/plans/<slug>.html` pair through the installed engine, and creates
   no Markdown authority for that pair.
2. **Legacy authority isolation.** Given an existing Markdown spec/plan pair,
   resume, proof, finalization, and worktree planning continue to use that exact
   pair without automatic conversion; an explicit reviewed migration is the only
   operation that can replace its authority with HTML.
3. **Partial-install failure boundary.** Given no payload, a corrupt payload, an
   unsupported advertised cell, or a manifest/binary identity mismatch, new HTML
   creation and existing HTML mutation fail before writing with a bounded repair
   diagnostic, while an unrelated existing Markdown workflow remains usable.
4. **Release-owned payload.** The exact PR head assembles and cold-installs every
   qualified Claude/Codex release archive and Pi npm tarball only from
   native-qualified candidates bound to that
   commit, protected CI workflow/run identity, platform, manifest, binary digest,
   and named test receipts; missing, extra, stale, cross-commit, or unqualified
   candidates block merge or publication. After merge, each exact published
   cohort package is installed and read back against those identities before
   full rollout readiness is asserted.
5. **Complete consumer closure.** The authoritative consumer inventory and an
   independent repository search agree that every live spec/plan producer and
   reader on the default path is either HTML-capable or explicitly legacy-only,
   with no pending/default-path closure classification and no untracked public or
   startup-loaded surface.
6. **Authority fidelity.** User, SMARTS, reviewer, task-state, verification, and
   acceptance transitions consumed by the HTML path are derived from the existing
   host authority boundaries and exact artifact identities; document text,
   checkboxes, status words, digests, or caller-supplied labels cannot manufacture
   or widen authority.
7. **Installed-host workflow and resume.** A clean installed-host run completes
   spec creation, plan binding, task start, interruption, process recreation,
   reconciliation, redispatch, verification, review, atomic acceptance, commit
   proof, and finalization against one HTML pair without reading a shadow Markdown
   ledger or relying on repository/PATH/Go/network fallback.
8. **Human review qualification.** Exact generated HTML bytes pass the declared
   native browser matrix for desktop, compact, print, doubled text, keyboard/focus,
   overflow, local-only loading, and automated accessibility checks; unsupported
   browser or accessibility claims remain explicit rather than inferred.
9. **Rollback and upgrade safety.** The selected production-repository pilot
   demonstrates clean install or upgrade, normal HTML work, interruption-safe
   recovery, rollback that stops new dispatch, and exact preservation of evidence
   and prior legacy bytes; downgrade alone never reinterprets HTML as Markdown.
10. **Activation and surface guard.** The one-PR activation change is rejected
    unless every pre-publication portion of criteria 1–9 and required exact-head
    CI are current and green and the post-merge publication-evidence deviation
    has formal rollout acceptance. Generated parity holds, the public
    command/agent/tool/top-level skill/startup-schema baselines do not grow, and
    `--farm` remains disabled. Merge alone is not a full-readiness assertion:
    exact published-package read-back for all three hosts closes the rollout,
    while any failure records a blocker and activates the stop/rollback path.

## Open questions

None. CONFIRM-05 remains open for the out-of-scope farm backend and does not
block premium-path structured-artifact rollout work.

**Governs:** core/artifacts/**, core/pysrc/_artifactlib.py, core/pysrc/_readinjectlib.py, core/pysrc/_intentlib.py, core/surface/**, tools/build-artifacts.py, tools/build-host-packages.py, tools/install-artifact-payload.py, .github/workflows/ci.yml, .github/workflows/release.yml, .github/actions/publish-release/**, .github/scripts/test_artifact_*.py, docs/artifacts/**
