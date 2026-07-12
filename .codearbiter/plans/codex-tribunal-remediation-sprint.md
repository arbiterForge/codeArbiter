# Sprint spec — Codex tribunal remediation

**Goal:** clear the tribunal findings (issues #255–#270) on `feat/codex-support-m0` so ca-codex can
leave BETA, without regressing the Claude host.

**Roles.** Fable (orchestrator, this session): decompose, review every author return through the gate
chain, open PRs, babysit CI, merge on green. Sonnet: execution — one fresh author per task, test-first.

## Hard branch policy
- Integration branch is **`feat/codex-support-m0`**. Every task branches a worktree off its current
  tip; every PR merges **into** it.
- **Nothing merges to `main`.** The codex branch stays off `main` until the maintainer verifies it
  live in Codex. This is a hard stop, not a default.
- No direct writes to any integration branch — worktree branch → PR → green CI → merge.

## Parallelism model
- **2–3 Sonnet authors in flight continuously**, each in its own git worktree (parallel authors in one
  checkout switch branches under each other — worktree isolation is mandatory).
- **Serial integration.** Because edits flow through `core/pysrc/` then re-vendor via `sync-core.py`
  into both plugins, two authors re-vendoring at once collide. So diffs are generated in parallel but
  merged **one PR at a time**; the next worktree rebases on the new tip. An author whose hot-file was
  touched by a just-merged PR rebases and re-verifies.
- **Hot-file sequencing.** No two in-flight authors may own the same core seam file. Hot files:
  `hostapi.py`, `_hooklib.py`, `session-start.py`, `doctor.py`, and the 20 entry scripts.

## Per-task loop (each issue)
1. Fresh Sonnet author, worktree off the current tip, told: test-first (tdd), edit `core/pysrc/`
   canonical (never the vendored copies), run `python tools/sync-core.py` then `--check`, run the
   affected suites from `tech-stack.md`.
2. Author returns a diff + verification output.
3. Fable review: spec-compliance + quality + dispatch the reviewer chain for security-touching diffs
   (security-reviewer / auth-crypto-reviewer on the enforcement-gate changes). Fresh-run verification.
4. Commit gate → PR into `feat/codex-support-m0` → babysit CI → merge on green. Never auto-merge red.

## Hard gates (true stops, surfaced to the maintainer)
- Any change to `security-controls.md` (#270 doc), the crypto/secret gates, or enforcement semantics
  that a reviewer flags CRITICAL.
- Merge-to-default (forbidden this sprint by policy).
- An unresolvable ambiguity in a finding's intended fix.

## Batches (dependency-ordered)

**Batch 1 — foundation (disjoint files, run in parallel):**
- **#255** load_host fail-open → fail closed + breadcrumb; `hostapi.load_host` + `pre-write` + test
  (folds coverage-003). *Foundation: changes seam error semantics others depend on.*
- **#256** apply_patch parser per-directive fail-closed; `ca-codex/_host.py` + adapter test (folds
  coverage-001, #266). *Disjoint Codex-only file.*
- **#258** CI/release/packaging epic; `.github/**`, `hooks.json`, manifests, `check_license_consistency`
  (folds architecture-003, infra-001/002/003, reliability-008). *Disjoint from Python core.*

**Batch 2 — seam correctness (after #255 lands; #255 owns hostapi.py first):**
- **#260** project-root seam: resolve dead payload leg, fix subdir root, memoize; `hostapi.project_root`
  + `_host.py` + `_hooklib` + entry mains (folds reliability-005, performance-001/003).
- **#263** host-aware manifest path; `doctor.py` + `_updatelib.py` (folds reliability-002,
  observability-003). *Parallel with #260 — coordinate a shared host manifest-path helper.*
- **#269** host attribution in audit logs; `_hooklib` log funcs (ADR-0012). *Sequence after #260 —
  both touch `_hooklib`.*

**Batch 3 — entries + host-conditional (after the seam is stable):**
- **#257** remove/wire the dead `run(host)` param across all 20 entries (folds performance-002).
  *Runs LAST of the wide-blast changes — it rewrites every entry signature.*
- **#268** surface host.name in session-start + doctor.
- **#264** route prune-transcript root through the seam.
- **#265** git-hook shim resolves either plugin or fails closed; `_githooks` + session-start.
- **#261** route pre-edit native-name branches through normalize_tool.

**Batch 4 — tests + docs (ride their batch or follow):**
- **#267** has_statusline gate end-to-end test.
- **#262** ORCHESTRATOR build-surface mechanism / CI check (with the #258 CI lane).
- **#270** document MCP-write out-of-scope in `security-controls.md` (hard-gate review).

## Out of scope
- #271 (pre-existing lock-free RMW + dev-marker clobber) — deferred per ADR-0012, host-agnostic.
- #270 code fix (guarding MCP writes) — only the doc lands; the guard is tracked future work.
- Merge to `main` — maintainer-gated on live Codex verification.

## Done when
Issues #255–#270 closed on `feat/codex-support-m0`, full suite green in CI, `sync-core --check` passing,
and the branch is staged for the maintainer's live-Codex test — not merged to main.
