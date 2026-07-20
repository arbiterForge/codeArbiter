# Hackathon PR #313 integration receipt

## Scope

PR #313 absorbs 16 GPT-authored corrective and parity PRs, represented by 29
source commits and 126 unique manifest paths. Dependabot PR #336 remains outside
the submission because it is automated dependency maintenance rather than
hackathon implementation or corrective analysis.

The exact inventory is in `source-prs.json`; machine-readable application
receipts are in `apply-receipts.json`.

## Application result

- Every source commit has an application receipt.
- 123 of 126 manifest paths appear directly in the integrated diff.
- The remaining three paths are the former monolithic `pre-bash.py` copies from
  PR #347. PR #313 had already extracted their H-05 logic into
  `_bashguardlib.py`, so the behavior was ported into the canonical shared core
  and synchronized to Claude Code, Codex, and Pi. This produces four target
  paths and preserves the thin host entry points.
- All other source patches applied directly or were composed with the current
  Pi-era content. No source behavior was silently discarded.

## Conflict decisions

1. H-05 Git checkout/restore protection lives in the extracted shared guard
   core, including separated-value Git global options. The focused guard matrix
   passed 142 assertions after the port.
2. Site generator copy retains both the Pi/Codex host note and the request-flow
   link. The sandbox diagram precedes, rather than replaces, the Pi trust and
   child-process section.
3. Codex documentation reflects current host-provided subagents while keeping
   context creation's stricter isolated-scout requirement.
4. Changelogs retain the Pi unreleased section, the 2.9.1 tribunal fix, and the
   prune-metric correction. The README retains the Pi badge and reports 2.9.1.
5. The docs-mirror board item remains done; the conflicting source hunk was its
   earlier in-progress transition.

## Append-only audit handling

Source audit additions were appended in source-commit order. The five H-05
gate events retain all three identical events emitted at 05:54:34Z.

Commit `09d7818ae2de527b7c4d3d320beaa81ccff81e28` repaired a historical
missing-newline join by rewriting the source branch's final line. Reproducing
that rewrite here would violate H-05. The integrated history instead appends
the intended PR-gate remediation and its correction as two separate records,
followed by a SMARTS decision explaining the normalization. Existing audit
bytes were not removed or rewritten.

## Recovery and preservation

Patch material remains at
`C:/Users/brenn/AppData/Local/Temp/ca-hackathon-apply-74b1c39cf5714703a0cb53ecf50ced05`.
Integration is isolated in
`C:/Users/brenn/projects/codeArbiter-worktrees/integrate-hackathon-pr313`.
The user's primary checkout, untracked plans/spec, gate-event changes, stash,
and existing worktrees have not been modified or cleaned.

## Local verification

- Canonical Python scripts and the 1,057-test hook suite pass.
- The H-05 matrix passes 142 assertions.
- Farm typecheck, 198 tests, build freshness, and critical-level audit pass.
- Pi typecheck/build/tests, all 12 security controls, 18/18 live process-tree
  variants, and the fixtures-only platform aggregate pass.
- The docs site passes typecheck, 418 tests, a 129-page production build, and
  an 18,483-link audit.
- Shared Python, generated host surfaces, host packages, JSON manifests,
  Python compilation, reference graph, secret preview, and diff checks pass.
- The one integration defect found by the site suite was a missing third
  activation-state diagram reference in `enforcement.md`; restoring the source
  PR's figure made the full site lane green.

## First hosted candidate feedback

Candidate `bff646957a60e001ae54eaec1f9dcf0c62d34025` passed its commit gate,
was pushed to `feat/pi-support`, and became PR #313's hackathon candidate.
The PR title/body enumerate all sixteen absorbed PRs and their issue closures,
so T-11 is accepted.

Hosted run `29772317278` passed the supported Pi matrix, Pi security, farm,
sandbox, and site lanes; CodeQL run `29772314303` also passed. The generated
surface, hook, and documentation contracts correctly rejected one source-of-
truth drift: #351's isolated-scout behavior was present in the Claude render,
but absent from canonical `core/surface/agents/scout.md` and therefore from the
Pi render. The existing generator regression reproduced the defect RED.

