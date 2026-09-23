# Release closure — cross-cutting journeys (T-20)

**Purpose.** AC-09, AC-10, AC-11, AC-12, AC-13, AC-15, AC-16: a cross-cutting integration
proof exercising this sprint's changes together, end to end, through real consumer
fixtures (`.github/scripts/test_consumer_smoke.py`'s established
`build_consumer_repo`/materialization idiom) — never live GitHub/npm, no network calls, no
actual publication. This report documents the scenario matrix; it does not restate
per-fix proof that T-01 through T-19/R-01 through R-04 already established in isolation.

**Candidate bytes.** This entire worktree is staged-but-not-committed (`git status` at the
start of this task showed every governed file as `M`/`A`, none committed). "NEW behavior"
below means the current working tree of `core/pysrc/_releaselib.py` and
`core/surface/skills/release/SKILL.md`. "OLD behavior" means the exact committed `HEAD`
bytes of the same two files, read via `git show HEAD:<path>` — a free, hermetic,
exact-byte oracle requiring no history rewrite and no network, confirmed in this task to
genuinely lack `verify-tag-ancestor` and the "Verify it immediately, before" Pre-flight
step. No test in this task (or added by it) reads a live GitHub/npm endpoint, mutates a
publisher, or creates a real GitHub Release; every tag created is a local, throwaway
annotated tag inside a scratch repo that is deleted at test teardown.

**Host and platform.** All evidence in this report is local, Windows, this task's own run.
No cross-platform or hosted-CI claim is made anywhere below — exhaustive cross-platform
proof is exact-head hosted CI's job, per `verification-boundary`. This is an open,
unmerged candidate; nothing below is a "shipped release" claim.

---

## 1. New test classes added by this task

All three are new in `.github/scripts/test_consumer_smoke.py` (bottom of file, after
`BackfillBranchRefusalTest`). `.github/scripts/test_release_lib.py` was **not** modified —
every AC-09 through AC-16 obligation that belongs at the unit/fixture level (ancestry
graphs, breaking classification, Phase 2 mutation-sensitive structure proofs, prerequisite
surface prose) is already covered there by T-10 through T-19's own tests; re-deriving that
coverage here would be redundant, not additive. This task's job is the cross-cutting
*journey* view, which only `test_consumer_smoke.py`'s real-consumer-fixture idiom can
provide.

| Class | Tests | What it proves | New vs. cited |
|---|---|---|---|
| `ComposedFixLaneJourneyTest` | 1 | THREE #570 fixes (prerequisite refusal T-12, branch-scoped back-fill refusal T-13, ancestry refusal T-10/T-11) driven against **one** real consumer repo in the order an operator hits them, ending in a genuine clean pass that creates a real local annotated tag through the #623-restructured Phase 2 | genuinely new — nothing else in this module chains these arms against a single repo |
| `AncestryOldVsNewBehaviorTest` | 3 | OLD (committed `HEAD`) lane run for real against the exact #570 finding-BODY-03 hazard, contrasted with NEW (working-tree) lane on the identical fixture | genuinely new — the "OLD would have done the wrong thing" arm, run as real code rather than narrated |
| `BreakingChangeRealHistoryClassificationTest` | 5 | AC-12's classification half (`classify_window`'s `breaking` field and real-order headline selection) driven by a REAL git history extracted via `git log`, not hand-typed commit dicts | new at the classification layer; composition (the literal `### Breaking` Markdown heading) is agent-executed SKILL.md prose, not code — cited, not re-proven (see §3) |

Total: **9 new tests**, all passing. Full before/after counts: this module ran 94 tests
(93 passed, 1 skipped) before this task; it now runs **103 tests (102 passed, 1 skipped)**.
The one skip (`test_plugin_root_preserves_executable_bits`, `ConsumerFixtureTest`) is
pre-existing, unrelated to this task, and self-documents its cause: "no POSIX executable
bit on win32" — this task's run is on Windows, so that skip is expected, not a gap.

---

## 2. #570's intended behavior changes — exercised as real behavior changes

Kept strictly separate from #623 below, per the plan's own instruction.

### 2a. Old-vs-new contrast (`AncestryOldVsNewBehaviorTest`)

The single most-validated finding in this sprint's scope (spec §"Phase-1 revalidation":
"the single most-validated item in this scope... what the last blind-exercise run... found
on a clean pass") is `last_tag_select`'s ancestry blindness. This class proves the OLD-vs-
NEW contrast as **executed code**, not narration:

- `test_old_bytes_have_no_ancestry_verification_at_all` — a class-level precondition,
  proven directly rather than merely asserted in a docstring: `HEAD`'s
  `core/pysrc/_releaselib.py` contains zero occurrences of `verify-tag-ancestor` /
  `verify_tag_ancestor`; `HEAD`'s `SKILL.md` contains zero occurrences of either string.
  The working-tree copies of both contain them. This confirms the two arms below are
  genuinely comparing different states, not the same file read twice under different
  names.
- `test_old_lane_selects_the_hazard_and_has_no_step_left_to_catch_it` — builds the exact
  sibling-branch hazard fixture (`AncestryDocumentedFlowTest`'s own scenario: a tag on a
  branch that diverged *before* the tag, never merged back, numerically the highest in its
  series). Runs the OLD `LAST_TAG=$(...)` pipeline extracted from `HEAD`'s own SKILL.md
  text (not hand-typed) against the OLD `_releaselib.py`: selection correctly picks the
  hazardous `v9.9.9` (selection predates this sprint and is unaffected, matching AC-09's
  own "existing version-policy selection... unaffected" clause). Then proves there is
  *no next step* for an operator following the OLD documented flow to reach: structurally,
  no "ancestor" mention anywhere between LAST_TAG resolution and `## Phase 1` in `HEAD`'s
  prose; executably, invoking `verify-tag-ancestor` against the OLD library's own CLI
  returns a "bad invocation" usage error (exit 2, unrecognized subcommand) — not a
  refusal, because the capability did not exist.
- `test_new_lane_selects_the_same_hazard_and_refuses_it` — the identical fixture, the NEW
  two-command Pre-flight sequence extracted from the working-tree SKILL.md: selects the
  same `v9.9.9`, then `verify-tag-ancestor` returns exit 1, naming the tag in stderr — a
  genuine refusal.

This is real, executed evidence of the wrong-old / correct-new arms the task asked for,
not merely today's already-passing `AncestryDocumentedFlowTest`/`AncestryGraphsTest`
proof that the NEW behavior alone is correct.

### 2b. Multi-fix composition (`ComposedFixLaneJourneyTest`)

One consumer repository, one sequential test method, seven stages:

1. **Zero-state, prerequisite refusal precondition** (T-12, AC-10) — no `tech-stack.md`;
   repo fingerprint (`git status --porcelain` + `git for-each-ref`) unchanged by the
   unresolved check alone.
2. Clear the prerequisite (write `tech-stack.md`).
3. **Still on the protected branch — back-fill branch-refusal precondition** (T-13,
   AC-11) — `backfill-detect` still only *prints* the candidate block; no
   `release-targets.md` write; fingerprint unchanged.
4. Move to a feature branch (clears the branch check) and declare
   `.codearbiter/release-targets.md`, committing it — as back-fill's own persist step
   would.
5. **An ancestry hazard on the SAME repo** (T-10/T-11, AC-09) — a release tag minted on an
   unmerged side branch, numerically highest in its "v" series but not an ancestor of the
   feature branch's `HEAD` (a descendant, not merged back — a realistic shape: "someone
   tagged a release on a topic branch that never landed"). `last-tag-for-policy` correctly
   selects it; `verify-tag-ancestor` correctly refuses (exit 1, tag named in stderr);
   fingerprint unchanged.
