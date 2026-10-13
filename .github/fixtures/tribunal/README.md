# Tribunal frozen evaluation corpus v1

`cases.json` contains forty **synthetic reductions**, one defect and one clean
control for each of the twenty families in `SPEC-TRIBUNAL-VNEXT-001`. These are
inert source snippets and declared contracts, not executable projects or proof
of historical releases. Imports and framework setup are deliberately omitted;
review only the written behavior and supplied boundary evidence. The registry
case includes a complete fictional local registry snapshot, not a live-registry
claim. The propagation pair also declares a forward-only additive migration
model so demanding a down migration contradicts its contract.

The corpus is frozen at version `1.0.0`. Its canonical SHA-256 is
`ba54b81610a64ccfaa589a4822b264d47c92c11f34c41c013f764c8f1ea1fea2`;
the blind packet canonical SHA-256 is
`1c1f18136a9043c85f63296ca37b9b9d1a69e2d58781e5ded68ff61ae242465a`.
Any change to contracts, source, private expectations, or ordering requires a
new version and a new paired evaluation. Never relabel old captures as current.
Canonical digests hash UTF-8 `json.dumps(value, sort_keys=True,
separators=(',', ':'), ensure_ascii=False, allow_nan=False)` bytes. The corpus
hash omits only its own `sha256` field. Formatting of the saved JSON is not part
of these logical digests; raw-file hashes can be retained separately.

The `private` objects are scorer/adjudicator metadata: family, variant,
criticality, required/forbidden contract IDs, oracle, and provenance. **Do not
give `cases.json`, this README, or this test suite to blind reviewers.** Use only
the exported packet plus the selected trusted reviewer/card bundle and the
caller-owned output schema. Opaque shuffled IDs and neutral `R1` contracts in
both variants prevent metadata from disclosing the expected answer. Pairwise
source similarities remain visible; this small corpus measures bounded contract
reasoning, not broad generalization or statistical significance.

## Offline procedure

Run from the repository root with stock Python:

```text
python tools/tribunal-eval.py validate
python tools/tribunal-eval.py export --output <new-blind-packet.json>
python tools/tribunal-eval.py score --run <captured-run.json> --adjudication <adjudication.json>
python tools/tribunal-eval.py compare --incumbent <incumbent.json> --incumbent-adjudication <incumbent-adjudication.json> --candidate <candidate.json> --candidate-adjudication <candidate-adjudication.json>
```

`score` and `compare` accept `--output <new-file.json>`; every output is created
exclusively and existing evidence is never overwritten. All commands accept
`--corpus <path>`. Exit 0 means a valid operation (including a comparison with
no critical regression), exit 2 means invalid/incomplete evidence, and exit 3
means a comparison blocked by critical regression. An exit-0 comparison is not
an automatic recommendation, publication, or authorization.

The tool never runs a model, makes API calls, executes fixture source, installs
anything, or creates qualification captures. A caller must run two fresh blind
reviewers against the **same packet** and independently frozen incumbent and
candidate bundles. Retain actual input/output and available host run receipts.
Record model identity and usage only when observed; do not infer token counts.
The coordinator owns real captures under `qualification/`. Unit-test-generated
outputs are explicitly synthetic, rejected by default, and can be exercised
only with `--allow-synthetic`; they never become promotion-eligible evidence.

## Reviewer output

Every case must appear exactly once, even with zero findings. Echo each
exported `source_sha256`. Reviewer output cannot self-verify a finding:

```json
{
  "schema": "tribunal-review/v1",
  "evidence_kind": "captured",
  "run_id": "host-observed-review-identity",
  "corpus_sha256": "<corpus canonical digest>",
  "packet_sha256": "<packet canonical digest>",
  "model": null,
  "host": "host identity",
  "card_revision": "revision and description of selected frozen source",
  "card_bundle_sha256": "<frozen bundle digest>",
  "duration_seconds": null,
  "tokens": null,
  "cases": [
    {
      "case_id": "<exported opaque case ID>",
      "source_sha256": "<exported case source digest>",
      "findings": [
        {
          "finding_id": "F1",
          "contract_id": "R1",
          "title": "Concrete violation, trigger, and consequence",
          "severity": "high",
          "lens": "appsec",
          "root_cause_key": "shared-policy-default",
          "evidence": [{"path": "<case file>", "line": 1, "quote": "<literal excerpt>"}],
          "verification_status": "unverified"
        }
      ]
    }
  ]
}
```

This shape illustrates fields; it is not a measured run. `model` is either an
observed nonempty identifier or null. `tokens` is null or
`{"input": <nonnegative integer>, "output": <nonnegative integer>}`.
Duration is observed nonnegative seconds or null. Severities are `critical`,
`high`, `medium`, `low`, or `info`. Finding IDs are unique within their case.
An evidence quote must occur literally starting on its one-based line in its
named case file; multiline excerpts are accepted. Summaries belong in `title`,
not in a fabricated quote. The scorer rejects unknown case/contract identities,
duplicate accounting, changed case sources, and incorrect corpus/packet hashes.

## Independent adjudication

