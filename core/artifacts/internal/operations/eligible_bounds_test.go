package operations

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestEligibleBoundedPrerequisites(t *testing.T) {
	f := newAssistiveFixture(t)
	changes := []any{}
	for i := 0; i < 16; i++ {
		changes = append(changes, object{"op": "record.add", "collection": "prerequisites", "record": object{
			"id": fmt.Sprintf("GATE-%02d", i), "title": "Local test service", "kind": "fact",
			"requirement": strings.Repeat("r", 1024), "task_refs": model.List("T-001"), "source_refs": empty(),
		}})
	}
	f.mutate("apply", object{"changes": changes})
	for i := 0; i < 16; i++ {
		f.mutate("prerequisite", object{"prerequisite": fmt.Sprintf("GATE-%02d", i), "observation": object{
			"outcome": "satisfied", "origin": "tool_result", "summary": strings.Repeat("s", 2048), "source": strings.Repeat("c", 1024),
		}})
	}
	before := f.doc("PLAN-EXAMPLE").Hash()
	result := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	encoded, err := json.Marshal(object{"protocol": Protocol, "operation": "eligible", "ok": true, "result": result})
	if err != nil {
		t.Fatal(err)
	}
	if len(encoded)+1 > 65536 {
		t.Fatalf("scheduling response exceeds CLI limit: %d bytes", len(encoded)+1)
	}
	if result["next_task"] != "T-001" || result["evidence_assessed"] != false || result["context_complete"] != false {
		t.Fatalf("bounded advice lost scheduling or omission disclosure: %v", result)
	}
	guidance := model.S(result["detail_read"])
	if !strings.Contains(guidance, "outline") || !strings.Contains(guidance, "task-context") || !strings.Contains(guidance, "RECORD_TOO_LARGE") {
		t.Fatal("detail guidance omitted supported operations or indivisible record limits")
	}
	if len(model.A(result["prerequisites"])) != 16 || model.I(result["prerequisites_omitted"]) != 0 {
		t.Fatal("compact prerequisite states were omitted unnecessarily")
	}
	for _, value := range model.A(result["prerequisites"]) {
		row := model.M(value)
		if row["outcome"] != "satisfied" || row["details_omitted"] != true {
			t.Fatalf("prerequisite status or detail disclosure lost: %v", row)
		}
	}
	page := f.call("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "GATE-00", "mode": "exact"})
	assessment := model.M(page["prerequisite_assessment"])
	if assessment["requirement"] != strings.Repeat("r", 1024) || model.M(assessment["observation"])["summary"] != strings.Repeat("s", 2048) {
		t.Fatal("exact read did not retain omitted details")
	}
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("scheduling changed the artifact")
	}
	f.assertNoAuthorityFiles()
}

func TestEligibleDisclosesOversizedTaskRows(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-reconcile", object{"task": "T-001", "state": "BLOCKED", "reason": strings.Repeat("<", 20000)})
	result := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	encoded, err := json.Marshal(object{"protocol": Protocol, "operation": "eligible", "ok": true, "result": result})
	if err != nil {
		t.Fatal(err)
	}
	if len(encoded)+1 > 65536 || model.I(result["tasks_omitted"]) != 1 || model.I(result["tasks_total"]) != 3 {
		t.Fatalf("oversized row was not bounded and disclosed: bytes=%d omitted=%v total=%v", len(encoded)+1, result["tasks_omitted"], result["tasks_total"])
	}
	if result["next_task"] != "" || len(model.A(result["tasks"])) != 2 {
		t.Fatal("omitting a row changed dependency advice")
	}
}
