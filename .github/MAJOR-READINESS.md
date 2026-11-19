# Major-program readiness

`major_readiness.py` implements Q-02 for `codearbiter-major-state-contracts`.
It guards publication effects while the integration candidate marker remains.
A target version mismatch refuses and must be reselected through its owner.
The publisher's observed `receipt`-only repair has no new publication effect,
but still requires the exact declared candidate version while the marker exists.
The Pi npm event/source equality check remains independently required.

## Trusted producer

The existing six-platform native build now retains its original named Go
outcomes and their join to the native payload stamp. It executes the tests
once. The Windows/amd64 owner has a trusted-main report step; the final
producer follows the ordinary merge checks. Both stop after the integration
marker is retired. The current semantic map covers only N09:04. Other
required cells, retained disposition proofs and host observers remain
incomplete, so this wiring cannot yet produce a ready record. Integration
and PR runs retain observations without publication authority.

The final main-push CI run owns production. Candidate PR and integration runs
test the verifier and do not produce publication authority. The producer runs
after the required qualification jobs and artifact uploads:

```sh
python .github/scripts/major_readiness.py produce \
  --source "$GITHUB_SHA" --ci-run-id "$GITHUB_RUN_ID" \
  --output "$RUNNER_TEMP/major-readiness.json"
```

Upload the single file as `major-readiness-$GITHUB_SHA`. The artifact archive
must contain only `major-readiness.json`. Production requires Actions read
permission and the exact same-repository main-push CI environment. It writes
no receipt when required tasks, dispositions, decisions, jobs or artifacts
remain incomplete.

Required task IDs come from the frozen prepublication task population plus
added required work. Q-03 is excluded. Required scenarios come from the
scenario contract. Installed cells come from
`major-qualification-policy.json`; the policy is reviewed when supported
platforms or runtimes change. The receipt binds the exact source, tree,
task/progress bytes, coverage ledger bytes and accepted ADR lifecycle bytes.
The existing ADR lifecycle verifier checks accepted bindings.
The exact selected source's `.codearbiter/open-questions.md` is also read;
numbered `CONFIRM` records refuse readiness, independently of execution
metadata. Its digest and unresolved count are bound into the receipt.

## Retained disposition proof

All 2,105 frozen finding, machine and transition IDs, plus added transitions,
must be present. Each disposition names retained proof with `kind`, the exact
tested source `commit`, `ref` (a committed proof JSON path), and its `sha256`.
An optional `ref_commit` names the later ancestor commit retaining that proof;
by default the selected candidate retains it. Both commits must exist and be
ancestors of the candidate.

A proof uses schema `codearbiter-disposition-evidence/1` and records
`source_commit`, `kind`, `result`, `disposition_ids`, `producer`, `inputs`, and
`raw_evidence`. `producer` contains an original `class` and `identity`.
Classes are `local-host`, `hosted`, `independent-review`, and
`source-conformance`. `inputs` maps checked repository paths to SHA-256
digests. The owning paths from each frozen disposition must be included, and
every recorded input must match both the tested source and the candidate.
The proof and its raw evidence must remain readable and match their digests.

Raw local evidence uses `{path, sha256}` in the retaining commit. Original
hosted evidence uses `{run_id, job_id, artifact_id, sha256}` and is read back
through authenticated successful same-repository CI/docs runs. Missing,
expired, mismatched or unavailable original proof refuses readiness. Tested
dispositions require actual successful `commands`; installed claims also
retain `host`, `platform` and `installed_artifacts`. N/A retains its exact
contract and rationale. A review can preserve many instruction/parser rows;
this does not require another runtime framework or one execution per row.
Retained local host proof remains labelled local when a trusted CI job
authenticates its source, retained bytes and candidate applicability.

## Qualification runner contract

Task jobs are named `major qualification / <task-owner>`. The composed
scenario job is `major qualification / scenarios`. Each installed cell has
a job named `major qualification / <cell-id>`. The producer's `requirements`
operation prints the complete cell-to-job map from the selected source.
Disposition cells use `disposition:<group>:<id>` and join their existing owner
job. Shared actual tests or reviewed conformance may cover many such cells.

Each actual runner uploads `major-qualification-<numeric-job-id>` containing
only `qualification.json`:

