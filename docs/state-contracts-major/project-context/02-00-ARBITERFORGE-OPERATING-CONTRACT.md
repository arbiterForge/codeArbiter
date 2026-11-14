# ArbiterForge Product-System Operating Contract

**Bootstrap snapshot:** 2026-09-01  
**Status:** STRUCTURE ESTABLISHED; AUDIT REVALIDATION NOT PERFORMED  
**Repository writes:** NONE

## 1. Purpose

This Project coordinates the personal ArbiterForge product system. It keeps repository facts,
release evidence, public surfaces, training, branding, policy claims, and known drift traceable to
their owning sources. It is an evidence index and decision ledger, not a replacement for repository
documentation.

This bootstrap records structure only. It does not remediate a repository, approve public copy,
determine release maturity, interpret a license, or establish an organization-wide implementation
architecture.

## 2. Authorized scope

Only repositories owned by the GitHub organization whose login is exactly `arbiterForge` are in
scope, and only these repositories are authorized:

- `arbiterForge/codeArbiter`, including its public `ca-pi` adapter
- `arbiterForge/arbiterIDE`
- `arbiterForge/arbiter-academy`
- `arbiterForge/.github`
- `arbiterForge/arbiterforge-site`
- `arbiterForge/arbiteride-site`
- `arbiterForge/coderabbit`

Navigator, coveNavigator, Navi, NaviControl, employer forks, COVE, GDIT, and all other work material
are excluded. Excluded material must not be opened for product discovery, summarized, adapted,
upstreamed, or used to infer public-product behavior. When exclusion is encountered, the only
permitted record is that out-of-scope downstream work was encountered and excluded.

## 3. Evidence notation

Every current repository-content fact uses the form:

```text
owner/repo@40-character-commit:path
```

Repository metadata that does not live in a file, such as visibility and default branch, is bound to
the exact inspected default-branch head and repository root as `owner/repo@commit:/`, with
`evidence_kind: github_repository_metadata` in the portfolio.

Release evidence is recorded in three layers:

1. Exact tag and dereferenced commit.
2. A file at that exact commit, written as `owner/repo@commit:path`.
3. Exact package or asset identity, digest, and inspection state.

A tag, release page, or manifest does not prove that marketplace, npm, installer, or archive bytes
match it. When exact distributed bytes were not acquired and inspected, artifact evidence is
`UNKNOWN` even when tag and release metadata are known.

The current default branch is development evidence. It is never described as released behavior.

## 4. Authority by claim type

| Claim type | Authority order |
|---|---|
| Released behavior | Exact distributed artifact or package; evidence against those bytes; exact tag and release metadata; then current source |
| Development architecture | Current implementation; implemented decisions; accepted plans; then historical discussion |
| Product identity and terminology | Approved Project canon; approved product exceptions; then current public surfaces |
| Legal, privacy, and security | Exact license, policy, and package notice at the relevant commit or artifact; marketing summaries are derivative |
| Training | Exact Academy release and asset; installed verifier; lesson/action/checkpoint source; declared codeArbiter compatibility |
| Organization tooling | Exact central configuration plus the effective resolved configuration observed in each consuming service |

An accepted ADR proves that a decision was accepted. It does not prove implementation, release,
deployment, or verification.

## 5. Fact-state vocabulary

- **CURRENT_SOURCE** — directly supported by an authorized repository at the inspected commit.
- **RELEASE_SPECIFIC** — bound to an exact tag, package, or artifact; scope does not extend to
  another release.
- **PLANNED** — proposed or accepted design without sufficient implementation evidence.
- **PROVISIONAL** — useful working classification awaiting explicit canon approval.
- **HISTORICAL** — evidence valid only for the recorded commit, tag, artifact, or date.
- **CONTRADICTED** — authoritative or derivative surfaces make materially incompatible claims.
- **UNKNOWN** — exact evidence was unavailable, not inspected, or does not exist in the source.
- **EXCLUDED** — outside the authorized product boundary and unusable as evidence.

Unknown is not equivalent to false. A current source claim is not automatically a release claim.

## 6. Property scopes

Every shared property is classified before it is propagated:

- **organization-global** — approved for every in-scope product and surface.
- **product-family shared** — shared by a named subset of products.
- **product-specific** — owned by one product.
- **surface-specific** — valid only for a site, marketplace, profile, README, or similar surface.
- **release-specific** — valid only for an exact tagged or packaged release.
- **approved exception** — deliberate divergence with owner, rationale, and evidence.

Observed similarity is not organization canon. The current codeArbiter documentation voice and
design system are product-specific until an explicit decision broadens their scope.

## 7. Discovery contract

A discovery pass must:

1. Freeze the repository list and default-branch commit SHAs.
2. Inventory the smallest set of owning sources needed for the question.
3. Separate current source, release evidence, plans, public derivatives, and unknowns.
4. Normalize cross-surface claims into `02-CROSS-SURFACE-CLAIMS.yaml`.
5. Record contradictions and stale evidence in `04-AUDIT-AND-DRIFT-LEDGER.md`.
6. Preserve product-specific exceptions and avoid organization-wide architectural inference.
7. Exclude all unauthorized work context.

Repository documentation is referenced, not copied wholesale.

## 8. Remediation-planning contract

Remediation is a later phase and begins only after discovery assumptions are approved. A remediation
plan must identify the owning source, the smallest durable correction, affected derivatives,
propagation order, exact-artifact tests, migration needs, rollback, and verification criteria.

No source is reported as changed until it was actually changed and inspected. This bootstrap made no
GitHub changes.

## 9. Prior-audit handling

The requested existing codeArbiter audit chat was not available through the connected Project files
or tools during this bootstrap. Its commit, artifact, findings, and date are therefore `UNKNOWN`.
It must not be treated as current evidence. Before audit revalidation, add an export or durable source
that identifies the exact commit or artifact inspected by that audit. Once supplied, its findings are
historical and commit-bound until revalidated.

## 10. Project-source maintenance

The six bootstrap files are proposed Project Sources. Future updates should be atomic:

1. Record newly inspected commits and artifacts.
2. Update the portfolio and claim registry.
3. Append or resolve ledger entries without deleting historical evidence.
4. Record approvals and open loops.
5. Validate YAML and evidence-reference syntax.
6. Retain the prior snapshot for rollback.

The Project must report conflicts between these sources and live GitHub rather than silently choosing
one.

## 11. Bootstrap evidence boundary

The exact repository snapshots are listed in `01-PORTFOLIO-AND-SURFACES.yaml`. Exact release evidence
was sampled only where needed to establish the authority model. Live site deployments, marketplace
installations, npm package bytes, and Academy release-archive bytes were not acquired; their exact
behavior remains `UNKNOWN` until artifact-led revalidation.
