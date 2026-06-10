# Open tasks

In-flight and queued work for the codeArbiter v2 rewrite. One `- ` bullet per task
(the statusline and SessionStart hook count these).

## In-flight
- Phase 7: tone pass (not evidenced as a distinct pass), marketplace publication (marketplace.json present but not confirmed published).

## Marketplace-release review backlog (2026-06-09 eight-persona adversarial review; quick kills already landed on chore/tone-pass)
- MR-10 (residual): live Claude Code session on physical macOS — optional; the CI macos-latest leg covers shell semantics (/bin/sh -c, per-entry stdin). Decide whether farm.test.ts/__fixtures__/tsconfig.json should move out of the published payload (no exclusion mechanism in git-sourced plugin installs — would require relocating the tools test harness).

## Done
- MR-10 (automated, 2026-06-10): cold-install smoke test is now CI (`hooks — cold-install matrix`, ubuntu/windows/macos × REAL/STUB/NONE PATH scenarios, .github/scripts/test_hooks_cold_install.py) — 110 assertions prove single persona injection, fallback-delivered exit-2 blocks under a Store-alias python3 stub (exit 9009, invocation-marked), dormancy in non-enabled repos, and LOUD failure with no Python. Live Windows client verified: persona injects exactly once on session start; `git add -A` via Bash is BLOCKED with the verbatim H-03 message and nothing reaches the index. Finding: the plugin cache does NOT refresh on `plugin update` when the version string is unchanged (stale v1 bash hooks.json survived a marketplace refresh; uninstall+reinstall required) — bump plugin.json version with any hooks change once 2.0.0 is published.
- MR-12 (2026-06-10): plugin.json claim honesty — "drives spec-driven TDD, mechanically enforces the commit and audit-trail gates".
- MR-11 (2026-06-10): CRYPTO_RE narrowed — crypto.randomUUID/getRandomValues no longer trip the gate; sensitive crypto.* members (subtle, sign, randomBytes, pbkdf2, …) and bcrypt still do. 9-case regression passes.
- MR-10 (partial, 2026-06-10): plugins/ca/README.md added for the marketplace-facing directory; prerequisites + dormancy + footprint disclosed.
- MR-9 (2026-06-10): SMARTS Precedent row — decision-variance Phase 3 tallies lens emphasis from the decision log and cites the 1–3 most-similar prior decisions under each table ("Precedent: none on record" on thin history); smarts.md tie-handling cross-references it.
- MR-8 (2026-06-10): decision-aware edit guard — ADR template gains optional `governs:` path globs; post-write-edit.py H-12 surfaces "governed by ADR-NNNN" on matching Write/Edit (mtime-keyed cache at .markers/governs-cache.json; superseded/rejected ADRs excluded). Verified: match, no-match, superseded, cache.
- MR-7 (2026-06-10): /ca:audit promotion-packet command — assembles commits, overrides (incl. DEV/SECURITY), triage classifications, ADRs, sprint auto-decisions, open CONFIRM-NN, and open checkpoint findings for a window into .codearbiter/audits/<date>.md; read-only, never overwrites, quotes audit lines verbatim. Cataloged + routed + README row.
- MR-6 (2026-06-10): stops deduped — tdd Phase 1 auto-passes spec-bijective obligations (user reviews only beyond-spec additions; /sprint inconsistency resolved); executing-plans Phase 1 breakdown is informational, first stop is the batch-1 checkpoint; sdd Phase 4 quality review runs once per scope over the combined diff with HIGH findings attributed back per task. ~7 stops → ~4 for a small feature.
- MR-5 (2026-06-10): /ca:chore (docs/deps/revert, type-scaled gates, always exits via commit-gate) and /ca:spike (spike/* branch, never merges, exits to .codearbiter/spikes/<slug>.md or /feature; commit-gate exemption scoped to the unmergeable branch) — cataloged + routed; ORCHESTRATOR §3 spike exception recorded.
- MR-4 (2026-06-10): /feature Step 0 change-class triage — mechanical small-lane criteria, one-reply mini-spec confirmation, classification logged append-only to .codearbiter/triage.log (now hook-guarded like overrides.log); full tdd + commit-gate retained in both lanes; ORCHESTRATOR §0.2 + routing table updated; /reconcile-vs-/conflict tiebreaker added to routing table. (/fix was already the lean lane for defects.)
- MR-3 (2026-06-10): farm setup doc now ships at ${CLAUDE_PLUGIN_ROOT}/includes/farm.md; all five references (ORCHESTRATOR, SPRINT, writing-plans ×2, farm-dispatch) repointed from the never-scaffolded .codearbiter/farm.md.
- MR-2 (2026-06-10): farm Windows-compat fixed — windowsVerbatimArguments for cmd.exe shell lines (gate, mutation runner), forward-slash normalization in the worker write guard; 10/10 tests green, typecheck clean, farm.js rebuilt in sync.
- MR-1 (2026-06-10): /dev env-gated (CODEARBITER_DEV=1) + entry/exit logged to overrides.log; /sprint un-hidden as flagship; secrecy clauses deleted; dev/arbiter/sprint registered as real commands (commands/{dev,arbiter,sprint}.md); COMMANDS.md Maintainer section; README /ca:sprint row; ref-checker hidden-command rule removed.
- Phase 2: plugin skeleton, activation hook, gated statusline, `.codearbiter/` layout, `ORCHESTRATOR.md`, `tdd` reference-migration pattern.
- Phase 3: core skills (tdd, commit-gate, decision-variance, debug, refactor, context-creation, decompose).
- Phase 4: dynamic-workflow layer (brainstorming, writing-plans, subagent-driven-development) + supporting skills.
- Phase 5: spec-driven /feature; hidden /sprint; /dev preserved.
- Phase 6: bulk migration + deletions per approved dispositions; legacy tree removed.
- Phase 7 (partial): README, docs/statusline.png, marketplace.json, plugin.json, CI workflow.