```json
{
  "schema": "codearbiter-major-qualification/1",
  "source_commit": "exact 40-hex source",
  "source_tree": "exact 40-hex tree",
  "ci_run_id": 123,
  "job_id": 456,
  "results": [{
    "cell": "task:NT-01",
    "result": "PASSED",
    "commands": [{"argv": ["actual", "command"], "exit_code": 0}],
    "selected_population": 1,
    "executed_population": 1,
    "payload_artifact_id": 789,
    "payload_archive_sha256": "actual downloaded archive SHA-256",
    "payload_members": [{"path": "actual member", "sha256": "actual consumed member SHA-256"}]
  }]
}
```

This is the accepted version-1 shape. Current producers emit
`codearbiter-major-qualification/2`: a top-level `payloads` table records each
positive `artifact_id`, `archive_sha256` and `members` inventory once, and
each result refers to it through `payload_artifact_id`. The verifier rejects
duplicate or conflicting identities, missing or unused payloads, and
row-local alternate payload bindings. This keeps a complete report within
the unchanged bounded-reader limit without weakening archive authentication.

A runner must emit actual command outcomes and the
selected and executed population from its checks. Generating all-pass rows
from task labels or a successful unrelated command is invalid. Missing,
skipped, unavailable, duplicate or unexecuted required cells prevent a receipt.
Installed jobs must exercise the actual package/runtime combination named
by their cell. Source tests cannot substitute for installed proof.

The runner records the downloaded archive and consumed member digests. These
must equal the producer's independent readback of the retained bytes.
Every report is read from an authenticated retained Actions artifact for the
same run and source. The job must have succeeded and its name must own that
cell. Each cell names the exact package artifact it exercised. The complete
population must cover both `artifact-host-payloads-<source>` and
`artifact-release-packages-<source>` cohorts. The producer downloads each
archive, checks its API SHA-256 identity, and records all regular member
digests. Unsafe, ambiguous, encrypted, empty or oversized archives refuse.

The qualification upload step must be named exactly
`Upload major qualification report`. The producer job must be named
`major readiness producer`, with upload step `Upload major readiness record`.
Both use the pinned
`actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9` action.
The verifier requires a successful exact API step and authenticates its
original job-log window, including pinned action, finalized artifact ID/name
and archive digest. The artifact creation time must belong to that upload
step. Artifact names and JSON job IDs alone cannot identify the uploader.

## Publisher verification

The publication composite calls `verify` after observing remote state and
before creating tags, drafts, registry packages, channel refs or public
Releases. Verification requires a successful same-repository main-push run
of `ci.yml`, the exact selected source/run, unexpired artifacts, and matching
archive and member bytes. It reconstructs the receipt from the original
qualification reports, so an edited receipt cannot invent a passed cell.
The publisher separately verifies its downloaded cohort before publication.

`PREPUBLICATION_READY` does not claim publication has happened.
`DISTRIBUTION_SETTLED` belongs to Q-03's subsequent external readback and
receipt settlement. No test receipt, committed JSON flag, integration
status or matching version string can replace this evidence.

## Settlement and marker retirement

The program marker remains active until Q-03 authenticates real settlement of
every required target through the existing trusted publisher, original
publication receipts and exact public readback owners. A committed
`DISTRIBUTION_SETTLED` flag, tag presence or an edited JSON assertion cannot
turn the barrier off. A mismatched candidate version is an error while this
marker exists, including a later patch number.

After genuine settlement, the integration owner prepares a separate reviewed
PR retiring `.github/integration-candidate.json`. That reviewed source change
restores ordinary independent later-version release behavior. It retains the
existing trusted-source/PR security model: reviewed source can already change
the gate code, so a second runtime settlement protocol would add another
authority system without strengthening that boundary. No marker is retired
by this verifier, and no current publication or cleanup is authorized here.
This lifecycle is a Q-03 obligation, not a circular prerequisite that requires
publication before the first `PREPUBLICATION_READY` receipt can be valid.

Read-only native observation may create the untracked, empty
`.codearbiter/.artifacts/store.lock`. Source stability excludes only that
exact ordinary, single-link, zero-length file beneath real directories.
Tracked, staged, nonempty or linked locks, other artifact files and source
changes still count as changes.
