package operations

import (
	"os"
	"path/filepath"
	"sort"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func captureObservedPromptFixture(t *testing.T, root, id, record, kind, authorityKind, verdict, sourceText string, payload object) string {
	t.Helper()
	docValue, err := Run(root, "identity", object{"protocol": Protocol, "artifact_id": id})
	if err != nil {
		t.Fatal(err)
	}
	identity := model.M(docValue)
	subject := object{"artifact_id": id, "normative_sha256": identity["normative_sha256"], "record_id": record}
	contextRequest := object{
		"protocol": Protocol, "artifact_id": id, "activity": kind,
		"record_id": record,
	}
	promptHash := canonical.BytesHash([]byte(sourceText))
	if kind == "approval" || kind == "prerequisite" || kind == "reconciliation" || kind == "farm_authorization" {
		contextRequest["prompt_sha256"] = promptHash
	}
	contextValue, err := Run(root, "evidence-context", contextRequest)
	if err != nil {
		t.Fatalf("evidence-context: %v", err)
	}
	contextResult := model.M(contextValue)
	contextBytes, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(model.S(contextResult["context_ref"]))))
	if err != nil {
		t.Fatal(err)
	}
	context, err := canonical.Object(contextBytes)
	if err != nil {
		t.Fatal(err)
	}
	profile, runID := "host-user-prompt/0.1.0", "test:fixture"
	producer := object{"host": "test", "session_id": "fixture", "prompt_sha256": promptHash}
	if kind == "verification" {
		profile, runID = "declared-command/0.1.0", "fixture-verifier"
		bindings := []any{}
		for _, value := range model.A(context["commands"]) {
			row := model.M(value)
			definition := model.M(row["definition"])
			argv := append([]any{filepath.Join(root, "synthetic-executable")}, model.A(definition["argv"])[1:]...)
			bindings = append(bindings, object{
				"definition_sha256": row["definition_sha256"], "argv": argv,
				"cwd": root, "cwd_filesystem_id": "fixture:cwd", "workspace_root": root,
				"workspace_filesystem_id": "fixture:root", "git_common_dir": root,
				"git_common_filesystem_id": "fixture:git", "executable_sha256": canonical.BytesHash([]byte("fixture executable")),
			})
		}
		workspace := object{"root": root, "filesystem_id": "fixture:root", "git_common_dir": root, "git_common_filesystem_id": "fixture:git", "head": "fixture", "status_sha256": canonical.BytesHash(nil), "content_sha256": canonical.BytesHash(nil)}
		producer = object{"environment_sha256": canonical.BytesHash([]byte("fixture environment")), "command_bindings": bindings, "workspace_before": []any{workspace}, "workspace_after": []any{workspace}, "commands": payload["commands"]}
	} else if kind == "spec_review" || kind == "quality_review" {
		profile, runID = "codex-review/0.1.0", "fixture-reviewer"
		coverageSet := map[string]bool{}
		records := model.A(context["tasks"])
		if kind == "spec_review" {
			records = []any{context["task"]}
		}
		for _, value := range records {
			for _, criterion := range model.Strings(model.M(value)["criterion_refs"]) {
				coverageSet[criterion] = true
			}
		}
		coverage := make([]string, 0, len(coverageSet))
		for criterion := range coverageSet {
			coverage = append(coverage, criterion)
		}
		sort.Strings(coverage)
		launch := object{"parent_session_id": "fixture-parent", "parent_turn_id": "fixture-turn", "tool_use_id": "fixture-tool", "post_confirmed": true, "agent_id": runID, "agent_type": "default", "task_name": "fixture-authority", "fork_turns": "none"}
		contract := object{"format": "codearbiter.review-decision/0.1.0", "decision": model.List("pass", "changes_requested"), "finding_severity": model.List("BLOCK", "WARN", "INFO"), "required_fields": model.List("format", "request_id", "target_sha256", "contract_sha256", "decision", "coverage", "findings", "assessment")}
		decision := object{"format": "codearbiter.review-decision/0.1.0", "request_id": canonical.BytesHash([]byte("fixture request")), "target_sha256": context["input_sha256"], "contract_sha256": mustHashFixture(t, contract), "decision": "pass", "coverage": model.List(coverage...), "findings": []any{}, "assessment": payload["assessment"]}
		producer = object{"launch": launch, "decision": decision}
	}
	observation := object{
		"format": "codearbiter.observation/0.2.0", "kind": kind, "subject": subject,
		"context_ref": contextResult["context_ref"], "context_sha256": contextResult["context_sha256"],
		"payload_sha256": mustHashFixture(t, payload), "producer_profile": profile,
		"producer_run_id": runID, "producer_result": producer,
		"producer_result_sha256": mustHashFixture(t, producer),
	}
	observationBytes, err := canonical.Marshal(observation)
	if err != nil {
		t.Fatal(err)
	}
	observationHash := canonical.BytesHash(observationBytes)
	writeFixture(t, root, filepath.Join(".codearbiter", ".artifacts", "observations", observationHash+".json"), observationBytes)
	event := object{
		"format": "codearbiter.workflow-event/0.2.0", "kind": kind,
		"authority_kind": authorityKind, "subject": subject, "actor": "synthetic test fixture",
		"origin": "isolated observed fixture", "verdict": verdict, "payload": payload,
		"source_text":        sourceText,
		"observation_ref":    ".codearbiter/.artifacts/observations/" + observationHash + ".json",
		"observation_sha256": observationHash,
	}
	eventBytes, err := canonical.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	eventHash := canonical.BytesHash(eventBytes)
	writeFixture(t, root, filepath.Join(".codearbiter", ".artifacts", "authority-sources", eventHash+".json"), eventBytes)
	result, err := Run(root, "capture-observation", object{
		"protocol":      Protocol,
		"source_ref":    ".codearbiter/.artifacts/authority-sources/" + eventHash + ".json",
		"source_sha256": eventHash,
	})
	if err != nil {
		t.Fatalf("capture-observation: %v", err)
	}
	return model.S(model.M(result)["receipt"])
}

func mustHashFixture(t *testing.T, value any) string {
	t.Helper()
	hash, err := canonical.Hash(value)
	if err != nil {
		t.Fatal(err)
	}
	return hash
}

func writeFixture(t *testing.T, root, relative string, data []byte) {
	t.Helper()
	target := filepath.Join(root, relative)
	if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, data, 0600); err != nil {
		t.Fatal(err)
	}
}
