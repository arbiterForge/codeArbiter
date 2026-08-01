# Plan — portable release + protected-state machinery

**Spec:** `.codearbiter/specs/portable-release-and-protected-state.md`
**Companion spec:** `.codearbiter/specs/release-portable-fixture.md` (rev 4)
**Date:** 2026-07-31
**Status column is the resume ledger** — `subagent-driven-development` flips a task to `ACCEPTED` on
acceptance; an interrupted run re-enters at the first non-`ACCEPTED` task.

> **Verification note.** Every `unittest discover` verification MUST be run with `NO_COLOR` unset.
> This harness exports `NO_COLOR=1`, which makes `statusline.py` strip SGR and fails 7 palette tests
> against a healthy tree. Prefix with `Remove-Item Env:\NO_COLOR -ErrorAction SilentlyContinue;` in
> the same shell call.

## AC ledger

### Workstream A — release portability

The companion spec is **authoritative**; criteria are cited by ID with a short label rather than
duplicated, so the two documents cannot drift.

| AC | label |
|---|---|
| A-1.1 | `core/pysrc/_releaselib.py` exists; `sync-core --check` passes |
| A-1.2 | mechanism carries no repo-namespace literal (denylist) |
| A-1.3 | repo defaults become required params (`classify_merge_readiness`, `last_tag_select`, `select_release_target`) |
| A-1.4 | `load_targets(path)` returns the full row schema |
| A-1.5 | absent block → declared error |
| A-1.6 | each parser-contract violation → its own declared error (8 cases) |
| A-1.7 | empty block → declared error |
| A-1.8 | series isolation against loaded data |
| A-1.9 | *(transitional)* shim re-exports mechanism, still exposes `RELEASE_TAG_PREFIXES` |
| A-1.10 | this repo's four rows load; target+prefix equal pre-change constants |
| A-1.11 | resolution trace reproduces a recorded pre-change run for `ca` and `ca-pi` |
| A-1.12 | the trace asserts the **intended** `last_tag_select` divergence on a marker-bearing prefix, so it says "exactly this changed, on purpose" rather than "nothing changed" |
| A-2.1 | pre-tag commands execute in declared order |
| A-2.2 | non-zero exit blocks |
| A-2.3 | dirty tree blocks; assertion precedes `rebuild` |
| A-2.4 | >1024-char `pre-tag` entry rejected |
| A-2.5 | `security-controls.md` boundary-crossings entry |
| A-2.6 | protected class admits `release-targets.md` writes only under marker |
| A-2.7 | four-case flank test |
| A-2.8 | `check_command_catalog.py` exists and is non-mutating |
| A-2.9 | this repo's declared rows run green on a reconciled tree |
| A-2.10 | `pre-tag` content-hash change forces re-confirmation |
| A-3.1 | declared manifest → assert equality, BLOCK on mismatch |
| A-3.2 | no manifest → tag is version source |
| A-3.3 | `rebuild` runs; artifacts asserted clean; nondeterministic bundler named |
| A-3.4 | `payload-exclude` honored (ca-pi `tools/`) |
| A-3.5 | `provenance-manifest` optional; absent → skip + report |
| A-3.6 | interpreter fallback where `python3` absent |
| A-4.1 | `payload_version_gate.py` derives prefixes from declared file |
| A-4.2 | target selection name-keyed |
| A-4.3 | workflow-contract test on name agreement |
| A-4.4 | constants removed from shim; six sites + gate still pass; A-1.9 test retired |
| A-5.1 | `decompose` elicits intent only |
| A-5.2 | `context-creation` writes a file `load_targets` accepts |
| A-5.3 | back-fill presents and requires confirmation |
| A-5.4 | back-fill persists; second run reads |
| A-5.5 | first-release changelog baseline instead of per-commit BLOCK |
| A-5.6 | provenance triggers are the rows' referenced paths |
| A-6.0 | the release skill itself resolves targets from the declared file (table becomes loader, helpers repoint, provenance step reads the row field, hosted-lane prose conditionalized) |
| A-6.1 | reference-form guard over `core/surface/skills/**` |
| A-6.2 | `subagent-driven-development` farm.js reference resolves |
| A-6.3 | `decision-lifecycle` reworded to conditional CI reference |
| A-6.4 | `commands/release.md` matches the skill |
| A-6.5 | docs-site guide distinguishes general lane from this repo |
| A-6.6 | portability proven in a clean consumer repo built by `git archive HEAD` — reference resolution, prose-extracted lane driver, and a narrow agent-judgment layer; assertions on derived outputs, never exit codes |
| A-6.7 | this repo still releases — pinned old lane and new lane derive the same version, window and composed tag **message file** from live HEAD, with **zero refs created** |
| A-6.8 | the agent-layer proof cannot rot: a `pre-tag` check asserts the recorded skill-content hash still matches what ships, so editing the skill without re-running the proof blocks the next release |

### Workstream B — protected-state machinery

