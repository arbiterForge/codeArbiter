package operations

import (
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestWorkViewSeparatesProgressChecksDeliveryAndSync(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		result, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return result.(object)
	}
	call("init-store", object{})
	call("create", object{"operation_id": "view-spec-001", "kind": "spec", "artifact_id": "SPEC-VIEW", "slug": "view", "title": "Specification", "summary": "Outcome <first>"})
	call("create", object{"operation_id": "view-plan-001", "kind": "plan", "artifact_id": "PLAN-VIEW", "slug": "view", "title": "Implementation plan", "summary": "Implement <safely>", "spec_id": "SPEC-VIEW"})
	created := call("work-create", object{"operation_id": "view-create-001", "title": "Deliver <outcome>", "intent": "Make the local journey useful", "work_type": "feature", "spec_id": "SPEC-VIEW", "plan_id": "PLAN-VIEW"})
	id := created["work_id"].(string)
	completed := call("work-update", object{"operation_id": "view-complete-001", "work_id": id, "action": "complete", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	if completed["check_status"] != "unknown" {
		t.Fatal("fixture changed the unknown check")
	}
	view := call("work-view", object{"work_id": id})
	html := view["html"].(string)
	for _, want := range []string{"Deliver &lt;outcome&gt;", "Outcome &lt;first&gt;", "Implement &lt;safely&gt;", "../../specs/view.html", "../../plans/view.html", "Current situation", "Recorded change", "Remaining obstacle", "Next action", "Local progress", "Checks", "Delivery", "Tracker sync", "Unknown"} {
		if !strings.Contains(html, want) {
			t.Fatalf("work view omitted %q", want)
		}
	}
	if strings.Contains(html, "Deliver <outcome>") || strings.Contains(html, "<script id=\"ca-artifact-model\"") {
		t.Fatal("derived work view emitted unescaped data or a canonical model")
	}
	if view["canonical"] != false || view["work_id"] != id {
		t.Fatalf("derived view identity is wrong: %v", view)
	}
	if view["view_path"] != ".codearbiter/views/work/"+id+".html" {
		t.Fatalf("derived view location is wrong: %v", view["view_path"])
	}
	for _, href := range []string{"../../specs/view.html", "../../plans/view.html"} {
		resolved := path.Clean(path.Join(path.Dir(view["view_path"].(string)), href))
		if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(resolved))); err != nil {
			t.Fatalf("derived link %q does not reach its canonical attachment: %v", href, err)
		}
	}
}

func TestGeneratedWorkViewIsNotCanonical(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	created, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "view-plain-001", "title": "Plain work", "intent": "Remain local", "work_type": "chore"})
	if err != nil {
		t.Fatal(err)
	}
	id := created.(object)["work_id"].(string)
	value, err := Run(root, "work-view", object{"protocol": Protocol, "work_id": id})
	if err != nil {
		t.Fatal(err)
	}
	html := []byte(value.(object)["html"].(string))
	if _, err := render.Parse(html); err == nil || !strings.Contains(err.Error(), "INVALID_CONTAINER") {
		t.Fatalf("generated overview was accepted as a canonical artifact: %v", err)
	}
	viewPath := filepath.Join(root, filepath.FromSlash(value.(object)["view_path"].(string)))
	if err := os.MkdirAll(filepath.Dir(viewPath), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(viewPath, html, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "index", object{"protocol": Protocol}); err != nil {
		t.Fatalf("derived view interfered with canonical discovery: %v", err)
	}
}

func TestWorkViewSelectsActualPlanTaskWithoutPromotingChecks(t *testing.T) {
	f := newAssistiveFixture(t)
	created := f.call("work-create", object{"operation_id": "plan-work-view-001", "title": "Carry the plan",
		"intent": "Show the selected next task", "work_type": "feature",
		"spec_id": "SPEC-EXAMPLE", "plan_id": "PLAN-EXAMPLE"})
	context := f.call("work-context", object{"work_id": created["work_id"]})
	task := model.M(context["plan_task"])
	if task["id"] != "T-001" || task["title"] != "Implement and verify stage 1" || task["binding_current"] != true {
		t.Fatalf("selected work context omitted the current plan task: %v", task)
	}
	html := model.S(f.call("work-view", object{"work_id": created["work_id"]})["html"])
	for _, want := range []string{"T-001", "Implement and verify stage 1", "Source binding current", "No check report recorded"} {
		if !strings.Contains(html, want) {
			t.Fatalf("plan work view omitted %q", want)
		}
	}
	if strings.Contains(html, "Checks passed") {
		t.Fatal("derived plan task promoted an unassessed check")
	}
}

