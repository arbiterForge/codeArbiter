# secrets-supply — lens mandate

Executed by `tribunal-lens-reviewer` under the `secrets-supply` assignment.

## Purpose / failure family
Find unsafe secret/crypto flows and dependency identity, provenance or use that
creates a concrete trust, exposure or distribution failure.

## Applicability
Assigned code/configuration handles sensitive values or cryptographic operations,
or depends on external packages/artifacts.

## Skip conditions
No relevant secret, crypto or dependency boundary. Unavailable registry or
advisory evidence is a stated limitation, not a clean result or a missing package.

## Scope emphasis
Manifests/locks and their intended registries, runtime/build dependency uses,
secret sources through logs/transmission/storage, and shipped artifact contents.

## Required reading
- Finding record (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/finding-record.md`) and review risk (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/review-risk.md`).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — approved secret stores,
  crypto, registries and trust exceptions; `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md`
  for dependency graphs, build/runtime roles and distribution model.

## Deterministic probes
Inspect lock/manifest consistency, package identity/resolution and redacted secret
pattern results. Registry-existence, advisory and provenance lookups use available
evidence or independently authorized probes, with registry/version/time recorded.
Do not install a package or execute its scripts to inspect it.

## Review questions
- Does the named package/version exist in the intended registry, and does a
  confusable identity or provenance substitution change the trust assumption?
- Is dependency use necessary to the behavior, or does a concrete unnecessary
  privilege/attack surface result? What reaches the built or shipped artifact?
- Does actual vulnerable package use make an advisory applicable?
- Can a real secret escape into logs, URLs, storage, artifacts or an unintended
  recipient? Are TLS, randomness and cryptographic choices fit for their contract?

## False-positive guards / non-findings
Clearly inert fixture values and credential-free examples are not leaked secrets.
An HTTP body over required TLS is not inherently a disclosure. A public-registry
miss does not prove absence from an intended private registry or workspace alias.
Package age, dependency count or supposed model training history is not a defect.

## Evidence requirements
Show the exact package/registry/version or redacted source-to-sink secret flow,
applicable policy and consequence. Never reproduce raw credentials in findings.
For absence, state the search universe across locks, registry resolution,
wrappers, redactors and artifact producers and identify the owning boundary.

## Exposure metric
Report dependency identities and sensitive-data flow paths examined separately,
including unavailable external checks.

## Escalation / cross-lens handoff
Infra owns pipeline credential/artifact trust and appsec owns application
injection/authorization. Send incomplete package propagation to change-closure;
consolidate shared exposure causes instead of duplicating findings.

## Out of scope
Installing or updating dependencies, secret extraction, authorship inference
and pipeline defects owned by infra.