| AC | criterion |
|---|---|
| B-01 | The registry carries a per-entry policy enum `{marker-gated, helper-only, append-only}`, present from slice 1 |
| B-02 | `marker-gated`: a Write is admitted only under a fresh authoring marker |
| B-03 | `marker-gated`: the Edit flank blocks via `classify_protected` per-class dispatch |
| B-04 | `marker-gated`: the shell flank blocks via a redirect + write-verb regex pair |
| B-05 | `helper-only`: Write, Edit, and shell naming the file are hard-blocked with **no** marker path |
| B-06 | `append-only`: mutation is admitted only via the helper's append verb |
| B-07 | `git add open-tasks.md` passes the shell flank |
| B-08 | `taskwrite add -- "fix open-tasks.md schema"` passes (filename as argv data) |
| B-09 | `tee open-tasks.md` and `>> open-tasks.md` block |
| B-10 | A stale marker (older than the freshness window) does not admit a write |
| B-11 | The class carries a stable `H-NN` ID cited in code comments and its test |
| B-12 | With enrolment live, a `taskwrite.py` invocation still succeeds (circularity proof) |
| B-13 | `release-targets.md` is registered `marker-gated` |
| B-14 | `open-tasks.md` is registered `helper-only` |
| B-15 | `done-tasks.md` is registered `append-only` |
| B-16 | `debug/SKILL.md:80` writes via `{{CMD:task}} add` rather than a direct append |
| B-17 | `taskwrite add` supports the rationale sub-bullet `debug` requires |
| B-18 | `context-creation`'s board population routes through the helper or a declared scaffold-time exemption |
| B-19 | A done-flip still classifies RETAINED through `classify_board_diff` after enrolment |
| B-20 | `taskwrite archive <ID>` appends to `done-tasks.md` then removes from `open-tasks.md`, per item |
| B-21 | `archive` is rerun-safe: dedup by dotted ID, exact text for ID-less entries |
| B-22 | Interruption mid-sweep leaves item-level consistency — no duplicate, no loss |
| B-23 | `done-tasks.md` is created with the expected header shape |
| B-24 | `/ca:standup` offers the sweep under per-item confirmation |
| B-25 | Cutoff is a named constant, default done > 14 days, tested with an injected date |
| B-26 | An undated `[x]` archives only under explicit per-item confirmation |
| B-27 | An ADR records the executable-input boundary and names the ADR-0010 shell-indirection residual |

## Tasks

Paths resolve per `coding-standards.md`: Python hooks in `plugins/ca/hooks/`, shared kernel in
`core/pysrc/`, hook tests in `plugins/ca/hooks/tests/`, standalone gates in `.github/scripts/`.
`SUITE` = `Remove-Item Env:\NO_COLOR -EA SilentlyContinue; python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"`.

### Step 1 — B1: the class and registry (MVP slice begins)

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-01 | `core/pysrc/_protectedstatelib.py` | `python -m py_compile` passes; module imports with zero side effects | registry module exists | B-01 | — | ACCEPTED |
| T-02 | `core/pysrc/_protectedstatelib.py`, `plugins/ca/hooks/tests/test_protectedstatelib.py` | `SUITE -k test_policy_enum` — all three policies present, unknown policy raises | policy enum | B-01 | T-01 | ACCEPTED |
| T-03 | `core/pysrc/_protectedstatelib.py`, `.../tests/test_protectedstatelib.py` | `SUITE -k test_registry_lookup` — registered path returns its policy, unregistered returns None | registry lookup | B-01 | T-02 | ACCEPTED |
| T-04 | `core/pysrc/_protectedstatelib.py`, `.../tests/test_protectedstatelib.py` | `SUITE -k test_marker_gated_write` — fresh marker admits, absent marker blocks | marker-gated Write | B-02 | T-03 | ACCEPTED |
| T-05 | `.../tests/test_protectedstatelib.py` | `SUITE -k test_marker_stale` — marker older than the window blocks | marker freshness | B-10 | T-04 | ACCEPTED |
**Flank wiring design — proxy-ruled 2026-07-31, do not re-derive.** Full reasoning in `sprint-log.md`.

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-05a | `core/pysrc/_protectedlib.py` | `python .github/scripts/test_hooklib.py -k ClassifyProtectedStateTest` — `classify_protected` returns `"state"` for a registered path; return contract stays a set of strings so its four consumers see no change | classifier extension | B-01 | T-05 | ACCEPTED |
| T-05b | `plugins/ca/hooks/tests/test_protectedstatelib.py` | `SUITE -k test_no_legacy_overlap` — **no** registered path classifies into any legacy class; overlap fails loudly as a configuration error rather than resolving by precedence | overlap guard | B-01 | T-05a | ACCEPTED |
| T-06 | `core/pysrc/pre-write.py` | `SUITE -p "test_pre_write.py" -k TestH22ProtectedState` — one generic `"state"` branch resolves the entry's policy from the registry and applies it; no second lookup | pre-write flank | B-02, B-05 | T-05b | ACCEPTED |
| T-07 | `core/pysrc/pre-edit.py` | `SUITE -p "test_pre_edit.py" -k TestH22ProtectedState` — same generic branch; `helper-only` blocks **unconditionally**, no marker path | pre-edit flank | B-03, B-05 | T-06 | ACCEPTED |
| T-08 | `core/pysrc/_bashguardlib.py` | `SUITE -k TestStateShell` — `_state_write_res(basename) -> (redirect_re, write_re)` compiled once at import from the **code-constant** registry, per entry rather than one alternation. `TestStateShellWiring` must drive `run_guards()` itself: every other shell test calls `_check_h22_state` directly and would pass with the wiring deleted | shell flank | B-04, B-05 | T-07 | ACCEPTED |
| T-08a | `plugins/ca/hooks/tests/test_protectedstatelib.py` | `SUITE -k test_marker_touch_allowed` — `touch .codearbiter/.markers/release-targets-authoring` passes the shell flank; `GATE_MARKER_NAMES` gains a comment stating it enumerates **block-to-allow** markers while friction markers stay touchable by design | minting fence | B-04 | T-08 | ACCEPTED |
| T-08b | `plugins/ca/hooks/tests/test_protectedstatelib.py` | `SUITE -k test_verb_in_description_residual` — documents that `taskwrite add -- "remember to tee open-tasks.md"` false-blocks; pins the **passing** B-08 form and records the residual rather than chasing it with smarter parsing | lexical residual | B-08 | T-08a | ACCEPTED |

