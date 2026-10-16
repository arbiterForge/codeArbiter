package operations

import (
	"encoding/json"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// dependencyAdvice follows the full dependency chain without changing progress.
func dependencyAdvice(d *model.Document, task object) (dependencies, waiting []any, err error) {
	dependencies, waiting = []any{}, []any{}
	seen := map[string]bool{model.S(task["id"]): true}
	queue := model.Strings(task["depends_on"])
	direct := map[string]bool{}
	for _, id := range queue {
		direct[id] = true
	}
	for i := 0; i < len(queue); i++ {
		id := queue[i]
		if seen[id] {
			continue
		}
		seen[id] = true
		predecessor, found := d.Symbols.ByID[id]
		if !found || predecessor.Retired || predecessor.Kind != "tasks" {
			return nil, nil, fault.At("DANGLING_REFERENCE", model.S(task["id"]), "depends_on", "task depends on an absent or retired task")
		}
		s := state(d, id)
		status := model.S(s["state"])
		dependency := object{"id": id, "title": predecessor.Value["title"], "state": status}
		unfinished := status != "REVIEW" && status != "ACCEPTED" && status != "DONE"
		if unfinished {
			waiting = append(waiting, id)
			dependency["reason"] = s["reason"]
		}
		if direct[id] || unfinished {
			dependencies = append(dependencies, dependency)
		}
		queue = append(queue, model.Strings(predecessor.Value["depends_on"])...)
	}
	return dependencies, waiting, nil
}

// eligible is scheduling advice, not authorization or verification. In particular,
// it must not snapshot source files or load approval/review receipt chains merely
// to tell the caller which recorded dependencies are available.
func (e *Engine) eligible(d *model.Document) (any, error) {
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "scheduling applies to implementation plans")
	}
	if err := validate.Error(validate.Structural(d)); err != nil {
		return nil, err
	}
	prerequisites := []any{}
	for _, value := range model.A(d.Norm()["prerequisites"]) {
		prerequisites = append(prerequisites, model.PrerequisiteAssessment(d, model.M(value)))
	}
	rows := []any{}
	next := ""
	for _, value := range model.A(d.Norm()["tasks"]) {
		task := model.M(value)
		id := model.S(task["id"])
		status := model.S(state(d, id)["state"])
		_, waiting, err := dependencyAdvice(d, task)
		if err != nil {
			return nil, err
		}
		conditions := []any{}
		for _, value := range prerequisites {
			condition := model.M(value)
			if condition["outcome"] == "satisfied" {
				continue
			}
			for _, affected := range model.Strings(condition["task_refs"]) {
				if affected == id {
					conditions = append(conditions, condition["id"])
					break
				}
			}
		}
		available := status == "PENDING" && len(waiting) == 0 && len(conditions) == 0
		row := object{"task": id, "state": status, "eligible": available,
			"waiting_on": waiting, "waiting_prerequisites": conditions,
			"reason": state(d, id)["reason"], "evidence_assessed": false}
		if status != "PENDING" {
			row["diagnostic"] = "NOT_PENDING"
		} else if len(waiting) != 0 {
			row["diagnostic"] = "DEPENDENCY_PENDING"
		} else if len(conditions) != 0 {
			row["diagnostic"] = "PREREQUISITE_PENDING"
		}
		if available && next == "" {
			next = id
		}
		rows = append(rows, row)
	}
	bindingCurrent := false
	if spec, err := e.Catalog.Spec(d); err == nil {
		bindingCurrent = spec.Doc.NormHash() == model.S(model.M(d.Norm()["spec_ref"])["normative_sha256"])
	}
	compact := []any{}
	for _, value := range prerequisites {
		assessment := model.M(value)
		row := object{"details_omitted": true}
		for _, field := range []string{"id", "kind", "scope", "task_refs", "outcome", "recorded_state", "definition_current", "provenance", "needs_decision", "evidence_assessed"} {
			row[field] = assessment[field]
		}
		compact = append(compact, row)
	}
	out := object{"artifact_id": d.ID(), "model_sha256": d.Hash(),
		"assessment": "advisory", "evidence_assessed": false, "binding_current": bindingCurrent,
		"next_task": next, "tasks": []any{}, "prerequisites": []any{}, "context_complete": false,
		"tasks_total": int64(len(rows)), "tasks_omitted": int64(len(rows)),
		"prerequisites_total": int64(len(compact)), "prerequisites_omitted": int64(len(compact)),
		"omitted_context": model.List("prerequisite titles, requirements and observations", "task or prerequisite rows that exceed the response budget"),
		"detail_read":     "Use outline for symbol IDs and read with mode exact for prerequisite details, task definitions and reported checks. Use task-context for state and reason; an indivisible oversized record may return RECORD_TOO_LARGE."}
	// Count JSON-escaped bytes, retaining headroom for the CLI envelope. A
	// large row cannot hide the global next-task decision or smaller rows.
	encoded, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	remaining := 65536 - 1024 - len(encoded)
	for _, group := range []struct {
		key  string
		rows []any
	}{{"tasks", rows}, {"prerequisites", compact}} {
		shown := []any{}
		for _, row := range group.rows {
			encoded, err := json.Marshal(row)
			if err != nil {
				return nil, err
			}
			if len(encoded)+1 <= remaining {
				shown = append(shown, row)
				remaining -= len(encoded) + 1
			}
		}
		out[group.key] = shown
		out[group.key+"_omitted"] = int64(len(group.rows) - len(shown))
	}
	return out, nil
}

// recordWork changes progress only. The existing write journal retains the
// before-image and reason, and Run applies CAS/replay before reaching this code.
// It never writes an approval, verification observation, or reviewer receipt.
func (e *Engine) recordWork(op string, r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "progress requires a plan")
	}
	id := model.S(r["task"])
	task, ok := d.Symbols.ByID[id]
	if !ok || task.Kind != "tasks" || task.Retired {
		return nil, fault.New("UNKNOWN_TASK", "task does not exist")
	}
	status := model.S(state(d, id)["state"])
	wanted, reason := "", any(nil)
	switch op {
	case "task-start":
		// A repeated operation ID is replayed before here. A *new* start must
		// not silently redispatch a running task or clear a recorded stop.
		if status != "PENDING" {
			return nil, fault.New("NOT_PENDING", "inspect existing work and reconcile its progress before a new start")
		}
		wanted = "IN_PROGRESS"
	case "task-review":
		if status != "IN_PROGRESS" && status != "REVIEW" {
			return nil, fault.New("INVALID_TRANSITION", "record implementation work before reporting it ready for review")
		}
		wanted, reason = "REVIEW", "Implementation reported complete; verification and review are not assessed by this progress update."
	case "task-reconcile":
		wanted, reason = model.S(r["state"]), r["reason"]
	default:
		return nil, fault.New("UNKNOWN_OPERATION", "not an ordinary progress operation")
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	s := state(next, id)
	s["state"], s["reason"] = wanted, reason
	// Preserve evidence as history. Progress labels alone never upgrade it to
	// current evidence, and do not reset unrelated implementation state.
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}
