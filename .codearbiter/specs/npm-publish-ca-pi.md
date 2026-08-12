# npm publishing for ca-pi

**Governs:** .github/workflows/npm-publish.yml, tools/build-host-packages.py

**Status:** APPROVED 2026-08-09 by the repository owner

**Origin:** user directive 2026-08-09 ("i'd like to start publishing to NPM in the arbiterforge
organization"; ADR approved by the user mid-session: "adr for change to publishing route approved").
The org actions secret `NPMJS_TOKEN` exists; the raw token was never ingested.

## Problem

ca-pi's only distribution path is a pinned Git tag (`pi install git:github.com/arbiterForge/
codeArbiter@ca-pi-v<version>`), while Pi's native package channel is npm (`pi install npm:<name>`).
Users who discover Pi extensions through npm cannot find or install ca-pi, and every install
instruction carries the full Git coordinates. Done = each `ca-pi-v*` release is also published to
npm under the arbiterforge org by CI, installable as `pi install npm:@arbiterforge/ca-pi`.

## Approach

Publish the existing repo-root Git package to npm unchanged in layout: extend the
`build-host-packages.py` generator (the single source of the root manifest) with the npm publishing
fields, and add one tag-triggered workflow that publishes with provenance. This is the only sane
approach: the root `package.json` + `plugins/ca-pi/**` payload IS the Pi package Pi already loads
from a Git install, so the npm tarball must be that same shape — a separate npm-specific package
would fork the payload ADR-0011 exists to keep single-sourced. Trade-off accepted: the npm package
page shows the monorepo README (v1 accepts this; a package-specific README is future polish).

## Scope

- Generator emits a publishable root manifest: scoped name, no private flag, publishConfig,
  files whitelist.
- One new workflow publishing on `ca-pi-v*` tags with npm provenance.
- Documentation posture flip (tech-stack, coding-standards, docs/parity.md, docs/pi-parity-testing.md)
  and the doc-contract tests that pin the old posture.
- ADR recording the distribution-route change with user attribution.

**Out of scope:** publishing `ca`, `ca-codex`, or `ca-sandbox` to npm (their hosts install from
marketplaces, not npm); removing or demoting the pinned-Git install path (it remains the
reproducible-pin channel); a package-specific README; automated unpublish/deprecation tooling;
executing the first publish (rides the next `ca-pi-v*` tag, or a manual dispatch after merge).

## Decided parameters

- Package name: `@arbiterforge/ca-pi` in the generated root manifest AND the nested
  `plugins/ca-pi/package.json` (the two stay name-synchronized; the org scope matches the token's
  org and avoids unscoped-name squatting).
- The nested manifest keeps `"private": true` (it is never the publish unit; the flag guards an
  accidental publish from that directory). The generated root manifest drops `private` and gains
  `"publishConfig": { "access": "public", "provenance": true }` plus
  `"repository": { "type": "git", "url": "git+https://github.com/arbiterForge/codeArbiter.git" }`
  — npm provenance validates the manifest's repository against the CI origin and refuses to
  publish without a matching field.
- Tarball contents via root `files` whitelist: `plugins/ca-pi/extensions/`, `skills/`, `generated/`,
  `helpers/`, `hooks/`, `includes/`, `agents/`, `routines/`, and `plugins/ca-pi/*.md` (SKILLS.md is
  the catalog); LICENSE rides automatically. `plugins/ca-pi/tools/**` (dev workspace), `plugins/ca*`
  siblings, `core/`, `site/`, `.github/`, `.codearbiter/` are excluded.
- Workflow: new `.github/workflows/npm-publish.yml`, triggered by `push: tags: ["ca-pi-v*"]` plus
  `workflow_dispatch` (tag input) for re-runs/backfill; `permissions: contents: read,
  id-token: write`; actions pinned by 40-hex SHA (repo contract); Node 22.19+ via setup-node with
  `registry-url: https://registry.npmjs.org`.
- Version guard in the workflow: the tag's `<version>` must equal BOTH manifests' `version` or the
  job fails before publishing (stdlib Python check, consistent with the repo's guard style).
- Publish step: `npm publish --provenance --access public` with
  `NODE_AUTH_TOKEN: ${{ secrets.NPMJS_TOKEN }}`; no `npm ci` anywhere in the workflow (the package
  is dependency-free; nothing to install, no lifecycle scripts to trust).
- Git install remains documented as the reproducible pin; npm is documented as the convenience
  channel. `docs/parity.md`'s "Pi npm package" exception row flips DEGRADED → SUPPORTED with the
  workflow as evidence.

## Acceptance criteria

1. `tools/build-host-packages.py` renders the root manifest with name `@arbiterforge/ca-pi`, no
   `private` key, `publishConfig` `{access: "public", provenance: true}`, a `repository` field
   pointing at `git+https://github.com/arbiterForge/codeArbiter.git`, the unchanged `pi`
   extension/skill paths, and the files whitelist; `build-host-packages.py --check` enforces
   byte-identity and `test_pi_package.py` pins the new fields.
2. `npm pack --dry-run --json` at the repo root lists the extension bundle, `SKILLS.md`, and the
   whitelisted payload directories plus LICENSE, and lists nothing under `plugins/ca-pi/tools/`,
   `plugins/ca/`, `plugins/ca-codex/`, `plugins/ca-sandbox/`, `core/`, `site/`, `.github/`, or
   `.codearbiter/` (asserted by a `test_pi_package.py` test running `npm pack` offline).
3. `.github/workflows/npm-publish.yml` exists with: trigger exactly `ca-pi-v*` tag push plus manual
   dispatch; `contents: read` + `id-token: write` permissions and no broader grant; every
   third-party `uses:` pinned to a 40-hex SHA (existing repo-wide contract passes); a version guard
   that fails when tag, nested manifest, and root manifest disagree; a publish step carrying
   `--provenance --access public` and `NODE_AUTH_TOKEN` from `secrets.NPMJS_TOKEN`; and no `npm ci`
   step (structural assertions in `test_ci_impact.py` or `test_pi_package.py`).
4. The documentation posture flips consistently: `tech-stack.md` release invariants,
   `coding-standards.md` Pi adapter section, `docs/parity.md` (distribution row, future-spike
   paragraph, exception row → SUPPORTED), `docs/pi-parity-testing.md`,
   `site/src/content/docs/getting-started/compatibility.md` (host row + distribution row), and
   `site/src/content/docs/getting-started/pi.md` — each adds `pi install npm:@arbiterforge/ca-pi`
   context or drops the "Git-only / no npm release" claim; `test_public_pi_docs.py`'s posture
   assertions are repointed to pin the NEW claims (the stale "no npm release" / npm-negative
   assertions removed or inverted), and both the python doc suite and the site vitest suite pass.
5. A new ADR under `.codearbiter/decisions/` records the publishing-route change with explicit user
   attribution (2026-08-09) and is indexed in the decision log; the doc surfaces in AC-4 cite it.
6. The full repo gate passes: `test_pi_package.py`, `test_pi_parity.py`, `test_public_pi_docs.py`,
   `test_ci_impact.py`, `test_host_descriptors.py`, and the three `--check` generators.

## Open questions

None. The org scope and token existence are user-confirmed; the first-publish execution is a
deliberate out-of-scope (rides the next tag or a post-merge dispatch).