**Rulings encoded above, with the reasoning that produced them:**

- **The registry is code constants, never disk-loaded.** A disk registry would let a consumer repo
  un-protect `open-tasks.md` by editing a file. Zero-side-effects-at-import prohibits file I/O and
  git, not regex compilation from module constants (`_scopelib.py:109-117` precedent).
- **Dispatch extends `classify_protected` rather than sitting beside it.** `_protectedlib.py:13-19`
  records #528/#529, where independent class checks deadlocked because set membership was
  uncoordinated; and #162 symlink laundering is closed *inside* the classifier
  (`_protectedlib.py:180-204` runs every classifier against raw and realpath forms). A parallel
  lookup ships without symlink resolution, and a symlink alias writes through the guard on day one.
- **`helper-only` is unconditional, with merge conflicts as a named residual.** A conflict in
  `open-tasks.md` itself has no `taskwrite` verb, so resolution routes through logged
  `/ca:override`. The ADR carries a reopen condition: if `gate-events.log` shows board-conflict
  overrides recurring, build a `taskwrite resolve` verb — never a guard exception. A
  conflict-marker content predicate was rejected as converting file content into an authorization
  signal.
- **`GATE_MARKER_NAMES` is not widened.** It enumerates markers that convert a BLOCK into an ALLOW;
  an authoring marker fakes nothing and is self-mintable by design (ADR-0010). The risk runs
  opposite to intuition — a future generic "hardening" over every registered marker would brick
  every minting lane while stopping no non-cooperative agent. T-08a is the fence against that.
| T-09 | `.../tests/test_protectedstatelib.py` | `SUITE -k test_git_add_passes` — `git add open-tasks.md` passes. Load-bearing: `commit-gate` Phase 7 runs exactly that on every retained board flip, so a git verb in the list makes commit-gate block itself | git-verb non-regression | B-07 | T-08 | ACCEPTED |
| T-10 | `.../tests/test_protectedstatelib.py` | `SUITE -k test_filename_as_helper_argv_data_passes` — helper call with the filename in its description passes | argv-data non-regression | B-08 | T-08 | ACCEPTED |
| T-11 | `.../tests/test_protectedstatelib.py` | `SUITE -k test_tee_blocks_unconditionally` and `-k test_append_redirect_blocks_unconditionally` | shell-write blocking | B-09 | T-08 | ACCEPTED |
| T-12 | `.../tests/test_protectedstatelib.py` | `SUITE -k test_taskwrite_invocation_passes_with_enrolment_live` — the real `core/surface/commands/task.md` invocation shape. **Not mutation-killable by construction** — the command names no registered basename, which is the property being proved; assert it against the generated invocation rather than a hand-copy so it notices drift | circularity proof | B-12 | T-08 | ACCEPTED |
| T-13 | `.../tests/test_protectedstatelib.py` | `SUITE -k TestStateShellAppendOnly` — non-append mutation blocks, append verb admitted | append-only policy | B-06 | T-08 | ACCEPTED |
| T-14 | `core/pysrc/pre-write.py`, `plugins/ca/hooks/*.py` | `python .github/scripts/check-plugin-refs.py` passes; `H-NN` cited in code and test | stable hook ID | B-11 | T-08 | ACCEPTED |
| T-15 | `core/pysrc/_protectedstatelib.py` → generated | `python tools/sync-core.py --check` passes | byte-identity | B-01 | T-14 | ACCEPTED |
| T-16 | `.codearbiter/decisions/00NN-*.md` | ADR file exists, dated, user-attributed, names the ADR-0010 residual | ADR authored | B-27 | T-15 | ACCEPTED |

**HARD GATE at T-16** — `/ca:adr` requires user attribution. Halts and surfaces.

