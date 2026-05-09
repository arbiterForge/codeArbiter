---
description: Run a full checkpoint review — architecture drift, test coverage, security, standards, scaffold completeness, and decision challenges. Produces a dated checkpoint document requiring sign-off before stage promotion.
argument-hint: "[focus: all|security|tests|drift|scaffold] — defaults to all"
---

Run a checkpoint review for `fusion-core`. Focus: `${1:-all}`.

## Pre-flight

1. Read `CLAUDE.md` in full — particularly §1 (stage), §3 (hard rules), §9 (TDD contract).
2. Read `.fusion/stage` — note the current stage number for all agents.
3. Confirm `docs/checkpoints/` directory exists. If not, create it with a `.gitkeep`.
4. Note today's date in YYYY-MM-DD format for the checkpoint filename.

## Phase 1 — Parallel Review (spawn all simultaneously)

Spawn the following seven subagents **in a single parallel batch** using the Agent tool.
Pass each agent: the current stage number, today's date, and the focus argument `${1:-all}`.
Capture each agent's full output — you will pass it to Phase 2.

| Subagent type | Prompt to pass |
|---|---|
| `architecture-drift-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Review the codebase for drift from all ADRs and architectural decisions. Focus: ${1:-all}." |
| `test-audit-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Audit test coverage against CLAUDE.md §9 obligations. Focus: ${1:-all}." |
| `auth-crypto-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Review auth, cryptography, and secrets handling against CLAUDE.md §3 hard rules. Focus: ${1:-all}." |
| `trust-zone-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Review trust zone boundary enforcement and HTTP client usage. Focus: ${1:-all}." |
| `standards-compliance-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Review code against docs/coding-standards.md and project conventions. Focus: ${1:-all}." |
| `scaffold-completeness-reviewer` | "Stage: [N]. Date: [YYYY-MM-DD]. Identify all planned artifacts that do not yet exist. Focus: ${1:-all}." |
| `decision-challenger` | "Stage: [N]. Date: [YYYY-MM-DD]. Challenge every ADR with adversarial reasoning. Identify the most load-bearing assumption in each decision. Focus: ${1:-all}." |

Wait for ALL seven agents to return before proceeding.

## Phase 2 — Finding Triage (sequential)

Spawn the `finding-triage` subagent.
Pass it the complete concatenated output of all seven Phase 1 agents.
Prompt: "Stage: [N]. Date: [YYYY-MM-DD]. Triage all findings from the seven reviewer reports below. Assign stage promotion impact to each finding. [PASTE ALL SEVEN REPORTS]"

Wait for the triage agent to return before proceeding.

## Phase 3 — Checkpoint Document (sequential)

Spawn the `checkpoint-aggregator` subagent.
Pass it the triage report from Phase 2 AND the raw decision-challenger report.
Prompt: "Stage: [N]. Date: [YYYY-MM-DD]. Write the checkpoint document to docs/checkpoints/[YYYY-MM-DD].md using the triage report and decision challenges below. [PASTE TRIAGE REPORT AND CHALLENGE REPORT]"

## Phase 4 — Report to user

After the aggregator completes, report:
- Path of the checkpoint document written
- Count of findings by severity (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- Count of BLOCKS_S2 findings (if > 0, stage promotion is blocked)
- Count of challenged decisions with confidence < 3
- One-sentence instruction: "Review docs/checkpoints/[YYYY-MM-DD].md and add your sign-off before running /promote-stage."

## Rules

- MUST NOT write code, modify source files, or fix findings during a checkpoint run.
- MUST NOT skip Phase 2 or Phase 3 even if Phase 1 produces no findings — an empty checkpoint with sign-off is a valid checkpoint.
- If any Phase 1 agent errors or returns no output, note it as "AGENT-ERROR" in the checkpoint document and continue. Do not re-run.
- The checkpoint document is the artifact. Do not summarize it in chat beyond the Phase 4 report.
