package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestTypedRecordReorder(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	h.mutate("apply", "PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.update", "symbol": "CP-02", "fields": object{"depends_on": []any{}}},
		object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": []any{}}},
	}})
	h.approve("PLAN-EXAMPLE")
	startNativeV1FixtureTask(t, h, "T-001")
	before := h.doc("PLAN-EXAMPLE")
	beforeExecution, err := canonical.Hash(before.Data["execution"])
	if err != nil {
		t.Fatal(err)
	}
	reorder := object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-02", "CP-01"}}
	preview := h.run("diff", object{"artifact_id": "PLAN-EXAMPLE", "changes": []any{reorder}})
	changes := model.A(preview["changes"])
	if len(changes) != 1 || model.S(model.M(changes[0])["field"]) != "normative.checkpoints" || model.S(model.M(changes[0])["change"]) != "reordered" {
		t.Fatalf("reorder preview omitted the order change: %v", changes)
	}

	h.mutate("apply", "PLAN-EXAMPLE", object{"changes": []any{
		reorder,
	}})
	after := h.doc("PLAN-EXAMPLE")
	checkpoints := model.A(after.Norm()["checkpoints"])
	if model.S(model.M(checkpoints[0])["id"]) != "CP-02" || model.S(model.M(checkpoints[1])["id"]) != "CP-01" {
		t.Fatalf("checkpoint order did not change: %v", checkpoints)
	}
	afterExecution, err := canonical.Hash(after.Data["execution"])
	if err != nil {
		t.Fatal(err)
	}
	if beforeExecution != afterExecution {
		t.Fatal("reorder changed historical execution evidence")
	}
	beforeApprovals, err := canonical.Hash(model.M(before.Data["governance"])["approvals"])
	if err != nil {
		t.Fatal(err)
	}
	afterApprovals, err := canonical.Hash(model.M(after.Data["governance"])["approvals"])
	if err != nil {
		t.Fatal(err)
	}
	if beforeApprovals != afterApprovals {
		t.Fatal("reorder changed historical approval receipts")
	}
	if model.S(model.M(after.Data["governance"])["state"]) != "draft" {
		t.Fatal("normative reorder did not invalidate approval")
	}
}

func TestRecordReorderRejectsInvalidCheckpointDependencyOrder(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	before := h.doc("PLAN-EXAMPLE")
	_, err := h.request("apply", object{
		"artifact_id": "PLAN-EXAMPLE", "operation_id": h.next(),
		"expected": object{"revision": before.Revision(), "model_sha256": before.Hash()},
		"changes":  []any{object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-02", "CP-01"}}},
	})
	if fault.Code(err) != "CHECKPOINT_ORDER" {
		t.Fatalf("invalid dependency order accepted or misclassified: %v", err)
	}
	after := h.doc("PLAN-EXAMPLE")
	if after.Hash() != before.Hash() || after.Revision() != before.Revision() {
		t.Fatal("rejected reorder changed artifact")
	}
}

func TestRecordReorderRejectsMalformedOrStaleRequestsAtomically(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	before := h.doc("PLAN-EXAMPLE")
	for _, tc := range []struct {
		name   string
		change object
		code   string
		stale  bool
	}{
		{"duplicate ID", object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-01", "CP-01"}}, "INVALID_PERMUTATION", false},
		{"omitted ID", object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-01"}}, "INVALID_PERMUTATION", false},
		{"foreign ID", object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-01", "CP-BOGUS"}}, "INVALID_PERMUTATION", false},
		{"non-symbol collection", object{"op": "record.reorder", "collection": "criterion_dispositions", "ids": []any{"AC-001"}}, "INVALID_COLLECTION", false},
		{"protected field", object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-01", "CP-02"}, "execution": object{}}, "INVALID_MODEL", false},
		{"stale revision", object{"op": "record.reorder", "collection": "checkpoints", "ids": []any{"CP-01", "CP-02"}}, "REVISION_CONFLICT", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			expected := object{"revision": before.Revision(), "model_sha256": before.Hash()}
			if tc.stale {
				expected["revision"] = before.Revision() - 1
			}
			_, err := h.request("apply", object{
				"artifact_id": "PLAN-EXAMPLE", "operation_id": h.next(), "expected": expected,
				"changes": []any{
					object{"op": "header.update", "fields": object{"summary": "This must not persist."}},
					tc.change,
				},
			})
			if fault.Code(err) != tc.code {
				t.Fatalf("want %s, got %v", tc.code, err)
			}
			after := h.doc("PLAN-EXAMPLE")
			if after.Hash() != before.Hash() || after.Revision() != before.Revision() {
				t.Fatal("rejected batch changed artifact")
			}
		})
	}
}
