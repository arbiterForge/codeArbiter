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
