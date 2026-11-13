package operations

// NT-09 accepted intentional-change contracts. D-PROGRESS=B replaces the NT-01
// baseline's destructive STALE propagation with independent recorded progress
// and derived readiness. Preservation contracts remain in preservation_contract_test.go.
//
// Transition rows: N11:03 (STALE propagation), N09:04, N10:02.

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// INTENTIONAL CHANGE: NT-09 under D-PROGRESS = B (progress.json later_decisions).
// Recorded progress is never overwritten by dependency invalidation;
// dependency readiness is derived.
func TestNT09TaskBlockPreservesDependentRecordedProgress(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	d := f.doc("PLAN-EXAMPLE")
	if d.Data["schema_version"] != model.ProgressVersion {
		t.Fatal("dependency semantics changed without the new schema epoch")
	}
	for _, id := range []string{"T-002", "T-003"} {
		s := state(d, id)
		if s["state"] != "REVIEW" || s["reason"] != "Implementation reported complete; verification and review are not assessed by this progress update." {
			t.Fatalf("dependency invalidation overwrote recorded progress: %s %v", id, s)
		}
	}
	// The explicit stop changes only its selected task. Dependent REVIEW labels
	// and their original reasons remain directly available.
	if state(d, "T-001")["state"] != "BLOCKED" {
		t.Fatal("blocked task lost its stop")
	}
	f.assertNoAuthorityFiles()
}

// Preserved completed work is not redispatched. Its blocked prerequisite is
// still visible independently of the retained REVIEW label.
func TestNT09PreservedProgressKeepsDependencyReadinessIndependent(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	second := model.M(model.A(advice["tasks"])[1])
	if second["state"] != "REVIEW" || second["diagnostic"] != "NOT_PENDING" || second["eligible"] != false || !equalValue(second["waiting_on"], model.List("T-001")) {
		t.Fatalf("recorded progress and dependency readiness were collapsed: %v", second)
	}
}

func TestNT09LegacyStaleIsUnresolvedAndRetainsRawReason(t *testing.T) {
	f := newAssistiveFixture(t)
	// A historical STALE label has no trustworthy prior progress in the live
	// state. Reconciliation may record what is known without inventing it.
	d := f.doc("PLAN-EXAMPLE")
	state(d, "T-001")["state"] = "STALE"
	state(d, "T-001")["reason"] = "Legacy dependency invalidation."
	d, err := render.Prepare(d.Data)
	if err != nil {
		t.Fatal(err)
	}
	b, err := render.Render(d)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"), b, 0600); err != nil {
		t.Fatal(err)
	}
	p := packetFor(f, "T-001")
	progress := model.M(p["progress"])
	if progress["recorded_state"] != "STALE" || progress["state"] != nil || progress["basis"] != "legacy_unresolved" || progress["recorded_reason"] != "Legacy dependency invalidation." {
		t.Fatalf("legacy progress was guessed or lost: %v", progress)
	}
	if p["state"] != "STALE" || p["checks_are_verified"] != false {
		t.Fatalf("legacy compatibility output or honest proof status lost: %v", p)
	}
	f.assertNoAuthorityFiles()
}

func TestNT09OrdinaryReviewAndDoneDoNotClaimIndependentProof(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	progress := model.M(packetFor(f, "T-001")["progress"])
	if progress["state"] != "REVIEW" || progress["basis"] != "caller_reported" || progress["evidence_assessed"] != false {
		t.Fatalf("ordinary review gained a proof claim: %v", progress)
	}
	f.mutate("task-start", object{"task": "T-002"})
	f.mutate("task-review", object{"task": "T-002"})
	f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Implementation complete; checks remain pending."})
	progress = model.M(packetFor(f, "T-001")["progress"])
	if progress["state"] != "DONE" || progress["basis"] != "caller_reported" || progress["evidence_assessed"] != false {
		t.Fatalf("DONE gained independent proof: %v", progress)
	}
}

func TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel(t *testing.T) {
	for _, label := range []string{"PENDING", "IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED", "BLOCKED", "STALE"} {
		t.Run(label, func(t *testing.T) {
			f := newAssistiveFixture(t)
			d := f.doc("PLAN-EXAMPLE")
			s := state(d, "T-002")
			s["state"], s["reason"] = label, "Retained original progress reason."
			if label == "DONE" {
				d.Data["schema_version"] = model.SchemaVersion
			}
			d, err := render.Prepare(d.Data)
			if err != nil {
				t.Fatal(err)
			}
			before := state(d, "T-002")
			b, err := render.Render(d)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"), b, 0600); err != nil {
				t.Fatal(err)
			}
			f.mutate("task-block", object{"task": "T-001", "reason": "Upstream stopped."})
			after := f.doc("PLAN-EXAMPLE")
			if !equalValue(before, state(after, "T-002")) {
				t.Fatal("dependency stop overwrote recorded history")
			}
			packet := packetFor(f, "T-002")
			if !equalValue(packet["waiting_on"], model.List("T-001")) || packet["checks_are_verified"] != false {
				t.Fatalf("dependency or proof axis collapsed: %v", packet)
			}
			f.mutate("task-reconcile", object{"task": "T-001", "state": "REVIEW", "reason": "Upstream available."})
			if !equalValue(before, state(f.doc("PLAN-EXAMPLE"), "T-002")) {
				t.Fatal("upstream recovery replaced dependent history")
			}
		})
	}
}
