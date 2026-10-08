package observation

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func testDigest(seed string) string { return canonical.BytesHash([]byte(seed)) }

func subject() map[string]any {
	return map[string]any{"artifact_id": "PLAN-EXAMPLE", "normative_sha256": testDigest("plan"), "record_id": "T-001"}
}

func commandResult() map[string]any {
	return map[string]any{"definition_sha256": testDigest("command"), "exit": int64(0), "tests": []any{map[string]any{"name": "TestOne", "status": "pass"}}, "stdout_sha256": testDigest("stdout"), "stderr_sha256": testDigest("stderr")}
}

func verificationProducerResult() map[string]any {
	executable, _ := os.Executable()
	root := filepath.Dir(executable)
	snapshot := map[string]any{"root": root, "filesystem_id": "1:2", "git_common_dir": root, "git_common_filesystem_id": "1:3", "head": "0123456789abcdef", "status_sha256": testDigest("status"), "content_sha256": testDigest("content")}
	return map[string]any{
		"environment_sha256": testDigest("environment"),
		"command_bindings":   []any{map[string]any{"definition_sha256": testDigest("command"), "argv": []any{executable, "test", "./..."}, "cwd": root, "cwd_filesystem_id": "1:4", "workspace_root": root, "workspace_filesystem_id": "1:2", "git_common_dir": root, "git_common_filesystem_id": "1:3", "executable_sha256": testDigest("executable")}},
		"workspace_before":   []any{snapshot}, "workspace_after": []any{snapshot}, "commands": []any{commandResult()},
	}
}

func currentVerificationObservation(contextHash, payloadHash string) map[string]any {
	result := verificationProducerResult()
	resultHash, _ := canonical.Hash(result)
	return map[string]any{
		"format": "codearbiter.observation/0.2.0", "kind": "verification", "subject": subject(),
		"context_ref": ContextRef(contextHash), "context_sha256": contextHash, "payload_sha256": payloadHash,
		"producer_profile": "declared-command/0.1.0", "producer_run_id": "run-00000001",
		"producer_result_sha256": resultHash, "producer_result": result,
	}
}

func testStore(t *testing.T) (*store.FS, string) {
	t.Helper()
	root, err := os.MkdirTemp(".", ".observation-test-*")
	if err != nil {
		t.Fatal(err)
	}
	root, err = filepath.Abs(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(root) })
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { f.Close() })
	return f, root
}