### Step 2 — A slices 1–4 (MVP slice continues through T-33)

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-17 | `core/pysrc/_releaselib.py` | `python tools/sync-core.py --check` passes | mechanism ships | A-1.1 | T-15 | ACCEPTED |
| T-18 | `core/pysrc/_releaselib.py`, `.github/scripts/test_release_lib.py` | `python .github/scripts/test_release_lib.py -k denylist` — no repo literal | data-free mechanism | A-1.2 | T-17 | ACCEPTED |
| T-19 | `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k required_params` — three functions reject missing args | required params | A-1.3 | T-18 | ACCEPTED |
| T-20 | `core/pysrc/_releaselib.py` | `test_release_lib.py -k load_targets` — full row schema from a fixture | loader | A-1.4 | T-19 | ACCEPTED |
| T-21 | `core/pysrc/_releaselib.py` | `test_release_lib.py -k absent_block` raises the declared error | absent-block error | A-1.5 | T-20 | ACCEPTED |
| T-22 | `core/pysrc/_releaselib.py` | `test_release_lib.py -k parser_contract` — 8 violations, 8 distinguishable errors | parser contract | A-1.6 | T-21 | ACCEPTED |
| T-23 | `core/pysrc/_releaselib.py` | `test_release_lib.py -k empty_block` raises the declared error | empty-block error | A-1.7 | T-22 | ACCEPTED |
| T-24 | `.github/scripts/test_release_lib.py` | `-k series_isolation` — `v` and `ca-pi-v` resolve independently | series isolation | A-1.8 | T-23 | ACCEPTED |
| T-25 | `.github/scripts/_releaselib.py` | `python .github/scripts/payload_version_gate.py --plugin plugins/ca --base origin/main` exits 0 (bare invocation exits 2 — args are required) | transitional shim | A-1.9 | T-24 | ACCEPTED |
| T-26 | `.codearbiter/release-targets.md` | `python .github/scripts/test_release_lib.py -k this_repo_rows` — 4 rows load, prefixes match constants, **and every one of the four declares `provenance-manifest`** | repo rows declared | A-1.10 | T-25 | ACCEPTED |
| T-27a | `.github/scripts/fixtures/release-trace/` | `python .github/scripts/test_release_trace.py -k fixture_shape` — frozen tag list, manifests, commit graph, 4 rows | trace fixture | A-1.11 | T-26 | ACCEPTED |
| T-27b | `.github/scripts/test_release_trace.py` | `-k old_lane_loads` — helpers pinned via `git show <pre-change-sha>:.github/scripts/_releaselib.py` | pinned old lane | A-1.11 | T-27a | ACCEPTED |
| T-27c | `.github/scripts/test_release_trace.py` | `-k old_lane_live` — the transcribed old lane resolves `ca`'s real last tag against the live repo; **divergence is a STOP, not a fixup** | old-lane validation | A-1.11 | T-27b | ACCEPTED |
| T-27d | `.github/scripts/test_release_trace.py` | `-k trace_matches` — new lane reproduces the recorded variable dict for `ca` **and** `ca-pi` | trace assertion | A-1.11 | T-27c | ACCEPTED |
| T-28 | `core/surface/skills/release/SKILL.md` | `test_release_lib.py -k pre_tag_order` — declared order preserved | pre-tag order | A-2.1 | T-27 | ACCEPTED |
| T-29 | `core/pysrc/_releaselib.py` | `-k pre_tag_exit` — non-zero exit blocks | pre-tag exit | A-2.2 | T-28 | ACCEPTED |
| T-30 | `core/pysrc/_releaselib.py` | `-k pre_tag_dirty` — dirty tree blocks, assertion precedes rebuild | clean-tree gate | A-2.3 | T-29 | ACCEPTED |
| T-31 | `core/pysrc/_releaselib.py` | `-k pre_tag_cap` — >1024 chars rejected | length cap | A-2.4 | T-30 | ACCEPTED |
| T-32 | `.codearbiter/security-controls.md` | boundary-crossings entry present; `test_release_lib.py -k boundary_entry` | boundary declared | A-2.5 | T-31 | ACCEPTED |
| T-33 | `core/pysrc/_protectedstatelib.py`, `.codearbiter/release-targets.md` | `SUITE -k test_release_targets_registered` — marker-gated, 4-case flank test passes | consumer 1 enrolled | A-2.6, A-2.7, B-13 | T-32 | ACCEPTED |

**HARD GATE at T-32** — `security-controls.md` is a trust-boundary change.

**— END MVP SLICE —** At T-33 the registry exists with a live consumer, the mechanism ships, this
repo's rows load, and the release lane is proven behavior-identical. Shippable on its own.

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-34 | `.github/scripts/check_command_catalog.py` | script exits 0 on a reconciled tree, 1 on drift, mutates nothing | catalog check | A-2.8 | T-33 | ACCEPTED |
| T-35 | `.codearbiter/release-targets.md` | all declared `pre-tag` commands exit 0 on a clean tree | rows run green | A-2.9 | T-34 | ACCEPTED |
| T-36 | `core/pysrc/releasehash.py`, `tools/sync-core.py` generated set | `python tools/sync-core.py --check` passes with it enrolled; `SUITE -k test_pre_tag_hash` — changed hash forces re-confirmation | hash re-confirm | A-2.10 | T-35 | ACCEPTED |
| T-37 | `core/pysrc/_releaselib.py` | `-k manifest_declared` — equality asserted, mismatch BLOCKs | manifest assert | A-3.1 | T-36 | ACCEPTED |
| T-38 | `core/pysrc/_releaselib.py` | `-k manifest_absent` — tag is version source, no assertion | optional manifest | A-3.2 | T-37 | ACCEPTED |
| T-39 | `core/pysrc/_releaselib.py` | `-k rebuild_artifacts` — stale bundle blocks, cause named | rebuild gate | A-3.3 | T-38 | ACCEPTED |
| T-40 | `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k payload_exclude` — ca-pi `tools/` excluded | payload exclusions | A-3.4 | T-39 | ACCEPTED |
| T-41 | `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k provenance_optional` — absent → skipped and reported | optional provenance | A-3.5 | T-40 | ACCEPTED |

