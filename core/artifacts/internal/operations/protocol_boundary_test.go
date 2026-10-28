//go:build linux

package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func TestApplyRejectsStaleModelHashWithCurrentRevision(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	before := h.doc("SPEC-EXAMPLE")
	staleHash := strings.Repeat("0", 64)
	if staleHash == before.Hash() {
		staleHash = strings.Repeat("1", 64)
	}
	_, err := h.request("apply", object{
		"artifact_id":  before.ID(),
		"operation_id": h.next(),
		"expected":     object{"revision": before.Revision(), "model_sha256": staleHash},
		"changes":      []any{object{"op": "header.update", "fields": object{"summary": "This write must be refused."}}},
	})
	if fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("current revision with stale model hash was accepted: %v", err)
	}
	after := h.doc("SPEC-EXAMPLE")
	if after.Revision() != before.Revision() || after.Hash() != before.Hash() {
		t.Fatalf("rejected mutation changed artifact: revision %d -> %d, hash %s -> %s", before.Revision(), after.Revision(), before.Hash(), after.Hash())
	}
}

func TestContextTicketCannotBeUsedAsPageCursor(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	ticket := h.context("T-001", 65536)
	path := filepath.Join(h.root, ".codearbiter", ".artifacts", "context-tokens", ticket+".json")
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	// A completed delivery has offset == total, which the offset guard also
	// rejects. Move it in range so this case isolates the purpose guard.
	payload, err := canonical.Object(before)
	if err != nil {
		t.Fatal(err)
	}
	payload["offset"] = int64(0)
	probe, err := canonical.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	cursor := canonical.BytesHash(probe)
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	if err := f.PutContextToken(cursor, probe); err != nil {
		f.Close()
		t.Fatal(err)
	}
	f.Close()
	out, err := h.request("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(65536), "cursor": cursor})
	if model.M(out) != nil || fault.Code(err) != "INVALID_CURSOR" {
		t.Fatalf("context ticket accepted as page cursor: code=%s returned=%t", fault.Code(err), model.M(out) != nil)
	}
	after, err := os.ReadFile(path)
	if err != nil || string(after) != string(before) {
		t.Fatalf("context ticket was consumed or changed: %v", err)
	}
	stored, err := os.ReadFile(filepath.Join(h.root, ".codearbiter", ".artifacts", "context-tokens", cursor+".json"))
	if err != nil || string(stored) != string(probe) {
		t.Fatalf("purpose-mismatched cursor was consumed or changed: %v", err)
	}
	if h.context("T-001", 65536) != ticket {
		t.Fatal("context ticket was no longer available")
	}
}

func TestOversizedFirstContextItemHasNoNonadvancingCursor(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001", "fields": object{"steps": model.List(strings.Repeat("x", 6500))},
	}}})
	input := object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(4096)}
	out, err := h.request("read", input)
	if model.M(out) != nil || fault.Code(err) != "RECORD_TOO_LARGE" {
		t.Fatalf("oversized first item produced a page: code=%s returned=%t", fault.Code(err), model.M(out) != nil)
	}
	path := filepath.Join(h.root, ".codearbiter", ".artifacts", "context-tokens")
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("failed page issued a context token: %v", err)
	}
	page := h.run("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(65536)})
	if len(model.A(page["items"])) == 0 {
		t.Fatal("valid oversized item could not be read at larger budget")
	}
}
