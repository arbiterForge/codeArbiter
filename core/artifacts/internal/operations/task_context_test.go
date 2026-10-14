package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func packetFor(f *assistiveFixture, task string) object {
	f.t.Helper()
	return f.call("task-context", object{
		"artifact_id": "PLAN-EXAMPLE", "task": task,
		"model_sha256": f.doc("PLAN-EXAMPLE").Hash(),
	})
}

func TestTaskContextReturnsBoundedReferencedContextWithoutAuthority(t *testing.T) {
	f := newAssistiveFixture(t)
	d := f.doc("PLAN-EXAMPLE")
	packet := packetFor(f, "T-001")
	if packet["assessment"] != "advisory" || packet["evidence_assessed"] != false || packet["context_complete"] != false {
		t.Fatalf("task context falsely claims verification/full context: %v", packet)
	}
	if packet["model_sha256"] != d.Hash() || packet["binding_current"] != true {
		t.Fatalf("task packet lost source identity: %v", packet)
	}
	task := model.M(packet["task"])
	if task["id"] != "T-001" || task["verification"] == nil || task["steps"] == nil {
		t.Fatalf("task packet omitted implementation obligations: %v", task)
	}
	criteria := model.A(packet["criteria"])
	if len(criteria) != 1 || model.M(criteria[0])["ref"] != "SPEC-EXAMPLE#AC-001" {
		t.Fatalf("task criteria are not source-bound: %v", criteria)
	}
	exact := f.call("read", object{"artifact_id": d.ID(), "symbol": "T-001", "mode": "exact"})
	if model.M(exact["record"])["title"] != task["title"] {
		t.Fatal("compact packet disagrees with canonical symbol read")
	}
	if _, exists := packet["authority"]; exists {
		t.Fatal("read response invented an authority result")
	}
	if _, exists := packet["context_ticket"]; exists {
		t.Fatal("task packet created a delivery ticket")
	}
	if _, exists := packet["all_accepted_and_current"]; exists {
		t.Fatal("task packet asserted accepted proof")
	}
	if d.Hash() != f.doc(d.ID()).Hash() {
		t.Fatal("reading task context mutated the document")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "fact")
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.add", "collection": "prerequisites",
		"record": object{
			"id": "LEGACY-QUESTION", "title": "Old unscoped condition",
			"requirement": "Needs applicability triage.", "source_refs": empty(),
		},
	}}})
	first := packetFor(f, "T-001")
	third := packetFor(f, "T-003")
	if len(model.A(first["prerequisites"])) != 1 || len(model.A(first["waiting_prerequisites"])) != 1 {
		t.Fatalf("affected task lost its scoped prerequisite: %v", first)
	}
	if len(model.A(third["prerequisites"])) != 0 || len(model.A(third["waiting_prerequisites"])) != 0 {
		t.Fatal("unrelated task inherited a prerequisite")
	}
	if len(model.A(first["unscoped_prerequisites"])) != 1 || len(model.A(third["unscoped_prerequisites"])) != 1 {
		t.Fatal("unknown legacy applicability disappeared")
	}
	f.mutate("prerequisite", prerequisiteReport("satisfied", "tool_result"))
	complete := packetFor(f, "T-001")
	if len(model.A(complete["waiting_prerequisites"])) != 0 {
		t.Fatal("current recorded fact did not update task advice")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextShowsStopsAndUnfinishedDependencies(t *testing.T) {
	f := newAssistiveFixture(t)
	second := packetFor(f, "T-002")
	if len(model.A(second["waiting_on"])) != 1 || model.A(second["waiting_on"])[0] != "T-001" {
		t.Fatalf("task does not name actual dependency: %v", second)
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "User requested a stop."})
	blocked := packetFor(f, "T-001")
	if blocked["state"] != "BLOCKED" || !strings.Contains(model.S(blocked["next_action"]), "do not clear") {
		t.Fatal("task packet hid an explicit stop")
	}
	f.mutate("task-reconcile", object{"task": "T-001", "state": "PENDING", "reason": "Owner resumed, no worker active."})
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	ready := packetFor(f, "T-002")
	if len(model.A(ready["waiting_on"])) != 0 || ready["evidence_assessed"] != false {
		t.Fatal("recorded predecessor progress was treated as verified evidence")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextRejectsStalePlanAndMissingOrWrongSubjects(t *testing.T) {
	f := newAssistiveFixture(t)
	hash := f.doc("PLAN-EXAMPLE").Hash()
	for _, req := range []object{
		{"artifact_id": "PLAN-EXAMPLE", "task": "T-MISSING", "model_sha256": hash},
		{"artifact_id": "SPEC-EXAMPLE", "task": "T-001", "model_sha256": f.doc("SPEC-EXAMPLE").Hash()},
	} {
		if _, err := f.request("task-context", req); err == nil {
			t.Fatal("unknown or wrong-kind task accepted")
		}
	}
	f.mutate("task-start", object{"task": "T-001"})
	if _, err := f.request("task-context", object{
		"artifact_id": "PLAN-EXAMPLE", "task": "T-001", "model_sha256": hash,
	}); fault.Code(err) != "STALE_CURSOR" {
		t.Fatalf("stale task identity accepted: %v", err)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade(t *testing.T) {
	f := newAssistiveFixture(t)
	initial := packetFor(f, "T-001")
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{
		"op": "header.update", "fields": object{"summary": "Requirements refined after the prior plan binding."},
	}}}))
	updated := packetFor(f, "T-001")
	if updated["binding_current"] != false || updated["bound_source_normative_sha256"] != initial["bound_source_normative_sha256"] {
		t.Fatal("changed source binding was hidden or silently rebased")
	}
	if !strings.Contains(model.S(updated["next_action"]), "binding changed") {
		t.Fatal("outdated requirements lack an explanatory next action")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextBoundsWholePacketWithoutPartialDisclosure(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001", "fields": object{"steps": model.List(strings.Repeat("x", 6500))},
	}}})
	if _, err := f.request("task-context", object{
		"artifact_id": "PLAN-EXAMPLE", "task": "T-001",
		"model_sha256": f.doc("PLAN-EXAMPLE").Hash(), "budget": int64(4096),
	}); fault.Code(err) != "RECORD_TOO_LARGE" {
		t.Fatalf("oversized packet did not fail rather than silently truncate: %v", err)
	}
	if packet := f.call("task-context", object{
		"artifact_id": "PLAN-EXAMPLE", "task": "T-001",
		"model_sha256": f.doc("PLAN-EXAMPLE").Hash(), "budget": int64(65536),
	}); model.M(packet["task"])["id"] != "T-001" {
		t.Fatal("complete packet missing with supported larger budget")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextAvoidsWholeSourceSnapshots(t *testing.T) {
	f := newAssistiveFixture(t)
	// This input exceeds the snapshot's real per-file bound, establishing a
	// negative control for any accidental whole-tree scan in a task read.
	large, err := os.Create(filepath.Join(f.root, "unrelated.bin"))
	if err != nil {
		t.Fatal(err)
	}
	if err := large.Truncate(33 << 20); err != nil {
		large.Close()
		t.Fatal(err)
	}
	if err := large.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := f.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err == nil {
		t.Fatal("snapshot negative control unexpectedly succeeded")
	}
	packetFor(f, "T-001")
	f.assertNoAuthorityFiles()
}
