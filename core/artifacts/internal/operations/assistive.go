package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

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
	rows := []any{}
	next := ""
	for _, value := range model.A(d.Norm()["tasks"]) {
		task := model.M(value)
		id := model.S(task["id"])
		status := model.S(state(d, id)["state"])
		waiting := []any{}
		for _, dep := range model.Strings(task["depends_on"]) {
			// REVIEW records finished implementation, not proof that checks ran.
			// Evidence applicability is assessed separately when making a claim.
			depState := model.S(state(d, dep)["state"])
			if depState != "REVIEW" && depState != "ACCEPTED" {
				waiting = append(waiting, dep)
			}
		}
		available := status == "PENDING" && len(waiting) == 0
		row := object{"task": id, "state": status, "eligible": available,
			"waiting_on": waiting, "reason": state(d, id)["reason"], "evidence_assessed": false}
		if status != "PENDING" {
			row["diagnostic"] = "NOT_PENDING"
		} else if len(waiting) != 0 {
			row["diagnostic"] = "DEPENDENCY_PENDING"
		}
		if available && next == "" {
			next = id
		}
		rows = append(rows, row)
	}
	prerequisites := []any{}
	for _, value := range model.A(d.Norm()["prerequisites"]) {
		record := model.M(value)
		id := model.S(record["id"])
		prerequisites = append(prerequisites, object{
			"id": id, "title": record["title"], "requirement": record["requirement"],
			"recorded_state": model.M(model.M(d.Data["execution"])["prerequisites"])[id],
			// Legacy records have no task scope. Do not silently turn that absence
			// into either a plan-wide permission gate or a satisfied condition.
			"scope": "unspecified", "evidence_assessed": false,
		})
	}
	bindingCurrent := false
	if spec, err := e.Catalog.Spec(d); err == nil {
		bindingCurrent = spec.Doc.NormHash() == model.S(model.M(d.Norm()["spec_ref"])["normative_sha256"])
	}
	return object{"artifact_id": d.ID(), "model_sha256": d.Hash(),
		"assessment": "advisory", "evidence_assessed": false, "binding_current": bindingCurrent,
		"next_task": next, "tasks": rows, "prerequisites": prerequisites}, nil
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
