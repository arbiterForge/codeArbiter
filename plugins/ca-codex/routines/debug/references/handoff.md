# Debug handoff field reference

Generated from the finite `_debughandofflib.MODEL` definitions.
The JSON Schema projects shape and scalar profiles. Cross-record SEM
rules, strict byte decoding, causal truth, freshness, and authority remain
separate obligations of the validator and its consumers.

Protocol: `codearbiter.debug-handoff/1.0.0`.

## blocker

| Field | Profile |
|---|---|
| `blocker.kind` | `enum(access, evidence, authority, capability, safety, scope, budget, input)` |
| `blocker.missing` | `text(1500)` |
| `blocker.owner` | `nullable(text(300))` |
| `blocker.resume_condition` | `text(1500)` |

## check

| Field | Profile |
|---|---|
| `check.authorization_basis` | `nullable(text(1000))` |
| `check.cwd` | `nullable(text(512))` |
| `check.evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `check.exit_code` | `nullable(integer)` |
| `check.expectation` | `text(1500)` |
| `check.id` | `check_id` |
| `check.observed` | `nullable(text(1500))` |
| `check.operation` | `text(2000)` |
| `check.side_effects` | `text(1500)` |
| `check.status` | `enum(planned, completed, not_run, interrupted)` |

## disposition

| Field | Profile |
|---|---|
| `disposition.blockers` | `array(object(blocker), 0..8)` |
| `disposition.cause_ids` | `refs(hypothesis_id, 0..16, unique)` |
| `disposition.evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `disposition.kind` | `enum(confirmed_code_defect, confirmed_noncode_cause, design_question, no_action, unresolved)` |
| `disposition.rationale` | `text(2000)` |

## evidence

| Field | Profile |
|---|---|
| `evidence.check_id` | `nullable(check_id)` |
| `evidence.coverage` | `enum(complete_for_claim, partial, unknown)` |
| `evidence.id` | `evidence_id` |
| `evidence.kind` | `enum(source, observation, user_report, command_result, contract)` |
| `evidence.limitations` | `nullable(text(1500))` |
| `evidence.locator` | `text(1000)` |
| `evidence.observation` | `text(2000)` |
| `evidence.observed_at` | `nullable(timestamp)` |
| `evidence.snapshot_id` | `nullable(snapshot_id)` |

## hypothesis

| Field | Profile |
|---|---|
| `hypothesis.discriminator` | `text(1500)` |
| `hypothesis.id` | `hypothesis_id` |
| `hypothesis.limitations` | `nullable(text(1500))` |
| `hypothesis.mechanism` | `text(2000)` |
| `hypothesis.opposing_evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `hypothesis.status` | `enum(supported, refuted, inconclusive)` |
| `hypothesis.supporting_evidence_ids` | `refs(evidence_id, 0..32, unique)` |

## next_step

| Field | Profile |
|---|---|
| `next_step.action` | `nullable(text(1500))` |
| `next_step.completion_evidence` | `nullable(text(1500))` |
| `next_step.owner` | `nullable(text(300))` |
| `next_step.target` | `enum(none, fix, adr, existing_owner, evidence)` |

## packet

| Field | Profile |
|---|---|
| `packet.case_id` | `case_id` |
| `packet.checks` | `array(object(check), 0..24)` |
| `packet.disposition` | `object(disposition)` |
| `packet.evidence` | `array(object(evidence), 1..32)` |
| `packet.hypotheses` | `array(object(hypothesis), 0..16)` |
| `packet.next_step` | `object(next_step)` |
| `packet.protocol` | `const(codearbiter.debug-handoff/1.0.0)` |
| `packet.regression` | `nullable(object(regression))` |
| `packet.reproduction` | `object(reproduction)` |
| `packet.request` | `object(request)` |
| `packet.snapshots` | `array(object(snapshot), 0..4)` |
| `packet.symptom` | `object(symptom)` |

## recipe

| Field | Profile |
|---|---|
| `recipe.cwd` | `text(512)` |
| `recipe.failure_signature` | `text(1000)` |
| `recipe.preconditions` | `text(1000)` |
| `recipe.steps` | `array(text(500), 1..8)` |

## regression

| Field | Profile |
|---|---|
| `regression.basis` | `enum(reproduction, causal_trace)` |
| `regression.candidate_test_id` | `nullable(text(500))` |
| `regression.evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `regression.obligation` | `text(2000)` |
| `regression.oracle` | `text(1500)` |
| `regression.reuse_existing` | `boolean` |
| `regression.snapshot_id` | `snapshot_id` |

## reproduction

| Field | Profile |
|---|---|
| `reproduction.evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `reproduction.limitations` | `nullable(text(1500))` |
| `reproduction.recipe` | `nullable(object(recipe))` |
| `reproduction.status` | `enum(reproduced, intermittent, not_yet_reproduced, unsafe_to_replay, unavailable)` |

## request

| Field | Profile |
|---|---|
| `request.intent` | `enum(diagnosis_only, repair_requested)` |
| `request.request_ref` | `text(512)` |
| `request.restrictions` | `array(text(500), 0..12)` |
| `request.scope` | `text(2000)` |

## snapshot

| Field | Profile |
|---|---|
| `snapshot.commit` | `nullable(git_oid)` |
| `snapshot.dirty_state` | `enum(clean, dirty, unknown)` |
| `snapshot.fingerprint` | `nullable(sha256)` |
| `snapshot.fingerprint_recipe` | `nullable(recipe_name)` |
| `snapshot.id` | `snapshot_id` |
| `snapshot.limitations` | `nullable(text(1500))` |
| `snapshot.repository` | `text(512)` |
| `snapshot.runtime_identity` | `nullable(text(500))` |
| `snapshot.worktree` | `text(512)` |

## symptom

| Field | Profile |
|---|---|
| `symptom.expected` | `nullable(text(1500))` |
| `symptom.expected_evidence_ids` | `refs(evidence_id, 0..32, unique)` |
| `symptom.observed` | `text(1500)` |
