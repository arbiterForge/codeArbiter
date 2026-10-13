# appsec — lens mandate

Executed by `tribunal-lens-reviewer` under the `appsec` assignment.

## Purpose / failure family
Find exploitable trust-boundary violations: unauthorized resource access,
injection, privilege confusion and untrusted data promoted to instructions.

## Applicability
Untrusted input, authenticated identities, resources or privileges cross an
application boundary in the assigned finding scope.

## Skip conditions
No relevant untrusted input or privilege boundary. Record the actual trust model;
do not assume every internal helper is directly attacker-controlled.

## Scope emphasis
Entry points through middleware, validation and policy to the resource or sink.
Include direct consumers needed to evaluate enforcement ownership.

## Required reading
- Finding record (`{{PLUGIN_ROOT}}/skills/tribunal/references/finding-record.md`) and review risk (`{{PLUGIN_ROOT}}/skills/tribunal/references/review-risk.md`).
- `{{PROJECT_DIR}}/.codearbiter/security-controls.md` — declared boundaries,
  accepted residual risks and approved patterns; inventory trust map and relevant
  authentication, authorization and public endpoint contracts.

## Deterministic probes
Inspect routes, policy/middleware chains, sink locations and input transformations.
Use available static scan results as candidates and validate the path to the
sink; inspect token settings and privilege transitions without exposing secrets.

## Review questions
- Can a principal access or mutate another principal's resource despite valid
  authentication? Where is resource-level authorization enforced?
- Does attacker-controlled data reach SQL, shell, HTML, path, deserialization
  or SSRF sinks after all validation, encoding and policy checks?
- Are session/token signature, expiry, issuer, audience and algorithm promises
  enforced where applicable?
- Can business-logic sequencing cross privileges or bypass validation?
- Can agentic input, retrieved text or tool output become execution/scope authority?

## False-positive guards / non-findings
A public credential-free endpoint may intentionally use a CORS wildcard.
Concatenation, a wildcard, or a scanner signature alone establishes neither
exploitability nor severity. Central middleware, parameterization or validated
construction may close the boundary; trace it before alleging missing control.

## Evidence requirements
Identify attacker capability, actual reachability, trust boundary, missing or
bypassed control and exploitable consequence. For absent authorization/validation,
state the search universe and ownership trace across routes, middleware and
resource policy. Derive severity from demonstrated impact and likelihood.

## Exposure metric
Count of distinct trust-boundary paths inspected from input/principal to
resource/sink, with untraced paths called out.

## Escalation / cross-lens handoff
Route secret flow and dependency trust to secrets-supply, pipeline attacks to
infra and non-security failure semantics to reliability. Serious candidates
require workflow verification before confirmed filing.

## Out of scope
Signature-only severity, arbitrary attack execution and standalone secret,
dependency or generic error-handling findings.
