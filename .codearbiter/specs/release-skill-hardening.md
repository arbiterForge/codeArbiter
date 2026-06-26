# Spec — release-skill hardening (v2.release.0002–0006)

Status: **APPROVED (brainstorming Phase 4 gate) — 2026-06-26, user (brennonhuff@gmail.com)**
Source: release-skill red-team 2026-06-23 → board tasks v2.release.0002–0006.
Branch: `feat/release-skill-hardening` (carries the `v2.prune.0001` board edit as a passenger, per user).

## Problem

`plugins/ca/skills/release/SKILL.md` is the single permitted path to a version tag, but five
red-team findings show load-bearing steps that are prose-only and can fail silently: an artifact
freshness check that only fires conditionally, a publish path that dead-ends when half-finished, a
release date typed three times by the model, a notes-file whose heading is never checked against the
tag, and an unverified pre-release-exclusion filter. The caller is the maintainer running
`/ca:release`; "done" is that each of these five steps has a mechanical backstop (a tested helper or
a structural assertion) so a model lapse can't ship a wrong or half-published release.

## Scope

**In:**
- Edits to `plugins/ca/skills/release/SKILL.md` (prose hardening of Pre-flight / Phase 2 / Phase 3).
- A new stdlib-only Python helper `.github/scripts/_releaselib.py` + `.github/scripts/test_release_lib.py`,
  following the established `_previewlib`/`_metricslib`/`_taskboardlib` lib+test pattern.
- Registration of `test_release_lib.py` in `.codearbiter/tech-stack.md` (Test section) and
  `.github/workflows/ci.yml` so it runs in CI parity.

**Out of scope (boundary):**
- The **ca-sandbox release path and `sandbox.js` freshness** — explicitly handed to
  `casandbox.release.0001` (Option B). `/ca:release` stays ca-only per ADR-0007; this spec touches
  `farm.js` only.
- `v2.release.0001` (tone pass + marketplace publication).
- No change to the SemVer **bump-derivation** logic, the changelog **format**, the two-plugin tag
  scoping, or the **publication-authorization** model (Phase 3 still requires explicit user
  authorization).
- No end-to-end release **integration** test — guards are unit-level; the skill prose remains the
  orchestration.

## Design decision (confirm at approval) — mechanization level

Per finding, "mechanical tested helper" vs "skill-prose + structural test." Recommended split:

| Finding | Sev | Mechanization | Why |
|---|---|---|---|
| 0006 beta-exclusion | LOW | tested helper `last_tag_select` | pure list→tag logic, trivially unit-testable; also pins the ca-only baseline |
| 0005 notes-heading↔tag | LOW | tested helper `notes_heading_matches` | pure text check; clean guard before `gh release create` |
| 0004 deterministic date | MED | tested helper `release_dates_consistent` + derive-once prose | post-hoc consistency assert is stronger than structural |
| 0003 half-finished-publish | MED | tested helper `classify_publish_state` + prose rewrite | the genuinely complex one; a classifier makes the branch decision testable |
| 0002 unconditional freshness | MED | **prose + structural test only** | the unconditional mechanical enforcement already exists: CI's `tools` job rebuilds `farm.js` + `git diff --quiet` on **every** `plugins/ca/**`-touching PR (ci.yml gate `ca == true`, not a `farm.ts` trigger), and a release necessarily touches the payload. A new guard would duplicate CI. The real defect is the skill's pre-flight *prose*, which conditions the local rebuild on an in-window `farm.ts` diff — misleading, and lets a maintainer skip the local belt. Fix the prose; point it at CI as the backstop |

**Decision (settled 2026-06-26, user):** Option 1. 0002 stays a prose-truth fix + structural test —
a real guard (Option 2/3) was rejected as duplicating the CI `tools` job, which already enforces
`farm.js` freshness unconditionally on every ca-touching PR. The other four findings have no CI
coverage (release-time logic), so their tested helpers stand.

## Acceptance criteria

Each criterion maps to exactly one `tdd` Phase 1 obligation / one test.

1. **AC-1 (0006).** `_releaselib.last_tag_select(tags)` returns the highest **ca** SemVer tag,
   excluding pre-releases (`-beta`/`-rc`/`-alpha`) and every `ca-sandbox-v*` tag; returns the
   `<none>` sentinel when no ca tag matches. Test: `["v2.5.0","v2.5.1","v2.6.0-beta.1","ca-sandbox-v0.1.0"]`
   → `"v2.5.1"`; `["ca-sandbox-v0.1.0","v2.7.0-rc.1"]` → `<none>`. The skill Pre-flight invokes this
   helper as the single source of truth for `LAST_TAG` (replacing the inline grep one-liner).
2. **AC-2 (0005).** `_releaselib.notes_heading_matches(notes_text, tag)` is `True` iff the notes'
   first `## vX.Y.Z` heading equals `tag`. Test: matching section → `True`; a `## v2.5.0` section
   against tag `v2.6.0` → `False`. Skill Phase 3 calls it before `gh release create` and STOPs on
   `False`.
3. **AC-3 (0004).** `_releaselib.release_dates_consistent(changelog_section, tag_message)` is `True`
   iff the `## vX.Y.Z — YYYY-MM-DD` date equals the `Released-at: YYYY-MM-DD` footer date. Test:
   equal → `True`; differing → `False`; missing either → `False`. Skill derives the date **once**
   (`date +%F`) in Phase 1 and reuses it in the tag footer and the Release; a structural assertion
   confirms the skill no longer instructs a second hand-typed date.
4. **AC-4 (0003).** `_releaselib.classify_publish_state(tag_exists, tag_sha, head_sha, tag_version,
   manifest_version, release_is_nondraft)` returns exactly one of
   `{"publish_fresh","resume_publish","already_published","abort_mismatch"}`:
   no tag → `publish_fresh`; tag at HEAD **and** `tag_version == manifest_version` **and** no
   non-draft Release → `resume_publish`; a non-draft Release already on the tag → `already_published`;
   tag pointing at a non-HEAD commit **or** version mismatch → `abort_mismatch`. Test: one case per
   branch. Skill Phase 2/3 branches on this instead of the flat "tag exists → STOP."
5. **AC-5 (0002).** The release SKILL.md Pre-flight rebuilds `plugins/ca/tools/farm.js` and asserts
   `git diff --quiet -- plugins/ca/tools/farm.js` **unconditionally** — not gated behind an in-window
   `git log LAST_TAG..HEAD -- …farm.ts` diff — scoped to `ca` only (no `sandbox.js`), and **names the
   CI `tools` job as the mechanical backstop** so the local check is explicitly belt-to-CI's-suspenders,
   not a standalone gate. Test (structural, `test_release_lib.py`): the Pre-flight section contains the
   unconditional rebuild + diff instruction, contains no `farm.ts`-conditional guarding that rebuild,
   and references the CI freshness job.
6. **AC-6 (wiring).** `test_release_lib.py` is listed in `.codearbiter/tech-stack.md` (Test section)
   and added to the CI test matrix in `.github/workflows/ci.yml`, and the suite passes green. Test:
   the registration strings are present and `python .github/scripts/test_release_lib.py` exits 0.

## Open questions

None blocking. (The 0002 mechanization level above is a recommendation to confirm at approval, not a
`[CONFIRM-NN]` — either answer ships a testable AC-5.)

## Notes / harvest

- `sandbox.js` freshness raised by 0002 is routed to the existing `casandbox.release.0001` task, not
  re-triaged here.
