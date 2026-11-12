package contextdocument

import (
	"encoding/base64"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func storedPreviewFixture() map[string]any {
	return map[string]any{
		"format": PreviewFormat,
		"request": map[string]any{
			"operation_id": "context-fixture-0001", "mode": "create", "document_id": "CONTEXT",
			"target_path": ".codearbiter/CONTEXT.md",
			"typed": map[string]any{"format": Format, "document_id": "CONTEXT", "entries": []any{
				map[string]any{"id": "FIELD-NAME", "kind": "identity", "field": "project_name", "value": "Fixture Project", "evidence_refs": []any{"CLAIM-NAME"}},
			}},
			"selections": []any{}, "expected_document_sha256": nil, "expected_provenance_sha256": nil,
			"proposed_provenance": map[string]any{"schema": int64(2)},
		},
		"preview_binding_sha256":   strings.Repeat("a", 64),
		"before_document_base64":   nil,
		"before_provenance_base64": nil,
	}
}

func storedPreviewBytes(t *testing.T, mutate func(map[string]any)) []byte {
	t.Helper()
	record := storedPreviewFixture()
	if mutate != nil {
		mutate(record)
	}
	b, err := canonical.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestStoredPreviewContractAcceptsRetainedPreviews(t *testing.T) {
	if err := ValidateStoredPreview(storedPreviewBytes(t, nil)); err != nil {
		t.Fatalf("valid create preview rejected: %v", err)
	}
	before := []byte("# Prior context\n")
	if err := ValidateStoredPreview(storedPreviewBytes(t, func(r map[string]any) {
		request := r["request"].(map[string]any)
		request["mode"] = "update"
		request["expected_document_sha256"] = canonical.BytesHash(before)
		r["before_document_base64"] = base64.StdEncoding.EncodeToString(before)
	})); err != nil {
		t.Fatalf("valid update preview with a retained preimage rejected: %v", err)
	}
	expected := map[string]any{}
	for _, path := range finalizationPaths() {
		expected[path] = strings.Repeat("b", 64)
	}
	stringExpected := map[string]string{}
	for path, value := range expected {
		stringExpected[path] = value.(string)
	}
	binding, err := FinalizationBinding(Finalization{OperationID: "context-final-0001", Expected: stringExpected})
	if err != nil {
		t.Fatal(err)
	}
	if err := ValidateStoredPreview(storedPreviewBytes(t, func(r map[string]any) {
		r["request"] = map[string]any{"operation_id": "context-final-0001", "mode": "finalize", "document_id": "CONTEXT",
			"target_path": ".codearbiter/CONTEXT.md", "expected": expected}
		r["preview_binding_sha256"] = binding
	})); err != nil {
		t.Fatalf("valid finalization preview rejected: %v", err)
	}
}

func TestStoredPreviewContractRejectsMalformedRecords(t *testing.T) {
	request := func(r map[string]any) map[string]any { return r["request"].(map[string]any) }
	for name, mutate := range map[string]func(map[string]any){
		"unknown record key":     func(r map[string]any) { r["extra"] = true },
		"missing record key":     func(r map[string]any) { delete(r, "before_document_base64") },
		"wrong format":           func(r map[string]any) { r["format"] = "codearbiter.context-preview/9.9.9" },
		"binding not a digest":   func(r map[string]any) { r["preview_binding_sha256"] = "not-a-digest" },
		"malformed before-image": func(r map[string]any) { r["before_document_base64"] = "%%%" },
		"non-string before-image": func(r map[string]any) {
			r["before_provenance_base64"] = int64(1)
		},
		// An over-limit before-image cannot occur inside a record that is itself
		// within the canonical byte limit; PreviewImage keeps the bound anyway.
		"unknown request key":   func(r map[string]any) { request(r)["extra"] = true },
		"bad operation id":      func(r map[string]any) { request(r)["operation_id"] = "x" },
		"unknown mode":          func(r map[string]any) { request(r)["mode"] = "replace" },
		"wrong document target": func(r map[string]any) { request(r)["target_path"] = ".codearbiter/tech-stack.md" },
		"unknown document":      func(r map[string]any) { request(r)["document_id"] = "README" },
		"typed for other document": func(r map[string]any) {
			request(r)["document_id"], request(r)["target_path"] = "code-map", ".codearbiter/code-map.md"
		},
		"invalid typed document": func(r map[string]any) { request(r)["typed"] = map[string]any{"format": Format} },
		"malformed selection": func(r map[string]any) {
			request(r)["selections"] = []any{map[string]any{"entry_id": "FIELD-NAME"}}
		},
		"provenance not object": func(r map[string]any) { request(r)["proposed_provenance"] = "x" },
		"preimage without expected identity": func(r map[string]any) {
			r["before_document_base64"] = base64.StdEncoding.EncodeToString([]byte("x"))
		},
		"expected identity without preimage": func(r map[string]any) {
			request(r)["expected_document_sha256"] = strings.Repeat("c", 64)
		},
		"preimage digest mismatch": func(r map[string]any) {
			r["before_document_base64"] = base64.StdEncoding.EncodeToString([]byte("x"))
			request(r)["expected_document_sha256"] = strings.Repeat("c", 64)
		},
		"finalization for other document": func(r map[string]any) {
			r["request"] = map[string]any{"operation_id": "context-final-0001", "mode": "finalize", "document_id": "code-map",
				"target_path": ".codearbiter/code-map.md", "expected": map[string]any{}}
		},
		"finalization binding mismatch": func(r map[string]any) {
			expected := map[string]any{}
			for _, path := range finalizationPaths() {
				expected[path] = strings.Repeat("b", 64)
			}
			r["request"] = map[string]any{"operation_id": "context-final-0001", "mode": "finalize", "document_id": "CONTEXT",
				"target_path": ".codearbiter/CONTEXT.md", "expected": expected}
		},
	} {
		t.Run(name, func(t *testing.T) {
			if err := ValidateStoredPreview(storedPreviewBytes(t, mutate)); fault.Code(err) != "INVALID_CONTEXT_PREVIEW" {
				t.Fatalf("malformed preview was admitted: %v", err)
			}
		})
	}
	if _, err := PreviewImage(strings.Repeat("A", (canonical.MaxBytes/3+2)*4)); fault.Code(err) != "INVALID_CONTEXT_PREVIEW" {
		t.Fatalf("oversized before-image was decoded: %v", err)
	}
	if err := ValidateStoredPreview([]byte("not json")); fault.Code(err) != "INVALID_CONTEXT_PREVIEW" {
		t.Fatalf("non-object preview was admitted: %v", err)
	}
}
