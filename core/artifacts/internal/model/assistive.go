package model

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"strings"
)

// HasAssistiveFields prevents new semantics from being stored under an old
// schema label. Reading an unchanged historical document never upgrades it.
func HasAssistiveFields(v map[string]any) bool {
	if S(v["kind"]) != "plan" {
		return false
	}
	for _, value := range A(M(v["normative"])["tasks"]) {
		if _, has := M(value)["shared_inputs"]; has {
			return true
		}
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
	if _, ok := ex["task_check_observations"]; ok {
		return true
	}
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

// TaskCheckDefinition tracks the task's *verification subject*, not the
// implementation recipe or presentation. A changed path or criterion can make
// an old command result inapplicable even when the command argv stays equal.
// File contents and external shared interfaces are never assessed here.
func TaskCheckDefinition(task map[string]any) (string, error) {
	fields := map[string]any{
		"verification": task["verification"], "paths": task["paths"],
		"criterion_refs": task["criterion_refs"], "source_refs": task["source_refs"],
	}
	// Existing records must not become stale simply because the engine learned
	// an *optional* field that is absent in the historical task definition.
	if shared, present := task["shared_inputs"]; present {
		fields["shared_inputs"] = shared
	}
	return canonical.Hash(fields)
}

// TaskCriterionSubject hashes exactly the declared normative criteria used by
// the selected task. Unlike a whole-spec digest, a different unrelated
// criterion or a presentation-only change does not automatically invalidate
// this task's observations. An incomplete reference fails closed.
func TaskCriterionSubject(spec *Document, task map[string]any) (string, error) {
	refs := Strings(task["criterion_refs"])
	rows := []any{}
	for _, ref := range refs {
		specID, id, ok := strings.Cut(ref, "#")
		if !ok || specID != spec.ID() {
			return "", canonicalError("task criterion is not bound to the selected spec")
		}
		record, found := spec.Symbols.ByID[id]
		if !found || record.Retired || record.Kind != "criteria" {
			return "", canonicalError("task criterion is missing or retired")
		}
		rows = append(rows, map[string]any{"ref": ref, "record": record.Value})
	}
	return canonical.Hash(map[string]any{
		"format": "task-criteria/1", "spec_id": spec.ID(), "criteria": rows,
	})
}

type canonicalError string

func (e canonicalError) Error() string { return string(e) }

// TaskCheckAssessments returns only caller-reported information. Matching
// command/spec definitions is not evidence that source files are unchanged or
// that a particular named test passed. A later failure remains the latest
// reported result; old observations stay in the native journal before-images.
func TaskCheckAssessments(d, spec *Document, id string) ([]any, bool) {
	entries := A(M(M(d.Data["execution"])["task_check_observations"])[id])
	record, ok := d.Symbols.ByID[id]
	if !ok || record.Kind != "tasks" {
		return []any{}, false
	}
	hash, err := TaskCheckDefinition(record.Value)
	if err != nil {
		return []any{}, false
	}
	bound := S(M(d.Norm()["spec_ref"])["normative_sha256"])
	criteriaHash, criteriaErr := "", error(nil)
	if spec != nil {
		criteriaHash, criteriaErr = TaskCriterionSubject(spec, record.Value)
	}
	out := []any{}
	for _, value := range entries {
		entry := M(value)
		// HTML-only presentation cannot load the external specification. It
		// displays unknown applicability instead of falsely reporting stale
		// or current code coverage.
		var current any
		if spec != nil {
			if recordedCriteria := S(entry["criterion_subject_sha256"]); recordedCriteria != "" {
				// New observations are scoped to referenced normative criteria.
				// Binding currency is exposed separately, not silently updated.
				current = criteriaErr == nil && hash == S(entry["task_subject_sha256"]) &&
					criteriaHash == recordedCriteria
			} else {
				// Historical records never acquire narrower scope retroactively.
				current = hash == S(entry["task_subject_sha256"]) &&
					spec.NormHash() == S(entry["source_normative_sha256"]) &&
					bound == spec.NormHash()
			}
		}
		note := map[string]any{
			"argv": entry["argv"], "cwd": entry["cwd"],
			"reported_outcome": entry["outcome"], "exit_code": entry["exit_code"],
			"summary": entry["summary"], "source": entry["source"],
			"origin": entry["origin"], "recorded_at": entry["recorded_at"],
			"definition_current": current, "worktree_freshness": "unassessed",
			"provenance": "caller_reported", "evidence_assessed": false,
			"declared_command":     entry["command_index"] != nil,
			"named_tests_verified": false,
			"history_trimmed":      entry["history_trimmed"],
			"scope_coverage":       "not_recorded",
		}
		if index, exists := entry["command_index"]; exists {
			note["command_index"] = index
		}
		if h, exists := entry["scoped_inputs_sha256"]; exists {
			note["recorded_scoped_inputs_sha256"] = h
			note["scope_coverage"] = "declared_task_paths_and_known_build_inputs_only"
		}
		if why, exists := entry["scope_unassessed_reason"]; exists {
			note["scope_reason"] = why
			note["scope_coverage"] = "attempted_unassessed"
		}
		if excerpt, exists := entry["output_excerpt"]; exists {
			note["output_excerpt"] = excerpt
		}
		out = append(out, note)
	}
	return out, len(entries) > 0 && M(entries[len(entries)-1])["history_trimmed"] == true
}
