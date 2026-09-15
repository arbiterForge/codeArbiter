# Site rolling release applicability

**State:** APPROVED
**Approved by:** repository owner standing campaign authority recorded 2026-09-14, including autonomous issue disposition, continuous campaign execution, rolling host-version policy, and SMARTS-directed enforceability
**Governs:** site/scripts/release-applicability.ts, site/scripts/gen.ts, site/src/generated/release-applicability.json, site/src/pages/release-applicability.json.ts, site/src/components/ReleaseApplicability.astro, site/src/components/HookProof.astro, site/src/content/docs/getting-started/compatibility.mdx, site/test/release-applicability/**, site/test/landing/landing-page.test.ts, .github/workflows/docs.yml, .github/scripts/test_ci_impact.py

## Problem

Prospective users and operators can see development versions, dated proof, and general host support, but cannot tell which exact independently published ca, ca-codex, and ca-pi artifacts the deployed documentation describes or which exact commit built the page. The caller is a reader evaluating support or replaying evidence. Done means the site derives, verifies, renders, and publishes those identities from repository-owned release evidence each time a host release changes.

This feature does not certify end-to-end runtime compatibility, perform installs, query GitHub from the browser or build, create a single portfolio version, publish a package or tag, change host maturity, or redesign unrelated site content.

## Approach

At build time, derive one strict applicability record from `.codearbiter/release-targets.md`, `.github/published-tags.json`, the historical manifest bytes at each recorded publication commit, the checked-out Git identity, and the existing direct-hook proof. The generator selects the latest stable SemVer independently for each governance host, validates tag-to-historical-manifest equality, and checks the replay digest against both current and latest-published ca hook bytes. The same generated JSON drives a rendered compatibility component, the hook-proof applicability label, and a static JSON endpoint.

A hand-authored table was rejected because it would recreate the drift this feature must prevent. A client-side GitHub API lookup was rejected because it adds a network dependency, rate-limit and availability ambiguity, and an unpinned trust boundary to a static documentation site. The build-time repository-evidence design costs a full-history checkout in GitHub Pages, but provides deterministic, reviewable failure behavior on free hosted CI.

## Scope

- Derive the public documentation build identity from the exact checked-out Git commit.
- Derive current published releases independently for the ca, ca-codex, and ca-pi governance hosts from the repository release declarations and original-publication receipt ledger.
- Verify each selected tag against the manifest at its recorded publication commit instead of substituting current development manifests.
- Bind the existing direct-hook replay to both its current source bytes and the latest published ca artifact bytes.
- Render the results on the public compatibility and proof surfaces and expose the same record as machine-readable static JSON.
- Make GitHub Pages rebuild when the publication receipt or release declaration changes, and fail when required release, historical manifest, build, or proof evidence is malformed or unavailable.
- Preserve the existing support, maturity, trust, and evidence-boundary language.

Out of scope: live client-side GitHub API calls, a single portfolio version, new dependencies, adapter or package releases, runtime certification, mutation of publication receipts or release declarations, and unrelated site redesign.

## Decided parameters

- The governed host set is exactly `ca`, `ca-codex`, and `ca-pi`; `ca-sandbox` is infrastructure rather than a governance host.
- “Current published” means the highest stable SemVer recorded in the original-publication receipt ledger for that target prefix. Prereleases and the closed legacy observation ledger do not qualify.
- Each selected tag must equal the `version` in its target's declared manifest at the recorded publication commit. Current development manifests are never substituted.
- GitHub Actions requires a valid 40-hex `GITHUB_SHA` equal to `HEAD`. Local generation records exact `HEAD` and whether tracked or untracked work makes the tree dirty.
- The public record uses full commit identities. Rendered summaries may show 12 characters only when the link and accessible label retain the full SHA.
- Proof applicability is a digest equality statement. A mismatch is rendered explicitly and never promoted to compatibility or host-registration evidence.
- The machine-readable route is `/release-applicability.json` and carries `application/json; charset=utf-8`.
- The record's evidence boundary is `release-and-build-identity`; it expressly excludes runtime, installation, and universal host certification.
- No new dependency is introduced. Git history is read through the existing Git executable, and JSON/Markdown inputs are parsed with repository code.
- Pages validation and build both use full Git history and both rerun when `.github/published-tags.json` or `.codearbiter/release-targets.md` changes.

## Acceptance criteria

1. Given release declarations and the original-publication ledger, the derivation selects the highest stable SemVer independently for `ca`, `ca-codex`, and `ca-pi` and rejects missing, duplicate, malformed, prerelease-only, or unsupported target data.
2. For each selected receipt, derivation reads the declared manifest at the receipt's recorded commit and rejects a tag/version mismatch, invalid SHA, missing object, or substituted current-development manifest.
3. A GitHub Actions build accepts only a 40-hex `GITHUB_SHA` equal to checked-out `HEAD`; a local build records exact `HEAD` plus dirty state, and neither mode represents a moving branch name as the deployed build identity.
4. Direct-hook applicability is true only when the replay digest equals both current source bytes and the latest published `ca` release's exact historical source bytes; either mismatch remains explicit and cannot be relabelled as a passing claim.
5. Generation writes one deterministic applicability record containing the exact build identity, host/version/tag/publication-commit rows, proof applicability, evidence sources, and the `release-and-build-identity` boundary.
6. The public Compatibility page renders three independent release rows and an exact documentation-build link. The hook-proof caption states whether the replay applies to the exact latest published `ca` artifact and links to the full record.
7. `/release-applicability.json` returns the same generated record used by both rendered surfaces with `application/json; charset=utf-8`.
8. The Pages workflow checks out full history for both validation and build and triggers on the publication receipt and release-target declaration, so a later independently versioned host publication cannot leave the deployed applicability surface stale.
9. Focused derivation, rendering, workflow, and proof regressions fail first, then pass. The complete site tests, typecheck, build, link audit, stage-2 site coverage floor, repository CI-impact checks, independent review, exact-head PR CI, merge, exact-main Pages deployment, and live source/rendered checks pass without a product or adapter release.

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

The strongest failure case is confusing a repository-recorded original-publication receipt with a fresh live-ref audit. The UI and JSON therefore name the source ledger and claim release/build identity only; existing tag-immutability CI owns live drift. The most fragile criterion is full-history availability: historical manifest and proof-byte verification cannot work from a shallow checkout, so both Pages jobs explicitly fetch full history and the workflow contract is regression-tested. The invalidating assumption would be a release that bypasses its receipt entry; all three selected targets already declare `.github/published-tags.json` as their provenance manifest, and the release and immutability gates fail on unrecorded governed tags.
