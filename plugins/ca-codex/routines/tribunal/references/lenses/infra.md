# infra — lens mandate

Executed by `tribunal-lens-reviewer` under the `infra` assignment.

## Purpose / failure family
Find unsafe build, deployment and publication boundaries, or configuration
failures that compromise the promised runtime/release behavior.

## Applicability
The assigned scope includes CI, containers, infrastructure configuration,
deployment or release automation with meaningful trust or lifecycle boundaries.

## Skip conditions
No affected pipeline/deployment surface. Do not infer a hosted-service posture
for a local development fixture or a declared disposable environment.

## Scope emphasis
Workflow event to credential/artifact/publish boundary; container and deploy
configuration to actual exposed service, privilege and resource lifecycle.

## Required reading
- Finding record ([routines/tribunal/references/finding-record.md](../finding-record.md)) and review risk ([routines/tribunal/references/review-risk.md](../review-risk.md)).
- `<project-root>/.codearbiter/security-controls.md` — pipeline trust and secret
  boundaries; `<project-root>/.codearbiter/tech-stack.md` — deploy targets,
  CI/release contracts and applicable protections.

## Deterministic probes
Inspect workflow triggers/permissions, action/image references, cache/artifact
producers and consumers, publish conditions, container users/mounts and deploy
exposure. Use existing configuration/provenance receipts; do not trigger jobs.

## Review questions
- Can untrusted event data become shell syntax, credential access or executable
  candidate code in a privileged workflow?
- Can a less-trusted cache or artifact cross into release without identity checks?
- Do masked failures or mismatched protections permit publication after failed gates?
- Are image provenance, privileges, secret layers and service exposure consistent
  with the declared threat model?
- Can deploy ordering, resource exhaustion or environment drift violate availability?

## False-positive guards / non-findings
A tag, root user or wide permission is a lead, not automatic exploitability.
Establish the reachable event, actual credential scope and accepted controls.
Inherited protections require evidence; unavailable remote settings remain
unverified rather than presumed missing or effective.

## Evidence requirements
Show the event/input-to-privilege or configuration-to-runtime trace and concrete
consequence. Absence claims state the search universe across reusable workflows,
environment/repository controls and deployment owners. Bind artifact claims to
actual identity; a successful source check does not prove published bytes.

## Exposure metric
Count of pipeline/deploy boundary paths inspected, distinguishing source
configuration from verified external settings and artifact evidence.

## Escalation / cross-lens handoff
Route application dependency trust to secrets-supply and incomplete propagation
to change-closure. Corroborate one root defect when bad artifact trust also
appears as a release-closure issue.

## Out of scope
Changing infrastructure, running jobs, application dependency audits and severity
based solely on a configuration signature.
