# change-closure — lens mandate

Executed by `tribunal-lens-reviewer` under the `change-closure` assignment.

## Purpose / failure family
Find changes that work at their source but fail to reach an obligated consumer,
host, generated projection, package or release surface.

## Applicability
A changed contract has declared downstream consumers or distribution obligations,
or a claimed shipped behavior requires proof across those surfaces.

## Skip conditions
No affected producer/consumer relationship or propagation obligation. Do not
invent additional supported hosts, package channels or release requirements.

## Scope emphasis
Follow canonical producer to consumer: callers, schemas, generated files, host
adapters, manifests, package contents, install/update/uninstall paths, CI gates,
release automation, migrations, compatibility and shipped operator docs.

## Required reading
- Finding record (`{{PLUGIN_ROOT}}/skills/tribunal/references/finding-record.md`) and review risk (`{{PLUGIN_ROOT}}/skills/tribunal/references/review-risk.md`).
- `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — canonical sources, generators,
  supported hosts and deployment/package boundaries.
- Relevant manifest, distribution contract, accepted decisions and inventory
  relationships; exact artifact/provenance evidence when a release is claimed.

## Deterministic probes
Compare declared producer/output maps, changed paths, package file lists,
entry-point/resource references, schema versions and available artifact digests.
Inspect generator and CI wiring as data; do not execute repository generators.

## Review questions
- Which consumers require this logical change, and which still use the old contract?
- Do generated projections and host adapters implement the same supported behavior?
- Does the package actually contain every runtime resource its entry points need?
- Can install, update, uninstall and mixed-version paths preserve compatibility?
- Does the release evidence identify the exact distributed artifact being claimed?

## False-positive guards / non-findings
An intentionally unaffected host or separately versioned consumer need not move
in lockstep. Generated differences allowed by the host contract are legitimate.
Current main does not prove release behavior. Missing release evidence is a
proof gap, not proof that a published package is defective.

## Evidence requirements
Show the declared propagation obligation, source change and stale/missing
consumer, with its user-visible consequence. An absence claim names the search
universe across canonical source, generation, packaging and runtime resolution.
Bind release claims to exact artifact identity and provenance; distinguish
source validation, candidate-package proof and published behavior.

## Exposure metric
Count of obligated producer-to-consumer relationships checked, with source,
package and released-artifact evidence levels stated separately.

## Escalation / cross-lens handoff
Route unsafe pipeline execution to infra, schema rollout hazards to migration,
and wrong source semantics to semantic-contract. Preserve unavailable-artifact
leads for the orchestrator; sharing evidence never widens filing scope.

## Out of scope
Publishing, regenerating or repairing artifacts, inferring released behavior
from repository HEAD, and unrelated consumers outside finding scope.
