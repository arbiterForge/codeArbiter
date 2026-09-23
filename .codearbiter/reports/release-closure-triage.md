# Release-contract closure — issue triage (T-01)

**Scope:** every distinct finding across #570 (issue body + all ten comments — see
"Provenance and methodology" below), #623, #626, #627. Each finding gets one line and
exactly one disposition: `fixed-here` (cites the plan task/AC that will close it),
`already-fixed-elsewhere` (cites a commit hash, personally spot-checked with
`git show <hash> --stat` and `git merge-base --is-ancestor <hash> HEAD`), or
`explicitly-deferred` (out of this sprint's bounded scope per the spec's Problem/Scope
sections, or not named by any AC-01..AC-18).

This report does not implement anything. It is read by T-24 (final disposition
reconciliation) and by the human reviewer.

## Provenance and methodology

**#570's round count.** The issue has one body (the "third blind agent-judgment
exercise" — run 3) and ten comments: Run 4, Run 5, Run 6, Run 7, Run 8, a "priority
note" (meta-commentary, not a new run), Run 9, Run 10, Run 11, and Run 13. Runs 1 and 2
are not represented here (their findings were fixed and closed under #563 before this
issue existed). Run 12 has no comment of its own on #570 — its one finding
(`classify_publish_state` not catching a partial multi-manifest bump on the
fresh-publish path) survives only as an inline citation inside
`core/surface/skills/release/SKILL.md`'s own prose ("Correction (HIGH, adversarial
review 2026-07-31, run 12)"). It is enumerated below as `570-R12-01` for
completeness, sourced from that inline citation rather than a comment. Runs 14 and
above belong to different issues (#576, #579, #623) and are out of #570's own
enumeration, though where SKILL.md's current text cites them I've noted it as context.

**A load-bearing discovery, not a nit.** Every commit hash the #570 comments cite as
"fixed in `<hash>`" for runs 4–11 (`fd3d8d6`, `02caf16`, `91c36b7`, `c46090d`,
`f870652`, `eb94af1`, `26ad016`) is a real object — `git cat-file -t <hash>` returns
`commit` and `git show <hash> --stat` returns a genuine, on-topic diff for every one of
them — but **none of them is an ancestor of the current `HEAD`**
(`git merge-base --is-ancestor <hash> HEAD` returns false for all seven), and
`git branch -a --contains <hash>` returns empty for each: the objects are not the tip
of, or contained in, any local or remote-tracking branch in this worktree. They are
loose/unreachable-from-any-ref commit objects, not commits living on some other branch
I simply didn't check.

Their content is not lost, though: `git log -S` on distinctive phrases unique to each of
these commits' bodies and diffs (`"stop destroying tag messages"`,
`"derive the commit window instead"`, `semver-greater`, `adoption-commit`,
`"never runs again for this project"`, `"Home for the composed section"`, `"run 12"`)
resolves to a single commit that **is** reachable from `HEAD`:
`8ee5fe119ebdd1b1957e20603e22220e8d7fa4c2` ("feat(release): a portable release fixture
and the protected-state machinery it needs (#563, #564) (#576)", 2026-08-01, one PR
merged the morning after Run 13 closed the campaign). The most plausible explanation is
a history rewrite (rebase/force-push) before that PR merged, which would squash the
seven individually-cited commits into one PR commit and leave their original hashes as
unreachable loose objects — but that is an inference from the pickaxe results and the
unreachability check, not something I directly observed (e.g. no reflog entry naming
the rewrite was checked). What is directly verified, and is what matters for this
report's citation requirement, is narrower and load-bearing on its own: the *content*
each issue comment attributes to its cited hash is present, verbatim in several cases,
in `8ee5fe11`'s commit message and diff, and `8ee5fe11` **is** reachable from `HEAD`.
Where a #570 finding's fix is attributed below to one of those seven short hashes per
the issue comment, the citation records **`8ee5fe11` as the actual fixed-commit on
`main`**, with the originally-cited hash noted for provenance only — citing the
unreachable hash alone would not be verifiable against this repository's real history.

Two later, independently-reachable commits close out several more items:
`53c788cd82ddbb50c50d657775edf5a01f10dc9e` (2026-08-04, "close the blind-run 16-18
gaps") and `b5eda09df8ad86578942dba7708d945bbdbb7774` (2026-08-06, "resolve a POSIX
shell for run-pre-tag on Windows (#622)") — both confirmed ancestors of `HEAD`.
`e3c6a9b2ac1221eabb1b0ceabefdcaf16c07fbbc` (2026-08-06, "re-adjudicate #578/#579
deferred findings from PR #576 (#629)") and `267b51bfe19aee78f2677abdc1cf3dbd73845802`
(2026-09-13) close two more; both confirmed ancestors.

Findings not resolved by any of the above were checked directly against current source
(`core/pysrc/_releaselib.py`, `core/pysrc/releasehash.py`,
`core/surface/skills/release/SKILL.md`, `core/surface/commands/release.md`,
`.github/scripts/_releaselib.py`, `.github/scripts/payload_version_gate.py`) via `Read`
and `Grep`, not assumed from a stale comment.

---

## #570 — release skill: two remote-blind states, and an ancestry-blind baseline

### Issue body (Run 3)

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-BODY-01 | `release_nondraft`'s only source is `gh release view`; a no-remote consumer gets the same non-zero exit for "no remote" and "no such release," and the skill has no path forward for a local-only consumer in the `resume_publish`/`already_published` branch. | explicitly-deferred | Spec Problem/Scope: one of the two named "remote-dependent #570 states"; explicitly excluded from AC-01–AC-18, gets its own acknowledged-deferred line per spec §"Out of scope." |
| 570-BODY-02 | `--latest` eligibility's second condition (newest across every declared series, via `gh release list`) is unevaluable with no remote — a row can declare `latest-eligible: true` while the skill has no way to check the second half of the rule. | explicitly-deferred | Spec Problem/Scope: the second named remote-dependent state; same carve-out as above. |
| 570-BODY-03 | `last_tag_select()` resolves by highest-SemVer scan only, no `git merge-base --is-ancestor` reachability check — a sibling branch that diverged before the newest tag still resolves that tag as `LAST_TAG`, corrupting the derived base version. | fixed-here | AC-09 / T-10, T-11. Confirmed still reproducing: `core/pysrc/_releaselib.py:630` `last_tag_select()` is a pure numeric-max scan with no ancestry check (read directly, 2026-09-21). Spec's Phase-1 revalidation names this the still-open item. |
| 570-BODY-04a | Back-fill's proposed row name (`app`) comes from module constant `_BACKFILL_DEFAULT_TARGET`, never from the consumer's own `package.json`/manifest. | explicitly-deferred | Spec Problem/Scope + explicit carve-out: "back-fill's hardcoded `app` display name / `prefix: v`." Confirmed still present: `core/pysrc/_releaselib.py:2265` `_BACKFILL_DEFAULT_TARGET = "app"`, used at line 2302. |
| 570-BODY-04b | Back-fill requires explicit confirmation before writing the declared row, so it cannot complete unattended by construction — correct for an interactive operator, but there is no automation path through first-time target declaration. | explicitly-deferred | Spec Out-of-scope: "unattended first-time target authorization." Deliberate design, not a defect; no AC touches it. |
| 570-BODY-05 | (LOW) `TAG_PREFIX=$(...)` capture in the prose has no exit-code check; on failure the lane silently derives `0.0.0`. Caveated by the issue itself as unreachable if the agent follows the STOP rules — an exposure in the written form, not a reachable defect. | explicitly-deferred | Not named by any AC; not part of AC-13/14's Phase-2 restructure scope (this is Phase 1 prose). Out of bounded scope. |

### Run 4 (comment 1, 2026-07-31)

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R4-01 | HIGH: `git tag`'s default `strip` cleanup mode deletes every `#`-prefixed line, destroying a Keep-a-Changelog-composed tag message (cross-ref #569; had already happened to a published tag). | already-fixed-elsewhere | `8ee5fe11` (methodology note above; originally landed as `fd3d8d6`, confirmed via `git show fd3d8d6 --stat`). Current `SKILL.md:338` shows `--cleanup=verbatim` is now used, with the fix's rationale inline. |
| 570-R4-02 | HIGH: `<release_nondraft>` took the raw `gh release view --json isDraft --jq` output with its polarity inverted. | already-fixed-elsewhere | `8ee5fe11` (originally `fd3d8d6`). Current `SKILL.md:338` documents the corrected polarity inline ("HIGH, run 4"). |
| 570-R4-03 | Back-fill's row name/prefix not derived from the consumer; a series like `release-1.2.0` still gets `prefix: v`, silently deriving a version below the manifest's own. | explicitly-deferred | Same carve-out as 570-BODY-04a (hardcoded name/prefix). |
| 570-R4-04 | `detect_candidate_target` accepts `target=`/`prefix=` kwargs but the CLI's one optional positional is the scan root, not the target name — no way to override the hardcoded default via CLI. | explicitly-deferred | Sub-detail of the hardcoded-name carve-out; no AC covers exposing these kwargs. |
| 570-R4-05 | `LAST_TAG=<none>` is a literal sentinel string substituted directly into `git log LAST_TAG..HEAD`, which is `fatal: bad revision`. | already-fixed-elsewhere | `8ee5fe11` (originally `02caf16`, confirmed via `git show 02caf16 --stat`; formally re-rated HIGH in Run 5's comment). Current `SKILL.md:194`: `$WINDOW` is derived (`if [ "$LAST_TAG" = "<none>" ]; then WINDOW=HEAD; ...`) before any command consumes it. |
| 570-R4-06 | Back-fill sits before the branch check in file order (Targets → Back-fill → Pre-flight); an operator on `main` with no declared file is told to commit there, then stopped afterward for being on `main`. | fixed-here | AC-11 / T-13. Confirmed still present: `SKILL.md:141` still routes Back-fill's declaration commit through `commit-gate` "on the current branch" ahead of Pre-flight's branch check (`SKILL.md:174`) — this is exactly what T-13 ("branch refusal happens before the declaration write") targets. |
| 570-R4-07 | "This lane never runs again for this project" is branch-scoped, not project-scoped — `release-targets.md` is a tracked file, so a branch created before the declaration commit still triggers Back-fill. | fixed-here | AC-11 / T-13. Confirmed still present verbatim: `SKILL.md:142` — "this back-fill lane never runs again for this project." The phrase was introduced (unfixed) by `8ee5fe11` itself and has not been corrected since (`git log -S "never runs again for this project"` returns only `8ee5fe11`). |
| 570-R4-08 | Back-fill routes its declaration commit through `commit-gate`, which reads `.codearbiter/` state a release-only consumer deliberately doesn't have; both exercising agents substituted a plain `git commit`. | explicitly-deferred | Floor item: the commit-gate-required-in-a-fresh-consumer tension. Spec Out-of-scope: "an alternate commit-gate." Cross-ref: AC-10/T-12 mitigates the write-before-refusal facet (fail before any tracked-file write when commit-gate prerequisites are unmet) but does not resolve the underlying requirement that `commit-gate` exist. Confirmed still required: `SKILL.md:141`. |
| 570-R4-09 | Two-scratch-file ambiguity: Phase 1 step 5's scratch file vs. Phase 2's `<message-file>` vs. Phase 3's notes file — one file mutated in place, or two? Invisible to every guard. | already-fixed-elsewhere | `8ee5fe11` (`git log -S "Home for the composed section"` resolves only to `8ee5fe11`). Current `SKILL.md:220` names one scratch file explicitly, states it is discarded after Phase 3, and that Phase 3 reconstructs the text mechanically from `$CHANGELOG` rather than depending on the scratch file surviving. |
| 570-R4-10 | `notes-match` raises a raw `UnicodeDecodeError` on a non-UTF-8 notes file rather than refusing cleanly; the skill's own prescribed heading contains an em dash. | already-fixed-elsewhere | `core/pysrc/_releaselib.py` now catches `UnicodeDecodeError` explicitly in three places (lines 930, 940, 946) and reads subprocess output with `encoding="utf-8", errors="replace"` (lines 870, 904). Confirmed present in current source, 2026-09-21. |

### Run 5 (comment 2, 2026-07-31)

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R5-01 | HIGH (re-rated from Run 4's MEDIUM): `<none>` sentinel breaks `git log <none>..HEAD`, and this hits every back-filled project's first release by construction. | already-fixed-elsewhere | Same as 570-R4-05 — `8ee5fe11` (originally `02caf16`). |
| 570-R5-02 | Unquoted empty `<tag_sha>` vanishes rather than becoming an empty positional, shifting `classify`'s five remaining args left and causing exit 2 on the ordinary fresh-publish path. | already-fixed-elsewhere | `8ee5fe11` (originally `02caf16`). Current `SKILL.md:338` explicitly instructs `"$TAG_SHA"`, always quoted, with the rationale inline. |
| 570-R5-03 | `<manifest_version>` named no extraction command — `jq`, `grep`, and a JSON parser could each return something different on a nested manifest. | already-fixed-elsewhere | `8ee5fe11` (originally `02caf16`). Current `SKILL.md:338` names format-specific extraction commands (JSON via `json.load`, TOML via `tomllib`). |
| 570-R5-04 | The tag round-trip check read `%(contents)`, a reconstruction that appends a trailing newline and cannot detect a byte-level difference even in principle. | already-fixed-elsewhere | `8ee5fe11` (originally `02caf16`). Current `SKILL.md:338` uses `git cat-file tag` against the raw tag object instead. |
| 570-R5-05 | (LOW) Phase 1 step 5 prescribes `## [X.Y.Z] — DATE` with an em dash while citing "the Keep-a-Changelog bracket heading," which uses ` - `; harmless to the guards (regex accepts either) but inconsistent within one file. | explicitly-deferred | Not named by any AC; a style nit, not a behavioral gap. Confirmed still present: `SKILL.md:220` still composes `## [${VERSION}] — $RELEASE_DATE` with an em dash. Consolidated with 570-R8-LOW-2 / 570-R13-LOW-3 below (same root cause). |

### Run 6 (comment 3, 2026-07-31)

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R6-01 | HIGH: a never-tagged manifest floor — a project shipped `1.4.2` without ever tagging in its series, `LAST_TAG=<none>` took `0.0.0` as the base, and the bump wrote `0.1.0` over the manifest, walking the version backward with every gate passing. | already-fixed-elsewhere | `8ee5fe11` (originally `91c36b7`, confirmed via `git show 91c36b7 --stat`). Current `SKILL.md:179,191` floors `$BASE_VERSION` on the maximum of `LAST_TAG` and every declared manifest's version. |
| 570-R6-02 | Missing `semver-greater` tool — version-floor arithmetic the hard rules say must never be guessed had no command. | already-fixed-elsewhere | `8ee5fe11` (originally `91c36b7`, whose diff adds the `semver-greater` CLI subcommand directly — confirmed in `git show 91c36b7 -- core/pysrc/_releaselib.py`). Present in current source as `version-greater` (`_releaselib.py:3544` retains `semver-greater` compatibility; `SKILL.md:219` documents `version-greater` as "the policy-general replacement for the legacy `semver-greater`"). |
| 570-R6-03 | `dates-match` absent from the CLI's own usage banner. | already-fixed-elsewhere | `8ee5fe11` (originally `91c36b7`). Current `_releaselib.py:2755` usage string enumerates `dates-match` alongside the other subcommands. |
| 570-R6-04 | Factual error in the skill's own rationale: `git show-ref --tags -d` exits 1 with zero tags, not 0 as claimed. | already-fixed-elsewhere | `8ee5fe11` (originally `91c36b7`). Current `SKILL.md:339` ("Zero-tag correction") explicitly handles exit 1 as the expected zero-tag state, distinct from any other nonzero exit. |
| 570-R6-05 | `latest-eligible` uniqueness is prose-only — a declared file with two rows both `latest-eligible: true` parses fine; nothing but agent memory of the prose prevents badge theft. | explicitly-deferred | Not named by any AC. Confirmed a parser-level constant exists (`_releaselib.py:1763` `_BOOLEAN_KEYS`) but no uniqueness enforcement was found across rows; this is a mechanism change with its own blast radius per the issue's own text ("filed rather than batched") and none of AC-01–AC-18 claims it. |
| 570-R6-06 | Back-fill step 3 tells you to commit on the branch Pre-flight's non-default-branch check will forbid — the direct rule conflict, distinct from mere ordering. | fixed-here | AC-11 / T-13 (same fix as 570-R4-06; this is the sharpened restatement of the same conflict). |
| 570-R6-07 | `[NEEDS-TRIAGE]` lines have a specified shape but no producer and no ordering rule; each run emitted them in a different order. | already-fixed-elsewhere | `8ee5fe11` (`git log -S "NEEDS-TRIAGE"` on `SKILL.md` shows meaningful content added at `8ee5fe11`). Current `SKILL.md:205,218` specify the producer (`classify-window`'s own printed `[NEEDS-TRIAGE] <short-sha> <subject>` lines) and the exact report shape (one line per offending commit, never collapsed). |
| 570-R6-08a | Unspecified: the release commit's own Conventional-Commits type/message. | explicitly-deferred | Not named by any AC. Confirmed still unspecified: `SKILL.md:238` (Phase 1 step 7) routes the commit through `commit-gate` without naming its type; contrast with Back-fill's declaration commit, which does name `chore:` (`SKILL.md:141`). |
| 570-R6-08b | Unspecified: the working directory `pre-tag` commands run in. | already-fixed-elsewhere | `8ee5fe11` — `git log -S "whatever directory the caller happened to be in"` on `SKILL.md` resolves only to `8ee5fe11`, directly pinning this exact fix to that commit. Current `SKILL.md:231` states `run-pre-tag` "runs every command in the project root rather than whatever directory the caller happened to be in." |
| 570-R6-09 | Nothing creates `.codearbiter/` before Back-fill's write — it works only as a side effect of the marker `mkdir -p`; an operator who skips the marker dance hits a failed write. | explicitly-deferred | Not named by any AC. Confirmed the mechanism is unchanged: `SKILL.md:131` still relies on `mkdir -p "$(git rev-parse --show-toplevel)/.codearbiter/.markers"` as the directory's only creation path. |
| 570-R6-OQ | Open design question: should a fresh project whose manifest predates its commits take `1.0.0` or `1.1.0` as its first release? | already-fixed-elsewhere | `c46090d` (content squashed into `8ee5fe11`, per the same methodology note). Spec's own "Open questions" section states this is "already resolved by a landed fix (`c46090d`) and is not reopened here" — independently confirmed via `git show c46090d --stat`. |

### Run 7 (comment 4, 2026-07-31)

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R7-01 | HIGH (caused by Run 6's own fix): a project with an existing tag derived off the tag alone, then failed its own manifest floor — a hard stop on a legitimate release. | already-fixed-elsewhere | `8ee5fe11` (originally `c46090d`, confirmed via `git show c46090d --stat`). Current `SKILL.md:179` collapses both floors into one `$BASE_VERSION` = max(tag, every manifest). |
| 570-R7-02 | MEDIUM: the unrunnable `<none>` comparison. | already-fixed-elsewhere | `8ee5fe11` (originally `c46090d`, same commit as 570-R7-01). |
| 570-R7-03 | MEDIUM: the JSON-only manifest reader raised `JSONDecodeError` on a `pyproject.toml`. | already-fixed-elsewhere | `8ee5fe11` (originally `c46090d`). Current `SKILL.md:338` names format-specific parsers (JSON, TOML). |
| 570-R7-04 | MEDIUM: unstated max-vs-first-manifest coupling — Pre-flight reads the maximum across every manifest but Phase 2 reads only the first, undocumented. | already-fixed-elsewhere | `8ee5fe11` (originally `c46090d`). Current `SKILL.md:338` states explicitly: "This reads the FIRST declared manifest, while Pre-flight's `$BASE_VERSION` reads the MAXIMUM across all of them. That difference is deliberate and is safe ONLY because step 6 bumps every declared path... which step 6 now ASSERTS mechanically." |
| 570-R7-05 | (LOW) Back-fill leaves an empty `.codearbiter/.markers/` directory — the marker file is removed, not the directory. | explicitly-deferred | Not named by any AC. Confirmed still present: `SKILL.md:131,138` still `mkdir -p` then only `rm -f` the marker file, never `rmdir`. Harmless (git ignores empty directories) per the issue's own text. |
| 570-R7-06 | (LOW) The default-branch fallback's failure is invisible to `$?` — `git symbolic-ref ... 2>/dev/null \| sed 's@^origin/@@'` prints nothing and the pipeline exits 0 because `sed`'s status is what's checked, not `git symbolic-ref`'s. | explicitly-deferred | Not named by any AC. Confirmed the same pipeline is still used verbatim: `SKILL.md:150`. Consolidated with 570-R11-05 (same fallback mechanism). |

### Run 8 (comment 5, 2026-07-31) — no HIGHs, first campaign stopping point

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R8-01 | `$BASE_VERSION` is defined as a MAXIMUM but no command computes the maximum itself — only pairwise `semver-greater` exists; on a multi-manifest row the maximum was taken by eye. | explicitly-deferred | Floor item: "the missing `semver-max` helper." Confirmed still absent: only `semver-greater` (pairwise, `_releaselib.py:3544`) exists; no `semver-max`/multi-arg maximum subcommand found. |
| 570-R8-02 | Phase 1 step 6's write side names no command for updating manifest versions, and for TOML no stdlib writer exists — `tomllib` is read-only, forcing a hand-rolled string replace, the exact "typed" edit the step's own heading forbids. | explicitly-deferred | Floor item: "the missing stdlib TOML writer for the manifest-update step." Confirmed unchanged: `SKILL.md:223` ("6a. Update the manifests. Set every path in `$MANIFEST` to the derived version...") still names no write command; spec's "No new dependencies" line rules out adding a third-party TOML writer. |
| 570-R8-03 | The first-release window (full history when `LAST_TAG=<none>`) re-publishes changelog entries already shipped under an earlier `## [X.Y.Z]` section — the prose handles the version-floor overlap but not the content overlap. | already-fixed-elsewhere | `8ee5fe11` (`git log -S "adoption-commit"` on `SKILL.md` resolves only to `8ee5fe11`). Current `SKILL.md:203` (Phase 1 step 0) floors `EFFECTIVE_WINDOW` at a confirmed adoption-commit boundary via the `adoption-commit` helper, rather than rolling the entire pre-adoption history into the new changelog section. |
| 570-R8-04 | The non-HEAD footer remedy (`git commit --amend` for HEAD, "an interactive rebase onto it" otherwise) has no non-interactive form. | explicitly-deferred | Not named by any AC. Confirmed unchanged: `SKILL.md:218` still names only the amend/rebase remedy for the currently-open footer-completeness gate. |
| 570-R8-05 | No instruction for a consumer with no test suite at all — the hard rule requires a green suite via `commit-gate`, and a plain project has neither. | explicitly-deferred | Same commit-gate-tension floor item as 570-R4-08; cross-ref AC-10/T-12 (fails before mutation, does not solve the underlying requirement). |
| 570-R8-06 | `commit-gate` required twice (Back-fill's declaration commit, Phase 1's release commit) in a lane whose stated purpose is letting a `commit-gate`-less consumer skip onboarding — the internal tension sharpened, not new. | explicitly-deferred | Same floor item as 570-R4-08/570-R8-05; consolidated, not a separate defect. |
| 570-R8-LOW-1 | `<tag_exists>` is the one `classify` argument with no emitting command (the prose only states the inference). | explicitly-deferred | Not named by any AC. Confirmed: `SKILL.md:338` still derives `<tag_exists>` from a prose-described ref-snapshot read, not a dedicated subcommand. |
| 570-R8-LOW-2 | Composed heading em dash inconsistent with the surrounding Keep-a-Changelog file's ` - ` separator. | explicitly-deferred | Same as 570-R5-05; consolidated (`SKILL.md:220` still uses an em dash). |
| 570-R8-LOW-3 | The TOML manifest reader hardcodes PEP 621 layout (`['project']['version']`); a `[tool.poetry]` manifest raises `KeyError`. | explicitly-deferred | Not named by any AC. Confirmed unchanged: `SKILL.md:338`'s TOML extraction snippet still hardcodes `['project']['version']`. Related to, but distinct from, the missing-TOML-writer floor item (this is the reader, not the writer). |

### Run 9 (comment 7, 2026-07-31) — pre-tag runner slice

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R9-01 | HIGH: the pristine-tree assertion blocked every release, because Phase 1 legitimately dirties the tree (changelog roll, manifest bump) before this step runs. | already-fixed-elsewhere | `8ee5fe11` (originally `f870652`, confirmed via `git show f870652 --stat`). Current `SKILL.md:231` uses a snapshot-and-diff assertion ("this command changed nothing NEW") instead of a pristine-tree requirement. |
| 570-R9-02 | HIGH: `run-pre-tag` executed in the inherited cwd rather than the project root. | already-fixed-elsewhere | `8ee5fe11` (originally `f870652`). Current `SKILL.md:231` states it "runs every command in the project root rather than whatever directory the caller happened to be in." |
| 570-R9-03 | `$BASE_VERSION` max-of-N has no helper, confirmed by a second independent run. | explicitly-deferred | Duplicate of 570-R8-01 (missing `semver-max`); same disposition, not a separate defect. |
| 570-R9-04 | `run-pre-tag` leaves the mutation it blocked on (exit 6) in place; the message tells the operator to revert but the command doesn't undo it itself. | already-fixed-elsewhere | Superseded/consolidated by Run 11's HIGH fix (570-R11-01, `26ad016`/`8ee5fe11`), which specifies the exact discard mechanism (`git checkout --` for pre-existing files, `rm` for lane-created ones) as the declaration-level remedy rather than an automatic revert inside the runner. |
| 570-R9-05 | Declared commands run through `cmd.exe` on Windows with no stated shell contract; a POSIX-idiom `pre-tag` command passes on Linux and fails on Windows silently. | already-fixed-elsewhere | `b5eda09df8ad86578942dba7708d945bbdbb7774` ("fix(release-lib): resolve a POSIX shell for run-pre-tag on Windows (#622)", 2026-08-06, confirmed ancestor of `HEAD`). Current `_releaselib.py` lines 1654-1722, 3438-3456 extensively document and implement POSIX-shell resolution for `shell=True` dispatch, distinguishing exit 9 ("no POSIX-compatible shell could be resolved") from exit 7. |
| 570-R9-06 | (LOW) A `pre-tag` command may write freely into gitignored paths — `git status --porcelain` excludes ignored paths, so the check-only rule is unenforced there. | explicitly-deferred | Not named by any AC. Confirmed: no `--ignored` or gitignore-aware handling found in `_releaselib.py`'s tree-state probes. Bounded risk per the issue's own text (ignored files can't reach a release). |
| 570-R9-07 | (LOW) A long-but-legal `prefix` (under the 1024-char cap) fails at `git tag` with "Filename too long" after the manifest bump is already committed. | explicitly-deferred | Not named by any AC. `VALUE_MAX_CHARS = 1024` (`_releaselib.py:542`) predates and is unrelated to git's own ref-name limit; no fix for the ordering (failure-after-commit) was found. |
| 570-R9-08 | (LOW) `ValueTooLongError` is undocumented in the module docstring the skill cites as the parser contract, and `SKILL.md` mentions no length limit at all. | partially already-fixed-elsewhere; remainder explicitly-deferred | The module-docstring half is fixed: `e3c6a9b2ac1221eabb1b0ceabefdcaf16c07fbbc` ("re-adjudicate #578/#579 deferred findings from PR #576 (#629)", 2026-08-06, confirmed ancestor) added `_releaselib.py:104` (`# ValueTooLongError — a declared value exceeds VALUE_MAX_CHARS`) to the docstring's exception enumeration. `SKILL.md` still names no length limit anywhere (confirmed via grep, no match) — that residual half is not covered by any AC, hence deferred. |
| 570-R9-09 | (LOW) Cosmetic path formatting in the parse error — mixed forward/back slashes, doubled by `repr`. | explicitly-deferred | Not named by any AC; cosmetic only, out of bounded scope. |

### Run 10 (comment 8, 2026-07-31) — pre-tag runner exercised straight through

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R10-01 | HIGH: step 7's conditional wording ("*if* the changelog edit needs to land as a commit") let a literal traversal answer "no" and tag an uncommitted tree. | already-fixed-elsewhere | `8ee5fe11` (originally `eb94af1`, confirmed via `git show eb94af1 --stat`). Current `SKILL.md:238` makes the commit unconditional ("this is not conditional"). |
| 570-R10-02 | HIGH: the mutation assertion compared porcelain *lines*, so a command mutating an already-`M` file exited 0 undetected. | already-fixed-elsewhere | `8ee5fe11` (originally `eb94af1`, same commit). Current `SKILL.md:231` describes a content-based ("changed nothing NEW") snapshot-and-diff assertion, not a line comparison. |
| 570-R10-03 | No Phase-1 step ever updates a non-manifest version surface (a badge, a catalog table) — the value such a check tracks doesn't exist until step 4 derives it, so the first pass of every release fails by construction. | already-fixed-elsewhere | `8ee5fe11` — `git log -S "would pass vacuously against the old one"` on `SKILL.md` resolves only to `8ee5fe11`, directly pinning this specific ordering rationale to that commit. Current `SKILL.md:231` (step 6d, `run-pre-tag`) runs "AFTER step 5's changelog roll and the manifest bump: a badge or catalog check compares a surface against the NEW version and would pass vacuously against the old one" — the ordering problem the finding describes is now the step's own stated rationale for its position. |
| 570-R10-04 | The exit-5 remedy commits a state where the target's own declared check is still red; if that check also runs in CI, the remedy pushes a red commit by design. | explicitly-deferred | Not named by any AC. Confirmed unaddressed: `SKILL.md:233`'s exit-5 remedy still says only "Commit the reconciliation ALONE, then re-run from Pre-flight," with no mention of the declared check's own CI status. |
| 570-R10-05 | "Discard this run's uncommitted release edits" (exit-5 remedy) names no command and no scope, and reconcile is stated before discard — a blanket `git checkout -- .` or `git reset --hard` is equally consistent with the words and would destroy the reconciliation just made. | explicitly-deferred | Not named by any AC. Confirmed: `SKILL.md:233`'s exit-5 paragraph still says only "discard this run's uncommitted release edits before starting over" without the explicit checkout/rm breakdown given to exit 6 (`SKILL.md:265`). |
| 570-R10-06 | Exit 6 has no remedy in the skill at all — exit 5 gets a full paragraph, exit 6 only a code-list entry. | already-fixed-elsewhere | Superseded by Run 11's HIGH finding and its fix — see 570-R11-01. Current `SKILL.md:265` gives exit 6 its own full remedy paragraph. |
| 570-R10-07 | Windows: a POSIX-idiom `pre-tag` command is reported as drift (exit 5) when it actually never ran under `cmd.exe`. | already-fixed-elsewhere | Duplicate of 570-R9-05; same fix, `b5eda09`. Current `SKILL.md:231` distinguishes exit 9 ("no POSIX-compatible shell resolved... NO command ran at all") from exit 5/7. |
| 570-R10-08 | `commit-gate` required at three points (Back-fill step 3, Phase 1 step 7, the exit-5 reconciliation) in a lane built for consumers that lack it. | explicitly-deferred | Same commit-gate-tension floor item as 570-R4-08; consolidated, not separate. |
| 570-R10-LOW-1 | `run-pre-tag` prints nothing for a zero-command row, so a log can't distinguish "declared none" from "ran and passed." | explicitly-deferred | Not named by any AC. Confirmed `SKILL.md:229` states a zero-command row "reports `no-commands` and exits 0, deliberately distinct from `confirmed`" for the `releasehash.py check` step, but no equivalent distinguishing print was found for `run-pre-tag` itself in step 6d. |
| 570-R10-LOW-2 | `<tag_exists>` remains the one `classify` argument with no producing command. | explicitly-deferred | Duplicate of 570-R8-LOW-1; consolidated. |

### Run 11 (comment 9, 2026-07-31) — four consumers, Pre-flight through just-before-publish

The final row in this table, `570-R12-01`, is **not** a Run 11 finding — it is Run 12's
sole finding, which has no comment of its own on #570 (see "Provenance and
methodology" above) and is placed here only because it is adjacent in read order to
Run 11's comment and Run 13's comment, not because Run 11 raised it.

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R11-01 | HIGH: the exit-6 remedy is non-terminating (reverts the very declaration causing the mutation, looping forever), destroys the just-composed changelog section, and is inexecutable on a first release (`git checkout --` on a path git has never seen). | already-fixed-elsewhere | `8ee5fe11` (originally `26ad016`, confirmed via `git show 26ad016 --stat`). Current `SKILL.md:265` names the declaration itself as the fault, requires fixing it (check-only or remove the row) before a wholesale discard, and explicitly separates exit 6 from exits 7/8. |
| 570-R11-02 | The two BLOCK-level Phase-1 checks (Conventional-Commits classification, breaking-footer scan) had no command behind them — hand-rolled, and two operators' parses of `feat!:` vs. `feat(scope)!:` vs. a bare `BREAKING CHANGE:` footer could disagree, on the single check that decides whether a release may proceed. | partially fixed-here; remainder explicitly-deferred | The classification-arithmetic half is now a tested helper (`classify-window`, confirmed at `SKILL.md:205,209`, citing this exact Run 11 finding: "Hand-rolling this parse is how it goes wrong... an exercising agent wrote `subject.split('(')[0]...`"). The remaining gap — no *per-commit* `classify` CLI subcommand, only the aggregate `classify-window` — is the floor item "the missing per-commit `classify` CLI subcommand"; `classify_commit` stays public-API-only (confirmed: no CLI dispatch for it in `_releaselib.py`'s `main()`). T-14/AC-12 reuses `classify_commit`/`classify_window` internally to *surface* breaking status in composed notes; it does not add an operator-facing per-commit CLI subcommand, so this residual half stays deferred rather than folding into AC-12. |
| 570-R11-03 | The exit-5 discard mechanism is still unnamed — same gap the exit-6 fix closed for exit 6, not restated for exit 5. | explicitly-deferred | Duplicate of 570-R10-05; consolidated. |
| 570-R11-04 | No Conventional type is specified for the commits the lane itself creates (the release commit, the exit-5 reconciliation commit). | explicitly-deferred | Same as 570-R6-08a; consolidated (Back-fill's own commit does name `chore:`, but the release/reconciliation commits still don't). |
| 570-R11-05 | Pre-flight's default-branch fallback dead-ends when unattended — `git symbolic-ref` prints nothing with no remote, and the prose then says "ask the user," with nobody to ask under autonomous invocation. | explicitly-deferred | Not named by any AC. Confirmed the exact "ask the user" fallback is still present verbatim: `SKILL.md:150`. Duplicate root cause of 570-R7-06; consolidated here. |
| 570-R11-LOW | `<tag_exists>` remains the one `classify` argument with no producing command, and the one that short-circuits three of the others. | explicitly-deferred | Duplicate of 570-R8-LOW-1; consolidated. |
| 570-R12-01 | (No #570 comment; inline SKILL.md citation only) `classify_publish_state` short-circuits on `if not tag_exists: return "publish_fresh"` before comparing manifest versions, so a partial multi-manifest bump passes unnoticed on a fresh publish (the common case) — only caught on the resume path. | already-fixed-elsewhere | `8ee5fe11` (`git log -S "run 12"` on `SKILL.md` resolves only to `8ee5fe11`). Current `SKILL.md:225` (step 6b) adds an independent, always-run `check-manifests` assertion in Phase 1 that does not depend on `classify_publish_state`'s tag-exists branching at all. |

### Run 13 (comment 10, 2026-08-01) — no HIGHs; the recorded proof; most-validated round

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 570-R13-01 | `<summary>`'s title rule has no `major` branch — a window that bumps major (not minor) falls through to the `Fixed` group's first bullet, producing a wrong release title for a breaking release. | fixed-here | AC-12 / T-15 ("prefer the first breaking entry over the existing minor/patch fallback"). This is one of the two items the spec names as still-open and load-bearing. |
| 570-R13-02 | Nothing in the composed changelog/tag/notes says "breaking" — `feat!` groups under `Added` exactly like an ordinary feature, and the `!` marker that forced the major bump is invisible in every user-facing artifact the lane produces. | fixed-here | AC-12 / T-14, T-15. Spec's Phase-1 revalidation names this explicitly: "the single most-validated item in this scope: it is what the last blind-exercise run (of thirteen) found on a clean pass." Confirmed still reproducing: current `SKILL.md:220` groups strictly by Conventional-Commits type (Added/Fixed/Performance/Changed) with no Breaking group anywhere. |
| 570-R13-03 | The per-commit classification Step 4 and Phase 2 step 2 both require has no command — `classify-window` gives only the aggregate; `classify_commit` is public API with no CLI subcommand, forcing hand-parsing as a workaround. | explicitly-deferred | Duplicate of 570-R11-02's residual half (missing per-commit `classify` CLI subcommand); consolidated, same disposition and cross-reference to T-14/AC-12. |
| 570-R13-04 | `commands/release.md` has drifted badly from `SKILL.md` — zero mentions of `release-targets`/`$TARGET`, documents `<version>`/`--auto`/`--dry-run` arguments absent from `SKILL.md`, and states `LAST_TAG` is "the newest `ca` SemVer tag... for the `ca` plugin only" (ADR-0007), a single-target design the multi-target skill replaced. | already-fixed-elsewhere | `8ee5fe119ebdd1b1957e20603e22220e8d7fa4c2` (confirmed ancestor; `git show 8ee5fe11 -- core/surface/commands/release.md` shows the exact three corrections landing same-day as Run 13: `release-targets.md` named in Flow, `[target]` replacing `<version>`/`--auto`, the ADR-0007/`ca`-only paragraph deleted). Current file (read 2026-09-21) confirms none of the three drift symptoms remain: line 12 names `release-targets.md`; line 42 states "There is no version or `--auto` argument"; no match for `ADR-0007` or "plugin only" anywhere in the file. Note: `core/surface/commands/release.md` also appears in T-12/T-13/T-15/T-19's path lists in the plan's task table, but those touches are for unrelated reasons (prerequisite refusal, back-fill ordering, breaking headline, host regeneration) — not a re-occurrence of this drift. |
| 570-R13-05 | The two writes (the changelog section insert, the manifest version write) are the only unguarded steps left in an otherwise fully guarded lane — `check-manifests` catches a wrong *version* but nothing checks the changelog insert's correctness or a regex that mangled the file's shape while landing the right string. | explicitly-deferred | Not named by any AC. This is explicitly grouped in the issue's own text with the `semver-max` and TOML-writer gaps ("together with `$BASE_VERSION`'s missing `semver-max` and the bump arithmetic, that is the remaining hand-done set") — cross-ref 570-R8-01/570-R8-02, same deferred cluster. |
| 570-R13-LOW-1 | The first-release changelog covers only the floored adoption window (2 of 9 commits in the fixture), which reads incomplete for a "first release" even though it's the defensible choice given `$ADOPTED` is the baseline. | explicitly-deferred | Not named by any AC; a documented design trade-off, not a defect. Out of bounded scope. |
| 570-R13-LOW-2 | A first release cannot ship the version its manifest already declares (the derived version must be strictly greater than `$BASE_VERSION`). | explicitly-deferred | Documented constraint, not a defect; not contradicted by AC-09 (ancestry only) or any other AC. Acknowledged, out of bounded scope. |
| 570-R13-LOW-3 | Step 5's heading template uses an em dash in the same sentence that routes entry prose through the anti-slop no-em-dash rule. | explicitly-deferred | Same as 570-R5-05/570-R8-LOW-2; consolidated (`SKILL.md:220` still uses `## [${VERSION}] — $RELEASE_DATE`). |

---

## #623 — release skill: Phase 2 step 1 is a single 1,700-word unbroken paragraph

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 623-01 | `core/surface/skills/release/SKILL.md` Phase 2 step 1 is one unbroken paragraph (originally 10,256 chars / ~1,700 words at line 240 on a since-superseded branch) that composes the tag message and covers several distinct sub-steps in prose form, with no traceability from an existing pinned literal assertion to its location. | fixed-here | AC-13, AC-14 / T-16, T-17, T-18. Confirmed the paragraph still exists and has grown, exactly as the spec's Phase-1 revalidation states ("grew slightly from unrelated intervening work; the defect is unchanged"): current `SKILL.md` Phase 2 begins at line 320, and the single unbroken numbered item "1." spans line 338 — one paragraph, thousands of characters, covering tag-message composition, `dates-match`, `<tag_exists>`/`<tag_sha>` resolution, all six `classify` arguments, `publish_fresh` tag creation, and round-trip verification. |
| 623-02 | Risk named by the issue itself: `.github/scripts/test_release_lib.py` carries pinned-phrase (`_GOVERNANCE_RULES`-style) mutation checks against this exact prose; restructuring risks silently dropping/rewording a pinned phrase (a silent contract regression disguised as a doc nit) or losing the "this sentence is the fix for finding X" traceability. | fixed-here | AC-14 / T-16 directly requires "Every retained normative obligation and affected literal assertion maps to its new instruction location and a proving test... No assertion is deleted or weakened to make the restructure pass" — this is the exact risk the issue raises, addressed by design in the plan rather than left as a residual. |

---

## #626 — release-lib CI shim: doc/API-surface gaps

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 626-01 | `.github/scripts/_releaselib.py`'s "Public API" header comment documents `select_release_target_by_name(pairs) -> str` as an importable module-level function, matching the pattern of its real siblings (`last_tag_select`, `select_release_target`, etc.) — but no such wrapper exists; the only call site is inline inside `main()`'s CLI dispatch. | fixed-here | AC-06 / T-07. Confirmed still reproducing exactly as described: `.github/scripts/_releaselib.py:87` still documents `select_release_target_by_name(pairs) -> str`; `grep -n "^def select_release_target_by_name"` returns no match; the only occurrence besides the doc comment is the inline call at line 372 inside `main()`. |
| 626-02 | `payload_version_gate.py`'s `tag_prefixes()` builds `{payload basename: tag prefix}` and silently overwrites on a basename collision between two declared rows — no diagnostic, would gate the wrong plugin under the wrong tag namespace. Currently latent (today's declared targets have distinct basenames). | fixed-here | AC-07 / T-08. Confirmed still reproducing: `.github/scripts/payload_version_gate.py:80-86` — `tag_prefixes()` does a plain `prefixes[payload.rsplit("/", 1)[-1]] = row["prefix"]` dict assignment with no collision check of any kind. |
| 626-03 | `payload_version_gate.py`'s `main()` → `gate()` → `tag_prefixes()` → `load_targets()` chain has no `try/except` around `ReleaseTargetsError` anywhere — a missing, malformed, or unreadable `.codearbiter/release-targets.md` crashes with an uncaught Python traceback and Python's default exit code, instead of the clean `FAIL:` message every other failure path in this gate produces. | fixed-here | AC-08 / T-09. Confirmed still reproducing: read `payload_version_gate.py` lines 218-233 (`main()`) and grepped the whole file for `try:`/`except` — the only two `try/except` blocks in the file guard `_manifest_version()` and `head_version()` (lines 118-122, 127-130); nothing wraps `gate()`'s call to `tag_prefixes()` (line 195) or `main()`'s call to `gate()` (line 231). |

---

## #627 — release lane robustness: untimed tree-state probe, overloaded exit code 2

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| 627-01 | `core/pysrc/_releaselib.py`'s `release_tree_status()` — the `git status --porcelain` probe backing `run-pre-tag`'s before/after tree-state assertion — passes no `timeout=`, unlike every other internal git probe in the module (12 other call sites all use `timeout=30`). A hung `git status` (index lock, network-mounted repo, unexpected credential-helper prompt) hangs the entire `/ca:release` lane indefinitely with no diagnostic. | fixed-here | AC-02, AC-03 / T-02, T-03, T-04. Confirmed still reproducing: `_releaselib.py:2012-2016` — `release_tree_status()`'s `subprocess.run(...)` call has no `timeout=` argument. The issue's own 2026-09-17 follow-up comment records a verified, ready-but-unlanded fix design (`timeout=30` + `TimeoutExpired` catch returning a synthetic failed `CompletedProcess`) and a working regression-test idiom, explicitly deferred pending this sprint's version-advance/CHANGELOG-placement decision, with instructions to "reuse the design verbatim, do not re-derive." T-02's verification text confirms this instruction is being followed. |
| 627-02 | `core/pysrc/releasehash.py`'s `main()` returns exit code `2` for three distinct outcomes: malformed CLI usage, an unknown release target, and `check`'s `NEVER_CONFIRMED` state (a normal first-run condition). Low-impact today because the one production caller (`SKILL.md` step 6c) treats any nonzero exit the same way and always invokes `check` with an already-resolved target — but a latent trap for any future/manual/scripted caller trying to distinguish these by exit code. | fixed-here | AC-04, AC-05 / T-05, T-06. Confirmed still reproducing: `releasehash.py` lines 185, 196, 226 all `return 2` for usage error, unknown target, and never-confirmed respectively; the module docstring's exit-code table still documents only "0 confirmed, 1 changed, 2 never confirmed, 3/4 declared-file states" with no mention of the code-2 reuse for the other two cases. |

---

## Summary

| Issue | Findings enumerated | fixed-here | already-fixed-elsewhere | explicitly-deferred | compound (split) |
|---|---|---|---|---|---|
| #570 (body + 10 comments) | 81 | 6 | 33 | 40 | 2 |
| #623 | 2 | 2 | 0 | 0 | 0 |
| #626 | 3 | 3 | 0 | 0 | 0 |
| #627 | 2 | 2 | 0 | 0 | 0 |
| **Total** | **88** | **13** | **33** | **40** | **2** |

Two rows (570-R9-08, 570-R11-02) carry a genuinely compound disposition — part of the
finding is verified fixed, part is not — rather than being forced into one bucket
where that would misstate either half. Both are called out with a "remainder
explicitly-deferred" line so the open half is never silently dropped. They are counted
in their own column above rather than folded into either pure bucket. No finding is
left without at least one explicit disposition.

Every `already-fixed-elsewhere` citation above was spot-checked with `git show <hash>
--stat` and cross-checked with `git merge-base --is-ancestor <hash> HEAD` (2026-09-21,
against this worktree's `HEAD` on `worktree-release-contract-closure`, itself a fresh
`origin/main`). Where a hash cited in an issue comment is not itself reachable from
`HEAD` (seven of the #570 hashes — see "Provenance and methodology"), the citation
above records the actual reachable commit (`8ee5fe11`) rather than the orphaned one.

The floor items named in this task's brief all received their own line, none folded
into a bucketed summary: the two remote-dependent states (570-BODY-01, 570-BODY-02);
back-fill's hardcoded `app`/`prefix: v` (570-BODY-04a, plus its duplicates
570-R4-03, 570-R4-04); the `commit-gate`-in-a-fresh-consumer tension
(570-R4-08, 570-R8-05, 570-R8-06, 570-R10-08, cross-referenced against AC-10/T-12); the
missing stdlib TOML writer (570-R8-02); the missing per-commit `classify` CLI
subcommand (570-R11-02's residual half, 570-R13-03); `commands/release.md`'s drift from
`SKILL.md` (570-R13-04 — resolved as already-fixed-elsewhere, not deferred, per direct
verification against current source and the plan's task table showing later touches to
that file are for unrelated reasons); and the missing `semver-max` helper (570-R8-01,
570-R9-03).

AC-01's two named residual items — the two `#570` remote-dependent states and the
hardcoded name/prefix — are each acknowledged above with their own line
(570-BODY-01/02, 570-BODY-04a) and are never described as fixed. AC-09 (ancestry-blind
baseline, 570-BODY-03) and AC-12 (breaking-change visibility, 570-R13-01/02) — the two
items the spec names as still-open and most load-bearing — are dispositioned
unambiguously above as `fixed-here`, pointing at T-10/T-11 and T-14/T-15 respectively.

No commit-hash citation in this report asserts a published release; each citation names
a commit only. Release/version status of any cited fix is not asserted here.

---

## T-21 — AC-17 verification: the automatic publisher's triggers, permissions, and scope

**Scope of this check.** AC-17: "No change to automatic-release triggers, publish
permissions, cohort continuation, immutable-tag rules, npm publishing, or provenance
semantics." This section records fresh evidence, gathered 2026-09-22 against this
worktree's `HEAD` (`5c876dd885598c248fa777e951dac4e628688d73`), that this sprint's
staged-not-committed diff did not touch any of those. This section makes no
production or test-suite change of its own.

**1. Real publish-relevant file paths, verified (not assumed).** `.github/workflows/`
contains `ci.yml`, `codeql.yml`, `docs.yml`, `npm-publish.yml`, `pi-promotion.yml`,
`release.yml`; `.github/actions/` contains one action, `publish-release/action.yml`.
The three files the task named are real, at exactly the named paths — no adjustment
needed:
- `.github/workflows/release.yml`
- `.github/workflows/npm-publish.yml`
- `.github/actions/publish-release/action.yml`

**2. Byte-for-byte diff against `HEAD`.** `git diff HEAD -- <path>` for each of the
three produced **empty output** — zero changes, not merely a small change:

```
git diff HEAD -- .github/workflows/release.yml            -> (empty)
git diff HEAD -- .github/workflows/npm-publish.yml         -> (empty)
git diff HEAD -- .github/actions/publish-release/action.yml -> (empty)
```

`git status --short -- .github/` and `git diff HEAD --name-status -- .github/` both
confirm the only touched paths under `.github/` are five files under
`.github/scripts/` (`_releaselib.py`, `payload_version_gate.py`,
`test_consumer_smoke.py`, `test_payload_version_gate.py`, `test_release_lib.py`) —
all declared plan scope (CI-only shim, version gate, tests). No file was added under
`.github/workflows/` or `.github/actions/`.

**3. `test_ci_impact.py` result.** `python .github/scripts/test_ci_impact.py` —
**83 tests, all passed** (`OK`, 5.2s). This is the suite that asserts impact-selection
routing and the secret-scan allowlist-anchoring contract stay correct; it is unaffected
by this sprint's diff and passes clean.

**4. Targeted scan of the sprint's own diff for the specific AC-17 concerns.** Grepped
the full sprint diff (`.github/scripts`, `core/pysrc`, `core/surface`, `plugins`) for
added lines matching `permissions:`, `contents:\s*write`, `npm publish`, and
`NPMJS_TOKEN` — **zero matches**. No `on:`/`workflow_dispatch`/`schedule`/`push:`
trigger block appears anywhere in the sprint's diff (those only exist in the untouched
workflow YAML files themselves).

**5. A real, checked nuance, not a gap: `core/pysrc/_releaselib.py` IS invoked by two
of the three publish-relevant files** (`release.yml` calls `show-row`, `run-pre-tag`;
`publish-release/action.yml` calls `changelog-section`, `notes-match`, `dates-match`),
and this sprint changes that file (229 lines). This was checked in full, not waved
through on the workflow-file diff alone:
- The diff to `_releaselib.py` is exactly six hunks: a new, additive
  `verify_tag_ancestor()` function + `verify-tag-ancestor` CLI subcommand (AC-09) —
  confirmed **not** referenced by any of the three publish-relevant files (`grep` for
  `verify-tag-ancestor` across them returns nothing); a `breaking`-field docstring
  addition to `classify_window()` (AC-12) that does not touch `notes-match`'s own code
  (read the hunk immediately following the insertion — `notes_heading_matches`/
  `notes-match` dispatch is byte-identical before and after); and a `timeout=30` +
  `TimeoutExpired` catch added to `release_tree_status()` (AC-02/AC-03), which is the
  probe behind `run-pre-tag`'s before/after tree-state assertion.
- The `release_tree_status()` timeout change **does** reach `run-pre-tag`, which
  `release.yml` calls twice (lines 248, 631) — but this is exactly AC-03's own
  declared, tested invariant: "A probe failure reaches `clean-tree-status` as a
  failure and `run-pre-tag` through its existing probe-failure path (never its
  mutation-detected path)," proven by T-03 (`-k TreeStatus -k RunPreTag`) and closed
  under the Scope A/B security review. It changes probe *timing/diagnostic* behavior
  only (per DECISION-0034, carried in the spec's Approach section), not `run-pre-tag`'s
  pass/fail semantics for CI callers, and does not touch triggers, permissions,
  cohort continuation, immutable-tag rules, npm publishing, or provenance.
- `payload_version_gate.py` (AC-07/AC-08) and `releasehash.py` (AC-04/AC-05) — two of
  the other three files this sprint changed — are **not referenced at all** by
  `release.yml`, `npm-publish.yml`, or `publish-release/action.yml` (grepped directly;
  `payload_version_gate.py` appears only in a `release.yml` comment, never invoked).
  This independently confirms AC-15's "CI-only fixes... stay CI-only" claim for these
  two files at the automatic-publisher boundary specifically, not just by plan
  declaration.
- **`.github/scripts/_releaselib.py` (the CI shim, T-07/AC-06/P4) IS directly invoked
  by the publisher, repeatedly** — `release.yml` calls its `select-target-named`,
  `merge-readiness`, and `auto-eligible` subcommands (lines 193, 266, 601);
  `publish-release/action.yml` calls its `peel-tag`, `notes-match`, and `classify`
  subcommands (lines 364, 445, 449, 460, 473, 481, 590). This sprint's diff to that
  file is exactly two hunks, confirmed by direct read: (1) the module-header "Public
  API" doc comment, corrected from claiming an importable
  `select_release_target_by_name(pairs) -> str` wrapper to documenting the real
  `select-target-named` CLI route; (2) one added line in `main()`'s usage/help banner
  describing that same subcommand. Neither hunk touches any `if cmd == ...` dispatch
  block or any function body — `select-target-named`'s actual dispatch logic (and
  every other subcommand the publisher calls) is byte-identical before and after.
  This is exactly P4's declared scope ("Correct the documentation only; do not add
  the absent... wrapper") reaching a file the publisher executes, with zero
  executable-behavior change — AC-17 holds for this file specifically, not merely by
  omission from the check.
- `npm-publish.yml` references none of this sprint's seventeen changed files at all
  (grepped directly) — npm publishing logic (ADR-0029's `NPMJS_TOKEN` boundary,
  `_npm_publishlib.py`, the pinned-npm-CLI acquisition) is untouched, confirming the
  "npm publishing" clause of AC-17 independently of the workflow-file diff already
  showing zero change.
- `.codearbiter/release-targets.md` — the H-22-protected data file whose declared
  `pre-tag`/`release-build` rows the hosted publisher actually executes (per
  `security-controls.md`'s "Declared release-target commands" boundary-crossing
  entry) — is not among this sprint's 17 changed files (`git diff HEAD --name-only`
  and `git status --short`, both empty for that path). The publish-relevant
  *executable input* surface, not just the workflow YAML, is confirmed untouched.

**Disposition: AC-17 holds.** The automatic publisher's triggers, permissions
(`contents: write` and all others), cohort-continuation logic, immutable-tag
enforcement (`check_tag_immutability.py` — not in this sprint's diff), npm publishing
(`_npm_publishlib.py`/`npm-publish.yml` — not in this sprint's diff), and provenance
semantics (`tag_publication_receipt.py`/`published-tags.json` — not in this sprint's
diff) are unchanged. Two of this sprint's changed files ARE directly invoked by the
hosted publisher (this is pre-existing architecture, not new): `core/pysrc/
_releaselib.py` (via `run-pre-tag`'s tree-status probe, changed only in the
declared, tested, semantics-preserving way AC-02/AC-03 already require and Scope
A/B's security review already closed) and `.github/scripts/_releaselib.py` (via
`select-target-named`/`merge-readiness`/`auto-eligible`/`peel-tag`/`notes-match`/
`classify`, changed only in a doc-comment and a help-banner line, with zero
executable-logic difference in any dispatched subcommand). No publish-permission,
trigger, npm, or provenance surface is touched; the publisher's actual executable
input surface (`.codearbiter/release-targets.md`'s declared commands) is also
confirmed unchanged. No STOP condition applies.

---

## T-24 — Final disposition and evidence index

**Role.** T-24 is the sprint's last task and this is its output: the final
disposition/evidence-index record for the whole `release-contract-closure` sprint,
read against `.codearbiter/plans/release-contract-closure.md` and
`.codearbiter/specs/release-contract-closure.md` end to end, plus this report
(T-01/T-21), `release-closure-invariant-map.md` (T-16), and
`release-closure-journeys.md` (T-20, T-22, T-23 rounds 1-2). It makes **no**
production-code change: no file under `core/pysrc/`, `.github/scripts/*.py`
(other than reading/running one test), `core/surface/`, or `plugins/*` was
touched by this task. It does not re-litigate T-23's disposition, which the
orchestrator has already decided (see the plan's T-23 row): bounded scope
delivered, 17 of 18 acceptance criteria met, AC-18 unmet with fully documented
evidence, P8's round budget fully spent.

**This is an open PR's evidence record, stated plainly, not a "shipped" claim.**
This worktree (`worktree-release-contract-closure`, `HEAD ==
5c876dd885598c248fa777e951dac4e628688d73 == origin/main` at sprint start) carries
every governed file as staged-but-uncommitted (`M`/`A`/`??` in `git status`); no
commit has been made on this branch, no PR has been opened, nothing has merged,
no tag has been created, and no package has been published. `git tag -l` does not
contain `v2.21.8`, `ca-codex-v0.13.8`, or `ca-pi-v0.14.8` (T-22's own verification,
re-confirmed here). Nothing in this report, the invariant map, the journeys
report, or this section should be read as asserting a shipped release — every
"fixed-here" and "already-fixed-elsewhere" disposition below names a change or a
commit, never a release.

### 1. The 88 T-01 findings (plus the named floor items): reconfirmed, not re-verified from scratch

T-01 enumerated 88 distinct findings across #570 (81, body + 10 comments),
#623 (2), #626 (3), and #627 (2), each with a disposition (13 fixed-here, 33
already-fixed-elsewhere, 40 explicitly-deferred, 2 compound); T-21 appended a
fresh AC-17 verification pass. Re-reading both in full for this task turned up
no gap: every finding row carries exactly one of the three disposition
categories (or the two compound rows' explicit "remainder explicitly-deferred"
form), and the floor items named in T-01's own brief — the two remote-dependent
states (570-BODY-01, 570-BODY-02), back-fill's hardcoded `app`/`prefix: v`
(570-BODY-04a + duplicates 570-R4-03/04), the commit-gate-in-a-fresh-consumer
tension (570-R4-08, 570-R8-05/06, 570-R10-08), the missing stdlib TOML writer
(570-R8-02), the missing per-commit `classify` CLI subcommand (570-R11-02's
residual half, 570-R13-03), `commands/release.md` drift from `SKILL.md`
(570-R13-04), and the missing `semver-max` helper (570-R8-01, 570-R9-03) — each
still carries its own line, none folded into a bucketed summary.

Per this task's own instruction, T-01/T-21's credible prior verification is
trusted rather than blindly re-derived, but a weighted sample was independently
spot-checked against the current HEAD-plus-staged-diff source (not merely
re-read from the report's own prose), skewed toward `fixed-here` claims since
those are the ones this sprint's own diff is supposed to have landed:

| Finding | Disposition claimed | Spot-check performed | Result |
|---|---|---|---|
| 570-BODY-03 (ancestry-blind baseline) | fixed-here, AC-09/T-10-11 | `Grep` for `def verify_tag_ancestor` and `def last_tag_select` in `core/pysrc/_releaselib.py` | Confirmed: `last_tag_select` at line 630 (selection only, unchanged per AC-09's "existing selection unaffected" clause), `verify_tag_ancestor` at line 745 (new) |
| 627-01 (untimed tree-status probe) | fixed-here, AC-02/03/T-02-04 | Read `release_tree_status()`, `core/pysrc/_releaselib.py:2118-2143` | Confirmed: `timeout=30` on the `subprocess.run` call, `TimeoutExpired` caught and converted to a synthetic failed `CompletedProcess`, docstring cites "#627 Finding 1" |
| 627-02 (overloaded exit code 2) | fixed-here, AC-04/05/T-05-06 | `Grep` for `return 64`/`return 65` in `core/pysrc/releasehash.py` | Confirmed: line 198 (`return 64`, malformed usage), line 209 (`return 65`, unknown target) |
| 626-01 (CI-shim false importable wrapper) | fixed-here, AC-06/T-07 | Read `.github/scripts/_releaselib.py:64-93` (the "Public API" header) | Confirmed: no `select_release_target_by_name` entry in either enumerated list; the doc explicitly states it is "NOT an importable name on this module," documenting `select-target-named` CLI route instead |
| 626-02 (basename-collision silent overwrite) | fixed-here, AC-07/T-08 | Read `tag_prefixes()`, `.github/scripts/payload_version_gate.py:78-115` | Confirmed: `BasenameCollisionError` raised the moment a collision is detected, citing "#626 finding 2a", before any dict overwrite |
| 626-03 (uncaught `ReleaseTargetsError` traceback) | fixed-here, AC-08/T-09 | `Grep` for `try:`/`except ReleaseTargetsError` in `payload_version_gate.py` | Confirmed: `try`/`except ReleaseTargetsError as exc` at lines 232/236, wrapping `gate()`'s call path |
| 570-R4-06 / 570-R6-06 (back-fill ordering vs. branch refusal) | fixed-here, AC-11/T-13 | Read Back-fill/Pre-flight ordering in `core/surface/skills/release/SKILL.md` | Confirmed structurally consistent with T-13's own declared fix (branch-not-default check precedes the declaration commit in the Persist step; independently exercised end-to-end by both `ComposedFixLaneJourneyTest` stage 3 and T-23 round 2's Fixture A) |
| 570-R13-01/02 (breaking changes invisible) | fixed-here, AC-12/T-14-15 | `Grep` for `### Breaking` in `core/surface/skills/release/SKILL.md` | Confirmed: two occurrences (Phase 1 step 5 composition rule, Phase 3 `<summary>` title-selection rule) |
| 623-01 (1,700-word monolithic paragraph) | fixed-here, AC-13/14/T-16-18 | `Grep` for `^### 2\.\d` in `SKILL.md` | Confirmed: twelve named substeps, `### 2.0` through `### 2.11`, present in order — no surviving monolithic item |
| 570-BODY-04a (hardcoded `app`/`prefix: v`) | explicitly-deferred (residual) | `Grep` for `_BACKFILL_DEFAULT_TARGET` in `core/pysrc/_releaselib.py` | Confirmed still present and still hardcoded: `_BACKFILL_DEFAULT_TARGET = "app"` at line 2393, consumed at line 2430 — genuinely unresolved, not silently fixed |
| 570-BODY-01 (remote-dependent `gh release view` state) | explicitly-deferred (residual) | `Grep` for `gh release view` in `SKILL.md` | Confirmed: `gh release view` remains the sole source for `<release_nondraft>`/publication read-back (Phase 2 substep 2.7, Phase 3 steps 4/"MUST verify... by read-back") — no local-only fallback added |
| 570-R13-04 (`commands/release.md` drift) | already-fixed-elsewhere, `8ee5fe11` | (verified by T-01 itself against current source, 2026-09-21; not independently re-spot-checked here since it is not a `fixed-here` claim and T-01's own citation methodology for this row already reads current source directly, not a stale comment) | Trusted per T-01's own stated methodology |

All twelve spot-checks (ten `fixed-here`, two residual/`explicitly-deferred`)
confirm the report's disposition is accurate as of this task's own read of HEAD
plus the staged diff — none is stale. No disposition was found to have drifted
since T-01/T-21 wrote it.

### 2. AC-18's outcome

**(a) AC-18 is unmet.** `.codearbiter/reports/agent-lane-proof.json`'s
`proof_current` field reads `false` (line 3, re-confirmed by this task's own
read; not edited by this task, per this task's own hard constraint). AC-18's own
declared verification — `python .github/scripts/check_skill_proof_fresh.py`
passing — does not pass, and is not expected to pass without either remediating
HIGH-T23R2-1 or an orchestrator ruling to accept it as a documented residual.

**(b) Both of P8's two rounds are spent; no third round was taken, and none is
permitted.** The spec's own text (P8, "Final review budget"): *"At most two
independent blind-exercise rounds of the final rendered candidate. Any
remaining blocker after the second round ends the sprint BLOCKED, with evidence
— never a third round, a silent severity downgrade, or a relaxed acceptance
criterion to force convergence."* T-23 ran round 1 (found HIGH-T23-1, remediated
as R-05, independently verified) and round 2 (found HIGH-T23R2-1, the subject of
this section) — round 2 is stated by the plan's own T-23 row and by
`release-closure-journeys.md`'s own text to be "round 2 of 2" under P8. No round
3 was run, and per P8's own text above, none may be.

**(c) HIGH-T23R2-1, its `run_18_HIGH_1` lineage, and the three remedies round 2
proved do not work for the affected population.** `release-closure-journeys.md`
(T-23 round 2, "Findings") records: R-05's own remediation for round 1's
HIGH-T23-1 (widening `adoption-commit` to also scan
`.codearbiter/release-targets.md`) makes the documented default, on the exact
empty-window shape round 1 found, to widen `EFFECTIVE_WINDOW` to bare `HEAD` for
the operator's confirm-or-replace. For any Back-fill first-release consumer with
**real pre-adoption history authored before the `CHANGELOG:` footer convention
began** — the population `release-closure-journeys.md`'s Fixture A was built to
represent — every nonempty candidate window (from the narrowest to full `HEAD`)
is unfootered and BLOCKs at Phase 1 step 3 with at least one `[NEEDS-TRIAGE]`
line; no member of the documented choice set both releases something and clears
step 3 cleanly. This reproduces
`.codearbiter/reports/agent-lane-proof.json`'s own `not_remediated_here
.run_18_HIGH_1` entry (independently re-read by this task, quoted verbatim
there): *"Back-fill's own first release cannot clear Phase 1 step 3. ... An
empty floor means the whole history is footer-checked — the exact unbounded
NEEDS-TRIAGE block A-5.5 exists to prevent, on the only path that lane serves.
Reproduced in a scratch repo: 4 commits, 4 NEEDS-TRIAGE lines."* Three remedies
were checked, per `release-closure-journeys.md`'s own text, and none works for
this population:

1. **Rewrite published history (amend/rebase).** Explicitly forbidden once a
   commit is published — the ordinary state for a project Back-fill exists to
   onboard, since by definition it is already shipping. "Reclassify its type"
   is the same amend/rebase operation under a different name, not an
   independent remedy.
2. **An undeclared `$CHANGELOG_RECONCILIATIONS` ledger.** The one remaining
   stated remedy in Phase 1 step 3's prose, but never proposed by
   `backfill-detect`'s own canonical block — confirmed in the journeys report:
   the printed block in Fixture A names only
   `prefix`/`manifest`/`changelog`/`payload`/`payload-exclude`/`latest-eligible`,
   no `changelog-reconciliations` row, and nothing in the Back-fill section
   tells an operator one must be hand-authored (a full 40-character SHA plus
   note/reason/authorization fields per pre-existing commit) before a first
   release can clear step 3.
3. **Accept the footer-completeness BLOCK as-is.** Correctly stops the operator
   from shipping an unverified changelog claim — but does not complete a
   release. A loud, correct STOP is not a working release path for the
   population Back-fill exists to serve.

**(d) R-05 did not cause this.** Before R-05, the same population hit an
uninformative empty-window STOP — Phase 1 step 1's "empty output STOPs as
nothing to release" firing with no connection back to its cause (HIGH-T23-1,
round 1's finding: `$ADOPTED` silently resolving to Back-fill's own
just-committed, payload-excluded declaration commit). After R-05, the same
population hits an accurate footer-completeness diagnosis: the widened
`EFFECTIVE_WINDOW=HEAD` default correctly identifies that the pre-existing
history has never been footer-checked and says so, commit by commit, via
`[NEEDS-TRIAGE]` lines. **Neither state completes a release for this
population** — but the second one tells the truth about why, rather than
reporting "nothing to release" over a project's real, shipping feature history.
R-05 is a genuine, verified fix for the narrower defect it targeted
(HIGH-T23-1's own silent-dead-end shape); it surfaced, rather than introduced,
the wider pre-existing gap this sprint's own spec already named as out of
bounded scope (see the spec's Scope section: *"a fully onboarding-free release
path for a zero-state consumer"* is explicitly not promised).

**Severity, restated exactly as T-23 round 2 recorded it, not softened.** Not a
data-loss/corruption/silent-wrong-action BLOCKER under P8's own strict bar — the
STOP is loud and fires strictly before any tracked-file mutation (before step 4
bumps a manifest, before step 5 writes a changelog section). It is a genuine,
reproduced **HIGH**: a real remedy is unavailable for a real, non-corner-case
population, and the finding reopens a defect this same campaign already found,
named, and left unremediated once before (`run_18_HIGH_1`). Whether to accept
HIGH-T23R2-1 as a documented residual, route it through a new remediation task
outside this sprint's T-23/R-05 pairing, or reopen the plan remains, as
`release-closure-journeys.md` itself states, the orchestrator's decision — not
this task's, and not T-23's.

**Note on `agent-lane-proof.json`'s own state.** As of this task's read, the
artifact's active `exercise` object (`run: 34`) records round 1's HIGH-T23-1
finding and `proof_current: false`; it does not yet carry a distinct entry for
round 2's HIGH-T23R2-1 (no `run: 35` object exists). This does not change AC-18's
outcome — `proof_current` is already, correctly, `false` — but is recorded here
for the orchestrator's awareness. This task did not add one, per its own
constraint against touching that file.

### 3. `test_public_codex_docs.py --require-current-candidate`: confirmed still red, by direct re-run

`release-closure-journeys.md` (T-22's addendum) records this check as a genuine,
unfabricable-in-session release-time prerequisite, not a sprint defect. Rather
than trust that claim uncritically, this task read the script's own flag
handling (`sys.argv` sentinel at `.github/scripts/test_public_codex_docs.py:17-19`,
not a standard `argparse` flag — confirmed via `--help`, which does not list it)
and re-ran it directly against this worktree's current state:

```
$ python .github/scripts/test_public_codex_docs.py --require-current-candidate
....F............F
======================================================================
FAIL: test_codex_live_baseline_rejects_candidate_digest_corruption
AssertionError: '0.13.8' != '0.13.7'
- 0.13.8
?      ^
+ 0.13.7
?      ^
 : release preflight requires live proof for the current package manifest
[... assertRaisesRegex wrapper mismatch, expected message shape changed ...]

======================================================================
FAIL: test_the_codex_support_claim_separates_continuous_from_manual
AssertionError: '0.13.8' != '0.13.7'
 : release preflight requires live proof for the current package manifest

Ran 18 tests in 0.760s
FAILED (failures=2)
```

This matches the journeys report's claim exactly: the live-baseline marker in
`docs/codex-parity-testing.md` genuinely records `adapter_version: "0.13.7"`
(real, externally-verified evidence bound to PR #829's hosted CI run), while
`plugins/ca-codex/.codex-plugin/plugin.json` now reads `0.13.8` (T-22's own
version bump, landed by this sprint). This is exactly the intended behavior of
`test_codex_live_baseline_may_lag_the_development_candidate` — the check is
*supposed* to stay red until a real live Codex CLI install/verification cohort
runs against the `0.13.8` candidate and records its own genuine CI run ID,
artifact ID, and digests, none of which a session can fabricate without
committing exactly the "silently against stale HEAD" violation AC-16/AC-18
forbid. **Disposition: confirmed still red, for the correct reason, as a
release-time prerequisite for shipping `ca-codex` `0.13.8` — not a defect in
this sprint's own work, and not fixable by this or any other task in this
sprint's bounded scope.**

### 4. #570's two original residuals: reconfirmed genuinely unresolved

Per §1's spot-check table: `_BACKFILL_DEFAULT_TARGET = "app"`
(`core/pysrc/_releaselib.py:2393`) is still a hardcoded module constant, never
derived from a consumer's own manifest or tags — 570-BODY-04a (plus its
duplicates 570-R4-03/04) is correctly labeled `explicitly-deferred`, never
implied fixed. `gh release view` remains the sole source for
`<release_nondraft>`/publication state, with no local-only fallback anywhere in
`SKILL.md` — 570-BODY-01 and 570-BODY-02 (the two remote-dependent states) are
correctly labeled `explicitly-deferred`, never implied fixed. Both residuals
carry their own line in §1 above and in T-01's original enumeration; neither is
silently absent from this record, per AC-01's own requirement.

### 5. This record's own status

This is an evidence index for an **open, unmerged PR-to-be**. Nothing in this
sprint has shipped: no commit exists on this branch beyond the pre-sprint
`origin/main` baseline, no PR has been opened, no tag has moved, no package has
published, and `check_skill_proof_fresh.py`/`test_public_codex_docs.py
--require-current-candidate` both remain correctly red for reasons this sprint's
own bounded scope cannot close from inside a session. Of the sprint's eighteen
acceptance criteria, seventeen (AC-01 through AC-17) are met with cited evidence
above and in T-01/T-16/T-20/T-21's own reports; AC-18 is unmet, with its own
unmet-ness fully documented in §2 above rather than hidden, downgraded, or
forced to a false pass.

## Post-T-24 amendment — HIGH-T23R2-1 remediated, not accepted or overridden

The T-24 status above is preserved as the accurate historical close of the original two-round
candidate. It is superseded for the materially changed candidate by the user's explicit
2026-09-22 direction: reject acceptance/override, fix the review finding, and commit the corrected
effort. The approved spec/plan record this as AC-19/R-06/T-25; no other deferred #570 item was
silently pulled into scope.

**Current disposition of HIGH-T23R2-1: fixed-here, pending commit/PR.** Back-fill now declares the
strict `changelog-reconciliations` ledger, requires operator-authored full-SHA note/reason/
authorization entries for the exact published pre-adoption history, validates the draft, commits
the declaration and ledger together, and forbids release re-entry until those exact files are
published on the fetched default branch. The existing immutable-tree loader and ancestry proof
remain the authority during `classify-window`; no footer gate, classification, bump, scope, tag,
or publication rule was weakened.

Evidence is indexed in `release-closure-journeys.md` §"T-25 — User-reopened remediation
verification": the focused regression was red for five route omissions before implementation;
the corrected focused suite passes 45 tests; a disposable Git fixture proves a real published
unfootered feature clears only through its exact ledger SHA; canonical/generated checks pass; and
an independent coverage audit returned no CRITICAL/HIGH finding. Its one MEDIUM test-gap finding
was remediated and the bounded follow-up reports no remaining HIGH/MEDIUM.

The ordinary public-Codex documentation suite now passes 18/18. The release-only
`--require-current-candidate` form remains honestly red on one test because externally verified
live proof still names 0.13.7 while this development candidate names 0.13.8. That gate is not
hand-cleared and no live-run identity is fabricated. Nothing has shipped at this point; the
candidate is still an uncommitted worktree until the commit gate below completes.