func TestLoadRejectsMutatedContentAddressedObservation(t *testing.T) {
	f, root := testStore(t)
	var err error
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	obs := currentVerificationObservation(contextHash, testDigest("payload"))
	b, _ := canonical.Marshal(obs)
	h := canonical.BytesHash(b)
	p := filepath.Join(root, filepath.FromSlash(Ref(h)))
	if err = os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(p, b, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err = Load(f, Ref(h), h); err != nil {
		t.Fatalf("valid content-addressed observation rejected: %v", err)
	}
	modelResult := obs["producer_result"].(map[string]any)
	modelResult["environment_sha256"] = testDigest("mutated-result")
	b, _ = canonical.Marshal(obs)
	if err = os.WriteFile(p, b, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err = Load(f, Ref(h), h); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
		t.Fatalf("mutated producer result did not break observation identity: %v", err)
	}
}

func TestLegacyObservationIsInspectableButCannotConferAuthority(t *testing.T) {
	f, root := testStore(t)
	var err error
	contextBytes, _ := canonical.Marshal(verificationContext())
	contextHash := canonical.BytesHash(contextBytes)
	legacy := currentVerificationObservation(contextHash, testDigest("payload"))
	legacy["format"] = "codearbiter.observation/0.1.0"
	delete(legacy, "producer_result")
	b, _ := canonical.Marshal(legacy)
	h := canonical.BytesHash(b)
	p := filepath.Join(root, filepath.FromSlash(Ref(h)))
	if err = os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(p, b, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err = Inspect(f, Ref(h), h); err != nil {
		t.Fatalf("legacy observation is not inspectable: %v", err)
	}
	if _, _, err = Load(f, Ref(h), h); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
		t.Fatalf("legacy observation conferred authority: %v", err)
	}
}

func verificationContext() map[string]any {
	command := map[string]any{
		"availability": "proposed", "cwd": ".", "argv": []any{"go", "test", "./..."},
		"expected_exit": int64(0), "assertion": "tests pass", "required_tests": []any{"TestOne"},
	}
	return map[string]any{
		"format": "codearbiter.evidence-context/0.1.0", "activity": "verification", "subject": subject(),
		"input_sha256": testDigest("input"), "input_manifest": map[string]any{"format": "codearbiter.verification-inputs/0.1.0", "engine": "test", "platform": "test/test", "engine_toolchain": "test", "roots": []any{"."}, "exclude_directories": []any{}, "entries": map[string]any{}},
		"spec_sha256": testDigest("spec"), "plan_sha256": testDigest("plan"), "task_sha256": testDigest("task"),
		"task": map[string]any{"id": "T-001"}, "commands": []any{map[string]any{"definition_sha256": testDigest("command"), "definition": command}},
	}
}

func verificationPayload(context map[string]any) map[string]any {
	return map[string]any{
		"input_sha256": context["input_sha256"], "spec_sha256": context["spec_sha256"],
		"task_sha256": context["task_sha256"], "commands": []any{commandResult()},
	}
}

func TestContextAndObservationSchemasAreClosed(t *testing.T) {
	context := verificationContext()
	if es := schema.ValidateWith(ContextSchema(), context); len(es) != 0 {
		t.Fatalf("valid verification context rejected: %v", es)
	}
	context["invented"] = true
	if es := schema.ValidateWith(ContextSchema(), context); len(es) == 0 {
		t.Fatal("unknown evidence-context field accepted")
	}
	delete(context, "invented")
	contextBytes, _ := canonical.Marshal(context)
	obs := currentVerificationObservation(canonical.BytesHash(contextBytes), testDigest("payload"))
	if es := schema.ValidateWith(Schema(), obs); len(es) != 0 {
		t.Fatalf("valid observation rejected: %v", es)
	}
	obs["verdict"] = "passed"
	if es := schema.ValidateWith(Schema(), obs); len(es) == 0 {
		t.Fatal("caller-selected observation verdict accepted")
	}
}

func TestValidateLinkRejectsEveryMutatedBinding(t *testing.T) {
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	payload := verificationPayload(context)
	payloadHash, _ := canonical.Hash(payload)
	base := currentVerificationObservation(contextHash, payloadHash)
	event := map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
	if err := ValidateLink(event, base, context, ContextRef(contextHash), contextHash); err != nil {
		t.Fatalf("valid link rejected: %v", err)
	}
	mutations := map[string]func(map[string]any){
		"kind": func(v map[string]any) { v["kind"] = "spec_review" },
		"subject": func(v map[string]any) {
			v["subject"] = map[string]any{"artifact_id": "PLAN-EXAMPLE", "normative_sha256": testDigest("plan"), "record_id": "T-002"}
		},
		"context_ref":    func(v map[string]any) { v["context_ref"] = ContextRef(testDigest("other-context")) },
		"context_sha256": func(v map[string]any) { v["context_sha256"] = testDigest("other-context") },
		"payload_sha256": func(v map[string]any) { v["payload_sha256"] = testDigest("other-payload") },
		"profile":        func(v map[string]any) { v["producer_profile"] = "codex-review/0.1.0" },
		"producer_result": func(v map[string]any) {
			model := v["producer_result"].(map[string]any)
			model["environment_sha256"] = testDigest("other-environment")
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			candidate, _ := canonical.Clone(base)
			mutate(candidate)
			if err := ValidateLink(event, candidate, context, ContextRef(contextHash), contextHash); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("mutation was not rejected: %v", err)
			}
		})
	}
}

