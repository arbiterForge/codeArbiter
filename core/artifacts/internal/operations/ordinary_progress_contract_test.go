package operations

// N09 ordinary-progress contracts. These are engine unit fixtures, not user
// acceptance or evidence qualification. ADR-0046 / D-PROGRESS=B retains
// recorded progress and history; none of these assertions restores destructive
// downstream STALE propagation.

import (
	"maps"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// References are explicitly unassessed historical fixture values. They are not
// manufactured receipts and no test claims that their presence verifies work.
func n09HistoricalRefs() []any {
	return model.List(".codearbiter/.artifacts/receipts/historical-one.json", ".codearbiter/.artifacts/receipts/historical-two.json")
}

func n09Seed(t *testing.T, f *assistiveFixture, change func(*model.Document)) {
	t.Helper()
	d := f.doc("PLAN-EXAMPLE")
	change(d)
	prepared, err := render.Prepare(d.Data)
	if err != nil {
		t.Fatal(err)
	}
	data, err := render.Render(prepared)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"), data, 0600); err != nil {
		t.Fatal(err)
	}
}

func n09State(t *testing.T, f *assistiveFixture, label string) {
	t.Helper()
	n09Seed(t, f, func(d *model.Document) {
		d.Data["schema_version"] = model.SchemaVersion
		s := state(d, "T-001")
		s["state"], s["reason"], s["evidence_refs"] = label, "Retained original reason.", n09HistoricalRefs()
	})
}

func n09Refuse(t *testing.T, f *assistiveFixture, op string, request object, code string) {
	t.Helper()
	before := descriptorEffectSnapshot(t, f.root)
	_, err := f.request(op, request)
	if err == nil || (code != "" && fault.Code(err) != code) {
		t.Fatalf("%s expected refusal %s, got %v", op, code, err)
	}
	if !maps.Equal(before, descriptorEffectSnapshot(t, f.root)) {
		t.Fatal("refused ordinary progress changed retained files")
	}
}

func TestN09StartLiveStateCASAndReplayBoundaries(t *testing.T) {
	for _, label := range []string{"IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED", "BLOCKED", "STALE"} {
		t.Run(label, func(t *testing.T) {
			f := newAssistiveFixture(t)
			n09State(t, f, label)
			n09Refuse(t, f, "task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-001"}), "NOT_PENDING")
		})
	}
	t.Run("absent-and-retired", func(t *testing.T) {
		f := newAssistiveFixture(t)
		n09Refuse(t, f, "task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-404"}), "UNKNOWN_TASK")
		if _, err := retireT002(f); err != nil {
			t.Fatal(err)
		}
		n09Refuse(t, f, "task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-002"}), "UNKNOWN_TASK")
	})
	t.Run("live-pending-cas-replay", func(t *testing.T) {
		f := newAssistiveFixture(t)
		n09State(t, f, "PENDING")
		stale := f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})
		f.mutate("task-start", object{"task": "T-003"})
		n09Refuse(t, f, "task-start", stale, "REVISION_CONFLICT")
		before := f.doc("PLAN-EXAMPLE")
		request := f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})
		f.call("task-start", request)
		after := f.doc("PLAN-EXAMPLE")
		expected := state(before, "T-001")
		expected["state"], expected["reason"] = "IN_PROGRESS", nil
		if !equalValue(state(after, "T-001"), expected) || after.NormHash() != before.NormHash() {
			t.Fatal("start changed more than selected implementation progress")
		}
		if !equalValue(state(before, "T-003"), state(after, "T-003")) {
			t.Fatal("start replaced unrelated recorded work")
		}
		settled := descriptorEffectSnapshot(t, f.root)
		f.call("task-start", request)
		if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
			t.Fatal("exact start replay repeated effects")
		}
		f.assertNoAuthorityFiles()
	})
}

func TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals(t *testing.T) {
	for _, label := range []string{"PENDING", "BLOCKED", "STALE", "DONE", "ACCEPTED"} {
		t.Run(label, func(t *testing.T) {
			f := newAssistiveFixture(t)
			n09State(t, f, label)
			n09Refuse(t, f, "task-review", f.mutation("PLAN-EXAMPLE", object{"task": "T-001"}), "INVALID_TRANSITION")
		})
	}
	t.Run("in-progress-and-review-repeat", func(t *testing.T) {
		f := newAssistiveFixture(t)
		n09State(t, f, "IN_PROGRESS")
		for repeat := 0; repeat < 2; repeat++ {
			before := f.doc("PLAN-EXAMPLE")
			request := f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})
			f.call("task-review", request)
			after := f.doc("PLAN-EXAMPLE")
			expected := state(before, "T-001")
			expected["state"], expected["reason"] = "REVIEW", ordinaryReviewReason
			if !equalValue(state(after, "T-001"), expected) || after.NormHash() != before.NormHash() || after.Revision() != before.Revision()+1 {
				t.Fatal("ordinary REVIEW repeat lost history or changed its meaning")
			}
			if !equalValue(state(before, "T-002"), state(after, "T-002")) {
				t.Fatal("ordinary review reset dependent work")
			}
			packet := packetFor(f, "T-001")
			if packet["evidence_assessed"] != false || packet["checks_are_verified"] != false {
				t.Fatal("historical references became proof merely through ordinary REVIEW")
			}
			settled := descriptorEffectSnapshot(t, f.root)
			f.call("task-review", request)
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("exact ordinary review replay repeated effects")
			}
		}
		f.assertNoAuthorityFiles()
	})
}

func TestN09OrdinaryReconcileAllLabelsTargetsAndHistory(t *testing.T) {
	for _, source := range []string{"PENDING", "IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED", "BLOCKED", "STALE"} {
		for _, target := range []string{"PENDING", "REVIEW", "BLOCKED"} {
			t.Run(source+"-to-"+target, func(t *testing.T) {
				f := newAssistiveFixture(t)
				n09State(t, f, source)
				n09Seed(t, f, func(d *model.Document) {
					s := state(d, "T-002")
					s["state"], s["reason"] = "BLOCKED", "Independent user stop."
				})
				before := f.doc("PLAN-EXAMPLE")
				reason := "Explicit correction of recorded implementation progress."
				request := f.mutation("PLAN-EXAMPLE", object{"task": "T-001", "state": target, "reason": reason})
				f.call("task-reconcile", request)
				after := f.doc("PLAN-EXAMPLE")
				expected := state(before, "T-001")
				expected["state"], expected["reason"] = target, reason
				if !equalValue(state(after, "T-001"), expected) || after.NormHash() != before.NormHash() || after.Data["schema_version"] != before.Data["schema_version"] {
					t.Fatal("ordinary reconcile replaced history, requirements or schema")
				}
				for _, id := range []string{"T-002", "T-003"} {
					if !equalValue(state(before, id), state(after, id)) {
						t.Fatal("ordinary reconcile invalidated dependent progress or an independent stop")
					}
				}
				settled := descriptorEffectSnapshot(t, f.root)
				f.call("task-reconcile", request)
				if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
					t.Fatal("ordinary reconcile replay repeated effects")
				}
				packet := packetFor(f, "T-001")
				if packet["evidence_assessed"] != false || packet["checks_are_verified"] != false {
					t.Fatal("ordinary correction turned historical references into assessed proof")
				}
				f.assertNoAuthorityFiles()
			})
		}
	}
	t.Run("closed-target-and-reason", func(t *testing.T) {
		f := newAssistiveFixture(t)
		for _, target := range []string{"IN_PROGRESS", "DONE", "ACCEPTED", "STALE"} {
			n09Refuse(t, f, "task-reconcile", f.mutation("PLAN-EXAMPLE", object{"task": "T-001", "state": target, "reason": "An explicit but invalid target."}), "")
		}
		for _, fields := range []object{{"task": "T-001", "state": "PENDING"}, {"task": "T-001", "state": "PENDING", "reason": ""}} {
			n09Refuse(t, f, "task-reconcile", f.mutation("PLAN-EXAMPLE", fields), "")
		}
	})
}

func TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation(t *testing.T) {
	t.Run("missing-empty-retired-reason", func(t *testing.T) {
		f := newAssistiveFixture(t)
		n09Refuse(t, f, "accept-scope", f.mutation("PLAN-EXAMPLE", object{"scope": "CP-MISSING", "reason": "An explicit implementation note."}), "UNKNOWN_SCOPE")
		// The maintained checkpoint schema itself rejects emptiness. Do not
		// manufacture a live invalid document to reach a defensive inner guard.
		n09Refuse(t, f, "apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.add", "collection": "checkpoints", "record": object{"id": "CP-EMPTY", "title": "Empty checkpoint fixture", "tasks": empty(), "exit": "No work.", "depends_on": empty()}}}}), "INVALID_MODEL")
		f.mutate("apply", object{"changes": []any{
			object{"op": "record.update", "symbol": "CP-01", "fields": object{"tasks": model.List("T-001", "T-002", "T-003")}},
			object{"op": "record.update", "symbol": "T-003", "fields": object{"checkpoint": "CP-01", "execution_scope": "CP-01"}},
			object{"op": "record.retire", "symbol": "CP-02", "reason": "Merge this checkpoint's task into CP-01."},
		}})
		n09Refuse(t, f, "accept-scope", f.mutation("PLAN-EXAMPLE", object{"scope": "CP-02", "reason": "An explicit implementation note."}), "UNKNOWN_SCOPE")
		for _, fields := range []object{{"scope": "CP-01"}, {"scope": "CP-01", "reason": ""}, {"scope": "CP-01", "reason": "   "}} {
			n09Refuse(t, f, "accept-scope", f.mutation("PLAN-EXAMPLE", fields), "")
		}
	})
	for _, label := range []string{"PENDING", "BLOCKED", "STALE"} {
		t.Run(label, func(t *testing.T) {
			f := newAssistiveFixture(t)
			n09State(t, f, label)
			n09Seed(t, f, func(d *model.Document) { state(d, "T-002")["state"] = "REVIEW" })
			n09Refuse(t, f, "accept-scope", f.mutation("PLAN-EXAMPLE", object{"scope": "CP-01", "reason": "An explicit implementation note."}), "SCOPE_UNFINISHED")
		})
	}
	t.Run("done-with-new-operation-id", func(t *testing.T) {
		f := newAssistiveFixture(t)
		n09State(t, f, "DONE")
		n09Seed(t, f, func(d *model.Document) { state(d, "T-002")["state"] = "IN_PROGRESS" })
		for _, reason := range []string{"Implementation completed.", "A distinct ordinary completion note."} {
			before := f.doc("PLAN-EXAMPLE")
			request := f.mutation("PLAN-EXAMPLE", object{"scope": "CP-01", "reason": reason})
			f.call("accept-scope", request)
			after := f.doc("PLAN-EXAMPLE")
			for _, id := range []string{"T-001", "T-002"} {
				expected := state(before, id)
				expected["state"], expected["reason"] = "DONE", reason+" Implementation completion only; verification and review are not assessed."
				if !equalValue(state(after, id), expected) {
					t.Fatal("new ordinary DONE operation changed historical refs or invented acceptance")
				}
				if strings.Contains(model.S(state(after, id)["reason"]), "passed") {
					t.Fatal("implementation note claimed passing checks")
				}
			}
			if after.Revision() != before.Revision()+1 || after.NormHash() != before.NormHash() || !equalValue(state(after, "T-003"), state(before, "T-003")) {
				t.Fatal("ordinary scope completion changed unrelated content")
			}
			settled := descriptorEffectSnapshot(t, f.root)
			f.call("accept-scope", request)
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("exact scope replay repeated effects")
			}
		}
		if f.doc("PLAN-EXAMPLE").Data["schema_version"] != model.SchemaVersion {
			t.Fatal("ordinary DONE lost its explicit 0.3.2 schema epoch")
		}
		f.assertNoAuthorityFiles()
	})
}
