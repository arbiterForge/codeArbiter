# Release tag provenance

Published tags never move or disappear. A bad release is corrected by a new
version, not by changing a recorded identity or retargeting a tag.

The release preflight uses `check_tag_immutability.py --require-recorded` before
authorizing publication. Missing records or unreadable evidence refuse release.
Ordinary CI remains an observation: it warns about unrecorded tags and reports
an explicit skip on unavailable inventory. An automatic run with no eligible
release does not require a new publication check.

## Closed legacy provenance epoch

ADR-0034 establishes `.github/legacy-published-tags.json` as a closed set of
44 historical baselines observed at `2026-09-04T20:45:43Z`. These records are
**not original-publication proof**. They preserve three evidence grades and
prove only the identity from which each listed ref is enforced immutable going
forward. A historical tag could have moved before that observation; available
evidence neither proves nor disproves that residual risk.

The guard strictly validates the ledger's observation, record count,
evidence-grade counts, source-matrix digest, and canonical identity-and-grade digest.
It rejects overlap with the original-publication ledger and compares both
classes with the complete live inventory. A legacy mismatch means only that the
ref moved after its recorded observation. It never proves where the ref was
originally published.

The legacy epoch cannot grow through release or reconciliation tooling. Adding
or replacing a legacy identity, source, or evidence grade requires a new accepted, user-attributed ADR
and architectural review. Every governed tag
outside that closed set requires an original-publication receipt before a later
release. Moving, retargeting, or deleting any recorded tag remains prohibited,
with no break-glass path; corrections use a new version.

## Capture and retain

The shared publisher captures the exact remote tag object and peeled commit,
bound to the repository, workflow revision, run ID, and run attempt. Capture and
artifact upload are attempted even when tag push succeeds but Release creation
fails. A capture or upload failure is a failed step, not a successful recording.
Cancellation or loss of the runner can still prevent retention; inspect the
actual artifact, not just the workflow definition.

Artifacts are named
`tag-publication-<job>-<run-id>-<run-attempt>` with a requested retention of
90 days, subject to repository and organization policy. Check the artifact's
actual expiration and reconcile it through a reviewed PR before it expires and
before another release.
Neither the receipt nor the reconciliation helper writes to `main`.

The schema calls this a `hosted-tag-observation`. It proves what a trusted run
observed, not necessarily where an older tag originally pointed. In particular,
rerunning capture on an old unrecorded tag cannot manufacture its original
publication provenance. Preserve unresolved historical gaps separately.

## Authenticate before reconciliation

The offline helper does **not** authenticate a downloaded JSON file. Before
using it, independently verify all of the following through GitHub's trusted
Actions run and artifact metadata:

- The run belongs to this repository's release workflow
  (`.github/workflows/release.yml`), not a pull-request or fork-controlled workflow.
- Its workflow source revision is the reviewed, protected-main revision expected
  for that release. Check the workflow identity, event, branch, revision, run ID,
  and attempt; a matching artifact name alone is insufficient.
- The artifact belongs to that exact run and attempt and the expected publisher
  job. Download it from that run, retaining the artifact metadata and digest.
- The expected tag and commit come from the authorized release record, not from
  fields supplied by the downloaded receipt. Verify that current remote refs
  still agree before proposing the ledger addition.

If the original run, artifact, or identity evidence is unavailable or ambiguous,
stop reconciliation and preserve that uncertainty. Do not substitute current
refs for original publication evidence or amend an existing entry to hide drift.

## Produce a reviewable candidate

Use an isolated branch with a clean ledger. Hash its exact current bytes using
SHA-256. Supply independently verified values for every `expected-*` argument;
do not fill them by copying fields out of the untrusted receipt.

```sh
python .github/scripts/reconcile_tag_receipt.py \
  --receipt /path/to/authenticated-receipt.json \
  --manifest .github/published-tags.json \
  --legacy-manifest .github/legacy-published-tags.json \
  --output /path/to/new-candidate.json \
  --expected-manifest-sha256 <current-ledger-sha256> \
  --expected-legacy-sha256 <current-legacy-ledger-sha256> \
  --expected-repo arbiterForge/codeArbiter \
  --expected-tag <authorized-tag> \
  --expected-commit <authorized-commit> \
  --expected-run-id <verified-run-id> \
  --expected-run-attempt <verified-attempt> \
  --expected-workflow-sha <verified-workflow-revision>
```

The helper validates both ledgers' bounded, exact schemas and digest bindings,
rejects conflicting, malformed, or legacy-set data, and produces an exclusive
candidate containing one new original-publication identity.
It preserves existing entries and metadata. An already identical entry is a
no-op with no output file; an existing output is never replaced. The manifest
digest prevents accidentally reconciling against a stale source snapshot.

Review the candidate against the original ledger. Apply only the verified
addition through the governed commit and PR path, retain the authenticated run
and artifact evidence in that PR, and run the tag audit and its tests. A candidate
file or a green unit test is not proof of hosted artifact authenticity, successful
publication, PR merge, or completion of other historical recording obligations.
