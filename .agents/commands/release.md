# /release ["version" | --auto | --dry-run]

## Purpose

Compose a tagged, announceable release. `/release` is the **only permitted path** to a version
tag. It does not duplicate the project's existing compliance machinery — it aggregates it. The
command routes to the `release` skill, which orders the `tdd` outcome, the `commit-gate`
SemVer classification, the `/checkpoint` review aggregate, the `decision-lifecycle` ADR health
audit, and the `stage-gating` stage threshold check into one sequenced gate run. If any prior
gate was DEFERRED rather than PASS, the release is BLOCKED — there are no partial releases.

A release is not a commit. A release is a deployment-readiness assertion: the codebase at this
SHA, under the current stage, satisfies every published threshold for shipping.

---

## Usage

```
/release                  # compute version from SemVer rules (same as --auto)
/release "1.2.3"          # use the explicit version supplied
/release --auto           # compute version from commit log (Conventional Commits)
/release --dry-run        # run all gates; STOP before composing the tag
```

### Argument Semantics

- **Explicit version (e.g., `"1.2.3"`).** The version is supplied by the operator. The release
  skill Phase 3 still classifies the commit window and BLOCKS if the supplied version disagrees
  with the SemVer-derived classification (e.g., a `feat` commit is present but the operator
  supplied a patch bump). The classification is not silently downgraded or upgraded.
- **`--auto`.** The version is derived mechanically from the commit log in `LAST_TAG..HEAD`
  using the Conventional Commits taxonomy enforced by the `commit-gate` skill. This is the
  default when no version argument is supplied.
- **`--dry-run`.** Runs Phases 1 through 6 in full, surfaces the deployment-readiness report
  as it stands, and STOPS before Phase 7 — no tag is composed, no changelog is appended, no
  release report is written to `${PROJECT_ROOT}/.agents/projectContext/releases/`. Use this to confirm the release
  would be green without committing the artifact.

The `--auto` and `--dry-run` flags MAY be combined. An explicit version MAY be combined with
`--dry-run`. An explicit version MUST NOT be combined with `--auto` — they are mutually
exclusive.

---

## Routes To

`release` skill (`${FRAMEWORK_ROOT}/.agents/skills/release/SKILL.md`) — Phases 1 through 7. The skill is a gate
aggregator; it routes to other skills and reads their verdicts. The command itself does not
dispatch agents directly.

### Phase Routing Map

| Phase | Name                          | Routes to                                              |
|-------|-------------------------------|--------------------------------------------------------|
| 1     | Pre-Flight Readiness          | Reads `tdd` Phase 6 result, `commit-gate` HEAD footer  |
| 2     | Checkpoint Gate               | Invokes `/checkpoint` (or reads fresh signed-off doc)  |
| 3     | Version Bump (SemVer)         | Reads commit log; reuses `commit-gate` Phase 3 taxonomy |
| 4     | Changelog Generation          | Reads `CHANGELOG:` footers from `commit-gate` output   |
| 5     | ADR Currency Check            | Routes to `decision-lifecycle` Phase 4                 |
| 6     | Stage Threshold Verification  | Routes to `stage-gating` Phase 1 + Phase 2             |
| 7     | Tag and Announce              | Composes annotated tag + writes release report         |

---

## What Happens Step by Step

1. **Pre-flight checks.** Verify `${PROJECT_ROOT}/.agents/projectContext/stage` is readable and numeric. Verify
   `audit-spec.md` is present. Verify the working tree is clean. Verify the current branch is
   the configured release branch. Identify `LAST_TAG` and the release window.
2. **Phase 1 readiness.** Confirm the most recent `tdd` Phase 6 was PASS, the HEAD commit was
   not produced via `/override`, no blocking `[CONFIRM-NN]` entries are open, and an ADR health
   table is available (or refresh it via `decision-lifecycle` Phase 1 + 2).
3. **Phase 2 checkpoint.** If a signed-off checkpoint document covers the release window, read
   it. Otherwise, invoke `/checkpoint` and wait. BLOCK on any unresolved CRITICAL finding or
   any open `BLOCKS_S<current-stage>` finding.
4. **Phase 3 version bump.** Classify every commit in `LAST_TAG..HEAD` by Conventional
   Commits type. Apply the highest-precedence bump (major beats minor beats patch). If an
   explicit version was supplied, verify it matches the classification.
5. **Phase 4 changelog.** Roll up every `CHANGELOG:` footer from `feat`, `fix`, and `perf`
   commits into a new section. BLOCK if any `feat` or `fix` commit lacks the footer.
6. **Phase 5 ADR currency.** Route to `decision-lifecycle` Phase 4. BLOCK on any ADR with a
   confidence rating ≤ 2.
