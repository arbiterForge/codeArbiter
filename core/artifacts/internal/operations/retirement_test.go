package operations

// NT-05 / N-F10: retirement keeps typed ownership of retained history.
// Transition rows: N06:03, N06:04, N04:02, N04:03, N13:01.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func retireT002(f *assistiveFixture) (any, error) {
	return f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.update", "symbol": "CP-01", "fields": object{"tasks": model.List("T-001")}},
		object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": model.List("T-001")}},
		object{"op": "record.retire", "symbol": "T-002", "reason": "Folded into T-001."},
	}}))
}

func tombstone(d *model.Document, id string) object {
	for _, v := range model.A(d.Norm()["retired_symbols"]) {
		if model.S(model.M(v)["id"]) == id {
			return model.M(v)
		}
	}
	return nil
}

// Acceptance "Checked task retirement".
func TestRetiringCheckedTaskKeepsTypedHistory(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, outcome := range []string{"pass", "fail"} {
		r := reportedCommand(outcome, true)
		r["task"] = "T-002"
		f.mutate("task-check", r)
	}
	before := model.A(model.M(model.M(f.doc("PLAN-EXAMPLE").Data["execution"])["task_check_observations"])["T-002"])
	if _, err := retireT002(f); err != nil {
		t.Fatalf("retiring a task with recorded checks was refused: %v", err)
	}
	d := f.doc("PLAN-EXAMPLE")
	stone := tombstone(d, "T-002")
	if stone["original_kind"] != "tasks" || d.Data["schema_version"] != model.RetirementVersion {
		t.Fatalf("tombstone lost its original kind or the version label: %v %v", stone, d.Data["schema_version"])
	}
	after := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-002"])
	if !equalValue(before, after) || len(after) != 2 {
		t.Fatal("retirement deleted or changed retained check history")
	}
	html, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"))
	if err != nil || !strings.Contains(string(html), "Retained command checks of this retired task") {
		t.Fatalf("rendered plan hides the retired task's retained checks: %v", err)
	}
	if caps := f.call("capabilities", object{}); caps["retirement_schema_version"] != model.RetirementVersion {
		t.Fatalf("capabilities do not advertise the retirement schema label: %v", caps["retirement_schema_version"])
	}
	if _, live := model.M(model.M(d.Data["execution"])["tasks"])["T-002"]; live {
		t.Fatal("retired task still has live scheduling state")
	}
	for _, row := range model.A(f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})["tasks"]) {
		if model.M(row)["task"] == "T-002" {
			t.Fatal("retired task appears in scheduling")
		}
	}
	if _, err := f.request("task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-002"})); fault.Code(err) != "UNKNOWN_TASK" {
		t.Fatalf("retired task accepted new progress: %v", err)
	}
	// Stable IDs stay reserved: no re-add, no repeated retirement.
	reused := object{}
	for key, value := range model.M(model.A(f.doc("PLAN-EXAMPLE").Norm()["tasks"])[0]) {
		reused[key] = value
	}
	reused["id"] = "T-002"
	if _, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.add", "collection": "tasks", "record": reused},
	}})); err == nil {
		t.Fatal("a duplicate/retired ID was reused")
	}
	if _, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.retire", "symbol": "T-002", "reason": "Again."},
	}})); err == nil {
		t.Fatal("a tombstone was retired twice")
	}
	// Later ordinary writes keep the version label and never downgrade it.
	f.mutate("task-start", object{"task": "T-001"})
	r := reportedCommand("unknown", true)
	f.mutate("task-check", r)
	f.mutate("task-review", object{"task": "T-001"})
	f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Batch implemented."})
	f.mutate("plan-bind", object{"spec_id": "SPEC-EXAMPLE"})
	if v := f.doc("PLAN-EXAMPLE").Data["schema_version"]; v != model.RetirementVersion {
		t.Fatalf("a later ordinary write relabeled the plan %v", v)
	}
	f.call("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-002", "mode": "exact"})
	f.assertNoAuthorityFiles()
}

