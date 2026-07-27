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
input to pin it — no such input exists. **But prove the redundancy before claiming it.** The first
draft of slice 2 asserted four arms were unreachable and a NUL byte, a long segment, and concurrent
writers reached three of them. "Layered, therefore untestable" is a conclusion to earn, not assume.

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
| 2 | `worktree-fs.ts` — `unsafe()` refusal / TOCTOU arms | **+8** (est. 19) | **DONE** |
| 3 | `mutation.ts` — `antiGamingCheck`, `FARM_MUTATION_CMD` hook path, loop bounds | ~42 | |
| 4 | `exec.ts` — `numEnv`, `awaitTaskkill`, `treeKill`, `run` timeout | ~20 | |
| 5 | `farm.ts` **exported only** — `runTask`, `validate`, `cleanupFailures` | ~68 | |
| 6 | clean-export measurement, close #511 | — | |

### Budget, corrected after slice 2

Slice 2 returned **+8 branches** (85.89% branches, 100% lines on `worktree-fs.ts`).

An earlier draft of this slice stopped at +4 and justified it by calling fifteen arms
"structurally unreachable, reaching them needs fault injection". **That was wrong**, and adversarial
review proved it with ordinary inputs and no source change: a NUL byte in a path segment reaches
both non-ENOENT `lstat` arms, a 300-character segment reaches the non-EEXIST `mkdir` arm, 40
concurrent writers reach the EEXIST arm, and the containment re-check is reachable through the same
exported hook the suite already used. Redundancy is a real property of this module, but it was being
used to retire work rather than to describe it.

Eleven arms remain, and these are characterised rather than claimed:

- **Platform-dead here:** the `O_NOFOLLOW` ternary's true arm (`constants.O_NOFOLLOW` is `undefined`
  on Windows — verified).
- **Mutually redundant:** the `contained()` backstops (L96, L103, L112, L124, L125, L129) and the
  `segment === "" | "." | ".."` guard (L80). Each is reachable only once an earlier layer is
  removed; L80 in particular fires the moment the lexical guard goes, so it is a live backstop, not
  dead code.
- **Needs a genuine race:** the post-open `sameFile` check (L122) and the `verifyDirectories`
  compound (L69).
- **POSIX-only:** L70 — an ancestor rename mid-write. Windows returns EPERM renaming a directory
  with an open descendant handle, so it cannot fire on the measurement host.

Worth recording about the source, not the tests: L124/L125/L129/L130 re-check `realpath` AFTER the
handle is open, but the write goes through that retained handle — so those checks cannot change
where bytes land. `handle.stat()`/`sameFile` (L122, L136) are the only post-open checks that can.
Not changed here: touching `worktree-fs.ts` rebuilds `farm.js`, which is declared payload.

| | now | need | gap |
|---|---|---|---|
| Lines | 807/1187 = 67.73% | 831 | +24 |
| Branches | 586/967 = 60.59% | 677 | **+91** |

Remaining realistic supply: `exec.ts` ~20, `mutation.ts` ~42, `farm.ts` exported ~68 = **~130**
against a need of **91**. `mutation.ts` was sized against its uncovered report before committing to
a number this time: its arms are business logic, not layered guards, and `MUT` is an exported
mutable object, so its knobs are settable from a test with no module surgery.

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
