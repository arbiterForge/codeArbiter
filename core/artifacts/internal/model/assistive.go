package model

import "github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"

// HasAssistiveFields prevents new semantics from being stored under an old
// schema label. Reading an unchanged historical document never upgrades it.
func HasAssistiveFields(v map[string]any) bool {
	if S(v["kind"]) != "plan" {
		return false
	}
	for _, value := range A(M(v["normative"])["prerequisites"]) {
		r := M(value)
		if _, ok := r["kind"]; ok {
			return true
		}
		if _, ok := r["task_refs"]; ok {
			return true
		}
	}
	ex := M(v["execution"])
	if _, ok := ex["prerequisite_observations"]; ok {
		return true
	}
	for _, value := range M(ex["tasks"]) {
		if S(M(value)["state"]) == "DONE" {
			return true
		}
	}
	return false
}

// PrerequisiteDefinition names only the meaning and applicability of a check.
// Presentation titles and unrelated task/method edits do not change this key.
func PrerequisiteDefinition(record map[string]any) (string, error) {
	return canonical.Hash(map[string]any{
		"id": record["id"], "kind": record["kind"], "requirement": record["requirement"],
		"task_refs": record["task_refs"], "source_refs": record["source_refs"],
	})
}

// PrerequisiteAssessment is a projection of recorded information, not a fresh
// execution or a permission decision. It never reads source files or receipts.
func PrerequisiteAssessment(d *Document, record map[string]any) map[string]any {
	id := S(record["id"])
	kind := S(record["kind"])
	if kind == "" {
		kind = "unspecified"
	}
	tasks := Strings(record["task_refs"])
	scope := "tasks"
	if len(tasks) == 0 {
		scope = "unspecified"
	}
	ex := M(d.Data["execution"])
	observation := M(M(ex["prerequisite_observations"])[id])
	outcome, provenance := "unknown", "none"
	var current any
	if observation != nil {
		provenance = "caller_reported"
		hash, err := PrerequisiteDefinition(record)
		matches := err == nil && hash == S(observation["definition_sha256"])
		current = matches
		if matches {
			outcome = S(observation["outcome"])
		}
	} else if S(M(ex["prerequisites"])[id]) == "satisfied" {
		// Keep historical approval status visible without treating it as a new,
		// live observation or silently recertifying its source.
		provenance = "legacy_receipt_unassessed"
	}
	return map[string]any{
		"id": id, "title": record["title"], "requirement": record["requirement"],
		"kind": kind, "scope": scope, "task_refs": List(tasks...), "outcome": outcome,
		"recorded_state": M(ex["prerequisites"])[id], "observation": observation,
		"definition_current": current, "provenance": provenance,
		"needs_decision": kind == "decision" && outcome == "unknown", "evidence_assessed": false,
	}
}