func TestVerificationProducerResultSemanticMutationsAreRejected(t *testing.T) {
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	payload := verificationPayload(context)
	payloadHash, _ := canonical.Hash(payload)
	base := currentVerificationObservation(contextHash, payloadHash)
	event := map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
	for name, mutate := range map[string]func(map[string]any){
		"definition": func(result map[string]any) {
			result["command_bindings"].([]any)[0].(map[string]any)["definition_sha256"] = testDigest("other-definition")
		},
		"argv": func(result map[string]any) {
			result["command_bindings"].([]any)[0].(map[string]any)["argv"] = []any{result["command_bindings"].([]any)[0].(map[string]any)["argv"].([]any)[0], "different"}
		},
		"workspace": func(result map[string]any) {
			result["workspace_after"].([]any)[0].(map[string]any)["status_sha256"] = testDigest("dirty")
		},
		"commands": func(result map[string]any) {
			result["commands"].([]any)[0].(map[string]any)["stdout_sha256"] = testDigest("other-output")
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate, _ := canonical.Clone(base)
			result := candidate["producer_result"].(map[string]any)
			mutate(result)
			resultHash, _ := canonical.Hash(result)
			candidate["producer_result_sha256"] = resultHash
			if err := ValidateLink(event, candidate, context, ContextRef(contextHash), contextHash); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("semantic mutation accepted: %v", err)
			}
		})
	}
}

func TestValidateLinkRejectsVerificationPayloadFromAnotherContext(t *testing.T) {
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	for _, field := range []string{"input_sha256", "spec_sha256", "task_sha256"} {
		t.Run(field, func(t *testing.T) {
			payload := verificationPayload(context)
			payload[field] = testDigest("other-" + field)
			payloadHash, _ := canonical.Hash(payload)
			observed := currentVerificationObservation(contextHash, payloadHash)
			event := map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
			if err := ValidateLink(event, observed, context, ContextRef(contextHash), contextHash); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("verification %s from another context was accepted: %v", field, err)
			}
		})
	}
}

func TestVerificationProducerCannotForgeFrozenExitOrRequiredTests(t *testing.T) {
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	basePayload := verificationPayload(context)
	basePayloadHash, _ := canonical.Hash(basePayload)
	base := currentVerificationObservation(contextHash, basePayloadHash)
	for name, mutate := range map[string]func(map[string]any){
		"wrong exit":            func(command map[string]any) { command["exit"] = int64(1) },
		"missing required test": func(command map[string]any) { command["tests"] = []any{} },
		"extra undeclared test": func(command map[string]any) {
			command["tests"] = append(model.A(command["tests"]), map[string]any{"name": "TestOther", "status": "pass"})
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate, _ := canonical.Clone(base)
			result := model.M(candidate["producer_result"])
			mutate(model.M(model.A(result["commands"])[0]))
			payload := verificationPayload(context)
			payload["commands"] = result["commands"]
			payloadHash, _ := canonical.Hash(payload)
			resultHash, _ := canonical.Hash(result)
			candidate["payload_sha256"] = payloadHash
			candidate["producer_result_sha256"] = resultHash
			event := map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
			if err := ValidateLink(event, candidate, context, ContextRef(contextHash), contextHash); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("self-consistent forged result accepted: %v", err)
			}
		})
	}
}

