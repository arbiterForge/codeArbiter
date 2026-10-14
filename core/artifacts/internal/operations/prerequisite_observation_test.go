package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

func addScopedPrerequisite(f *assistiveFixture, kind string) {
	f.t.Helper()
	f.mutate("apply", object{"changes": []any{
		object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": empty()}},
		object{"op": "record.add", "collection": "prerequisites", "record": object{
			"id": "GATE-LOCAL", "title": "Local service", "kind": kind,
			"requirement": "The local test service is available.", "task_refs": model.List("T-001"), "source_refs": empty(),
		}},
	}})
}
func prerequisiteReport(outcome, origin string) object {
	return object{"prerequisite": "GATE-LOCAL", "observation": object{
		"outcome": outcome, "origin": origin, "summary": "Recorded result: " + outcome,
		"source": "Session tool output: service probe; no command is executed by this record.",
	}}
}
func currentPrerequisite(f *assistiveFixture) object {
	f.t.Helper()
	page := f.call("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "GATE-LOCAL", "mode": "exact"})
	return model.M(page["prerequisite_assessment"])
}

func TestAssistiveScopedFactsKeepIndependentWorkMoving(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "fact")
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if advice["next_task"] != "T-003" {
		t.Fatalf("unobserved local prerequisite stopped independent work: %v", advice)
	}
	first := model.M(model.A(advice["tasks"])[0])
	if len(model.A(first["waiting_prerequisites"])) != 1 {
		t.Fatal("missing scoped prerequisite diagnostic")
	}
	f.mutate("prerequisite", prerequisiteReport("satisfied", "tool_result"))
	advice = f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if advice["next_task"] != "T-001" {
		t.Fatalf("recorded fact did not make dependent work available: %v", advice)
	}
	assessment := currentPrerequisite(f)
	if assessment["outcome"] != "satisfied" || assessment["provenance"] != "caller_reported" || assessment["evidence_assessed"] != false {
		t.Fatalf("recorded fact was misrepresented: %v", assessment)
	}
	d := f.doc("PLAN-EXAMPLE")
	if model.M(model.M(d.Data["execution"])["prerequisites"])["GATE-LOCAL"] != "not_satisfied" {
		t.Fatal("observation fabricated a legacy authority flag")
	}
	f.assertNoAuthorityFiles()
}

func TestAssistivePrerequisiteNewFailureAndUnknownReplaceOldSuccess(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "fact")
	for _, outcome := range []string{"satisfied", "unsatisfied", "unknown", "satisfied"} {
		f.mutate("prerequisite", prerequisiteReport(outcome, "tool_result"))
		if currentPrerequisite(f)["outcome"] != outcome {
			t.Fatal("older success masked the latest recorded result")
		}
		advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
		want := "T-003"
		if outcome == "satisfied" {
			want = "T-001"
		}
		if advice["next_task"] != want {
			t.Fatalf("wrong task after %s: %v", outcome, advice)
		}
	}
	// Definition changes make the previous observation inapplicable, not false
	// history. Neither title edits nor unrelated task method changes do this.
	f.mutate("apply", object{"changes": []any{
		object{"op": "record.update", "symbol": "GATE-LOCAL", "fields": object{"title": "Readable prerequisite title"}},
		object{"op": "record.update", "symbol": "T-003", "fields": object{"steps": model.List("Use a simpler implementation method.")}},
	}})
	if currentPrerequisite(f)["definition_current"] != true {
		t.Fatal("unrelated change invalidated a fact")
	}
	f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "GATE-LOCAL", "fields": object{"requirement": "The new service endpoint is available."}}}})
	assessment := currentPrerequisite(f)
	if assessment["definition_current"] != false || assessment["outcome"] != "unknown" || model.M(assessment["observation"])["outcome"] != "satisfied" {
		t.Fatalf("changed definition lost history or silently reused it: %v", assessment)
	}
	f.assertNoAuthorityFiles()
}

