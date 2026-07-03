---
title: Hardening History
description: "Design notes on why codeArbiter's enforcement gates are built the way they are, plus a dated log of hardening work as it shipped."
---

[Enforcement & Security](/enforcement/) states what is enforced. This page explains why some of those gates are built the way they are, and records the hardening work that shaped them over time.

## Why the Crypto/Secret Gate Is Digest-Bound (H-09b / H-10b)

The crypto/secret gate does not just check freshness. The crypto-compliance and secret-handling skills record a `security-gate-passed` marker holding the **digest of every sensitive line the gate approved**. At commit time, `pre-bash.py` requires both:

- **freshness** (the marker is under 30 minutes old), and
- **coverage** (every sensitive line in the diff being committed hashes to a line in the approved set).

Coverage is what closes the time-of-check / time-of-use window: a pass minted for one diff cannot launder a *different* diff committed inside the freshness window. The scan reads the staged diff, plus the worktree diff when the commit uses `-a`/`--all`, stages files in the same command, or names a `git commit <pathspec>` (whose worktree content the `--cached` scan would miss).

The gate fails closed when the diff cannot be read. If git is unavailable or times out, `added_lines()` returns `None` (distinct from an empty diff), and codeArbiter treats that as a reason to block the commit rather than wave it through. H-14's file-list read follows the same fail-closed rule.

The detection corpus is shared: `CRYPTO_RE` and `SECRET_RE` live once in `_hooklib.py`, so the redactor and the gate stay aligned on what counts as crypto or a secret — there is exactly one place either pattern set can be edited, and both consumers pick up the change together.

## Why the Board Has One Writer (ADR-0008)

`open-tasks.md` has one sanctioned writer: `/ca:task`. No other agent, hook, or workflow modifies that file directly. The three mutations it performs are a queued add (a new task in `[ ]` state), the start-flip (`[ ]` to `[~]` with a stamped date), and the done-flip (`[~]` to `[x]`).

The commit gate is the single board-sync chokepoint. Phase 6 of the commit-gate skill identifies a schema-valid board transition and exempts it from the scope-creep check; Phase 7 stages it alongside the work. The board flip lands atomically with the code it describes: an abandoned PR abandons the flip with it, and there is no window where the board reads done while the corresponding work is not yet merged.

This design replaced an earlier pattern of a separate, lagging `chore(board)` PR that could drift from the code it described. Cross-session board drift — a task left open after its work lands — is now eliminated by construction rather than by process discipline. See ADR-0008 for the full design rationale.

`/ca:standup` and `/ca:doctor` each run a read-only reconciliation sweep and surface any merged-but-not-flipped task; they report findings without writing to the board themselves.

## Hardening Log

Dated record of enforcement hardening as it shipped, newest first. Versions correspond to `CHANGELOG.md` entries in the repository root.

- **v2.5.2 (2026-06-25)** — Broadened crypto detection: `CRYPTO_RE` now flags `rc2` and `blowfish` alongside MD5, SHA-1, DES, 3DES, and RC4, plus TLS-disable forms (`rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED`, `verify=False`, `InsecureSkipVerify`).
- **v2.5.2 (2026-06-25)** — Compound-name secret detection: `SECRET_RE` now matches compound keys (`aws_secret_access_key`, `client_secret`, `private_key`) and known token shapes (`AKIA…`, `ghp_…`, `sk-ant-…`).
- **v2.5.2 (2026-06-25)** — Gate-pass markers became atomic and digest-bound, so an unrelated edit inside the freshness window no longer inherits an unrelated approval.
- **v2.5.2 (2026-06-25)** — Audit-path sets centralized: `AUDIT_LOG_NAMES` and the decisions-path tokens live once in `_hooklib`, so the shell, Write, and Edit flanks can no longer disagree on which files are append-only.
- **v2.5.2 (2026-06-25)** — `ca-sandbox` isolation hardened for untrusted repositories: non-root (`--user 1000:1000`), `--read-only` root, `--cap-drop ALL`, `--security-opt no-new-privileges`, and a fail-closed network policy (default `--network none`; an unknown policy is a hard error rather than a silent pass-through). No host bind mounts; the docker socket is never mounted.

## Related

- [Enforcement & Security](/enforcement/) — the user-facing statement of what is enforced.
- [ADRs and the Decision Log](/concepts/adrs/)
- [Hooks reference](/hooks/)