func TestReviewProducerResultIsSemanticallyBound(t *testing.T) {
	if got := reviewContractHash(); got != "d1e571a86c531ee38e78101452ee5b6148710c7dda5b13cbbc44e4951fd39197" {
		t.Fatalf("review contract drifted from the host producer: %s", got)
	}
	context := verificationContext()
	context["activity"] = "spec_review"
	context["task"] = map[string]any{"id": "T-001", "criterion_refs": []any{"AC-002", "AC-001"}}
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	payload := map[string]any{"assessment": "All required criteria pass."}
	payloadHash, _ := canonical.Hash(payload)
	decision := map[string]any{
		"format": "codearbiter.review-decision/0.1.0", "request_id": testDigest("request"),
		"target_sha256": context["input_sha256"], "contract_sha256": reviewContractHash(), "decision": "pass",
		"coverage": []any{"AC-002", "AC-001"}, "findings": []any{map[string]any{"severity": "INFO", "code": "OK", "message": "Reviewed."}},
		"assessment": payload["assessment"],
	}
	result := map[string]any{
		"launch":   map[string]any{"parent_session_id": "parent", "parent_turn_id": "turn", "tool_use_id": "tool", "post_confirmed": true, "agent_id": "agent-1", "agent_type": "default", "task_name": "review", "fork_turns": "none"},
		"decision": decision,
	}
	resultHash, _ := canonical.Hash(result)
	observed := map[string]any{
		"format": "codearbiter.observation/0.2.0", "kind": "spec_review", "subject": subject(),
		"context_ref": ContextRef(contextHash), "context_sha256": contextHash, "payload_sha256": payloadHash,
		"producer_profile": "codex-review/0.1.0", "producer_run_id": "agent-1", "producer_result_sha256": resultHash, "producer_result": result,
	}
	event := map[string]any{"kind": "spec_review", "subject": subject(), "payload": payload}
	if es := schema.ValidateWith(Schema(), observed); len(es) != 0 {
		t.Fatalf("review observation schema rejected: %v", es)
	}
	if err := ValidateLink(event, observed, context, ContextRef(contextHash), contextHash); err != nil {
		t.Fatalf("valid review observation rejected: %v", err)
	}
	for name, mutate := range map[string]func(map[string]any){
		"agent": func(v map[string]any) { v["producer_run_id"] = "other-agent" },
		"assessment": func(v map[string]any) {
			v["producer_result"].(map[string]any)["decision"].(map[string]any)["assessment"] = "Different."
		},
		"coverage": func(v map[string]any) {
			v["producer_result"].(map[string]any)["decision"].(map[string]any)["coverage"] = []any{"AC-001"}
		},
		"blocking": func(v map[string]any) {
			v["producer_result"].(map[string]any)["decision"].(map[string]any)["findings"] = []any{map[string]any{"severity": "BLOCK", "code": "NO", "message": "Blocked."}}
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate, _ := canonical.Clone(observed)
			mutate(candidate)
			newHash, _ := canonical.Hash(candidate["producer_result"])
			candidate["producer_result_sha256"] = newHash
			if err := ValidateLink(event, candidate, context, ContextRef(contextHash), contextHash); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("review mutation accepted: %v", err)
			}
		})
	}
}

func claudeReviewFixture(t *testing.T) (map[string]any, map[string]any, map[string]any, string) {
	t.Helper()
	context := verificationContext()
	context["activity"] = "spec_review"
	context["task"] = map[string]any{"id": "T-001", "criterion_refs": []any{"AC-001"}}
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	payload := map[string]any{"assessment": "All required criteria pass."}
	payloadHash, _ := canonical.Hash(payload)
	decision := map[string]any{
		"format": "codearbiter.review-decision/0.1.0", "request_id": testDigest("request"),
		"target_sha256": context["input_sha256"], "contract_sha256": reviewContractHash(), "decision": "pass",
		"coverage": []any{"AC-001"}, "findings": []any{}, "assessment": payload["assessment"],
	}
	result := map[string]any{
		"launch": map[string]any{
			"parent_session_id": "session", "parent_prompt_id": "prompt", "tool_use_id": "toolu_1", "post_confirmed": true,
			"agent_id": "agent-1", "agent_type": ClaudeReviewer, "subagent_type": ClaudeReviewer,
			"model": "opus", "resolved_model": "claude-opus-5-5", "first_stop": true,
		},
		"decision": decision,
	}
	resultHash, _ := canonical.Hash(result)
	observed := map[string]any{
		"format": "codearbiter.observation/0.2.0", "kind": "spec_review", "subject": subject(),
		"context_ref": ContextRef(contextHash), "context_sha256": contextHash, "payload_sha256": payloadHash,
		"producer_profile": ClaudeReviewProfile, "producer_run_id": "agent-1", "producer_result_sha256": resultHash, "producer_result": result,
	}
	event := map[string]any{"kind": "spec_review", "subject": subject(), "payload": payload}
	return observed, event, context, contextHash
}

