# Security controls — codeArbiter

This document records accepted boundaries and their owners. It is not a claim
that every tool call is intercepted or that every host/platform is qualified.
ADR-0043 removes the duplicate artifact permission layer for already-authorized
work; it preserves host permissions, explicit user denials/stops, sandbox and
filesystem restrictions, repository integrity, safe persistence and publication
authorization. Progress may be recorded without claiming verification or review.

## Cryptographic primitives

SHA-256 and the SHA-2 family are approved for hashing/integrity. MD5, SHA-1, DES,
3DES, RC4, RC2 and Blowfish are prohibited. Test fixture strings describing
forbidden primitives are not approval to use them. The owning detection and
commit-marker controls are `_sensitivelib.py`, `_hooklib.py`, and their tests.
Do not weaken these controls as part of the assistive lifecycle change.

## Secret store and access method

This project has no runtime secrets vault. Secrets belong in the owning process's
approved environment or release secret store,
never source, logs, artifacts, prompts, configuration commits, or diagnostic
echoes. `FARM_API_KEY` is allowed only as farm runtime input. Sandbox
`CLAUDE_CODE_OAUTH_TOKEN` injection is explicit `--with-claude` behavior; do not
mount credential material with untrusted source or silently widen egress.

Pi's ADR-0019 parent inference broker supersedes stored-provider credential
projection. A child receives a short-lived per-child loopback token, not reusable
provider credentials. The selected provider/model is exact; unavailable service
must not cause automatic fallback. This is cooperative same-user isolation,
not an OS security boundary: another local process holding the child token may
use it until revocation. The broker closes and temporary state is cleaned on
completion/failure. Secrets do not enter child argv or diagnostic output.

Child provider configuration is credential-blind and schema-bounded. Only
approved keys/shapes and pure environment references for API-key/header fields
are projected; executable `!` values and unsupported provider/OAuth routes fail
closed. Endpoint URLs exclude userinfo, query and fragment. Preserve bounded
case-insensitive route validation. Child OS environment is minimal, excluding
farm/Claude credentials; home, agent and session state are isolated, prompts use
stdin, and `PI_PACKAGE_DIR` exposes only the intended parent package resources.
Dummy-credential tests must not read real home authentication.

## Network and untrusted execution

TLS verification stays enabled. API endpoints use HTTPS except narrowly bounded
loopback test/broker paths. Farm validates its resolved base URL and each fetch,
rejects userinfo and redirects, and emits origin-only diagnostics. Provider
response bodies must not be copied into reports, retry messages or stderr.

The update notifier makes bounded unauthenticated GitHub release reads without
repository content, PII or credentials: at most ten pages/1,000 results, daily
per-host caching, standard-library verified TLS, and fail-silent asynchronous
behavior that does not add SessionStart network latency.

Sandbox containers use non-root UID 1000, `--cap-drop ALL`, read-only root,
`no-new-privileges`, resource caps and no privileged mode or Docker socket.
`mounts.ts` is the single mount constructor: named volumes/tmpfs only, no host
bind mounts. Network is offline by default and an unknown policy is an error.
Clone inputs are bounded to approved HTTPS/SSH forms; reject leading options
and transport-helper forms, preserve argv separation and `--`, and never
interpolate untrusted input into a shell. Installed nixpacks detection does not
authorize downloading/installing a helper at runtime. Container image inputs
are digest-pinned; supply-chain tests reject floating `latest` inputs.

## Dependency policy

Dependencies and lockfile resolutions use the official npm registry. Repository
metadata links are not dependency-source exceptions. New/changed dependencies
retain provenance, vulnerability and license review. The high-severity audit
threshold includes development dependencies in the three tools projects; site
production dependencies use the exception-aware gate. An exception identifies
the exact advisory/package, maximum severity, owner rationale and expiry of at
most 30 days. `site/audit-exceptions.json` owns the current exception; the recorded
2026-10-03 approval for GHSA-ch52-4w7c-c8xp expires no later than 2026-11-02.
Do not infer that an old no-fix observation remains current.

### Approved licenses