7. **Phase 6 stage thresholds.** Route to `stage-gating` Phase 1 + Phase 2 against the full
   codebase scope. Confirm coverage threshold, fail-closed audit posture, and trust-zone
   declarations meet the current stage's requirements.
8. **Phase 7 tag and announce.** If every prior phase recorded PASS, compose the annotated tag
   and write the deployment-readiness report to `${PROJECT_ROOT}/.agents/projectContext/releases/vMAJOR.MINOR.PATCH.md`.
   If `--dry-run` was supplied, STOP here without composing the tag.
9. Surface the deployment-readiness report path to the user. MUST NOT push the tag to a remote
   without explicit user authorization.

---

## Hard Gates

- **No release tag without all 7 release-skill phases green.** Any phase verdict of BLOCK or
  DEFERRED halts the release. DEFERRED is not PASS.
- All seven phases of the `release` skill MUST run in order. No phase may be skipped, even on
  `--dry-run` (the dry-run flag suppresses only the Phase 7 tag composition, not the gate
  evaluation).
- MUST NOT compose a tag if the `/checkpoint` document covering the release window is unsigned
  by a named approver. The approver MUST be a person — never "codeArbiter" or "automated".
- MUST NOT silently downgrade or upgrade the SemVer classification in Phase 3. An explicit
  version argument that disagrees with the commit log BLOCKS the release.
- MUST NOT auto-fill a missing `CHANGELOG:` footer in Phase 4. The absence is a compliance gap
  surfaced for user remediation via `commit-gate`.
- MUST NOT modify ADR status to clear a blocking ADR in Phase 5. ADR status changes route
  through `/adr` with explicit user attribution.
- MUST NOT push the composed tag to a remote without explicit user instruction. Tag publication
  is a separate decision after the user reviews the deployment-readiness report.
- Any phase BLOCK may be bypassed only via `/override`, which appends to
  `${PROJECT_ROOT}/.agents/projectContext/overrides.log`.

---

## Interactions

- **`/checkpoint`** is invoked from Phase 2 if a fresh signed-off checkpoint document is not
  already present for the release window. The release skill reads the resulting document and
  gates on finding counts; it does not re-implement the checkpoint review.
- **`decision-lifecycle` skill** is routed to from Phase 1 (Phases 1 + 2 for a surface ADR
  health table) and from Phase 5 (Phase 4 for Challenge Routing). The release inherits the
  skill's confidence-rating gate: ratings ≤ 2 BLOCK.
- **`stage-gating` skill** is routed to from Phase 6 (Phases 1 + 2 against the full codebase
  scope at HEAD). The release inherits the skill's authority on which rules apply at the
  current stage.
- **`commit-gate` skill** is referenced (not routed to) in Phase 3 for the Conventional Commits
  taxonomy and in Phase 4 for the `CHANGELOG:` footer contract. The HEAD commit MUST have been
  produced by `commit-gate` with all phases PASS — if produced via `/override`, Phase 1 BLOCKS
  pending fresh re-authorization.
- **`/adr` command** is the user-facing route to resolve a blocking ADR surfaced in Phase 5.
  The release skill MUST NOT author replacement ADRs on its own.

---

## Example Invocations

```
/release
```
Default flow. Equivalent to `/release --auto`. Runs Phases 1–7, classifies the commit window,
computes the next version, and composes the tag if every gate is green.

```
/release --auto
```
Explicit form of the default. Useful when the operator wants to be unambiguous in scripts or
in audit-traceable conversations.

```
/release "2.0.0"
```
Operator supplies an explicit version. Phase 3 still classifies the commit log and BLOCKS if
the supplied version disagrees (e.g., the operator supplied a major bump but the commit window
contains only `fix` commits, or vice versa).

```
/release --dry-run
```
Runs all seven gates and surfaces the deployment-readiness report as it stands, then STOPS
before tag composition. Useful as a pre-flight before a real release window opens.

```
/release "1.4.0" --dry-run
```
Validates that an explicit version `1.4.0` would pass every gate without committing the tag.
Combine when the operator wants to pre-confirm a planned version against the current SHA.

---

## When NOT to Use

- **Tagging an in-progress branch.** `/release` operates only on the configured release branch
  with a clean working tree. Use `/feature` / `/fix` to land work first.
- **A hotfix that bypasses a gate.** Hotfixes that need to skip a gate are `/override` events,
  not `/release` events. There are no abbreviated releases.
- **Pushing an already-composed tag.** `/release` composes the tag locally; remote publication
  is a separate user-authorized step.
- **Producing only a changelog.** The changelog is a phase output, not the deliverable. Use the
  full command — there is no changelog-only flow.

---

## See Also

- `/checkpoint` — full cross-cutting review of the codebase; required input to release Phase 2
- `/stage` — stage promotion; consumes the release tag at stages requiring one
- `/adr-status` — surface-scan ADR health table; useful before `/release` to anticipate Phase 5
