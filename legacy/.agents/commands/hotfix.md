<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: hotfix.md
-->

# /hotfix "reason" --severity P0|P1 --escalation-tier <user> --auto-revert-window 24h|72h|7d

## Purpose

Emergency-bypass channel for P0/P1 incidents where waiting on the full gate suite
would extend production harm. Unlike `/override` (a per-action escape hatch),
`/hotfix` is a **two-person, time-boxed, post-hoc-audited** bypass: it requires a
second-identity attestation, records an auto-revert deadline, and mandates a
post-hoc ADR within 72 hours.

Hotfixes are never silent. Every invocation appends to
`${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` and is surfaced at the next `/checkpoint`.

## Usage

```
/hotfix "auth service returning 500 for all tenants — rollback blocked by failing migration-reviewer" \
  --severity P0 \
  --escalation-tier "j.smith@example.com" \
  --auto-revert-window 72h
```

### Required Arguments

| Arg | Values | Meaning |
|---|---|---|
| `"reason"` | free-form string | What is being bypassed and why the incident justifies skipping the gate. Vague reasons ("prod is down") are rejected. |
| `--severity` | `P0` or `P1` | Incident severity. P0 = customer-facing outage or data-integrity event. P1 = severe degradation. Anything lower MUST NOT use `/hotfix` — use `/override` instead. |
| `--escalation-tier` | identity string (email or username) | The second human attesting to the bypass. MUST differ from the auto-detected operator identity (see Identity Detection). |
| `--auto-revert-window` | `24h`, `72h`, or `7d` (default `72h`) | Wall-clock window after which `/checkpoint` will flag the hotfix as expired-without-followup and BLOCK stage promotion. |

## Routes To

Workflow implemented inline in this command body — no backing skill. The command
dispatches its own steps (see Inline Workflow below) and reads/writes
`${PROJECT_ROOT}/.agents/projectContext/hotfixes.log`.

## Identity Detection (in priority order — never ask if any succeeds)

Same path as `/override`:

1. `git config user.email` and `git config user.name` — always try first
2. `GITHUB_ACTOR`, `GITEA_TOKEN`, `GITEA_ACTOR` environment variables
3. GitHub CLI: `gh auth status` — extract logged-in username
4. If ALL detection fails → ask: "Please state your name for the hotfix log."

The result of this detection is the **operator identity**.

## Second-Identity Attestation

`/hotfix` requires a second human in the loop. The user passed via
`--escalation-tier` is the **attesting identity**.

**Hard rule:** the attesting identity MUST differ from the operator identity. If
they match — by email, by username, or by any normalized form codeArbiter can
detect — the command BLOCKS with:

```
BLOCK: second-identity attestation failed.
  operator:   <detected>
  escalation-tier: <same>
A hotfix requires a second human. Re-invoke with --escalation-tier set to a
different identity, or use /override for a single-actor bypass.
```

The second-identity check is non-negotiable. There is no flag to disable it. If
the attesting party is unreachable, the correct path is `/override` plus a
follow-up ADR — not a forged second identity.

## Log File

Appends to `${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` (append-only, never modified,
parallel to `overrides.log`).

The meta-framework does NOT pre-place `hotfixes.log`. It is created at first
invocation in a downstream project. The file is committed to the repo as a
permanent audit artifact.

### Log Entry Format

```
[ISO-8601 timestamp] | BY: <operator-name> <<operator-email>> | ATTESTED-BY: <escalation-tier> | SEVERITY: <P0|P1> | GATE: <gate bypassed> | EXPIRES: <ISO-8601 deadline> | ADR: <pending|ADR-NNNN> | REASON: <user's reason>
```

The `ADR:` field is written as `pending` at invocation time and updated in-place
**only by `/adr`** when the post-hoc ADR is authored. This is the single
exception to the append-only rule and is enforced by `/adr`, not by hand.

## Auto-Revert Window

The `--auto-revert-window` value is added to the invocation timestamp to compute
the **expiration deadline**. The deadline is written into the log entry's
`EXPIRES:` field.

After expiration:

