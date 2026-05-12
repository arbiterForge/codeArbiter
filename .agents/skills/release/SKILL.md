---
name: release
---

# Skill: release

## Purpose

Drive a project from "green on main" to a tagged, announceable release. The release skill is the
single permitted path to a version tag. It composes the project's existing compliance machinery —
the `tdd` outcome, the `commit-gate` SemVer classification, the `/checkpoint` review aggregate, the
`decision-lifecycle` ADR health audit, and the `stage-gating` stage threshold — into one ordered
gate sequence. It does not duplicate those skills; it routes to them, reads their outputs, and
BLOCKS if any of them was DEFERRED rather than PASS.

A release is not a commit. A release is a deployment-readiness assertion: that the codebase at this
SHA, under the current stage, satisfies every published threshold for shipping. The skill produces
a tag, a roll-up changelog, and a deployment-readiness report. If any prior gate was deferred, the
release is BLOCKED — there are no partial releases.

---

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

The orchestrator routes to this skill when:

- The user invokes `/release` (or equivalent release command) on a non-protected branch with a
  green main and an authorized release window.
- A stage promotion is queued and the promotion criteria require a release tag at the current stage
  before promotion proceeds.
- A scheduled release window has been declared in `${PROJECT_ROOT}/.agents/projectContext/` and the current SHA is the
  candidate.
- The routing table in `AGENTS.md` references this skill for a release-class workflow.

This skill MUST NOT be invoked to produce a "hotfix tag" without running every phase. There are no
abbreviated releases. A hotfix that requires bypassing a gate is an `/override` event, logged
permanently to `${PROJECT_ROOT}/.agents/projectContext/overrides.log`.

---

## Pre-Flight

Before Phase 1 begins, confirm the following. Each check either passes silently or hard-stops with
a specific error message.

1. `${PROJECT_ROOT}/.agents/projectContext/stage` is readable and contains a valid integer 1–4. If missing or
   non-numeric, STOP and surface the error — the release cannot proceed without a known stage.
2. `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` is readable. If missing, STOP — fail-closed audit policy
   verification in Phase 6 has no source of truth.
3. The working tree is clean. Run `git status` and confirm there are no uncommitted changes. If
   the tree is dirty, STOP and instruct the user to commit or stash via the `commit-gate` skill.
4. The current branch is the configured release branch (typically `main` or `release/*`). If the
   branch is a feature branch, STOP and instruct the user to merge first.
5. The most recent tag is identifiable via `git describe --tags --abbrev=0`. If the repository has
   no tags, record `LAST_TAG=<none>` and treat the entire commit history as the release window.
6. The commit set since `LAST_TAG..HEAD` is non-empty. If empty, STOP — there is nothing to
   release.

If every check passes, proceed to Phase 1.

---

## Phase 1 — Pre-Flight Readiness

**Goal:** Confirm the project is in a state where a release is even conceivable: tests green,
commit-gate clean, no blocking CONFIRM placeholders, ADR health within tolerance.

**Inputs:**
- The most recent `tdd` skill run result (specifically, Phase 6 green/red on `LAST_TAG..HEAD`).
- The most recent `commit-gate` skill run on the HEAD commit.
- `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` — for any `[CONFIRM-NN]` entries flagged as blocking
  the target stage.
- The ADR health table from the most recent `decision-lifecycle` run, or the requirement to run it.

**Actions:**

1. Confirm the most recent full test suite run was green. If the last `tdd` Phase 6 result is not
   PASS, record `READINESS=BLOCK` and surface the failing test set.
2. Confirm the HEAD commit was produced by the `commit-gate` skill with all eight phases PASS.
   Read the most recent commit message footer and verify it was not produced via `/override`. An
   override-tagged HEAD commit BLOCKS Phase 1 unless the user explicitly re-authorizes the release
   via a new `/override`.
3. Read `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`. Identify every `[CONFIRM-NN]` entry whose
   target stage equals or exceeds the current stage. If any are still in OPEN or
   PARTIALLY-EVIDENCED status (per the `decision-lifecycle` taxonomy), record `READINESS=BLOCK`
   with the entry IDs.
