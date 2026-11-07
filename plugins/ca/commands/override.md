---
description: Sanctioned, logged bypass of a gate or hard rule — one audit line, then proceed.
argument-hint: "<reason>"
---

# /ca:override — logged bypass

The sanctioned escape hatch. Bypass is permitted only with an audit log entry. Overrides are always
logged, always visible, never silent. Single identity, single confirm.

## Flow

1. Validate `$ARGUMENTS` — the reason names the gate being bypassed and a justification. Reject a
   vague reason ("just skip it") and ask for a specific one.
2. Detect the operator identity from `git config user.email` only. If it is unset, ask the user once
   to state their identity for the log. (No platform ladder, no second confirmation.)
3. For an ordinary override, use the private locked audit helper from the repository root.
   `--gate` takes a compact gate identifier, not a description: it starts with an ASCII
   letter or digit and uses only ASCII letters and digits, `.`, `_`, `:` and `-`, with no
   spaces, up to 128 characters, for example `lint:max-line-length` or `coverage-threshold`.
   The helper refuses anything else. Put the human explanation in `--reason`. A security
   gate such as H-09b/H-10b never takes this path; see the security ceiling below.

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/append-override.py" --gate "<gate-id>" --reason "<specific reason>"
   ```

   It appends one line to `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log`:

   ```
   [ISO-8601 timestamp] | BY: <email> | GATE: <gate-id> | REASON: <reason>
   ```

   The log is append-only — never edited or deleted, committed as a permanent audit artifact. The
   helper fails closed if another official writer or conflict resolver owns the audit-path lock; the
   overridden action must not proceed unless the row lands. A guard-permitted raw append remains a
   cooperative operator escape hatch, but it must not run concurrently with conflict resolution.
4. A genuine three-stage Git conflict on an H-05 append-only path uses the dedicated helper instead
   of the ordinary step 3 append. Run it once from the conflicted repository, with the specific
   repo-relative path and the same reason:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-append-only-conflict.py" ".codearbiter/overrides.log" --reason "<specific reason>"
   ```

   The helper derives the same `git config user.email` identity, validates the merge-base and both
   append suffixes, writes the attributed H-05 record, and explicitly stages only the validated
   deterministic union. It refuses a missing or malformed three-stage conflict, any edit to prior
   bytes, unsupported paths, invalid encoding, dirty audit sink, or replay after resolution. This is
   scoped to the immediate action only; it creates no marker, standing exception, or general H-05
   bypass. It takes canonical per-audit-path locks and supports only `overrides.log` and the
   repository-owned `gate-events.log` sink; official writers share those locks. Conflict resolution
   is an exclusive cooperative operation: do not start a raw append before or during it. Never
   hand-resolve the protected log with Write, patch, checkout, or restore.
5. Proceed with the overridden action. Note in the response that the override is logged.

## Security ceiling — heavier path for security-critical stops

A routine gate (lint, a style rule, a non-security review finding) takes the single-confirm path above.
But a **security-critical stop is NOT bypassable by a single confirm.** The following require the
heavier path below, never the one-line flow:

- a security **CRITICAL** finding;
- the crypto/secret commit gate (hook **H-09b / H-10b** — staged crypto/TLS or secret without a gate pass);
- an **irreversible** operation (data loss, a destructive migration, anything unrollbackable).

Heavier path (all required, in order):
1. **Surface the specific finding verbatim** — name the exact primitive/secret/operation and the
   concrete risk. A generic "security override" is rejected.
2. **Explicit per-finding acknowledgement** — the user must acknowledge *that specific finding* in
   their own words (a bare "yes"/"go ahead"/"I trust you" is declined — this mirrors `decision-variance`).
   Detect identity from `git config user.email`; if unset, ask once.
3. **Choose the candidate route before writing the log.** For reviewable text, use the same locked
   helper so the mandatory row cannot race conflict resolution:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/append-override.py" --security-finding "<specific finding>" --reason "<reason>"
   ```

   It appends a line tagged `SECURITY-OVERRIDE` that records the specific finding, not just the gate name:

   ```
   [ISO-8601] | BY: <email> | SECURITY-OVERRIDE | FINDING: <specific finding> | REASON: <reason>
   ```
   If the gate explicitly reports a genuine binary whose text context is unavailable, skip this
   helper and use the combined producer in step 4; that producer writes this same row exactly once
   before it writes the distinct binary marker.
4. **Only then** record the bypass. For a reviewable-text crypto/secret commit gate, use the
   host's known Python 3 launcher in place of `python` when its literal name differs, then run
   the producer as one standalone command from the exact reviewed checkout root:

   ```sh
   python "${CLAUDE_PLUGIN_ROOT}/hooks/security-pass.py"
   ```

   Do not combine launcher discovery and the producer in one chained shell expression, and never
   use `python3 X || python X`, which reruns X on any nonzero exit (#577). The producer
   writes `${CLAUDE_PROJECT_DIR}/.codearbiter/.markers/security-gate-passed` bound to the
   sensitive lines it approves, so hook H-09b/H-10b allows the commit — recorded **only** after
   steps 1–3, never to skip the gate proper.

   If the gate explicitly reports a genuine binary whose text context is unavailable, run the
   combined audited producer below from the exact reviewed checkout root. It appends the mandatory `SECURITY-OVERRIDE` row first and
   only then writes a distinct exact-candidate binary override marker; it never represents the
   bypass as an independent-review PASS:

   ```sh
   python "${CLAUDE_PLUGIN_ROOT}/hooks/security-pass.py" --binary-override --security-finding "<specific finding>" --reason "<reason>"
   ```

Under `/ca:sprint`, a security-critical override is a hard-gate STOP: it surfaces to the user and is
**never** auto-decided, even in autonomous mode (`SPRINT.md` hard gates).

## Hard gate

MUST write the log line before proceeding — it is not optional. MUST capture an operator identity —
"codeArbiter" or "automated" are not valid. MUST include a justification. The override is scoped to
the immediate action only; it creates no standing exception. MUST NOT edit or delete an existing
`overrides.log` entry. For an H-05 three-stage conflict, the dedicated helper's validated union and
audit write are the single immediate action; do not pre-edit the conflicted file. MUST route a
security-critical / crypto-secret / irreversible stop through the
**Security ceiling** path — never the single-confirm flow — and MUST NOT auto-decide such an override
under `/ca:sprint`.

## When NOT to use

- Routine work that passes all gates — never needed.
- Reconciling two conflicting sources → `/ca:conflict`.