Approved licenses are MIT, ISC, Apache-2.0, BSD-2-Clause, BSD-3-Clause,
BlueOak-1.0.0, CC0-1.0 and Unlicense. Retain these accepted scoped additions:

| License | Accepted scope |
|---|---|
| MPL-2.0 | Development/build-time dependencies in site and tools; not shipped runtime code. |
| LGPL-3.0-or-later | The accepted `@img/sharp-libvips-*` docs-site build-time packages only; optimized output does not embed that library. |
| 0BSD | Development/build-time site/tools dependencies. |
| Artistic-2.0 | The exact vetted npm 11.19.1 CI CLI only. |
| CC-BY-3.0 | Bundled `spdx-exceptions` 2.5.0 in that exact vetted CLI only. |

The accepted argparse license-metadata mismatch resolves to upstream MIT;
satteri ships MIT despite missing SPDX metadata. These are specific accepted
findings, not blanket missing-license exemptions. A license outside the approved
set/scopes needs explicit review and the existing override record. Preserve the
2026-07-02 and 2026-07-14 user decisions and attribution in history. The Pi npm
package is public; private build/test manifests do not make all repository
packages private.

## Hook security (Python)

Hooks use Python's standard library. Malformed hook stdin has the deliberately
fail-open entry behavior in `_hooklib.read_input`; that is not a rule to treat
unsafe filesystem state or failed security reads as success. Git-operation cwd
respects repeated `-C`. Codex does not inherit `CLAUDE_PROJECT_DIR`; host payload
cwd remains a host trust boundary. Git owns config grammar and hook execution.
Default worktree layout support does not imply all separate-Git-dir, UNC or WSL
topologies are qualified. Do not alter safe.directory to manufacture a result.

The hook identity bundle comprises three atomically bound records; malformed,
stale or inconsistent identities fail closed. Uninstall removes only owned
configuration. Preserve conservative cache invalidation and actual-runtime
identity checks. A source checkout, package inventory, doctor result or prior
session cannot substitute for current live enforcement proof.

### Pi trust boundary

Pi can load an extension before project trust. Before affirmative
`isProjectTrusted()`, only the bounded context marker is read; Python/Git work,
mutations and doctor probes remain unavailable. Session-start and final
pre-execution checks invalidate/re-read trust as required. Unknown tools fail
closed unless the host descriptor supplies an allowed mapping. Exact final
argument order is a promotion requirement; a host unable to guarantee it is not
qualified. Child execution disables ambient extension/session/approval discovery
and loads the intended resources explicitly. A child marker prevents recursive
dispatch only; it does not disable security controls. Use `shell:false`, bounded
redacted inputs, minimal environment and whole-process-tree cleanup.

ADR-0010 accepts that trusted same-process extensions and a cooperative parent
with filesystem/shell access can bypass or forge unkeyed local records. Source
hashes/receipts are integrity and provenance records within that model, not
signed attestation against the parent. Stronger secret-key attestation remains
a separately recorded product decision, not an implicit requirement of this
refresh. Ordinary progress never needs such an attestation.

## Audit trail

Append-only records include overrides.log, triage.log, sprint-log.md,
gate-events.log, done-tasks.md, decisions/decision-log.md and ADR lifecycle
history under their existing owning controls. H-05 protects existing history;
it does not guarantee every event was logged. The accepted completeness strategy
is a lightweight staleness warning with the best-effort gate-events sink. Sink
failure/lock contention must not reverse a guard's verdict. Warnings are advisory
and not persisted as fabricated events. `/override` is not staleness-tracked.

`.codearbiter/decisions/adr-lifecycle.jsonl` is the append-only decision-lifecycle
ledger. Its exact repository-relative path is authoritative; hook classification
also compares it case-folded so mixed-case aliases cannot evade protection on
supported case-insensitive filesystems. Tail append is its only permitted write
shape. H-05 enforces append-only write shape by blocking rewrites, truncation,
deletion and non-tail edits. The lifecycle checker separately validates JSONL
syntax, event completeness, schema, and committed-prefix integrity after writes
and in CI; H-05 does not validate appended content. H-11 separately protects
governed decision-document paths.

