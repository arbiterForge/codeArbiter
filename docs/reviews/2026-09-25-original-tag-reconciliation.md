# Original tag receipt reconciliation for the C04 CI continuation

Status: review candidate, not an amendment of existing tag history. The ledger append
is not authoritative on protected main until a reviewed merge incorporates it.

## Why this is included

PR #862's exact-head CI run `36106378375`, job `107980009625`, rejected two public tags
absent from the provenance ledgers. Both were created by an earlier protected-main
publication run, not by this documentation work. The requested continuation through
green CI uses the existing reconciliation procedure rather than suppressing that gate.

Only two identities are appended to `.github/published-tags.json`. Its 166 existing
records and metadata are retained; `.github/legacy-published-tags.json` is unchanged.
No tag, Release, package, registry channel, publication permission or workflow gate is
created, moved, retried, relaxed or represented as successful by this change.

## Independently authenticated original evidence

Repository: `arbiterForge/codeArbiter`. Original Release workflow run
[36084996407, attempt 1](https://github.com/arbiterForge/codeArbiter/actions/runs/36084996407)
executed at `929229354e3a15ae3002c82116b66c837ab43729` after the qualifying main CI.
Its job logs explicitly record **new tag creation**, followed by successful receipt
capture and artifact upload. These are not fresh observations substituted for missing
original history.

| Tag | Original job | Artifact | Downloaded ZIP SHA-256 |
|---|---|---|---|
| `v2.21.15` | [107914929264](https://github.com/arbiterForge/codeArbiter/actions/runs/36084996407/job/107914929264) | [10843288417](https://github.com/arbiterForge/codeArbiter/actions/runs/36084996407/artifacts/10843288417), 433 bytes | `d7f343833e59cb27daaaa59fdc3d871db2aca59aa31919d64bb0cb28e1ea7468` |
| `ca-codex-v0.13.16` | [107915186019](https://github.com/arbiterForge/codeArbiter/actions/runs/36084996407/job/107915186019) | [10842718926](https://github.com/arbiterForge/codeArbiter/actions/runs/36084996407/artifacts/10842718926), 449 bytes | `19f0cfe70d40cafbc6d07d568714a556cc19fd5170bdd61f867b8cbabed39bc1` |

The Claude log records its new tag at `2026-09-25T02:09:25.2424836Z`, then receipt
capture and upload ending at `02:09:28.2913748Z`. The Codex log records its new tag
at `02:10:31.0906184Z`, followed by receipt capture and upload ending at
`02:10:34.166380Z`. Each publisher reports `marker_durable_tag_created`, not an
already-existing-tag resume. Artifact metadata, downloaded bytes and the recorded
repository/run/attempt/source bindings were checked independently.

The current remote annotated tag objects were also read and matched these originals:
`f74de069c2aa47728667ebf8060b471df485fffd` and
`c3a34e1ff51412fc39d4a2a20978efa471f49d1e`, respectively. Both peel to the source
commit above. That comparison checks subsequent identity; the original hosted log
and artifact, not the current ref alone, establish the publication-time evidence.

## Original receipt contents

These are the downloaded records, retained as data rather than new authority events.
The producer's `hosted-tag-observation` label by itself does not prove originality;
the original-run creation evidence above is required.

```json
{
  "identity": {
    "commit_sha": "929229354e3a15ae3002c82116b66c837ab43729",
    "object_sha": "f74de069c2aa47728667ebf8060b471df485fffd",
    "object_type": "tag"
  },
  "repo": "arbiterForge/codeArbiter",
  "schema_version": 1,
  "source": {
    "kind": "hosted-tag-observation",
    "run_attempt": 1,
    "run_id": 36084996407,
    "workflow_sha": "929229354e3a15ae3002c82116b66c837ab43729"
  },
  "tag": "v2.21.15"
}
```

```json
{
  "identity": {
    "commit_sha": "929229354e3a15ae3002c82116b66c837ab43729",
    "object_sha": "c3a34e1ff51412fc39d4a2a20978efa471f49d1e",
    "object_type": "tag"
  },
  "repo": "arbiterForge/codeArbiter",
  "schema_version": 1,
  "source": {
    "kind": "hosted-tag-observation",
    "run_attempt": 1,
    "run_id": 36084996407,
    "workflow_sha": "929229354e3a15ae3002c82116b66c837ab43729"
  },
  "tag": "ca-codex-v0.13.16"
}
```

## Partial publication is not hidden

The original run concluded **failure**. The Codex job created its tag and retained
the receipt, but later failed with `Codex npm package and metadata must be real
sibling files`. Its npm publication, cold install, Release finalization and channel
advance were not completed by that run. Pi publication was skipped. This ledger
append does not certify the cohort, claim successful Codex distribution, or resume
publication. The parent branch's separate metadata correction remains separate work.

The owning action explicitly captures tag identity even when a later publication
step fails. See
`arbiterForge/codeArbiter@929229354e3a15ae3002c82116b66c837ab43729:.github/actions/publish-release/action.yml`.

## Candidate preparation and verification

The unchanged `.github/scripts/reconcile_tag_receipt.py` was run offline once per
receipt, with independently supplied expected repository, tag, commit, run, attempt
and workflow SHA. Source hashes were pinned before each append. The resulting
identities were compared with the final manifest. Its original prefix is preserved
byte-for-byte; only the two records and necessary joining delimiter are added.

- Original manifest SHA-256: `179a726b8ed0b925cd45791a7cd472ff9ae8cbe5aaaba91ea21e222e486811aa`.
- Candidate manifest SHA-256: `188cd1b4dbbbe86a9e58dd08f2e50f48f4da795f3073a2895e6976a18358a119`.
- Unchanged legacy manifest SHA-256: `d9ae0a45cec0a873c8ed5d28e9f3fc255a6e7cfb4c79e3ccfba80b8294a7e8db`.

All existing receipt/reconciliation tests passed locally. Exact-head remote tag
comparison and normal aggregate CI remain separate hosted checks. This candidate
must pass the unchanged `--require-recorded` gate; no manual status substitutes for
it. Review and merge are still owner actions.

Rollback before acceptance is removal of this candidate append and note as one
reviewed change, not deletion or retargeting of either published tag. Once protected
history adopts an authentic record, do not erase or replace it merely to clear a
future drift failure. No other provenance record is altered.