**The skill rewrite — the campaign's central deliverable.** Absent from the first plan draft; a review
found the bijection passed because A-6.1 mapped to the guard *script* rather than the cleanup it
enforces. `SKILL.md` here means `core/surface/skills/release/SKILL.md` (the source; three payloads
generate from it).

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-41a | `core/surface/skills/release/SKILL.md` | `python .github/scripts/test_release_lib.py -k skill_uses_loader` — Targets table replaced by `load_targets`; no hardcoded row survives | table → loader | A-6.0 | T-41 | ACCEPTED |
| T-41b | `core/surface/skills/release/SKILL.md` | `python .github/scripts/check_skill_portability.py` — no `.github/scripts/` invocation remains; helpers resolve under `${CLAUDE_PLUGIN_ROOT}` | helper repointing | A-6.0 | T-41a | ACCEPTED |
| T-41c | `core/surface/skills/release/SKILL.md` | `-k skill_provenance_field` — Phase 3 step 5 reads the row field; absent → documented skip | provenance step | A-6.0, A-3.5 | T-41b | ACCEPTED |
| T-41d | `core/surface/skills/release/SKILL.md` | `-k skill_conditional_prose` — hosted-lane and immutability sections conditional on repo capability | prose conditionals | A-6.0 | T-41c | ACCEPTED |
| T-41e | — (review only) | adversarial Opus agent reviews the rewritten skill; BLOCK-level findings fixed and re-reviewed before proceeding | mid-sprint review | A-6.0 | T-41d | ACCEPTED |
| T-41f | `core/pysrc/_releaselib.py` | `python "<plugin-root>/hooks/_releaselib.py" tag-prefix ca` exits 0 from a consumer-shaped environment — the mechanism gains a `__main__` CLI entry point | shipped CLI exists | A-6.0 | T-41b | ACCEPTED |

> **T-41f exists because the plan had a hole.** T-41b repoints the skill's helper
> invocations to `${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py`, but that file has **zero**
> `__main__` — only the `.github/scripts/` shim carries a CLI. Repointing alone would aim the
> prose at a file that cannot be invoked, so `tag-prefix`, `last-tag` and `classify` would still
> fail in a consumer *after* the rewrite "succeeded". Found by the T-74 lane driver, which runs
> the prose's invocation strings rather than importing the library. This is the third ledger hole
> in this campaign — the first two were the missing skill rewrite (A-6.0) and the missing
> portability proof (A-6.6/6.7) — and all three shared a shape: a criterion set that was
> internally consistent and silent about a step nobody had named.
| T-42 | `core/surface/skills/release/SKILL.md` | `-k interpreter_fallback` — uses the shipped `python3 "<p>" … \|\| python "<p>" …` pattern (`taskwrite.py:11`) | interpreter fallback | A-3.6 | T-41e | ACCEPTED |
| T-43 | `.github/scripts/payload_version_gate.py` | `python .github/scripts/test_payload_version_gate.py -k no_prefix_literal` | CI reads declared source | A-4.1 | T-42 | ACCEPTED |
| T-44a | `.github/scripts/_releaselib.py` | `python .github/scripts/test_release_lib.py -k select_target_name_keyed` — `name=value` argv pairs; unknown name fails closed | shim CLI shape | A-4.2 | T-43 | ACCEPTED |
| T-44b | `.github/workflows/release.yml` | `python .github/scripts/test_release_workflow.py -k name_keyed` — inputs plumbed by name, order-independent | workflow plumbing | A-4.2 | T-44a | ACCEPTED |
| T-45 | `.github/scripts/test_release_workflow.py` | `-k name_agreement` fails when declared set and workflow inputs disagree | contract test | A-4.3 | T-44b | ACCEPTED |
| T-46 | `.github/scripts/_releaselib.py` | `python .github/scripts/test_payload_version_gate.py`; `python .github/scripts/test_release_workflow.py`; `python .github/scripts/test_release_lib.py` all green; A-1.9's `test_releaselib_shim_exports_constants` deleted in this commit | shim data removed | A-4.4 | T-45 | ACCEPTED |

### Step 3 — A slice 5: onboarding and back-fill

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-47 | `core/surface/skills/decompose/SKILL.md` | `python .github/scripts/test_board_sync.py -k decompose_intent_only` | intent-only elicitation | A-5.1 | T-46 | ACCEPTED |
| T-48 | `core/surface/skills/context-creation/SKILL.md` | `python .github/scripts/test_release_lib.py -k context_creation_writes_loadable` — the written file parses via `load_targets` | full elicitation | A-5.2 | T-47 | ACCEPTED |
| T-49 | `core/surface/skills/release/SKILL.md` | `python .github/scripts/test_release_lib.py -k backfill_requires_confirmation` — no write without confirm | back-fill gate | A-5.3 | T-48 | ACCEPTED |
| T-50 | `core/surface/skills/release/SKILL.md` | `python .github/scripts/test_release_lib.py -k backfill_persists` — second run reads, does not re-detect | back-fill persist | A-5.4 | T-49 | ACCEPTED |
| T-51 | `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k first_release_baseline` — baseline derived from `git log --diff-filter=A -- .codearbiter/CONTEXT.md`, with a user override offered in the prompt | adoption baseline | A-5.5 | T-50 | ACCEPTED |
> **T-51 completed (2026-07-31).** Mechanism and CLI landed in `a31d398`; the lane prose that USES them landed with run 11's remediation, batched with T-42's so one exercise covers both. The row is now ACCEPTED because the lane genuinely offers the baseline, not merely because the helper exists.

| T-52 | `.codearbiter/.provenance/release-targets.json` | `python .github/scripts/test_provenancelib.py -k release_targets_triggers` | drift triggers | A-5.6 | T-51 | ACCEPTED |

