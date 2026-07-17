# Pi promotion orchestrator and repository documentation contract

**Status:** approved; implementation plan recorded

## Purpose

Turn the advisory Pi `latest` canary into a controlled promotion path. A
compatible exact Pi release is validated across the supported platforms and
opens a normal reviewable promotion PR. An incompatible release remains a
high-signal red result with actionable evidence. No workflow accepts a moving
`latest` version as a production runtime.

At the same time, add one repository-wide documentation contract so a version
promotion cannot leave current documentation stale. This extends, rather than
replaces, the existing narrow plugin-reference, README-badge, generated-surface,
and docs-site checks.

## Implementation boundary

This feature's implementation changes are confined to `.github/**` plus this
governing specification. It must not edit concurrent core, adapter, generated,
or documentation work in the current branch. A successful future workflow may
create its own `automation/pi-<exact-version>` branch containing the declared
policy and documentation updates; that generated promotion branch is a separate
review lane, not a mutation made while building this CI feature.

## Decisions

- The candidate is the exact stable semver resolved from npm `latest` at the
  start of a run. Prereleases and malformed versions are rejected.
- The current support policy is a rolling two-version window: the capability
  floor and one exact last-live-verified release. Promotion replaces the latter;
  it does not make an open-ended version range valid.
- A green promotion run opens a normal PR but never merges, tags, or publishes.
  The existing release lane remains the only release authority.
- The promotion PR includes the independent `ca-pi` patch-version bump and a
  changelog entry because the supported runtime boundary changed.
- Promotion text updates are deterministic fact substitutions only. The
  automation does not use a model to rewrite explanatory prose.
- The repository documentation contract is required on every PR, including
  docs-only PRs. Historical evidence is checked for structure and links but is
  not rewritten to state current facts.

## Architecture

### Support policy and promotion worker

Add CI-owned fact extractors and binding configuration under `.github/` that
read the existing authoritative Pi compatibility policy, Node floor, package
metadata, and descriptor facts. The CI feature does not relocate or rewrite
those sources of truth. It detects disagreement between them and the CI matrix,
public Pi facts, and declared documentation bindings.

A trusted workflow, runnable by schedule and manual dispatch from default-branch
code only, performs the following sequence:

1. Resolve npm `latest` to an exact version and reject unsupported version
   shapes before making any policy change.
2. Install the candidate with `--ignore-scripts`; capture a bounded, redacted
   public API/help snapshot and compare it with the accepted baseline.
3. Run the candidate's adapter, trust, child-runner, doctor, security, and
   platform contracts on Linux, macOS, and Windows.
4. If every contract passes and no incompatible API/help delta is found, use the
   CI-owned promotion recipe to create an isolated branch named
   `automation/pi-<exact-version>` with the declared policy, deterministic
   documentation, artifact, fixture/fingerprint, package-version, and changelog
   updates.
5. Open a normal promotion PR. The PR runs normal CI independently and must
   clear merge readiness before a human decides whether to merge it.

The worker refuses to open a PR when the candidate is already supported, a
promotion PR for that exact version is open, the version is not strictly newer,
or any validation/API comparison fails. It must run only trusted repository code
and must not use `pull_request_target` or execute untrusted PR contents. Its
write token is limited to creating the automation branch and PR after all
validation jobs pass.

### Failure receipt

On a failed candidate, the workflow opens no PR. It writes a compact job summary
and a short-lived artifact containing only the exact candidate version, platform,
failed contract identifiers, and a bounded API/help delta. It must never include
environment values, provider credentials, prompts, or raw tool output.

The existing `latest` canary remains advisory. Its failure is a promotion signal,
not a merge-readiness failure for an ordinary PR.

### Repository documentation contract

Add an always-required CI job named:

```text
[CHECK] | [REPO] | Documentation contract
```

It is included in the `ci-passed` required-results list and invokes a repository
root documentation-contract checker. The checker owns an inventory that classifies
every tracked Markdown document; an unclassified document fails the check.

Each inventory entry is one of:

- **generated** — its committed bytes must match the owning generator;
- **current** — relative links and declared fact bindings must match current
  canonical facts, including the Pi support policy;
- **historical** — links and declared structure are checked, but the document
  is immutable evidence and never receives a current-version rewrite.

Promotion updates every declared current document that binds to Pi support facts.
The PR also runs the updater in check mode; if it would make an additional
deterministic documentation change, CI fails. Existing scoped documentation gates
remain in place as specialized checks.

## Rollout

Initially, the promotion workflow is manually dispatched while the existing
scheduled canary continues to collect evidence. After two clean promotion cycles,
scheduled promotion-PR creation may be enabled. The documentation contract itself
is required for every PR immediately once introduced.

## Acceptance criteria

1. A Pi candidate is promoted only as an exact stable version after clean
   three-platform validation; `latest` is never admitted directly.
2. A clean candidate opens one normal, non-merging promotion PR with an exact
   branch name, support-policy update, `ca-pi` patch bump, and changelog entry.
3. Duplicate, non-newer, prerelease, malformed, API-incompatible, or
   contract-failing candidates open no PR and emit a redacted receipt.
4. CI-owned fact extractors prove the adapter's admission boundary, doctor
   output, CI matrix, artifacts, and declared current docs agree with the
   existing authoritative support policy.
5. The documentation contract classifies every tracked Markdown file and runs
   as a required merge-readiness dependency on every PR.
6. Generated documentation drift, broken relative links, missing fact updates,
   and unclassified Markdown files fail the documentation-contract job.
7. Historical reports remain unmodified by promotion automation while retaining
   link/structure validation.
8. The promotion workflow uses only trusted default-branch code, scripts-disabled
   package installation, pinned actions, least-privilege PR creation permissions,
   and no `pull_request_target` execution path.

## Verification

Tests cover support-policy parsing, candidate-version rejection, API/help delta
classification, deterministic/idempotent updater behavior, no historical-document
rewrite, inventory completeness, fact-binding and link failures, promotion branch
deduplication, workflow trust/permission boundaries, and PR-creation conditions.
CI additionally proves the new documentation job is required by merge readiness.
