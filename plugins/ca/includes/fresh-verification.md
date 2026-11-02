# Current verification evidence

Verify the caller's actual task or acceptance criterion before claiming completion.
Read the command, cwd, relevant source and input identities, output and exit code.
A result is reusable across a delegated handoff, execution, commit and PR preparation when those inputs
still match and the observed behavior proves the required claim.

- Reuse inspected current results, including an earlier phase's result. A phase
  transition, bookkeeping edit or new receipt ID alone requires no rerun.
- Run the missing or affected check when evidence is absent, its inputs changed,
  its scope is insufficient, or its outcome is unresolved. A passing general suite
  cannot replace a missing criterion-specific check.
- Inspect delegated command output and its source binding before relying on it.
  A self-report without accessible evidence is insufficient.
- A changed runner, requirement or relevant input invalidates only the claims it affects.
  An unrelated edit, new task label or new PR does not erase other inspected results.
- Keep a relevant failure or contradictory later result visible until resolved.
  Correct the affected work and rerun its check; preserve unrelated valid results.
