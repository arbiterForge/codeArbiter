# Debug handoff contract: proposed closed model

Status: Reviewed design input only. No runtime validator, native artifact kind, or approval is implemented by this document.  
Protocol: `codearbiter.debug-handoff/1.0.0` (proposed, not a released version)  
Parent specification: [SPEC.md](SPEC.md), R08-R13  
Verification cases: [SCENARIOS.md](SCENARIOS.md), especially V19-V22 and V37-V40  
D1 finite primitive/process profile: [D1-PROFILE.md](D1-PROFILE.md); frozen controls: [D1-CASES.json](D1-CASES.json)

## 1. Representation and single owner

The packet is transient JSON carried through an existing session/tool-input channel. It is not a repository file or proof receipt. Every object is closed: all listed fields are required, no additional properties are accepted, and nullable fields must explicitly contain null when unknown. Arrays have the stated ceilings; these are not content targets.

Implement the finite model once in the shared standard-library Python library. Generate the JSON Schema and field-reference projection from those same definitions. The implementation must not maintain two independent runtime validators or create a general-purpose schema interpreter. This document fixes the reviewed behavior; the generated schema alone cannot enforce cross-record semantics, input-byte limits, duplicate-key rejection, or authority.

No caller may provide a schema path, remote reference, executable path, new extension fields, approval flags, or producer-selected authority kind. Unknown protocol versions fail explicitly. The validator neither dereferences a locator nor runs a recorded operation.

## 2. Primitive profile

- `text(N)`: Unicode string with at least one non-whitespace character and at most N Unicode code points. No unpaired surrogate code points. Leading/trailing text is preserved, not silently repaired.
- `nullable(T)`: T or null, never an omitted required field.
- `refs(P,N)`: array of distinct identifiers of namespace P; minimum zero and maximum N unless a semantic rule requires a member.
- Namespace identifiers are full-string matches: `S-`, `E-`, `H-`, or `C-`, followed by 2-4 ASCII decimal digits. Case identity is `DBG-` followed by one ASCII alphanumeric character and then 2-63 ASCII alphanumeric, underscore, or hyphen characters. A regex match ending before a final newline is not a full match.
- `git_oid`: exactly 40 or 64 lowercase hexadecimal characters. It identifies supplied source evidence, not necessarily the executing/deployed artifact.
- `sha256`: `sha256:` followed by exactly 64 lowercase hexadecimal characters.
- `timestamp`: timezone-bearing date-time in the finite `debug-rfc3339/1` profile defined by D1-PROFILE.md. Date/time values must actually be checked, not merely labeled with an annotation. Implementation tests must verify the frozen fractional-second/offset cases and calendar validity against the selected conformance checker; do not silently claim broader date-time conformance. Timestamps are observations, not currentness or authority by themselves.
- `integer`: finite mathematically integral JSON number. Thus 0.0 is an integer value under the reference JSON Schema interpretation; true/false are never integers. No NaN/Infinity. The production implementation and conformance checker must agree rather than accidentally relying on Python's bool subclassing or requiring integer lexical spelling only.
- Global serialized-input ceiling: 65,536 UTF-8 bytes. Read no more than the limit plus one byte before rejecting oversize input. Container nesting ceiling: 16, counting the root object as level 1, each child object/array as one additional level, and scalars as adding no container level. Reject escaped unpaired surrogates, malformed UTF-8/JSON, duplicate keys, and excess input. Do not silently truncate or coerce.

T03's primitive/process choices are frozen in D1-PROFILE.md. Its timestamp subset, exact-number and Unicode semantics, fingerprint omission/inspection boundary, and private output protocol complete this contract. D1-CASES.json fixes positive and negative controls. Implementation and reference-conformance checks remain required; do not claim full RFC3339 acceptance or use binary-float loading to erase numeric counterexamples. No native approval is implied.

## 3. Top-level object

| Field | Type and limits |
|---|---|
| protocol | Exact protocol string above. |
| case_id | Full-match case identity above. |
| request | Request. |
| snapshots | Array of Snapshot, 0-4. |
| symptom | Symptom. |
| reproduction | Reproduction. |
| hypotheses | Array of Hypothesis, 0-16. |
| checks | Array of Check, 0-24. |
| evidence | Array of Evidence, 1-32. An initial user report is valid evidence of a report, not proof of causation. |
| disposition | Disposition. |
| next_step | NextStep. |
| regression | nullable(Regression). |

### Request

