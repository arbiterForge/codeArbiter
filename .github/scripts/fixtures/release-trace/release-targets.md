# Resolution-trace fixture — frozen declared-target rows

A-1.11 (T-27a): a FROZEN, self-contained copy in the declared-target grammar
— deliberately separate from this repository's own
`.codearbiter/release-targets.md`, so the trace stays stable even if that
file changes shape later. Paths are relative to this fixture directory, not
the repository root.

<!-- release-targets -->
[ca]
prefix: v
manifest: manifests/ca-plugin.json
changelog: CHANGELOG.md
payload: ca/
artifacts: ca/tools/farm.js
provenance-manifest: published-tags.json
latest-eligible: true

[ca-codex]
prefix: ca-codex-v
manifest: manifests/ca-codex-plugin.json
changelog: ca-codex/CHANGELOG.md
payload: ca-codex/
provenance-manifest: published-tags.json
latest-eligible: false

[ca-sandbox]
prefix: ca-sandbox-v
manifest: manifests/ca-sandbox-plugin.json
changelog: ca-sandbox/CHANGELOG.md
payload: ca-sandbox/
artifacts: ca-sandbox/tools/sandbox.js
artifacts: ca-sandbox/tools/claude-inside.js
provenance-manifest: published-tags.json
latest-eligible: false

[ca-pi]
prefix: ca-pi-v
manifest: manifests/ca-pi-package.json
manifest: manifests/ca-pi-root-package.json
changelog: ca-pi/CHANGELOG.md
payload: ca-pi/
payload-exclude: ca-pi/tools/
artifacts: ca-pi/extensions/codearbiter.js
artifacts: ca-pi/extensions/codearbiter-child.js
provenance-manifest: published-tags.json
latest-eligible: false
<!-- /release-targets -->
