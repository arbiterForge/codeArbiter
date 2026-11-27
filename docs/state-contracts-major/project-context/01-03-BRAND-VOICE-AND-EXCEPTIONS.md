# Brand, Voice, and Exceptions

**Snapshot:** 2026-09-01  
**Status:** EVIDENCE-BASED CLASSIFICATION; NO NEW BRANDING OR MARKETING COPY

## 1. Current boundary

This file records existing naming, voice, and visual constraints. It does not create a logo, slogan,
tagline, campaign, or public claim. No organization-global design system was approved by this
bootstrap.

## 2. Organization identity rules proposed for canon

| Property | Proposed rule | Evidence | State |
|---|---|---|---|
| GitHub owner | Use the exact organization login `arbiterForge` in repository paths. | `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:/` and the other repository-root snapshots in the portfolio | PROVISIONAL |
| Repository names | Preserve exact repository identifiers: `codeArbiter`, `arbiterIDE`, `arbiter-academy`, `.github`, `arbiterforge-site`, `arbiteride-site`, `coderabbit`. | `01-PORTFOLIO-AND-SURFACES.yaml` | PROVISIONAL |
| Product display names | Preserve observed product casing: `codeArbiter`, `arbiterIDE`, `Arbiter Academy`, and `arbiterForge`. | `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:README.md`; `arbiterForge/arbiterIDE@53e121dd689b505a834ac258b2968baf145f5b74:README.md`; `arbiterForge/arbiter-academy@cfb8fcab5468f592f0d11c0e0464c86d9210a5ac:README.md`; `arbiterForge/.github@263be7740b1b41a085ead05d517781d37ca56eb6:profile/README.md` | PROVISIONAL |
| Public domains | Treat each domain as surface-specific until its live deployment is captured. | `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/public/CNAME`; `arbiterForge/arbiterforge-site@d29aa6bbdbf5643081b765382fa2088054898d97:CNAME`; `arbiterForge/arbiteride-site@b6586706baa9e40a5dacf324912ec482bb47d1ec:CNAME` | PARTIALLY VERIFIED |

These identity rules require approval before they become durable Project canon.

## 3. Existing codeArbiter documentation voice

The codeArbiter documentation owns a written voice contract at
`arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/VOICE.md`. Its current rules include:

- In documentation, “you” addresses the reader, not the model or orchestrator.
- Landing, instructional, explanatory, and reference pages have different registers.
- Instructional steps should be observable and verifiable.
- Reference prose is neutral and front-loaded.
- Terms such as gate, lane, STOP, BLOCK, override, Feature Forge, and tribunal have product-specific
  meanings.
- The guide prohibits em dashes as sentence separators in authored site prose.

The documentation design contract at
`arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/DESIGN-SYSTEM.md` adds product-specific principles:
proof before promise, source-visible reference, local-first site assets, restrained use of the gate
color, and explicit verification before documentation changes ship.

**Classification:** product-specific. These rules do not automatically govern arbiterIDE, Academy,
the organization site, or CodeRabbit.

## 4. Observed visual relationship

Current source shows a related deep-slate and gate-gold treatment across:

- codeArbiter documentation: `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/DESIGN-SYSTEM.md`
- organization site: `arbiterForge/arbiterforge-site@d29aa6bbdbf5643081b765382fa2088054898d97:index.html`
- IDE site: `arbiterForge/arbiteride-site@b6586706baa9e40a5dacf324912ec482bb47d1ec:index.html`

This is an observation, not an approved organization rule. The organization site README says it
shares color and typography tokens with codeArbiter docs at
`arbiterForge/arbiterforge-site@d29aa6bbdbf5643081b765382fa2088054898d97:README.md`. That source-visible statement does
not prove automated token sharing or require Academy and CodeRabbit to use the same system.

## 5. Product and surface exceptions

### codeArbiter

- Host entry spelling is adapter-specific (`ca`, `ca-codex`, `ca-pi`) while the product name remains
  `codeArbiter`: `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/src/content/docs/overview.md`.
