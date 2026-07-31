# Release targets — codeArbiter (this repository)

Declared-target-file for the portable `/ca:release` lane (issue #563,
`.codearbiter/specs/release-portable-fixture.md`). Parsed by
`load_targets()` / `parse_release_targets()` (`core/pysrc/_releaselib.py`,
vendored byte-identically into every governance plugin's `hooks/` directory)
per the spec's "File grammar" and "Parser contract" sections, which are
authoritative over this file's shape.

Four rows, one per shipped plugin (the four rows the pre-rewrite
`plugins/ca/skills/release/SKILL.md` used to hardcode as a Targets table,
before T-41a replaced that table with this declared file and a loader).
Every row declares
`provenance-manifest: .github/published-tags.json` (maintainer decision,
2026-07-31): an absent field silently skips the tag-provenance recording
step, and all four of this repository's release lanes record provenance.

Only `ca` is `latest-eligible` — one repo-wide "Latest" badge across four
release series; a sibling claiming it would hide `ca`'s current release from
every visitor.

`ca-pi` has **two** manifests — the plugin's own `plugins/ca-pi/package.json`
plus the GENERATED repo-root `package.json` Pi actually installs — and its
payload **excludes** `tools/`, which ships neither generated policy nor a
built runtime artifact under `extensions/`. The root `package.json` is never
hand-edited: it is declared in `generated-manifest`, and its paired
`generate` command (`tools/build-host-packages.py`) is what the release
skill runs to regenerate it before asserting it equals the derived version —
the same trap the pre-change skill only stated in prose (HIGH-3, adversarial
review 2026-07-31), now declarable rather than folklore a consumer had no
way to express. The `pre-tag: ... --check` entry is the belt to that
suspenders: a non-mutating verify that also catches drift introduced any
other way.

This file's `pre-tag` entries — and, as of HIGH-3, `ca-pi`'s `generate`
entry — are operator-authored executable input that a `contents: write`
release lane later runs, which is why it is a *declared* candidate for the
H-22 protected-state registry
(`.codearbiter/security-controls.md`, "Protected-state registry"). **It is
NOT protected yet** — the registry ships EMPTY as of this slice, and this
file's own enrolment is tracked, PENDING, as task T-33
(`.codearbiter/plans/portable-release-and-protected-state.md`). Until T-33
lands, this file sits on disk with no marker-gated write protection, same as
any other file (M-1, adversarial review 2026-07-31).

<!-- release-targets -->
[ca]
prefix: v
display-name: codeArbiter
manifest: plugins/ca/.claude-plugin/plugin.json
changelog: CHANGELOG.md
payload: plugins/ca/
rebuild: cd plugins/ca/tools && npm run build
artifacts: plugins/ca/tools/farm.js
provenance-manifest: .github/published-tags.json
latest-eligible: true
pre-tag: python3 .github/scripts/check_badge_consistency.py
pre-tag: python3 .github/scripts/check_command_catalog.py
pre-tag: python3 .github/scripts/check_skill_proof_fresh.py

[ca-codex]
prefix: ca-codex-v
manifest: plugins/ca-codex/.codex-plugin/plugin.json
changelog: plugins/ca-codex/CHANGELOG.md
payload: plugins/ca-codex/
provenance-manifest: .github/published-tags.json
latest-eligible: false

[ca-sandbox]
prefix: ca-sandbox-v
manifest: plugins/ca-sandbox/.claude-plugin/plugin.json
changelog: plugins/ca-sandbox/CHANGELOG.md
payload: plugins/ca-sandbox/
rebuild: cd plugins/ca-sandbox/tools && npm run build
artifacts: plugins/ca-sandbox/tools/sandbox.js
artifacts: plugins/ca-sandbox/tools/claude-inside.js
provenance-manifest: .github/published-tags.json
latest-eligible: false

[ca-pi]
prefix: ca-pi-v
manifest: plugins/ca-pi/package.json
manifest: package.json
generated-manifest: package.json
generate: python3 tools/build-host-packages.py
changelog: plugins/ca-pi/CHANGELOG.md
payload: plugins/ca-pi/
payload-exclude: plugins/ca-pi/tools/
rebuild: cd plugins/ca-pi/tools && node build.mjs
artifacts: plugins/ca-pi/extensions/codearbiter.js
artifacts: plugins/ca-pi/extensions/codearbiter-child.js
provenance-manifest: .github/published-tags.json
latest-eligible: false
pre-tag: python3 tools/build-host-packages.py --check
<!-- /release-targets -->
