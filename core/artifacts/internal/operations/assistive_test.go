package operations

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// This fixture deliberately creates no approvals, observations, or receipts.
// It exercises public engine operations, not a mock that bypasses their checks.
type assistiveFixture struct {
	t    *testing.T
	root string
	n    int
}

func newAssistiveFixture(t *testing.T) *assistiveFixture {
	t.Helper()
	f := &assistiveFixture{t: t, root: testutil.Root(t)}
	sn := model.M(testutil.Spec()["normative"])
	f.call("create", object{"operation_id": f.next(), "kind": "spec", "artifact_id": "SPEC-EXAMPLE", "slug": "example", "title": sn["title"], "summary": sn["summary"], "normative": sn})
	pn := model.M(testutil.Plan(f.doc("SPEC-EXAMPLE"))["normative"])
	f.call("create", object{"operation_id": f.next(), "kind": "plan", "artifact_id": "PLAN-EXAMPLE", "slug": "example", "title": pn["title"], "summary": pn["summary"], "spec_id": "SPEC-EXAMPLE", "normative": pn})
	return f
}
func (f *assistiveFixture) next() string { f.n++; return fmt.Sprintf("assistive-op-%04d", f.n) }
func (f *assistiveFixture) request(op string, r object) (any, error) {
	r["protocol"] = Protocol
	return Run(f.root, op, r)
}
func (f *assistiveFixture) call(op string, r object) object {
	f.t.Helper()
	out, err := f.request(op, r)
	if err != nil {
		f.t.Fatalf("%s: %v", op, err)
	}
	return model.M(out)
}
func (f *assistiveFixture) doc(id string) *model.Document {
	f.t.Helper()
	fs, err := store.Open(f.root)
	if err != nil {
		f.t.Fatal(err)
	}
	defer fs.Close()
	catalog, err := repository.Scan(fs)
	if err != nil {
		f.t.Fatal(err)
	}
	entry, err := catalog.Resolve(id)
	if err != nil {
		f.t.Fatal(err)
	}
	return entry.Doc
}
func (f *assistiveFixture) mutation(id string, r object) object {
	d := f.doc(id)
	r["artifact_id"], r["operation_id"] = id, f.next()
	r["expected"] = object{"revision": d.Revision(), "model_sha256": d.Hash()}
	return r
}
func (f *assistiveFixture) mutate(op string, r object) object {
	f.t.Helper()
	return f.call(op, f.mutation("PLAN-EXAMPLE", r))
}
func (f *assistiveFixture) assertNoAuthorityFiles() {
	f.t.Helper()
	for _, name := range []string{"receipts", "events", "observations", "authority-sources", "contexts"} {
		entries, err := os.ReadDir(filepath.Join(f.root, ".codearbiter", ".artifacts", name))
		if err != nil && !os.IsNotExist(err) {
			f.t.Fatal(err)
		}
		if len(entries) != 0 {
			f.t.Fatalf("ordinary work created %s: %v", name, entries)
		}
	}
}

func TestAssistiveDraftWorkNeedsNoApprovalOrContextTicket(t *testing.T) {
	f := newAssistiveFixture(t)
	before := f.doc("PLAN-EXAMPLE").NormHash()
	report := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if report["assessment"] != "advisory" || report["next_task"] != "T-001" || report["evidence_assessed"] != false {
		t.Fatalf("draft scheduling did not return honest advice: %v", report)
	}
	if _, exists := report["all_accepted_and_current"]; exists {
		t.Fatal("scheduler returned a verification claim")
	}
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	d := f.doc("PLAN-EXAMPLE")
	if state(d, "T-001")["state"] != "REVIEW" || len(model.A(state(d, "T-001")["evidence_refs"])) != 0 {
		t.Fatal("implementation completion invented review or verification evidence")
	}
	if d.NormHash() != before {
		t.Fatal("progress changed the plan's requirements")
	}
	report = f.call("eligible", object{"artifact_id": d.ID()})
	if report["next_task"] != "T-002" {
		t.Fatalf("recorded implementation did not support scheduling: %v", report)
	}
	f.mutate("task-start", object{"task": "T-002"})
	f.assertNoAuthorityFiles()
	if _, err := f.request("verification-status", object{"artifact_id": d.ID()}); err == nil {
		t.Fatal("unapproved and unverified fixture produced verified acceptance")
	}
}

func TestAssistiveWorkDoesNotSnapshotUnrelatedSource(t *testing.T) {
	f := newAssistiveFixture(t)
	large, err := os.Create(filepath.Join(f.root, "unrelated.bin"))
	if err != nil {
		t.Fatal(err)
	}
	if err = large.Truncate(33 << 20); err != nil {
		large.Close()
		t.Fatal(err)
	}
	if err = large.Close(); err != nil {
		t.Fatal(err)
	}
	// A real snapshot of this fixture must hit the existing per-file bound.
	if _, err = f.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err == nil {
		t.Fatal("fixture did not exercise the source snapshot limit")
	}
	f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	f.assertNoAuthorityFiles()
}

