package operations

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
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

func addTaskConstraints(f *assistiveFixture) {
	f.t.Helper()
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{
		object{"op": "record.add", "collection": "constraints", "record": object{
			"id": "CON-REFERENCED", "statement": "Preserve validated false values.", "applies_to": empty(), "source_refs": empty(),
		}},
		object{"op": "record.add", "collection": "constraints", "record": object{
			"id": "CON-APPLICABLE", "statement": "Report ambiguous configuration.", "applies_to": model.List("AC-001"), "source_refs": empty(),
		}},
		object{"op": "record.add", "collection": "constraints", "record": object{
			"id": "CON-SCOPE", "statement": "Preserve the input scope contract.", "applies_to": model.List("SCOPE-01"), "source_refs": empty(),
		}},
		object{"op": "record.add", "collection": "constraints", "record": object{
			"id": "CON-GLOBAL", "statement": "Never expose secret configuration values.", "applies_to": model.List("all"), "source_refs": empty(),
		}},
		object{"op": "record.add", "collection": "constraints", "record": object{
			"id": "CON-UNRELATED", "statement": "Parsing remains out of scope.", "applies_to": model.List("NON-GOAL-01"), "source_refs": empty(),
		}},
		object{"op": "record.update", "symbol": "AC-001", "fields": object{"constraint_refs": model.List("CON-REFERENCED")}},
	}}))
	f.mutate("plan-bind", object{"spec_id": "SPEC-EXAMPLE"})
}

