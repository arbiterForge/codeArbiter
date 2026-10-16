# PR #983 release-owner exercise

An independent agent exercised the current rendered release owner on
2026-10-16. This is a bounded fixture exercise, not publication or a claim that
all historical release scenarios were rerun. The agent did not read prior proof
reports or expected outcomes before selecting and executing its scenarios.

The rendered owner was SHA-256
`693f5dabc5d351ba375494ee9993933fbc9dc8bd8ee427e532444579450bdd2b`.
Its shipped release helper was
`bde7b9e3479552b5b91c29aad56f47cc870addad4052fef672ca63dee9611228`.
All six recorded owner/helper/include hashes were unchanged after the exercise.

The agent authored a disposable two-target Git repository and copied exact
helper bytes into paths containing spaces. Git for Windows Bash and the shipped
helpers performed these checks:

| Scenario | Observed result |
|---|---|
| Omitted target with two declarations | Stopped for target selection, exit 66. |
| Selected target with complete footers | Derived 1.5.0 from 1.4.2; sibling and excluded breaking commits did not affect the minor bump. |
| Selected target with missing footer | Stopped with the concrete triage record, exit 1; no derived version. |
| Separate Phase 1 step 5 simulation | New version below the complete nonempty Unreleased body and above prior releases; prior prefix/suffix preserved; notes-match exit 0. |

Each dry run preserved every fixture byte, including `.git`, and created no
scratch files in the fixture. The placement simulation changed only its
designated fixture changelog. No actionable finding was established.

Local fixture commits and tags were setup only. No remote fetch, releasehash
confirmation, manifest bump, commit-gate traversal, Phase 2/3 execution, signing,
hosted CI, live host/model loading, or publication was performed. Declared
rebuild/generate/pre-tag commands were listed, not executed. Historical exercise
44 remains preserved in the proof record and is not reattested by this run.

The accompanying JSON report records input hashes, scenarios and limitations;
the command transcript retains argv, cwd, exit status and bounded fixture output.
