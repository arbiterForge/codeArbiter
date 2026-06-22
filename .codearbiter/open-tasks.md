# Open tasks

In-flight and queued work for the codeArbiter v2 rewrite. One top-level `- ` bullet
per task. Schema and the count rule: see `plugins/ca/hooks/init-codearbiter.py`
(`OPEN_TASKS`) or `.codearbiter/specs/task-board-lifecycle.md`.

## In-flight
- [ ] v2.release.0001 - Phase 7 tone pass + marketplace publication
  - Desc: tone pass not evidenced as a distinct pass; marketplace.json present but publication not confirmed.
  - Done when: a tone-pass record exists and the marketplace listing is confirmed live.

## Carried triage (folded from the 2026-06-13 session-hygiene sprint by review-remediation 2026-06-16)
- [ ] v2.docs.0002 - Resolve the absent coding-standards.md (SH-TRIAGE-2)
  - Desc: `.codearbiter/coding-standards.md` is named as required pre-flight reading by `tdd`, `refactor`, `writing-plans`, and the author agents, but the file is absent from this repo. Confirmed still missing 2026-06-21 during the task-board-lifecycle tdd pre-flight.
  - Done when: either the file exists (style/structure/naming for the plugin's Python + TS) OR those pre-flight reads tolerate its absence.
  - Boundaries: none
- [ ] v2.security.0003 - Record/close the farm.ts assertSecureBaseUrl focused re-review (SD-02)
  - Desc: the farm.ts `new URL()` host-normalization loosening was flagged for a focused security re-review the sprint log never records. Pass-D re-examined `assertSecureBaseUrl` and confirmed it is loopback-bounded and well-tested (https unconditional, http only for bare loopback, userinfo rejected) — risk is low, but the formally-requested focused pass is still unrecorded.
  - Done when: acceptance is confirmed in writing OR the focused pass is run and recorded.
  - Boundaries: egress, secrets

## Marketplace-release review backlog (2026-06-09 eight-persona adversarial review; quick kills already landed on chore/tone-pass)
- [ ] mkt.review.0004 - Live macOS session + decide test-fixture payload exclusion (MR-10 residual)
  - Desc: live Claude Code session on physical macOS is optional (CI macos-latest covers shell semantics: /bin/sh -c, per-entry stdin). Decide whether farm.test.ts/__fixtures__/tsconfig.json should leave the published payload (no exclusion mechanism in git-sourced plugin installs — would require relocating the tools test harness).
  - Done when: a decision on the test-harness payload boundary is recorded.

## Done
- [x] v2.prep.0010 - pre-release improvement batch: pre-bash bypasses closed (62-assertion CI matrix), CI version-bump guard, /ca:doctor, pipeline resume (plan status column), README banner + threat-model table  (done 2026-06-10)
- [x] mkt.review.0011 - cold-install smoke test is now CI (ubuntu/windows/macos x REAL/STUB/NONE, 110 assertions); live Windows verify: single persona inject, H-03 git add -A block; finding: plugin cache does not refresh on unchanged version string  (done 2026-06-10)
- [x] mkt.review.0012 - plugin.json claim honesty: "drives spec-driven TDD, mechanically enforces the commit and audit-trail gates"  (done 2026-06-10)
- [x] mkt.review.0013 - CRYPTO_RE narrowed: crypto.randomUUID/getRandomValues no longer trip the gate; sensitive crypto.* members and bcrypt still do; 9-case regression passes  (done 2026-06-10)
- [x] mkt.review.0014 - plugins/ca/README.md added for the marketplace-facing directory; prerequisites + dormancy + footprint disclosed  (done 2026-06-10)
- [x] mkt.review.0015 - SMARTS Precedent row: decision-variance Phase 3 tallies lens emphasis from the decision log and cites the most-similar prior decisions  (done 2026-06-10)
- [x] mkt.review.0016 - decision-aware edit guard: ADR template gains optional governs: globs; post-write-edit.py H-12 surfaces "governed by ADR-NNNN" on matching Write/Edit  (done 2026-06-10)
- [x] mkt.review.0017 - /ca:audit promotion-packet command: assembles commits, overrides, triage, ADRs, sprint auto-decisions, open CONFIRM-NN, checkpoint findings; read-only  (done 2026-06-10)
- [x] mkt.review.0018 - stops deduped: tdd Phase 1 auto-passes spec-bijective obligations; executing-plans first stop is batch-1 checkpoint; sdd Phase 4 quality review once per scope  (done 2026-06-10)
- [x] mkt.review.0019 - /ca:chore and /ca:spike shipped (type-scaled gates / unmergeable spike branch); cataloged + routed; ORCHESTRATOR spike exception recorded  (done 2026-06-10)
- [x] mkt.review.0020 - /feature Step 0 change-class triage: mechanical small-lane criteria, one-reply mini-spec, classification logged to triage.log; full tdd + commit-gate both lanes  (done 2026-06-10)
- [x] mkt.review.0021 - farm setup doc ships at CLAUDE_PLUGIN_ROOT/includes/farm.md; all five references repointed from the never-scaffolded .codearbiter/farm.md  (done 2026-06-10)
- [x] mkt.review.0022 - farm Windows-compat: windowsVerbatimArguments for cmd.exe shell lines, forward-slash normalization in the worker write guard; 10/10 green, farm.js rebuilt  (done 2026-06-10)
- [x] mkt.review.0023 - /dev env-gated (CODEARBITER_DEV=1) + entry/exit logged; /sprint un-hidden as flagship; dev/arbiter/sprint registered as real commands  (done 2026-06-10)
- [x] v2.build.0030 - Phase 2: plugin skeleton, activation hook, gated statusline, .codearbiter/ layout, ORCHESTRATOR.md, tdd reference-migration pattern  (done 2026-06-13)
- [x] v2.build.0031 - Phase 3: core skills (tdd, commit-gate, decision-variance, debug, refactor, context-creation, decompose)  (done 2026-06-13)
- [x] v2.build.0032 - Phase 4: dynamic-workflow layer (brainstorming, writing-plans, subagent-driven-development) + supporting skills  (done 2026-06-13)
- [x] v2.build.0033 - Phase 5: spec-driven /feature; hidden /sprint; /dev preserved  (done 2026-06-13)
- [x] v2.build.0034 - Phase 6: bulk migration + deletions per approved dispositions; legacy tree removed  (done 2026-06-13)
- [x] v2.build.0035 - Phase 7 (partial): README, docs/statusline.png, marketplace.json, plugin.json, CI workflow  (done 2026-06-13)
