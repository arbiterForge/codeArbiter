# Hosted static ca-codex release contract

**Date:** 2026-08-31
**Status:** approved
**Approved by:** User, in the active campaign conversation
**Supersession scope:** Replaces only ADR-0031's mandatory actual-Windows desktop-shell release evidence. ADR-0031's canonical `core/` kernel, deterministic generators, separate Claude/Codex packages, host-native adapters, compatibility alias, and Forge-only Pi decisions remain unchanged.

## Problem

The current `ca-codex` release lane treats a protected Store/MSIX desktop exercise as mandatory evidence. That requirement pulled a self-hosted Windows runner, Hyper-V, a disposable VM, Microsoft ADK tooling, device authorization, protected-environment approval, a broker/driver/probe stack, attestations, and a durable desktop receipt into the publication path. It blocks the already prepared `ca-codex` 0.7.5 release even though the shipped object is a static Codex plugin bundle whose correctness is determined by its manifest, Markdown resources, generated surfaces, hook declarations, path graph, and deterministic package bytes.

The user has revoked all authority to use their personal PC as a repository runner or desktop-proof host and has rejected desktop installation as release evidence. The current mandatory desktop gate must be retired rather than bypassed or relabeled.

## Goal

Make `ca-codex` publication depend on a proportionate, GitHub-hosted, deterministic static-plugin contract, then publish the already prepared version and prove practical usability by updating the supported CodeArbiter marketplace installation used by Codex here and loading it in a fresh task.

## Approved architecture

### Required release evidence

The exact candidate built from the final release tree must pass all of the following using trusted repository code on GitHub-hosted runners:

1. `.codex-plugin/plugin.json` parses under the supported manifest schema and declares the expected name and version.
2. Every host-discoverable Markdown skill, routine, and agent resource has the required front matter for its resource class. Includes are ordinary linked Markdown fragments, so they are instead required to be UTF-8, contained in the package resource graph, and free of unresolved or escaping links.
3. Every declared or rendered resource reference resolves beneath the candidate plugin root; there are no missing resources, escaping paths, unresolved host tokens, or accidental absolute machine paths.
4. The Codex resource and route inventory is complete and agrees with canonical `core/` descriptors and deterministic generator output.
5. Hook declarations parse, reference shipped files, use approved host-root vocabulary, and preserve existing fail-closed enforcement contracts.
6. A clean rebuild from canonical source produces the expected managed outputs and deterministic candidate archive identity.
7. Release manifest version, changelog section, tag, GitHub Release, provenance record, and published archive identity agree exactly.
8. Existing hosted security, secret-scan, CodeQL, governance, and merge-readiness checks remain required where their impact selectors apply.

Candidate bytes selected by an event or release input are inert data. Verifier, packager, and publication code executes only from the trusted release tree selected by the governed workflow. Missing, malformed, ambiguous, or mismatched package evidence fails closed.

### Explicitly retired release evidence

The following are neither required nor admissible substitutes for the static contract:

- Store/MSIX desktop installation or UI automation;
- ChatGPT device authorization or any API credential;
- self-hosted GitHub runners or repository use of the user's personal PC;
- Hyper-V, VM images, virtual switches, ADK/BCDBoot, disposable Windows accounts, or UAC;
- the `codex-desktop-candidate` protected environment, workflow, broker, driver, probe, receipt, or attestation chain;
- screenshots, synthetic desktop receipts, or manual claims about desktop behavior.

The obsolete desktop workflow and its executable infrastructure are removed rather than left available as an attractive but unsupported release path. Historical ADRs, plans, reports, and immutable audit records remain intact and are superseded forward by the new decision record.

### Practical live check

After the governed tag and GitHub Release exist, update `ca-codex` through the supported CodeArbiter marketplace path at a safe task boundary. A fresh Codex task must read back the new version and selected plugin root. `$ca-doctor` must verify package ownership, manifest/resource completeness, hook enforcement, and its harmless live-fire route. This is a Codex plugin-load check, not a Windows desktop application install.

## Release behavior