func TestClaudeReviewProfile(t *testing.T) {
	observed, event, context, contextHash := claudeReviewFixture(t)
	if es := schema.ValidateWith(Schema(), observed); len(es) != 0 {
		t.Fatalf("claude review observation schema rejected: %v", es)
	}
	if err := ValidateLink(event, observed, context, ContextRef(contextHash), contextHash); err != nil {
		t.Fatalf("valid claude review observation rejected: %v", err)
	}
	codexLaunch := map[string]any{"parent_session_id": "parent", "parent_turn_id": "turn", "tool_use_id": "tool", "post_confirmed": true, "agent_id": "agent-1", "agent_type": "default", "task_name": "review", "fork_turns": "none"}
	for name, mutate := range map[string]func(map[string]any){
		"codex launch under claude profile": func(v map[string]any) { model.M(v["producer_result"])["launch"] = codexLaunch },
		"claude launch under codex profile": func(v map[string]any) { v["producer_profile"] = "codex-review/0.1.0" },
		"fork subagent":                     func(v map[string]any) { model.M(model.M(v["producer_result"])["launch"])["subagent_type"] = "fork" },
		"unpinned agent type": func(v map[string]any) {
			model.M(model.M(v["producer_result"])["launch"])["agent_type"] = "general-purpose"
		},
		"not first stop":     func(v map[string]any) { model.M(model.M(v["producer_result"])["launch"])["first_stop"] = false },
		"unconfirmed launch": func(v map[string]any) { model.M(model.M(v["producer_result"])["launch"])["post_confirmed"] = false },
		"other agent":        func(v map[string]any) { v["producer_run_id"] = "agent-2" },
	} {
		t.Run(name, func(t *testing.T) {
			candidate, _ := canonical.Clone(observed)
			mutate(candidate)
			newHash, _ := canonical.Hash(candidate["producer_result"])
			candidate["producer_result_sha256"] = newHash
			schemaOK := len(schema.ValidateWith(Schema(), candidate)) == 0
			if schemaOK && ValidateLink(event, candidate, context, ContextRef(contextHash), contextHash) == nil {
				t.Fatal("claude review mutation accepted")
			}
		})
	}
}

