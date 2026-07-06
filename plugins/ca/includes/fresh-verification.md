# Fresh-run verification

The shared proof-by-fresh-evidence discipline. Used by `subagent-driven-development` Phase 4 (per
accepted task, against the task's verification command) and `commit-gate` Phase 5 (the whole change,
against the spec's acceptance criterion). Each caller supplies its own target; this is the common rule.

A green suite proves the tests pass — not that the change does what was asked. Before accepting or
committing:

- **Run the proving command FRESH**, in a clean invocation, in this phase. Do not accept a logged
  result from an earlier phase, and never trust a subagent's self-report.
- **Read the actual output AND the exit code.** A non-zero exit, or output that does not demonstrate
  the obligation/acceptance criterion, fails the gate and returns the work for correction.
- A self-reported "it works" is never evidence — proof is.

**No success language before evidence.** Do not write "Done", "Perfect", "Great", "All working" —
or any phrasing that implies success, exact or paraphrased — before the proving command has run IN
THIS PHASE and its output was read. State the result the evidence supports, nothing ahead of it.

**What proves a claim — and what only looks like it does:**

| Claim | Required evidence | NOT sufficient |
|---|---|---|
| Tests pass | The runner's output and exit code from a fresh run | An earlier phase's log; "the suite was green before" |
| The change works | Output demonstrating the obligation/acceptance criterion | Tests passing alone; the code "looking right" |
| Agent completed its task | The diff exists and the proving command passes on it | The agent reporting "success" |
| Lint/type-check clean | The tool's output: zero errors, this run | A partial check; extrapolating from touched files |

**Rationalizations — already refuted:**

| Excuse | Reality |
|---|---|
| "Should work now" | RUN the command. "Should" is a prediction, not evidence. |
| "The suite passed two phases ago" | The tree changed since. Fresh run or no verdict. |
| "The subagent said it verified" | A self-report is a claim. Re-run the proving command yourself and read its exit code. |
| "The output looks roughly right" | The criterion is exact — match it or fail the gate. Roughly is a miss. |