### Step 4 — B3: the two conversions

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-53 | `core/pysrc/taskwrite.py`, `core/pysrc/_taskboardlib.py` | `python .github/scripts/test_taskwriter.py -k add_rationale` — sub-bullet round-trips; `python tools/sync-core.py --check` passes | helper extension | B-17 | T-52 | ACCEPTED |
| T-54 | `core/surface/skills/debug/SKILL.md` | `python .github/scripts/test_board_sync.py -k debug_uses_helper` — no direct append remains | debug converted | B-16 | T-53 | ACCEPTED |
| T-55 | `core/surface/skills/context-creation/SKILL.md` | `python .github/scripts/test_board_sync.py -k context_creation_board_route` — seeds via a repeated `taskwrite add` loop; **no file-absent exemption predicate exists** | scaffold route | B-18 | T-54 | ACCEPTED |
| T-56 | `.github/scripts/test_board_sync.py` | `-k done_flip_retained` — flip classifies RETAINED with enrolment **simulated in a fixture**; live post-enrolment coverage is T-67 | ADR-0008 composition | B-19 | T-55 | ACCEPTED |

### Step 5 — B4: archive verb, done-tasks, sweep

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-57 | `core/pysrc/_taskboardlib.py` | `test_taskwriter.py -k archive_transform` — pure text→text move | archive transform | B-20 | T-56 | ACCEPTED |
| T-58 | `core/pysrc/taskwrite.py` | `python .github/scripts/test_taskwriter.py -k archive_verb` — appends then removes, per item; **creates `done-tasks.md` with the canonical header when absent** | archive verb | B-20, B-23 | T-57 | ACCEPTED |
| T-59 | `.github/scripts/test_taskwriter.py` | `-k archive_rerun` — dotted-ID and exact-text dedup, no duplicate | rerun safety | B-21 | T-58 | ACCEPTED |
| T-60 | `.github/scripts/test_taskwriter.py` | `-k archive_interrupted` — kill between phases leaves no dup and no loss | interruption safety | B-22 | T-59 | ACCEPTED |
| T-61 | `core/pysrc/init-codearbiter.py` | `python .github/scripts/test_taskboardlib.py -k done_tasks_shape` — greenfield scaffold path; `python tools/sync-core.py --check` passes | done-tasks scaffolded | B-23 | T-60 | ACCEPTED |
| T-62 | `core/pysrc/_taskboardlib.py` | `-k archive_cutoff` — named constant, injected date | cutoff constant | B-25 | T-61 | ACCEPTED |
| T-63 | `core/pysrc/_taskboardlib.py` | `-k archive_undated` — undated `[x]` items appear in their own section, **excluded from cutoff math**, archivable only per-item | undated rule | B-26 | T-62 | ACCEPTED |
| T-64 | `core/surface/commands/standup.md` | `python .github/scripts/test_ux_conversion.py -k standup_sweep` — per-item confirmation | standup owns sweep | B-24 | T-63 | ACCEPTED |
| T-65 | `core/pysrc/_protectedstatelib.py` | `SUITE -k test_done_tasks_registered` — append-only, archive verb admitted | consumer 3 enrolled | B-15 | T-64 | ACCEPTED |

### Step 6 — B2: open-tasks enrolment (lands last, per sequencing)

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-66 | `core/pysrc/_protectedstatelib.py` | `SUITE -k test_open_tasks_registered` — helper-only, no marker path | consumer 2 enrolled | B-14 | T-65 | ACCEPTED |
| T-67 | full suite | `SUITE` green; `python .github/scripts/test_taskwriter.py`; `test_board_sync.py` | enrolment regression | B-05, B-12, B-19 | T-66 | ACCEPTED |