| Field | Type |
|---|---|
| intent | `diagnosis_only` or `repair_requested`. This is a reported label, not permission. |
| request_ref | text(512), locator for the request being reported. |
| scope | text(2000). |
| restrictions | Array of text(500), 0-12. |

### Snapshot

| Field | Type |
|---|---|
| id | S identifier. |
| repository | text(512), observed repository identifier or explicitly described unknown, not an executable URL. |
| worktree | text(512), observed worktree identity/label or explicitly described unknown. |
| commit | nullable(git_oid). |
| dirty_state | `clean`, `dirty`, or `unknown`. |
| fingerprint | nullable(sha256). |
| fingerprint_recipe | nullable(text(160)). |
| runtime_identity | nullable(text(500)), kept distinct from local source commit. |
| limitations | nullable(text(1500)). |

Unknown identities require meaningful limitations. Fingerprint and recipe must be both present or both null. A non-null recipe names a documented local versioned computation, not a network schema or arbitrary instruction. No secret values are hashed as environmental proof. Unknown/ignored inputs remain limitations. A consumer rechecks relevant current state even when a fingerprint is present.

### Symptom

| Field | Type |
|---|---|
| observed | text(1500). |
| expected | nullable(text(1500)). |
| expected_evidence_ids | refs(E,32). |

### Recipe

| Field | Type |
|---|---|
| steps | Array of text(500), 1-8. |
| cwd | text(512). |
| preconditions | text(1000). |
| failure_signature | text(1000). |

Recipe steps are inert descriptions, not executable authority.

### Reproduction

| Field | Type |
|---|---|
| status | `reproduced`, `intermittent`, `not_yet_reproduced`, `unsafe_to_replay`, or `unavailable`. |
| recipe | nullable(Recipe). |
| evidence_ids | refs(E,32). |
| limitations | nullable(text(1500)). |

`reproduced` requires a Recipe and supporting executed-observation evidence. `unsafe_to_replay` and `unavailable` require a limitation. A planned check, report label, or status value is not execution evidence. Intermittent evidence states trial limits; it is not a deterministic proof claim.

### Hypothesis

| Field | Type |
|---|---|
| id | H identifier. |
| mechanism | text(2000). |
| discriminator | text(1500). |
| status | `supported`, `refuted`, or `inconclusive`. |
| supporting_evidence_ids | refs(E,32). |
| opposing_evidence_ids | refs(E,32). |
| limitations | nullable(text(1500)). |

Supported requires supporting evidence; refuted requires opposing evidence. Distinct observations from one file may be separate records. Do not give the same observation both roles for one hypothesis merely to satisfy the structure.

### Check

| Field | Type |
|---|---|
| id | C identifier. |
| operation | text(2000), recorded command/action, never executed by validation. |
| cwd | nullable(text(512)). |
| status | `planned`, `completed`, `not_run`, or `interrupted`. |
| exit_code | nullable(integer). |
| expectation | text(1500), expected discriminator. |
| observed | nullable(text(1500)). |
| evidence_ids | refs(E,32). |
| authorization_basis | nullable(text(1000)), reported basis only. |
| side_effects | text(1500), observed/expected effect boundary and limitations. |

Completed requires an observation; process exit may remain null when the action genuinely has no process exit code. Planned/not_run require null observation and exit code. Interrupted is never a successful completed check, even if an intermediate child emitted zero. Do not convert cancellation or timeout into green.

### Evidence

| Field | Type |
|---|---|
| id | E identifier. |
| kind | `source`, `observation`, `user_report`, `command_result`, or `contract`. |
| snapshot_id | nullable(S identifier). |
| locator | text(1000). |
| observation | text(2000). |
| observed_at | nullable(timestamp). |
| check_id | nullable(C identifier). |
| coverage | `complete_for_claim`, `partial`, or `unknown`. |
| limitations | nullable(text(1500)). |

A command_result requires a check_id resolving to an actually executed check. Evidence and check references must not describe contradictory executions. Missing source/time identity or incomplete capture requires an appropriate limitation. `complete_for_claim` remains a claim to inspect, not a validator-issued guarantee.

### Blocker

| Field | Type |
|---|---|
| kind | `access`, `evidence`, `authority`, `capability`, `safety`, `scope`, `budget`, or `input`. |
| missing | text(1500), the missing discriminator/prerequisite. |
| owner | nullable(text(300)). |
| resume_condition | text(1500). |

### Disposition