4. If a `decision-lifecycle` run has not occurred in the current session, route to it now for a
   surface health check (Phase 1 + Phase 2 only — full ADR challenge happens in Phase 5 below).
   Capture the ADR health table for use in Phase 5.

**Output:** Pre-flight readiness verdict — `PASS` or `BLOCK` — with cited evidence for each
sub-check.

**Gate:** BLOCK on any failing sub-check. MUST NOT proceed to Phase 2 with a known-red test suite,
an override-tagged HEAD, an unresolved blocking `[CONFIRM-NN]`, or a missing ADR health table.

---

## Phase 2 — Checkpoint Gate

**Goal:** Run a full cross-cutting review of the codebase before the tag is composed. A release
without a fresh checkpoint is a release without a baseline.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/checkpoints/` — for the most recent checkpoint document.
- The current value of `${PROJECT_ROOT}/.agents/projectContext/stage` — to compute stage-appropriate BLOCKS
  classifications.

**Actions:**

1. Determine whether a checkpoint document dated within the release window
   (`LAST_TAG..HEAD` time range) already exists in `${PROJECT_ROOT}/.agents/projectContext/checkpoints/`. If yes and it
   is signed off by a named approver, capture it. If no, route to the `/checkpoint` command and
   wait for completion.
2. The `/checkpoint` command dispatches all seven checkpoint agents and writes
   `${PROJECT_ROOT}/.agents/projectContext/checkpoints/YYYY-MM-DD.md`. The release skill does not re-implement that work —
   it routes to it and reads the output.
3. After `/checkpoint` returns, parse the checkpoint document and tabulate:
   - Total CRITICAL findings.
   - Total `BLOCKS_S<current-stage>` findings still open.
   - Total `BLOCKS_S<current-stage+1>` findings (informational at this stage but flagged for the
     deployment-readiness report).
4. If any CRITICAL finding is unresolved, record `CHECKPOINT=BLOCK`. If any open
   `BLOCKS_S<current-stage>` finding is present, record `CHECKPOINT=BLOCK`.

**Output:** Checkpoint summary — finding counts by severity and stage classification, plus the
checkpoint document path.

**Gate:** BLOCK on any unresolved CRITICAL finding. BLOCK on any open `BLOCKS_S<current-stage>`
finding. The release MUST NOT proceed if the checkpoint has not been signed off by a named
approver (per the `/checkpoint` command's own gate).

---

## Phase 3 — Version Bump (SemVer)

**Goal:** Classify the change set since the last tag and compute the next version number using the
same Conventional Commits taxonomy the `commit-gate` skill enforces. The release version is not a
guess — it is derived mechanically from the commit log.

**Inputs:**
- `git log LAST_TAG..HEAD --pretty=format:%H%n%s%n%b%n----`
- The commit type taxonomy from the `commit-gate` skill Phase 3 (`feat`, `fix`, `refactor`,
  `test`, `docs`, `chore`, `ci`).
- The current version, parsed from `LAST_TAG` (or `0.0.0` if no prior tag exists).

**Actions:**

1. Read every commit subject in the `LAST_TAG..HEAD` window. For each commit, extract the
   Conventional Commits type from the subject line prefix.
2. Apply SemVer classification:
   - Any commit with a `BREAKING CHANGE:` footer OR a `!` after the type/scope → **major** bump.
   - Else, any commit of type `feat` → **minor** bump.
   - Else, any commit of type `fix`, `refactor`, `perf` → **patch** bump.
   - Commits of type `test`, `docs`, `chore`, `ci` do not, on their own, trigger any bump. If the
     entire change set consists only of these types, record `VERSION=NONE` and surface to the user
     — there is nothing to release.
3. Compute the next version by applying the highest-precedence bump to the current version. Major
   beats minor beats patch.
4. Verify that the proposed version is monotonically greater than `LAST_TAG`. If not, record
   `VERSION=BLOCK` — the version classification disagrees with the commit log.
5. Present the proposed version and the classification reasoning to the user for confirmation.
   The user MAY override the classification — but only via `/override`, which logs the bypass.

**Output:** Proposed next version (`vMAJOR.MINOR.PATCH`) with the per-commit classification table
attached as evidence.

**Gate:** BLOCK if the version classification disagrees with the commit log (e.g., a `feat` commit
exists but the proposed bump is only `patch`). BLOCK if the entire change set is non-bumping
(`test`/`docs`/`chore`/`ci` only). The release skill MUST NOT silently downgrade or upgrade the
classification.

---

## Phase 4 — Changelog Generation

**Goal:** Roll up the `CHANGELOG:` footers from every user-visible commit in the release window
into a single, audience-ready changelog section. The changelog is generated from the commits — it
is not authored from scratch.

**Inputs:**
- `git log LAST_TAG..HEAD --pretty=format:%H%n%s%n%b%n----`
- The commit-type classification table from Phase 3.

**Actions:**

1. For every commit in the window classified as `feat`, `fix`, or `perf`, extract the
   `CHANGELOG:` footer line. (The `commit-gate` skill Phase 7 requires this footer for any
   `feat`/`fix` commit, so it must be present.)
2. If any `feat` or `fix` commit lacks a `CHANGELOG:` footer, record `CHANGELOG=BLOCK` and surface
   the commit SHA and subject. The release MUST NOT proceed with a missing user-visible summary —
   the commit-gate skill should have caught this, and its absence is itself a finding worth
   surfacing.
3. Group the extracted footers into three sections:
   - **Added** — from `feat` commits.
   - **Fixed** — from `fix` commits.
   - **Performance** — from `perf` commits.
4. Append the rendered changelog block to the project's changelog file (typically
   `CHANGELOG.md`) under a new heading `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`. The previous
   entries remain intact and unmodified.
5. If the changelog file does not yet exist, create it with a top-level `# Changelog` heading and
   write the first section.

