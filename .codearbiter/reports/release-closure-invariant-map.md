# Release closure — Phase 2 invariant map (T-16)

**Purpose.** AC-14 (invariant-to-evidence traceability) requires every retained normative
obligation and affected literal assertion in `core/surface/skills/release/SKILL.md` Phase 2 to
map to (a) a proposed new-instruction location for T-17's split and (b) the exact test(s) in
`.github/scripts/test_release_lib.py` that currently prove it. This report does that mapping. It
makes **no** change to `SKILL.md`, `_releaselib.py`, or any test file — T-17 (split) and T-18
consume this map; they do not inherit code edits from it.

Investigation only touched (read-only): `core/surface/skills/release/SKILL.md`,
`.github/scripts/test_release_lib.py`, `core/pysrc/_releaselib.py`.

**Citation stability note.** `.github/scripts/test_release_lib.py` line numbers cited below are
accurate as of this task's snapshot but that file is itself `M` (modified, uncommitted) in this
worktree, and T-18/T-19 will edit and regenerate around it further. Where a proving test is one of
the pinned-phrase rules in `_GOVERNANCE_RULES` (used by `GovernanceSurvivalTest`), the **durable**
identifier is the dict key quoted in the table (e.g. `"HIGH (run 4): the tag message is written
verbatim, not strip-cleaned"`), not the line number — match on the key, not the line, if this
file has moved by the time T-17 reads it.

---

## 0. Fresh marker-count reconciliation (the floor)

T-10 through R-03 landed between this plan's authoring and this task, and Phase 2 moved. The
plan's recorded line span (320–346) is stale; Phase 2's actual current span in this checkout is:

```
## Phase 1 — Version & changelog · gate: BLOCK     line 209
## Phase 2 — Tag & report · gate: BLOCK             line 330
## Phase 3 — Publish · gate: STOP                   line 356
```

So the correct current span for the plan's own command is `330,355` (the blank line before
`## Phase 3`), not `320,346`. Re-run fresh against that span:

```
$ sed -n '330,355p' core/surface/skills/release/SKILL.md | grep -c "MUST\|STOP\|BLOCK\|exit [0-9]"
9
```

**Fresh count = 9, not the plan-authoring-time 10.** Verified cause, not inferred: I compared the
committed `HEAD` copy of `SKILL.md` (`git show HEAD:core/surface/skills/release/SKILL.md`) against
this worktree's uncommitted content (`git status` shows `SKILL.md` as `M` — T-10 through R-03's
work is still an uncommitted working-tree diff here, not yet a separate commit to `git log`
against).

- At `HEAD`, `## Phase 2` is at line 320 and `## Phase 3` is at line 346 — exactly the plan's
  original span. Running the plan's literal command against `HEAD`'s content
  (`sed -n '320,346p' | grep -c ...`) returns **10**, and the 10th matching line is line 346
  itself: `## Phase 3 — Publish · gate: STOP` — the **next section's own header**, swept in only
  because the plan's inclusive upper bound (346) happened to land exactly on it at
  authoring time.
