# Spec — Migration commit-time backstop

**Source:** issue #77 (routing/firing audit). Decided **option (a)** via SMARTS
(strength `moderate`, 2026-06-19): build the backstop rather than accept the residual
risk. Securable + Reliable + Testable favored (a); precedent DECISION-0003 (closed an
analogous commit/call-time bypass bound to approved content).

## Problem

A database migration can reach a commit with **no migration review**. When a migration
is committed via bare `/ca:commit` or the `/feature` small lane, commit-gate Phase 6
diff-review checks secrets and scope-creep but never classifies a migration, and **no
hook fires** (`grep migration hooks/` = zero). The data-classification and
destructive-schema review that the `migration-reviewer` agent performs is silently
skipped on that path. The `/review`, `/checkpoint`, `/pr`, and sprint lanes already
dispatch `migration-reviewer`; this is the narrow gap on the commit-only paths.

## Scope

**In scope**

- A commit-time **backstop** that blocks committing a staged migration file unless a
  recorded migration-review pass covers that file's exact content — mirroring the
  H-09b/H-10b security-gate pattern (`hooks/security-pass.py` + `pre-bash.py`).
- **Hybrid migration-path detection**: a built-in default glob set, extendable and
  narrowable by a per-project declaration in `security-controls.md`.
- A **self-healing** commit-gate path: commit-gate detects a staged migration,
  dispatches `migration-reviewer`, and records the marker on PASS.
- **Content-digest binding, no time window**: the marker holds each approved
  migration's file-content digest; it is valid as long as content is unchanged. An
  edit to a reviewed migration changes the digest → BLOCK (enforces immutability and
  closes TOCTOU for free).

**Out of scope (the honest boundary)**

- NOT a migration runner, schema linter, or re-implementation of `migration-reviewer`'s
  checks in the hook — the hook only enforces *that the review happened* and is bound
  to this content.
- NOT a test-executing commit hook — it stays cheap (marker check only), so it does
  not trigger the "slow and invasive" concern behind deferred finding #6.
- NOT a change to the `/pr`, `/review`, `/checkpoint`, or sprint lanes, which already
  dispatch `migration-reviewer`.
- NOT dogfooded in this repo: codeArbiter is database-free (DECISION-0004) and has no
  migrations. The feature is validated entirely by hook-test fixtures with synthetic
  migration paths.

## Design (settled by brainstorming forks)

- **Detection** lives in `_hooklib.py` as a shared `is_migration_path(rel, root)`,
  consumed by both the producer and the backstop. Default globs cover the common
  ecosystems: `**/migrations/**`, `**/migrate/**`, `**/db/migrate/**`, Alembic
  `**/alembic/versions/*.py`, Prisma `**/prisma/migrations/**`. A
  `security-controls.md` declaration block extends the set (additional globs) and/or
  narrows it (exclusion globs) — the false-positive escape hatch. Declaration format
  is stdlib-regex-parseable from the prose file (no YAML dependency).
- **Producer** `hooks/migration-pass.py`: scans staged migration files (plus
  worktree/untracked under `-a`, mirroring `security-pass.py`'s candidate scan),
  writes their content digests to `.codearbiter/.markers/migration-gate-passed`.
  Idempotent. Run by the dispatching prose on `migration-reviewer` PASS.
- **Backstop** in `pre-bash.py`: on `git commit`, for each staged migration file whose
  content digest is not in the marker, BLOCK with a new `H-NN` tag (next free integer,
  assigned at implementation by scanning `pre-bash.py`). No freshness window — coverage
  is by content digest only.
- **Prose wiring**: commit-gate gains a migration-classification step that, on a
  detected staged migration, dispatches `migration-reviewer` and runs
  `migration-pass.py` on PASS — exactly how crypto-compliance/secret-handling run
  `security-pass.py`.
- **stdlib-only** (DECISION-0004); dormant outside an `arbiter: enabled` repo,
  consistent with the rest of `pre-bash.py`.

## Acceptance criteria

Each criterion is verifiable by a single test → one `tdd` Phase 1 obligation.

1. **Default-glob detection** — `is_migration_path` returns True for `db/migrate/20240101_x.rb`,
   `migrations/0001_init.py`, `alembic/versions/abc_x.py`, and
   `prisma/migrations/2024_x/migration.sql`; returns False for `src/app.py` and
   `docs/migrations-guide.md`.
2. **Override extends** — given a `security-controls.md` declaration adding
   `schema/changesets/**`, a staged `schema/changesets/v5.sql` is detected as a migration.
3. **Override excludes** — given a declaration excluding `migrations/seed/**`, a staged
   `migrations/seed/data.sql` is NOT detected (false-positive escape hatch).
4. **Producer records content digest** — running `migration-pass.py` with a staged
   migration writes that file's content digest to
   `.codearbiter/.markers/migration-gate-passed`.
5. **Backstop blocks unreviewed migration** — `git commit` staging a migration with no
   marker (or a marker missing the file's digest) exits 2 (BLOCK) and names the new H-tag.
6. **Backstop admits reviewed migration** — after `migration-pass.py` records the digest,
   the same `git commit` is admitted (exit 0).
7. **Edited-after-review re-blocks** — a migration whose content changes after the marker
   was minted (digest mismatch) is BLOCKed (TOCTOU + immutability enforcement).
8. **Non-migration commit unaffected** — a `git commit` staging only non-migration files
   passes with no marker required (no regression to ordinary commits).
9. **Dormant outside an arbiter repo** — with no `.codearbiter/` present, the backstop
   does not fire.
10. **`-a` / untracked coverage** — a migration staged via `git commit -a`, or an
    untracked new migration, is still detected and gated (mirrors the security check's
    `-a`/HEAD handling).
11. **Prose wiring present** — commit-gate's skill prose contains a migration-classification
    step that dispatches `migration-reviewer` and runs `migration-pass.py` on PASS
    (structural test, in the style of `test_ux_conversion.py`).

## Open questions

None. No new `[CONFIRM-NN]` raised — the four design forks were resolved during
brainstorming and the default glob set is concrete (long-tail gaps handled by the
override). Known accepted cost: a default glob may match a non-DB `migrations/`
directory; `migration-reviewer` PASSes a file with no migration findings (friction, not
a hard block), and the override narrows it.

## Decision lineage

- Issue #77; SMARTS decision (a), `moderate`, 2026-06-19.
- Precedent: DECISION-0003 (close a bound bypass), DECISION-0002 (the rejected accept-
  and-document alternative), DECISION-0004 (stdlib-only).
- Consistent with deferred finding #6 (`open-questions.md`): actions one named sibling of
  the deferred commit-time-enforcement class via the cheap marker pattern, without
  reopening the broad deferral.
