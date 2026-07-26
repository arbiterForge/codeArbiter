# Plan — #511: raise `plugins/ca/tools` to the stage-2 coverage floor

Approved 2026-07-26. Closes #511. Companion flake filed as #515.

## Goal

`plugins/ca/tools` reaches ≥ 70% **lines and branches** (both binding, stage 2 per
`plugins/ca/includes/maturity-coverage.md`), driven by the uncovered report rather than by the
number. AC-2 is the operative constraint: a test that asserts nothing meaningful is worse than the
gap it closed.

## Measured baseline (2026-07-26, `main` @ c9c5cbc, Windows)

```
File            | % Stmts | % Branch | % Funcs | % Lines
All files       |   63.91 |    59.46 |   56.77 |   67.22
 exec.ts        |   75.22 |    63.88 |   76.00 |   81.05
 farm.ts        |   62.95 |    59.55 |   52.51 |   64.44
 mutation.ts    |   51.31 |    43.29 |   47.36 |   57.98
 redactor.ts    |   76.19 |    50.00 |  100.00 |   77.77
 worktree-fs.ts |   78.88 |    75.64 |   90.00 |   97.10
```

| | now | need | gap |
|---|---|---|---|
| Lines | 798/1187 = 67.22% | 831 | **+33** |
| Branches | 575/967 = 59.46% | 677 | **+102** |

## The binding facts

**1. Branches is binding everywhere; lines is not.** 74 uncovered lines sit outside `farm.ts`
against a need of 33.

**2. The tree cannot clear 70% branches without `farm.ts`.** Perfect coverage of the four small
modules yields ~104 against a need of 102 — no margin. At a realistic conversion rate they give
~83, so `farm.ts` must supply ~20 at minimum and ~40 for margin.

**3. `farm.ts`'s required contribution does not touch `main`.** Uncovered branches by enclosing
function:

```
  99  private  main          37  private  writeReport    24  private  runCanary
  36  EXPORTED runTask       14  private  callApi        12  EXPORTED validate
   9  private  resolveConfig  8  private  bestOfN         ...
  EXPORTED: 68    private: 220
```

`runTask` has a 10-point `RunTaskDeps` injection seam already driven by `farm.unit.test.ts`.

**4. Subprocess tests contribute zero coverage.** `farm.test.ts` (48 tests) and `farm-dist.test.ts`
(14 tests) run the dispatcher via `spawn(process.execPath, ...)`. The v8 provider does not
instrument child processes. This is why `farm.ts` sits at 64% lines despite heavy end-to-end
testing — and it means the 220 private-function branches are unreachable by *any* coverage-visible
test in the current harness style, not merely expensive. Slice 5's export-surface-only scope is
therefore the only option, not a preference.

## Test standard (binding on every slice)

> Every new test must carry at least one assertion that fails if the **property** the covered line
> enforces is removed — a negated condition, a changed constant, a removed statement, an off-by-one
> boundary.

Per test: *if I flip this `if` in the source, does my test go red?* Exact values over
`toBeDefined()`; exact call arguments over `toHaveBeenCalled()`; both sides of every branch claimed;
error identity **and** observable consequence. No broad snapshots, no lone `not.toThrow()`, no
asserting on a mock instead of the subject.

### Amended after slice 2 — "line" was the wrong unit

The original wording said *"fails if the LINE it covers is mutated"*. That is **unsatisfiable by
construction for layered code**, and `worktree-fs.ts` proved it: 4 of 24 single-point mutants died,
yet every survivor was a guard whose property another layer also enforces. Removing all four
`isSymbolicLink()` checks passes (a Windows junction also fails `isDirectory()`); removing all three
`isDirectory()` checks passes (`isSymbolicLink()` catches it). Redundant guards cannot be
distinguished from outside the module — that is what defence in depth *means*.

So the unit is the **property**, not the line, and the mutation harness needs a multi-edit mode that
removes every layer guarding one property at once (`mutate-multi.mjs`). A single-point survivor on a
layered module is evidence about the design, not about the test.

Where a single guard is *fully* redundant with another, say so and move on rather than inventing an
input to pin it — no such input exists.

Each slice runs a hand mutation pass: mutate the covered source lines, show the tests go red,
restore. **A control run on unmutated source must pass first** — a harness whose control fails
proves nothing.

## Slices

