# Reviewer contract — findings format, output template, out-of-scope rule

For every security policy reference below, follow `{{PLUGIN_ROOT}}/includes/knowledge.md`
("Read security policy before a security decision"): select the repository's
context format, read the complete policy from exact `CTX-SECURITY-CONTROLS`
records in HTML mode or the full Markdown controls in Markdown mode, and read
operative scope blocks when applicable. Required policy that is missing or
unreadable blocks a security decision; scope blocks alone are not full policy.

Canonical for every gate reviewer agent (`security-reviewer`, `auth-crypto-reviewer`,
`dependency-reviewer`, `migration-reviewer`, `coverage-auditor`). Loaded via each agent's
Required Reading; the agent bodies do not restate these blocks. An agent body MAY narrow the
subject field or add fields and heading qualifiers — additions extend this contract, never
replace it.

## Findings format

```
**Severity:** CRITICAL | HIGH | MEDIUM | LOW
**File:** <path>:<line>
**Description:** <specific problem — no vague claims>
**Remediation:** <concrete fix>
```

Agent-specific deltas declared in the agent body (examples): `security-reviewer` and
`auth-crypto-reviewer` add a `**Control:**` line citing
`{{PROJECT_DIR}}/.codearbiter/security-controls.md`; `dependency-reviewer` uses
`**Package:** <name@version>` as the subject field; `coverage-auditor` uses
`**File:** <source path> / <test path, if exists>`.

## Severity and gate

Severity is one scale with one meaning in every reviewer: any **CRITICAL** or **HIGH** finding
blocks (gate status BLOCK); **MEDIUM** and **LOW** never do. An agent body may not declare a
non-blocking HIGH; where a risk should not block, the body assigns a lower severity by a closed,
named rule. The only such rule today: dependency-reviewer's maintenance-only risk (unmaintained or
abandoned, no security finding) is **MEDIUM**; a finding that mixes maintenance with a security
problem keeps the security severity (D-HIGH, B 2026-11-12). Resubmitting or reformatting a report
with unchanged findings cannot change their severity or gate disposition.

## Review output template

```
## <Role> Review — <date>

### CRITICAL findings (N)
[findings or "none"]

### HIGH findings (N)
[findings or "none"]

### MEDIUM findings (N)
[findings or "none"]

### LOW findings (N)
[findings or "none"]

### Gate status
PASS (no CRITICAL or HIGH) | BLOCK (N CRITICAL, N HIGH must resolve before merge)
```

`<Role>` is the reviewer's own review name (Security, Auth/Crypto, Dependency, Migration,
Coverage); an agent body may qualify the heading (e.g. the dependency review includes
`<package@version>`).

## Out-of-scope findings

**Out-of-scope finding:** do not act on it and do not author an ADR for it (ADRs are
user-attributed, via `/adr` only). Mark it inline with a `[NEEDS-TRIAGE]` marker; never
silently drop it.

## Corrected review submissions

A rejected request remains terminal. Where the installed authority adapter owns
the review, use its internal `artifact-authority.py resubmit-review --root
<project> --request-id <unsuccessful-original> --operation-id <stable-correction-id>
--correction report-correction|target-correction|operational-recovery` route for
a corrected logical submission. The adapter admits only known correctable
review failures or validated recovery states. Explicit user/host denials,
stops, unknown failures and ambiguous launch responses remain unavailable;
this route cannot restore permission. Ordinary host permissions still govern
the actual launch and every later action.

Keep the original request and rejected history. The new request captures the
current frozen target, contract and selected context; launch its exact envelope
with a fresh independent child and retain its actual first terminal result.
Never relabel a later stop from the original child as `first_stop`, steer that
child into a replacement result, or treat request creation as a passing receipt.
`changes_requested` and `BLOCK` require fresh substantiated review; resubmission
alone changes neither findings nor gate disposition. Severity rules above apply.

Reuse the same operation ID after a lost response. An immutable, separately
versioned intent and successor link recover the same request even if arming or
the link response was interrupted. The response distinguishes transport replay
from a new correction and returns a launch envelope only while the successor
is `ARMED`; it never launches a child itself. Changed operation inputs or a
changed context/contract before arming require a new correction operation after
the actual change. Retry an unchanged uncertain publication with its original
request/operation, not a new review. Completion review additionally requires
explicit current `--completion-receipt` selections and any `--supporting-file`
inputs; old completion evidence is not silently inherited.

Lineage metadata lives in the existing Git-common authority spool under
`review-resubmissions/v1/`, outside the closed request and native observation
schemas. Old readers ignore it. Rollback may stop new resubmissions; it must
retain those links, terminal originals and already observed successor results.
