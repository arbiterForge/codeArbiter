---
status: proposed
date: 2026-09-25
title: Release each plugin independently on merge with consumer-safety-only publication gates
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0039-publish-ca-codex-qualified-packages-to-npm
governs: .github/workflows/release.yml, .github/actions/publish-target/*, .github/scripts/release_target.py, .github/scripts/_npm_publishlib.py, tools/promote-claude-marketplace.py, tools/promote-codex-marketplace.py, tools/build-host-packages.py, .claude-plugin/marketplace.json
---

# ADR-0040 — Release each plugin independently on merge with consumer-safety-only publication gates

## Status
Proposed

## Context
Between 2026-09-06 and 2026-09-25 about 57 of roughly 80 `release.yml` runs failed. Almost none
caught a defective package. They failed on the pipeline's own bookkeeping — the cross-plugin
publication cohort, its resume/continuation path and repair allowlist, supersession of historical
cohorts, draft markers — or on publish code that could only execute after merge. A single partial
cohort (ca-codex 0.13.16 left as a Draft, ca-pi 0.14.15 never published) blocked every later merge
and could only be cleared by bumping all three plugins at once.

Separately, a normal Claude Code install (`/plugin install ca@codearbiter` from main) received no
native artifact engine, because `helpers/artifacts/` is never committed to main. With typed HTML
specs/plans on by default, every new full-lane `/ca:feature` on a normal install stopped with
`CAPABILITY_MISSING`.

The user decided, on 2026-09-25, to loosen the gates the pipeline could not meet, ship the engine
to every host, and release on every merge.

## Decision
1. **Independent, idempotent per-plugin release.** When `ci` succeeds for a main push, each of ca,
   ca-codex, ca-pi and ca-sandbox whose manifest advanced (or whose own tag exists but whose Release
   is not published) releases in its own job. No job depends on another plugin's job. There is no
   cohort, resume/continuation state, repair allowlist or supersession logic. Every publish step
   observes the remote first and does only what is missing; re-running the job (or dispatching the
   workflow for that target) is the recovery path.
2. **Claude Code receives the engine through a Git distribution channel.** The qualified release
   archive is published as an orphan `ca-dist-v<version>` tag and the `ca-marketplace` branch is
   advanced to it. Main's `.claude-plugin/marketplace.json` points `ca` at that branch with a
   `git-subdir` source, so existing installs migrate on their next update.
3. **Codex npm publication is deferred.** Codex stays on the working Git channel
   (`ca-codex-marketplace` pinning an immutable `ca-codex-dist-v*` tag). This supersedes ADR-0039's
   npm channel until a later ADR resumes it; the npm tooling remains in the tree, dormant. The user
   wants npm in the future and functional releases now.
4. **Hard gates only where they protect consumers:** manifest = tag = CHANGELOG version; the CI
   package cohort verifies (member digests and the cold-install receipt matrix); an existing tag must
   name the release commit (otherwise the version is spent — bump and merge again); published bytes
   read back exactly (Release asset digest, npm integrity). Provenance extras — npm attestation and
   signature verification, the Codex ruleset audit, and the release-skill pre-tag proof — warn and do
   not block. The published-tag ledger check (`check_tag_immutability.py --require-recorded`) is
   unchanged by this decision.

## Alternatives considered
- **Keep the cohort and fix its resume path** — keeps the class of failure that recurred all month;
  each fix to the publisher disqualified the in-flight resume.
- **Commit the native binaries to main** — simplest install, but permanently grows main's history
  with platform binaries on every engine change.
- **Download the engine on first use** — needs network at first use and adds a new download trust
  surface.
- **Finish Codex npm now** — more moving parts in the release path while releases are broken.

## Consequences
- One plugin's failure no longer blocks the others or future merges; a stuck release is fixed by a
  re-run or, for a spent version, a bump.
- Claude Code and Codex users receive the engine from Git distribution refs; Pi from npm. A main
  checkout never carries it, and the `CAPABILITY_MISSING` diagnostic names the concrete repair.
- Provenance evidence is still collected and reported, but a provenance-only failure no longer stops
  a release.
- The first release after this lands must create `ca-marketplace`; until it exists, Claude installs
  that refresh the catalog cannot resolve `ca`.

## Risks
- A provenance regression can ship unnoticed except as a warning; watch release logs.
- Independent plugins can briefly sit at mixed versions across hosts.
- If Claude Code does not re-resolve a moving `git-subdir` ref on update, users stay on an older
  cached version; verify with a real `/plugin update` after the first release.
- Proven wrong if releases keep failing on merge for reasons other than consumer safety.