The canonical scout contract now carries the isolated `context-creation`
boundary and regenerates the Pi copy. The exact surface and documentation
checks pass, all 25 hook-contract steps pass, and the hook unittest suite passes
1,057 tests when Git Bash is available on Windows as required by that fixture.
This repair requires a new candidate commit and hosted run before T-12 can be
accepted.

The replacement candidate's first hosted attempt then encountered two
independent runner outcomes. Pi security failed before checkout after three
action-download timeouts and passed unchanged on retry. Windows Pi 0.80.5
repeatedly reached the same Vitest ceiling in the live contained-child proof:
117 sibling checks passed, but the proof was limited to 20 seconds after #367
had added a second bounded 15-second admission attempt. Its own allowed work
also includes a 10-second output wait and a 5.25-second cleanup window. The
test-only ceiling is now 60 seconds so Vitest can observe those existing
bounded outcomes; no production admission, output, or cleanup timeout changed.
Typecheck and three consecutive focused Windows runs pass locally. A new hosted
candidate is still required before T-12 can be accepted.

Replacement candidate `64086bb1b6a1f75676db36fe9bbeb18367333297`
completed main CI run `29775519583`, CodeQL run `29775517282`, and docs run
`29775519576` successfully on the exact head. All six supported Pi cells,
Pi security, all hook platforms, sandbox, farm, docs, generators, references,
version gates, the repository aggregate, and merge readiness are green. T-12
is accepted.

Fresh Windows-local platform contracts pass on Pi 0.80.5 in 104,240 ms and
Pi 0.80.10 in 103,985 ms. The global Pi CLI was restored to 0.80.10. The
sanitized evidence generator successfully assembled those measurements and
candidate-matched hosted durations for
`64086bb1b6a1f75676db36fe9bbeb18367333297`; the unchanged real 0.80.6 refusal
canary remains `VERSION_UNSUPPORTED`.

The strict final replay then exposed a consolidation-boundary gap: its legacy
evidence-only allowlist admitted the Pi plan and handoff receipt but not this
approved hackathon plan and integration receipt. A regression now requires
exact admission of only those two files; arbitrary report or plan paths remain
rejected. The generated promotion pair was restored to its prior committed
state until this verifier change earns a new hosted candidate.

Replacement candidate `f764929e02fbb67b43a3b828686c0007445a0316`
completed main CI run `29777295584`, CodeQL run `29777291834`, and docs run
`29777295518` successfully on the exact head. The same full candidate inventory
is green, including all six supported Pi cells and merge readiness.

Post-candidate Windows-local contracts pass on Pi 0.80.5 in 104,547 ms and
Pi 0.80.10 in 103,745 ms, with the global CLI again restored to 0.80.10. The
sanitized promotion pair now binds those measurements and candidate-matched
hosted durations to `f764929e02fbb67b43a3b828686c0007445a0316`; the unchanged
real 0.80.6 refusal canary remains `VERSION_UNSUPPORTED`.

The strict final verifier passes all 46 canonical repository gates, the exact
hosted attestation and sanitized rendering, and PI-AC-01 through PI-AC-38 in an
isolated `feat/pi-support` clone at the exact candidate SHA. T-13 is accepted.

Evidence-only commit `6173b1d4d2ae6380ef577fd631131c9469a898c1`
passed the commit gate and exact-head main CI run `29778968354`, CodeQL run
`29778964688`, and docs run `29778968433`. Both Windows Pi cells, sandbox, all
other repository checks, and merge readiness are green. T-14 is accepted.

After that exact-head success, source PRs #347, #348, #349, #350, #351, #354,
#356, #357, #358, #359, #360, #362, #363, #365, #367, and #368 were each
closed unmerged with one redirect comment to #313. A fresh API audit proves all
16 remain at their manifest-recorded heads, all 16 redirects cite the final
evidence head, all 16 appear in #313's body, and #313 remains open and
unmerged. T-15 is accepted; the single-PR consolidation is complete.
