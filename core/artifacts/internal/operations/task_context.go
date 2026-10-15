package operations

import (
	"encoding/json"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

// taskContext is a bounded, read-only orientation packet. It does not inspect
// source files, run checks, mint delivery receipts, or grant authority.
func (e *Engine) taskContext(d *model.Document, id string, budget int) (any, error) {
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "task context requires a plan")
	}
	task, ok := d.Symbols.ByID[id]
	if !ok || task.Kind != "tasks" || task.Retired {
		return nil, fault.New("UNKNOWN_TASK", "task is absent or retired")
	}
	spec, err := e.Catalog.Spec(d)
	if err != nil {
		return nil, err
	}
	bound := model.S(model.M(d.Norm()["spec_ref"])["normative_sha256"])
	current := spec.Doc.NormHash() == bound
	criteria := []any{}
	for _, ref := range model.Strings(task.Value["criterion_refs"]) {
		artifact, criterionID, err := symbol.Split(ref)
		if err != nil || artifact != spec.Doc.ID() {
			return nil, fault.At("DANGLING_REFERENCE", id, "criterion_refs", "task criterion is not in the selected source")
		}
		record, found := spec.Doc.Symbols.ByID[criterionID]
		if !found || record.Retired || record.Kind != "criteria" {
			return nil, fault.At("DANGLING_REFERENCE", id, "criterion_refs", "task references an absent or retired criterion")
		}
		criteria = append(criteria, object{
			"ref": ref, "title": record.Value["title"], "statement": record.Value["statement"],
			"trigger": record.Value["trigger"], "preconditions": record.Value["preconditions"],
			"guarantees": record.Value["guarantees"], "verification": record.Value["verification"],
			"full_symbol": criterionID,
		})
	}

	waiting := []any{}
	dependencies := []any{}
	for _, dep := range model.Strings(task.Value["depends_on"]) {
		predecessor, found := d.Symbols.ByID[dep]
		if !found || predecessor.Retired || predecessor.Kind != "tasks" {
			return nil, fault.At("DANGLING_REFERENCE", id, "depends_on", "task depends on an absent or retired task")
		}
		status := model.S(state(d, dep)["state"])
		dependencies = append(dependencies, object{"id": dep, "title": predecessor.Value["title"], "state": status})
		if status != "REVIEW" && status != "DONE" && status != "ACCEPTED" {
			waiting = append(waiting, dep)
		}
	}

	prerequisites := []any{}
	unscoped := []any{}
	waitingOnFacts := []any{}
	for _, value := range model.A(d.Norm()["prerequisites"]) {
		record := model.M(value)
		assessed := model.PrerequisiteAssessment(d, record)
		refs := model.Strings(record["task_refs"])
		if len(refs) == 0 {
			// Old unscoped conditions must be exposed without assuming either
			// that they apply globally or that they are satisfied.
			unscoped = append(unscoped, assessed)
			continue
		}
		for _, ref := range refs {
			if ref == id {
				prerequisites = append(prerequisites, assessed)
				if assessed["outcome"] != "satisfied" {
					waitingOnFacts = append(waitingOnFacts, assessed["id"])
				}
				break
			}
		}
	}

	status := model.S(state(d, id)["state"])
	checks, historyBounded := model.TaskCheckAssessments(d, spec.Doc, id)
	// Small model-facing packet: last three reports only. The typed HTML
	// includes the bounded recorded history; native transaction before-images
	// retain older reports. Neither claims source-file applicability.
	shown := checks
	if len(shown) > 3 {
		shown = shown[len(shown)-3:]
	}
	out := object{
		"artifact_id": d.ID(), "revision": d.Revision(), "model_sha256": d.Hash(),
		"normative_sha256": d.NormHash(), "source_artifact_id": spec.Doc.ID(),
		"source_revision": spec.Doc.Revision(), "source_normative_sha256": spec.Doc.NormHash(),
		"bound_source_normative_sha256": bound, "binding_current": current,
		"assessment": "advisory", "evidence_assessed": false, "context_complete": false,
		"task": object{
			"id": id, "title": task.Value["title"], "checkpoint": task.Value["checkpoint"],
			"execution_scope": task.Value["execution_scope"], "depends_on": task.Value["depends_on"],
			"steps": task.Value["steps"], "paths": task.Value["paths"], "rollback": task.Value["rollback"],
			"criterion_refs": task.Value["criterion_refs"], "verification": task.Value["verification"],
			"done_when": task.Value["done_when"], "source_refs": task.Value["source_refs"],
		},
		"state": status, "reason": state(d, id)["reason"], "criteria": criteria,
		"dependencies": dependencies, "waiting_on": waiting,
		"prerequisites": prerequisites, "unscoped_prerequisites": unscoped,
		"waiting_prerequisites": waitingOnFacts,
		"reported_checks":       shown, "check_reports_omitted": int64(len(checks) - len(shown)),
		"check_history_bounded": historyBounded, "checks_are_verified": false,
		"next_action":     "Inspect the recorded dependencies and checks; execute work through existing host permissions.",
		"omitted_context": model.List("unrelated tasks", "broader specification decisions", "full source and test output"),
	}
	if !current {
		out["next_action"] = "Source binding changed; inspect affected requirements and reconcile the plan without resetting unrelated work."
	} else if status == "BLOCKED" {
		out["next_action"] = "Inspect the recorded stop; do not clear it or redispatch until the actual condition or user decision is resolved."
	} else if len(shown) > 0 {
		latest := model.M(shown[len(shown)-1])
		switch model.S(latest["reported_outcome"]) {
		case "fail":
			out["next_action"] = "The latest command was reported failing; inspect actual output and repair the affected work before claiming verification. No new artifact permission is required."
		case "skip", "unknown":
			out["next_action"] = "The latest command was skipped or remains unknown; record the missing or unavailable check honestly and continue other authorized work."
		case "pass":
			out["next_action"] = "A command was reported passing, but named-test and source-file evidence is not attested; assess relevant coverage before any verification claim."
		}
	}
	b, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	if len(b)+1024 > budget {
		return nil, fault.At("RECORD_TOO_LARGE", id, "", "task packet exceeds response budget; use exact symbol reads or increase budget; no truncated packet returned")
	}
	return out, nil
}
