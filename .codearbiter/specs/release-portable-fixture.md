# Spec — `/ca:release` as a portable, shippable fixture

**Date:** 2026-07-30 (rev 4, after three adversarial review passes — cleared for planning)
**Status:** awaiting approval
**Issue:** #563
**Governs:** core/surface/skills/release/**, core/surface/commands/release.md, core/pysrc/_releaselib.py, plugins/ca/skills/release/**, .github/scripts/_releaselib.py, .codearbiter/release-targets.md

## Problem

`/ca:release` encodes this repository's release mechanics as skill logic and depends on three files
outside the plugin payload — `.github/scripts/_releaselib.py`, `tools/build-host-packages.py`, and
`.github/published-tags.json`. None ship under `plugins/ca/`, so the lane cannot execute in any repo
that installs codeArbiter. Pre-flight's first resolution step calls a helper that is not there.

The skill was portable at `6a45173` (51 lines, `git describe --tags`, root `CHANGELOG.md`) and lost
portability at `c12b1a3` (#125), which is an ancestor of the multi-plugin work at `c20c2d0` (#497).
Every hardening commit fixed a real failure; the defect is that each fix was written as a hardcoded
fact about this repository instead of a parameter read from project state.

**Measurement rule.** A reference is contaminating when it names a path **belonging to this
repository** that the skill *executes or reads*. Bare substring matching is rejected —
`context-creation/SKILL.md:49` has a scout read `.github/workflows/` in the **consumer's** repo,
which is correct and must never be flagged. Under this rule three shipped skills are contaminated:
`release` (heavily), `subagent-driven-development:45` (`tools/farm.js`, which ships at
`plugins/ca/tools/farm.js` and so resolves in neither form), and `decision-lifecycle:70`.

## Scope

**In scope.** Split `_releaselib` into portable mechanism (to `core/pysrc/`) and repo-specific data
(to project state); a new `.codearbiter/release-targets.md` with a defined grammar and parser
contract; check-only pre-tag commands per row (DECISION-0034); a new protected-write class for the
declaration file; `context-creation` full elicitation with `decompose` intent-only and a release-time
back-fill; CI repointed to the declared source with name-keyed target selection; all three
contaminated skills fixed; `commands/release.md` reconciled with the skill.

**Explicitly out of scope.** Changing what the gates *do* — immutable-tag doctrine, the
`CHANGELOG:`-footer BLOCK, publish read-back, derive-don't-guess all survive unchanged in behavior.
Redesigning `_releaselib`'s algorithms. The `release.yml` job structure beyond name-keying selection.
Adding a governance host. Changing this repo's four target definitions. **Relocating**
`.github/published-tags.json` — its path becomes an optional row field; where this repo's copy lives
is deferred to D-6.

## Source of truth

Every skill and command edit lands in `core/surface/`, never a generated `plugins/*/` copy. The
release skill ships in three payloads (`plugins/ca/skills/release/`,
`plugins/ca-codex/skills/ca-release/`, `plugins/ca-pi/skills/ca-release/` plus
`plugins/ca-pi/routines/release/`). Guards and structural assertions target the surface source.

## Migration ordering (load-bearing)

Six sites shell out to `python3 .github/scripts/_releaselib.py` — `release.yml:135,171` and
`.github/actions/publish-release/action.yml:125,164,180,228` — and `payload_version_gate.py:53`
imports `RELEASE_TAG_PREFIXES` from it at module load.

**The shim is permanent.** `.github/scripts/_releaselib.py` remains as CI's stable entry point,
becoming a thin, **data-free** re-export of the generated mechanism plus a CLI that loads target data
from the declared file. It is never deleted. This deliberately avoids coupling six CI call sites to a
generated payload path.

1. **Slice 1** lands `core/pysrc/_releaselib.py` (mechanism only) and converts the shim to re-export
   it while **temporarily retaining** the data constants. Every CI consumer keeps working unchanged.
2. **Slice 4** removes the constants from the shim once the gate and workflow read the declared file.
   The shim itself survives.

The invariant is scoped, not absolute: **until slice 4 completes**, no commit may leave
`RELEASE_TAG_PREFIXES` unimportable from the shim. AC-1.9 is explicitly **transitional** — it is
superseded by AC-4.4, and the obligation test it creates (`test_releaselib_shim_exports_constants`)
is retired in the same commit that satisfies AC-4.4.

The shim locates the declared file from its own `__file__` rather than the working directory, using
the cwd-independent pattern already at `payload_version_gate.py:56`. All six shell-out sites run at
the checkout root of a full `actions/checkout` and the file is tracked, so it is present wherever the
shim is. **An absent or unparseable file fails closed** — the loud parser error turns preflight or
the gate red, which is the correct direction for a `contents: write` publisher. Nobody should later
"fix" that into a default.

## File grammar

Per-target sub-blocks of `key: value` lines inside the HTML-comment delimiters `_scopelib`
recognizes. **Not a markdown table** — this repo's pre-tag commands contain pipes.

```
<!-- release-targets -->
[ca]
prefix: v
manifest: plugins/ca/.claude-plugin/plugin.json
changelog: CHANGELOG.md
payload: plugins/ca/
rebuild: cd plugins/ca/tools && npm run build
artifacts: plugins/ca/tools/farm.js
provenance-manifest: .github/published-tags.json
latest-eligible: true
pre-tag: python3 .github/scripts/check_badge_consistency.py
pre-tag: python3 .github/scripts/check_command_catalog.py