// Retiring a checkpoint with a retained scope baseline keeps the baseline as
// typed history instead of failing with ORPHAN_STATE.
func TestRetiringCheckpointKeepsScopeBaseline(t *testing.T) {
	f := newAssistiveFixture(t)
	// A baseline is written only by a receipted review; seed one through the
	// supported repair-free path: write it via a real apply is not possible, so
	// construct it on a retirement candidate document directly.
	d := f.doc("PLAN-EXAMPLE")
	next, err := d.Clone()
	if err != nil {
		t.Fatal(err)
	}
	model.M(model.M(next.Data["execution"])["scopes"])["CP-02"] = object{"base_input_sha256": strings.Repeat("a", 64), "plan_sha256": d.NormHash()}
	norm := next.Norm()
	norm["checkpoints"] = model.A(norm["checkpoints"])[:1]
	cp := model.M(model.A(norm["checkpoints"])[0])
	cp["tasks"] = model.List("T-001", "T-002", "T-003")
	task := model.M(model.A(norm["tasks"])[2])
	task["checkpoint"], task["execution_scope"] = "CP-01", "CP-01"
	norm["retired_symbols"] = append(model.A(norm["retired_symbols"]), object{"id": "CP-02", "retired_in_revision": d.Revision(), "reason": "Merged into CP-01.", "replacement_ref": "CP-01", "original_kind": "checkpoints"})
	next.Data["schema_version"] = model.RetirementVersion
	if _, err := model.Check(next.Data); err != nil {
		t.Fatalf("typed checkpoint tombstone was not admitted: %v", err)
	}
	if es := validateStructural(next.Data); len(es) != 0 {
		t.Fatalf("retained scope baseline of a typed retired checkpoint is orphaned: %v", es)
	}
	stone := model.M(model.A(norm["retired_symbols"])[len(model.A(norm["retired_symbols"]))-1])
	delete(stone, "original_kind")
	if es := validateStructural(next.Data); len(es) == 0 {
		t.Fatal("an untyped legacy tombstone was trusted to own a scope baseline")
	}
}

// Acceptance "Unknown legacy kind": an untyped tombstone is never resolved
// from its ID prefix, and the new field cannot ride on an old version label.
func TestUntypedTombstoneDoesNotOwnHistory(t *testing.T) {
	f := newAssistiveFixture(t)
	r := reportedCommand("pass", true)
	r["task"] = "T-002"
	f.mutate("task-check", r)
	if _, err := retireT002(f); err != nil {
		t.Fatal(err)
	}
	d := f.doc("PLAN-EXAMPLE")
	legacy, _ := d.Clone()
	stone := tombstone(legacy, "T-002")
	delete(stone, "original_kind")
	if es := validateStructural(legacy.Data); len(es) == 0 || es[0].Code != "ORPHAN_STATE" {
		t.Fatalf("task-looking ID prefix was trusted as typed ownership: %v", es)
	}
	old, _ := d.Clone()
	old.Data["schema_version"] = "0.3.2"
	if _, err := model.Check(old.Data); fault.Code(err) != "UNSUPPORTED_VERSION" {
		t.Fatalf("typed tombstone was accepted under schema 0.3.2: %v", err)
	}
	bad, _ := d.Clone()
	tombstone(bad, "T-002")["original_kind"] = "retired_symbols"
	if es := validateStructural(bad.Data); len(es) == 0 {
		t.Fatal("tombstone accepted a non-record original kind")
	}
	for _, originalKind := range []string{"imaginary", "criteria", "task_check_observations"} {
		bad, _ := d.Clone()
		tombstone(bad, "T-002")["original_kind"] = originalKind
		if es := validateStructural(bad.Data); len(es) == 0 {
			t.Fatalf("plan tombstone accepted an absent record collection %q", originalKind)
		}
	}
}

func validateStructural(v object) []fault.Error {
	d, err := model.Check(v)
	if err != nil {
		return []fault.Error{{Code: fault.Code(err), Message: err.Error()}}
	}
	return validate.Structural(d)
}

func TestRetirementKindMustNameAnActualCollection(t *testing.T) {
	f := newAssistiveFixture(t)
	d, _ := f.doc("PLAN-EXAMPLE").Clone()
	d.Data["schema_version"] = model.RetirementVersion
	d.Norm()["retired_symbols"] = append(model.A(d.Norm()["retired_symbols"]), object{
		"id": "RETIRED-EXAMPLE", "retired_in_revision": d.Revision(),
		"reason": "Historical record retired.", "replacement_ref": nil, "original_kind": "imaginary",
	})
	if es := validateStructural(d.Data); len(es) == 0 {
		t.Fatal("a typed tombstone accepted an invented record collection")
	}
}
