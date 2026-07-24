# Gap 03: No guidance on concurrent/simultaneous dual-host use of the shared store

**Severity:** low

**Page(s):** `site/src/content/docs/getting-started/claude-code-and-codex.md`

## What the user was trying to do

A team wants to have one person driving Claude Code and another driving Codex against the same checked-out repo at the same time (not sequentially), both writing to `.codearbiter/` — e.g., both running commit-gate or task-board mutations in the same working tree in the same session window.

## What's missing

The page states parity claims about "controlled concurrent append-only audit writes with host attribution and no lost records" (CI-verified) and describes alternating hosts or two people on *different checkouts*, but never addresses two hosts writing to the *same working tree* concurrently — e.g., whether `open-tasks.md`/`overrides.log` writes can race, what happens if both hosts try to flip the same task, or whether this scenario is supported/recommended at all. A user attempting this pairing pattern has no documented answer and would have to test it themselves.

## One-line remediation shape

Add a short "Same checkout, same time" subsection under "Use one repository from either host" stating the supported concurrency model (e.g., sequential-per-checkout only; same-tree concurrent writes untested/unsupported) or pointing to the CI evidence file for the actual guarantee scope.