// smartsLink builds an internally consistent SMARTS approval event, its
// engine context and the host observation for one recorded decision under
// the given producer profile, so ValidateLink exercises the full contract:
// profile admission, routing and the profile's own decision validator.
func smartsLink(t *testing.T, profile string, decision map[string]any) (event, observed, context map[string]any, ref, contextHash string) {
	t.Helper()
	steps := model.A(model.M(model.A(decision["options"])[model.I(decision["selected"])])["steps"])
	before := map[string]any{"tasks": []any{map[string]any{"id": "T-001", "title": "Method task", "steps": []any{"Original step."}}}}
	after := map[string]any{"tasks": []any{map[string]any{"id": "T-001", "title": "Method task", "steps": steps}}}
	scope, err := ProtectedPlanHash(before)
	if err != nil {
		t.Fatal(err)
	}
	identity := func(id, kind string) map[string]any {
		return map[string]any{"artifact_id": id, "kind": kind, "revision": int64(1), "model_sha256": testDigest(id + "-model"), "normative_sha256": testDigest(id + "-norm")}
	}
	pair := map[string]any{"format": "codearbiter.sprint-pair/0.1.0", "spec": identity("SPEC-EXAMPLE", "spec"), "plan": identity("PLAN-EXAMPLE", "plan"), "approved_plan_normative_sha256": testDigest("approved"), "scope_sha256": scope, "delegate_methods": true}
	record := map[string]any{"pair": pair, "grant_receipt": ".codearbiter/.artifacts/receipts/grant.json", "decision": decision, "before_normative": before, "after_normative": after}
	payload := map[string]any{"smarts": record}
	decisionBytes, _ := canonical.Marshal(decision)
	afterHash, _ := canonical.Hash(map[string]any{"format_version": model.FormatVersion, "kind": "plan", "schema_version": model.SchemaVersion, "artifact_id": "PLAN-EXAMPLE", "normative": after})
	subj := map[string]any{"artifact_id": "PLAN-EXAMPLE", "record_id": "PLAN-EXAMPLE", "normative_sha256": afterHash}
	runID := "smarts-apply-1"
	event = map[string]any{"kind": "approval", "authority_kind": "smarts_workflow", "origin": runID, "subject": subj, "payload": payload, "source_text": string(decisionBytes)}
	payloadHash, _ := canonical.Hash(payload)
	context = map[string]any{"activity": "approval", "subject": subj, "record": payload, "record_sha256": payloadHash, "input_sha256": afterHash, "prompt_sha256": canonical.BytesHash(decisionBytes)}
	contextBytes, _ := canonical.Marshal(context)
	contextHash = canonical.BytesHash(contextBytes)
	decisionHash, _ := canonical.Hash(decision)
	result := map[string]any{"grant_receipt": record["grant_receipt"], "decision_sha256": decisionHash, "scope_sha256": scope}
	resultHash, _ := canonical.Hash(result)
	ref = ContextRef(contextHash)
	observed = map[string]any{"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": subj, "context_ref": ref, "context_sha256": contextHash, "payload_sha256": payloadHash, "producer_profile": profile, "producer_run_id": runID, "producer_result": result, "producer_result_sha256": resultHash}
	return event, observed, context, ref, contextHash
}

// legacyDecision is a historical four-state smarts-plan-method/0.1.0
// decision whose selected option marks Scalable Indifferent while the other
// option marks it Weak: valid under 0.1.0, rejected by the 0.2.0 uniformity
// rule.
func legacyDecision() map[string]any {
	lenses, other := map[string]any{}, map[string]any{}
	for _, name := range Lenses {
		lenses[name] = map[string]any{"verdict": "Adequate", "reason": "Existing bounded task contracts remain unchanged."}
		other[name] = map[string]any{"verdict": "Adequate", "reason": "Existing bounded task contracts remain unchanged."}
	}
	lenses["Scalable"] = map[string]any{"verdict": "Indifferent", "reason": "Load is fixed at this scope."}
	other["Scalable"] = map[string]any{"verdict": "Weak", "reason": "Rebuilds the index on each call."}
	return map[string]any{"task_id": "T-001", "options": []any{
		map[string]any{"label": "Explicit precedence", "steps": []any{"Write the retained negative test.", "Use an explicit precedence table."}, "lenses": lenses},
		map[string]any{"label": "Implicit precedence", "steps": []any{"Derive precedence at call time."}, "lenses": other},
	}, "selected": int64(0), "strength": "moderate", "rationale": "The recorded spec determines precedence; this method preserves its constraints."}
}

// unknownDecision is a five-state decision whose only option carries a
// non-critical Unknown: valid only under smarts-plan-method/0.2.0.
func unknownDecision() map[string]any {
	return decisionV2([]any{optionV2("Bounded cache", baselineLensesV2(map[string]map[string]any{
		"Available": unknownCellV2("Failover behavior is not yet measured.", "Cache behavior during a node restart.", false),
	}))}, 0, "moderate")
}

