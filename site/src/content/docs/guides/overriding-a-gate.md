---
title: "Override a Gate Safely"
description: "Bypass a blocked gate with /ca:override, the only sanctioned path: one audit line is appended to overrides.log, your identity comes from git config user.email, and the bypass is permanent in the trail."
---

A gate blocked your command and the action is genuinely justified. Use `/ca:override "reason"` to bypass it — the only sanctioned path, since any other bypass leaves no record in the audit trail.

Before running it, identify which kind of gate you are facing. The two paths are different.

## Before You Start

**Routine gate** — a lint rule, a style check, a scope-creep finding, a non-security review result. The single-confirm path described in [Run the command](#run-the-command) applies.

**Security-critical stop** — one of the following requires the heavier path described in [Security-critical stops](#security-critical-stops), never the single-confirm flow:

- A security CRITICAL finding.
- The crypto/secret commit gate (H-09b / H-10b): a commit introduces a banned crypto primitive or a secret line without a recorded gate pass.
- An irreversible operation: data loss, a destructive migration, anything that cannot be rolled back.

Under an autonomous `/ca:sprint` run, a security-critical stop is a hard-gate STOP. It surfaces to you and is never auto-decided.

## When Not to Override

Hard gates exist because the cost of the mistake they prevent is higher than the cost of stopping. A gate that trips often signals the spec or plan was too thin, not an obstacle to work around.

Do not use `/ca:override` when:

- The gate caught a real problem. Fix the problem instead: replace the banned primitive, correct the failing test, remove the secret.
- Routine work passed all gates. The command is not needed and running it creates a permanent log entry for no reason.
- Two sources conflict rather than one blocking the other. Use `/ca:conflict` instead.

The bypass applies only to the immediate action; future commands still hit the gate.

## Run the Command

```text
/ca:override "H-03: wildcard staging blocked — the generated migration file was omitted from the explicit list; reviewed the staged diff, this commit only"
```

The reason must name the gate and justify the action. A vague reason such as "just skip it" is rejected. codeArbiter asks for a specific one before proceeding.

## What Happens

1. codeArbiter reads your identity from `git config user.email`. If that value is unset, it asks once. No second prompt.
2. One line is appended to `.codearbiter/overrides.log`:

   ```text
   [2026-06-27T14:30:00Z] | BY: you@example.com | GATE: H-03 wildcard staging | REASON: generated migration file omitted from explicit list; reviewed the staged diff, this commit only
   ```

3. The blocked action proceeds. The response confirms that the override is logged.

The override covers only the immediate action.

## Security-Critical Stops

These require explicit per-finding acknowledgement and a heavier log entry. The single-confirm flow is not available for any of these.

1. codeArbiter surfaces the specific finding verbatim: the exact primitive, secret, or operation, and the concrete risk. A generic "security override" is rejected.
2. You acknowledge that specific finding in your own words. A bare "yes" or "go ahead" is declined, the same way `/ca:conflict` declines a bare confirmation on a contested decision.
3. codeArbiter appends a `SECURITY-OVERRIDE` line:

   ```text
   [2026-06-27T14:30:00Z] | BY: you@example.com | SECURITY-OVERRIDE | FINDING: <specific finding> | REASON: <reason>
   ```

4. Only after steps 1 through 3 does the bypass record. For H-09b / H-10b, recording the bypass means running `security-pass.py`, which writes a digest-bound gate-pass marker covering the specific sensitive lines approved. The commit gate then allows the commit for those exact lines.

## The Audit Trail Is Permanent

`overrides.log` is an append-only artifact. H-05 blocks every attempt to truncate, overwrite, or delete it at the shell, Write, and Edit flanks. An empty-`old_string` Edit on a log file is also blocked, because that operation cannot be verified as an append.

Once written, an override line cannot be removed. The log accumulates for the lifetime of the repository and is part of the governance record that `/ca:audit` assembles on demand.

## How Overrides Appear in the Statusline

If the statusline is wired in, the arbiter row shows `over:N`, where N is the count of non-comment lines in `overrides.log` recorded after the last checkpoint. The segment turns red when N is greater than zero. Running `/ca:checkpoint` resets the counter by recording the current total as the new baseline.

## Related

- [override](/reference/commands/override/) command reference
- [Enforcement & Security](/enforcement/) (H-05: append-only audit log; H-09b / H-10b: crypto and secret commit gate)
- [Concepts](/concepts/) (gate strengths, the auditability model)
- [audit](/reference/commands/audit/) command reference (assembles the governance record on demand)