In CI, the lifecycle checker compares the base and current ledger as committed Git blobs
and requires the base to be an exact byte prefix of the current blob. Missing,
unresolvable or all-zero base identities fail closed. Immutable accepted packets
retain their exact bindings; local checks do not rewrite historical evidence.
Sanctioned marker producers are cooperative attestations; never mint a marker,
approval source or test/review result without its actual underlying action.

Lexical shell guards have accepted indirection boundaries, including variable
and descriptor/compound-shell forms; they are not an adversarial OS sandbox.
The accepted MCP write-hook gap remains for both host surfaces under ADR-0010:
doctor reports configuration availability/counts without exposing server
details. Reopen this decision when a supported host matcher exists, a cooperative
consumer incident occurs, a shipped/recommended MCP tool needs coverage, or the
doctor visibility guarantee is lost. A tool name alone does not prove coverage.

## Protected-state registry

`_protectedstatelib.py` owns protected paths. `open-tasks.md` is helper-only
mutable through taskwrite.py; `done-tasks.md` is append-only. Context documents
use their bounded owned writer. `release-targets.md` is marker-gated because
its generation/pre-tag/release-build declarations execute in privileged release
lanes; do not raw-write it or treat it as ordinary prose. Case/slash normalization,
known write verbs and interpreter-inline forms preserve cross-platform matching.
Broad-basename overmatching and the deliberate touch exclusion retain their
recorded scope; a refresh must not silently choose a new enforcement policy.

## Native artifacts and recovery

The native engine is pinned to the installed package's manifest/digest/platform
qualification. Never discover a replacement on PATH or fetch one at runtime.
Packaging/installers retain their platform-specific safe-path, no-follow and
identity boundaries. Static source or fixture tests do not establish installed
host permissions.

CI qualification receipts are issued by one Linux `artifact-engine` job, not on
each native host. Its trust basis is this run's artifact store, the required
native stages' success (`ci20_native_binding.py gate`), and each native
consumer's on-host `verify` of the builder's stamp against that host's Go
toolchain. The issuer re-binds run, source, module, platform, toolchain and
bytes. Keep those consumer `verify` steps unconditional on every platform;
contract: `docs/plans/ci20-02-candidate-admission.md`, CI20-04.

Bounded requests/reads, stable IDs, exact revisions, safe HTML escaping,
transaction journals, before-images, operation replay and no-follow filesystem
checks protect data integrity. Progress and reported checks must remain separate
from assessed evidence. A failed/flaky later result must remain visible.
Reconciliation cleanup cannot erase a captured real stop because the capture
preceded attempt persistence; recovery reuses the existing immutable observation
and source, original operation ID and revision binding. Ambiguous/missing inputs
stay unresolved without inventing authority. Migration/rollback preserves later
work and complete-store history; it is explicit, not an automatic rewrite.

## Published tag immutability

The four installable release series are `v*` (ca), `ca-sandbox-v*`,
`ca-codex-v*` and `ca-pi-v*`. Consumers pin tags as payload identities.
**A published tag is immutable: there is no break-glass.** Moving, retargeting
or deleting one is prohibited for every actor, including administrators.
Correct a bad release with a new version. This preserves the maintainer's
2026-07-25 ruling on issue #386; no standing bypass credential is justified
by a recovery action the project expressly forbids.

A mutable tag can redirect a pinned install to unreviewed code while its old
release notes still imply the reviewed payload; deletion breaks availability.
Preserve the two independent controls:

1. Repository tag rulesets prevent deletion and non-fast-forward movement over
   the release namespaces, without bypass actors for this immutability control.
   Rulesets are external settings, not source files; a historical setting
   snapshot does not prove current configuration.
2. `.github/scripts/check_tag_immutability.py` detects drift against the disjoint
   union of `.github/published-tags.json` (original-publication receipts) and
   `.github/legacy-published-tags.json` (closed historical baselines). The
   `[CHECK] | [REPO] | Published tag immutability` job is read-only. Detection
   cannot prevent an install between a ref change and the next audit, so it
   does not replace the preventive ruleset.