| Field | Type |
|---|---|
| kind | `confirmed_code_defect`, `confirmed_noncode_cause`, `design_question`, `no_action`, or `unresolved`. |
| rationale | text(2000). |
| evidence_ids | refs(E,32). |
| cause_ids | refs(H,16). |
| blockers | Array of Blocker, 0-8. |

Code and non-code confirmation require supporting cause(s) and evidence. Design/no-action require supporting evidence. Unresolved requires a blocker. No-action has no blocker requiring continuation. Confirmation can include a blocker on repair authority without erasing the diagnosis.

### NextStep

| Field | Type |
|---|---|
| target | `none`, `fix`, `adr`, `existing_owner`, or `evidence`. |
| owner | nullable(text(300)). |
| action | nullable(text(1500)). |
| completion_evidence | nullable(text(1500)). |

This is a recommendation, not proof of dispatch. `existing_owner` requires a non-null actual owner name. If none is known, use the evidence target with an explicit missing-owner statement and next action. Any target other than none requires non-null action and completion_evidence. A none target carries null owner/action/completion_evidence and cannot conceal a required next action.

### Regression

| Field | Type |
|---|---|
| basis | `reproduction` or `causal_trace`. |
| snapshot_id | S identifier. |
| obligation | text(2000). |
| oracle | text(1500). |
| candidate_test_id | nullable(text(500)). |
| reuse_existing | boolean. |
| evidence_ids | refs(E,32), at least one. |

`reuse_existing: true` requires candidate_test_id and supporting evidence that the named existing test is adequate target-red evidence. A merely suggested existing test can be named with reuse_existing false until checked. Fix revalidates current applicability and actual red before implementation. Reproduction basis refers to the observed failure, not just an expectation record; causal-trace basis carries current source/contract evidence and a concrete test obligation without claiming a replay that did not happen.

## 4. Outcome matrix

| Disposition | Regression | NextStep | Required supporting structure |
|---|---|---|---|
| confirmed_code_defect | Present. | fix, actionable. | Non-null expected behavior with expectation references; relevant snapshot; supported cause(s); defect/causal evidence; regression oracle and basis. |
| confirmed_noncode_cause | Null. | existing_owner or evidence, actionable. | Supported cause(s), evidence, actual owner or explicit absence; continuation blockers retained. |
| design_question | Null. | adr or evidence, actionable. | Specific intended-behavior question, evidence, no assumed ADR approval. |
| no_action | Null. | none, all subordinate fields null. | Positive supporting evidence; no required blocker or remaining action. |
| unresolved | Null. | evidence, actionable. | At least one missing discriminator/prerequisite with resume condition, owner when known. No invented cause needed. |

These are transfer conditions. They never allow data to assert permission to carry out the next step. A diagnosis-only case can correctly recommend fix while the actual caller stops after returning it.

## 5. Semantic rule ledger

Preserve the original identities. Each rule requires focused negative testing of the production validator or the specified outer boundary. Judgment requirements are not falsely presented as mechanically proven.

| ID | Invariant |
|---|---|
| SEM-01 | Snapshot, evidence, hypothesis, and check IDs are unique within namespaces; every non-null reference resolves. |
| SEM-02 | Code defects have expected behavior and expectation references; references identify the expectation, not an approval flag. Meaning is checked by the consumer/reviewer. |
| SEM-03 | Supported/refuted hypotheses have corresponding evidence; one observation cannot be both support and opposition for the same hypothesis without separating observations. |
| SEM-04 | Confirmed code/non-code dispositions name supported causes and include their cited supporting observations in disposition evidence. |
| SEM-05 | Code-defect handoff includes regression, relevant snapshot, oracle, and evidence for its reproduction/causal basis. Other outcomes have no repair-ready regression. |
| SEM-06 | Reproduced includes recipe and an executed observation; planned checks are insufficient; unsafe/unavailable state has a limitation. |
| SEM-07 | Completed checks have observations; planned/not_run have no result/exit; interrupted is not passing; command_result points to an executed check. |
| SEM-08 | Unresolved includes missing discriminator/prerequisite, resume condition, and actionable next step or explicit missing-owner treatment. |
| SEM-09 | No-action has positive evidence, no regression, no required continuation blocker, and no action/mutation target. Evidence sufficiency is not inferred by schema. |
| SEM-10 | Design names an intended-behavior decision, not authorization; non-code names an owner or its explicit absence, not execution authority. |
| SEM-11 | Unknown source/runtime/fingerprint facts have limitations. Confirmation cannot rely solely on a user-report label where observed/source proof is required. |
| SEM-12 | All identifiers, paths, locators, recorded operations, intent labels, and digests are inert; no execution, external load, access confirmation, or authority in validation. |
| SEM-13 | Exact byte/count/depth/field/type/profile boundaries, strict decoding, duplicate-key and non-finite rejection. |
| SEM-14 | Producer and consumer use the same protocol; actual freshness and authority checks occur outside pure validation, never by accepting a self-asserted packet field. |
| SEM-15 | Preserve contradictory/insufficient evidence as limitations; do not drop it to pass validation or claim algorithmic proof of causation. |
| SEM-16 | Reusing an existing regression requires a test identity and cited adequate red evidence; a suggested candidate is not a proven reusable baseline. |
| SEM-17 | Every non-none next step is actionable and has completion evidence; existing_owner has an owner; none is empty of required work. |
| SEM-18 | Fingerprint/recipe nullability is paired; non-null recipe is versioned and documented; unavailable identity remains limited rather than fabricated. |
| SEM-19 | Identifiers match the entire string; timestamp format is asserted; Unicode/numeric handling is explicit and agrees across generated schema and runtime. |

