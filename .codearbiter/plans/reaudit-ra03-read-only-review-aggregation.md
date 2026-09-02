# RA-03 Read-only Review Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make review aggregation provably read-only while preserving explicit, non-overwriting checkpoint persistence.

**Architecture:** Canonical Markdown under `core/surface` defines the workflow. A new read-only `verdict-aggregator` becomes the terminal review funnel, while `/checkpoint` explicitly calls the existing writer after receiving that verdict. Static contract tests traverse both working-diff and inbound-PR review routes, inspect reachable frontmatter, and prove the verifier leaves repository bytes unchanged.

**Tech Stack:** Python `unittest`, canonical Markdown surfaces, `tools/build-surface.py`, generated Claude/Codex/Pi packages.

**Spec:** `.codearbiter/specs/reaudit-ra03-read-only-review-aggregation.md`

**Implementation status:** COMPLETE — PR #729 is open; review-amendment exact-head CI is pending.

## Global Constraints

- Edit canonical `core/surface` inputs only; regenerate host projections with `python tools/build-surface.py`.
- No new dependency, public command, severity rule, or checkpoint format.
- Follow red-green-refactor: observe the focused contract test fail before changing production surfaces.
- Preserve the controller checkout and all unrelated campaign findings.

---

### Task 1: Lock the read-only funnel contract with a failing test

**Files:**
- Create: `.github/scripts/test_review_funnel.py`

**Interfaces:**
- Consumes: canonical review, dispatch, triage, verdict, and checkpoint Markdown.
- Produces: `verify_review_route(repo, target_kind)` and byte-invariance assertions for `working-diff` and `inbound-pr`.

- [x] **Step 1: Write the failing route test**

```python
for target in ("working-diff", "inbound-pr"):
    before = snapshot_tracked_bytes(REPO_ROOT)
    route = verify_review_route(REPO_ROOT, target)
    self.assertEqual(route, ("finding-triage", "verdict-aggregator"))
    self.assertEqual(snapshot_tracked_bytes(REPO_ROOT), before)
```

- [x] **Step 2: Assert the writer separation**

```python
self.assertNotIn("checkpoint-aggregator", review_terminal_funnel)
self.assertIn("verdict-aggregator", checkpoint_command)
self.assertIn("checkpoint-aggregator", checkpoint_command)
self.assertIn("MUST NOT overwrite", checkpoint_charter)
```

- [x] **Step 3: Run the test and verify RED**

Run: `python .github/scripts/test_review_funnel.py`
Expected: FAIL because `verdict-aggregator.md` does not exist and current review routes name `checkpoint-aggregator`.

---

### Task 2: Implement the canonical read-only verdict path

**Files:**
- Create: `core/surface/agents/verdict-aggregator.md`
- Modify: `core/surface/agents/finding-triage.md`
- Modify: `core/surface/agents/INDEX.md`
- Modify: `core/surface/commands/review.md`
- Modify: `core/surface/commands/checkpoint.md`
- Modify: `core/surface/skills/dispatching-parallel-agents/SKILL.md`
- Modify: `core/surface/includes/routing-table.md`
- Modify: `tools/build-surface.py`

**Interfaces:**
- Consumes: complete finding-triage report and unit terminal-state findings.
- Produces: one in-memory verdict with status `PASS`, `BLOCKING_FINDINGS`, or `INCOMPLETE`, plus every finding and errored/deferred unit.

- [x] **Step 1: Add the minimal read-only charter**

```yaml
name: verdict-aggregator
tools: Read, Grep, Glob
classification: reviewer
```

The body must require complete input accounting, structured status/counts/findings, and `Modify no file`.

- [x] **Step 2: Replace review and generic funnel terminal routes**

Use `finding-triage` → `verdict-aggregator` in `/review` and `dispatching-parallel-agents`; do not mention the checkpoint writer as their terminal aggregator.

- [x] **Step 3: Make checkpoint persistence explicit**

`/checkpoint` receives the verdict, then separately dispatches `checkpoint-aggregator` to write the dated non-overwriting document.

- [x] **Step 4: Update inventory and dispatch policy**

Add `verdict-aggregator` to the agent index and the `read-only reviewer/extractor` policy set. Replace the hard-coded canonical count with the new exact count.

- [x] **Step 5: Run the focused test and verify GREEN**

Run: `python .github/scripts/test_review_funnel.py`
Expected: PASS for both target kinds with identical before/after tracked-byte snapshots.

---

### Task 3: Regenerate and verify every supported host surface

**Files:**
- Modify generated files under `plugins/ca/`, `plugins/ca-codex/`, and `plugins/ca-pi/` using the generator only.
- Modify: `.github/scripts/test_build_surface.py` where the exact inventory/route receipt changes.

**Interfaces:**
- Consumes: canonical surface templates and `core/hosts.json`.
- Produces: byte-consistent Claude, Codex, and Pi projections with closed references.

- [x] **Step 1: Regenerate**

Run: `python tools/build-surface.py`

- [x] **Step 2: Update exact inventory expectations from generated evidence**

Add `verdict-aggregator` to the expected role set and update only route receipt counts actually changed by the canonical routes.

- [x] **Step 3: Run focused verification**

Run: `python .github/scripts/test_build_surface.py`
Run: `python .github/scripts/check-plugin-refs.py`
Run: `python tools/build-surface.py --check`
Expected: all exit 0.

- [x] **Step 4: Run governed whole-surface verification and review**

Execute the repository-required `$ca-commit` and `$ca-pr` gates, record exact commands and results, then open a PR without merging or releasing unless separately authorized.
