# 02. Acceptance and test matrix

All identifiers below are **proposed regression cases**, not claims that tests already exist. Generate the minimal failing tests first, retain baseline outputs, then implement. Go and Python must validate the *same* wire fields and canonical source.

## A. Adoption / identity

| ID | Fixture / operation | Required observation |
|---|---|---|
| A01 | Two distinct rows share one `(from ...)` origin | Preview and Go cutover produce two different WORK IDs; source provenance retained and accessible |
| A02 | Actual codeArbiter board shape: 19 rows across six shared-origin groups and 45 titles over 240 characters at baseline | Preview succeeds in a disposable copy; apply succeeds if no independent malformed data; accounting covers each distinct row |
| A03 | 600-character single-line task title | Bounded native title; original complete text recoverable in intent or immutable historical source |
| A04 | Unicode title with multi-byte emoji/non-ASCII at the truncation boundary | No invalid UTF-8 or Python/Go length mismatch |
| A05 | 4,001+ characters or otherwise unrepresentable record | Explicit board/path/line refusal; no partial cutover |
| A06 | Duplicate explicit Work ID or alias on distinct rows | Refuse; neither unique ID overwritten nor history silently coalesced |
| A07 | Identical duplicate task block in same board | Refuse as genuine duplicate |
| A08 | Exact open/archive crash duplicate (existing supported archival shape) | One logical record when truly identical; retain both source bytes and explain disposition |
| A09 | Distinct open/archive rows share origin | Distinct native records; no false archive deduplication |
| A10 | Originless row and normalized non-native historical origin | Stable legal native origin/ID; exact original block recoverable |
| A11 | Existing valid explicit Work ID | ID unchanged after adoption and restart |
| A12 | Python inventory vs Go block reconstruction | Compare all normative/execution fields, row count and source block identity, not only a success boolean |
| A13 | Board changed between preview and apply | CAS or revision conflict; no native owner or partial file set |
| A14 | Same operation ID/input retried after lost response | Same committed outcome, no second work item |
| A15 | Same operation ID with different payload | Refuse; no rewrite |
| A16 | New clone with canonical project/work files and historical snapshots, without old local journal | Work still readable; provenance and ID portable |
| A17 | Symlink, invalid UTF-8, malformed metadata, unsupported archive bytes or cap overrun | Preserve strict scoped refusal |
| A18 | Old legacy writer runs after native adoption | Refuses; no second writable board owner |
| A19 | Historic work/source detail view | Original source block and origin remain accessible; derived views never become canonical artifacts |
| A20 | Reordered/edited board before a new preview | New valid preview has unambiguous deterministic identities; an older preview cannot apply |

For A02, do not write to the actual `.codearbiter` tree. Build fixtures from a frozen, sanitized, temporary copy. A live board's exact counts may change after this packet; rerun before using the counts as a current assertion.

## B. Commit-gate lifecycle

| ID | Owner-produced change | Expected `classify_board_diff` / gate |
|---|---|---|
| G01 | Create one queued task block | Accept |
| G02 | Start one existing keyed item | Accept |
| G03 | Complete one active keyed item | Accept |
| G04 | Attach spec/plan to one selected existing item | **Accept after fix** (currently rejects) |
| G05 | Start and attach spec/plan to same item | **Accept after fix** (currently rejects) |
| G06 | Create and start same item within one staged diff | **Accept after fix** (currently rejects) |
| G07 | Start then complete same item within one staged diff | **Accept after fix** (currently rejects) |
| G08 | Change unrelated second row | Reject |
| G09 | Add arbitrary or unknown indented metadata | Reject |
| G10 | Change an unrelated heading, prose, table, scope or a different row | Reject |
| G11 | Delete archived/history or remove a task without an owning operation | Reject |
| G12 | Forge lifecycle state without proper dates/shape | Reject |
| G13 | Mix one accepted task change with unrelated source modification of board text | Reject board exemption; let normal changed-file scope evaluation own independent authorization |
| G14 | Fixture produced by actual `work.py` and `taskwrite.py` | Same verdict at classifier and commit-gate, with no unsupported shortcut |

Do not treat the classifier's `True` as authorization for an arbitrary repository commit. The ordinary commit gate, host permissions, review and protected-path rules still run.

## C. End-to-end and failure evidence

| ID | Journey | Expected result |
|---|---|---|
| E01 | Existing project with legacy board -> preview -> explicit adoption -> selected work read | One native owner; counts, titles, original blocks and work IDs accounted for |
| E02 | Fresh native project -> create -> attach -> start -> complete -> reopen/archive | Stable identity; native lifecycle works independently of legacy classifier |
| E03 | Feature lane on adopted work | Spec/plan binding and task transition in the same governed commit without false scope-creep |
| E04 | Fix/sprint lane completes work in one change | One row is updated; check status not inferred from completion |
| E05 | Restart midway and run same operation ID | Exact replay/recovery; no duplicate work or synthetic check |
| E06 | Explicit blocked/user-stopped work | Stop remains; unrelated authorized work may proceed |
| E07 | Reported failing check then unrelated passing check | Applicable failure remains visible until genuinely resolved |
| E08 | Local work update while GitHub unavailable | Local operation succeeds; remote status remains unknown/pending, no silent send |
| E09 | Derived work/project views on narrow/desktop widths, offline | Navigable and accessible; no external runtime assets; truthful statuses |
| E10 | Three host package/installed paths | Record source candidate, package digest and actual installed result separately |
| E11 | Native plan update after real evidence | Recorded state matches inspected implementation/check/delivery evidence; absence remains unknown |
| E12 | Damaged journal, changed source, stale operation, lock conflict | Safe refusal/recovery, never overwrite or delete unknown history |

## D. Validation commands and coverage owners

First discover the repository's actual supported toolchain, generated-file checks and CI contracts at the newly pinned head. Candidate commands from the inspected source:

```sh
python .github/scripts/test_taskboardlib.py
python .github/scripts/test_taskwriter.py
python .github/scripts/test_artifact_work_cli.py
python .github/scripts/test_context_consumers.py
python .github/scripts/test_board_sync.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
```

Native Go package tests, from `core/artifacts`:

```sh
go test ./internal/operations ./internal/repository ./internal/render -count=1
go vet ./...
```

Also run the appropriate codeArbiter CI, site/host package and installed candidate tests selected from current repository guidance. Do not represent the example commands as executed by this handoff. No claimed pass counts are supplied.

## E. Evidence standard

A test result must capture: exact head/commit, command, environment, actual exit code, observed assertion, relevant package/engine identity, and whether it is source-only, built-candidate, installed-host, or remote readback. Keep test-specific evidence separate from governance labels. Evidence and implementation status must not be silently promoted to release status.