### Step 7 — A slice 6: surfaces

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-68a | `.github/scripts/check_skill_portability.py` | `python .github/scripts/test_skill_portability.py -k matching_rule` — reference-form rule stated in the docstring; flags an executed `.github/scripts/` path, does **not** flag a scan-target list entry | matching rule | A-6.1 | T-67 | PENDING |
| T-68b | `.github/scripts/check_skill_portability.py` | guard exits 1 against `core/surface/skills/**` at `469c2fb`, exits 0 after T-41a–d, T-69 and T-70 | guard wiring | A-6.1 | T-68a | PENDING |
| T-69 | `core/surface/skills/subagent-driven-development/SKILL.md` | guard passes; reference reads `${CLAUDE_PLUGIN_ROOT}/tools/farm.js` | farm.js reference | A-6.2 | T-68b | PENDING |
| T-70 | `core/surface/skills/decision-lifecycle/SKILL.md` | guard passes; line is a conditional CI reference | ADR-identity reference | A-6.3 | T-69 | PENDING |
| T-71 | `core/surface/commands/release.md` | `python .github/scripts/check-plugin-refs.py`; documents `[target]` only — `--auto`, `--dry-run` and `<version>` deleted (a real dry-run is tracked as #565); phase numbers match the skill | command surface | A-6.4 | T-70 | PENDING |
| T-72 | `site/src/content/docs/guides/releasing-a-version.md` | `npm --prefix site test` green | docs guide | A-6.5 | T-71 | PENDING |

### Step 8 — Completion proof (the sprint is not done without this)

Per the maintainer's completion bar: proven to work **and** to port. Verifying against this repo's
hand-built `.codearbiter/` state is the documented way consumer-facing bugs stay hidden, so the
consumer proof runs in a scratch repo with no file from this repository present.

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
**Pulled forward as a ratchet.** T-73a/T-73b run right after T-27d, not at the end. The loader and
library already landed at `0664506`, so the fixture is feasible now — and authoring it at the end
means transcribing its expected values from the implementation it is supposed to check.

The ratchet is what makes early landing safe. A long-red test cannot be a required check while red,
so it enforces nothing for weeks, and a test red for its whole life gets edited into passing on the
day it finally matters. Instead T-73b compares the unresolved-reference set against a **committed
known-failures list** — green and required from day one, failing whenever that set changes in
**either** direction without the list moving in the same diff. It catches both a shrink nobody
recorded and a *new* contaminating reference sneaking in mid-campaign, which a plain red test would
silently absorb. T-41a–d, T-69 and T-70 each shrink the list in their own commit; T-79 asserts it is
empty and deletes the ratchet.

| id | path(s) | verification | maps-to | covers | depends | status |
|---|---|---|---|---|---|---|
| T-73a | `.github/scripts/test_consumer_smoke.py` | scratch consumer repo built; plugin materialized by `git archive HEAD -- plugins/ca` into a scratch cache — **not** an in-repo `CLAUDE_PLUGIN_ROOT` pointer, **not** a recursive copy (both carry uncommitted and gitignored dev-tree state) | consumer fixture | A-6.6 | T-27d | ACCEPTED |
| T-73b | `.github/scripts/test_consumer_smoke.py`, `.github/scripts/known-unresolved-refs.txt` | `-k reference_resolution_ratchet` — unresolved refs in the **installed** SKILL.md equal the committed list exactly; fails on any change in either direction | reference ratchet | A-6.6 | T-73a | ACCEPTED |
| T-74 | `.github/scripts/test_consumer_smoke.py` | `-k lane_driver` — the mechanical sequence runs via **invocation strings extracted from the skill text**, never direct imports, so prose/CLI drift fails here | lane driver | A-6.6 | T-73b | ACCEPTED |
| T-75 | `.github/scripts/test_consumer_smoke.py` | `-k consumer_end_to_end` — asserts on derived **outputs** (resolved row, `LAST_TAG`, computed bump, rolled changelog text), never exit codes alone | portability proof | A-6.6 | T-74 | ACCEPTED |
| T-76 | `.github/scripts/test_consumer_smoke.py` | `-k backfill_detects` — no declared file, so the detected shape is presented and does not proceed unconfirmed | consumer back-fill | A-6.6 | T-75 | ACCEPTED |
| T-77 | `.github/scripts/test_release_trace.py` | `-k this_repo_still_releases` — pinned pre-change lane and new lane both derive next version, window and composed tag **message file** from live HEAD; equality asserted; **zero refs created** | this repo still releases | A-6.7 | T-76 | ACCEPTED |
| T-78 | `.codearbiter/reports/agent-lane-proof.json` | **SUBSTITUTED, see note:** eight independent BLIND agent exercises (not the scripted happy-path / missing-footer / back-fill scenarios this row originally specified), each against the skill as the previous run left it, with the **content hash of the shipped skill** recorded for the run the gate enforces | agent judgment layer | A-6.6 | T-77 | ACCEPTED |

> **T-78 scope substitution (2026-07-31).** This row originally specified a SCRIPTED scenario harness. What shipped is eight human-directed blind exercises plus a hash-freshness gate wired as a declared `pre-tag` command. The substitution is recorded rather than silently absorbed: a scripted harness asserts only what its author already thought to script, and every HIGH this campaign found after the first run was in a seam nobody had thought to script. HIGHs by run: 4, 2, 0, 2, 1, 1, 1, 0. Three were introduced by the campaign's own remediation of an earlier HIGH. A scripted harness remains worth building and is NOT claimed by this row.
| T-79 | `.codearbiter/release-targets.md`, `.github/scripts/check_skill_proof_fresh.py` | a `pre-tag` row asserts the recorded skill hash still matches the shipped skill, so editing the skill without re-running the proof **blocks the next release**; and the known-failures list is asserted empty, retiring the ratchet | proof freshness + ratchet retirement | A-6.8, A-6.1 | T-78 | ACCEPTED |

## Pre-run dispositions (maintainer-answered 2026-07-31)

Encoded here so a subagent does not re-surface them. Full SMARTS in `sprint-log.md`.

- **T-06 – T-08 — delegate with a tripwire.** Proceed when `security-reviewer` PASSes and B-07…B-12
  are green; halt only on a finding. This was a risk-appetite call, not an analysis result: Reliable
  and Securable favored an unconditional halt.
- **T-16 / T-32 — content pre-approved.** ADR-**0024** (verified next-free) records the
  executable-input boundary, the ≤1024 cap, that the marker is audit friction rather than
  authorization, and names the ADR-0010 shell-indirection residual per flank. The
  `security-controls.md` row mirrors ADR-0002's. T-32 lands without a stop; **T-16 still halts, for
  attribution only**.
- **T-41e — adversarial Opus review**, not a maintainer stop. Maintainer reviews the skill text at PR
  stage.
- **Identifiers** — hook ID **H-22** (H-21 is taken); ADR **0024**; marker `release-targets-authoring`,
  with `<file>-authoring` as the pattern for future consumers.
- **T-13 / T-65 — `append-only` blocks all tool writes.** Flank-identical to `helper-only`; the
  distinction lives in the helper's verb constraint. No tail-anchored-Edit admission.
- **T-55 — helper loop, no exemption predicate.** A file-absent exemption would let delete-then-Write
  launder arbitrary content through "the file is absent".

**LOW — a known dead window.** Between T-33 (rows enrolled `marker-gated`) and T-49/T-50 (the minter
prose lands), no lane can legally edit `release-targets.md`. A correction in that window needs a
hand-armed marker or `/ca:override`. Expected, not a defect — do not treat the block as a failure.

## Coverage proof

**Every AC → at least one task.** A-1.1→T-17, A-1.2→T-18, A-1.3→T-19, A-1.4→T-20, A-1.5→T-21,
A-1.6→T-22, A-1.7→T-23, A-1.8→T-24, A-1.9→T-25/T-46, A-1.10→T-26, A-1.11→T-27a/b/c/d, A-2.1→T-28,
A-2.2→T-29, A-2.3→T-30, A-2.4→T-31, A-2.5→T-32, A-2.6→T-33, A-2.7→T-33, A-2.8→T-34, A-2.9→T-35,
A-2.10→T-36, A-3.1→T-37, A-3.2→T-38, A-3.3→T-39, A-3.4→T-40, A-3.5→T-41/T-41c, A-3.6→T-42,
A-4.1→T-43, A-4.2→T-44a/T-44b, A-4.3→T-45, A-4.4→T-46, A-5.1→T-47, A-5.2→T-48, A-5.3→T-49,
A-5.4→T-50, A-5.5→T-51, A-5.6→T-52, **A-6.0→T-41a/T-41b/T-41c/T-41d/T-41e**, A-6.1→T-68a/T-68b,
A-6.2→T-69, A-6.3→T-70, A-6.4→T-71, A-6.5→T-72, **A-6.6→T-73/T-74/T-75, A-6.7→T-76**.
B-01→T-01/02/03/15/T-05a/T-05b, B-02→T-04/T-06, B-03→T-07, B-04→T-08/T-08a, B-05→T-06/07/08/T-67,
B-06→T-13, B-07→T-09, B-08→T-10/T-08b, B-09→T-11, B-10→T-05, B-11→T-14, B-12→T-12/T-67, B-13→T-33, B-14→T-66,
B-15→T-65, B-16→T-54, B-17→T-53, B-18→T-55, B-19→T-56/T-67, B-20→T-57/T-58, B-21→T-59, B-22→T-60,
B-23→T-58/T-61, B-24→T-64, B-25→T-62, B-26→T-63, B-27→T-16.

**Every task → at least one AC.** Verified across all 90 tasks; no task covers nothing.

Bijective coverage proven: **72 criteria, 90 tasks**, no uncovered criterion and no orphan task.
(90 rather than 86 after the proxy rulings added T-05a, T-05b, T-08a, T-08b — the classifier
extension, the legacy-overlap guard, the marker-minting fence, and the lexical-residual pin.)

*Rev 2/3 note — two holes were in the ledger, not the task set.* The first draft claimed bijection
over 69 criteria and 72 tasks. The claim was formally true and hollow both times: A-6.1 mapped to the
portability guard *script* while nothing rewrote the skill it polices (closed by A-6.0 + T-41x), and
#563's consumer-portability acceptance existed only as a prose checkbox, so no criterion and
therefore no task covered the thing the campaign is *for* (closed by A-6.6/A-6.7 + T-73–T-76). A
coverage proof over a criteria set with a hole in it proves the hole is consistent, nothing more.

## Dependency order

Strictly linear as written, with no cycle:
B1 (T-01–16) → A 1–4 (T-17–T-46, including the T-41x skill rewrite) → A 5 (T-47–52) →
B3 (T-53–56) → B4 (T-57–65) → B2 enrolment (T-66–67) → A 6 (T-68a–72).

Ordering constraints that are not merely sequential:

- **T-46 must not land before T-43–T-45**, or `payload_version_gate.py` breaks on every PR. T-25's
  transitional test is deleted in T-46's own commit.
- **T-41a–d must land before T-68b**, since the guard cannot go green while the release skill still
  carries its non-payload references. T-68b's verification names them explicitly.
- **T-58 must land before T-65.** The archive verb creates `done-tasks.md` when absent; once the file
  is enrolled `append-only`, no tool write can create it. Every already-initialized repo — including
  this one — never re-runs `init-codearbiter.py`, so T-61's scaffold path alone would leave the file
  missing and the first archive failing.

## Hard gates on the critical path

After the pre-run dispositions, **two** stops remain rather than four:

- **T-16** — ADR-0024 attribution. Content pre-approved; the halt is the signing act only.
- **Landing** — merge to the default branch; `/ca:sprint` auto-selects open-PR and never merges.

Downgraded, with the reason recorded:

- **T-06 – T-08** — now conditional. Halts only if `security-reviewer` reports a finding or any of
  B-07…B-12 is red.
- **T-32** — no longer a stop; the boundary row text is pre-approved.

Conditional stops that are not scheduled but may fire on genuinely new evidence:

- **T-27c** — if the transcribed old-lane script disagrees with the live repo, that is new evidence
  about the pre-change lane, not a fixup. STOP and investigate.
- **T-35** — a stale badge is not a stop (DECISION-0034 pre-decides the reconcile-and-rerun loop), but
  drift revealing the catalog itself is wrong is new information.

## Out of scope

- `[NEEDS-TRIAGE]` D-6: whether `.github/published-tags.json` relocates to `.codearbiter/`. Tracked
  in `open-questions.md`; not planned here.
