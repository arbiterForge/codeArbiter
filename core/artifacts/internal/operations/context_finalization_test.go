package operations

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func finalizationOperationsFixture(t *testing.T) (string, object) {
	t.Helper()
	root := testutil.Root(t)
	write := func(path string, body []byte) {
		t.Helper()
		full := filepath.Join(root, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(full), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, body, 0644); err != nil {
			t.Fatal(err)
		}
	}
	source := []byte("observed source\n")
	write("source.txt", source)
	expected := object{}
	for _, item := range []struct{ id, body, owner string }{
		{"CONTEXT", "---\narbiter: enabled\nstage: 1\n---\n\n# Project: Sample\n\n## Human\nPreserve me.\n", "project_name"},
		{"tech-stack", "# Tech stack\n\n<!-- ca:field CLAIM-ONE fact runtime -->\nRuntime: Go\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		{"coding-standards", "# Coding standards\n\n<!-- ca:field CLAIM-ONE fact coding_pattern -->\nPattern: Go\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		{"security-controls", "# Security controls\n\n<!-- ca:field CLAIM-ONE fact security_observation -->\nNo persistent data in scope.\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		{"code-map", "# Code map\n\n## Core\n- `source.txt` — source\n", "map:Core:source.txt"},
	} {
		path := ".codearbiter/" + item.id + ".md"
		body := []byte(item.body)
		write(path, body)
		expected[path] = canonical.BytesHash(body)
		field, claim := "FIELD-ONE", "CLAIM-ONE"
		if item.id == "CONTEXT" {
			field, claim = "FIELD-NAME", "CLAIM-NAME"
		}
		provenance := object{"schema": int64(2), "doc": item.id, "created": "2026-09-27",
			"document": object{"path": path, "digest_method": "sha256-raw", "digest": canonical.BytesHash(body)},
			"fields": []any{object{"id": field, "owner_ref": item.owner, "claims": []any{object{
				"id": claim, "semantic_review": object{"state": "reviewed", "reference": "fixture review"},
				"evidence":                 []any{object{"kind": "content", "path": "source.txt", "digest_method": "sha256-raw", "digest": canonical.BytesHash(source)}},
				"effective_authority_refs": []any{},
			}}}},
		}
		provRaw, err := canonical.Marshal(provenance)
		if err != nil {
			t.Fatal(err)
		}
		provPath := ".codearbiter/.provenance/" + item.id + ".json"
		write(provPath, provRaw)
		expected[provPath] = canonical.BytesHash(provRaw)
	}
	for path, body := range map[string]string{
		".codearbiter/open-tasks.md":     "# Open tasks\n",
		".codearbiter/open-questions.md": "# Open questions\n\n_None open._\n",
		".codearbiter/overrides.log":     "# codeArbiter override log - append-only audit artifact. Never edit or delete prior lines.\n",
	} {
		write(path, []byte(body))
		expected[path] = canonical.BytesHash([]byte(body))
	}
	return root, object{"protocol": Protocol, "operation_id": "context-final-0001", "mode": "finalize",
		"document_id": "CONTEXT", "target_path": ".codearbiter/CONTEXT.md", "expected": expected}
}

func TestContextFinalizationReceiptOnlyApply(t *testing.T) {
	root, request := finalizationOperationsFixture(t)
	prompt := "approve-context CONTEXT-CONTEXT fixture-finalize-token"
	request["prompt_sha256"] = canonical.BytesHash([]byte(prompt))
	issuedValue, err := Run(root, "context-finalize-evidence-context", request)
	if err != nil {
		t.Fatalf("finalization preview failed: %v", err)
	}
	issued := model.M(issuedValue)
	previewDocument := model.S(issued["preview_document"])
	if !strings.Contains(previewDocument, "<!--INITIALIZED-->") {
		t.Fatal("preview omitted marker")
	}
	before, err := os.ReadFile(filepath.Join(root, ".codearbiter", "CONTEXT.md"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(before), "<!--INITIALIZED-->") {
		t.Fatal("preview wrote early marker")
	}
	subject := model.M(issued["subject"])
	payload := object{"preview_binding_sha256": issued["preview_binding_sha256"]}
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
	// A changed independent output invalidates even an observed reply.
	board := filepath.Join(root, ".codearbiter", "open-tasks.md")
	if err := os.WriteFile(board, []byte("# Open tasks\nnew task\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "capture-observation", object{"protocol": Protocol, "source_ref": sourceRef, "source_sha256": sourceHash}); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("raced independent output accepted: %v", err)
	}
	if err := os.WriteFile(board, []byte("# Open tasks\n"), 0644); err != nil {
		t.Fatal(err)
	}
	captured, err := Run(root, "capture-observation", object{"protocol": Protocol, "source_ref": sourceRef, "source_sha256": sourceHash})
	if err != nil {
		t.Fatalf("approval capture failed: %v", err)
	}
	receipt := model.S(model.M(captured)["receipt"])
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("source drift\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt}); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("source drift admitted at apply: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("observed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	applied, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt})
	if err != nil {
		t.Fatalf("approved finalization failed: %v", err)
	}
	if model.M(applied)["document_id"] != "CONTEXT" {
		t.Fatalf("wrong apply result: %v", applied)
	}
	after, err := os.ReadFile(filepath.Join(root, ".codearbiter", "CONTEXT.md"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(after), "<!--INITIALIZED-->") || !strings.Contains(string(after), "Preserve me.") {
		t.Fatal("marker or human content lost")
	}
	prov, err := os.ReadFile(filepath.Join(root, ".codearbiter", ".provenance", "CONTEXT.json"))
	if err != nil {
		t.Fatal(err)
	}
	var record map[string]any
	if err := json.Unmarshal(prov, &record); err != nil {
		t.Fatal(err)
	}
	if record["document"].(map[string]any)["digest"] != canonical.BytesHash(after) {
		t.Fatal("marker provenance mismatch")
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt}); err != nil {
		t.Fatalf("receipt replay failed: %v", err)
	}
}