The original-publication ledger retains both the tag object and peeled commit.
A current API ref or mutable Release `target_commitish` cannot reconstruct a
lost original identity. Ledger integrity rests on reviewed Git history and
protected-main updates; changing a recorded identity to silence a red drift
check is never a repair. Authenticate the original publisher run/artifact before
reconciliation, bind its expected identity independently, and preserve uncertainty
when that evidence is unavailable. A retained receipt is not a completed ledger
handoff: only its reviewed addition merged to main completes ingestion.

ADR-0034 fixes the legacy epoch at **44 records observed at
`2026-09-04T20:45:43Z`**. It is **not original-publication proof**: a historical
ref could have moved before observation. Its canonical identity-and-grade digest,
source-matrix digest, timestamp, record count and **15/28/1 evidence-grade
distribution** stay bound. The baseline provides forward detection only.
Publishers and receipt reconcilers cannot grow the closed set. Adding or
replacing an identity, source or grade requires a **new accepted, user-attributed
ADR and architectural review**. Later tags use original-publication receipts;
none may be relabelled as legacy to clear a failure. There is no break-glass
for deletion, retargeting or movement; correction remains a new version.

ADR-0040's accepted exception is narrow: required CI and the release workflow's
preflight run without `--require-recorded`. A recorded tag that moved or
disappeared, or invalid/unreadable inventory, still fails; an unrecorded new tag
warns. Do not describe either workflow as strict missing-receipt enforcement.
The checker still supports an explicitly selected `--require-recorded` audit;
that capability is not evidence that every caller selects it. Receipt
reconciliation remains separately authenticated and reviewed. Publication and
ledger-PR merge are not transactional, and a later publication can race an
already-green check. Preserve the accepted provenance-warning residual rather
than inventing original-publication evidence or bypassing a drift failure.

## Hosted publication and distribution

Governance publication uses exact retained qualified cohort bytes. Local source,
hosted candidate, published archive, npm/cold install, marketplace and actual
fresh host-session checks are distinct. The normal cohort archives are tarballs;
the hosted Codex static ZIP validator is a separate bounded inspection surface,
not a claim of live Codex execution. That validator limits archives to 8 MiB,
1,024 entries, 2 MiB per file, 32 MiB total and 100:1 expansion; accepts only the
expected plugin subtree; rejects symlinks/reparse/encrypted/unsafe/ambiguous
paths; and checks manifest, frontmatter, resources, hooks and generated digests.
No desktop VM/device-auth/API-key simulation substitutes for actual host proof.

### ca-pi npm publication boundary

Pi publication of `@arbiterforge/ca-pi` explicitly forwards the authorized
repository or organization Actions secret `NPMJS_TOKEN`, never all
secrets. `NODE_AUTH_TOKEN` is exposed only to the publish invocation. The exact
npm@11.19.1 CLI is acquired without credentials over verified non-redirecting
TLS, with pinned SHA-512 SRI, bounded regular contained archive extraction and
a verified temporary CLI; never a global install or PATH replacement. Pins and
the scoped registry are verified; install/pack/publish scripts are disabled.
The credential-free download is exactly
`https://registry.npmjs.org/npm/-/npm-11.19.1.tgz`, bound to
`sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g==`.
Archive path-containment and the resolved executable are verified before use.
`npm audit signatures` and SLSA checks bind source, builder, payload and commit;
OIDC provenance is the approved publication identity. Credential rotation or
revocation occurs in the organization Actions secret store, never through a
repository change or fallback credential. Pin changes need fresh review.

Codex distribution uses the protected `codex-distribution` environment's six
named values: `CODEX_DISTRIBUTION_APP_ID`, `CODEX_DISTRIBUTION_APP_INSTALLATION_ID`,
`CODEX_DISTRIBUTION_APP_PRIVATE_KEY`, `CODEX_RULESET_VERIFIER_APP_ID`,
`CODEX_RULESET_VERIFIER_APP_INSTALLATION_ID`, `CODEX_RULESET_VERIFIER_APP_PRIVATE_KEY`.
Do not fall back to arbitrary repository/org secrets or local files. The
separately user-authorized initial Codex npm organization token remains a
recorded broader exposure/unknown-privilege residual; do not falsely describe
it as environment-narrowed.