[ca-pi]
prefix: ca-pi-v
manifest: plugins/ca-pi/package.json
manifest: package.json
changelog: plugins/ca-pi/CHANGELOG.md
payload: plugins/ca-pi/
payload-exclude: plugins/ca-pi/tools/
rebuild: node plugins/ca-pi/tools/build.mjs
artifacts: plugins/ca-pi/extensions/codearbiter.js
artifacts: plugins/ca-pi/extensions/codearbiter-child.js
latest-eligible: false
pre-tag: python3 tools/build-host-packages.py --check
<!-- /release-targets -->
```

A single-artifact consumer declares one block:

```
<!-- release-targets -->
[app]
prefix: v
manifest: package.json
changelog: CHANGELOG.md
payload: .
<!-- /release-targets -->
```

`prefix`, `changelog`, `payload` are required. All other keys are optional.

**Script status.** `check_badge_consistency.py` exists. `tools/build-host-packages.py --check` exists
(line 177) and is used directly rather than wrapping it in a new script. `check_command_catalog.py`
does **not** exist and must be authored (AC-2.8).

### Parser contract

Every case below is a declared, distinguishable error unless stated otherwise — never a silent
default, never a partial parse.

- Values split on the **first** colon; later colons are part of the value.
- A trailing `\r` is stripped from every line before parsing. This repo has documented LF→CRLF drift
  from editing on Windows, and a naive parse would turn `latest-eligible: true\r` into a value that
  is not `true`, silently dropping `ca`'s Latest badge — exactly the silent-default failure the
  loud-failure criteria exist to forbid.
- Booleans are exactly `true` or `false`; any other value errors.
- A duplicate scalar key within a block errors. Keys that are lists (`manifest`, `artifacts`,
  `pre-tag`, `payload-exclude`) repeat by design and preserve order.
- A duplicate `[target]` block errors.
- An unknown key errors, so a typo (`latest-eligibile:`) cannot silently drop a setting.
- More than one delimiter block in the file errors.
- A value containing the literal closing delimiter errors, rather than truncating the block under
  non-greedy matching as `_scopelib.py:48` would.
- The `[target]` header grammar is covered by the generic malformed-block error: an empty `[]`, a
  header carrying characters outside `[A-Za-z0-9._-]`, and any key appearing before the first header
  all error rather than being skipped.

## Acceptance criteria

Grouped by slice; each is one `tdd` Phase 1 obligation and individually testable.

### Slice 1 — mechanism ships, data loads, this repo proven unchanged

1.1 `core/pysrc/_releaselib.py` exists and `python tools/sync-core.py --check` passes with it in the
    generated set.
1.2 The mechanism contains no literal from this repo's namespace or CI vocabulary — a denylist over
    `[REPO]`, `ca-pi`, `ca-codex`, `ca-sandbox`, `plugins/`, and the tag-prefix constants.
1.3 Repo-specific defaults become required parameters: `classify_merge_readiness` takes the check
    name, `last_tag_select` takes the prefix, and `select_release_target` takes the target list —
    none with a default, so no module-global survives to detonate at slice 4.
1.4 `load_targets(path)` returns rows carrying `target`, `prefix`, `manifest[]`, `changelog`,
    `payload`, `payload_exclude[]`, `rebuild`, `artifacts[]`, `provenance_manifest`, `pre_tag[]`,
    `latest_eligible`, stdlib only.
1.5 An **absent** block raises a distinguishable declared error.
1.6 Each parser-contract violation raises its own distinguishable declared error: malformed block
    (including a bad `[target]` header), non-boolean boolean, duplicate scalar key, duplicate target
    block, unknown key, multiple delimiter blocks, delimiter-in-value. A missing required key errors
    too, rather than silently defaulting. *(Rev 4.2: an earlier draft listed "CRLF-bearing boolean"
    among the violations. That is the opposite — `latest-eligible: true\r` must parse cleanly to
    `True`. It is a positive case and is asserted as one.)*

    **A dedicated CR-stripping pass is dead code.** Every line is independently `.strip()`-ed and
    Python's `str.strip()` already removes `\r`, so a separate pass can be deleted with the CRLF
    test still green. Do not reintroduce one.

    *(Rev 4.3 correction: an earlier revision of this note also claimed "a single-point mutant
    cannot kill the CRLF test." That is false and was written in from an unverified report. Measured,
    removing `raw_line.strip()` alone DOES kill it — and for an incidental reason: with CRLF input
    the extracted block's first line is a bare `\r`, which unstripped becomes a spurious key line and
    raises `MalformedBlockError` before the boolean assertion is reached. The other two strip points
    do survive individually. The CRLF property therefore needs a test that asserts the parsed boolean
    directly against a CRLF fixture, not one that passes because an earlier error path fires.)*
1.7 An **empty** block raises a distinguishable declared error.
1.8 Series isolation holds against loaded data: a fixture with `v1.0.0` and `ca-pi-v0.1.0` resolves
    each declared prefix to its own newest tag, pre-releases excluded.
1.9 *(transitional — retired by AC-4.4)* The shim re-exports the generated mechanism and still
    exposes `RELEASE_TAG_PREFIXES`; `payload_version_gate.py` imports and runs unchanged.
1.10 This repo's four rows load, and `target` and `prefix` equal the recorded pre-change constants.
1.11 **Resolution trace.** Constructed by: (a) freezing a synthetic fixture — tag list, manifest
     files, a small commit graph, the four rows; (b) implementing the pre-change pre-flight as a
     test-only script whose helper calls pin to the pre-change module via
     `git show <pre-change-sha>:.github/scripts/_releaselib.py`; (c) recording the resolved-variable
     dict (`TAG_PREFIX`, `LAST_TAG`, window commit set, manifest versions, artifact list); (d)
     asserting the new lane reproduces it. The old-lane script is validated once against the live
     repo before freezing. The trace covers **`ca` and `ca-pi`** — `ca` alone exercises neither
     `payload-exclude`, nor multiple manifests, nor the generated-root rule, which are the three
     behaviors most likely to change in migration. *Honest limit:* variables that existed only as
     prose still enter the old-lane script by transcription, so this narrows the oracle problem
     rather than eliminating it.

### Slice 2 — pre-tag execution (check-only, DECISION-0034)

2.1 Declared commands execute in declared order.
2.2 A non-zero exit from any pre-tag command blocks the release.
2.3 A pre-tag command that leaves the tree dirty blocks the release; the assertion is unconditional
    with no per-row opt-out. It is evaluated **before** any `rebuild` runs, so a rebuild's legitimate
    bundle rewrite is never attributed to a pre-tag command.
2.4 A `pre-tag` entry exceeding 1024 characters is rejected, per ADR-0002's precedent.
2.5 `security-controls.md` carries a boundary-crossings entry naming `release-targets.md` as
    operator-authored executable input.
2.6 **A new protected-write class** admits mutations of `release-targets.md` only under a fresh
    authoring marker **of its own**, on the H-11 pattern (`decision-lifecycle/SKILL.md:37,55` — mint
    immediately before the write, `rm -f` at lane exit; `marker_fresh` is a 30-minute mtime window).
    Reusing `adr-authoring-active` is wrong in both directions: an `/adr` session could write rows,
    and a row edit would arm ADR authoring. Every existing class is unusable — `context`
    (`pre-write.py:68-90`) admits any write whose result keeps `arbiter: enabled` frontmatter, which
    this file does not have, so every write would block; `marker` blocks outright; `audit` is
    append-only; `decisions` requires a marker only `/adr` mints. **The class registers on all three
    flanks**, with CONTEXT.md's guards as the template: `pre-write.py`, `pre-edit.py`'s per-class
    `classify_protected` dispatch, and a `_bashguardlib` redirect/write-verb pair mirroring
    `CONTEXT_REDIRECT_RE` / `CONTEXT_WRITE_RE` (lines 355-356, checked at 1011). Sanctioned minters:
    `context-creation`, the back-fill lane, and `/ca:release`'s own row-edit path.
2.7 **Four-case flank test:** a Write blocks, an Edit blocks, a shell redirect and a `sed -i`-class
    write verb block, and the AC-5.4 marker-fresh back-fill write succeeds. Testing the Write door
    alone passes while `echo 'pre-tag: ...' >> .codearbiter/release-targets.md` still plants a
    command the release lane later executes — which is the whole attack the class exists to price up.
2.8 `check_command_catalog.py` exists and asserts, without mutating, that the canonical catalog
    enumerates exactly the command files and that the README table lists every one.
2.9 This repo's declared rows execute end-to-end green on a clean, reconciled tree — the criterion
    that stops slice 2 passing on fixtures while the first real release blocks.
2.10 A change to a row's `pre-tag` content hash forces re-confirmation before the next execution. The
     hash is minted by a sanctioned Python producer, since H-19 (`pre-write.py:63`) blocks Write-tool
     writes under `.markers/`. Re-confirmation is cooperative-grade per ADR-0010, which the new ADR
     states rather than implies.

### Slice 3 — schema completeness and consumer viability

3.1 A row declaring a manifest asserts version equality and BLOCKs on mismatch.
3.2 A row declaring no manifest proceeds with the derived tag as version source, no assertion.
3.3 A declared `rebuild` runs and every `artifacts` entry is asserted clean afterward; a stale bundle
    blocks. A nondeterministic bundler makes this permanently blocking, which is acceptable since
    `rebuild` is optional — but the block report must name that as the cause.
3.4 `payload-exclude` entries are excluded from the commit window, verified against `ca-pi`'s
    `tools/` exclusion.
3.5 `provenance-manifest` is optional; when absent the tag-provenance recording step is skipped and
    the report says so explicitly.
3.6 Interpreter resolution succeeds where `python3` is absent but `python` is present, matching the
    hook layer's existing fallback.

### Slice 4 — CI reads the declared source

4.1 `payload_version_gate.py` derives prefixes from the declared file; no tag-prefix literal remains.
4.2 Target selection is **name-keyed**: each confirmation input carries its target name, and
    selection never depends on row order.
4.3 A workflow-contract test fails when the declared target set and the workflow's inputs disagree by
    name.
4.4 The data constants are removed from the shim, the shim survives as CI's entry point loading data
    from the declared file, all six shell-out sites and `payload_version_gate.py` still pass, and
    AC-1.9's transitional test is retired in the same commit.

### Slice 5 — onboarding and back-fill

5.1 `decompose` elicits intent only — tag prefix, whether a changelog is kept — and writes no row it
    cannot substantiate, since it runs before any manifest or tag exists.
5.2 `context-creation` scouts candidate manifests and changelogs and writes a file that
    `load_targets` accepts; the assertion is on the **written file's validity**, not skill prose.
5.3 With no declared file, the back-fill presents a detected shape and does not proceed without
    explicit confirmation.
5.4 On confirmation the back-fill persists the file, and a second run reads it rather than
    re-detecting.
5.5 First release after adoption: with `LAST_TAG=<none>`, the lane offers a changelog baseline at the
    adoption commit instead of BLOCKing once per pre-adoption commit missing a `CHANGELOG:` footer.
5.6 `.codearbiter/.provenance/release-targets.json` records the rows' **own referenced paths**
    (`manifest`, `changelog`, each `artifacts` entry) as drift triggers. A CONTEXT.md-Scope trigger is
    explicitly not used: `_provenancelib.compute_drift` compares whole-file git oids with no
    section-level machinery, so it would fire on a `stage:` flip and stay silent when a manifest path
    moves. Routine per-release version bumps **will** trip these triggers by design; `heal_worklist`
    auto-heals them in the same release commit, and the spec records this so a later maintainer does
    not delete the triggers to quiet the noise.

### Slice 6 — surfaces agree

6.0 **The release skill itself resolves its targets from the declared file.** Its Targets table is
    replaced by `load_targets`, its helper invocations resolve under `${CLAUDE_PLUGIN_ROOT}`, its
    Phase-3 tag-provenance step reads the `provenance-manifest` row field, and its hosted-lane and
    immutability prose are conditional on what the consumer's repo actually has. *(Added rev 4.1 — a
    review of the plan found that no criterion required rewriting the skill, so a task set could
    prove bijective coverage while the campaign's central deliverable was missing.)*
6.1 A guard scans `core/surface/skills/**` and fails on any reference naming a **this-repo path the
    skill executes or reads**, permitting `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PROJECT_DIR}`
    prefixes and permitting repo-path *patterns* inside scout scan-target lists. The guard states its
    matching rule in its own docstring.
6.2 `subagent-driven-development`'s reference resolves as `${CLAUDE_PLUGIN_ROOT}/tools/farm.js`.
6.3 `decision-lifecycle`'s line is **reworded to a conditional CI reference** rather than naming a
    script the skill executes, since `check_adr_identity.py` is CI-only and is not shipped.
6.4 `commands/release.md` documents the same arguments and phase numbering as the skill.
6.5 The docs-site release guide distinguishes the general lane from this repo's configuration.
6.6 **Portability is proven in a clean consumer repo, not asserted.** A scratch git repo containing a
    single `package.json`, a `CHANGELOG.md`, one `v*` tag, and an installed codeArbiter — with **no
    file from this repository present** — runs `/ca:release` through target resolution, window
    derivation, bump classification, and changelog rolling. *(Added rev 4.1: #563's acceptance carried
    this as a checkbox but no numbered criterion existed, so no task covered it. Verifying against
    this repo's own hand-built state is the documented way consumer-facing bugs stay hidden.)*
6.7 **This repo still releases.** After the migration, `/ca:release ca` reaches a composed tag on a
    scratch branch with the same version the pre-change lane would have derived, and the tag is
    discarded rather than published.

## Decisions on record

- **DECISION-0034** (supersedes 0033) — pre-tag commands are declared per row and check-only; no
  assert-clean flag. Reconciliation is a separate operator action through `commit-gate`.
- Declaration home is a separate `.codearbiter/release-targets.md` rather than a `CONTEXT.md` block,
  on **context economy**: `CONTEXT.md` is read every session, release config only when tagging. The
  write guard is recovered explicitly by AC-2.6 and relevance by JIT enrolment.
- `context-creation` owns full elicitation; `decompose` owns intent only; release-time detection is
  back-fill.

## Splitting

Three parts are separable and should be planned as their own clusters rather than interleaved with
the release slices.

**The protected-write class (AC-2.6, 2.7) is the significant one, and it is not release machinery.**
It touches three hook flanks that run on every session in every consumer repo, so its blast radius is
far wider than this lane. It is also the first instance of a pattern the project is heading toward
deliberately: more project-state files that are **written by helpers rather than by inference**, with
a guard making the helper the only path. `_taskboardlib`'s `next_seq` / `add_entry` / `set_state`
already supply the helper half for `open-tasks.md`; what is missing is the guard.

It therefore MUST be designed as **generic marker-gated project-state machinery** parameterized over
a registry of protected files, never as a `release-targets.md` special case. `release-targets.md` is
its first consumer, not its reason. A one-off implementation here would have to be torn out the first
time `open-tasks.md` adopts it.

**AC-6.5 (docs-site guide)** has no code coupling to any slice and carries its own verification
regime (`npm test` over the generator suites), so it belongs in a docs lane.

**AC-3.6 (interpreter fallback)** likely generalizes to any skill that shells `python3`. Keep it here,
but if implementation reveals a shared convention change, split it rather than widening this campaign
silently.

## Open questions

None blocking. **D-6** is narrowed: the `provenance-manifest` field now exists, so the portable lane
is coherent without relocating the file. Deferred is only whether this repo's copy physically moves
from `.github/` to `.codearbiter/`.

## Review provenance

Two adversarial passes. Pass 1 found the rev-1 criteria set unsatisfiable, the MVP slice ordering
CI-breaking, the drift trigger decorative, the golden test's oracle circular, the positional
`select-target` a reorder-to-mispublish hazard, and corrected the contamination measurement. Pass 2
verified 11 of 15 repairs sound and found four defects, two introduced by the repairs themselves:
AC-2.6 was specified against a false model of the protected-write machinery and would have blocked
the very onboarding writes it sits beside, and the migration invariant contradicted AC-4.4 while
shim removal would have broken six CI call sites uncovered by any criterion. Both are fixed above.