func TestAssistiveDecisionRemainsAUserChoiceNotAToolResult(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "decision")
	if currentPrerequisite(f)["needs_decision"] != true {
		t.Fatal("unresolved choice hidden")
	}
	before := f.doc("PLAN-EXAMPLE").Hash()
	for _, origin := range []string{"tool_result", "agent_report"} {
		_, err := f.request("prerequisite", f.mutation("PLAN-EXAMPLE", prerequisiteReport("satisfied", origin)))
		if fault.Code(err) != "DECISION_SOURCE_REQUIRED" {
			t.Fatalf("non-user source resolved user decision: %v", err)
		}
	}
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("rejected decision modified state")
	}
	f.mutate("prerequisite", prerequisiteReport("unknown", "agent_report"))
	f.mutate("prerequisite", prerequisiteReport("unsatisfied", "user_statement"))
	if currentPrerequisite(f)["outcome"] != "unsatisfied" {
		t.Fatal("user decline was lost")
	}
	if f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})["next_task"] != "T-003" {
		t.Fatal("decline affected unrelated work")
	}
	f.mutate("prerequisite", prerequisiteReport("satisfied", "user_statement"))
	if currentPrerequisite(f)["provenance"] != "caller_reported" {
		t.Fatal("conversation note claimed authenticated user authority")
	}
	f.assertNoAuthorityFiles()
}

func TestAssistivePrerequisiteObservationCASReplayAndClosedShapes(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "fact")
	request := f.mutation("PLAN-EXAMPLE", prerequisiteReport("satisfied", "tool_result"))
	f.call("prerequisite", request)
	before := f.doc("PLAN-EXAMPLE").Hash()
	f.call("prerequisite", request)
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("replay duplicated a result")
	}
	request["operation_id"] = f.next()
	if _, err := f.request("prerequisite", request); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale writer accepted: %v", err)
	}
	for _, alteration := range []func(object){
		func(r object) { r["receipt"] = "invented" },
		func(r object) { model.M(r["observation"])["provenance"] = "host_verified" },
		func(r object) { model.M(r["observation"])["recorded_at"] = "2026-10-14T00:00:00Z" },
		func(r object) { model.M(r["observation"])["summary"] = strings.Repeat("x", 2049) },
		func(r object) { model.M(r["observation"])["source"] = " " },
		func(r object) { r["prerequisite"] = "T-001" },
	} {
		r := f.mutation("PLAN-EXAMPLE", prerequisiteReport("satisfied", "tool_result"))
		alteration(r)
		if _, err := f.request("prerequisite", r); err == nil {
			t.Fatal("invalid observation accepted")
		}
		if f.doc("PLAN-EXAMPLE").Hash() != before {
			t.Fatal("rejected observation modified state")
		}
	}
}

func TestAssistivePrerequisiteReferencesHistoryAndInertHTML(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "fact")
	before := f.doc("PLAN-EXAMPLE").Hash()
	_, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{object{
		"op": "record.update", "symbol": "GATE-LOCAL", "fields": object{"task_refs": model.List("T-ABSENT")},
	}}}))
	if fault.Code(err) != "DANGLING_REFERENCE" || f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatalf("invalid task scope was saved: %v", err)
	}
	r := prerequisiteReport("satisfied", "tool_result")
	model.M(r["observation"])["source"] = "<script>alert('x')</script>; $(touch should-not-exist); Unicode: 日本語"
	f.mutate("prerequisite", r)
	d := f.doc("PLAN-EXAMPLE")
	batch := f.call("read-batch", object{"artifact_id": d.ID(), "model_sha256": d.Hash(), "symbols": model.List("GATE-LOCAL")})
	if model.M(model.A(batch["records"])[0])["prerequisite_assessment"] == nil {
		t.Fatal("batch lost the bounded assessment")
	}
	bytes, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(bytes), "<script>alert('x')</script>") || !strings.Contains(string(bytes), "Recorded prerequisite assessment") {
		t.Fatal("HTML did not safely render the observation")
	}
	if _, err := os.Stat(filepath.Join(f.root, "should-not-exist")); !os.IsNotExist(err) {
		t.Fatal("observation executed its source")
	}
	f.mutate("apply", object{"changes": []any{object{"op": "record.retire", "symbol": "GATE-LOCAL", "reason": "Service requirement no longer applies."}}})
	retired := f.doc("PLAN-EXAMPLE")
	if model.M(model.M(retired.Data["execution"])["prerequisite_observations"])["GATE-LOCAL"] == nil {
		t.Fatal("retirement erased observation history")
	}
	if _, err := f.request("prerequisite", f.mutation("PLAN-EXAMPLE", prerequisiteReport("unknown", "agent_report"))); fault.Code(err) != "UNKNOWN_PREREQUISITE" {
		t.Fatalf("retired prerequisite accepted new result: %v", err)
	}
}

