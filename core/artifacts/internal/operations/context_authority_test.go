package operations

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func contextFixture(t *testing.T) (string, object) {
	t.Helper()
	root := testutil.Root(t)
	if err := os.MkdirAll(filepath.Join(root, ".codearbiter"), 0755); err != nil {
		t.Fatal(err)
	}
	source := []byte("observed source\n")
	if err := os.WriteFile(filepath.Join(root, "source.txt"), source, 0644); err != nil {
		t.Fatal(err)
	}
	typed := object{"format": contextdocument.Format, "document_id": "CONTEXT", "entries": []any{
		object{"id": "FIELD-NAME", "kind": "identity", "field": "project_name", "value": "Fixture Project", "evidence_refs": []any{"CLAIM-NAME"}},
	}}
	typedBytes, _ := canonical.Marshal(typed)
	preview, err := contextdocument.RenderPreview(typedBytes, nil, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	provenance := object{"schema": int64(2), "doc": "CONTEXT", "created": "2026-09-27",
		"document": object{"path": ".codearbiter/CONTEXT.md", "digest_method": "sha256-raw", "digest": preview.AfterSHA256},
		"fields": []any{object{"id": "FIELD-NAME", "owner_ref": "project_name", "claims": []any{object{
			"id": "CLAIM-NAME", "semantic_review": object{"state": "reviewed", "reference": "fixture review"},
			"evidence":                 []any{object{"kind": "content", "path": "source.txt", "digest_method": "sha256-raw", "digest": canonical.BytesHash(source)}},
			"effective_authority_refs": []any{},
		}}}},
	}
	r := object{"protocol": Protocol, "operation_id": "context-fixture-0001", "mode": "create",
		"document_id": "CONTEXT", "target_path": ".codearbiter/CONTEXT.md", "typed": typed,
		"selections": []any{}, "expected_document_sha256": nil, "expected_provenance_sha256": nil,
		"proposed_provenance": provenance,
	}
	return root, r
}

func contextSourceFixture(t *testing.T, root, sub string, value object) (string, string) {
	t.Helper()
	b, err := canonical.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	h := canonical.BytesHash(b)
	p := filepath.Join(".codearbiter", ".artifacts", sub, h+".json")
	if err := os.MkdirAll(filepath.Join(root, filepath.Dir(p)), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, p), b, 0644); err != nil {
		t.Fatal(err)
	}
	return ".codearbiter/.artifacts/" + sub + "/" + h + ".json", h
}

func TestContextAuthorityExactPreviewFixture(t *testing.T) {
	root, request := contextFixture(t)
	prompt := "approve-context CONTEXT-CONTEXT fixture-token-001"
	request["prompt_sha256"] = canonical.BytesHash([]byte(prompt))
	issuedValue, err := Run(root, "context-evidence-context", request)
	if err != nil {
		t.Fatalf("fixture context issue: %v", err)
	}
	issued := model.M(issuedValue)
	contextRaw, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(model.S(issued["context_ref"]))))
	if err != nil {
		t.Fatal(err)
	}
	context, err := canonical.Object(contextRaw)
	if err != nil {
		t.Fatal(err)
	}
	binding := model.S(issued["preview_binding_sha256"])
	subject := model.M(issued["subject"])
	payload := object{"preview_binding_sha256": binding}
	producer := object{"host": "fixture", "session_id": "test", "prompt_sha256": request["prompt_sha256"]}
	observed := object{"format": "codearbiter.observation/0.2.0", "kind": "context_approval",
		"subject": subject, "context_ref": issued["context_ref"], "context_sha256": issued["context_sha256"],
		"payload_sha256": mustHashFixture(t, payload), "producer_profile": "host-user-context-preview/0.1.0",
		"producer_run_id": "fixture:test", "producer_result": producer,
		"producer_result_sha256": mustHashFixture(t, producer)}
	observationRef, observationHash := contextSourceFixture(t, root, "observations", observed)
	event := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "context_approval",
		"authority_kind": "user_workflow", "subject": subject, "actor": "fixture user",
		"origin": "fixture:UserPromptSubmit:test", "verdict": "approved", "payload": payload,
		"source_text": prompt, "observation_ref": observationRef, "observation_sha256": observationHash}
	sourceRef, sourceHash := contextSourceFixture(t, root, "authority-sources", event)
	capturedValue, err := Run(root, "capture-observation", object{"protocol": Protocol, "source_ref": sourceRef, "source_sha256": sourceHash})
	if err != nil {
		t.Fatalf("fixture context capture: %v", err)
	}
	receipt := model.S(model.M(capturedValue)["receipt"])
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := authority.ValidateContextPreview(f, receipt, binding); err != nil {
		t.Fatalf("exact fixture preview rejected: %v", err)
	}
	if err := authority.ValidateContextPreview(f, receipt, canonical.BytesHash([]byte("unrelated preview"))); fault.Code(err) != "STALE_EVIDENCE" {
		t.Fatalf("replayed unrelated approval accepted: %v", err)
	}
	if model.S(context["input_sha256"]) != binding {
		t.Fatal("fixture issuer did not calculate exact preview binding")
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("changed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "capture-observation", object{"protocol": Protocol, "source_ref": sourceRef, "source_sha256": sourceHash}); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("source drift did not block fresh capture: %v", err)
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt}); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("source drift did not block uncommitted apply: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("observed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	appliedValue, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt})
	if err != nil {
		t.Fatalf("approved fixture context apply: %v", err)
	}
	if appliedValue.(map[string]any)["transaction"].(store.Outcome).Replay {
		t.Fatal("first context apply was treated as replay")
	}
	if _, err := os.Stat(filepath.Join(root, ".codearbiter", "CONTEXT.md")); err != nil {
		t.Fatalf("approved context document not written: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("changed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	replayedValue, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt})
	if err != nil || !replayedValue.(map[string]any)["transaction"].(store.Outcome).Replay {
		t.Fatalf("committed historical replay lost after source drift: %v / %v", replayedValue, err)
	}
}