- The pending release remains `ca-codex` 0.7.5 unless the implementation changes shipped `plugins/ca-codex/` payload bytes in a way that requires a successor version under the declared release contract.
- Release-infrastructure-only changes do not invent an empty plugin version bump.
- The automatic tag lane and manual GitHub Release lane both apply the same hosted static candidate contract.
- `ca-codex` remains in its own `ca-codex-v*` tag series and never takes the repository-wide Latest badge from `ca`.
- Merge, tag, GitHub Release, marketplace update, installed version, and fresh-task proof are recorded as distinct states.

## Acceptance criteria

- **AC-1:** No required workflow uses `self-hosted`, `codex-desktop-ephemeral`, a protected desktop environment, device authorization, UAC, Hyper-V, or the user's PC.
- **AC-2:** The desktop candidate workflow and executable broker/driver/probe/boundary assets are removed, and no active workflow, actionlint configuration, or release job references them.
- **AC-3:** A failing-first workflow contract proves `ca-codex` release no longer downloads or requires `codex-desktop-candidate-resolution.json`, a desktop transfer artifact, or desktop attestation.
- **AC-4:** A failing-first static-package contract proves malformed/missing plugin manifest fields, missing or malformed front matter, missing referenced resources, path escape, forbidden root vocabulary, generated drift, hook drift, and candidate digest mismatch each fail closed.
- **AC-5:** CI impact routing sends every static verifier, manifest, generator, hook, and `plugins/ca-codex/**` change to the required hosted resource lane and registers that lane in both aggregate wait and verdict mechanisms.
- **AC-6:** Manual and automatic `ca-codex` release paths execute verifier/packager code only from the trusted release tree and treat candidate bytes only as inert data.
- **AC-7:** Focused static-contract, release-workflow, CI-impact, generator, hook, and candidate-provenance suites pass, followed by the repository's required whole-branch hosted checks.
- **AC-8:** The exact reviewed PR head is merged only after required CI is green and every CodeRabbit thread is resolved in code or explicitly dispositioned.
- **AC-9:** The governed `ca-codex` tag and GitHub Release are created from the verified merged tree, with manifest, changelog, provenance, and deterministic archive identity in agreement.
- **AC-10:** The supported marketplace update selects the new `ca-codex` version; a fresh task loads it and `$ca-doctor` passes without desktop/MSIX installation, API billing, copied credentials, or machine/network changes.

## Repository surfaces

Expected active-code changes include:

- `.github/workflows/release.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/codex-desktop-candidate.yml` (remove)
- `.github/actionlint.yaml`
- `.github/desktop-proof-boundary.json` (remove)
- `.github/scripts/Invoke-CodeArbiterDesktopCandidate.ps1` (remove)
- `.github/scripts/Invoke-CodeArbiterDesktopUiDriver.ps1` (remove)
- `.github/scripts/Invoke-CodeArbiterDesktopRouteProbe.ps1` (remove)
- `.github/scripts/check_codex_skill_resources.py`
- `.github/scripts/verify_codex_candidate_provenance.py`
- the directly corresponding workflow/resource/provenance tests
- forward-only architecture and security-control records required to supersede the desktop evidence clause

Historical plans, accepted ADR text, prior reports, audit logs, and published release records are not rewritten.

## Constraints

- Preserve ADR-0031 outside the explicitly superseded desktop-proof clause.
- Preserve user-owned work by implementing from exact `origin/main` in the isolated `codex/hosted-static-codex-release` worktree.
- Do not weaken manifest, resource, hook, generator, provenance, security, or merge-readiness checks.
- Do not use API keys, copied sessions, billable API access, desktop/MSIX installation, self-hosted runners, UAC, Hyper-V, or network mutation.
- Do not publish Pi as a peer host package or create a runtime/public `ca-core` package.
- Do not claim publication or installation before direct evidence exists.

## Delivery authority

The user grants continuing merge authority for every campaign-scoped PR needed through parity `ca-codex` publication and supported local marketplace installation. Each merge still requires green required CI, every CodeRabbit review concern resolved in code or explicitly dispositioned against evidence, and verification that the reviewed head is the head being merged. The active campaign then authorizes the governed `ca-codex` release, marketplace update, fresh-task load, and `$ca-doctor` proof described above.