func TestAssistiveScopeCanFinishWithoutReviewPermissionOrTestClaim(t *testing.T) {
	f := newAssistiveFixture(t)
	before := f.doc("PLAN-EXAMPLE").Hash()
	if _, err := f.request("accept-scope", f.mutation("PLAN-EXAMPLE", object{"scope": "CP-01", "reason": "Report completed batch."})); fault.Code(err) != "SCOPE_UNFINISHED" {
		t.Fatalf("pending work marked done: %v", err)
	}
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("failed completion changed state")
	}
	for _, task := range []string{"T-001", "T-002"} {
		f.mutate("task-start", object{"task": task})
	}
	f.mutate("task-block", object{"task": "T-002", "reason": "User asked to pause this task."})
	if _, err := f.request("accept-scope", f.mutation("PLAN-EXAMPLE", object{"scope": "CP-01", "reason": "Report completed batch."})); fault.Code(err) != "SCOPE_UNFINISHED" {
		t.Fatalf("completion cleared an explicit stop: %v", err)
	}
	f.mutate("task-reconcile", object{"task": "T-002", "state": "REVIEW", "reason": "User resumed; implementation finished."})
	request := f.mutation("PLAN-EXAMPLE", object{"scope": "CP-01", "reason": "Implemented the configuration precedence change."})
	f.call("accept-scope", request)
	d := f.doc("PLAN-EXAMPLE")
	for _, task := range []string{"T-001", "T-002"} {
		if state(d, task)["state"] != "DONE" || len(model.A(state(d, task)["evidence_refs"])) != 0 {
			t.Fatal("completion manufactured acceptance or evidence")
		}
	}
	f.call("accept-scope", request)
	if f.doc("PLAN-EXAMPLE").Hash() != d.Hash() {
		t.Fatal("scope completion replay rewrote state")
	}
	if f.call("eligible", object{"artifact_id": d.ID()})["next_task"] != "T-003" {
		t.Fatal("reported scope completion did not permit dependent scheduling")
	}
	if _, err := f.request("verification-status", object{"artifact_id": d.ID()}); err == nil {
		t.Fatal("DONE became a verified acceptance claim")
	}
	f.assertNoAuthorityFiles()
}

func TestAssistiveLegacyReadPreservesBytesAndNewFieldsRequireNewSchema(t *testing.T) {
	f := newAssistiveFixture(t)
	d := f.doc("PLAN-EXAMPLE")
	// Build a historical-format fixture, not a relabelled new observation.
	d.Data["schema_version"] = "0.3.1"
	legacy, err := render.Prepare(d.Data)
	if err != nil {
		t.Fatal(err)
	}
	bytes, err := render.Render(legacy)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
	if err = os.WriteFile(path, bytes, 0600); err != nil {
		t.Fatal(err)
	}
	f.call("eligible", object{"artifact_id": legacy.ID()})
	unchanged, err := os.ReadFile(path)
	if err != nil || string(unchanged) != string(bytes) {
		t.Fatal("read silently migrated an old artifact")
	}
	addScopedPrerequisite(f, "fact")
	f.mutate("prerequisite", prerequisiteReport("satisfied", "tool_result"))
	upgraded := f.doc(legacy.ID())
	if upgraded.Data["schema_version"] != "0.3.2" || upgraded.ID() != legacy.ID() {
		t.Fatal("new fields lack an explicit compatible schema identity")
	}
	upgraded.Data["schema_version"] = "0.3.1"
	if _, err := model.Check(upgraded.Data); fault.Code(err) != "UNSUPPORTED_VERSION" {
		t.Fatalf("new content was accepted under the old schema label: %v", err)
	}
}
