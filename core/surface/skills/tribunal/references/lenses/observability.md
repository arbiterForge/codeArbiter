# observability — lens mandate

Executed by `tribunal-lens-reviewer` under the `observability` assignment.

## Purpose / failure family
Find failures operators or callers cannot diagnose, correlate or recover from
despite an applicable operational or audit obligation.

## Applicability
The product's operating model requires diagnosis, correlation, security/audit
events or failure visibility at the assigned boundary.

## Skip conditions
Local libraries or pure helpers with no operational/diagnostic contract need not
have tracing or metrics. Record a skip when diagnosis is adequately owned by
the caller and no separate obligation applies.

## Scope emphasis
Critical failure/recovery paths and service/async boundaries where actionable
reason, correlation or audit completeness is required.

## Required reading
- Finding record (`{{PLUGIN_ROOT}}/skills/tribunal/references/finding-record.md`) and review risk (`{{PLUGIN_ROOT}}/skills/tribunal/references/review-risk.md`).
- `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — logging/tracing/metrics stack
  and operating model; applicable runbook/audit contracts and inventory boundaries.

## Deterministic probes
Inspect event/error emission, correlation propagation and diagnostic consumers.
Compare declared event requirements with existing logging/audit tests and
operational evidence; event counts do not prove diagnostic usefulness.

## Review questions
- Can an operator distinguish the critical failure reason and select recovery?
- Is required correlation preserved across the actual async/service boundary?
- Are security/audit outcomes complete enough for the declared forensic purpose?
- Are diagnostic details bounded and appropriate to the recipient?
- Does a suppressed or misleading success signal hide a relevant failure mode?

## False-positive guards / non-findings
No universal tracing, structured-logging or metrics requirement applies.
Central instrumentation and returned errors may satisfy a boundary's obligation.
Do not propose logging every call or emitting duplicate diagnostics without
showing which real failure would remain undiagnosable.

## Evidence requirements
Cite the required operational/audit obligation, failure scenario and unavailable
diagnostic or recovery decision. For missing signals, state the search universe
and ownership trace through emitters, middleware, collectors and callers; include
available evidence about retention/visibility without assuming remote settings.

## Exposure metric
Count of applicable failure/audit boundary paths whose diagnostic outcome was
traced, not raw log statements.

## Escalation / cross-lens handoff
Send sensitive-data logging to secrets-supply and the underlying lost operation
to reliability. Keep a diagnostic consequence as corroboration when it shares
the same root failure rather than filing duplicate findings.

## Out of scope
Tracing for its own sake, correctness of the logged operation, and independent
secret disclosure findings.