The authorization for the first `@arbiterforge/ca-codex` publication recorded
that the token was available to all organization repositories, with unknown
npm privilege scope. Preserve that attribution; it is not a claim that the
current deferred Codex publication workflow receives the token. When that
authorized boundary is exercised, expose NODE_AUTH_TOKEN only in the authenticated publish step.
Public cold install uses token-free npm configuration and exact retained package
bytes; publication and channel advancement still require their owning checks.

Publisher and verifier Apps have distinct positive IDs and process environments.
Publisher: Actions read, Contents read/write, Metadata read, sole non-admin
ruleset bypass. Verifier: Administration read/write and Metadata read, no
Contents write and no bypass. Ordinary GITHUB_TOKEN stays read-only except the
specifically owned Pi release job's Actions-read/Contents-write scope for draft
Release access. Temp private keys use restrictive permissions, short-lived
SHA-256 JWTs, verified TLS API calls and exit cleanup; only masked token outputs
cross the intended step handoff. Job-scoped OIDC availability to all steps is
an accepted residual, not a step-local capability.

Release-target rows declare `pre-tag`, `rebuild`, `generate` and optional
`release-build` as operator-authored executable inputs, length-capped to 1,024
characters. Release hashes bind the ordered `pre-tag` list plus `release-build`,
`rebuild` and `generate`; changing any one invalidates the per-target
confirmation. Read every declared executable input before recording that
confirmation, and check it before the first executable declaration runs.
Dry runs only list the commands and never mint a durable confirmation. `pre-tag` is
check-only and mechanically guarded by `run-pre-tag`. The reviewed hosted-build
path runs `release-build` only in the exact-candidate publisher, with a newly
empty `RELEASE_ASSET_DIR`, a clean tracked tree before and after, and exact
asset-inventory verification.

The alternative retained-cohort path treats its exact fail-closed sentinel as
policy, never as a locally runnable builder. It accepts only retained CI packages
whose digests, receipts, source commit and flat names bind to the exact candidate;
arbitrary build failures cannot select this exception. H-22 protects the declaring
file with its actual authoring marker. This remains a cooperative governance
boundary, not shell sandboxing or filesystem confinement. Package identity,
deterministic contents, registry ownership, provenance and public cold install
are verified before marketplace promotion. Preserve explicit publication
authorization and exact distributed-byte readback.

## Boundary crossings

Farm stages explicit worker paths, never blanket `git add -A`. Its unattended
dispatcher commits use the accepted NOSIGN path; the integration PR carries the
reviewed signed artifact. Operator-authored plan gate/test commands and
`FARM_MUTATION_CMD` use the accepted shell execution path, bounded to 1,024
characters; this is not authority to execute untrusted source as shell text.

Historical explicit attestation adapters remain available with their recorded
limits: the verifier script is pinned but its interpreter is selected by name;
unresolvable live request/spool handling, registry publication, stop-before-bind
ordering, live-workspace review reads and session/CLI-defined reviewer shadows
have separately tracked residuals. Pi has no equivalent hook-captured
verification/review producer. Do not erase those findings because ordinary
progress no longer requires the producers, and do not describe their unkeyed
records as protection against a malicious parent.

The Codex self-hosted desktop/device-auth/VM/OIDC proof boundary was retired by
ADR-0032; static hosted package inspection is its current release boundary.
The sandbox pipe-to-shell nixpacks installer was removed; existing builder
detection and fallback do not reopen that exception. Historical records retain
these closures without reintroducing their old machinery.

## Evidence owners

Use the retained ADRs and owning source/tests for details rather than adding
successive snapshots to this document: ADR-0010 (cooperative boundary), ADR-0019
(Pi broker), ADR-0029/0032/0034/0040 (publication history), ADR-0031 (shared kernel),
ADR-0038 (bounded platform recovery), ADR-0043 (assistive engine),
`core/pysrc/_protectedstatelib.py`, hook guard/cold-install tests,
`plugins/ca-pi/tools/src/`, sandbox mount/run tests, native store/render/recovery
tests, and `.github/workflows/` with their contract tests. Retain original
attribution and historical evidence in Git/ADRs/logs when refreshing current
guidance; this document does not decide unresolved product policy.
