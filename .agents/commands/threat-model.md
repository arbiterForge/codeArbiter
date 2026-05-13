<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: threat-model.md
-->

# /threat-model "scope description"

## Purpose

Pre-implementation security architecture review for a proposed feature, zone crossing, or attack surface change. STRIDE analysis. Must run **before** implementation begins whenever new trust zone crossings, new external endpoints, new secrets handling paths, or new auth/authz flows are introduced. Read-only — does not modify any file.

## Usage

```
/threat-model "description of what is being built or changed"
```

Description should include: what the component does, which trust zones it touches, what data it handles, which actors interact with it.

## Routes To

`security-architecture` skill (`${FRAMEWORK_ROOT}/.agents/skills/security-architecture/SKILL.md`). Skill reads:

- `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` — required before any analysis begins
- `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` — compliance requirements
- `${PROJECT_ROOT}/.agents/projectContext/decisions/` — existing security-relevant ADRs

## Output format

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

## When NOT to Use

- Reviewing already-written code: `/review`
- Full checkpoint: `/checkpoint`
- Question about trust zones: `/btw`
