// Package testutil contains synthetic fixture contracts, never production approvals.
package testutil

import (
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"testing"
)

type M = map[string]any

func Arr(v ...any) []any {
	if v == nil {
		return []any{}
	}
	return v
}
func Base(kind, id string) M {
	comp := "../plans/example.html"
	if kind == "plan" {
		comp = "../specs/example.html"
	}
	return M{"format": model.Format, "format_version": model.FormatVersion, "kind": kind, "schema_version": model.SchemaVersion, "artifact_id": id, "slug": "example", "revision": int64(1), "governance": M{"state": "draft", "approvals": Arr(), "review_notes": Arr()}, "presentation": render.Presentation(comp), "normative": M{"title": "Configuration precedence", "summary": "Environment values take precedence without treating false as absent.", "baseline": M{"repository": nil, "commit": nil, "observed_date": "2026-09-14"}, "sections": Arr(), "sources": Arr(), "retired_symbols": Arr()}}
}
func Spec() M {
	v := Base("spec", "SPEC-EXAMPLE")
	n := model.M(v["normative"])
	n["intent"] = M{"id": "INTENT-01", "problem": "Configuration precedence is ambiguous.", "caller": "Application initialization", "outcome": "Deterministic effective configuration", "source_refs": Arr()}
	n["approach"] = M{"id": "APPROACH-01", "choice": "Resolve validated values in explicit order.", "tradeoff": "Validation is a separate boundary.", "binding_decision_refs": Arr()}
	n["constraints"] = Arr()
	n["scope"] = Arr(M{"id": "SCOPE-01", "statement": "Resolve present values"})
	n["non_goals"] = Arr(M{"id": "NON-GOAL-01", "statement": "Parsing raw configuration"})
	n["decisions"] = Arr()
	n["governs"] = model.List("src/*.go")
	n["open_decisions"] = Arr()
	n["criteria"] = Arr(Criterion("AC-001"))
	return v
}
func Criterion(id string) M {
	return M{"id": id, "title": "Select the environment value", "kind": "behavior", "obligation": "must", "intent_refs": model.List("SCOPE-01"), "statement": "When both sources contain a valid value, select the environment value.", "preconditions": model.List("Both values are validated."), "trigger": "Resolve a supported key.", "guarantees": model.List("Effective value equals environment value."), "scenarios": Arr(M{"id": "SCN-" + id, "given": "Environment=false, file=true", "when": "Resolve key", "then": "Effective value=false"}), "verification": M{"id": "VER-" + id, "method": "automated", "planned_target": "TestEnvironmentOverrides", "oracle": "Assert effective value is false.", "negative_control": "File-first resolver fails.", "evidence_state": "planned"}, "source_refs": Arr(), "constraint_refs": Arr(), "applicability": M{"mode": "conditional", "rationale": "Both sources are present."}}
}
func Plan(spec *model.Document) M {
	v := Base("plan", "PLAN-EXAMPLE")
	n := model.M(v["normative"])
	n["spec_ref"] = M{"artifact_id": spec.ID(), "normative_sha256": spec.NormHash(), "binding_mode": "draft_preview"}
	tasks := Arr()
	states := M{}
	for i := 1; i <= 3; i++ {
		id := fmt.Sprintf("T-%03d", i)
		cp := "CP-01"
		deps := Arr()
		if i > 1 {
			deps = model.List(fmt.Sprintf("T-%03d", i-1))
		}
		if i == 3 {
			cp = "CP-02"
		}
		tasks = append(tasks, M{"id": id, "title": fmt.Sprintf("Implement and verify stage %d", i), "checkpoint": cp, "execution_scope": cp, "depends_on": deps, "paths": Arr(M{"path": fmt.Sprintf("src/stage%d.go", i), "action": "create"}), "criterion_refs": model.List(spec.ID() + "#AC-001"), "steps": model.List("Write the negative test.", "Implement the contract."), "verification": Arr(M{"availability": "proposed", "cwd": ".", "argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "expected_exit": int64(0), "assertion": "Named test runs and passes.", "required_tests": model.List("TestEnvironmentOverrides")}), "done_when": model.List("The named test passes."), "rollback": "Revert this stage.", "source_refs": Arr()})
		states[id] = M{"state": "PENDING", "evidence_refs": Arr(), "reason": nil}
	}
	n["tasks"] = tasks
	n["checkpoints"] = Arr(M{"id": "CP-01", "title": "Core", "tasks": model.List("T-001", "T-002"), "exit": "Combined scope verified.", "depends_on": Arr()}, M{"id": "CP-02", "title": "Integration", "tasks": model.List("T-003"), "exit": "Integration verified.", "depends_on": model.List("CP-01")})
	n["prerequisites"] = Arr()
	n["criterion_dispositions"] = Arr()
	v["execution"] = M{"tasks": states, "prerequisites": M{}, "prerequisite_evidence": M{}, "scopes": M{}}
	return v
}
func Seal(t testing.TB, v M) *model.Document {
	t.Helper()
	d, e := render.Prepare(v)
	if e != nil {
		t.Fatal(e)
	}
	return d
}
