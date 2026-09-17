//go:build linux

package operations

import (
	"encoding/json"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"os"
	"path/filepath"
	"testing"
)

func TestReviewRetryPreservesMutationResult(t *testing.T) {
	h := newHarness(t)
	req := object{"operation_id": "review-replay-001", "artifact_id": "SPEC-REPLAY", "kind": "spec", "slug": "replay", "title": "Replay", "summary": "Retry creates no duplicate."}
	first := h.run("create", req)
	value, err := h.request("create", req)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(value)
	var second object
	if err = json.Unmarshal(raw, &second); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"artifact_id", "kind", "path", "model_sha256", "normative_sha256"} {
		if second[key] != first[key] {
			t.Errorf("retry lost %s: first=%v retry=%v", key, first[key], second[key])
		}
	}
	if _, ok := second["transaction"]; !ok {
		t.Error("retry changed response shape: transaction field absent")
	}
}

func TestReviewDiffIncludesNormativeHeader(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	out := h.run("diff", object{"artifact_id": "SPEC-EXAMPLE", "changes": []any{object{"op": "header.update", "fields": object{"summary": "Changed required scope explanation."}}}})
	if len(model.A(out["changes"])) == 0 {
		t.Fatal("normative header changed but semantic diff reports no changes")
	}
}

func TestReviewNewlyRetiredIDIsNeverReusable(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{
		object{"op": "record.add", "collection": "scenarios", "parent_id": "AC-001", "record": object{"id": "SCN-TRANSIENT", "given": "x", "when": "y", "then": "z"}},
		object{"op": "record.retire", "symbol": "SCN-TRANSIENT", "reason": "Superseded during this edit."},
	}})
	d := h.doc("SPEC-EXAMPLE")
	r, ok := d.Symbols.ByID["SCN-TRANSIENT"]
	if !ok || !r.Retired {
		t.Fatal("ID created and retired in one transaction has no tombstone")
	}
	_, err := h.request("apply", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "changes": []any{object{"op": "record.add", "collection": "scenarios", "parent_id": "AC-001", "record": object{"id": "SCN-TRANSIENT"}}}})
	if fault.Code(err) != "DUPLICATE_ID" {
		t.Fatalf("retired ID reused: %v", err)
	}
}

func TestReviewIndexCursorBindsAuthoritySources(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	// Force enough long-title specs for multiple bounded catalog pages.
	for i := 0; i < 8; i++ {
		id := "SPEC-CATALOG-" + string(rune('A'+i))
		h.run("create", object{"operation_id": h.next(), "artifact_id": id, "kind": "spec", "slug": "catalog-" + string(rune('a'+i)), "title": "Catalog entry", "summary": "Pagination fixture"})
	}
	first := h.run("index", object{"budget": int64(4096)})
	if first["next_offset"] == nil {
		t.Fatal("test requires pagination")
	}
	d := h.doc("SPEC-EXAMPLE")
	a := model.M(model.A(model.M(d.Data["governance"])["approvals"])[0])
	ref := model.S(a["source_ref"])
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	b, err := f.Read(ref, 1<<20)
	f.Close()
	if err != nil {
		t.Fatal(err)
	}
	_ = b
	// Removing an authority source without changing HTML must invalidate a cursor.
	removeFixtureFile(t, h.root, ref)
	_, err = h.request("index", object{"budget": int64(4096), "offset": first["next_offset"], "catalog_sha256": first["catalog_sha256"]})
	if fault.Code(err) != "STALE_CURSOR" {
		t.Fatalf("authority changed but catalog continuation returned %v", err)
	}
}

func TestReviewPartialUnboundPlanStructuralValidation(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	// A draft plan must remain structurally inspectable when its companion is unavailable.
	removeFixtureFile(t, h.root, ".codearbiter/specs/example.html")
	result, err := h.request("validate", object{"artifact_id": "PLAN-EXAMPLE", "gate": "structural"})
	if err != nil {
		t.Fatalf("structural check unnecessarily resolved absent source: %v", err)
	}
	if model.M(result)["valid"] != true {
		t.Fatal("intact draft plan is structurally valid")
	}
	_, err = h.request("validate", object{"artifact_id": "PLAN-EXAMPLE", "gate": "ready"})
	if err == nil {
		t.Fatal("ready check must still reject missing companion")
	}
}

func TestReviewRetirementPreservesHistoryAfterNestedAdd(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{
		object{"op": "record.update", "symbol": "AC-001", "fields": object{"scenarios": []any{object{"id": "SCN-AC-001", "given": "x", "when": "y", "then": "z"}, object{"id": "SCN-EPHEMERAL", "given": "a", "when": "b", "then": "c"}}}},
		object{"op": "record.retire", "symbol": "SCN-EPHEMERAL", "reason": "No longer needed."},
	}})
	d := h.doc("SPEC-EXAMPLE")
	r, ok := d.Symbols.ByID["SCN-EPHEMERAL"]
	if !ok || !r.Retired {
		t.Fatal("nested update bypassed lifetime ID reservation")
	}
}

func removeFixtureFile(t *testing.T, root, p string) {
	t.Helper()
	if err := os.Remove(filepath.Join(root, filepath.FromSlash(p))); err != nil {
		t.Fatal(err)
	}
}

func TestReviewRetryReturnsOriginalIdentityAfterLaterEdits(t *testing.T) {
	h := newHarness(t)
	req := object{"operation_id": "original-replay-001", "artifact_id": "SPEC-REPLAY", "kind": "spec", "slug": "replay", "title": "Original", "summary": "Original completion identity."}
	first := h.run("create", req)
	h.mut("apply", "SPEC-REPLAY", object{"changes": []any{object{"op": "header.update", "fields": object{"title": "Later revision"}}}})
	retry := h.run("create", req)
	if retry["model_sha256"] != first["model_sha256"] || retry["normative_sha256"] != first["normative_sha256"] {
		t.Fatal("retry substituted the latest identity for its original completion")
	}
	current := h.doc("SPEC-REPLAY")
	if current.Hash() == retry["model_sha256"] {
		t.Fatal("fixture did not change identity")
	}
}
