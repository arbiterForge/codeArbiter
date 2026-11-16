//go:build linux || darwin || windows

package operations

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// This characterization uses only an owned ordinary-work
// journal is converted to a supported historical/resultless representation;
// no approvals or synthetic authority receipts are needed or fabricated.
func TestN02ResultlessReplayRequiresRefreshWithoutInventingIdentity(t *testing.T) {
	for _, format := range []string{"codearbiter.transaction/0.1.0", "codearbiter.transaction/0.2.0"} {
		t.Run(format, func(t *testing.T) {
			h := newHarness(t)
			h.run("init-store", object{})
			request := object{"operation_id": "legacy-fallback-create-001", "title": "Original", "intent": "Keep the later work identity", "work_type": "fix"}
			created := h.run("work-create", request)
			id := model.S(created["work_id"])
			if id == "" {
				t.Fatal("ordinary owner did not create a work identity")
			}
			later := h.run("work-update", object{"operation_id": "legacy-fallback-later-001", "work_id": id, "action": "rename", "title": "Later", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
			if later["model_sha256"] == created["model_sha256"] {
				t.Fatal("fixture needs a genuinely later identity")
			}
			journalPath := filepath.Join(h.root, ".codearbiter", ".artifacts", "transactions", "legacy-fallback-create-001.json")
			bytes, err := os.ReadFile(journalPath)
			if err != nil {
				t.Fatal(err)
			}
			journal, err := canonical.Object(bytes)
			if err != nil {
				t.Fatal(err)
			}
			if journal["state"] != "committed" || model.M(journal["result"])["work_id"] != id {
				t.Fatal("fixture journal did not retain the real original result")
			}
			journal["format"] = format
			if format == "codearbiter.transaction/0.1.0" {
				delete(journal, "result")
			} else {
				journal["result"] = nil
			}
			legacy, err := canonical.Marshal(journal)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(journalPath, legacy, 0600); err != nil {
				t.Fatal(err)
			}
			before := readModeTree(t, h.root)
			raw, replayErr := h.request("work-create", request)
			after := readModeTree(t, h.root)
			if replayErr != nil {
				t.Fatalf("supported resultless replay failed: %v; tree changed=%v", replayErr, !reflect.DeepEqual(before, after))
			}
			result := model.M(raw)
			transaction, ok := result["transaction"].(store.Outcome)
			if len(result) != 2 || result["refresh_required"] != true || !ok || !transaction.Replay || transaction.State != "committed" || transaction.OperationID != "legacy-fallback-create-001" || transaction.Result != nil || len(transaction.Paths) == 0 {
				t.Fatalf("resultless retry fabricated identity or lost its original terminal receipt: %#v", raw)
			}
			for _, key := range []string{"artifact_id", "work_id", "revision", "model_sha256", "normative_sha256", "title", "path", "kind"} {
				if _, present := result[key]; present {
					t.Fatalf("resultless response fabricated %s", key)
				}
			}
			if !reflect.DeepEqual(before, after) {
				t.Fatal("same-ID replay rewrote the later tree or retained journal/history")
			}
			current := h.run("work-get", object{"work_id": id})
			if current["title"] != "Later" || current["model_sha256"] != later["model_sha256"] || current["revision"] != later["revision"] {
				t.Fatal("legacy replay replaced later work identity")
			}
			changed, err := canonical.Clone(request)
			if err != nil {
				t.Fatal(err)
			}
			changed["title"] = "Different request under the same ID"
			before = readModeTree(t, h.root)
			_, mismatch := h.request("work-create", changed)
			after = readModeTree(t, h.root)
			if fault.Code(mismatch) != "OPERATION_ID_REUSE" || !reflect.DeepEqual(before, after) {
				t.Fatalf("changed request was not a no-write refusal: %v", mismatch)
			}
		})
	}
}
