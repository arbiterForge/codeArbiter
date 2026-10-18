//go:build linux

package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestVerificationStatusLaterCheckFailure(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", true))
	h.approvePair()
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		h.start(id)
		h.review(id)
		if id == "T-002" {
			h.accept("CP-01")
		}
		if id == "T-003" {
			h.accept("CP-02")
		}
	}
	before := h.doc("PLAN-EXAMPLE")
	input := h.input()
	refs, _ := canonical.Hash(state(before, "T-001"))
	if h.run("verification-status", object{"artifact_id": before.ID()})["all_accepted_and_current"] != true {
		t.Fatal("later attested success did not supersede the earlier failed report")
	}
	h.mut("task-check", before.ID(), reportedCommand("fail", true))
	result := h.run("verification-status", object{"artifact_id": before.ID()})
	row := model.M(model.A(result["tasks"])[0])
	if result["all_accepted_and_current"] != false || row["current_evidence"] != true || row["has_conflicting_check_reports"] != true {
		t.Fatalf("later failed check hidden by historical acceptance: %v", result)
	}
	conflicts := model.A(row["conflicting_check_reports"])
	if len(conflicts) != 1 || model.M(conflicts[0])["provenance"] != "caller_reported" || model.M(conflicts[0])["worktree_freshness"] != "scoped_unchanged" {
		t.Fatalf("conflict lacks scope and provenance: %v", row)
	}
	for _, unrelated := range []object{reportedCommand("pass", false), reportedCommand("skip", true)} {
		h.mut("task-check", before.ID(), unrelated)
		if h.run("verification-status", object{"artifact_id": before.ID()})["all_accepted_and_current"] != false {
			t.Fatal("unrelated pass or skipped check erased the failure")
		}
	}
	h.mut("task-check", before.ID(), reportedCommand("pass", true))
	result = h.run("verification-status", object{"artifact_id": before.ID()})
	if result["all_accepted_and_current"] != true || model.M(model.A(result["tasks"])[0])["has_conflicting_check_reports"] != false {
		t.Fatalf("reported recovery required recertification: %v", result)
	}
	after := h.doc(before.ID())
	gotRefs, _ := canonical.Hash(state(after, "T-001"))
	if after.NormHash() != before.NormHash() || h.input() != input || gotRefs != refs {
		t.Fatal("reporting changed progress, source identity or retained receipts")
	}
	scopedWrite(t, h.root, "src/stage1.go", "package changed\n")
	h.mut("task-check", before.ID(), reportedCommand("fail", true))
	result = h.run("verification-status", object{"artifact_id": before.ID()})
	row = model.M(model.A(result["tasks"])[0])
	if row["current_evidence"] != false || row["has_conflicting_check_reports"] != true || result["all_accepted_and_current"] != false {
		t.Fatalf("stale verification superseded a current failure: %v", result)
	}
}

func TestVerificationStatusFailureAfterCapturePrecedesReceiptAttachment(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
	h.approvePair()
	h.start("T-001")
	verification, review := h.taskReceipts("T-001")
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", true))
	h.mut("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": review})
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	h.start("T-003")
	h.review("T-003")
	h.accept("CP-02")
	result := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
	row := model.M(model.A(result["tasks"])[0])
	if result["all_accepted_and_current"] != false || row["current_evidence"] != true || row["has_conflicting_check_reports"] != true {
		t.Fatalf("attaching older evidence erased a failure after its capture: %v", result)
	}
}

func TestVerificationStatusMatchingUnindexedFailure(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
	h.approvePair()
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		h.start(id)
		h.review(id)
		if id == "T-002" {
			h.accept("CP-01")
		}
		if id == "T-003" {
			h.accept("CP-02")
		}
	}
	unrelated := reportedCommand("fail", false)
	model.M(unrelated["check"])["argv"] = model.List("go", "test", "./unrelated")
	h.mut("task-check", "PLAN-EXAMPLE", unrelated)
	if h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})["all_accepted_and_current"] != true {
		t.Fatal("unrelated ad-hoc failure contradicted declared verification")
	}
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", false))
	result := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
	row := model.M(model.A(result["tasks"])[0])
	if result["all_accepted_and_current"] != false || row["current_evidence"] != true || row["has_conflicting_check_reports"] != true {
		t.Fatalf("matching unindexed failure hidden by acceptance: %v", result)
	}
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("pass", false))
	if h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})["all_accepted_and_current"] != false {
		t.Fatal("unindexed pass acquired declared-success semantics")
	}
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("pass", true))
	if h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})["all_accepted_and_current"] != true {
		t.Fatal("declared recovery did not resolve the matching failure")
	}
}
