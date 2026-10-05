# Tribunal vNext qualification — 2026-10-05

PR #887 implements `SPEC-TRIBUNAL-VNEXT-001` on the existing branch. Local
implementation and distribution checks pass. The recorded comparison found no
critical regression: both configurations detected and independently verified all
20 seeded defects, with no findings on 20 clean controls. This is parity on the
small diagnostic corpus, not evidence of improved general detection accuracy.
Merge and publication remain deferred to the owner.

## Delivered behavior

- Source-bound runs reject changed inputs and allocate exclusive directories.
  Report completion is separate from filing and telemetry follow-up completion.
- Deterministic inventory reads repository facts without executing project code.
  Host-supplied profiles distinguish fresh threads from native agent registration
  and preserve unavailable settings and usage as explicit limits.
- Thirteen cards add semantic-contract and change-closure. Coverage and
  test-fidelity share verification-quality guidance and retain their names/URLs.
- Serious claims require independent verification before confirmed fix work.
  Leads, dispositions and root-cause grouping survive interruption. Filing and
  aggregate telemetry keep their separate explicit authorization.

## Fresh deterministic verification

The coordinator independently ran these checks against the delivered changes:

| Check | Result |
| --- | --- |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_tribunal*.py" -v` | 87 tests PASS, 54.091s |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*_tribunal_usage.py" -v` | 34 tests PASS, 0.087s, rebuilt host instructions |
| Card/workflow tests after the resource-notation correction | 14 + 10 tests PASS, 0.008s + 11.663s |
| `.github/scripts/test_build_surface.py -k tribunal` after correction | 6 tests PASS, 1.135s |
| `.github/scripts/test_host_descriptors.py -k version` | 2 tests PASS, 0.022s |
| Separate real CLI exercise in a disposable Git repository | 19 operations PASS: inventory, profiles, costs, leads, resume, follow-ups, terminal state and drift write refusal |
| `tools/sync-core.py --check`, `tools/build-surface.py --check`, `tools/build-host-packages.py --check` | PASS; 88 core files across all three hosts byte-identical |
| `.github/scripts/check-plugin-refs.py` | PASS; full plugin reference graph, including generic and literal Codex agent routes |
| Command-route declarations, badge and catalog checks | PASS |
| Codex inert candidate package/resource contract before the delivery-hook correction | PASS; package digest `f5c8659e3a28c98311f8f026c4775b52e3fbe06b90664e51b132555d43709ba1` |
| Three focused site suites: lens pages, reference sidebar, trust-policy claims | 32 tests PASS |
| Site typecheck, build, internal link audit | PASS; 173 built pages, 13 lens pages, search over 192 pages; 34,976 internal links resolve |

The existing site checks preserve all eleven historical lens/agent URLs and
exercise both new generated pages and their index/command/sidebar links.
No instrumented production TypeScript changed. Python uses the declared
`tech-stack.md` exemption: "There is **no coverage tooling for the Python hooks
or build tools** (`core/pysrc/*.py`, `plugins/*/hooks/*.py`,
`.github/scripts/*.py`, `tools/*.py`)." No numeric Python coverage is claimed.

Independent security, coverage and crypto reviews closed the original component
findings. Corrections include inert signed-history inspection, binding/refusal of
unavailable declared evidence, four drift-checked persisted writers, binding
comparison exceptions to both adjudications, and isolated tests for independent
verification and lost verified recall. Focused removal/forwarding faults failed
at their intended assertions. Original reports and correction histories remain
retained; this report does not relabel failed attempts as successful evidence.

## Recorded comparison

The frozen corpus contains forty synthetic reductions in twenty defect/control
pairs. Fresh actors received the same opaque public packet and their selected
frozen bundle, without private expectations or the other review. A separate fresh
verifier traced every actual finding against the public contracts and files.
Neither review was generated from expected answers, and no fixture program ran.

| Measurement | Incumbent | Candidate |
| --- | ---: | ---: |
| Required defects found / verified | 20 / 20 | 20 / 20 |
| Recall / verified recall | 100% / 100% | 100% / 100% |
| False-positive findings / clean controls flagged | 0 / 0 | 0 / 0 |
| Serious findings surviving verification | 9 / 9 | 5 / 5 |
| Unique verified root causes | 20 | 20 |
| Same-lens duplicates / cross-lens corroborations | 0 / 1 | 0 / 0 |
| Split root identities | 0 | 0 |
| Prompt-injection case assignment compliance | 100% | 100% |
| Public evidence bytes | 29,750 | 29,750 |
| Frozen configuration bytes (canonical JSON) | 65,421 | 116,245 |
| Finding-evidence bytes | 7,338 | 7,380 |
| Controller-observed task seconds | 362.955 | 426.193 |
| Exact model / token counts | unavailable | unavailable |

All 21 incumbent and 20 candidate claims were independently confirmed. Different
serious-finding counts are observed severity assignments, not proof of better
severity calibration. The candidate configuration is larger; no cost or speed
improvement is claimed. The observed time includes scheduling, handoff and
controller processing, not only inference. Both actors inherited the same
configured model without requested overrides. A single saturated synthetic
comparison cannot establish broader recall, false-positive rate or efficiency.
Assignment compliance is judged from the supplied evidence/results; the verifier
did not receive review tool histories. Prompt obedience outside this exercise
is not proven.

The offline critical-case gate is **clear**, with no regressions and no exception
approvals. It permits this bounded comparison; it does not publish a configuration.

| Canonical binding | SHA-256 |
| --- | --- |
| Corpus | `ba54b81610a64ccfaa589a4822b264d47c92c11f34c41c013f764c8f1ea1fea2` |
| Public packet | `1c1f18136a9043c85f63296ca37b9b9d1a69e2d58781e5ded68ff61ae242465a` |
| Incumbent run | `c6df7a16734fc7f9a55f84dfae7d4522d11442db2d9b764549e44ce91f137cb9` |
| Candidate run | `a2bac779cd331cd2c2c425241359cce2ee972575488f7a54d2f94f349fdb122f` |
| Incumbent adjudication | `bd493a2fd12b48fdc15e44224ae407d14938944f047399e5267f05a676cb4456` |
| Candidate adjudication | `42b67e1488ecdf61dfa7d29cfc125b49a570bdbefa854613ebbd77a64802e70f` |

All [captures, frozen bundles, controller receipts and the reproducible comparison](../../.github/fixtures/tribunal/qualification/README.md)
are checked in. Raw reviews are preserved; the final run objects differ only by
controller-observed duration. Unknown model/token fields remain null.

Final package checking found and fixed a reference-format integration defect:
42 links in 19 canonical files had been double-wrapped by Codex rendering. The
captured candidate bundle is preserved exactly. A separate delivered bundle and
mechanical-delta receipt prove that only link notation changed, preserving every
label, path and all other text. The model comparison predates that formatting
correction; it was not rerun or silently rebound to different bytes. Fresh
resource, projection, card, workflow and site checks cover the delivered notation.

## Delivery-hook correction

The actual commit gate exposed a shared-hook parsing defect: the freshness probe
emitted multiple stale registrations on separate lines, while its shell consumer
matched space-delimited names. Native Windows CRLF also needed normalization.
A two-line correction in the canonical hook generator and its three copies fixes
that consumer without changing the probe, ownership policy or security markers.

The named real-hook regression failed with H-09b before the correction, then
passed with the same test bytes. It also requires the current enforcer to reject
an unapproved migration with H-14. Nine focused tests, syntax and generator parity
pass. The coordinator independently reran the three freshness tests; independent
security and coverage reviews found no remaining issue. A reviewer omitted the
selected enforcer invocation only in a temporary fixture, and the migration
assertion failed as intended.

The reviewed normal installer refreshed both local managed shims. All registered
paths, freshness timestamps and trusted executable identities remained unchanged;
the actual managed pre-commit and feature commit then passed. This local repair
does not install a plugin release or alter another checkout's source.

The final inert Codex candidate contract passes at package digest
`b49790e3f09e07f911b0b2cfe90ccfad3618f12049d7e60196612ffa9a429470`.
The previous digest above preserves the pre-correction check. The model-capture
bundles do not include this hook helper, so their original bindings remain intact.

## Distribution boundary

Prepared package versions: ca **2.25.0**, ca-codex **0.16.0**, ca-pi **0.17.0**.
The external supported Pi version remains **1.0.2**. The dependency review found
only version metadata changes: no new dependencies, graphs, lifecycle scripts or
entry points. No new mandatory CI job or live model evaluation is introduced.

Local validation is not hosted qualification. The PR must show the required
checks for its final pushed commit before merge; that receipt belongs in the PR
status, not a self-referential commit claim in this file. No release, tag,
deployment or merge is claimed here.
