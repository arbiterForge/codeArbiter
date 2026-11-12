package operations

// NT-01 intentional-change pins. These tests encode CURRENT behavior that the
// state-contract program deliberately changes. Each names the task and the
// recorded decision that owns the change; change an assertion here only in that
// task, together with its replacement test. Preservation contracts live in
// preservation_contract_test.go and must not move here to make a change pass.
//
// Transition rows: N11:03 (STALE propagation), N09:04, N10:02.

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// INTENTIONAL CHANGE: NT-09 under D-PROGRESS = B (progress.json later_decisions).
// Today task-block overwrites every transitive non-PENDING/non-BLOCKED
// dependent's recorded progress with STALE and a "Dependency invalidated" reason.
// Under option B recorded progress is never overwritten by dependency
// invalidation; dependency readiness is derived. NT-09 replaces this test.
func TestNT09IntentionalChangeTaskBlockOverwritesDependentProgressWithStale(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	d := f.doc("PLAN-EXAMPLE")
	for _, id := range []string{"T-002", "T-003"} {
		s := state(d, id)
		if s["state"] != "STALE" || s["reason"] != "Dependency invalidated: Upstream input unavailable." {
			t.Fatalf("current propagation changed outside NT-09: %s %v", id, s)
		}
	}
	// The prior REVIEW label of T-002/T-003 is not recoverable from the stored
	// task state: only the transaction before-image retains it. This is the
	// legacy ambiguity NT-09 must display as unresolved, not guess.
	if state(d, "T-001")["state"] != "BLOCKED" {
		t.Fatal("blocked task lost its stop")
	}
	f.assertNoAuthorityFiles()
}

// INTENTIONAL CHANGE: NT-09 under D-PROGRESS = B. A STALE dependent is not
// selectable and is reported NOT_PENDING by scheduling advice, even though its
// implementation was reported complete before the upstream stop.
func TestNT09IntentionalChangeStaleDependentIsNotPendingInAdvice(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	second := model.M(model.A(advice["tasks"])[1])
	if second["state"] != "STALE" || second["diagnostic"] != "NOT_PENDING" || second["eligible"] != false {
		t.Fatalf("current STALE advice changed outside NT-09: %v", second)
	}
}
