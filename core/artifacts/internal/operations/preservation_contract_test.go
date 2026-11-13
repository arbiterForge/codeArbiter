package operations

// NT-01 preservation contracts. Every assertion in this file pins behavior the
// state-contract program must PRESERVE. Assertions that encode semantics the
// program deliberately changes live in intentional_change_test.go instead, so a
// later task can change them only with its recorded decision.
//
// Transition rows (docs/state-contracts-major/contracts/transition-coverage.json)
// exercised here: N01:06, N02:05, N02:06, N02:07, N02:08, N03:01, N03:02,
// N09:01, N09:02, N09:03, N09:04, N09:05, N10:01, N10:04, N10:05, N11:01,
// N11:02, N13:01.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

const ordinaryReviewReason = "Implementation reported complete; verification and review are not assessed by this progress update."

// Acceptance sequence "Baseline ordinary work": a draft plan with no approval or
// context ticket records start, reported-ready and failed/unknown checks; the
// reads keep the reported failure and the unassessed proof explicit.
func TestNT01BaselineOrdinaryWorkKeepsReportedFailuresExplicit(t *testing.T) {
	f := newAssistiveFixture(t)
	if advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"}); advice["next_task"] != "T-001" ||
		advice["evidence_assessed"] != false || advice["assessment"] != "advisory" {
		t.Fatalf("draft scheduling was not honest advice: %v", advice)
	}
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	reportFor(f, "fail", true)
	reportFor(f, "unknown", true)

	d := f.doc("PLAN-EXAMPLE")
	s := state(d, "T-001")
	if s["state"] != "REVIEW" || s["reason"] != ordinaryReviewReason {
		t.Fatalf("ordinary reported-ready progress changed meaning: %v", s)
	}
	if len(model.A(s["evidence_refs"])) != 0 || s["completion_review_receipt"] != nil {
		t.Fatalf("ordinary progress or a reported check invented evidence: %v", s)
	}
	history := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-001"])
	if len(history) != 2 || model.M(history[0])["outcome"] != "fail" || model.M(history[1])["outcome"] != "unknown" {
		t.Fatalf("reported outcomes were not retained in order: %v", history)
	}

	packet := packetFor(f, "T-001")
	if packet["state"] != "REVIEW" || packet["evidence_assessed"] != false || packet["checks_are_verified"] != false ||
		packet["assessment"] != "advisory" {
		t.Fatalf("task context presented reported progress as assessed proof: %v", packet)
	}
	checks := model.A(packet["reported_checks"])
	if len(checks) != 2 {
		t.Fatalf("task context hid a reported check: %v", checks)
	}
	for i, want := range []string{"fail", "unknown"} {
		check := model.M(checks[i])
		if check["reported_outcome"] != want || check["evidence_assessed"] != false ||
			check["named_tests_verified"] != false || check["provenance"] != "caller_reported" {
			t.Fatalf("reported %s check was presented as verification: %v", want, check)
		}
	}
	// The earlier reported failure stays visible: an unknown result after it does
	// not erase the failure the caller actually observed.
	summary := model.M(packet["check_summary"])
	if summary["evidence_assessed"] != false || summary["has_conflicting_check_reports"] != true ||
		!strings.Contains(model.S(packet["next_action"]), "reported failing") {
		t.Fatalf("a later unknown report hid the earlier applicable failure: summary=%v next=%v", summary, packet["next_action"])
	}

	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	rows := model.A(advice["tasks"])
	if advice["next_task"] != "T-002" || model.M(rows[0])["state"] != "REVIEW" ||
		model.M(rows[0])["evidence_assessed"] != false || advice["evidence_assessed"] != false {
		t.Fatalf("ordinary progress did not keep scheduling available or claimed evidence: %v", advice)
	}
	if _, exists := advice["all_accepted_and_current"]; exists {
		t.Fatal("scheduling advice returned a verification claim")
	}
	if _, err := f.request("verification-status", object{"artifact_id": "PLAN-EXAMPLE"}); err == nil {
		t.Fatal("ordinary progress plus reports produced verified acceptance")
	}
	f.assertNoAuthorityFiles()
}

