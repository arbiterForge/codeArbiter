# Recorded Tribunal comparison, 2026-10-05

These are actual static review captures for PR #887, using the forty-case frozen
public packet. The incumbent and candidate actors received only that packet and
their respective frozen configuration bundle. They did not receive the private
case labels, oracle, scorer, or each other's output. A separate fresh verifier
then traced every finding against the public contracts and files, without the
private oracle or either configuration bundle. No fixture code was executed.

`*-raw.json` preserves each actor's original review. `*-run.json` changes only
`duration_seconds`, using the controller's recorded dispatch-to-observed-completion
wall time in `*-dispatch.json`. That duration includes scheduling and handoff
latency, not just inference. Exact model identity and tokens were unavailable and
remain null; both actors inherited the same configured model without overrides.

The JSON scorer uses canonical SHA-256 bindings, including the exact final runs
and independent adjudications. The candidate bundle identifies the reviewed
working-tree content before its containing commit. The bundles preserve that
content even after the branch receives a commit hash. This is a single small
synthetic diagnostic comparison, not a general or statistical quality claim.

Reproduce the retained comparison from the repository root (read-only stdout):

```sh
python tools/tribunal-eval.py compare --incumbent .github/fixtures/tribunal/qualification/incumbent-run.json --incumbent-adjudication .github/fixtures/tribunal/qualification/incumbent-adjudication.json --candidate .github/fixtures/tribunal/qualification/candidate-run.json --candidate-adjudication .github/fixtures/tribunal/qualification/candidate-adjudication.json
```

No synthetic-evidence flag or exception approval is used. The comparison gate is
limited to critical-case regression; it does not authorize publishing or merging.
The [qualification report](../../../../.codearbiter/reports/2026-10-05-tribunal-vnext-qualification.md)
explains the measured result and deterministic delivery checks.

Final package validation subsequently corrected resource-link notation in 19
canonical files (42 links) so Codex no longer emitted nested Markdown links.
`candidate-resource-correction.json` and `candidate-delivered-bundle.json` retain
the exact mechanical delta: every label, target and all other content is preserved.
The benchmark remains bound to its original pre-format-correction bundle; its
findings were not rerun or edited. Package reference/parity checks independently
verify the delivered notation.

`launch-evidence.json` retains selected fields from the actual native collaboration
launch calls and their tool responses: all three used fresh contexts (`fork_turns:
none`) without model/reasoning overrides. The three assignment exports retain the
actual declared input boundaries, with only the controller temporary-directory
prefix redacted. Original/export hashes are recorded. Encrypted native launch
messages and unrelated session content are not exported; these records do not
claim a complete child tool trace or a cryptographic host attestation.
