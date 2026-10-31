# Site rolling release applicability

**State:** APPROVED
**Approved by:** repository owner standing campaign authority recorded 2026-09-14, including autonomous issue disposition, continuous campaign execution, rolling host-version policy, and SMARTS-directed enforceability
**Amended:** 2026-10-30 by the repository owner through `/ca:conflict` (option "Derive from tags"): ADR-0040 stopped new tags from requiring a receipt, so the receipt ledger lagged publication and the site presented ca 2.21.15 as latest after 3.6.0 shipped. "Current published" is now the highest stable release tag; receipt status is a separate field.
**Amended:** 2026-10-31 by the repository owner (issue #1071, deferred from the #1070 review): the Pi page pins the published `ca-pi` tag, but its Pi prerequisite came from the development tree, so a merged but unreleased promotion could require a Pi version that tag rejects. The record now carries the Pi versions the selected `ca-pi` tag accepts (schema 3), and the published Pi prerequisite derives from it.
**Governs:** site/scripts/release-applicability.ts, site/scripts/version-facts.ts, site/scripts/gen.ts, site/src/generated/release-applicability.json, site/src/pages/release-applicability.json.ts, site/src/components/ReleaseApplicability.astro, site/src/components/HookProof.astro, site/src/content/docs/getting-started/compatibility.mdx, site/test/release-applicability/**, site/test/landing/landing-page.test.ts, .github/workflows/docs.yml, .github/scripts/test_ci_impact.py

## Problem

Prospective users and operators can see development versions, dated proof, and general host support, but cannot tell which exact independently published ca, ca-codex, and ca-pi artifacts the deployed documentation describes or which exact commit built the page. The caller is a reader evaluating support or replaying evidence. Done means the site derives, verifies, renders, and publishes those identities from repository-owned release evidence each time a host release changes.

This feature does not certify end-to-end runtime compatibility, perform installs, query GitHub from the browser or build, create a single portfolio version, publish a package or tag, change host maturity, or redesign unrelated site content.

## Approach

At build time, derive one strict applicability record from `.codearbiter/release-targets.md`, the release tags in the full-history checkout, `.github/published-tags.json` (receipt status only), the historical manifest bytes at each selected tag's commit, the checked-out Git identity, and the existing direct-hook proof. The generator selects the latest stable SemVer independently for each governance host, validates tag-to-historical-manifest equality, and checks the replay digest against both current and latest-published ca hook bytes. The same generated JSON drives a rendered compatibility component, the hook-proof applicability label, and a static JSON endpoint.

A hand-authored table was rejected because it would recreate the drift this feature must prevent. A client-side GitHub API lookup was rejected because it adds a network dependency, rate-limit and availability ambiguity, and an unpinned trust boundary to a static documentation site. The build-time repository-evidence design costs a full-history checkout in GitHub Pages, but provides deterministic, reviewable failure behavior on free hosted CI.

## Scope

- Derive the public documentation build identity from the exact checked-out Git commit.
- Derive current published releases independently for the ca, ca-codex, and ca-pi governance hosts from the repository release declarations and the release tags in the checkout, and report each selected tag's original-publication receipt status separately.
- Verify each selected tag against the manifest at the commit the tag peels to instead of substituting current development manifests.
- Bind the existing direct-hook replay to both its current source bytes and the latest published ca artifact bytes.
- Record the exact Pi versions the selected `ca-pi` tag accepts, read at that tag's commit, so the published Pi prerequisite matches the release the install instructions pin.
- Render the results on the public compatibility and proof surfaces and expose the same record as machine-readable static JSON.
- Make GitHub Pages rebuild when the publication receipt or release declaration changes or a release run completes, and fail when required release, historical manifest, build, or proof evidence is malformed or unavailable.
- Preserve the existing support, maturity, trust, and evidence-boundary language.

Out of scope: live client-side GitHub API calls, a single portfolio version, new dependencies, adapter or package releases, runtime certification, mutation of publication receipts or release declarations, and unrelated site redesign.

## Decided parameters

- The governed host set is exactly `ca`, `ca-codex`, and `ca-pi`; `ca-sandbox` is infrastructure rather than a governance host.
- “Current published” means the highest stable SemVer release tag in the checkout for that target prefix (a longer declared prefix owns its own tags). Prereleases do not qualify, a malformed matching tag fails, and a host with no stable tag fails closed. Each host row also states whether that tag's original-publication receipt is `recorded` in `.github/published-tags.json` or `not-recorded`; a recorded receipt naming a different commit than the tag fails. The receipt status is never presented as a live tag audit, and a tag is never called a receipt.
- Each selected tag must equal the `version` in its target's declared manifest at the commit the tag peels to. Current development manifests are never substituted.
- The published Pi support is the `SUPPORTED_PI_VERSIONS` set in `plugins/ca-pi/tools/src/compatibility.ts` at the selected `ca-pi` tag's commit: exactly one declaration of quoted exact `X.Y.Z` versions, sorted, recorded as `publishedPiSupport` with that tag, commit and path, and listed as a `published-pi-compatibility` evidence source. A missing object, missing or duplicated declaration, empty set, or non-exact entry fails generation. The `pi.supported` version fact reads this field, never the development tree. It is a declared support set, not runtime certification.
- GitHub Actions requires a valid 40-hex `GITHUB_SHA` equal to `HEAD`. Local generation records exact `HEAD` and whether tracked or untracked work makes the tree dirty.
- The public record uses full commit identities. Rendered summaries may show 12 characters only when the link and accessible label retain the full SHA.
- Proof applicability is a digest equality statement. A mismatch is rendered explicitly and never promoted to compatibility or host-registration evidence.
- The machine-readable route is `/release-applicability.json` and carries `application/json; charset=utf-8`.
- The record's evidence boundary is `release-and-build-identity`; it expressly excludes runtime, installation, and universal host certification.
- No new dependency is introduced. Git history is read through the existing Git executable, and JSON/Markdown inputs are parsed with repository code.
- Pages validation and build both use full Git history and both rerun when `.github/published-tags.json` or `.codearbiter/release-targets.md` changes. A completed `release` workflow run on main also rebuilds and redeploys main, because release tags are pushed after main's own docs build; most such runs publish nothing and redeploy identical content. Every version-fact source in `site/scripts/version-facts.ts` is a rebuild path.

## Acceptance criteria

1. Given release declarations, the checkout's release tags, and the original-publication ledger, the derivation selects the highest stable release tag independently for `ca`, `ca-codex`, and `ca-pi`, reports each tag's receipt status separately, and rejects missing, duplicate, malformed, prerelease-only, or unsupported target data and a receipt whose commit differs from its tag.
2. For each selected tag, derivation reads the declared manifest at the tag's commit and rejects a tag/version mismatch, invalid SHA, missing object, or substituted current-development manifest.
3. A GitHub Actions build accepts only a 40-hex `GITHUB_SHA` equal to checked-out `HEAD`; a local build records exact `HEAD` plus dirty state, and neither mode represents a moving branch name as the deployed build identity.
4. Direct-hook applicability is true only when the replay digest equals both current source bytes and the latest published `ca` release's exact historical source bytes; either mismatch remains explicit and cannot be relabelled as a passing claim.
5. Generation writes one deterministic applicability record containing the exact build identity, host/version/tag/publication-commit/receipt-status rows, proof applicability, evidence sources, and the `release-and-build-identity` boundary.
6. The public Compatibility page renders three independent release rows and an exact documentation-build link. The hook-proof caption states whether the replay applies to the exact latest published `ca` artifact and links to the full record.
7. `/release-applicability.json` returns the same generated record used by both rendered surfaces with `application/json; charset=utf-8`.
8. The Pages workflow checks out full history for both validation and build and triggers on the publication receipt, the release-target declaration, and every completed release run on main, so a later independently versioned host publication cannot leave the deployed applicability surface stale.
9. Focused derivation, rendering, workflow, and proof regressions fail first, then pass. The complete site tests, typecheck, build, link audit, stage-2 site coverage floor, repository CI-impact checks, independent review, exact-head PR CI, merge, exact-main Pages deployment, and live source/rendered checks pass without a product or adapter release.
10. Generation records the Pi versions the selected `ca-pi` tag accepts, read at that tag's commit, and fails closed on an unreadable or malformed declaration; a change to `compatibility.ts` that has not been released leaves the published Pi prerequisite unchanged.

## Open questions

None. CONFIRM-05 concerns Feature Forge farm promotion and is unrelated. The deferred test-running commit-hook decision does not apply because this feature relies on the existing commit gate and hosted CI, not a new local commit hook.

## Intent and completeness review

- Conforms to ADR-0025: the current user direction outranks and aligns with the accepted record; the design uses the decision log and accepted ADRs rather than a stale imported recommendation.
- Conforms to ADR-0035: Pi remains an independently advancing reviewed release line. No permanent Pi version or singleton portfolio version is introduced.
- Conforms to DECISION-0032: `site/` remains inside the existing coverage gate.
- Conforms to DECISION-0033/0034: release declarations remain check-only executable release input and are read, not mutated or executed, by this generator.
- The mechanical `uncovered-intent` backstop returned empty.
- Negative completeness question: if every criterion passes, the imported WEB-022 and WEB-011 obligations are closed. Browser-quality enforcement, search lifecycle, and accessibility matrices remain explicitly separate WEB-031/035 work rather than hidden omissions.

## Adversarial review

The strongest failure case is confusing a repository-recorded original-publication receipt with a fresh live-ref audit. The UI and JSON therefore name the source ledger and claim release/build identity only; existing tag-immutability CI owns live drift. The most fragile criterion is full-history availability: historical manifest and proof-byte verification cannot work from a shallow checkout, so both Pages jobs explicitly fetch full history and the workflow contract is regression-tested. The original invalidating assumption, a release that bypasses its receipt entry, became normal under ADR-0040 and stranded the site at ca 2.21.15; the 2026-10-30 amendment therefore selects from release tags and reports receipt status separately. Tags are mutable refs, so the selection leans on the live tag rulesets and tag-immutability CI that ADR-0040 already relies on to refuse movement and deletion; the record still claims release/build identity only.
