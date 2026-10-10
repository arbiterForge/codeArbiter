package read_test

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

type object = map[string]any

func request(t *testing.T, root, op string, input object) (any, error) {
	t.Helper()
	input["protocol"] = operations.Protocol
	return operations.Run(root, op, input)
}

func run(t *testing.T, root, op string, input object) object {
	t.Helper()
	out, err := request(t, root, op, input)
	if err != nil {
		t.Fatalf("%s: %v", op, err)
	}
	return out.(map[string]any)
}

func batchFixture(t *testing.T) (string, object) {
	t.Helper()
	root := testutil.Root(t)
	spec := testutil.Spec()
	norm := model.M(spec["normative"])
	run(t, root, "create", object{"operation_id": "batch-spec-create", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": norm["title"], "summary": norm["summary"], "normative": norm})
	plan := testutil.Plan(testutil.Seal(t, spec))
	for _, value := range model.A(model.M(plan["normative"])["tasks"]) {
		model.M(value)["steps"] = model.List(strings.Repeat("λ", 700))
	}
	pn := model.M(plan["normative"])
	run(t, root, "create", object{"operation_id": "batch-plan-create", "artifact_id": "PLAN-EXAMPLE", "kind": "plan", "slug": "example", "spec_id": "SPEC-EXAMPLE", "title": pn["title"], "summary": pn["summary"], "normative": pn})
	return root, run(t, root, "identity", object{"artifact_id": "PLAN-EXAMPLE"})
}

func batchRequest(identity object, ids ...string) object {
	return object{"artifact_id": identity["artifact_id"], "model_sha256": identity["model_sha256"], "symbols": model.List(ids...), "offset": int64(0), "budget": int64(4096)}
}

func TestExactBatchWholeRecordParityAndPages(t *testing.T) {
	root, identity := batchFixture(t)
	ids := []string{"T-003", "T-001", "T-002"}
	input := batchRequest(identity, ids...)
	seen := []string{}
	pages := 0
	for {
		page := run(t, root, "read-batch", input)
		pages++
		for _, key := range []string{"artifact_id", "revision", "model_sha256", "normative_sha256"} {
			if page[key] != identity[key] {
				t.Fatalf("identity %s changed", key)
			}
		}
		if page["mode"] != "exact" || page["context_complete"] != false || page["context_ticket"] != nil {
			t.Fatal("batch became context delivery")
		}
		raw, _ := json.Marshal(page)
		if len(raw) > 4096 {
			t.Fatal("page exceeds byte budget")
		}
		if model.I(page["total"]) != 3 || model.I(page["offset"]) != int64(len(seen)) {
			t.Fatal("wrong selection bounds")
		}
		for _, value := range model.A(page["records"]) {
			row := model.M(value)
			id := model.S(row["id"])
			exact := run(t, root, "read", object{"artifact_id": identity["artifact_id"], "symbol": id, "mode": "exact", "budget": int64(4096)})
			if row["kind"] != "tasks" || row["retired"] != false || !reflect.DeepEqual(row["record"], exact["record"]) {
				t.Fatal("batch changed the whole exact record")
			}
			seen = append(seen, id)
		}
		if page["next_offset"] == nil {
			break
		}
		if model.I(page["next_offset"]) != int64(len(seen)) || pages > len(ids) {
			t.Fatal("nonadvancing or skipped page")
		}
		input["offset"] = page["next_offset"]
	}
	if pages < 2 || !reflect.DeepEqual(seen, ids) {
		t.Fatalf("incomplete ordered pages: %d %v", pages, seen)
	}
	for _, directory := range []string{"context-tokens", "receipts", "evidence-contexts"} {
		if _, err := os.Stat(filepath.Join(root, ".codearbiter", ".artifacts", directory)); !os.IsNotExist(err) {
			t.Fatalf("batch produced %s: %v", directory, err)
		}
	}
}

func TestExactBatchRejectsInvalidWholeSelection(t *testing.T) {
	root, identity := batchFixture(t)
	tooMany := []any{}
	for i := 0; i < 129; i++ {
		tooMany = append(tooMany, fmt.Sprintf("T-%03d", i))
	}
	cases := []struct {
		name, field string
		value       any
		code        string
	}{
		{"empty", "symbols", []any{}, "INVALID_MODEL"},
		{"duplicate", "symbols", model.List("T-001", "T-001"), "INVALID_MODEL"},
		{"oversized selection", "symbols", tooMany, "INVALID_MODEL"},
		{"wrong ID type", "symbols", []any{int64(1)}, "INVALID_MODEL"},
		{"missing last ID", "symbols", model.List("T-001", "T-MISSING"), "SYMBOL_NOT_FOUND"},
		{"stale first page", "model_sha256", strings.Repeat("0", 64), "STALE_CURSOR"},
		{"negative offset", "offset", int64(-1), "INVALID_MODEL"},
		{"past selection", "offset", int64(2), "INVALID_OFFSET"},
		{"empty trailing page", "offset", int64(1), "INVALID_OFFSET"},
		{"small budget", "budget", int64(4095), "INVALID_MODEL"},
		{"large budget", "budget", int64(65537), "INVALID_MODEL"},
		{"unknown field", "unsafe", true, "INVALID_MODEL"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			input := batchRequest(identity, "T-001")
			input[tc.field] = tc.value
			out, err := request(t, root, "read-batch", input)
			if fault.Code(err) != tc.code || out != nil {
				t.Fatalf("partial/incorrect refusal: %#v %v", out, err)
			}
		})
	}
	input := batchRequest(identity, "T-001")
	delete(input, "model_sha256")
	if out, err := request(t, root, "read-batch", input); fault.Code(err) != "INVALID_MODEL" || out != nil {
		t.Fatalf("missing pin accepted: %#v %v", out, err)
	}
}

func TestExactBatchRejectsOversizedLaterRecordBeforeDelivery(t *testing.T) {
	root, identity := batchFixture(t)
	run(t, root, "apply", object{"artifact_id": "PLAN-EXAMPLE", "operation_id": "batch-enlarge-task", "expected": object{"revision": identity["revision"], "model_sha256": identity["model_sha256"]}, "changes": []any{object{"op": "record.update", "symbol": "T-002", "fields": object{"steps": model.List(strings.Repeat("λ", 3000))}}}})
	identity = run(t, root, "identity", object{"artifact_id": "PLAN-EXAMPLE"})
	if out, err := request(t, root, "read-batch", batchRequest(identity, "T-001", "T-002")); fault.Code(err) != "RECORD_TOO_LARGE" || out != nil {
		t.Fatalf("partial oversized selection: %#v %v", out, err)
	}
}

func TestExactBatchPinsContinuationAndKeepsRenderValidation(t *testing.T) {
	root, identity := batchFixture(t)
	input := batchRequest(identity, "T-001", "T-002", "T-003")
	page := run(t, root, "read-batch", input)
	if page["next_offset"] == nil {
		t.Fatal("fixture must span pages")
	}
	run(t, root, "apply", object{"artifact_id": "PLAN-EXAMPLE", "operation_id": "batch-change-plan", "expected": object{"revision": identity["revision"], "model_sha256": identity["model_sha256"]}, "changes": []any{object{"op": "header.update", "fields": object{"summary": "Changed between pages."}}}})
	input["offset"] = page["next_offset"]
	if out, err := request(t, root, "read-batch", input); fault.Code(err) != "STALE_CURSOR" || out != nil {
		t.Fatalf("mixed generation: %#v %v", out, err)
	}
	path := filepath.Join(root, ".codearbiter", "plans", "example.html")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	raw = []byte(strings.Replace(string(raw), "Configuration precedence", "Misleading replacement", 1))
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	if out, err := request(t, root, "read-batch", batchRequest(identity, "T-001")); fault.Code(err) != "RENDER_DRIFT" || out != nil {
		t.Fatalf("render drift accepted: %#v %v", out, err)
	}
}