6. **Fix the graph** — a real `--no-ff` merge brings the tagged commit into ancestry, plus
   one genuine `feat:` commit with a `CHANGELOG:` footer. Re-running the same two-command
   sequence: selection is unchanged (still `v9.9.9`, proving AC-09's "existing... selection
   is unaffected" holds even mid-journey), and ancestry verification now passes cleanly.
7. **Clean pass** — re-runs T-74/T-75's own six-anchor lane driver
   (`_execute_lane_sequence`) against this exact post-fix repo state: derives `bump="minor"`
   (the merge commit itself carries no bumping type and correctly does not drive the bump;
   only the trailing real `feat` commit does), `next_version="9.10.0"`, rolls the changelog
   section, and creates a **real local annotated tag** — proven by `git cat-file -t` on the
   resulting ref.

Every refusal stage (1, 3, 5) asserts the repo's `(git status --porcelain,
git for-each-ref)` fingerprint is byte-identical before and after — the same
mutation-detection idiom `AncestryDocumentedFlowTest` already uses — so a refusal that
silently no-oped past a write would fail this test, not merely pass by coincidence. This
proves what no single-fix class in this module previously proved: an earlier refusal's
no-op leaves the repo in a state the *next* fix can still correctly act on, and a consumer
who clears every refusal in order reaches a genuine, correctly-derived release.

### 2c. Breaking-change visibility (`BreakingChangeRealHistoryClassificationTest`) — AC-12

**Composition is agent-executed prose, not code, and this report does not claim
otherwise.** The literal `### Breaking` Markdown heading in a composed changelog
section/tag message/Release notes is written by the release skill's own Phase 1 step 5
prose (SKILL.md), reusing the `breaking` field `classify_window` already computes. There
is no production "compose the notes" function in `_releaselib.py` — confirmed directly in
`test_release_lib.py`'s own `BreakingHeadlineTest` docstring ("No production compose
function exists in this lane: grouping and title selection are agent-executed SKILL.md
steps"), and independently confirmed here: this module's own pre-existing lane-driver
transcriptions of the Phase 1 rolling rule (`_classify_bump`/`_roll_changelog`, used by
`ConsumerEndToEndTest` and now `ComposedFixLaneJourneyTest`) implement only the
Added/Fixed/Performance groups — no `### Breaking` group exists in that test-authored
transcription either, because there is no CLI to extract it from.

Given that, this task adds real-history proof of the CODE half only — the classification
and real-order headline-selection `classify_window` performs — through a throwaway repo
with three real commits (an ordinary `fix:`, a `feat(api)!:` bang-breaking commit, and a
`refactor:` commit carrying a bare `BREAKING CHANGE:` footer with no type group of its
own), their history extracted via the real `git log --pretty=format:%H%n%s%n%b%n----`
pretty-format this module's own lane driver uses (`_parse_window_log`) — never hand-typed
commit dicts:

- the ordinary `fix:` commit is never mislabeled breaking (the AC-12 negative control,
  run against real history rather than a synthetic fixture);
- both the `!` bang form and the bare footer form classify breaking;
- headline selection picks the first breaking entry **in real `git log`'s own
  newest-first order** (the footer commit, which is chronologically later and therefore
  listed first) — not the chronologically-earlier bang commit — matching
  `test_release_lib.py`'s own documented "first means first as the window lists it, never
  re-sorted" rule, now demonstrated against genuine log output instead of a hand-ordered
  list.

The PROSE half (the `### Breaking` heading itself, the major-branch `<summary>` title
rule) is proven structurally by `test_release_lib.py`'s `BreakingHeadlineTest` against the
installed SKILL.md text — **cited, not re-derived, here.**

---

## 3. #623's behavior-preserving reorg — cited, not re-run

**This task cites T-17/T-18's own mutation-proof work rather than re-running it.**
`test_release_lib.py`'s `Phase2StructureTest` (T-18, AC-13/AC-14) already carries:

- a positive check that all twelve named substeps are present in fixed order
  (`test_all_twelve_substeps_present_in_fixed_order`);
- a genuine deletion-mutant proof, run against a **scratch copy**, never `SKILL.md`
  itself, confirming the same predicate the class trusts actually detects a missing
  substep (`test_a_mutated_copy_missing_one_substep_is_detected`);
- a genuine reordering-mutant proof, swapping two substeps and confirming the predicate
  detects the inversion, not only outright deletion
  (`test_a_mutated_copy_with_swapped_substep_order_is_detected`);
- an explicit "no competing executable correction paragraph exists afterward" proof
  (`test_split_replaces_rather_than_duplicates_the_old_monolithic_item`), including a line-
  length ceiling that would catch a future re-collapse into one giant paragraph.

`.codearbiter/reports/release-closure-invariant-map.md` (T-16) additionally maps every
retained normative obligation to its new instruction location and proving test, ahead of
the split. Re-deriving any of this in T-20 would be redundant, not additive — this is
exactly the kind of citable prior proof the task description anticipates.