// Ordinary and receipted REVIEW share a label but not a basis; DONE and
// ACCEPTED differ by the evidence each one consumed. These are the distinct
// bases a later projection must keep separate (N-F04, NT-09).
func TestNT01TaskLabelBasesAreDistinct(t *testing.T) {
	t.Run("ordinary", func(t *testing.T) {
		f := newAssistiveFixture(t)
		if s := state(f.doc("PLAN-EXAMPLE"), "T-001"); s["state"] != "PENDING" || s["reason"] != nil {
			t.Fatalf("new task was not PENDING: %v", s)
		}
		f.mutate("task-start", object{"task": "T-001"})
		if s := state(f.doc("PLAN-EXAMPLE"), "T-001"); s["state"] != "IN_PROGRESS" {
			t.Fatalf("start did not record IN_PROGRESS: %v", s)
		}
		f.mutate("task-review", object{"task": "T-001"})
		f.mutate("task-start", object{"task": "T-002"})
		f.mutate("task-review", object{"task": "T-002"})
		ordinary := state(f.doc("PLAN-EXAMPLE"), "T-001")
		if ordinary["state"] != "REVIEW" || ordinary["reason"] != ordinaryReviewReason || len(model.A(ordinary["evidence_refs"])) != 0 {
			t.Fatalf("ordinary REVIEW basis changed: %v", ordinary)
		}
		f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Batch implemented."})
		d := f.doc("PLAN-EXAMPLE")
		for _, id := range []string{"T-001", "T-002"} {
			s := state(d, id)
			if s["state"] != "DONE" || len(model.A(s["evidence_refs"])) != 0 ||
				!strings.HasSuffix(model.S(s["reason"]), "Implementation completion only; verification and review are not assessed.") {
				t.Fatalf("receipt-free scope completion claimed more than implementation: %v", s)
			}
		}
		f.mutate("task-block", object{"task": "T-003", "reason": "User stopped this task."})
		if s := state(f.doc("PLAN-EXAMPLE"), "T-003"); s["state"] != "BLOCKED" || s["reason"] != "User stopped this task." {
			t.Fatalf("explicit stop was not recorded with its reason: %v", s)
		}
		// Receipt-free reconcile writes the requested label and reason only.
		f.mutate("task-reconcile", object{"task": "T-003", "state": "PENDING", "reason": "User resumed this task."})
		if s := state(f.doc("PLAN-EXAMPLE"), "T-003"); s["state"] != "PENDING" || s["reason"] != "User resumed this task." {
			t.Fatalf("receipt-free reconcile changed more than progress: %v", s)
		}
		f.assertNoAuthorityFiles()
	})
	t.Run("receipted", func(t *testing.T) {
		h, _ := completionHarness(t)
		material := filepath.Join(t.TempDir(), "matrix.txt")
		if err := os.WriteFile(material, []byte("Task completion evidence matrix\n"), 0600); err != nil {
			t.Fatal(err)
		}
		receipts := []string{}
		for _, id := range []string{"T-001", "T-002"} {
			verification, _ := completeTask(t, h, id, h.root, material, false)
			receipts = append(receipts, verification)
		}
		receipted := state(h.doc("PLAN-EXAMPLE"), "T-001")
		refs := model.Strings(receipted["evidence_refs"])
		if receipted["state"] != "REVIEW" || receipted["reason"] != nil || len(refs) != 2 ||
			receipted["completion_review_receipt"] == nil {
			t.Fatalf("receipted REVIEW basis changed: %v", receipted)
		}
		for _, ref := range refs {
			if !strings.HasPrefix(ref, ".codearbiter/.artifacts/receipts/") {
				t.Fatalf("receipted REVIEW does not reference retained receipts: %v", refs)
			}
		}
		acceptScope(t, h, "CP-01", material, receipts)
		d := h.doc("PLAN-EXAMPLE")
		for _, id := range []string{"T-001", "T-002"} {
			s := state(d, id)
			if s["state"] != "ACCEPTED" || s["reason"] != nil || len(model.Strings(s["evidence_refs"])) != 3 {
				t.Fatalf("strict acceptance did not consume and retain its quality receipt: %v", s)
			}
		}
		// A receipted ACCEPTED scope is not downgraded by a later ordinary
		// completion label on that scope.
		before := state(h.doc("PLAN-EXAMPLE"), "T-001")
		h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "reason": "Ordinary completion note."})
		if !equalValue(state(h.doc("PLAN-EXAMPLE"), "T-001"), before) {
			t.Fatal("ordinary completion overwrote strict acceptance")
		}
	})
}