- In the current working tree, `## Phase 2` is at 330 and `## Phase 3` is at 356 (both shifted by
  the same +10 lines — content was added *before* line 320/Phase 2 begins, not inside Phase 2's
  body; none of Phase 2's own paragraphs moved relative to each other). Re-running the plan's
  command with the *same* off-by-one span shape against the current file
  (`sed -n '330,356p' | grep -c ...`) also returns **10**, and line 356 is again `## Phase 3 —
  Publish · gate: STOP`. Using the *correctly* re-located Phase 2 body span — `330,355`, stopping
  at the blank line immediately before Phase 3's header rather than including it — returns **9**.

**Conclusion: the 10→9 delta is not a lost obligation.** It is an off-by-one artifact in the
plan's own floor-check command, present since authoring: the Phase 3 section header's `STOP` in
its own gate declaration was never a Phase 2 obligation, and including it was never intentional —
the plan's command range simply ended exactly on that header line by coincidence of the line
count at authoring time. This task's fresh re-run correctly excludes it. The genuine content of
Phase 2's body — all 9 marker lines below, and every individual obligation traced in §1–§3 — is
unchanged between `HEAD` and the working tree; nothing was deleted or weakened. The floor-check
command itself carries this off-by-one forward in the plan file; see the `[NEEDS-TRIAGE]` entry in
§4, since that is a plan-file defect outside this task's edit scope (`SKILL.md`/tests only), not
an AC-14 finding against `SKILL.md`'s content.

One row per matching line, per the plan's own reconciliation instruction:

| # | SKILL.md line | Marker(s) matched | What the line is | Obligation ref (§2/§3) |
|---|---|---|---|---|
| 1 | 330 | `BLOCK` | Section header: `## Phase 2 — Tag & report · gate: BLOCK` | §1-S (section gate) |
| 2 | 336 | `STOP` | "...STOPs before tag composition..." (no hosted publisher) | §1-D |
| 3 | 338 | `MUST` | "...MUST NOT execute the tag-composition commands below locally." | §1-E |
| 4 | 342 | `STOP`(x2) | "Bind the hosted candidate..." paragraph — "...either case STOPs and restarts Phase 1." | §1-G |
| 5 | 344 | `STOP` | "Reconstruct Phase 1's section..." paragraph — "...STOP if it is empty..." | §1-H |
| 6 | 346 | `MUST` | "Zero-tag execution order:" — "...MUST NOT be executed." | §1-I / §3-A |
| 7 | 348 | `MUST`(x6+), `STOP`(x4+), `exit 0`(x2), `exit 1` | Item 1 — the 9,324-char monolithic paragraph | §2 (all rows) |
| 8 | 349 | `MUST` | "Zero-tag correction" paragraph — "...MUST NOT be executed." | §3 (all rows) |
| 9 | 352 | `MUST` | Item 3 — "MUST NOT push the tag or create the GitHub Release here." | §1-K |

Confirmed: `grep -c` on line 348 collapses roughly a dozen `MUST`/`STOP`/`exit N` occurrences into
one counted line, exactly as the test-file comment warns. That is why §2 below enumerates
**obligations**, not marker occurrences — occurrence-counting is the correct unit for T-17's split
(one row per decision point), the marker *line*-count is only the correct unit for reconciling
against the plan's floor check above.

---

## 1. Obligations in Phase 2's header/context prose (lines 330–346, 351–354)

These sit outside item 1's monolithic paragraph. They are short, already discrete, and — per
AC-14's "Historical rationale may move to a packaged reference; every decision-point guard stays
in the procedure" — most are decision-point guards that stay in Phase 2's main body regardless of
how item 1 is split. Included for completeness since AC-14 scopes to "every…obligation", not only
those inside the one long paragraph.

| ID | Obligation (paraphrase, SKILL.md line) | Proposed T-17 target | Proving test | Disposition |
|---|---|---|---|---|
| 1-S | Phase 2 header/gate: `## Phase 2 — Tag & report · gate: BLOCK` (330) | Unchanged — section header | Implicit (section boundary anchor used by every `phase2 = self.skill[self.skill.index("## Phase 2") : ...]` slice in `ReleaseSurfaceTest`) | Retained in place |
| 1-A | Phase 2 is a hosted-publisher contract, not a local fallback (332–333) | Retained — Phase 2 preamble, unaffected by item-1 split | `ReleaseSurfaceTest.test_release_publication_requires_merged_hosted_exact_head_evidence` (line 10124) | Retained in place |
| 1-B | Re-enter only after PR merge, from a clean checkout at `origin/$DEFAULT_BRANCH` (333–334) | Retained — Phase 2 preamble | `test_release_publication_requires_merged_hosted_exact_head_evidence` (asserts "The release commit must merge through a pull request before any tag is composed") | Retained in place |
| 1-C | Publication requires a hosted workflow with verified green exact-head evidence (334–335) | Retained — Phase 2 preamble | same test, asserts "Publication requires a hosted workflow that verifies green exact-head evidence" | Retained in place |
| 1-D | No qualifying hosted publisher → STOP before tag composition, add capability in a separate PR (335–337) | Retained — Phase 2 preamble | same test, asserts "A project with no qualifying hosted publisher STOPs before tag composition" and `assertNotIn` on the old local-fallback wording | Retained in place |
| 1-E | Interactive agent MUST NOT execute the tag-composition commands locally; may only authorize/dispatch/observe the publisher (337–338) | Retained — Phase 2 preamble | **none found** | **GAP** — see §4-G1 |
| 1-F | All version-sensitive helper calls use the declared policy; `notes-match ${TAG_PREFIX}${VERSION} <stored-file> "$VERSION_POLICY" "$INITIAL_VERSION"`; shorter spellings below document retained CLI arity only (340) | Retained — Phase 2 preamble, cross-references item 1's round-trip `notes-match` call | `ReleaseSurfaceTest.test_version_and_changelog_routes_are_policy_aware` (line 9923) — checks `"$VERSION_POLICY" "$INITIAL_VERSION"` is present in the file (whole-file scope, not Phase-2-scoped) | Retained; test is whole-file-scoped, not Phase-2-scoped — weak but present |
| 1-G | Bind the hosted candidate to the release-surface commit (`HOSTED_HEAD`, `--first-parent`, manifest blob-identity checks, "later commit cannot reuse older changelog authorization") (342) | New substep, e.g. **"2.0 Bind the hosted candidate"** (T-17 to name) | `ReleaseSurfaceTest.test_hosted_candidate_is_the_release_surface_commit` (line 10070) | Retained → new named substep |
| 1-H | Reconstruct Phase 1's section in the hosted checkout before composing the tag (`PHASE2_SECTION_FILE`, `changelog-section`, `notes-match`, `RELEASE_DATE` derivation, `dates-match`) (344) | New substep, e.g. **"2.1 Reconstruct the Phase-1 section"** | `ReleaseSurfaceTest.test_phase2_reconstructs_the_section_after_the_pr_boundary` (line 10047) | Retained → new named substep |
| 1-I | Zero-tag execution order warning: use only the guarded ref snapshot; any pipe-form `show-ref`/`peel-tag` is rejected and MUST NOT be executed (346) | New substep, e.g. **"2.2 Resolve `<tag_exists>`/`<tag_sha>`"**, immediately followed by the guarded snapshot itself (§3) | `ReleaseSurfaceTest.test_zero_tag_execution_order_contains_no_unguarded_pipeline` (line 10080) | Retained → new named substep |
| 1-J | Report obligations: `$TARGET`, version, bump rationale, per-commit classification, changelog section, tag SHA (351, item 2) | Retained — Phase 2 closing items | **none found** | **GAP** — see §4-G2 |
| 1-K | MUST NOT push the tag or create the Release here; publication is Phase 3, user-authorized (352, item 3) | Retained — Phase 2 closing items | **none found** | **GAP** — see §4-G3 |
| 1-L | Gate: hosted publisher has composed the tag and delivered the report; nothing published (354) | Retained — Phase 2 gate | **none found** | **GAP** — see §4-G4 |

---

## 2. Obligations inside item 1 — the 9,324-char monolithic paragraph (line 348)

This is the paragraph issue #623 names and the one T-17 actually splits. Confirmed still exactly
9,324 characters, one unbroken line, in the current file. Below, every distinct normative
obligation is enumerated in the order it appears, each mapped to a proposed T-17 substep target
and its current proving test(s).

| ID | Obligation (paraphrase) | Proposed T-17 substep | Proving test(s) | Disposition |
|---|---|---|---|---|
| 2-01 | Compose the annotated tag message = Phase-1 section + `Released-at: $RELEASE_DATE` footer into a message file | **2.3 Compose the tag message** | `ReleaseSurfaceTest.test_phase2_reconstructs_the_section_after_the_pr_boundary` (composition-order assertion); behaviorally `ReleaseDatesTest`/`Core...` `dates_match`/`release_dates_consistent` tests (lines 199–230, 4060–4090) | Retained → new substep |
| 2-02 | Assert the two dates agree via `dates-match <Phase-1 section file> <message-file>`, must exit 0 | **2.3 Compose the tag message** (same substep as 2-01) | `_GOVERNANCE_RULES["MEDIUM (run 4): the required date check has a runnable command"]` (test file line 8628) via `GovernanceSurvivalTest.test_every_governance_rule_survives_in_every_payload`; behaviorally `ReleaseDatesTest.test_*`, `test_dates_match_exits_0_when_the_two_dates_agree` (4438), `test_dates_match_exits_1_when_the_dates_disagree` (4443), `test_dates_match_bad_invocation_exits_2` (7081) | Retained → new substep |
| 2-03 | Do not run `git tag` yet — classify first, then tag; the tag command appears only in the `publish_fresh` branch | **2.4 Classification precedes tagging (ordering rule)** | **none found** | **GAP** — see §4-G5 |
| 2-04 | Resolve `<tag_exists>`/`<tag_sha>` from the LOCAL guarded ref snapshot, never a bare `git rev-parse ${TAG_PREFIX}${VERSION}` (that returns the tag object, not the commit) | **2.2 Resolve `<tag_exists>`/`<tag_sha>`** | `_GOVERNANCE_RULES["HIGH-1 (re-run): tag_sha is peeled, never a raw rev-parse"]` (test line 8558); behaviorally `CorePeelTagTest`/`PeelTagTest` (438–465, 4096–4119, 7177–7265), esp. `test_peel_tag_dispatches_and_peels_an_annotated_tag` (7177) which proves the naive-vs-peeled distinction end to end | Retained → new substep |
| 2-05 | Empty ref-snapshot output means `<tag_exists>=false` (`classify` short-circuits past `<tag_sha>`); non-empty output is the commit sha | **2.2 Resolve `<tag_exists>`/`<tag_sha>`** (same as 2-04) | Behaviorally `test_peel_tag_prints_empty_for_an_absent_tag` (7201/588); `CoreClassifyPublishStateTest.test_no_tag_is_publish_fresh` (233/3749) | Retained → new substep |
| 2-06 | Quote `"$TAG_SHA"` always — unquoted empty value disappears as a positional and shifts `classify`'s six args to five (exit 2 on the ordinary fresh-publish path) | **2.5 Invoke `classify`** | `_GOVERNANCE_RULES["MEDIUM (run 5): the possibly-empty tag_sha is quoted"]` (test line 8633) | Retained → new substep |
| 2-07 | Source the other four `classify` arguments explicitly — none is the agent's to invent (lead-in sentence) | **2.5 Invoke `classify`** | **none found for the lead sentence itself** (its four sub-clauses below ARE individually tested) | **GAP** — see §4-G6 |
| 2-08 | `<head_sha>` = `git rev-parse HEAD` | **2.5 Invoke `classify`** | No dedicated pinned-phrase rule; covered only implicitly by `classify_publish_state`'s `head_sha` parameter tests (`ClassifyPublishTest`/`CoreClassifyPublishStateTest`, all rows) | Retained; weak (behavioral only, not textual) |
| 2-09 | `<tag_version>` = the version DERIVED in Phase 1, reused verbatim, never re-parsed from a tag or file | **2.5 Invoke `classify`** | No dedicated pinned-phrase rule found (distinct from 2-10's re-read rule) | Retained; weak — see §4-G7 |
| 2-10 | `<manifest_version>` = first declared manifest's `version`, extracted with the FORMAT'S OWN parser (not a line-grep); JSON via `json.load`, TOML via `tomllib.load`, equivalent for other declared formats | **2.6 Read `<manifest_version>` in its declared format** | `_GOVERNANCE_RULES["MEDIUM (runs 5+7): manifest_version is parsed by the file's own format"]` (8635) + `["MEDIUM (run 7): the manifest reader follows the file's format"]` (8646, pins `import tomllib`) | Retained → new substep |
| 2-11 | This reads the FIRST declared manifest, while Pre-flight's `$BASE_VERSION` reads the MAXIMUM across all — deliberate, safe only because step 6 now asserts every declared path is bumped | **2.6 Read `<manifest_version>`...** (same substep) | `_GOVERNANCE_RULES["MEDIUM (run 7) / HIGH (run 12): max-vs-first coupling, with a REAL guard"]` (8648–8654, pins `check-manifests $TARGET <derived>`) | Retained → new substep |
| 2-12 | Correction: `classify` does NOT catch a partial bump on a fresh publish — `classify_publish_state` short-circuits on `if not tag_exists` before comparing versions; only fires on the resume path | **2.6 / rationale callout** — candidate for `tagging-rationale.md` per AC-14 ("historical rationale may move to a packaged reference") | `test_classify_short_circuits_before_comparing_versions_on_a_fresh_publish` (line 5886, explicit behavioral proof of exactly this correction) | Retained; **strong** proving test — good candidate to keep in-procedure as a decision-point guard rather than move to reference, since it corrects a load-bearing misconception, not mere backstory |
| 2-13 | `<manifest_version>` is re-read from the file NOW, never the value Pre-flight read (Pre-flight read it before step 6's bump) | **2.6 Read `<manifest_version>`...** (same substep) | `_GOVERNANCE_RULES["HIGH (run 4): manifest_version is re-read after the bump, not carried"]` (8619) | Retained → new substep |
| 2-14 | `<tag_version>` is carried, `<manifest_version>` is re-read — the two are sourced differently on purpose | **2.6** (same substep, closing sentence) | Implicitly covered by 2-09/2-13's tests jointly; no single pinned rule for the *contrast* statement itself | Retained; weak — see §4-G7 |
| 2-15 | `<release_nondraft>` = `false` whenever `<tag_exists>` is `false` (never consulted); otherwise `gh release view ... --json isDraft --jq '.isDraft'` **with its answer inverted** | **2.7 Derive `<release_nondraft>`** | `_GOVERNANCE_RULES["HIGH (run 4): release_nondraft inverts gh's isDraft"]` (8621) | Retained → new substep |
| 2-16 | Pass the bare literal `true`/`false`, never the raw `--json` object (coerces falsey and silently hides `already_published`) | **2.7 Derive `<release_nondraft>`** (same substep) | No dedicated pinned-phrase rule found; distinct from 2-15's inversion rule | Retained; weak — see §4-G8 |
| 2-17 | If the `gh` call fails for any reason other than a genuinely absent Release (no remote, no network, unauthenticated) — STOP and surface it rather than guessing | **2.7 Derive `<release_nondraft>`** (same substep) | **none found** | **GAP** — see §4-G9 |
| 2-18 | If the tag exists, classify the state via `classify <tag_exists> <tag_sha> <head_sha> <tag_version> <manifest_version> <release_nondraft>` rather than flatly aborting | **2.5 Invoke `classify`** | Behaviorally the full `ClassifyPublishTest`/`CoreClassifyPublishStateTest` suite (arity + all 4 branches); CLI dispatch proven by `test_classify_prints_label` (504), `test_last_tag_and_notes_match_and_classify_all_dispatch` (7136), consumer-CLI arity loop (7064–7079) | Retained → new substep |
| 2-19 | `publish_fresh` → write the tag ref now, and only here: `git tag -a ${TAG_PREFIX}${VERSION} -F <message-file> --cleanup=verbatim` — never `-m`, never an interactive editor; sole tag-creation point in the whole lane | **2.8 `publish_fresh`: create the tag** | `_GOVERNANCE_RULES["HIGH (run 4): the tag message is written verbatim, not strip-cleaned"]` (8615, pins the `-F <message-file> --cleanup=verbatim` command form + the `strip`-mode rationale); the "sole point" / "never `-m`" claim itself has **no dedicated proving test** | Retained → new substep; partial gap — see §4-G10 |
| 2-20 | `--cleanup=verbatim` is load-bearing: default `strip` mode deletes every `#`-prefixed line, destroying Keep-a-Changelog headings; already happened to a real published tag; a published tag is immutable so a mangled message can never be repaired | **2.8** (same substep, rationale) | Same rule as 2-19 (8615–8616); overlaps `_GOVERNANCE_RULES["immutable-tag hard rule"]` (8506, shared with "Recovering from a bad release") | Retained → new substep; candidate for partial move to `tagging-rationale.md` (historical "already happened" backstory), keep the `--cleanup=verbatim` requirement itself in-procedure |
| 2-21 | Verify it round-tripped rather than trusting the flag: `git cat-file tag ... > <stored-file>` (the raw object, not `git tag -l --format='%(contents)'`, which reconstructs and cannot detect byte differences), then `notes-match ${TAG_PREFIX}${VERSION} <stored-file>` must exit 0 | **2.9 Verify the stored tag round-tripped** | `_GOVERNANCE_RULES["HIGH (run 4): the stored tag message is verified, not assumed"]` (8617) + `["LOW (run 5): the round-trip check reads the raw object, not a reconstruction"]` (8637, pins `git cat-file tag ${TAG_PREFIX}${VERSION}`); behaviorally `test_notes_match_exit_codes` (490) | Retained → new substep |
| 2-22 | `release_dates_consistent` cannot catch a stripped heading on its own (reads a separate argument, only needs `Released-at:`, which survives stripping) — the heading check is the only guard that sees it | **2.9** (same substep, rationale) | No dedicated pinned-phrase rule; implicit from 2-21's test coverage plus `ReleaseDatesTest`'s scope (proves what `dates-match` checks, by omission proves what it does not) | Retained; candidate for `tagging-rationale.md` (explains *why*, not *what*) |
| 2-23 | `notes-match` takes a file path, not a pipe — a shell-specific stdin spelling would not survive the Windows-consumer move | **2.9** (same substep) | **none found** | **GAP** — see §4-G11 |
| 2-24 | `abort_mismatch` (tag points at non-HEAD commit, or version disagrees with manifest) → STOP | **2.10 Classification outcomes** | `ClassifyPublishTest`/`CoreClassifyPublishStateTest` abort_mismatch rows (254–285, 3770–3790) plus the naive-vs-peeled `abort_mismatch` proof at 7217–7265 | Retained → new substep |
| 2-25 | `already_published` (non-draft Release exists) → nothing to do | **2.10 Classification outcomes** | `test_nondraft_release_is_already_published` (247/3763) | Retained → new substep |
| 2-26 | `resume_publish` (tag at HEAD, matching version, no Release) → skip re-tagging, resume at Phase 3 to create the missing Release | **2.10 Classification outcomes** | `ClassifyPublishTest.test_tag_at_head_version_match_no_release_is_resume` (240) and its `CoreClassifyPublishStateTest` mirror (3757) | Retained → new substep |
| 2-27 | `resume_publish` still requires explicit user authorization at Phase 3, exactly as a fresh publish does — landing in `resume_publish` does not shorten/imply/waive the Phase-3 STOP | **2.10** (same substep) | `_GOVERNANCE_RULES["HIGH-4: resume_publish still requires authorization"]` (8538, pins `resume_publish`, `still requires explicit user authorization`) | Retained → new substep |
| 2-28 | Parenthetical: `classify_publish_state` cannot tell whether the tag has been PUSHED (only local tag_sha/head_sha/release_is_nondraft); distinguishing would need a `git ls-remote` round-trip threaded through every call site — deliberately not implemented, closed instead by the authorization restatement in 2-27 | Candidate for `tagging-rationale.md` (explicitly self-described as an unimplemented-by-design explanation, not a decision-point guard) | No pinned test (nothing to test — it documents a non-implementation) | Retained-as-rationale; not a gap since there is no behavior to prove |

---

## 3. Obligations in the "Zero-tag correction" paragraph (line 349)

Directly adjacent to and load-bearing for item 1 (2-04's guarded-snapshot resolution depends on
this exact sequence), but is itself already a separate line/paragraph, not part of the 9,324-char
block.

| ID | Obligation (paraphrase) | Proposed T-17 substep | Proving test(s) | Disposition |
|---|---|---|---|---|
| 3-A | A pipe-form `show-ref`/`peel-tag` assignment MUST NOT be executed under `set -euo pipefail` (a tagless repo makes `show-ref` exit 1 and aborts the assignment before `peel-tag` runs) | **2.2 Resolve `<tag_exists>`/`<tag_sha>`** (same substep as 2-04, its executable form) | `ReleaseSurfaceTest.test_zero_tag_execution_order_contains_no_unguarded_pipeline` (10080, asserts `MUST NOT be executed` and `assertNotIn("git show-ref --tags -d |", ...)`) | Retained → new substep |
| 3-B | Guarded snapshot sequence: `TAG_REFS_FILE=$(mktemp)`, `SHOW_REF_STATUS=0`, `git show-ref --tags -d > "$TAG_REFS_FILE" \|\| SHOW_REF_STATUS=$?`, exit-1-only-is-ok guard, `peel-tag` reads from the file, cleanup | **2.2** (same substep) | `ReleaseSurfaceTest.test_zero_tag_probe_normalizes_only_show_ref_exit_one` (9990, textual) **and** `test_guarded_zero_tag_probe_executes_under_pipefail` (9997, actually executes the literal script under a real POSIX shell against a fresh empty repo — the strongest proof in the file for this obligation) | Retained → new substep |
| 3-C | Exit status 1 alone means the ordinary zero-tag state and becomes empty input; every other non-zero status is terminal | **2.2** (same substep) | Same two tests as 3-B (the executed-script test asserts `test -z "$TAG_SHA"` after a fresh-repo run, i.e. exit-1-is-ok path) | Retained → new substep |
| 3-D | This spelling is safe under `set -euo pipefail` because the expected non-zero status sits left of `\|\|`, not hidden in a pipeline | **2.2** (same substep, rationale) | `_GOVERNANCE_RULES["LOW (run 6): the show-ref exit-status rationale is corrected, not repeated"]` (8655, pins "the expected non-zero status is on the left of `\|\|`") | Retained → new substep |
| 3-E | Never revive the deprecated local-object spelling `git rev-parse ${TAG_PREFIX}${VERSION}`; it returns the tag object, not the commit | **2.2** (same substep, closing warning) | Shares its literal token with 2-04's rule (`_GOVERNANCE_RULES["HIGH-1 (re-run)..."]`, 8558), which anchors on the SAME phrase `git rev-parse ${TAG_PREFIX}${VERSION}` that also appears in item 1 (line 348) | Retained; **weak/shared anchor** — see §4-G12 |

---

## 4. Gaps found (no current proving test) — flagged for T-17/T-18, not filled here

Per this task's scope ("flag any gap you find rather than necessarily filling it"), these are
reported, not patched. All are genuine textual/behavioral obligations with zero hits across
`_GOVERNANCE_RULES`, direct `assertIn`/`assertNotIn` calls, and behavioral unit tests in
`.github/scripts/test_release_lib.py`.

- **G1 (obligation 1-E, HIGH-adjacent) — CLOSED by T-17.** "the interactive agent MUST NOT execute
  the tag-composition commands below locally" has no pinned-phrase or behavioral test. This is the
  core hosted-vs-local boundary the whole Phase-2 redesign exists to enforce, and it currently has
  no textual guard distinct from the surrounding "STOPs before tag composition" sentence (1-D,
  which IS tested). Worth a dedicated `_GOVERNANCE_RULES` entry before or during T-17. *Closed by
  T-17's `_GOVERNANCE_RULES["G1 (T-17): the interactive agent must not execute tag composition
  locally"]`.*
- **G2 (obligation 1-J) — CLOSED by T-18.** the Report-content obligation (item 2: `$TARGET`,
  version, bump rationale, per-commit classification, changelog section, tag SHA) is untested.
  *Closed by `_GOVERNANCE_RULES["G2 (T-18): the Phase-2 report lists all six obligations"]`
  (`.github/scripts/test_release_lib.py`) and `Phase2GovernanceCarryTest` (`test_consumer_smoke.py`),
  anchored on the tail of the report sentence carried verbatim from the pre-split paragraph.*
- **G3 (obligation 1-K) — CLOSED by T-17.** "MUST NOT push the tag or create the GitHub Release
  here" (item 3) is untested — this is the load-bearing Phase-2/Phase-3 boundary statement and
  currently has no guard of its own (Phase 3's own STOP gate is tested elsewhere, but not this
  Phase-2-side half of the boundary). *Closed by T-17's `_GOVERNANCE_RULES["G3 (T-17): Phase 2
  must not push the tag or create the Release"]`.*
- **G4 (obligation 1-L) — CLOSED by T-18.** the Phase 2 closing gate sentence itself is untested.
  *Closed by `_GOVERNANCE_RULES["G4 (T-18): the Phase-2 closing gate says nothing is published
  yet"]` and `Phase2GovernanceCarryTest`.*
- **G5 (obligation 2-03) — CLOSED by T-18.** "classify first, then tag" ordering rule (MEDIUM, run
  3) — the underlying code fact (tag creation only in the `publish_fresh` branch) is implicitly
  true by construction of the prose, but nothing pins the *prose* against regressing to writing
  the ref before classification. *Closed by `_GOVERNANCE_RULES["G5 (T-18): classification precedes
  tagging, stated as an ordering rule"]` (real-source mutation-proved: deleting the sentence turns
  `GovernanceSurvivalTest` and the anchor-uniqueness ratchet both red) plus `Phase2StructureTest`'s
  positional proof that substep 2.4 (classify) precedes substep 2.9 (create the tag) in the
  rendered substep order.*
- **G6 (obligation 2-07) — CLOSED by T-18.** the lead sentence "Source the other four arguments
  explicitly — none of them is yours to invent" has no test of its own; its four sub-clauses
  (2-08/2-09/2-13/2-15) are unevenly covered — see G7/G8. *Closed by `_GOVERNANCE_RULES["G6
  (T-18): the classify-arguments lead sentence names its own scope"]`.*
- **G7 (obligations 2-09, 2-14) — CLOSED by T-18.** `<tag_version>` = the Phase-1-derived version,
  reused verbatim and never re-parsed, and the "carried vs. re-read" contrast sentence, have no
  dedicated pinned-phrase test (only 2-13's re-read half is pinned). *Closed by
  `_GOVERNANCE_RULES["G7 (T-18): tag_version is carried verbatim, manifest_version is
  re-read"]`.*
- **G8 (obligation 2-16) — CLOSED by T-18.** "pass the bare literal `true`/`false`, never the raw
  `--json` object" is untested — distinct from and stronger than 2-15's inversion rule, since it
  guards against a different failure mode (silent falsey coercion of `already_published`). *Closed
  by `_GOVERNANCE_RULES["G8 (T-18): release_nondraft is passed as a bare literal, not raw
  JSON"]`.*
- **G9 (obligation 2-17) — CLOSED by T-17.** the `gh` failure-STOP rule (fail loud on anything but
  a genuinely absent Release) is untested. This is a real operational risk: a transient `gh`
  auth/network failure could currently be mis-handled without any test catching a prose regression
  here. *Closed by T-17's `_GOVERNANCE_RULES["G9 (T-17): a gh failure other than absent-Release
  STOPs, never guesses"]`.*
- **G10 (obligation 2-19, partial) — CLOSED by T-18.** the `--cleanup=verbatim` *command form* is
  pinned (rule at test line 8615), but "sole point in the whole lane at which a tag is created" and
  "never `-m` for multi-line content, never an interactive editor" are not. *Closed by
  `_GOVERNANCE_RULES["G10 (T-18): git tag -a is the sole tag-creation point, never -m"]`.*
- **G11 (obligation 2-23) — CLOSED by T-18.** "`notes-match` takes a path, not a pipe... a
  shell-specific stdin spelling would not survive the move to a Windows consumer" is untested.
  *Closed by `_GOVERNANCE_RULES["G11 (T-18): notes-match takes a path so the check is
  Windows-portable"]`.*
- **G12 (obligation 3-E, weak anchor not a hard gap) — CLOSED by T-18.** the "never revive the
  deprecated `git rev-parse ${TAG_PREFIX}${VERSION}` spelling" sentence at line 349 shares its
  literal anchor phrase with 2-04's rule, whose tokens are already satisfied by line 348 alone.
  Deleting 3-E in isolation would not fail `GovernanceSurvivalTest` today. Flagged the same way the
  test file's own `_KNOWN_WEAK_ANCHORS` ratchet flags this class of defect — a candidate for a
  uniquely-anchored rule if T-17's split separates these two sentences into different substeps
  (which the split's own design intent, "one executable zero-tag sequence", suggests it will).
  *T-17's split kept 2-04 and 3-E adjacent within the SAME substep (2.2) rather than separating
  them into different substeps, so the shared-anchor risk this note predicted did NOT resolve
  itself as a side effect of the split — closed directly instead by
  `_GOVERNANCE_RULES["G12 (T-18): the deprecated rev-parse warning has its own unique anchor"]`,
  anchored on tokens unique to 3-E's own sentence. Real-source mutation-proved: deleting only 3-E's
  sentence (leaving 2-04's rule's own anchor tokens intact) now turns `GovernanceSurvivalTest` and
  the anchor-uniqueness ratchet both red, closing the exact gap this bullet described.*

All twelve gaps are now CLOSED: G1/G3/G9 by T-17, and G2/G4/G5/G6/G7/G8/G10/G11/G12 by T-18. See
`.github/scripts/test_release_lib.py`'s `_GOVERNANCE_RULES` (rules tagged `(T-18)`),
`Phase2StructureTest` (source-only substep-skeleton ordering, with in-suite synthetic-mutant
proofs), and `.github/scripts/test_consumer_smoke.py`'s `Phase2GovernanceCarryTest`
(distribution-faithful archived-payload re-proof of the same nine T-18 phrases, with its own
in-suite mutant proof). T-18 additionally re-anchored `ReleaseSurfaceTest
.test_phase2_reconstructs_the_section_after_the_pr_boundary` from the stray "1. Compose the
annotated tag message" numbered-list marker onto the `### 2.3` heading text T-17 introduced (both
were flagged together in T-17's own handoff note); the stray "1." itself was left alone in
`SKILL.md`, per T-18's scope discipline (prose edits are T-17's territory, already accepted).

- **[NEEDS-TRIAGE] (plan file, not `SKILL.md`):** the T-16 row's own floor-check command in
  `.codearbiter/plans/release-contract-closure.md` (`sed -n '320,346p' ... | grep -c "MUST\|STOP\|
  BLOCK\|exit [0-9]"`) uses an inclusive upper line bound that lands exactly on the *next*
  section's own header (`## Phase 3 — Publish · gate: STOP`) — true at plan-authoring time (line
  346) and, coincidentally, at the same shifted offset in this worktree's current file (line 356,
  see §0). It counts Phase 3's own gate declaration as a 10th Phase-2 marker, which it never was.
  Not fixed here — plan files are outside this task's edit scope (`SKILL.md`/tests only). Any
  later re-run of this floor check (by T-19, T-20, or a future audit) should scope to Phase 2's
  actual body span, currently `330,355` in this file, and re-locate that span fresh each time
  rather than reusing a hardcoded line range.

---

## Summary

- Fresh marker count against the correctly re-located Phase 2 span (`330,355`, not the stale
  `320,346`): **9**, differing from the plan's recorded **10**. Verified in §0 by diffing `HEAD`
  against the working tree: the plan's original command range ended exactly on the *next*
  section's own header line (`## Phase 3 ... gate: STOP`) both at plan-authoring time (line 346)
  and, coincidentally, at the same shifted offset in the current file (line 356) — an off-by-one
  in the floor-check command itself, not a lost Phase 2 obligation. No marker line and no
  obligation is missing between `HEAD` and this worktree.
- Distinct obligations mapped: **13** in the header/context prose (§1, including the section
  header row and 4 flagged gaps), **28** inside item 1's monolithic paragraph (§2, including 8
  flagged gaps and one weak-but-present case), and **5** in the adjacent Zero-tag-correction
  paragraph (§3, including 1 weak-anchor flag) — **46 total obligations**, of which **12** had no
  current proving test at T-16 authoring time (§4: G1–G11 hard gaps, G12 weak-anchor).
- **T-18 update:** all 12 gaps are now CLOSED — G1, G3, G9 by T-17 (`_GOVERNANCE_RULES` entries
  tagged `(T-17)`), and the remaining nine (G2, G4, G5, G6, G7, G8, G10, G11, G12) by T-18
  (`_GOVERNANCE_RULES` entries tagged `(T-18)`, `Phase2StructureTest` in
  `.github/scripts/test_release_lib.py`, and `Phase2GovernanceCarryTest` in
  `.github/scripts/test_consumer_smoke.py`). See §4 above for the per-gap closure citation. Zero
  gaps remain open as of this task.
