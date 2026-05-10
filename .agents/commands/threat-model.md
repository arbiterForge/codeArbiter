# /threat-model "scope description"

## Purpose

Run a pre-implementation security architecture review for a proposed feature, zone crossing, or attack surface change. STRIDE analysis. Must run **before** implementation begins whenever new trust zone crossings, new external endpoints, new secrets handling paths, or new authentication/authorization flows are introduced.

## Usage

```
/threat-model "description of what is being built or changed"
```

The description should include: what the component does, which trust zones it touches, what data it handles, and which actors interact with it.

## Routes To

`security-architecture` skill (`.agents/skills/security-architecture/SKILL.md`).

Also reads:
- `projectContext/trust-zones.md` — required before any analysis begins
- `projectContext/security-controls.md` — compliance requirements and controls
- `projectContext/decisions/` — existing ADRs relevant to security posture

## What Happens Step by Step

1. codeArbiter reads `projectContext/trust-zones.md` — full read required before analysis
2. `security-architecture` skill identifies all trust zone crossings the proposed change introduces or modifies
3. STRIDE analysis runs for each crossing:
   - **S**poofing — can an actor impersonate another? What controls prevent it?
   - **T**ampering — can data be modified in transit or at rest? What controls prevent it?
   - **R**epudiation — can actions be denied? What audit controls exist?
   - **I**nformation disclosure — what data is exposed? To which actors? Is it classified?
   - **D**enial of service — can the crossing be overwhelmed or blocked?
   - **E**levation of privilege — can the crossing be used to gain unauthorized permissions?
4. For each identified threat: threat description, likelihood, impact, mitigating control (or "none — needs control")
5. Undeclared egress check — any network path not in `projectContext/trust-zones.md` is flagged as BLOCK
6. Output: threat model report with findings and recommended controls

## Output Structure

```
## Scope
<what is being analyzed>

## Trust zone crossings identified
- <Zone A> → <Zone B>: <mechanism>

## STRIDE findings
| Threat | Category | Likelihood | Impact | Control |
|--------|----------|------------|--------|---------|
| ...    | S/T/R/I/D/E | H/M/L  | H/M/L  | <control or NONE — needs control> |

## Undeclared egress
<list or "none identified">

## Recommended controls before implementation
- <control 1>
- <control 2>

## Clearance status
CLEAR TO IMPLEMENT | BLOCKED — resolve findings first
```

## Hard Gates

- MUST run BEFORE implementation begins for any new trust zone crossing
- MUST run BEFORE implementation begins for any new external endpoint
- MUST run BEFORE implementation begins for any new secrets handling path
- Any undeclared egress BLOCKS implementation — must be declared in `projectContext/trust-zones.md` first
- If status is BLOCKED: implementation MUST NOT begin until user resolves each blocking finding
- This command is read-only — it does not modify any file

## When NOT to Use

- For reviewing already-written code: use `/review`
- For a full checkpoint: use `/checkpoint`
- For a question about trust zones: use `/btw`
