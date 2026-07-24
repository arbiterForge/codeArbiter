# infra — lens mandate

Executed by `tribunal-infra-reviewer`. Write contract + evidence discipline: `finding-record.md`.

## Checklist
- CI/CD workflows: untrusted input (PR titles, branch names, comments) interpolated into `run:` steps; excessive workflow/token `permissions`; third-party actions pinned to tags, not SHAs; fork-writable cache keys (poisoning); artifacts promoted without provenance; masked failures (swallowed exit codes) ahead of a publish step.
- Container posture: base image unpinned or of unvetted provenance; running as root; secrets baked into layers or build args.
- IaC/deploy manifests: drift between environments; missing resource limits; services exposed wider than intended.
- Release automation: publish/tag steps ungated by branch or tag protections.

## Categories & severity
`security` for exploitable pipeline issues (injection, token overreach, cache poisoning); `dependency` for provenance/pinning; `reliability` for deploy-config correctness. Exploitable-from-fork is critical/high.

## Exposure
Count of workflows + Dockerfiles/compose files + IaC/deploy manifests examined.

## Out of scope
Supply-chain risk of app dependencies (secrets-supply) — this lens owns the pipeline and deploy surface itself.