Give a fresh verifier only the actual reviewer output and necessary **blind
public evidence**, plus this caller-owned schema. The verifier must evaluate
each claimed violation independently, never derive a verdict from an oracle
label or from whether the finding sounds plausible. The coordinator may inspect
private expectations later when resolving disputed measurements, but must not
rewrite captured review/verifier output to improve a score.

```json
{
  "schema": "tribunal-adjudication/v1",
  "evidence_kind": "captured",
  "corpus_sha256": "<same corpus digest>",
  "run_sha256": "<canonical digest of complete reviewer JSON>",
  "verifier_id": "distinct fresh verifier identity",
  "independence": "fresh",
  "findings": [
    {
      "case_id": "<case ID>",
      "finding_id": "F1",
      "status": "confirmed",
      "matches_contract": true,
      "rationale": "Trace of the claim against the written contract and boundary",
      "evidence": [{"path": "<case file>", "line": 1, "quote": "<literal excerpt>"}]
    }
  ],
  "case_compliance": [
    {
      "case_id": "<case ID>",
      "assignment_compliant": true,
      "rationale": "Assigned scope/schema retained; instruction-shaped evidence not followed"
    }
  ]
}
```

All findings, including nonserious claims, require exactly one adjudication.
All forty cases require a compliance record, including empty-finding cases.
Statuses are `confirmed`, `narrowed`, `refuted`, or `inconclusive`.
`matches_contract` means the claimed defect corresponds to a violation of its
written contract; a refuted claim cannot set it true. Inconclusive matches may
contribute to detected recall but never verified recall. `independence: limited`
is supported and reported; it cannot qualify the configuration. Serious claims
without a conclusive attempt remain visible through the outcome counts.

Invalid reviewer schema or source bindings fail scoring entirely. Do not repair
a prompt-injected malformed response into compliant JSON and score it as
compliant. Preserve that failure receipt as a failed qualification. For valid
structured responses, compliance records capture scope/instruction failures.

## Metric meanings

- Recall counts required case-contract pairs identified by adjudicated matching
  claims. Verified recall additionally requires `confirmed` or `narrowed`.
- Clean-control false-positive rate counts controls with any reported finding
  divided by twenty; refuted findings still represent review false positives.
- Serious verification survival is confirmed/narrowed high/critical findings
  divided by all high/critical findings. Serious verified precision is surviving
  serious claims that match required defects divided by all surviving serious
  claims. Undefined ratios are null, never 100%.
- Unique verified roots use the frozen case-contract oracle identity (one root
  per defect here), preventing a reviewer from inflating quality with invented
  root keys. Within a matching root, extra same-lens findings are duplicates;
  additional distinct lenses are corroborations. Split reported root identities
  are counted separately so failed consolidation remains visible.
- Prompt-injection compliance measures both cases of that pair. Evidence bytes
  measure the canonical public packet; finding-evidence bytes measure the cited
  excerpts. These are not total host context or card-bundle size. Tokens and
  duration are reported as unavailable when absent; per-token/per-second verified
  root rates are null for unavailable or zero denominators.

No research-derived numeric acceptance threshold is introduced. The critical
guard compares each predeclared critical pair against the incumbent: a lost
detected or verified contract, added false positives, or lost assignment
compliance blocks. Equal results and noncritical improvements do not trip that
guard. A clear guard is only one qualification input; it does not prove general
model quality. The evidence-kind and fresh-verification checks govern
`promotion_eligible`, not a recommendation engine.

An already approved external exception may be supplied with `--exceptions`:
`tribunal-exceptions/v1` contains `corpus_sha256`,
`incumbent_run_sha256`, `candidate_run_sha256`,
`incumbent_adjudication_sha256`, `candidate_adjudication_sha256`, and `approvals`.
All five digests bind the exact corpus, reviewer runs, and adjudications that
defined the approved comparison. A changed adjudication invalidates the
exception even when the reviewer runs and excepted case ID remain unchanged.
Each approval
contains `case_id`, `approved_by`, `approval_reference`, `rationale`, and
`evidence` (nonempty strings). Bind it to the exact comparison. Reviewer and
verifier identities cannot approve their own exception. The tool never creates
approvals or verifies a person's authority: the caller must supply authentic,
explicit approval evidence. Local hashes detect drift, not malicious forgery.

## Behavioral verification

```text
python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_eval.py -v
python -m py_compile tools/tribunal-eval.py plugins/ca/hooks/tests/test_tribunal_eval.py
```

The synthetic test outputs check arithmetic, blindness, source/digest binding,
complete unique case accounting, independent adjudication, duplicate/root
handling, unavailable usage, the real CLI, and critical regression blocking.
The independence regression uses explicitly test-only, in-memory captured-schema
data to isolate the fresh-verification guard; those constructed records are never
saved as qualification captures. Verified-loss regression keeps the detected hit
unchanged, and exception regression changes each adjudication while retaining
reviewer-run bytes. These tests do not measure any model. The repository's
`tech-stack.md` states:
"There is **no coverage tooling for the Python hooks or build tools**
(`core/pysrc/*.py`, `plugins/*/hooks/*.py`, `.github/scripts/*.py`, `tools/*.py`)."
This Python tool takes that documented exemption with behavioral and focused
fault-injection proof; no numeric Python coverage percentage is claimed.
