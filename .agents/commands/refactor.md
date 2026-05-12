# /refactor "surface and motivation"

## Purpose

Restructure existing code without changing observable behavior. The only permitted path to begin
refactor work. Routes to the `refactor` skill, which proves behavioral parity through pre-existing
test coverage before any edit lands and refuses to accept modified tests as evidence of correctness.

A refactor that cannot demonstrate parity through unmodified pre-existing tests is not a refactor —
it is a feature change in disguise and will be re-routed to `/feature`.

## Usage

```
/refactor "description of surface and motivation"
```

The description has two required parts:

1. **Surface** — the exact files, functions, classes, or methods being restructured. Vague surfaces
   ("the auth module", "some helpers in utils") will be rejected at Phase 1. A reader must be able
   to grep the repo for the named symbols and arrive at the same file set.
2. **Motivation** — why the restructure is worth doing (e.g., "to remove the duplicated retry logic
   between `httpClient` and `wsClient`", "to extract `signToken` from `auth/index.ts` into its own
   module before further auth changes land").

## What it routes to

`refactor` skill (`${FRAMEWORK_ROOT}/.agents/skills/refactor/SKILL.md`) — all six phases:

1. **Phase 1 — Surface Identification:** lock the exact files, symbols, and public signatures.
2. **Phase 2 — Behavioral Parity Coverage Proof:** demonstrate pre-existing tests already cover the
   named surface to the stage threshold, with at least one direct test per public method.
3. **Phase 3 — Red Parity Tests (conditional):** when the refactor exposes a new test seam, write
   failing tests pinning the seam's contract before implementation.
4. **Phase 4 — Implementation:** apply the restructure mechanically within the surface table; no
   new behavior, branches, error paths, or side effects.
5. **Phase 5 — Parity Verification:** the full pre-existing test suite passes with zero edits to
   any pre-existing test file.
6. **Phase 6 — Lint/Coverage Gate:** lint, type-check, and coverage all clear; surface coverage
   MUST NOT regress.

### Hard gate

**No refactor proceeds without behavioral-parity coverage proof in Phase 2.** If the named surface
is below the stage coverage threshold, or any public method has zero direct tests, the skill halts
and routes to `tdd` Phase 1 to backfill obligations and tests. Refactor resumes only after the
backfill is green.

Additional gates: a Phase 4 diff that would classify as `feat` under `commit-gate` Phase 3, or a
Phase 5 verification that depends on edits to a pre-existing test, both terminate the refactor and
re-route to `/feature` or `/fix`.

## When NOT to use

- **New behavior:** use `/feature`. If the change adds a branch, an error path, a side effect, a new
  public method beyond a Phase 3 seam, or alters the value any pre-existing input maps to, it is a
  feature, not a refactor.
- **Bug fix:** use `/fix`. A change motivated by "the current behavior is wrong" is a bug fix; its
  Phase 1 is framed around a failing regression test, not parity coverage.
- **Questions or discussion:** use `/btw`.
- **Committing an already-completed refactor:** use `/commit` — `commit-gate` still classifies and
  gates the staged diff.

## Examples

```
/refactor "extract signToken, verifyToken, and rotateKey from src/auth/index.ts into src/auth/tokens.ts so the next auth-rotation feature has a clean seam"
```

```
/refactor "rename `UserRepo.fetchById` to `UserRepo.findById` across src/users/** and update all call sites in src/api/**"
```

```
/refactor "collapse the duplicated retry-with-backoff implementations in src/http/client.ts and src/ws/client.ts into a shared src/net/retry.ts"
```

```
/refactor "inline the single-call-site helper `formatLogLine` from src/log/format.ts into src/log/emit.ts and delete the now-empty format.ts"
```

```
/refactor "split src/payments/processor.ts (currently 800 lines) into processor.ts (orchestration), validation.ts, and settlement.ts without changing the exported Processor class signature"
```

## See also

- `/feature` — for any change that adds, removes, or alters observable behavior.
- `/fix` — for confirmed bugs; Phase 1 framed around a failing regression test.
- `/commit` — for gating the staged diff after the refactor's six phases complete.
