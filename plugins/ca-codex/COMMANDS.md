# codeArbiter commands

Start with the job in front of you. A direct instruction outside a command channel routes to the
closest supported lane; installed legacy entry points remain listed under [Compatibility
routes](#compatibility-routes). Each route ships as a `ca-`-prefixed skill; invoke it as
`$ca-<name>`.

A command body ([skills/ca-<name>/SKILL.md](skills/ca-<name>/SKILL.md))
loads only when that route is invoked. Never bulk-read the directory.

## Installed surface

| Visibility | Count |
|---|---:|
| Core | 18 |
| Advanced | 11 |
| Canonical total | 29 |
| Compatibility aliases | 5 |
| Internal | 1 |
| Deprecated | 1 |
| **Total** | **36** |

## Core lanes

### Evaluate

| Command | Argument | Purpose |
|---|---|---|
| `$ca-preview` | _(none)_ | Predict the reviewer fleet and run a state-free secret scan without writing. |

### Initialize

| Command | Argument | Purpose |
|---|---|---|
| `$ca-init` | `[--stage N] [--greenfield\|--brownfield] \| --check` | Scaffold or inspect `.codearbiter/`; explicit strategies enter the existing greenfield or brownfield workflows. |

### Change

| Command | Argument | Purpose |
|---|---|---|
| `$ca-feature` | `"description"` | Approve a spec and plan, then build test-first. This is the entry to new behavior. |
| `$ca-sprint` | `["goal"] [--farm]` | Run one approved spec through plan-to-PR execution with SMARTS-scored decisions. `--farm` is an off-by-default Feature Forge preview that requires `FARM_API_KEY`. |
| `$ca-fix` | `"bug description"` | Prove a confirmed defect with a failing regression test, then make the smallest fix. |
| `$ca-refactor` | `"surface and motivation"` | Restructure behind behavioral parity proven by unchanged pre-existing tests. |
| `$ca-chore` | `<docs\|deps\|revert> …` | Route non-behavioral work through type-scaled gates. |
| `$ca-spike` | `"question" [timebox]` | Explore on a disposable branch and exit to findings or `$ca-feature`; never merge the spike. |
| `$ca-add-dep` | `"package"` | Vet license, provenance, maintenance, known vulnerabilities, and supply-chain risk before install. |

### Review

| Command | Argument | Purpose |
|---|---|---|
| `$ca-review` | `[path or scope]` | Run the reviewer fleet over the current diff and block on CRITICAL or HIGH findings. |

### Decide

| Command | Argument | Purpose |
|---|---|---|
| `$ca-adr` | `"title"` | Author a numbered, dated, user-attributed architecture decision. |

### Ship

| Command | Argument | Purpose |
|---|---|---|
| `$ca-commit` | _(none)_ | Run the full commit gate and stage only the reviewed paths. |
| `$ca-pr` | `["title"] \| --watch [PR] \| --cleanup` | Open or finish a pull request; watch hosted CI; or clean a proven merged branch. Never write directly to the default branch. |
| `$ca-release` | `[--dry-run]` | Prepare a target-aware SemVer bump, changelog, and annotated tag when release authority is explicit. |

### Operate

| Command | Argument | Purpose |
|---|---|---|
| `$ca-status` | `(none) \| drift` | Show project state, or explicitly inspect provenance drift. The default path is read-only. |
| `$ca-task` | `add "<desc>" \| start <id\|"title"> \| done <id\|"title">` | Add, start, or complete task-board entries through the only sanctioned writer. |
| `$ca-doctor` | _(none)_ | Verify the active install, payload, package ownership, enforcement, and a harmless live-fire probe. |
| `$ca-override` | `"reason"` | Log one attributed bypass when the governing hard rule permits it. |

<details>
<summary><strong>Advanced operations</strong></summary>

### Change

| Command | Argument | Purpose |
|---|---|---|
| `$ca-debug` | `"symptom"` | Investigate an unknown cause, then exit to `$ca-fix`, `$ca-adr`, or a no-action close. |

### Review

| Command | Argument | Purpose |
|---|---|---|
| `$ca-checkpoint` | `[focus]` | Run a periodic whole-codebase reviewer sweep and return a triaged report. |
| `$ca-threat-model` | `"scope"` | Run an opt-in lightweight STRIDE pass for a sensitive feature. |
| `$ca-tribunal` | `[scope-path] [--tag <label>]` | Run a deep, resumable eleven-lens audit. It is expensive and never a routine gate. |

### Decide

| Command | Argument | Purpose |
|---|---|---|
| `$ca-adr-status` | `[--adr N]` | Inspect ADR health, age, challenges, and supersession chains without writing. |
| `$ca-reconcile` | `["scope"]` | Reconcile architectural artifacts through explicit, user-attributed SMARTS choices. |

### Operate

| Command | Argument | Purpose |
|---|---|---|
| `$ca-standup` | _(none)_ | Review repository hygiene, then confirm each safe cleanup action separately. |
| `$ca-audit` | `[range]` | Assemble a dated governance packet from source records. Read-only. |
| `$ca-metrics` | `[--window N]` | Report override, small-lane, and low-confidence trends against the prior window. |

### Extend

| Command | Argument | Purpose |
|---|---|---|
| `$ca-new-skill` | `"gap"` | Prove a capability gap, approve a spec, then author a new skill. |

### Help

| Command | Argument | Purpose |
|---|---|---|
| `$ca-commands` | _(none)_ | Show this grouped catalog. |

</details>

<details>
<summary><strong>Compatibility routes</strong></summary>

These entry points remain installed for the declared compatibility window. New work should use the
canonical form; each legacy route continues to execute its original workflow.

| Existing route | Canonical form | Purpose |
|---|---|---|
| `$ca-watch` | `$ca-pr --watch [PR]` | Watch hosted CI, diagnose red, and offer the merge on green. |
| `$ca-cleanup` | `$ca-pr --cleanup` | Finish a proven merged branch under per-item discard consent. |
| `$ca-decompose` | `$ca-init --greenfield` | Populate a new project through the layered decomposition interview. |
| `$ca-create-context` | `$ca-init --brownfield` | Scout an existing codebase and backfill repository context. |
| `$ca-context-check` | `$ca-status drift` | Inspect provenance-tracked document drift and offer explicit follow-up choices. |

</details>

<details>
<summary><strong>Internal and deprecated routes</strong></summary>

| Status | Command | Argument | Purpose |
|---|---|---|---|
| Internal protocol | `$ca-conflict` | `"description"` | Stop work when governing rules contradict and surface both sides for the user. |
| Deprecated | `$ca-btw` | `"question"` | Ask a lightweight project question without state change. Prefer asking the question directly. |

</details>

## Glossary

- **stage:** the project's maturity level in `.codearbiter/CONTEXT.md`; higher stages demand stricter coverage and review.
- **skill:** a gated routine that a command routes to, such as `tdd` or `commit-gate`.
- **phase:** one step inside a skill. Each phase ends at a gate.
- **gate:** a phase exit condition. **STOP** waits for the user; **BLOCK** halts until the condition is met.
- **severity:** a review finding's CRITICAL, HIGH, MEDIUM, or LOW classification, independent of gate action.
- **`[CONFIRM-NN]`:** a numbered question only the user can resolve; dependent work pauses until `.codearbiter/open-questions.md` records the answer.
- **SMARTS:** the Scalable, Maintainable, Available, Reliable, Testable, and Securable lenses used for attributed arbitration.
- **ADR:** an Architecture Decision Record under `.codearbiter/decisions/`, authored only through `$ca-adr`.
