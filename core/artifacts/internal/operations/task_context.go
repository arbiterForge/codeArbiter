package operations

import (
	"encoding/json"
	"sort"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
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
	criterionRecords, constraintRecords, err := model.TaskRequirementRecords(spec.Doc, task.Value)
	if err != nil {
		return nil, fault.At("DANGLING_REFERENCE", id, "criterion_refs", err.Error())
	}
	criteria, constraints := []any{}, []any{}
	omitted := map[string]bool{}
	for _, ref := range model.Strings(task.Value["source_refs"]) {
		omitted[d.ID()+"#"+ref] = true
	}
	project := func(record object) object {
		out := object{"ref": spec.Doc.ID() + "#" + model.S(record["id"]), "full_symbol": record["id"]}
		for field, value := range record {
			out[field] = value
		}
		for _, field := range []string{"intent_refs", "source_refs"} {
			for _, ref := range model.Strings(record[field]) {
				omitted[spec.Doc.ID()+"#"+ref] = true
			}
		}
		return out
	}
	for _, record := range criterionRecords {
		criteria = append(criteria, project(record.Value))
	}
	for _, record := range constraintRecords {
		constraints = append(constraints, project(record.Value))
	}
	omittedRefs := []string{}
	for ref := range omitted {
		omittedRefs = append(omittedRefs, ref)
	}
	sort.Strings(omittedRefs)

	dependencies, waiting, err := dependencyAdvice(d, task.Value)
	if err != nil {
		return nil, err
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
	checks, historyBounded := e.assessTaskChecks(d, spec.Doc, id)
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
			"shared_inputs":  task.Value["shared_inputs"],
			"criterion_refs": task.Value["criterion_refs"], "verification": task.Value["verification"],
			"done_when": task.Value["done_when"], "source_refs": task.Value["source_refs"],
		},
		"state": status, "reason": state(d, id)["reason"], "criteria": criteria, "constraints": constraints,
		"dependencies": dependencies, "waiting_on": waiting,
		"prerequisites": prerequisites, "unscoped_prerequisites": unscoped,
		"waiting_prerequisites": waitingOnFacts,
		"reported_checks":       shown, "check_reports_omitted": int64(len(checks) - len(shown)),
		"check_history_bounded": historyBounded, "checks_are_verified": false,
		"next_action":        "Inspect the recorded dependencies and checks; execute work through existing host permissions.",
		"omitted_context":    model.List("unrelated tasks", "broader specification decisions", "constraints without declared applicability", "referenced intent and source records", "full source and test output"),
		"omitted_references": model.List(omittedRefs...),
	}
	if !current {
		out["next_action"] = "Source binding changed; inspect affected requirements and reconcile the plan without resetting unrelated work."
	} else if status == "BLOCKED" {
		out["next_action"] = "Inspect the recorded stop; do not clear it or redispatch until the actual condition or user decision is resolved."
	} else if len(waiting) != 0 {
		out["next_action"] = "Inspect unresolved dependencies and preserve their recorded stops; continue independent work while those conditions remain unresolved."
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
		if model.S(latest["worktree_freshness"]) == "scoped_changed" {
			out["next_action"] = "Declared task or shared source input bytes changed; refresh the affected command check. Independent review and host permissions remain separate."
		}
	}
	b, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	// Knowledge fills what the task packet leaves of the budget, keeping room
	// for the omission list; whole records that do not fit are named instead.
	for k, v := range e.taskKnowledge(task.Value, budget-len(b)-4096) {
		out[k] = v
	}
	b, err = json.Marshal(out)
	if err != nil {
		return nil, err
	}
	if len(b)+1024 > budget {
		return nil, fault.At("RECORD_TOO_LARGE", id, "", "task packet exceeds response budget; use exact symbol reads or increase budget; no truncated packet returned")
	}
	return out, nil
}