**Output:** Updated changelog file with the new release section appended.

**Gate:** BLOCK if any `feat` or `fix` commit in the release window lacks a `CHANGELOG:` footer.
The commit-gate skill SHOULD have prevented this, so its presence here is a compliance gap that
must be surfaced — not silently auto-filled by the release skill.

---

## Phase 5 — ADR Currency Check

**Goal:** Confirm the decision record is not stale at the moment of release. A release is a
moment-in-time declaration that the project's design intent matches its implementation; aged or
unchallenged ADRs undermine that declaration.

**Inputs:**
- The ADR health table from `decision-lifecycle` Phase 1 (captured during Phase 1 above, or
  refreshed if it is older than the release window).
- The challenge results from `decision-lifecycle` Phase 4 (must be re-run if the most recent
  results predate `LAST_TAG`).

**Actions:**

1. Route to the `decision-lifecycle` skill specifically requesting Phase 4 (Challenge Routing).
   The `decision-lifecycle` skill dispatches the `decision-challenger` agent for every AGED or
   UNCHALLENGED ADR and returns a confidence rating (0–3) for each.
2. Receive the full challenge results table. For every ADR with a confidence rating ≤ 2, record
   the ADR ID, the challenger reasoning, and the recommended action.
3. Apply the release gate:
   - Confidence rating **0** → BLOCK. The ADR is invalid or superseded; the release MUST NOT ship
     against an invalid decision baseline.
   - Confidence rating **1** → BLOCK. The decision is questionable; ship under a revisit, not
     under a release.
   - Confidence rating **2** → BLOCK. Per the `decision-lifecycle` skill's own gate, ratings ≤ 2
     block stage promotion; the release skill inherits that gate.
   - Confidence rating **3** → PASS.
4. Surface every blocking ADR to the user. The release skill does not author replacement ADRs or
   modify ADR status — that is the user's call, recorded via `/adr` with explicit attribution.

**Output:** ADR currency verdict — `PASS` or `BLOCK` — with every blocking ADR cited.