- `/checkpoint` MUST scan `hotfixes.log` for entries past their `EXPIRES:`
  deadline with `ADR: pending`.
- Any such entry causes `/checkpoint` to flag it as **expired-without-followup**
  and BLOCK stage promotion until either:
  - the post-hoc ADR is authored (updating `ADR:` to a real ID), or
  - the bypass is reverted and a new log entry is appended noting the revert.

`/checkpoint` does NOT automatically revert code. The "auto" in
`--auto-revert-window` refers to the automatic surfacing and BLOCK, not to an
automated code revert.

## Mandatory Post-Hoc ADR

Within **72 hours** of invocation (independent of the `--auto-revert-window`
value), the operator MUST author a post-hoc ADR via `/adr` documenting:

- What gate was bypassed and why the bypass was necessary
- What the longer-term decision is (keep the change, revert, refactor, etc.)
- What signals would trigger the same bypass in the future, if any

When `/adr` is invoked for a hotfix-driven decision, it updates the
corresponding `hotfixes.log` entry's `ADR:` field from `pending` to the assigned
ADR ID.

**Failure to author the post-hoc ADR within 72h = BLOCK on stage promotion.**
`/checkpoint` enforces this independent of the auto-revert window.

## Inline Workflow

`/hotfix` dispatches the following steps in order. Each step is a hard gate —
failure halts the command.

1. **Identity detection + second-identity check.** Resolve operator identity
   via the priority sequence above. Compare to `--escalation-tier`. BLOCK if
   they are the same identity.
2. **Hotfix log entry written.** Append a new line to
   `${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` with `ADR: pending` and the computed
   `EXPIRES:` timestamp. The log write happens BEFORE the bypass is applied —
   no silent bypasses.
3. **Apply the bypass.** Proceed with the gated action that triggered the
   hotfix.
4. **Record the auto-revert deadline.** Confirm the `EXPIRES:` field in the
   log entry matches the computed deadline. Surface the deadline in the
   response.
5. **Surface to operator.** Emit:

   ```
   Hotfix recorded.
     log:      ${PROJECT_ROOT}/.agents/projectContext/hotfixes.log
     attested: <escalation-tier>
     expires:  <ISO-8601 deadline>
   Post-hoc ADR required by <ISO-8601 72h-deadline>.
   /checkpoint will BLOCK promotion until the ADR exists.
   ```

## Hard Gates

- MUST detect operator identity before writing the log entry.
- MUST verify `--escalation-tier` differs from operator identity. BLOCK on
  match.
- MUST write to `${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` BEFORE applying the
  bypass.
- MUST include severity, escalation-tier, and a justification. Vague reasons
  are rejected.
- MUST emit the post-hoc-ADR deadline in the response.
- The hotfix is scoped to the immediate action only — it does not create a
  standing exception.

## Differences from /override

| Dimension | `/override` | `/hotfix` |
|---|---|---|
| Intended use | Per-action escape hatch for any gate | P0/P1 incidents only |
| Identities required | One (operator) | Two (operator + escalation-tier) — MUST differ |
| Severity flag | None | `--severity P0\|P1` required |
| Time-boxed | No | Yes — `--auto-revert-window` (24h/72h/7d) |
| Post-hoc ADR | Optional | **Mandatory within 72h** |
| Log file | `${PROJECT_ROOT}/.agents/projectContext/overrides.log` | `${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` |
| Checkpoint behavior | Surfaced at next checkpoint | Surfaced + BLOCKS stage promotion if expired or ADR-missing |
| Reversibility framing | Justification-based | Deadline-based; expiration forces resolution |

If you are reaching for `/hotfix` but the incident is not P0 or P1, use
`/override` instead. If you are reaching for `/override` but cannot reach a
second human, that is the correct call — do not synthesize a second identity to
unlock `/hotfix`.

## See Also

- `/override` — single-actor escape hatch with audit log
- `/adr` — authors the mandatory post-hoc decision record and updates the
  `hotfixes.log` entry's `ADR:` field
- `/checkpoint` — enforces expiration and post-hoc-ADR gates; BLOCKS stage
  promotion when either is unsatisfied