- `Feature Forge` and its reader-facing presentation are codeArbiter terminology, not an
  organization-global maturity system: `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:site/VOICE.md`.
- Claude marketplace contents are surface-specific. A two-plugin Claude marketplace description
  does not define the total host-adapter count:
  `arbiterForge/codeArbiter@60bd988faae481a26d51ee812d4659eb6baef7ce:.claude-plugin/marketplace.json`.

### arbiterIDE

- arbiterIDE is a separate product, not a renamed codeArbiter host adapter:
  `arbiterForge/arbiterIDE@53e121dd689b505a834ac258b2968baf145f5b74:README.md`.
- The public site’s “in development” and availability wording is surface-specific and must not be
  converted into a release decision without exact distribution evidence:
  `arbiterForge/arbiteride-site@b6586706baa9e40a5dacf324912ec482bb47d1ec:index.html`.
- Accepted content-source decisions are product-specific and remain planned until implementation is
  proven: `arbiterForge/arbiterIDE@53e121dd689b505a834ac258b2968baf145f5b74:.codearbiter/decisions/0012-content-as-data-upstream.md`.

### Arbiter Academy

- Academy is an instructional product. Its learner-facing procedures, verifier messages, lab IDs,
  and graduation language are governed by the exact Academy release, not by the codeArbiter docs
  voice guide: `arbiterForge/arbiter-academy@dfd86a25bc2d1a90551d1cbd3d738a38825bd193:academy/publication/preview-0.30.json`
  and `arbiterForge/arbiter-academy@dfd86a25bc2d1a90551d1cbd3d738a38825bd193:academy_engine/cli.py`.
- Training claims must identify the exact Academy tag and declared codeArbiter compatibility.
  Preview 0.30 names supported hosts but no exact codeArbiter versions, so compatibility is UNKNOWN.

### Organization profile and organization site

- These are derivative portfolio and claim surfaces, not the source of product behavior, release
  evidence, license meaning, privacy behavior, or security behavior:
  `arbiterForge/.github@263be7740b1b41a085ead05d517781d37ca56eb6:profile/README.md` and
  `arbiterForge/arbiterforge-site@d29aa6bbdbf5643081b765382fa2088054898d97:index.html`.
- Absolute proof, privacy, telemetry, version, and legal statements must be traced back to their
  product-specific owning source and exact release before publication.

### CodeRabbit

- Review-bot instructions are operational prompts, not public product voice. Current source asks for
  concise, specific, evidence-focused review and is advisory rather than a merge gate:
  `arbiterForge/coderabbit@2acf0f1a27dee314b81ff48a14d5db06d7be1ec7:.coderabbit.yaml`.
- The effective prompt and behavior remain UNKNOWN until a consuming pull request’s resolved
  configuration is inspected, as required by
  `arbiterForge/coderabbit@2acf0f1a27dee314b81ff48a14d5db06d7be1ec7:README.md`.

## 6. Language guardrails pending approval

These are governance controls, not replacement copy:

1. Do not use an absolute proof claim across products when their enforcement boundaries differ.
2. Do not collapse “no default telemetry,” “no project-operated server,” “no network calls,” and
   “explicit opt-in transmission” into one claim.
3. Do not infer license scope or commercial rights from a badge or landing-page summary.
4. Do not call current `main` a released product version.
5. Do not use an Academy lab count or compatibility statement without an exact release manifest.
6. Do not extend codeArbiter terms or voice rules to another product without an approved exception
   record.

## 7. Approval needed

Before audit revalidation, approve:

- the exact organization and product naming table;
- whether the observed visual relationship is organization-global, product-family shared, or merely
  surface-specific;
- which subset, if any, of the codeArbiter documentation voice becomes organization-wide;
- product-specific proof and maturity vocabulary;
- Academy’s position in the public portfolio;
- who owns legal, privacy, and security claim approval.
