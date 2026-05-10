# fusion-commit-gate Skill

## Identity
Claude IS the gatekeeper for all commits. It commits because every named gate has passed — not because something looks good.

## Trigger
- User says "commit", "commit this", "go ahead and commit", or equivalent direct language.
- User says "do X and commit it" — commit happens only after X is fully complete and all gates pass.
- When the routing table entry for "commit" fires.

## Phases

### Phase 1 — Permission Gate
Verify the user has explicitly instructed a commit. The following do NOT constitute permission:
- Completing a task ("all done")
- "It looks good"
- Mid-task checkpoints
- Speculative commits ("I'll commit this since it seems ready")

If the instruction is ambiguous, ask. STOP if permission is not clear.

**Gate:** Explicit user commit instruction confirmed.

### Phase 2 — Branch Gate
Run:

```bash
git branch --show-current
```

If the current branch is `main`: STOP. Output the error. Do not proceed. The agent MUST NOT commit to `main` under any circumstances.

**Gate:** Current branch is not `main`.

### Phase 3 — Classification
Examine the staged (or to-be-staged) files. Classify the change:

| Type | Scope | Description |
|---|---|---|
| `feat` | `backend`, `frontend` | New behavior + its tests + CHANGELOG entry |
| `fix` | `backend`, `frontend` | Bug fix + regression test + CHANGELOG entry |
| `test` | `backend`, `frontend` | Test additions or corrections only |
| `refactor` | `backend`, `frontend` | Code restructure, no behavior change |
| `docs` | `docs`, `agents` | Documentation changes only |
| `chore` | `ci`, `infra`, `schemas` | Config, tooling, non-functional |
| `ci` | `ci` | CI/CD workflow changes only |

If staged files span more than one type, STOP and split into separate commits — unless the user explicitly instructs combining them.

**Gate:** Change classified. Single commit type confirmed (or user explicitly approved combining).

### Phase 4 — Verification Gates
Run the gates that match the classification:

| Change classification | Required gates |
|---|---|
| Backend source changed | `make backend-test` then `make backend-lint` — both MUST pass |
| Frontend source changed | `make frontend-test` then `make frontend-lint` — both MUST pass |
| Both backend and frontend | All four gates — all MUST pass |
| Docs / config / tooling only | `make secrets-scan` — MUST pass |

`make secrets-scan` runs on ALL commits regardless of classification.

BLOCK on any gate failure. Surface the failure output. Do not commit. Do not use `--no-verify`.

**Gate:** All applicable verification gates exit 0.

### Phase 5 — Diff Review
Run:

```bash
git diff --staged
```

Read the full output. Identify:
- Unexpected files (unrelated to the stated task)
- Accidental inclusions (`.env`, credentials, large binaries, generated files)
- Incomplete changes (half-written functions, TODO markers in new code)

STOP if unexpected content is found. Surface the discrepancy to the user.

**Gate:** Diff reviewed in full. No unexpected files. No credential or secret content. No half-written code.

### Phase 6 — Selective Stage
Stage files by explicit path only:

```bash
git add path/to/specific/file.ts
git add path/to/another/file.ts
```

MUST NOT use `git add -A`, `git add .`, or any glob/wildcard. If a file is unrelated to the current logical unit, do not stage it — leave it for a separate commit.

**Gate:** All staged files are explicit paths. No wildcard staging used.

### Phase 7 — Commit Message
Format: Conventional Commits

```
type(scope): short imperative description — 72 chars max on this line

Body: explain WHY, not what. The diff shows what.
Reference BLOCKS_S2 findings as F-NNN if applicable.
If any procedure step was waived by explicit user instruction, state it here:
  OVERRIDE: user waived Step 4 gate (make backend-test) — reason: <reason>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

For `feat` and `fix` types: MUST include a CHANGELOG entry in the `[Unreleased]` section of `CHANGELOG.md` in the same commit.

**Gate:** Commit message follows Conventional Commits. CHANGELOG updated if type is `feat` or `fix`.

### Phase 8 — Commit and Report
Run the commit. If a pre-commit hook fails:
1. Read the hook output
2. Fix the underlying issue
3. Re-run the affected verification gates from Phase 4
4. Create a NEW commit — MUST NOT `--amend`

Report to the user: commit SHA + one sentence describing what was committed. Nothing else.

**Gate:** Commit created successfully. SHA reported.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| No permission | Speculative or mid-task commit attempt | STOP |
| On main | Current branch is main | STOP |
| Gate failure | Any verification gate exits non-zero | BLOCK |
| Unexpected diff | Staged diff contains unrelated or sensitive content | STOP |
| Mixed types | Staged files span multiple commit types | STOP — split commits |
| Hook failure | Pre-commit hook fails | Fix + new commit, never --amend |

## Hard Rules
- MUST NOT `git add -A` or `git add .` — stage explicit file paths only.
- MUST NOT use `--no-verify`, `--no-gpg-sign`, or any hook-bypass flag.
- MUST NOT amend a commit that has already been pushed to a remote.
- MUST NOT commit to `main` under any circumstances.
- MUST NOT commit when `vitest` is red in any changed package.
- MUST NOT commit when `make secrets-scan` reports findings.
- MUST NOT commit speculatively — explicit user instruction required.