**Gate:** BLOCK on any ADR with a confidence rating ≤ 2. The release skill MUST NOT silently
defer aged-and-unchallenged ADRs; the gate is binary.

---

## Phase 6 — Stage Threshold Verification

**Goal:** Confirm that the project, at this SHA, meets the published thresholds for the current
stage as recorded in `${PROJECT_ROOT}/.agents/projectContext/stage` and its supporting policy documents.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/stage` — the integer 1–4.
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` — for stage-specific fail-closed audit policy.
- Project-specific stage policy in `${PROJECT_ROOT}/.agents/projectContext/decisions/` or `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`
  (per the `stage-gating` skill's reference table).

**Actions:**

1. Route to the `stage-gating` skill specifically requesting Phase 1 (Stage Read) and Phase 2
   (Rule Inventory) on the release scope (the entire codebase at HEAD, not a single change).
2. Receive the active rule inventory for the current stage. For every active rule, confirm the
   release artifact does not violate it.
3. Verify stage-specific release thresholds:
   - **Coverage threshold.** Read the threshold for the current stage from the project's coverage
     policy (typically declared in `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` or `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`). Run
     the coverage report. If coverage is below the threshold, record `STAGE=BLOCK`.
   - **Fail-closed audit policy.** Read the stage's required audit posture from
     `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`. Confirm the deployed audit configuration is fail-closed at or above the
     stage's required level. If not, record `STAGE=BLOCK`.
   - **Trust-zone declarations.** If the current stage requires declared egress points (typically
     S3+), confirm `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` declares every outbound integration present in
     the code at HEAD.
4. The `stage-gating` skill is authoritative on what rules apply at the current stage. The release
   skill MUST NOT infer a different set.

**Output:** Stage threshold verdict — `PASS` or `BLOCK` — with every threshold check cited.

**Gate:** BLOCK if any stage-required threshold is unmet. BLOCK if `stage-gating` reports any
active rule violation. The release skill MUST NOT ship a tag against a sub-threshold codebase
even if every other gate is green.

---

## Phase 7 — Tag and Announce

**Goal:** Compose the annotated tag, write the deployment-readiness report, and deliver both to
the user. This phase only runs if every prior phase returned PASS — there are no partial releases.

**Inputs:**
- Proposed version from Phase 3.
- Rendered changelog section from Phase 4.
- ADR currency verdict from Phase 5.
- Stage threshold verdict from Phase 6.
- Checkpoint summary from Phase 2.

**Actions:**

1. Verify that every prior phase recorded `PASS`. If any phase recorded `BLOCK` or `DEFERRED`,
   STOP and surface the deferred phase. A DEFERRED gate is not a PASS — the release skill MUST
   NOT promote a DEFERRED outcome into a tag.
2. Compose the annotated tag:
   - Tag name: `vMAJOR.MINOR.PATCH` from Phase 3.
   - Tag message: a single block containing the changelog section from Phase 4 plus a footer
     line `Released-at: YYYY-MM-DD` and `Stage: <current-stage>`.
   - Use `git tag -a vMAJOR.MINOR.PATCH -F <message-file>` — never `-m` with multi-line content,
     and never an interactive editor.
3. Compose the deployment-readiness report. The report contains exactly seven sections, one per
   phase, each citing the verdict and the supporting evidence:
   - Pre-Flight Readiness verdict + evidence.
   - Checkpoint summary (findings counts, checkpoint path, approver name).
   - Version classification table + proposed version.
   - Changelog rollup (footer count, missing-footer count).
   - ADR currency table (every reviewed ADR + confidence rating).
   - Stage threshold checks (coverage %, audit policy, trust-zone declarations).
   - Tag composition (tag name, tag SHA, tag message preview).
4. Deliver the report to the user. The report is the release artifact — preserve it. Write it to
   `${PROJECT_ROOT}/.agents/projectContext/releases/vMAJOR.MINOR.PATCH.md` for permanent record.
5. MUST NOT push the tag to a remote without explicit user instruction. Tag publication is a
   separate decision the user MUST authorize after reviewing the report.

**Output:** Annotated tag in the local repository, plus the deployment-readiness report at
`${PROJECT_ROOT}/.agents/projectContext/releases/vMAJOR.MINOR.PATCH.md`.

**Gate:** BLOCK if any prior phase recorded DEFERRED rather than PASS. BLOCK if tag composition
fails for any reason (e.g., tag already exists). BLOCK if `${PROJECT_ROOT}/.agents/projectContext/releases/` cannot be
written. MUST NOT push the tag without explicit user authorization.

---

## Hard Rules

- MUST NOT compose a tag without all seven phases returning PASS.
- MUST NOT promote a DEFERRED phase verdict into a PASS for the purpose of reaching Phase 7.
- MUST NOT push a tag to a remote without explicit user authorization, even if the local tag is
  composed successfully.
- MUST NOT bypass the `commit-gate` skill's SemVer classification — the version bump is derived
  from the commit log, not from operator judgment.
- MUST NOT bypass the `decision-lifecycle` skill's confidence rating gate — ratings ≤ 2 BLOCK.
- MUST NOT bypass the `stage-gating` skill's active rule inventory — the release scope is the
  entire codebase, not a single change.
- MUST NOT author replacement ADRs or modify ADR status to clear a blocking ADR. ADR status
  changes require `/adr` with user attribution.
- MUST NOT silently auto-fill a missing `CHANGELOG:` footer in Phase 4. The absence is a
  compliance gap that the user MUST resolve, ideally by going back through `commit-gate`.
- MUST NOT release on a protected branch directly without the release branch policy being
  satisfied (per `commit-gate` Phase 2 rules, inherited).
- MUST NOT release without the `/checkpoint` document signed off by a named approver — the
  approver MUST be a person, never "codeArbiter" or "automated".

---

## Decision Gates Summary

| Gate         | Condition                                                              | Action if blocked                                                |
|--------------|------------------------------------------------------------------------|------------------------------------------------------------------|
| Pre-Flight   | Missing stage file, audit-spec, dirty tree, or empty release window    | STOP; surface gap; do not proceed                                |
| Phase 1 exit | Red tests, override-tagged HEAD, blocking `[CONFIRM-NN]`, no ADR table | BLOCK; surface evidence; do not proceed to checkpoint            |
| Phase 2 exit | Any CRITICAL or open `BLOCKS_S<current>` finding from `/checkpoint`    | BLOCK; require resolution + approver sign-off; do not proceed    |
| Phase 3 exit | Version classification disagrees with commit log, or non-bumping set   | BLOCK; surface mismatch; require user reconciliation             |
| Phase 4 exit | Any `feat`/`fix` commit in window lacks `CHANGELOG:` footer            | BLOCK; surface commit SHA; do not auto-fill                      |
| Phase 5 exit | Any ADR with confidence rating ≤ 2 (per `decision-lifecycle` Phase 4)  | BLOCK; surface ADR; require `/adr` resolution with attribution   |
| Phase 6 exit | Any stage-required threshold unmet (per `stage-gating`)                | BLOCK; surface threshold gap; require remediation                |
| Phase 7 exit | Any prior phase verdict was DEFERRED rather than PASS                  | BLOCK; promote no deferred outcome; surface deferred phase       |

---

## Interactions with other skills

The release skill is the most-interacting skill in the framework. It does not duplicate the work of
the skills it depends on — it routes to them, reads their outputs, and BLOCKS on their verdicts.

- **`/checkpoint` command (Phase 2).** The release skill invokes `/checkpoint` directly (or reads
  a fresh signed-off checkpoint document already present in `${PROJECT_ROOT}/.agents/projectContext/checkpoints/`). The
  `/checkpoint` command dispatches all seven checkpoint reviewer agents. The release skill MUST
  NOT re-implement that work; it reads the resulting checkpoint document and gates on
  finding counts.
- **`commit-gate` skill (Phase 3 — by reference).** The SemVer classification logic in Phase 3 is
  identical to the commit-type taxonomy in `commit-gate` Phase 3 and the footer requirement in
  `commit-gate` Phase 7. The release skill MUST NOT diverge from that taxonomy.
- **`decision-lifecycle` skill (Phase 1, Phase 5).** Phase 1 routes to `decision-lifecycle`
  Phase 1+2 for a surface ADR health table. Phase 5 routes to `decision-lifecycle` Phase 4
  specifically (Challenge Routing) and inherits its confidence-rating gate (≤ 2 BLOCKS).
- **`stage-gating` skill (Phase 6).** Phase 6 routes to `stage-gating` Phase 1+2 (Stage Read +
  Rule Inventory) against the full codebase scope at HEAD. The release skill inherits
  `stage-gating`'s authority on what rules apply at the current stage.
- **`tdd` skill (Phase 1 — by reference).** The release skill reads the most recent `tdd` Phase 6
  result. It does not re-run `tdd`; that is the responsibility of the commit-gate skill before
  the HEAD commit was produced.
- **`/adr` command (Phase 5 — by reference).** When Phase 5 surfaces a blocking ADR, the user
  resolves it via `/adr` with explicit attribution. The release skill MUST NOT modify ADR status
  on its own.
- **`/override` command (any phase).** Any phase BLOCK can be bypassed only via `/override`,
  which logs the bypass to `${PROJECT_ROOT}/.agents/projectContext/overrides.log`. The release skill itself MUST
  NOT silently lower a gate.

---

## Failure Modes

| Failure                                              | Response                                                                  |
|------------------------------------------------------|---------------------------------------------------------------------------|
| `${PROJECT_ROOT}/.agents/projectContext/stage` missing               | STOP in Pre-Flight; surface gap; the release cannot proceed               |
| `audit-spec.md` missing                              | STOP in Pre-Flight; Phase 6 has no source of truth                        |
| Empty commit window (`LAST_TAG..HEAD`)               | STOP in Pre-Flight; there is nothing to release                           |
| Tests red                                            | BLOCK in Phase 1; surface failing tests; route user to `tdd` skill        |
| HEAD produced via `/override`                        | BLOCK in Phase 1; require fresh user re-authorization via `/override`     |
| Unresolved blocking `[CONFIRM-NN]`                   | BLOCK in Phase 1; route to `decision-lifecycle` Phase 2 for surfacing     |
| Checkpoint document missing or unsigned              | BLOCK in Phase 2; route to `/checkpoint` and wait for approver sign-off   |
| CRITICAL finding in checkpoint                       | BLOCK in Phase 2; require resolution; no release on critical findings    |
| Version classification mismatch                      | BLOCK in Phase 3; surface mismatch; user reconciles or `/override`s       |
| Missing `CHANGELOG:` footer in `feat`/`fix` commit   | BLOCK in Phase 4; surface SHA; user re-commits via `commit-gate`          |
| ADR confidence rating ≤ 2                            | BLOCK in Phase 5; user resolves via `/adr` with attribution               |
| Coverage below stage threshold                       | BLOCK in Phase 6; user remediates coverage; no release on sub-threshold   |
| Fail-closed audit policy not met for current stage   | BLOCK in Phase 6; user remediates audit config; no release on open policy |
| Tag already exists                                   | BLOCK in Phase 7; surface conflict; user resolves before retry            |
| `${PROJECT_ROOT}/.agents/projectContext/releases/` not writable              | BLOCK in Phase 7; surface filesystem issue; the report MUST be preserved  |
| Any prior gate DEFERRED                              | BLOCK in Phase 7; MUST NOT promote DEFERRED into PASS                     |

---

## Subagents Invoked

None directly. The release skill routes to other skills and commands:

- `/checkpoint` (Phase 2) — which itself dispatches seven reviewer agents.
- `decision-lifecycle` skill (Phase 1, Phase 5) — which dispatches `decision-challenger`.
- `stage-gating` skill (Phase 6) — no agent dispatch; pure rule inventory.

The release skill itself does not dispatch agents. It is a gate aggregator.