func smartsRecordOf(event map[string]any) map[string]any {
	return model.M(model.M(event["payload"])["smarts"])
}

func validateSMARTSLink(t *testing.T, profile string, decision map[string]any) error {
	t.Helper()
	event, observed, context, ref, contextHash := smartsLink(t, profile, decision)
	if es := schema.ValidateWith(Schema(), observed); len(es) > 0 {
		return &es[0]
	}
	return ValidateLink(event, observed, context, ref, contextHash)
}

func TestSMARTSProfileLegacyAccepted(t *testing.T) {
	t.Run("historical 0.1.0 record validates under the four-state schema", func(t *testing.T) {
		if err := validateSMARTSLink(t, LegacySMARTSProfile, legacyDecision()); err != nil {
			t.Fatalf("0.1.0 record rejected: %v", err)
		}
		event, _, _, _, _ := smartsLink(t, LegacySMARTSProfile, legacyDecision())
		if err := ValidateSMARTSRecord(smartsRecordOf(event)); err != nil {
			t.Fatalf("producer entry point rejected a 0.1.0 record: %v", err)
		}
	})
	t.Run("0.2.0 record carrying Unknown validates under the five-state schema", func(t *testing.T) {
		if err := validateSMARTSLink(t, SMARTSProfileV2, unknownDecision()); err != nil {
			t.Fatalf("0.2.0 record rejected: %v", err)
		}
	})
	t.Run("0.2.0 record is judged by the 0.2.0 rules", func(t *testing.T) {
		// legacyDecision passes under 0.1.0 (above); recorded under 0.2.0 its
		// non-uniform Indifferent must be rejected.
		if fault.Code(validateSMARTSLink(t, SMARTSProfileV2, legacyDecision())) != "OBSERVATION_UNVERIFIED" {
			t.Fatal("0.2.0 record escaped the 0.2.0 validator")
		}
		event, _, _, _, _ := smartsLink(t, SMARTSProfileV2, legacyDecision())
		assertInvalidSmarts(t, ValidateSMARTSRecordFor(SMARTSProfileV2, smartsRecordOf(event)), "indifferent")
	})
	t.Run("unrecognized profile is rejected", func(t *testing.T) {
		const profile = "smarts-plan-method/0.3.0"
		event, observed, context, ref, contextHash := smartsLink(t, profile, legacyDecision())
		if fault.Code(ValidateLink(event, observed, context, ref, contextHash)) != "OBSERVATION_UNVERIFIED" {
			t.Fatal("contract admitted an unrecognized SMARTS profile")
		}
		if len(schema.ValidateWith(Schema(), observed)) == 0 {
			t.Fatal("observation schema admitted an unrecognized SMARTS profile")
		}
		assertInvalidSmarts(t, ValidateSMARTSRecordFor(profile, smartsRecordOf(event)), "unrecognized")
	})
}

func TestSMARTSProfileLegacyRejectsUnknown(t *testing.T) {
	t.Run("0.1.0 record carrying Unknown fails the contract", func(t *testing.T) {
		if fault.Code(validateSMARTSLink(t, LegacySMARTSProfile, unknownDecision())) != "OBSERVATION_UNVERIFIED" {
			t.Fatal("0.1.0 record carrying Unknown was accepted")
		}
	})
	t.Run("0.1.0 record carrying Unknown fails the four-state schema", func(t *testing.T) {
		event, _, _, _, _ := smartsLink(t, LegacySMARTSProfile, unknownDecision())
		record := smartsRecordOf(event)
		for name, err := range map[string]error{"routed": ValidateSMARTSRecordFor(LegacySMARTSProfile, record), "producer": ValidateSMARTSRecord(record)} {
			if fault.Code(err) != "INVALID_MODEL" {
				t.Fatalf("%s: expected a schema rejection, got %v", name, err)
			}
		}
	})
}
