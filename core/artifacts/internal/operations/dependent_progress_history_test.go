package operations

// N11:03 under accepted ADR-0046 / D-PROGRESS=B. These engine fixtures
// exercise retained progress/history and derived readiness, never the old
// destructive downstream STALE effect or actual user/host approval.

import (
	"bytes"
	"encoding/json"
	"maps"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops(t *testing.T) {
	for _, mode := range []string{"ancestor-block", "receipted-pending", "receipted-blocked"} {
		t.Run(mode, func(t *testing.T) {
			h, f := receiptedReconcileFixture(t, true)
			// Prime the real progress epoch before capturing task-scoped
			// observations: a 0.3.2 approval cannot authorize a 0.3.4 plan.
			f.mutate("task-block", object{"task": "T-003", "reason": "Prime the isolated fixture's progress schema."})
			if f.doc("PLAN-EXAMPLE").Data["schema_version"] != model.ProgressVersion {
				t.Fatal("fixture did not enter the actual progress epoch")
			}
			h.approve("PLAN-EXAMPLE")
			f.mutate("task-reconcile", object{"task": "T-003", "state": "REVIEW", "reason": "Fixture priming complete; synthetic implementation remains available."})
			// Both downstream tasks acquire a real retained receipt through the
			// actual capture/receipt/reconcile owner. The synthetic observation
			// source is the existing fixture helper, not fabricated receipt bytes.
			for _, id := range []string{"T-002", "T-003"} {
				receipt := receiptedReconcileObservation(t, h, id, "PENDING")
				f.mutate("task-reconcile", object{"task": id, "state": "PENDING",
					"reason": "Synthetic fixture correction through the real receipt owner.", "receipt": receipt})
				f.mutate("task-start", object{"task": id})
				f.mutate("task-review", object{"task": id})
				refs := model.Strings(state(f.doc("PLAN-EXAMPLE"), id)["evidence_refs"])
				if len(refs) == 0 || !equalValue(model.List(refs...), model.List(receipt)) {
					t.Fatal("fixture lacks the actual selected downstream reconciliation receipt")
				}
			}
			for _, outcome := range []string{"fail", "unknown"} {
				report := reportedCommand(outcome, true)
				report["task"] = "T-002"
				f.mutate("task-check", report)
			}
			stopReason := "The owner independently stopped the downstream task."
			f.mutate("task-block", object{"task": "T-003", "reason": stopReason})
			operation, target := "task-block", "BLOCKED"
			reason := "The ancestor input is unavailable."
			fields := object{"task": "T-001", "reason": reason}
			selectedReceipt := ""
			if mode != "ancestor-block" {
				operation = "task-reconcile"
				if mode == "receipted-pending" {
					target = "PENDING"
				}
				selectedReceipt = receiptedReconcileObservation(t, h, "T-001", target)
				fields["state"], fields["receipt"] = target, selectedReceipt
			}
			before := f.doc("PLAN-EXAMPLE")
			history := model.A(model.M(model.M(before.Data["execution"])["task_check_observations"])["T-002"])
			if len(history) < 3 || model.M(history[len(history)-2])["outcome"] != "fail" ||
				model.M(history[len(history)-1])["outcome"] != "unknown" {
				t.Fatal("fixture lacks retained adverse dependent check history")
			}
			// Compare the complete dependent states/check history as bytes as
			// well as retaining each admitted receipt's original physical bytes.
			projection := func(d *model.Document) []byte {
				value := object{"T-002": state(d, "T-002"), "T-003": state(d, "T-003"),
					"checks": model.M(d.Data["execution"])["task_check_observations"]}
				encoded, err := json.Marshal(value)
				if err != nil {
					t.Fatal(err)
				}
				return encoded
			}
			beforeProjection := projection(before)
			receiptBytes := map[string][]byte{}
			for _, id := range []string{"T-002", "T-003"} {
				for _, ref := range model.Strings(state(before, id)["evidence_refs"]) {
					if !strings.HasPrefix(ref, ".codearbiter/.artifacts/receipts/") ||
						strings.Contains(ref, "..") || filepath.IsAbs(ref) {
						t.Fatal("receipt owner returned an unexpected fixture path")
					}
					value, err := os.ReadFile(filepath.Join(f.root, filepath.FromSlash(ref)))
					if err != nil {
						t.Fatal(err)
					}
					receiptBytes[ref] = value
				}
			}
			if len(receiptBytes) != 2 {
				t.Fatal("both dependents must have distinct nonempty retained receipts")
			}
			staleFields := object{}
			for key, value := range fields {
				staleFields[key] = value
			}
			request := f.mutation("PLAN-EXAMPLE", fields)
			stale := f.mutation("PLAN-EXAMPLE", staleFields)
			f.call(operation, request)
			after := f.doc("PLAN-EXAMPLE")
			if !bytes.Equal(beforeProjection, projection(after)) || before.NormHash() != after.NormHash() {
				t.Fatal("ancestor change overwrote dependent progress, history, stop or requirements")
			}
			for ref, want := range receiptBytes {
				got, err := os.ReadFile(filepath.Join(f.root, filepath.FromSlash(ref)))
				if err != nil || !bytes.Equal(got, want) {
					t.Fatal("ancestor change rewrote retained receipt bytes")
				}
			}
			selected := state(after, "T-001")
			if selected["state"] != target || selected["reason"] != reason {
				t.Fatal("selected ancestor transition was not recorded exactly")
			}
			wantedRefs := model.Strings(state(before, "T-001")["evidence_refs"])
			if selectedReceipt != "" {
				wantedRefs = append(wantedRefs, selectedReceipt)
			}
			if !equalValue(selected["evidence_refs"], model.List(wantedRefs...)) {
				t.Fatal("ancestor change lost prior refs or appended an unselected receipt")
			}
			packet := packetFor(f, "T-002")
			if packet["state"] != "REVIEW" || !equalValue(packet["waiting_on"], model.List("T-001")) ||
				packet["evidence_assessed"] != false || packet["checks_are_verified"] != false {
				t.Fatal("dependent recorded progress, readiness and unassessed history were collapsed")
			}
			seen := map[string]bool{}
			for _, value := range model.A(packet["reported_checks"]) {
				check := model.M(value)
				seen[model.S(check["reported_outcome"])] = true
				if check["evidence_assessed"] != false || check["named_tests_verified"] != false {
					t.Fatal("retained caller-reported checks became proof after ancestor change")
				}
			}
			if !seen["fail"] || !seen["unknown"] {
				t.Fatal("ancestor change hid retained adverse observations")
			}
			stop := packetFor(f, "T-003")
			if stop["state"] != "BLOCKED" || stop["reason"] != stopReason {
				t.Fatal("ancestor change cleared the independent stop")
			}
			settled := descriptorEffectSnapshot(t, f.root)
			f.call(operation, request)
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("exact ancestor request replay repeated effects")
			}
			if _, err := f.request(operation, stale); fault.Code(err) != "REVISION_CONFLICT" {
				t.Fatalf("stale ancestor writer did not refuse at CAS: %v", err)
			}
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("stale ancestor CAS refusal changed retained files")
			}
		})
	}
}