func TestWorkViewKeepsUnresolvedPlanFailureAfterUnrelatedPasses(t *testing.T) {
	f := newAssistiveFixture(t)
	created := f.call("work-create", object{"operation_id": "plan-failure-view-001", "title": "Fix selected work",
		"intent": "Keep unresolved verification visible", "work_type": "fix",
		"spec_id": "SPEC-EXAMPLE", "plan_id": "PLAN-EXAMPLE"})
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "fail", true)
	for i := 0; i < 3; i++ {
		r := reportedCommand("pass", false)
		model.M(r["check"])["argv"] = model.List("python", "-c", "print('unrelated')")
		f.mutate("task-check", r)
	}
	context := f.call("work-context", object{"work_id": created["work_id"]})
	selected := model.M(context["plan_task"])
	if model.M(selected["check_summary"])["has_conflicting_check_reports"] != true {
		t.Fatalf("work context hid selected task's unresolved failure: %v", selected)
	}
	html := model.S(f.call("work-view", object{"work_id": created["work_id"]})["html"])
	if !strings.Contains(html, "Unresolved reported failure") || strings.Contains(html, "Checks passed") {
		t.Fatalf("derived view lost verification obstacle: %s", html)
	}
}

func TestWorkContextShowsBlockedPlanTaskAndUnresolvedReportWithoutChangingIt(t *testing.T) {
	f := newAssistiveFixture(t)
	created := f.call("work-create", object{"operation_id": "plan-blocked-view-001", "title": "Stopped work",
		"intent": "Keep the owner stop visible", "work_type": "fix",
		"spec_id": "SPEC-EXAMPLE", "plan_id": "PLAN-EXAMPLE"})
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "fail", true)
	f.mutate("task-block", object{"task": "T-001", "reason": "Owner paused this work."})
	before := f.doc("PLAN-EXAMPLE")
	context := f.call("work-context", object{"work_id": created["work_id"]})
	selected := model.M(context["plan_task"])
	if selected["id"] != "T-001" || selected["state"] != "BLOCKED" ||
		model.M(selected["check_summary"])["has_conflicting_check_reports"] != true ||
		!strings.Contains(model.S(selected["next_action"]), "do not clear") {
		t.Fatalf("work context hid blocked task, its stop, or its reported failure: %v", selected)
	}
	html := model.S(f.call("work-view", object{"work_id": created["work_id"]})["html"])
	start := strings.Index(html, "<dt>Next action</dt><dd>")
	if start < 0 {
		t.Fatal("work view omitted snapshot next action")
	}
	next := strings.SplitN(html[start:], "</dd>", 2)[0]
	if !strings.Contains(next, "do not clear") || !strings.Contains(html, "Unresolved reported failure") {
		t.Fatalf("work view displaced the stop or hid the report: next=%q", next)
	}
	after := f.doc("PLAN-EXAMPLE")
	if after.Hash() != before.Hash() || model.S(state(after, "T-001")["state"]) != "BLOCKED" {
		t.Fatal("work-context or work-view changed the blocked plan task")
	}
}

func TestWorkViewRetainsObservedPullSeparatelyFromChecksAndIssue(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		result, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return result.(object)
	}
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "delivery-work-create-001", "title": "Finish the fix", "intent": "Keep delivery distinct", "work_type": "fix"})
	completed := call("work-update", object{"operation_id": "delivery-work-complete-001", "work_id": work["work_id"], "action": "complete", "expected": object{"revision": work["revision"], "model_sha256": work["model_sha256"]}})
	observed := call("work-update", object{"operation_id": "delivery-work-observe-001", "work_id": work["work_id"], "action": "observe-delivery", "expected": object{"revision": completed["revision"], "model_sha256": completed["model_sha256"]},
		"repository": "owner/repo", "pull_number": int64(12), "pull_state": "open", "observed_at": "2026-10-31T12:00:00Z"})
	if observed["check_status"] != "unknown" || observed["state"] != "complete" {
		t.Fatalf("delivery observation changed local progress or checks: %v", observed)
	}
	view := call("work-view", object{"work_id": work["work_id"]})
	html := view["html"].(string)
	for _, required := range []string{"PR open", "Observed 2026-10-31T12:00:00Z", `<a href="https://github.com/owner/repo/pull/12">`, "Check evidence is unknown", "Tracker sync", "Unconfigured"} {
		if !strings.Contains(html, required) {
			t.Fatalf("selected work view omitted %q", required)
		}
	}
	if strings.Contains(html, "The PR changed a file with this Work ID") {
		t.Fatal("native delivery observation claimed PR diff verification it did not perform")
	}
	if strings.Contains(html, "Merged") || strings.Contains(html, "Checks</h2><p class=\"state\">Passed") {
		t.Fatal("open PR observation implied a merge or passing checks")
	}
	if _, err := Run(root, "work-update", object{"protocol": Protocol, "operation_id": "delivery-work-observe-invalid", "work_id": work["work_id"], "action": "observe-delivery", "expected": object{"revision": observed["revision"], "model_sha256": observed["model_sha256"]},
		"repository": "owner/other", "pull_number": int64(0), "pull_state": "merged", "observed_at": "2026-10-31T12:00:00Z"}); err == nil {
		t.Fatal("invalid PR identity was recorded")
	}
	reopened := call("work-update", object{"operation_id": "delivery-work-reopen-001", "work_id": work["work_id"], "action": "reopen", "expected": object{"revision": observed["revision"], "model_sha256": observed["model_sha256"]}})
	if reopened["delivery_observation"] == nil || reopened["check_status"] != "unknown" {
		t.Fatal("local lifecycle erased the independent delivery observation or check state")
	}
}