Each: branch from `main` (never stacked) → work → full suite + the Python suites named in
`tech-stack.md` → `commit-gate` → PR → verify CI actually ran → adversarial review → fix → merge.
Test-only, so `test(farm):` and no version bump (see Constraints).

| # | target | branches | status |
|---|---|---|---|
| 1 | `redactor.ts` — PEM span boundaries, basename denylist | +3 | **DONE** (#517) |
| 2 | `worktree-fs.ts` — `unsafe()` refusal / TOCTOU arms | **+4** (est. 19) | **DONE** |
| 3 | `mutation.ts` — `antiGamingCheck`, `FARM_MUTATION_CMD` hook path, loop bounds | ~45 | |
| 4 | `exec.ts` — `numEnv`, `awaitTaskkill`, `treeKill`, `run` timeout | ~20 | |
| 5 | `farm.ts` **exported only** — `runTask`, `validate`, `cleanupFailures` | ~68 | |
| 6 | clean-export measurement, close #511 | — | |

### Budget, corrected after slice 2

Slice 2 returned **+4 branches, not the estimated 19**. Fifteen of `worktree-fs.ts`'s uncovered arms
are structurally unreachable through the public API — an earlier layer always fires first — plus one
that is platform-dead (`O_NOFOLLOW` is `undefined` on Windows, so the true arm of that ternary cannot
be taken) and one whose guard (`segment === "" | "." | ".."`) cannot trigger because
`path.resolve` + `path.relative` normalise those segments away before the split. Reaching them needs
fault injection, i.e. new test seams in the source — and a source change to `worktree-fs.ts` rebuilds
`farm.js`, which **is** declared payload, forcing a `ca` version bump for coverage's sake. Not worth
it; recorded instead.

| | now | need | gap |
|---|---|---|---|
| Lines | 803/1187 = 67.64% | 831 | +28 |
| Branches | 582/967 = 60.18% | 677 | **+95** |

Remaining realistic supply: `exec.ts` ~20, `mutation.ts` ~55, `farm.ts` exported ~68 = **~143**
against a need of **95**. Feasible, but it needs ~66% conversion across all three — slice 5
(`farm.ts`'s exported surface) is now load-bearing rather than a top-up, and slices 3–5 have no
slack for another over-estimate.

Slice 1 is deliberately small so the file convention and the mutation bar are validated on a
cheap surface before slices 3–5 scale them.

### Sequencing note

`worktree-fs.ts` is **not** "effectively done". That reading comes from the line column (97.1%). On
branches it is 75.64% with 19 uncovered arms, every one an `unsafe()` refusal — symlinked root,
containment escape, `mkdir` EEXIST race, hardlink (`nlink !== 1`), and the three TOCTOU
re-verifications before the retained handle is truncated. Largest security-refusal gap outside
`farm.ts`, and exactly AC-3.

## Constraints and known-unreachable

- **No version bump for test-only slices.** `payload_scope.py` excludes `plugins/ca/tools/` from
  `ca`'s payload except `farm.js`. Any edit to `farm.ts` forces a `farm.js` rebuild, which **is**
  declared payload → `ca` version bump + `farm-dist.test.ts` parity re-check. A further reason
  slice 5 stays inside the existing export surface.
- **`redactor.ts:106` has an unreachable branch.** `relPath.split(...).pop() ?? relPath` — `split`
  never returns an empty array, so the `??` right arm is dead. It exists only because TypeScript
  types `pop()` as `T | undefined`. Not chased.
- **~6 branches are platform-dead.** Measurement host is Windows, so `exec.ts`'s POSIX `treeKill`
  block and the non-win32 arms of `SHELL_BIN` / `SHELL_OPTS` / `detached` are unreachable without
  stubbing `process.platform` behind `vi.resetModules()`. Budgeted as unreachable.
- **#515** — `farm.test.ts` `#387` escalates one of 12 tasks under six-way concurrency in full-suite
  runs. Pre-existing, load-sensitive, will intermittently redden CI during this work. Out of scope
  here (this backfill adds no behaviour and modifies no pre-existing test).

## Acceptance

- AC-1: ≥ 70% lines and branches, measured by `npm --prefix plugins/ca/tools run coverage`, from a
  clean export (`git archive HEAD | tar -x` + `npm ci --ignore-scripts`), not the dev tree — local
  `.farm/` state skews the line figure by ~0.1.
- AC-2: every added test pins a real behaviour; the mutation pass is the evidence.
- AC-3: error and refusal paths before happy paths.
- AC-4: no pre-existing test modified.