**What this task adds instead, specific to the journey view:** `ComposedFixLaneJourneyTest`
Stage 7 (§2b above) proves the split Phase 2 still *drives the same executable lane* the
#570 fixes run through — not a second prose-structure check. It extracts and runs the
`tag_message_composition` anchored invocation (Phase 2's own tag-creation step) from the
current, already-restructured `core/surface/skills/release/SKILL.md`, and that invocation
succeeds in creating a real annotated tag at the tail of a journey that also exercised
three #570 fixes ahead of it. This is evidence the restructure did not silently break
extraction or execution for a real downstream consumer of Phase 2's prose — a claim
`Phase2StructureTest`'s own structural/mutation proof does not itself make, since it never
executes the file it structurally validates.

---

## 4. Gaps found while composing the fixes

**No regression was found in any #570 or #623 production behavior.** Every fix, run in
composition, behaves exactly as its own isolated proof (T-10 through T-19) already
established.

One latent gap was found and fixed, entirely inside test-only infrastructure, not
production code:

**`_execute_lane_sequence` (T-74/T-75, predates this sprint's plan entirely — part of the
older #563 campaign) had never been exercised against the CANONICAL `core/surface/...`
prose before this task.** Every existing caller (`ConsumerEndToEndTest`,
`NumericSequenceConsumerEndToEndTest`, `NeverTaggedManifestFloorTest`) passes it the
`_FIXTURE.plugin_root`-materialized copy, which is an ALREADY-RENDERED, `git archive
HEAD`-snapshotted "claude"-host payload — necessarily pre-sprint bytes (T-10 through T-15's
diff is staged, not committed). Two consequences, both discovered only because
`ComposedFixLaneJourneyTest` Stage 7 is the first caller to reuse this shared driver
against the CURRENT (post-sprint) SKILL.md text:

1. The post-R-02 `window_last_tag` bullet pins tag selection with
   `git -C "$PROJECT_ROOT" tag -l` (`AncestryRepoRootBindingTest`'s own fix); the driver's
   `_run_command_substitution` call never substituted a `$PROJECT_ROOT` mapping entry, so
   the literal token reached `git -C` unresolved and the call failed. **Fixed** by adding
   `"$PROJECT_ROOT": consumer_root` to that one call's mapping — additive and
   backward-compatible: the archived pre-R-02 text this driver was originally written
   against never contains the `$PROJECT_ROOT` token at all, so the new mapping entry is a
   no-op for every existing caller (confirmed: the full 103-test run below includes all
   three pre-existing callers, unchanged, still green).
2. The canonical `core/surface/...` text spells its plugin-root placeholder
   `{{PLUGIN_ROOT}}` (the un-rendered template token); the driver's own `root_mapping` is
   hardcoded to the already-rendered `claude`-host spelling `${CLAUDE_PLUGIN_ROOT}`. This
   is not a driver defect — the driver was correctly written for its actual callers, all of
   which pass already-rendered text. `ComposedFixLaneJourneyTest` instead performs the
   exact single substring substitution the real `claude`-host generator performs
   (`{{PLUGIN_ROOT}}` → `${CLAUDE_PLUGIN_ROOT}`) on its own local copy of the skill text
   before calling the shared driver, rather than changing the driver's contract for its
   other callers.

This is judged in-scope for direct correction (not a `[NEEDS-TRIAGE]` item requiring a
separate remediation task) because it is test-only scaffolding predating this sprint's plan
by an unrelated older campaign, touches no file this sprint's T-01–T-19/R-01–R-04 already
landed a fix in beyond `test_consumer_smoke.py` itself (one of T-20's own three declared
paths), and the fix is purely additive with the full existing suite re-verified green
afterward. Recorded here in full rather than silently folded into the diff, per this task's
own honesty requirement.

---

## 5. Verification

Both full suites, bare, no `-k` filter, this Windows host, this task's own run:

```
python .github/scripts/test_release_lib.py
  Ran 657 tests in 25.816s
  OK

python .github/scripts/test_consumer_smoke.py
  Ran 103 tests in 16.166s
  OK (skipped=1)
    -> 102 passed, 1 skipped (test_plugin_root_preserves_executable_bits,
       ConsumerFixtureTest, "no POSIX executable bit on win32" — expected
       on this Windows host, pre-existing, unrelated to this task)
```

Zero failures, zero errors, zero unexplained skips. No live GitHub/npm mutation anywhere
in this task's new tests: every network-shaped action is a local `git` operation against a
scratch repository under a `tempfile.mkdtemp` root, cleaned up in `tearDownClass`/
`addCleanup`. This is proof against an open, staged-but-uncommitted candidate on one local
host — not a hosted-CI or cross-platform claim, and not a claim that anything here has
shipped.

**Scope discipline.** No prior task's already-landed fix (`core/pysrc/_releaselib.py`,
`core/surface/skills/release/SKILL.md`, `.github/scripts/_releaselib.py`,
`.github/scripts/payload_version_gate.py`, `releasehash.py`, or any of their vendored
copies) was modified by this task. The only production-adjacent file touched is
`.github/scripts/test_consumer_smoke.py` itself (this task's own declared path), and the
one non-additive-looking change inside it (§4 above) is confined to test-only shared
infrastructure predating this sprint's plan.

---

## 6. T-22 — version/changelog metadata reconciliation (AC-15, AC-16, AC-17)

**Mechanism used, not a hand-picked number.** `.github/scripts/payload_version_gate.py`
(gating `ca` and `ca-codex` at `pull_request`/`merge_group`, `.github/workflows/ci.yml`
lines 2373/2443) and `tools/build-host-packages.py --release-guard-base`
(`pi_release_guard`, gating `ca-pi`) both enforce the same rule: once a manifest version is
on the default branch with shipped payload attached, that string is SPENT — tag or no tag —
and the next shipped-payload change must strictly advance it (`_releaselib.semver_greater`).
This is a `pull_request`/`merge_group`-time gate, not a tag-time one, so the advance belongs
in this PR, not deferred to an eventual `/ca:release` run — confirmed against this repo's
own convention: every prior merged PR that touched a plugin payload carries its version
bump and dated CHANGELOG heading in the same PR (e.g. `9482b2c2`/`67d4edb1`
"fix(release): advance canary payload versions", and `57617269` "chore(release): advance
ca/ca-codex/ca-pi past main's merged baseline"), and every plugin's `CHANGELOG.md` keeps
`## [Unreleased]` permanently empty while dated headings land at PR time.

**Which targets actually changed.** This worktree started at `HEAD == origin/main ==
5c876dd8`, where `ca` read `2.21.7`, `ca-codex` read `0.13.7`, and `ca-pi` read `0.14.7` —
none tagged, but all three already merged (spent, per the rule above). Measured with the
same pathspec `payload_scope.py`/`pi_release_guard` use (the plugin directory minus its
`tools/` build directory), via `git diff --cached --quiet -- <plugin>
":(exclude)<plugin>/tools"` against this task's own staged tree (a like-for-like proxy for
`base...HEAD` since HEAD had not yet moved):

| target | payload changed? | evidence |
|---|---|---|
| `plugins/ca` | yes | staged `plugins/ca/hooks/_releaselib.py`, `plugins/ca/hooks/releasehash.py`, `plugins/ca/skills/release/SKILL.md` (T-19's regeneration) |
| `plugins/ca-codex` | yes | staged `plugins/ca-codex/hooks/_releaselib.py`, `plugins/ca-codex/hooks/releasehash.py`, `plugins/ca-codex/routines/release/SKILL.md` |
| `plugins/ca-pi` | yes | staged `plugins/ca-pi/hooks/_releaselib.py`, `plugins/ca-pi/hooks/releasehash.py`, `plugins/ca-pi/routines/release/SKILL.md` (none under the excluded `plugins/ca-pi/tools/`) |
| `plugins/ca-sandbox` | **no** | `git diff --cached --quiet -- plugins/ca-sandbox` returns 0 (empty) — zero files under `plugins/ca-sandbox/` are touched anywhere in this sprint's diff |

`ca-sandbox`'s version, manifest, and `CHANGELOG.md` were left untouched — exactly AC-17's
own named example ("never bumping a target (e.g. `ca-sandbox`) whose payload didn't
change").

**Bump size, derived not chosen.** `core/pysrc/_releaselib.py`'s `classify_window`
(reused by AC-12) ranks a commit window's bump by Conventional-Commit type and a `!`/
`BREAKING CHANGE:` marker. Every change this sprint makes is a defect correction (a bounded
timeout, a disambiguated exit code, a documentation correction, a collision/declaration
rejection, an ancestry refusal, a prerequisite check, a back-fill ordering fix, a breaking-
change *visibility* fix reusing an already-computed field, a behavior-preserving readability
split) — `fix`-class throughout: no new capability (`feat`), no `!` subject, no
`BREAKING CHANGE:` footer anywhere in this sprint's own scope. `classify_window` on that
shape yields `patch`. Hence `2.21.7 -> 2.21.8`, `0.13.7 -> 0.13.8`, `0.14.7 -> 0.14.8` — the
established "next patch, Fixed-only" pattern every recent entry in all three CHANGELOGs
already follows (`2.21.4` through `2.21.7`, `0.13.4` through `0.13.7`, `0.14.4` through
`0.14.7`, all "### Fixed" only, all sequential patch bumps).

**Files changed by this task.**
- `plugins/ca/.claude-plugin/plugin.json` — `2.21.7` -> `2.21.8`.
- `plugins/ca-codex/.codex-plugin/plugin.json` — `0.13.7` -> `0.13.8`.
- `plugins/ca-pi/package.json` — `0.14.7` -> `0.14.8`.
- `package.json` (repo root) — regenerated via `python tools/build-host-packages.py`
  (never hand-edited; `--check` confirms it matches `plugins/ca-pi/package.json` and the Pi
  descriptor).
- `CHANGELOG.md`, `plugins/ca-codex/CHANGELOG.md`, `plugins/ca-pi/CHANGELOG.md` — one new
  dated heading each (`## [2.21.8] - 2026-09-22`, `## [0.13.8] - 2026-09-22`,
  `## [0.14.8] - 2026-09-22`), inserted directly below the pre-existing, still-empty
  `## [Unreleased]` heading, above the prior version's heading. No existing heading, dated
  entry, or `[Unreleased]` placeholder was reordered, edited, or removed in any of the three
  files.
- `README.md` — the version badge (`check_badge_consistency.py`'s own gate) read `2.21.7`
  and drifted the moment `plugins/ca/.claude-plugin/plugin.json` advanced; updated to
  `2.21.8` and reverified.

**Verification run.**
- `python tools/build-host-packages.py` (regenerate) then `--check`:
  `package.json matches plugins/ca-pi/package.json and the Pi descriptor`.
- `python .github/scripts/check_badge_consistency.py`:
  `badge/core-lane/catalog consistent with the repo` (failed once, pre-fix, naming the
  exact stale badge string, then passed after the README edit above).
- `python .github/scripts/check_command_catalog.py` (declared `ca` pre-tag command):
  `command catalog consistent with the repo` — unaffected by a version-only change.
- Manual advance check (the gate itself cannot be run meaningfully here: `git diff
  base...HEAD` reads committed history, and this task's changes are staged, not committed,
  so a live `payload_version_gate.py --base origin/main` run would report "no shipped
  payload change" — a measurement of nothing, not evidence of correctness): `2.21.8 >
  2.21.7`, `0.13.8 > 0.13.7`, `0.14.8 > 0.14.7` all hold under `_releaselib.semver_greater`;
  none of `v2.21.8`, `ca-codex-v0.13.8`, `ca-pi-v0.14.8` exists in this repo's tag list
  (confirmed against the full local tag set, which does carry `v2.21.4`, `v2.21.6`,
  `ca-codex-v0.13.6`, `ca-pi-v0.14.6` — consistent with #530's "spent means merged, not
  tagged" rule: `2.21.7`/`0.13.7`/`0.14.7` are already spent despite carrying no tag either).

**Known transient state this task's bump produces (not a regression, mirrors the plan's
own documented T-05→T-19 pattern) — left for T-23, not fixed here:**
- `python .github/scripts/test_public_codex_docs.py --require-current-candidate` (the
  declared `ca-codex` pre-tag check) now fails: `docs/codex-parity-testing.md`'s
  `CODEX-LIVE-BASELINE-META` marker records `"adapter_version":"0.13.7"` — an exact,
  hash-bound live-proof receipt from PR #829, genuinely matching the version this task just
  advanced past. It passed at `0.13.7` and cannot pass at `0.13.8` without a new live
  Codex-host exercise producing a new marker; that is AC-18/T-23's job (`check_skill_proof_
  fresh.py`'s Claude-side equivalent), not something this task can fabricate without
  exactly the "silently against stale HEAD" failure AC-16/AC-18 forbid.
- `python .github/scripts/check_skill_proof_fresh.py` (the declared `ca` pre-tag check)
  already failed **before** this task's version bump — it is stale against T-19's
  regenerated `plugins/ca/skills/release/SKILL.md` bytes (`sha256` mismatch reported
  directly), unrelated to the version number. Also explicitly T-23's job.
- Neither check is part of this task's own declared verification
  (`python tools/build-host-packages.py --check`), and neither is silently claimed passing
  above — both are recorded here so T-23 starts from an accurate, undropped picture rather
  than discovering the staleness itself.

**Not touched, and why.** `plugins/ca-sandbox/.claude-plugin/plugin.json` and
`plugins/ca-sandbox/CHANGELOG.md` — zero payload change (table above). No release, tag, or
publish action was taken or simulated; `release-build` for `ca`/`ca-codex`/`ca-pi` remains
the existing `raise SystemExit(...)` refusal declared in `.codearbiter/release-targets.md`,
unmodified.

**Additional real version surfaces found and reconciled, beyond the manifest/CHANGELOG/
badge set above.** An unrestricted grep for `2.21.7`/`0.13.7`/`0.14.7` across the whole
repository (not just Markdown) surfaced two more genuinely pinned, tested surfaces this
task's initial pass missed:

1. **The update-notifier `adapter_version` constant** (`core/pysrc/hostapi.py`'s base
   `Host.adapter_version`, vendored byte-identically into `plugins/ca/hooks/hostapi.py`,
   `plugins/ca-codex/hooks/hostapi.py`, `plugins/ca-pi/hooks/hostapi.py` via
   `tools/sync-core.py`; and each plugin's own `hooks/_host.py` override —
   `ClaudeHost.adapter_version`, `CodexHost.adapter_version`, `PiHost.adapter_version`).
   `resolve_plugin_root()` hard-asserts `adapter_version == <manifest version>` at runtime
   and fails closed (`PluginRootError`) on any mismatch; `plugins/ca/hooks/tests/
   test_plugin_root_resolution.py::test_shipped_adapter_version_constants_match_manifests`
   pins exactly this for all three hosts. Fixed at the canonical source
   (`core/pysrc/hostapi.py`: `2.21.7` -> `2.21.8`), regenerated via `python
   tools/sync-core.py` (per AC-15 — canonical-owner-then-mechanical-regeneration, the same
   discipline T-04/T-19 already used), then the three per-plugin `_host.py` overrides
   hand-edited (`2.21.7` -> `2.21.8` for `ca`, `0.13.7` -> `0.13.8` for `ca-codex`,
   `0.14.7` -> `0.14.8` for `ca-pi`, since `_host.py` is deliberately NOT part of the shared
   core — each plugin ships its own, per its own file-header comment). Verified:
   `python tools/sync-core.py --check` and `python tools/build-surface.py --check` both
   OK; `test_plugin_root_resolution.py`'s full suite (17 tests) and specifically the
   pinning test pass.
2. **`.codearbiter/.provenance/code-map.json`'s installable-manifest claims and Git-blob
   hashes** for all three manifests. `.github/scripts/test_provenance_wiring.py::
   test_code_map_installable_manifest_claims_are_current` pins both the claim text's
   embedded version string and `git hash-object`'s exact blob hash for each of
   `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`,
   `plugins/ca-pi/package.json` — this test failed with all six expected values named
   directly in its own diagnostic before the fix. Updated all three claim strings
   (`v2.21.7`->`v2.21.8`, `v0.13.7`->`v0.13.8`, `v0.14.7`->`v0.14.8`) and their three
   `hash` fields to the exact `git hash-object` values the test itself reported
   (`a52c7b4b1807da65c4419db5b16405b1ae0370e8`,
   `cc1bef23e20026dc7074171708aae8b93d15d640`,
   `0e3cd911278692d26adac25e9dca3164e506612d`). Verified: full
   `test_provenance_wiring.py` — 8/8 checks green.

**A staging-order artifact this task hit and resolved, recorded for transparency.**
Immediately after the `hostapi.py`/`_host.py` edits above (before staging them),
`.github/scripts/test_pi_package.py`'s
`test_real_rpc_enabled_start_never_executes_project_git_and_installs_absolute_hook_
identities` failed with `PI bridge error (PluginRootError)`. Cause: that test's
`durable_pi_package_copy()` helper builds its throwaway package from `git ls-files
--stage` (the Git INDEX), not the working tree — so it packaged the just-bumped
`plugins/ca-pi/package.json` (`0.14.8`, already staged) against the not-yet-staged
`plugins/ca-pi/hooks/_host.py` (still `0.14.7` in the index), producing a genuine
version-mismatch `PluginRootError` — the exact fail-closed behavior `resolve_plugin_root`
is supposed to produce on a real drift, correctly triggered here by an incomplete `git add`
rather than a code defect. Resolved by staging the `hostapi.py`/`_host.py` edits (`git add
core/pysrc/hostapi.py plugins/ca/hooks/hostapi.py plugins/ca/hooks/_host.py
plugins/ca-codex/hooks/hostapi.py plugins/ca-codex/hooks/_host.py
plugins/ca-pi/hooks/hostapi.py plugins/ca-pi/hooks/_host.py`); the full
`test_pi_package.py` suite (61 tests) and both full suites (`test_release_lib.py` 657
tests, `test_consumer_smoke.py` 103 tests/1 pre-existing Windows skip) all re-verified
green afterward with no other regression.

**Files touched by this addendum, on top of §6's original list:** `core/pysrc/hostapi.py`,
`plugins/ca/hooks/hostapi.py`, `plugins/ca-codex/hooks/hostapi.py`,
`plugins/ca-pi/hooks/hostapi.py` (all four mechanically identical, sync-core-verified),
`plugins/ca/hooks/_host.py`, `plugins/ca-codex/hooks/_host.py`, `plugins/ca-pi/hooks/
_host.py`, `.codearbiter/.provenance/code-map.json`.

---

## T-23 — final blind exercise, round 1

**Role.** Independent blind exercise per AC-18/P8, dispatched with no visibility into T-01
through T-22's implementation reports or the triage report's per-issue dispositions; read
only `core/surface/skills/release/SKILL.md` (the source template) and the spec's acceptance
criteria before starting, and the triage report's `#570` section only after forming an
independent view, per the dispatch's own instruction.

**Candidate exercised.** `core/surface/skills/release/SKILL.md`, confirmed byte-identical to
the shipped `plugins/ca/skills/release/SKILL.md` (sha256
`da791d806da41a589902561cfe3f291d777cc43e2c1e38d65edbe499e2f1c04e`, 123,993 bytes) via
`python tools/build-surface.py --check` (OK, claude/codex/pi in sync) and every
`core/pysrc/_releaselib.py`/`releasehash.py` invocation below via `python tools/sync-core.py
--check` (OK, 71 core files x 3 plugins, byte-identical) — the commands documented as
`{{PLUGIN_ROOT}}/hooks/_releaselib.py` and the ones actually run from `core/pysrc/` in this
exercise are the same bytes.

**Method.** Built three disposable git repositories under the system temp directory
(`%TEMP%\ca-t23-fixture1`, `...-fixture2`; a third scratch state was folded into fixture2
rather than a separate directory once its purpose was covered) via real `git init` /
`commit` / `tag` / `branch` / `merge` — never inside this repo's own worktree, confirmed by
`git status` in this worktree showing no new untracked paths from the fixture work. Ran the
documented helper commands from `core/pysrc/_releaselib.py` and `core/pysrc/releasehash.py`
verbatim, pointed at each fixture via `CLAUDE_PROJECT_DIR` (the same env-first-else-cwd
precedence the skill itself documents) rather than shortcuts. No tracked file in this repo
was changed by the exercise itself except this report and
`.codearbiter/reports/agent-lane-proof.json`.

### Fixture scenarios

1. **Fixture 1 — Back-fill lane, genuine first release, single target.** Fresh repo on
   branch `trunk`, one `chore` commit, then a `feat: add index` commit (with a `CHANGELOG:`
   footer) on branch `feature/first`. No `.codearbiter/` state at all. Walked `backfill-
   detect` → Present (block matches the documented shape exactly: `payload: .`,
   `payload-exclude: .codearbiter/`, `latest-eligible: true`) → the two Persist
   prerequisite gates (tech-stack.md existence, branch-not-default) → marker mint/write/
   remove → `chore: declare release targets` commit → re-entry into Pre-flight
   (`list-targets`, `show-row`, `clean-tree-status`, `LAST_TAG` resolution via
   `last-tag-for-policy`/`verify-tag-ancestor`, `adoption-commit`, `classify-window`).
2. **Fixture 2 — established single target, ancestry refusal, Phase 2 substeps, breaking
   changes.** Repo with a stray branch tagging `v9.0.0` on history unreachable from `trunk`;
   a real merge commit binding for 2.0's `--first-parent` claim; a real annotated tag
   created with `--cleanup=verbatim` and round-tripped; `run-pre-tag` exercised against both
   a no-op and a real tree-mutating declared command; `classify-window` exercised against
   `feat!:`, `feat(api)!:`, and an unfootered `chore!:` commit in the same window.
3. **Zero-tag Phase 2 substep 2.2** was exercised directly against fixture 1 (still
   tagless): the guarded `show-ref --tags -d` / `peel-tag` sequence, and `classify`'s three
   argument shapes (`publish_fresh`, `resume_publish`, `abort_mismatch`) were run as
   standalone CLI invocations per the module docstring's own worked example, not tied to
   either fixture's git state.

### Exact commands run (representative; full list is longer)

```
git init -q -b trunk <fixture>
git -C <fixture> config user.email/user.name/core.autocrlf
python core/pysrc/_releaselib.py backfill-detect <fixture>
CLAUDE_PROJECT_DIR=<fixture> python core/pysrc/_releaselib.py show-row app
CLAUDE_PROJECT_DIR=<fixture> python core/pysrc/_releaselib.py clean-tree-status app
git -C <fixture> tag -l | python core/pysrc/_releaselib.py last-tag-for-policy v semver ""
python core/pysrc/_releaselib.py verify-tag-ancestor <tag|"<none>"> <fixture>
python core/pysrc/_releaselib.py adoption-commit < <adds-file>
CLAUDE_PROJECT_DIR=<fixture> python core/pysrc/_releaselib.py classify-window app trunk < <window-file>
python core/pysrc/_releaselib.py changelog-section <fixture> <hosted_head> CHANGELOG.md <version>
python core/pysrc/_releaselib.py notes-match v<version> <file>
python core/pysrc/_releaselib.py dates-match <section-file> <message-file>
git tag -a v0.2.0 -F <message-file> --cleanup=verbatim
git cat-file tag v0.2.0 > <stored-file>
CLAUDE_PROJECT_DIR=<fixture> python core/pysrc/releasehash.py check|record app
CLAUDE_PROJECT_DIR=<fixture> python core/pysrc/_releaselib.py run-pre-tag app
python core/pysrc/_releaselib.py classify <tag_exists> <tag_sha> <head_sha> <tag_version> <manifest_version> <release_nondraft>
python .github/scripts/check_skill_proof_fresh.py
python .github/scripts/test_public_codex_docs.py --require-current-candidate
```

### Findings

**HIGH-T23-1 — Back-fill's own canonical first release silently dead-ends via the
adoption-boundary default (reproduced; NO-BLOCKER under P8's strict bar, but a real,
ordinary-path defect).**

Phase 1 step 0 resolves the adoption floor via `adoption-commit`, now scanning **both**
`.codearbiter/CONTEXT.md` and `.codearbiter/release-targets.md` — this sprint's own stated
fix for the campaign's previously-recorded, not-yet-remediated `run_18_HIGH_1` (see
`agent-lane-proof.json`'s `not_remediated_here`), which described an *unbounded* floor when
`CONTEXT.md` is absent. Reproduced against fixture 1's ordinary path: after Back-fill's
Persist step commits `chore: declare release targets`, that commit is (a) the only match
`adoption-commit`'s scan finds (no `CONTEXT.md` exists — the documented common case for this
lane's own target audience) and (b) by construction the newest commit in the repository the
moment Pre-flight is re-entered, so `$ADOPTED` resolves to it. Since the canonical Back-fill
row declares `payload-exclude: .codearbiter/` and that chore commit touches nothing else,
`EFFECTIVE_WINDOW="${ADOPTED}^..HEAD"` is payload-scoped-empty:

```
git -C <fixture1> log "<chore-sha>^..<chore-sha>" --format=%H -- . ":(exclude).codearbiter/"
# (no output)
```

Phase 1 step 1's mandatory non-empty check ("empty output STOPs as nothing to release")
therefore fires on the project's genuine first release — discarding its entire pre-existing,
already-shipping feature history (`feat: add index`, footer-complete, sitting one commit
before the boundary) by default. This is not a corner case: since Back-fill triggers only
when `.codearbiter/release-targets.md` is genuinely absent and its own step 3 always ends by
committing that file immediately before re-entering Pre-flight, this is the *ordinary*
sequence for every project's first release through that lane, not an edge case.

Step 0's own escape hatch does mechanically work, composed from two separately-verified
facts rather than run as one end-to-end command: (1) the fixture's root commit genuinely has
no parent (`git rev-parse --verify <root>^` exits 128, "Needed a single revision"), which is
exactly the input step 0's own stated rule keys on — "when `$ADOPTED` is the root commit and
has no parent, use `EFFECTIVE_WINDOW=HEAD`"; and (2) that full-`HEAD` window (independently
run as `classify-window app trunk` against the real 2-commit history) classifies cleanly —
`minor`, zero `NEEDS-TRIAGE` lines. Composing (1) and (2) per step 0's own stated rule shows
the replacement path is sound; this exercise did not additionally re-run the adoption-
commit/step-0 machinery itself with `$ADOPTED` set to the root SHA as a single command. So
this is not a dead end in the strict sense; a sufficiently alert operator who both (a)
notices the proposed `$ADOPTED` is suspicious and (b) knows to replace it with something
earlier can recover. But nothing in the prose:

- warns that `$ADOPTED` will systematically equal the just-authored declaration commit on
  this lane's own canonical path,
- connects the resulting generic "nothing to release" STOP back to the adoption-boundary
  choice as its cause, or
- states what a working replacement value looks like.

**Severity call.** Not a data-loss/version-corruption/silent-wrong-action BLOCKER under
P8's strict bar — the failure is a loud, recoverable STOP with a mechanically working manual
override, not silent corruption. Recorded as **HIGH**, this round's verdict is **NO-BLOCKER**
on it alone; it is exactly the kind of "self-inflicted" seam
`agent-lane-proof.json`'s own `self_inflicted_pattern` field already names as this
campaign's most common category (a fix for one HIGH opening a new one), and belongs to
whichever task owns Phase 1 step 0's adoption-boundary text for remediation.

**Everything else exercised — verified working, no other finding at HIGH or above:**

- `verify-tag-ancestor` correctly refuses (exit 1, documented diagnostic) a tag reachable
  only from an abandoned sibling branch (fixture 2's `stray`/`v9.0.0` vs. `feature/real`).
- The zero-tag Phase 2 guarded ref-snapshot sequence (2.2) behaves exactly as documented:
  `git show-ref --tags -d` exits 1 with no tags, and `peel-tag` correctly returns empty
  (`<tag_exists>=false`) rather than raising, under the `set -euo pipefail`-safe spelling.
- `classify`'s four outcomes reproduce exactly, including the module docstring's own worked
  example (`classify false "" <head> 1.4.3 1.1.0 false` → `publish_fresh`).
- 2.0's `--first-parent` requirement is genuinely load-bearing: against a real no-fast-
  forward merge, the plain (non-`--first-parent`) form returns the side-branch's last-
  touching commit, not `HOSTED_HEAD`; `--first-parent` returns the merge commit correctly.
- `changelog-section` → `notes-match` → `dates-match` chain correctly against a real
  committed changelog section; `git tag -a --cleanup=verbatim` preserves every `#`-prefixed
  heading (verified via `git cat-file tag` byte inspection), and `notes-match` against the
  round-tripped stored tag object passes.
- `run-pre-tag` exit-6 mutation detection fires correctly, names the mutated path, and
  reports the documented discard-and-restart remedy, against a real tree-mutating declared
  `pre-tag` command.
- `classify-window` correctly derives `major` and flags an unfootered breaking `chore!:` as
  its own `[NEEDS-TRIAGE]` line (exit 1) while leaving a footered `feat!:` unflagged in the
  same window; a scoped `feat(api)!:` also classifies `major` — the historically-named
  bang-stripped-before-scope-detection bug does not reproduce.
- The prerequisite gates (`tech-stack.md` existence, branch-not-default) evaluate correctly
  as literal shell conditions in both directions (present/non-default → proceed;
  absent → STOP-condition holds), confirmed against both fixtures.

### The two declared pre-tag checks T-22 left red

**`check_skill_proof_fresh.py`.** Read in full: it is a legitimate, mechanical "regenerate
the recorded proof for the new bytes" check *only when the fresh exercise is clean*. Because
this round's exercise found a live HIGH against the exact current bytes, setting
`proof_current: true` would contradict the artifact's own established convention (a run with
a live HIGH is recorded with `disposition: "Blocked proof."`, not promoted to the active
`exercise` object — see `historical_exercise_30`'s precedent) and would be exactly the
"hand-edit `proof_current` back to true without re-running the exercise" move the script's
own docstring names as defeating the only check in this repo that covers whether an agent
can actually follow the release prose. **Action taken:** recorded this round's real exercise
in `.codearbiter/reports/agent-lane-proof.json` as the new `exercise` object (run 34, HIGH
finding included, `proof_current: false`), preserved the superseded run 33 verbatim as
`historical_exercise_33`, and left `proof_current` false. `python
.github/scripts/check_skill_proof_fresh.py` **still fails**, honestly — the artifact's own
`proof_current` flag, not a hash mismatch, is now the stated reason. `python
.github/scripts/test_check_skill_proof_fresh.py` (28 tests) passes against the edited
artifact. This check cannot honestly be made to pass this round without either fixing
HIGH-T23-1 or an orchestrator ruling to accept it, per P8.

**`test_public_codex_docs.py --require-current-candidate`.** Read `live_baseline_marker`,
`validate_live_candidate_run`, and `_assert_live_baseline_marker` in full, and the live
marker in `docs/codex-parity-testing.md`. This is **not** a mechanical refresh. The marker
is schema_version 3 and binds real, externally-verified evidence to an exact commit: a real
GitHub Actions `candidate_ci_run_id`/`candidate_artifact_id`, a real 64-hex
`candidate_artifact_sha256`/`candidate_archive_sha256`, real 40-hex commit/tree/PR-head/PR-
base SHAs, and a real PR number/head-ref bound by `validate_live_candidate_run` to an actual
completed, green, `pull_request`-event CI run. The currently recorded marker
(`adapter_version: "0.13.7"`, PR #829, run `35525299189`) is genuine historical evidence for
a prior candidate; the manifest now reads `0.13.8` (this sprint's own version bump), and
`test_codex_live_baseline_may_lag_the_development_candidate` exists specifically to bless
this lag during ordinary development — the check is *supposed* to stay red until a real live
Codex CLI install/verification cohort runs against the `0.13.8` candidate and records its
genuine CI run ID, artifact ID, and digests. **This cannot be produced from this session**:
it requires dispatching and observing a real hosted CI run, downloading a real artifact, and
recording its real provenance — outside what a blind-exercise agent is authorized or able to
fabricate. **Action taken: none.** `docs/codex-parity-testing.md` was left untouched. This is
a genuine release-time prerequisite for shipping `ca-codex` `0.13.8` (the `ca-codex` row's
declared `pre-tag` command, gating that target's own `/release ca-codex`), not a T-23
artifact-refresh gap — flagged here for the orchestrator/closing task (T-24) to record as an
open, correctly-red prerequisite rather than a defect in this sprint's work.

### Limitations — stated plainly, not silently absorbed

- No live GitHub API, hosted workflow dispatch, tag push, Release creation, asset read-back,
  or `--latest` behavior was exercised.
- Not exercised this round: `run-pre-tag` exit codes 5, 7, 8, 9 (only 0 and 6 were fired);
  `backfill-detect`'s zero/multiple-candidate ambiguity exits; the reconciliation-ledger path
  (`$CHANGELOG_RECONCILIATIONS`); `numeric-sequence` version policy; `render-release-assets`/
  `verify-release-assets`; the full `--dry-run` flow end-to-end; Back-fill step 3's belt-and-
  braces re-check-existence-before-write race (reasoned about as a literal, correctly-
  evaluating file check; not reproduced under an actual concurrent race); the `commit-gate`
  skill itself (its stated prerequisites were checked as file/branch conditions, exactly as
  Pre-flight's own prose does, not by invoking `commit-gate`).
- Windows Git Bash / interpreter-resolution paragraphs were read but not independently
  re-exercised on a second host shape this round; relied on prior rounds' verification for
  that surface, which this round's byte changes did not touch.
- All fixture work happened in disposable `%TEMP%` directories (`ca-t23-fixture1`,
  `ca-t23-fixture2`), deleted-safe and never staged into this repository; confirmed via `git
  status` in this worktree before and after.

### Verdict

**NO-BLOCKER under P8's literal bar** (data loss / version corruption / silent wrong
action) — the failure is a loud, recoverable STOP with a mechanically working manual
override, not silent corruption. **BLOCKING in practice for this task's own verification
line and for sprint close-out**, though: one genuine **HIGH** finding (HIGH-T23-1, Back-
fill's adoption-boundary default) is recorded and reproduced against the exact current
bytes, `proof_current` was correctly set to `false` rather than faked, and
`check_skill_proof_fresh.py` therefore fails and is expected to keep failing until one of
two things happens — the orchestrator must rule between them, not this task:

1. A quick, clearly-scoped prose/diagnostic fix to Phase 1 step 0's adoption-boundary text
   (narrowly within an already-landed task's own declared scope), followed by this same
   round's re-verification against the fixed bytes; or
2. A full second blind-exercise round under P8's remaining one-round budget.

The `ca-codex` live-baseline prerequisite is separately red for a correct,
unrelated reason (a real live-verification cohort genuinely has not run against `0.13.8`
yet) and is not this sprint's defect to fix.

---

## T-23 — final blind exercise, round 2 (2026-09-22)

**Role.** T-23 round 2 of at most 2 (P8/spec AC-18). Genuinely independent second exercise
against the exact current shipped `core/surface/skills/release/SKILL.md`, per this task's own
dispatch: read `SKILL.md` and `.codearbiter/specs/release-contract-closure.md` fresh, did NOT
read round 1's own "Fixture scenarios"/"Exact commands run"/"Findings" prose above before
forming an independent view (this section was written before reading them), and did not read
`release-closure-triage.md`'s per-issue disposition detail. Unavoidable prior context: this
task's own dispatch required reading `.codearbiter/plans/release-contract-closure.md`'s T-23/R-05
rows and `agent-lane-proof.json`'s existing entries before starting (the task instructions
mandate this — "read its schema and existing entries first, mirror the established
convention"), so the shape of round 1's HIGH finding and R-05's claimed remediation were known
going in. What follows is independent verification against real fixtures, not a restatement of
that prior narrative.

**Exercised candidate.** `core/surface/skills/release/SKILL.md`: 126,176 bytes,
`sha256=43e2a994b410d56d817efa3331c2eee8de5043ee426b849d439611de2d568f6c`. Rendered
`plugins/ca/skills/release/SKILL.md`: 126,437 bytes,
`sha256=5c5b95447980308133615463e1c3302d4b0e420cd84328ee9402a35d3903ece8`. Confirmed in sync via
`python tools/build-surface.py --check` → `OK (claude, codex, pi in sync)`. `core/pysrc/_releaselib.py`
and `core/pysrc/releasehash.py` exercised directly (never imported in-process, per the plan's
documented module-caching-collision trap); every command below was run as a real subprocess
against real disposable git fixtures under `%TEMP%\t23r2\` — never inside this worktree, never
staged, never touching `git status` here.

### Fixture scenarios

- **Fixture A** — a first-time Back-fill consumer with **real pre-existing feature history**
  (not an empty repo): `chore: initial scaffold` → `feat: add feature one` → `feat: add feature
  two` → `fix: correct off-by-one bug` → `chore: add tech-stack for commit-gate`, all on a
  feature branch (`feature/history`), `main` pointed at the same tip as the project's default
  branch, no `.codearbiter/CONTEXT.md` ever created. Walked Detect → Present → Persist
  (tech-stack.md prerequisite check, branch-not-default check, marker mint/write/remove, `chore:
  declare release targets` commit) verbatim, then re-entered Pre-flight/Phase 1 step 0/1 for real.
- **Fixture B** — an established consumer with an **ancestry-hazard tag**: `v1.0.0` tagged on
  `main`, then an `abandoned` sibling branch created from `main`, bumped to `1.1.0` and tagged
  `v1.1.0` there, never merged. A fresh `feature/next` branch cut from `main` (not from
  `abandoned`) carries the next real, footered `feat` commit.
- **Fixture C** — a **zero-tag Phase 2 tag-composition/classification flow through to a real
  local tag**: one committed `feat!:`-with-footer-and-`BREAKING CHANGE:` commit bumping
  `package.json` to `0.1.0` and rolling a `## [0.1.0]` changelog section (with a `### Breaking`
  group) directly, then the documented zero-tag ref-snapshot sequence (2.2), `classify` (2.8),
  `git tag -a … --cleanup=verbatim` (2.9), and the round-trip verify (2.10).
- **Fixture D** — attempted (a throwaway repo with no `tech-stack.md`, to fire AC-10's
  prerequisite STOP negatively) but **not actually exercised this round** — budget went to
  chasing Fixture A's finding to ground instead. Recorded honestly as unexercised, not implied
  coverage.

### Exact commands run (representative)

```
# Fixture A — backfill-detect, then the real Pre-flight/Phase-1 sequence
python _releaselib.py backfill-detect                              # -> exit 0, printed block
python _releaselib.py list-targets                                 # -> "app", exit 0
git tag -l | python _releaselib.py last-tag-for-policy v semver "" # -> <none>
git log --diff-filter=A --format=%H -- .codearbiter/CONTEXT.md .codearbiter/release-targets.md \
  | python _releaselib.py adoption-commit                          # -> a959ed4... (== HEAD)
git log a959ed4...^..HEAD --format=%H -- . ":(exclude).codearbiter/"   # -> EMPTY
git log HEAD --format=%H -- . ":(exclude).codearbiter/"                # -> 4 commits (real history)
python _releaselib.py classify-window app main < <HEAD-window>     # -> minor, 3x [NEEDS-TRIAGE], exit 1
python _releaselib.py classify-window app main < <narrowest-nonempty-window>  # -> still exit 1

# Fixture B — ancestry hazard
git tag -l | python _releaselib.py last-tag-for-policy v semver "" # -> v1.1.0 (the abandoned tag)
python _releaselib.py verify-tag-ancestor v1.1.0 <root>            # -> exit 1, correct diagnostic
python _releaselib.py verify-tag-ancestor v1.0.0 <root>            # -> exit 0 (genuine ancestor)
python _releaselib.py verify-tag-ancestor -- evil <root>           # -> exit 2 (argv-injection guard, R-01)

# Fixture C — zero-tag Phase 2 flow
python _releaselib.py changelog-section <root> <full-sha> CHANGELOG.md 0.1.0 semver "" # exit 0
python _releaselib.py dates-match <section-file> <message-file>    # exit 0
git show-ref --tags -d                                             # exit 1 (ordinary zero-tag state)
python _releaselib.py peel-tag v0.1.0 < <empty-show-ref-output>    # exit 0, empty TAG_SHA
python _releaselib.py classify false "" <head-sha> 0.1.0 0.1.0 false  # -> publish_fresh
git tag -a v0.1.0 -F <message-file> --cleanup=verbatim
git cat-file tag v0.1.0 > <stored-file>                            # headings preserved verbatim
python _releaselib.py notes-match v0.1.0 <stored-file>             # exit 0
python _releaselib.py classify-window < <fixture-C-window>         # -> major (feat!: correctly classified)

# releasehash.py exit-code spot check
python releasehash.py                                               # -> usage, exit 64
python releasehash.py check nonexistent-target                      # -> exit 65
python releasehash.py check app                                     # -> no-commands, exit 0

python check_skill_proof_fresh.py                                   # -> exit 1, proof_current is
                                                                      #    still false (expected,
                                                                      #    correct for this round)
```

### Findings

**HIGH-T23R2-1 — R-05's own remediation for round 1's HIGH lands the Back-fill lane back on
this campaign's own previously-recorded and never-fully-closed `run_18_HIGH_1`, for any Back-fill
consumer with real pre-adoption history (the exact population Fixture A was built to represent,
per this task's own dispatch instruction).**

Round 1 found that Back-fill's canonical first-release path resolves `$ADOPTED` to its own
just-committed `chore: declare release targets` commit (payload-excluded), collapsing
`EFFECTIVE_WINDOW` to an empty payload-scoped range and STOPping "nothing to release" on the
ordinary first Back-fill release. R-05's remediation (present in the current SKILL.md, step 0
and step 1) makes the documented default, when that exact empty-window shape is detected, to
propose widening `EFFECTIVE_WINDOW` to bare `HEAD` — the **entire** repository history, not
scoped to any adoption boundary — for the operator's confirm-or-replace.

Reproduced exactly as documented in Fixture A: `LAST_TAG=<none>`, `ADOPTED == $(git rev-parse
HEAD)` both hold; step 1's narrow-window check is empty; the documented `EFFECTIVE_WINDOW=HEAD`
default is proposed. Accepting it and running `classify-window` on that window (the real,
pre-existing `feat`/`fix` history this fixture was built with) returns **exit 1 with one
`[NEEDS-TRIAGE]` line per pre-existing bumping commit** (3 of 3, in this fixture) — because none
of that history was authored under the `CHANGELOG:` footer convention, since by construction the
convention began with the declaration commit itself.

This is not a corner case of Fixture A's specific size. It is the artifact's own previously-known,
previously-unfixed defect, restated: `.codearbiter/reports/agent-lane-proof.json`'s
`not_remediated_here.run_18_HIGH_1` already recorded, in a prior campaign round, the identical
shape — *"Back-fill's own first release cannot clear Phase 1 step 3. ... An empty floor means the
whole history is footer-checked — the exact unbounded NEEDS-TRIAGE block A-5.5 exists to prevent,
on the only path that lane serves. Reproduced in a scratch repo: 4 commits, 4 NEEDS-TRIAGE
lines."* Fixture A reproduces the same shape today (3 commits, 3 lines) through R-05's own
documented default. Widening `adoption-commit` to also scan `release-targets.md` (this sprint's
fix for round 1's finding) closed the empty-window STOP by routing the lane onto exactly the
unbounded-footer-block path `run_18_HIGH_1` already named and the module's own docstring for
`first_release_baseline` explains at length (A-5.5) — the round-trip between these two shapes is
the finding, not just the BLOCK on its own.

**Checked whether a working escape hatch exists, per the prose's own "confirm or explicit
replacement" offer, before rating severity** (advisor-directed follow-up, verified against real
fixture data, not asserted):

1. **No `EFFECTIVE_WINDOW` in Fixture A is simultaneously payload-nonempty and step-3-clean.**
   Every payload-scoped commit in this fixture's history — from the narrowest nonempty range
   (`71e0961^..HEAD`, one commit) up to the full `HEAD` window — is an unfootered `feat`/`fix`
   predating the declaration commit, so every nonempty range BLOCKs at step 3 with at least one
   `[NEEDS-TRIAGE]` line (verified: the narrowest nonempty window still returns exit 1). The
   operator's documented choice set (accept `HEAD`, or replace with an explicit earlier SHA) has
   no member that both releases something and clears step 3 cleanly.
2. **Step 3's own stated remedies do not actually route around this for a real back-filled
   project.** "Amend or rebase" is explicitly forbidden once a commit is published (the ordinary
   state for a project Back-fill exists to onboard — it is, by definition, already
   shipping). "Reclassify its type" also rewrites the commit message, i.e. the same
   amend/rebase operation under a different name — not an independent remedy. The one remaining
   stated remedy, the `$CHANGELOG_RECONCILIATIONS` ledger, is never declared by `backfill-detect`'s
   own canonical block (confirmed: the printed block in Fixture A names only
   `prefix`/`manifest`/`changelog`/`payload`/`payload-exclude`/`latest-eligible` — no
   `changelog-reconciliations` row), and nothing in the Back-fill section tells an operator they
   need to hand-author one, with a full 40-character SHA plus note/reason/authorization fields
   per pre-existing commit, before their first release can clear step 3.
3. The prose is not silent about the risk — it explicitly names "a project adopting at its 500th
   commit getting a 500-line `[NEEDS-TRIAGE]` block" as a known consequence of the `HEAD` default.
   That is an honest disclosure, not a missing warning. The gap is narrower and sharper than "no
   warning": the prose names the outcome and offers a choice, but for a Back-fill consumer with
   real pre-adoption history and no reconciliation ledger already declared, neither branch of
   that choice actually completes a release without first manually rewriting or reconciling an
   unbounded amount of pre-existing history — exactly the burden A-5.5 was written to prevent
   "on precisely the population the Back-fill lane exists to serve."

**Severity/blocker classification, per P8's stated bar.** The failure is loud and non-destructive
— `classify-window` exits 1 and STOPs at step 3, strictly before step 4 bumps any manifest or
step 5 writes any changelog section; nothing is silently dropped, corrupted, or wrongly published.
Under this artifact's own established bar (data-loss/corruption/silent-wrong-action), this is
**not a BLOCKER**. It is a genuine, reproducible **HIGH**: R-05's remediation trades round 1's
"loud STOP with a working override" for a loud STOP whose only documented override path is
non-functional for the population Back-fill exists to serve, and it reopens a defect
(`run_18_HIGH_1`) this same campaign already found, named, and left unremediated once before.

### Other findings

None at HIGH or above outside the one above. Everything else exercised held:

- Fixture B: `last-tag-for-policy` selected `v1.1.0` (the abandoned sibling's tag) purely by
  value, exactly as designed (it has no git access); `verify-tag-ancestor v1.1.0` correctly
  refused with exit 1 and the documented diagnostic naming the tag and the cause; the genuine
  ancestor `v1.0.0` passed with exit 0; a leading-dash tag name (`--evil`) was rejected cleanly
  with exit 2 rather than being misread as a git flag (R-01's argv-injection guard held).
- Fixture C: the zero-tag `show-ref`/`peel-tag` guarded sequence (2.2) behaved exactly as
  documented (`show-ref --tags -d` exit 1 on the ordinary zero-tag state, `peel-tag` on empty
  input printing nothing); `classify` returned `publish_fresh` from the six sourced arguments;
  `git tag -a … --cleanup=verbatim` preserved every `#`-prefixed heading in the stored tag object
  (`git cat-file tag` round-trip inspected directly); `notes-match` passed; `dates-match` passed;
  `classify-window`'s no-argument legacy form correctly classified a footered `feat!:` commit as
  `major` (AC-12's classification, not composition — the hand-authored `### Breaking` group in
  this fixture's changelog was not independently generated by step 5's own composition code this
  round, so AC-12's *composition* path is a limitation below, not a finding).
- `releasehash.py`: malformed usage returned 64, an unknown target returned 65, and a
  never-confirmed declared-but-empty row returned the distinct `no-commands`/exit 0 — all
  matching AC-04/AC-05 exactly.
- `check_skill_proof_fresh.py` correctly failed (exit 1) against the still-`proof_current: false`
  artifact state — the correct outcome for a non-clean round, recorded here rather than forced.

### Limitations — stated plainly

- Fixture D (AC-10's prerequisite-STOP negative case) was **not exercised** this round; budget
  went to grounding Fixture A's finding instead. Not implied as covered.
- AC-12's changelog **composition** (step 5's own `### Breaking`-group-first, harvested-footer
  logic) was not independently re-derived this round; only its `classify-window` **classification**
  input (`major` for a footered `feat!:`) was verified against a hand-composed changelog section.
- No live GitHub API, hosted workflow dispatch, tag push, Release creation, or `gh`-dependent path
  was exercised (`#570`'s two remote-dependent states remain explicit residuals, unchanged by this
  round).
- Fixture A's "already published" dimension of finding HIGH-T23R2-1's remedy-unavailability
  argument (point 2 above) was reasoned about using the documented rule, not independently
  reproduced against a real configured `origin` remote — doing so would touch the explicitly
  deferred remote-dependent states. The core finding (no `EFFECTIVE_WINDOW` choice is both
  nonempty and step-3-clean) does not depend on this and was fully reproduced.
- Did not re-exercise Windows Git-Bash/interpreter-resolution paragraphs, `run-pre-tag` beyond
  what round 1 already covered, `--dry-run`, asset rendering/verification, or provenance-manifest
  recording this round; relied on round 1's and the underlying unit/consumer-smoke suites'
  coverage there.
- `changelog-section <root> HEAD <path> <version> <policy> <initial>` (literal string `HEAD`, as
  opposed to a resolved SHA) returned exit 3 in Fixture C. This is correct-by-design per 2.1's own
  contract ("never a mutable revision expression") — the skill always passes an already-resolved
  `$HOSTED_HEAD`/`$RECOVERY_HEAD` SHA, never the literal token — noted here as a non-finding, not
  inflated into one.

### Verdict

**BLOCKER classification: NO-BLOCKER under this artifact's established data-loss/corruption/
silent-wrong-action bar** — the STOP is loud, fires before any tracked-file mutation, and nothing
is silently discarded or wrongly published. **But this round is NOT clean**: HIGH-T23R2-1 is a
real, reproduced, unremediated finding, and per this task's own instruction a round with a finding
that needs further remediation does not get `proof_current: true` regardless of BLOCKER
classification. `proof_current` stays `false`. Per P8 (at most two independent blind-exercise
rounds; a third is not permitted), this is round 2 of 2 — whether to accept HIGH-T23R2-1 as a
documented residual, route it through a new remediation task outside this sprint's T-23/R-05
pairing, or reopen the plan is the orchestrator's decision, not this exercise's. No production
file (`SKILL.md`, `_releaselib.py`, `releasehash.py`, or any test file) was modified to produce
this result.

## T-25 — User-reopened remediation verification (2026-09-22)

This is not a rewrite or third attempt at T-23's final candidate. After T-24 recorded
HIGH-T23R2-1 as unresolved, the user explicitly rejected accepting or overriding the finding and
directed the sprint to fix it and commit the corrected effort. The approved spec and plan now
record that bounded post-review amendment as AC-19/R-06/T-25. T-23 rounds 1 and 2 remain
historical failures exactly as recorded above.

### Remedy exercised

- `backfill-detect` now emits
  `changelog-reconciliations: .codearbiter/release-changelog-reconciliations.json`; the generic
  renderer still omits the key when a caller did not declare one.
- Back-fill classifies the exact fetched default-branch history before tracked writes. Every
  historical bumping commit without a footer requires an operator-authored ledger entry with
  exact `target`, full lowercase 40-character `commit_sha`, `changelog`, `reason`, and
  `authorization`; the lane explicitly forbids invented text or inferred authorization.
- `validate-reconciliations` applies the same strict ledger parser before commit and fails closed
  on a missing/non-regular/symlinked, oversized, growing, unreadable, non-UTF-8, or malformed
  draft. This is structural validation only; it never claims publication.
- The declaration and validated ledger commit together. The release lane then STOPs until that
  commit lands on and is fetched from the default branch. Only a fresh non-default release branch
  may re-enter. The existing `classify-window "$TARGET" "$DEFAULT_BRANCH"` path continues to load
  the ledger from the exact published default-branch tree and independently proves each used SHA
  is an ancestor of that published commit. Missing, incomplete, unpublished, or non-ancestor
  evidence remains a loud failure.

### Discriminating evidence

The regression was observed red before implementation: the focused Back-fill suite produced five
failures because the detected/round-tripped/CLI rows carried no reconciliation declaration and the
skill carried neither the authoring route nor the publish-before-reentry boundary. After the fix,
the focused suite passes 45 tests.

The key end-to-end test builds a real disposable Git repository with an unfootered
`feat: legacy published feature`, generates the target declaration through the actual
`detect_candidate_target` plus `format_release_targets_block` seam, authors a ledger bound to that
commit's exact SHA, commits both files, advances simulated `refs/remotes/origin/trunk` to that
declaration commit, and runs the real `classify-window app trunk` CLI over the widened payload
history. It requires exit 0, a `[RECONCILED]` row, and no `[NEEDS-TRIAGE]`. No history is amended,
rebased, replaced, or retagged.

Independent coverage audit found zero CRITICAL/HIGH findings. Its one MEDIUM noted missing direct
tests for validator file-boundary arms; follow-up tests now cover missing and directory paths,
symlink refusal, pre-read and post-read size limits, `getsize`/read `OSError`, non-UTF-8 bytes, and
malformed JSON/schema. The bounded follow-up result is recorded in the active proof artifact.

Exact exercised payloads after canonical regeneration:

- `plugins/ca/skills/release/SKILL.md`: 130310 bytes,
  SHA-256 `4eae711068e270818e5b86f00a4e5ccffb196af2d2cde52b8fe8c770647eca6e`.
- `core/pysrc/_releaselib.py` and every vendored host copy: 201167 bytes,
  SHA-256 `c3c94cdd3bc433123666a8e132b57811c1742b85330d71e9c0367adfd49eb471`.
- `sync-core.py --check`, `build-surface.py --check`, `build-host-packages.py --check`, and
  `git diff --check`: all pass.

Final named suites on the exact candidate: release helper 677/677; packaged consumer smoke
107/107 with one declared skip; release workflow 169/169; payload-version gate 34/34;
release trace 29/29 with one declared skip; CI impact 83/83; ordinary public Codex docs 18/18;
proof freshness green.

The `ca-codex` live-proof release prerequisite remains deliberately separate: ordinary
`test_public_codex_docs.py` passes 18/18 after its digest-mutation fixture was correctly bound to
the current development manifest, while `--require-current-candidate` still fails exactly one
test because the real retained live proof is for 0.13.7 and the candidate is 0.13.8. No CI run,
artifact identity, or digest was fabricated to clear that release-time gate.