SEM-16 through SEM-19 clarify acceptance already required by AC-07, AC-10, AC-13 through AC-16, and AC-18. They do not introduce a persisted artifact family or a new authorization mechanism.

## 6. Proposed private API and process boundary

Placement choices for native planning:

- `core/pysrc/_debughandofflib.py`: finite definitions, strict decoder, shape/semantic validation, deterministic diagnostics; no import-time effects.
- `core/pysrc/debug-handoff.py`: thin stdin/stdout wrapper. Its installed copies live in the existing host hooks directories but it is not a registered hook or public command.
- `core/surface/skills/debug/references/handoff.md` and `debug-handoff.schema.json`: on-demand generated reference/projection.
- `core/surface/includes/helper-invocation.md`: bounded shared invocation guidance for affected callers, only if existing guidance cannot own it without duplication.

The proposed invocation is the resolved Python 3 executable with `-B`, the absolute trusted installed helper path, and the literal `validate` operation. Packet bytes arrive on stdin. No project-root argument is needed for pure validation; no packet path or schema path is accepted. The wrapper sets bytecode suppression before importing any local module as a defense in depth. The invocation is a private helper operation, not a new model tool or registered skill.

Output is one bounded JSON result using `codearbiter.debug-validation/1.0.0`, with the exact closed envelope, error-code ordering, and interrupted/broken-output treatment in D1-PROFILE.md:

- valid: true with an empty errors list and exit 0;
- invalid input: valid false, fixed error code plus bounded field path, exit 2;
- internal/helper failure: valid false with a fixed non-sensitive error code, exit 3.

At most 16 diagnostic rows and 8,192 output bytes; no payload values, full packet echo, arbitrary exception messages, or tracebacks. Preserve the original nonzero status without retrying through another interpreter. Diagnostics must be deterministic for identical bytes. This response attests only to validation, never to authorization, causal truth, freshness, or a passing regression.

The wrapper may read its own installed code and stdin; the decoder/validator must not read project files, create files/cache, start subprocesses, or contact the network. Test with a read-only installed directory, redirected cache locations, denied socket/process calls, before/after filesystem checks, and a secret canary in rejected input. An unavailable helper permits an honest capability explanation but blocks the validated handoff and repair.

The consumer performs current-source, caller-intent, authority, and regression-proof checks through existing owners/tools separately. Do not move those effects into this validator or manufacture a simulated consumer that is never used by the real fix path.

## 7. Compatibility and implementation acceptance

The proposal changes no stored data. Legacy prose is evidence input that may be normalized in memory; missing details remain unknown. Unknown protocol is rejected rather than treated as an older shape. No automatic persistence, historical note migration, or packet-as-approval interpretation.

Tests must differentially check generated-schema shape and production validation where their domains overlap, while separately exercising strict decoding and cross-record semantics. The original v1 reference schema intentionally accepted semantic-invalid examples; that distinction remains visible. Do not label every schema-accepted mutant a runtime vulnerability. New V37-V40 probes target explicit contract gaps or specified mechanical obligations.

A source-checked contract is not an installed journey. Verify generated public and private invocation locations, the actual trusted helper, literal argv/stdin delivery, and the real fix/TDD consumer under each claimed host. No source-path rescue, unapproved provider use, or inferred platform qualification is allowed.
