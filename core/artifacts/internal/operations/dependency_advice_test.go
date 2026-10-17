package operations

import (
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent(t *testing.T) {
	for _, target := range []string{"PENDING", "BLOCKED"} {
		t.Run(target, func(t *testing.T) {
			f := newAssistiveFixture(t)
			for _, id := range []string{"T-001", "T-002"} {
				f.mutate("task-start", object{"task": id})
				f.mutate("task-review", object{"task": id})
			}
			report := reportedCommand("pass", true)
			report["task"] = "T-002"
			f.mutate("task-check", report)
			before := f.doc("PLAN-EXAMPLE")
			stale := f.mutation(before.ID(), object{"task": "T-003"})
			reason := "The dependency needs an external condition resolved."
			request := f.mutation(before.ID(), object{"task": "T-001", "state": target, "reason": reason})
			f.call("task-reconcile", request)
			after := f.doc(before.ID())
			if after.NormHash() != before.NormHash() || !equalValue(state(before, "T-002"), state(after, "T-002")) ||
				!equalValue(model.M(before.Data["execution"])["task_check_observations"], model.M(after.Data["execution"])["task_check_observations"]) {
				t.Fatal("reconciliation changed requirements, dependent progress, or check history")
			}
			advice := f.call("eligible", object{"artifact_id": before.ID()})
			third := model.M(model.A(advice["tasks"])[2])
			packet := packetFor(f, "T-003")
			if third["eligible"] != false || !equalValue(third["waiting_on"], model.List("T-001")) ||
				!equalValue(packet["waiting_on"], third["waiting_on"]) {
				t.Errorf("scheduler and task context missed the unresolved ancestor: row=%v packet=%v", third, packet)
			}
			if !strings.Contains(model.S(packet["next_action"]), "unresolved dependencies") {
				t.Errorf("task context did not direct attention to the dependency: %v", packet["next_action"])
			}
			dependencies := model.A(packet["dependencies"])
			if len(dependencies) != 2 || model.M(dependencies[1])["id"] != "T-001" ||
				model.M(dependencies[1])["state"] != target || model.M(dependencies[1])["reason"] != reason {
				t.Errorf("task context omitted the transitive dependency condition: %v", dependencies)
			}
			if f.doc(before.ID()).Hash() != after.Hash() {
				t.Fatal("dependency advice mutated recorded progress")
			}
			f.call("task-reconcile", request)
			if f.doc(before.ID()).Hash() != after.Hash() {
				t.Fatal("replayed reconciliation changed progress")
			}
			if _, err := f.request("task-start", stale); fault.Code(err) != "REVISION_CONFLICT" {
				t.Fatalf("reconciliation lost compare-and-swap protection: %v", err)
			}
			f.mutate("task-reconcile", object{"task": "T-001", "state": "REVIEW", "reason": "The condition is resolved and implementation is complete."})
			ready := packetFor(f, "T-003")
			if f.call("eligible", object{"artifact_id": before.ID()})["next_task"] != "T-003" ||
				len(model.A(ready["waiting_on"])) != 0 {
				t.Fatal("resolved ancestor did not restore scheduling advice")
			}
			if dependencies := model.A(ready["dependencies"]); len(dependencies) != 1 || model.M(dependencies[0])["id"] != "T-002" {
				t.Fatalf("ready task context expanded completed ancestor history: %v", dependencies)
			}
			f.assertNoAuthorityFiles()
		})
	}
}

func TestTaskContextReportsSharedDependencyAncestorsOnce(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": model.List("T-001", "T-002")},
	}}})
	f.mutate("task-block", object{"task": "T-001", "reason": "The upstream input is unavailable."})
	packet := packetFor(f, "T-003")
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	third := model.M(model.A(advice["tasks"])[2])
	if len(model.A(packet["dependencies"])) != 2 || !equalValue(packet["waiting_on"], model.List("T-001", "T-002")) ||
		!equalValue(packet["waiting_on"], third["waiting_on"]) {
		t.Fatalf("shared ancestor was repeated or omitted: row=%v dependencies=%v", third, packet["dependencies"])
	}
}

func TestDependencyInvalidationPreservesIndependentStops(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	reason := "The user denied this task."
	f.mutate("task-block", object{"task": "T-002", "reason": reason})
	stop := state(f.doc("PLAN-EXAMPLE"), "T-002")
	f.mutate("task-reconcile", object{"task": "T-003", "state": "REVIEW", "reason": "Its implementation remains available."})
	f.mutate("task-block", object{"task": "T-001", "reason": "An upstream input is unavailable."})
	after := f.doc("PLAN-EXAMPLE")
	if !equalValue(state(after, "T-002"), stop) {
		t.Errorf("dependency invalidation replaced an independent stop: %v", state(after, "T-002"))
	}
	if state(after, "T-003")["state"] != "STALE" {
		t.Fatal("preserving a stop prevented traversal to its affected dependents")
	}
	f.mutate("task-reconcile", object{"task": "T-001", "state": "REVIEW", "reason": "The upstream input is available again."})
	packet := packetFor(f, "T-002")
	if packet["state"] != "BLOCKED" || packet["reason"] != reason {
		t.Fatalf("upstream recovery cleared the independent user decision: %v", packet)
	}
	f.assertNoAuthorityFiles()
}