func TestTaskContextIncludesSelectedCriterionAndApplicableConstraints(t *testing.T) {
	f := newAssistiveFixture(t)
	addTaskConstraints(f)
	packet := packetFor(f, "T-001")
	criterion := model.M(model.A(packet["criteria"])[0])
	for field, want := range f.doc("SPEC-EXAMPLE").Symbols.ByID["AC-001"].Value {
		if !reflect.DeepEqual(criterion[field], want) {
			t.Errorf("task context omitted or changed criterion field %s: got %v; want %v", field, criterion[field], want)
		}
	}
	constraints := model.A(packet["constraints"])
	if len(constraints) != 4 {
		t.Fatalf("task context should include exactly its referenced, applicable, scope and global constraints: %v", constraints)
	}
	for _, value := range constraints {
		got := model.M(value)
		id := model.S(got["id"])
		if id == "CON-UNRELATED" || got["ref"] != "SPEC-EXAMPLE#"+id {
			t.Fatalf("constraint is unrelated or not source-bound: %v", got)
		}
		for field, want := range f.doc("SPEC-EXAMPLE").Symbols.ByID[id].Value {
			if !reflect.DeepEqual(got[field], want) {
				t.Errorf("constraint %s omitted field %s", id, field)
			}
		}
	}
	if packet["context_complete"] != false || len(model.A(packet["omitted_references"])) == 0 {
		t.Fatal("packet hid the remaining referenced intent/source context")
	}
	f.assertNoAuthorityFiles()
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

func TestTaskContextKeepsApplicableFailureBeyondRecentUnrelatedPasses(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "fail", true)
	for i := 0; i < 3; i++ {
		r := reportedCommand("pass", false)
		model.M(r["check"])["argv"] = model.List("python", "-c", "print('unrelated')")
		f.mutate("task-check", r)
	}
	packet := packetFor(f, "T-001")
	summary := model.M(packet["check_summary"])
	if summary["has_conflicting_check_reports"] != true || len(model.A(summary["conflicting_check_reports"])) != 1 {
		t.Fatalf("current declared failure disappeared behind unrelated passes: %v", packet)
	}
	if summary["assessment"] != "caller_reported_advisory" || summary["evidence_assessed"] != false ||
		summary["scope_complete"] != false || summary["verification_boundary_assessed"] != false {
		t.Fatalf("caller-report summary claimed source scope or attested verification: %v", summary)
	}
	if packet["check_reports_omitted"] != int64(1) || packet["checks_are_verified"] != false || packet["evidence_assessed"] != false {
		t.Fatalf("compact packet misstated history or promoted reports: %v", packet)
	}
	if !strings.Contains(model.S(packet["next_action"]), "reported failing") {
		t.Fatalf("failure did not outrank latest unrelated pass: %v", packet["next_action"])
	}
	reportFor(f, "pass", true)
	resolved := packetFor(f, "T-001")
	if model.M(resolved["check_summary"])["has_conflicting_check_reports"] != false {
		t.Fatalf("later applicable declared pass did not clear failure: %v", resolved)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextCapsUnresolvedDetailsAndCarriesOmittedCountToWorkView(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	first := model.M(model.A(f.doc("PLAN-EXAMPLE").Symbols.ByID["T-001"].Value["verification"])[0])
	verification := []any{}
	for i := 0; i < 4; i++ {
		command, err := canonical.Clone(first)
		if err != nil {
			t.Fatal(err)
		}
		command["argv"] = model.List("go", "test", "./...", "-run", "TestBoundedFailure"+string(rune('A'+i)))
		command["assertion"] = "Reported command remains unresolved."
		verification = append(verification, command)
	}
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001", "fields": object{"verification": verification},
	}}})
	for i, value := range verification {
		command := model.M(value)
		report := reportedCommand("fail", true)
		check := model.M(report["check"])
		check["argv"] = command["argv"]
		check["command_index"] = int64(i)
		f.mutate("task-check", report)
	}
	packet := packetFor(f, "T-001")
	summary := model.M(packet["check_summary"])
	if got := len(model.A(summary["conflicting_check_reports"])); got != 3 ||
		model.I(summary["conflicting_check_reports_omitted"]) != 1 {
		t.Fatalf("task context did not cap four unresolved commands at three details plus one omitted: %v", summary)
	}
	created := f.call("work-create", object{"operation_id": "bounded-failure-work-001",
		"title": "Bounded failure view", "intent": "Keep every unresolved count visible", "work_type": "fix",
		"spec_id": "SPEC-EXAMPLE", "plan_id": "PLAN-EXAMPLE"})
	context := f.call("work-context", object{"work_id": created["work_id"]})
	workSummary := model.M(model.M(context["plan_task"])["check_summary"])
	if len(model.A(workSummary["conflicting_check_reports"])) != 3 ||
		model.I(workSummary["conflicting_check_reports_omitted"]) != 1 {
		t.Fatalf("work context lost the bounded unresolved summary: %v", workSummary)
	}
	html := model.S(f.call("work-view", object{"work_id": created["work_id"]})["html"])
	if !strings.Contains(html, "Unresolved reported failure: 4 declared command(s)") {
		t.Fatalf("work view did not combine detailed and omitted failures: %s", html)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskContextReportsFailureAlongsideStopsAndSourceDrift(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "fail", true)
	reportFor(f, "skip", true)
	reportFor(f, "unknown", true)
	f.mutate("task-block", object{"task": "T-001", "reason": "Owner stopped this work."})
	blocked := packetFor(f, "T-001")
	if model.M(blocked["check_summary"])["has_conflicting_check_reports"] != true ||
		!strings.Contains(model.S(blocked["next_action"]), "do not clear") {
		t.Fatalf("stop or unresolved failure disappeared: %v", blocked)
	}
	scopedWrite(t, f.root, "src/stage1.go", "package changed\n")
	stale := packetFor(f, "T-001")
	summary := model.M(stale["check_summary"])
	if summary["has_conflicting_check_reports"] != false || model.I(summary["check_reports_ignored"]) < 1 {
		t.Fatalf("source-stale reports were presented as current: %v", stale)
	}
	if !strings.Contains(model.S(stale["next_action"]), "do not clear") {
		t.Fatal("source drift overwrote the recorded owner stop")
	}
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