func TestAssistiveSelectionUsesDependenciesNotCheckpointOrder(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("apply", object{"changes": []any{
		object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": empty()}},
		object{"op": "record.update", "symbol": "CP-02", "fields": object{"depends_on": empty()}},
		object{"op": "record.add", "collection": "prerequisites", "record": object{"id": "GATE-LOCAL", "title": "Local service", "requirement": "Check whether the local test service is available.", "source_refs": empty()}},
	}})
	f.mutate("task-block", object{"task": "T-001", "reason": "Explicit stop for the first task only."})
	report := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if report["next_task"] != "T-003" {
		t.Fatalf("unrelated work was hidden behind a checkpoint: %v", report)
	}
	prerequisites := model.A(report["prerequisites"])
	if len(prerequisites) != 1 || model.M(prerequisites[0])["recorded_state"] != "not_satisfied" {
		t.Fatalf("unresolved prerequisite was silently satisfied or omitted: %v", report)
	}
	if model.M(prerequisites[0])["scope"] != "unspecified" {
		t.Fatal("legacy prerequisite scope was invented")
	}
}

func TestAssistiveResumePreservesStopsAndRejectsDuplicateStart(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-start", object{"task": "T-001"})
	if _, err := f.request("task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})); fault.Code(err) != "NOT_PENDING" {
		t.Fatalf("active task was redispatched: %v", err)
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "User stopped this task."})
	if _, err := f.request("task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})); fault.Code(err) != "NOT_PENDING" {
		t.Fatalf("start silently cleared a stop: %v", err)
	}
	f.mutate("task-reconcile", object{"task": "T-001", "state": "PENDING", "reason": "User resumed work; checked that no worker remains active."})
	f.mutate("task-start", object{"task": "T-001"})
	f.assertNoAuthorityFiles()
}

func TestAssistivePlanMaintenancePreservesProgressAndCAS(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	stale := f.mutation("PLAN-EXAMPLE", object{"task": "T-002"})
	f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-002", "fields": object{"steps": model.List("Use a smaller implementation step; outcome is unchanged.")}}}})
	if _, err := f.request("task-start", stale); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale writer was accepted: %v", err)
	}
	if state(f.doc("PLAN-EXAMPLE"), "T-001")["state"] != "REVIEW" {
		t.Fatal("method edit reset unrelated progress")
	}
	f.mutate("plan-bind", object{"spec_id": "SPEC-EXAMPLE"})
	if state(f.doc("PLAN-EXAMPLE"), "T-001")["state"] != "REVIEW" {
		t.Fatal("binding reset progress")
	}
	request := f.mutation("PLAN-EXAMPLE", object{"task": "T-002"})
	f.call("task-start", request)
	after := f.doc("PLAN-EXAMPLE").Hash()
	f.call("task-start", request)
	if f.doc("PLAN-EXAMPLE").Hash() != after {
		t.Fatal("replay repeated a successful mutation")
	}
	f.assertNoAuthorityFiles()
}

func TestAssistiveReportedReviewCannotMasqueradeAsReceiptedReview(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-start", object{"task": "T-001"})
	before := f.doc("PLAN-EXAMPLE").Hash()
	for _, fields := range []object{
		{"task": "T-001", "verification_receipt": "missing"},
		{"task": "T-001", "review_receipt": "missing"},
		{"task": "T-001", "completion_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
	} {
		if _, err := f.request("task-review", f.mutation("PLAN-EXAMPLE", fields)); err == nil {
			t.Fatal("partial asserted evidence was accepted")
		}
	}
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("rejected review changed progress")
	}
}

func TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress(t *testing.T) {
	f := newAssistiveFixture(t)
	before := f.doc("PLAN-EXAMPLE").NormHash()
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{
		object{"op": "header.update", "fields": object{"summary": "Changed after the last context delivery."}},
	}}))
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if advice["binding_current"] != false || advice["evidence_assessed"] != false {
		t.Fatalf("stale binding was hidden: %v", advice)
	}
	f.mutate("task-start", object{"task": "T-001", "context_ticket": "historical-ticket-is-not-permission"})
	after := f.doc("PLAN-EXAMPLE")
	if after.NormHash() != before || state(after, "T-001")["state"] != "IN_PROGRESS" {
		t.Fatal("progress rewrote the requirement binding or failed to record the start")
	}
	f.assertNoAuthorityFiles()
}
