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
	payload := map[string]any{"commands": []any{commandResult()}}
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
	payload := map[string]any{"commands": []any{commandResult()}}
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

func TestVerificationProducerCannotForgeFrozenExitOrRequiredTests(t *testing.T) {
	context := verificationContext()
	contextBytes, _ := canonical.Marshal(context)
	contextHash := canonical.BytesHash(contextBytes)
	basePayload := map[string]any{"commands": []any{commandResult()}}
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
			payload := map[string]any{"commands": result["commands"]}
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
