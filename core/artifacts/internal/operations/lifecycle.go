package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	reads "github.com/arbiterForge/codeArbiter/core/artifacts/internal/read"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func (e *Engine) guards(d *model.Document) (*model.Document, error) {
	if d.Kind() == "spec" {
		if err := validate.Error(validate.Ready(d, nil)); err != nil {
			return nil, err
		}
		if _, err := authority.Approved(e.FS, d); err != nil {
			return nil, err
		}
		return d, nil
	}
	s, err := e.Catalog.Spec(d)
	if err != nil {
		return nil, err
	}
	if err = validate.Error(validate.Ready(d, s.Doc)); err != nil {
		return nil, err
	}
	if model.S(model.M(d.Norm()["spec_ref"])["binding_mode"]) != "approved_source" {
		return nil, fault.New("DRAFT_BINDING", "plan must be explicitly rebound to an approved source")
	}
	if _, err = authority.Approved(e.FS, s.Doc); err != nil {
		return nil, err
	}
	if _, err = authority.Approved(e.FS, d); err != nil {
		return nil, err
	}
	return s.Doc, nil
}
func (e *Engine) approve(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	var spec *model.Document
	if d.Kind() == "plan" {
		s, err := e.Catalog.Spec(d)
		if err != nil {
			return nil, err
		}
		spec = s.Doc
		if model.S(model.M(d.Norm()["spec_ref"])["binding_mode"]) != "approved_source" {
			return nil, fault.New("DRAFT_BINDING", "plan-bind must precede plan approval")
		}
		if _, err = authority.Approved(e.FS, spec); err != nil {
			return nil, err
		}
	}
	if err := validate.Error(validate.Ready(d, spec)); err != nil {
		return nil, err
	}
	receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
	if err != nil {
		return nil, err
	}
	if err = receipt.Subject(d, d.ID(), "approval"); err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	g := model.M(next.Data["governance"])
	g["state"] = "approved"
	g["approvals"] = append(model.A(g["approvals"]), authority.ApprovalRecord(receipt, d))
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}
func (e *Engine) bind(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "only a plan can bind a specification")
	}
	s, err := e.Catalog.Resolve(model.S(r["spec_id"]))
	if err != nil {
		return nil, err
	}
	if s.Doc.Kind() != "spec" {
		return nil, fault.New("WRONG_KIND", "binding target is not a specification")
	}
	if _, err = e.guards(s.Doc); err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	if len(model.A(r["changes"])) > 0 {
		next, _, err = Changes(next, model.A(r["changes"]))
		if err != nil {
			return nil, err
		}
	}
	next.Norm()["spec_ref"] = object{"artifact_id": s.Doc.ID(), "normative_sha256": s.Doc.NormHash(), "binding_mode": "approved_source"}
	model.M(next.Data["governance"])["state"] = "draft"
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	if err = validate.Error(validate.Binding(next, s.Doc)); err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}
func state(d *model.Document, id string) object {
	return model.M(model.M(model.M(d.Data["execution"])["tasks"])[id])
}
func (e *Engine) prerequisites(d *model.Document) error {
	ex := model.M(d.Data["execution"])
	for _, v := range model.A(d.Norm()["prerequisites"]) {
		r := model.M(v)
		id := model.S(r["id"])
		if model.S(model.M(ex["prerequisites"])[id]) != "satisfied" {
			return fault.New("PREREQUISITE_UNSATISFIED", "plan prerequisite is not satisfied: "+id)
		}
		ok := false
		for _, p := range model.Strings(model.M(ex["prerequisite_evidence"])[id]) {
			receipt, err := authority.Load(e.FS, p)
			if err == nil && receipt.Subject(d, id, "prerequisite") == nil {
				ok = true
			}
		}
		if !ok {
			return fault.New("STALE_EVIDENCE", "prerequisite evidence is not current")
		}
	}
	return nil
}
func (e *Engine) priorScopes(d, spec *model.Document, scope, input string) error {
	found := false
	for _, v := range model.A(d.Norm()["checkpoints"]) {
		cp := model.M(v)
		if model.S(cp["id"]) == scope {
			found = true
			break
		}
		for _, id := range model.Strings(cp["tasks"]) {
			if err := evidence.AcceptedFresh(e.FS, d, spec, id, input); err != nil {
				return err
			}
		}
	}
	if !found {
		return fault.New("UNKNOWN_SCOPE", "execution scope does not exist")
	}
	return nil
}
func (e *Engine) taskEligible(d, spec *model.Document, id, input string) error {
	r, ok := d.Symbols.ByID[id]
	if !ok || r.Kind != "tasks" {
		return fault.New("UNKNOWN_TASK", "task does not exist")
	}
	if model.S(state(d, id)["state"]) != "PENDING" {
		return fault.New("NOT_PENDING", "task requires revalidation/reconciliation rather than a new dispatch")
	}
	scope := model.S(r.Value["checkpoint"])
	if err := e.priorScopes(d, spec, scope, input); err != nil {
		return err
	}
	for _, dep := range model.Strings(r.Value["depends_on"]) {
		dr := d.Symbols.ByID[dep]
		s := model.S(state(d, dep)["state"])
		if model.S(dr.Value["checkpoint"]) == scope && s == "REVIEW" {
			if err := evidence.TaskFresh(e.FS, d, spec, dr.Value, input); err != nil {
				return err
			}
		} else if err := evidence.AcceptedFresh(e.FS, d, spec, dep, input); err != nil {
			return err
		}
	}
	return nil
}
func (e *Engine) eligible(d *model.Document) (any, error) {
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "eligibility applies to implementation plans")
	}
	spec, err := e.guards(d)
	if err != nil {
		return nil, err
	}
	if err = e.prerequisites(d); err != nil {
		return nil, err
	}
	snap, err := evidence.Snapshot(e.FS, d)
	if err != nil {
		return nil, err
	}
	input := model.S(snap["sha256"])
	tasks := []any{}
	next := ""
	allAccepted := true
	for _, v := range model.A(d.Norm()["tasks"]) {
		r := model.M(v)
		id := model.S(r["id"])
		status := model.S(state(d, id)["state"])
		err := e.taskEligible(d, spec, id, input)
		row := object{"task": id, "state": status, "eligible": err == nil}
		if err != nil {
			row["diagnostic"] = fault.Code(err)
		}
		if status == "ACCEPTED" {
			fresh := evidence.AcceptedFresh(e.FS, d, spec, id, input) == nil
			row["current_evidence"] = fresh
			if !fresh {
				allAccepted = false
			}
		} else {
			allAccepted = false
		}
		if err == nil && next == "" {
			next = id
		}
		tasks = append(tasks, row)
	}
	return object{"artifact_id": d.ID(), "model_sha256": d.Hash(), "input_sha256": input, "next_task": next, "tasks": tasks, "all_accepted_and_current": allAccepted}, nil
}
func appendRefs(s object, refs ...string) {
	existing := model.Strings(s["evidence_refs"])
	set := map[string]bool{}
	for _, v := range existing {
		set[v] = true
	}
	for _, v := range refs {
		if !set[v] {
			existing = append(existing, v)
			set[v] = true
		}
	}
	s["evidence_refs"] = model.List(existing...)
}
func invalidateDependents(d *model.Document, id, reason string) {
	changed := map[string]bool{id: true}
	again := true
	for again {
		again = false
		for _, v := range model.A(d.Norm()["tasks"]) {
			task := model.M(v)
			tid := model.S(task["id"])
			if changed[tid] {
				continue
			}
			for _, dep := range model.Strings(task["depends_on"]) {
				if changed[dep] {
					changed[tid] = true
					again = true
					s := state(d, tid)
					if model.S(s["state"]) != "PENDING" {
						s["state"] = "STALE"
						s["reason"] = "Dependency invalidated: " + reason
					}
					break
				}
			}
		}
	}
}
func (e *Engine) progress(op string, r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "progress operations require a plan")
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	// Blocking is always safe: it grants no execution and may be necessary after
	// the spec binding has become stale. Every positive transition checks guards.
	if op == "task-block" {
		id := model.S(r["task"])
		task, ok := d.Symbols.ByID[id]
		if !ok || task.Kind != "tasks" {
			return nil, fault.New("UNKNOWN_TASK", "task does not exist")
		}
		s := state(next, id)
		s["state"] = "BLOCKED"
		s["reason"] = r["reason"]
		invalidateDependents(next, id, model.S(r["reason"]))
		next.Data["revision"] = d.Revision() + 1
		next, err = render.Prepare(next.Data)
		if err != nil {
			return nil, err
		}
		return e.save(r, entry, next)
	}
	spec, err := e.guards(d)
	if err != nil {
		return nil, err
	}
	snap, err := evidence.Snapshot(e.FS, d)
	if err != nil {
		return nil, err
	}
	input := model.S(snap["sha256"])
	ex := model.M(next.Data["execution"])
	if op == "prerequisite" {
		id := model.S(r["prerequisite"])
		record, ok := d.Symbols.ByID[id]
		if !ok || record.Kind != "prerequisites" {
			return nil, fault.New("UNKNOWN_PREREQUISITE", "prerequisite is absent")
		}
		receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
		if err != nil {
			return nil, err
		}
		if err = receipt.Subject(d, id, "prerequisite"); err != nil {
			return nil, err
		}
		model.M(ex["prerequisites"])[id] = "satisfied"
		refs := model.Strings(model.M(ex["prerequisite_evidence"])[id])
		refs = append(refs, receipt.Path)
		model.M(ex["prerequisite_evidence"])[id] = model.List(refs...)
	} else {
		if err = e.prerequisites(d); err != nil {
			return nil, err
		}
		switch op {
		case "task-start":
			id := model.S(r["task"])
			if err = e.taskEligible(d, spec, id, input); err != nil {
				return nil, err
			}
			if err = reads.CheckTicket(e.FS, e.Catalog, d, id, model.S(r["context_ticket"])); err != nil {
				return nil, err
			}
			scope := model.S(d.Symbols.ByID[id].Value["checkpoint"])
			scopes := model.M(ex["scopes"])
			if base := model.M(scopes[scope]); base == nil {
				scopes[scope] = object{"base_input_sha256": input, "plan_sha256": d.NormHash()}
			} else if model.S(base["plan_sha256"]) != d.NormHash() {
				return nil, fault.New("SCOPE_RECONCILIATION_REQUIRED", "scope baseline predates the current plan")
			}
			s := state(next, id)
			s["state"] = "IN_PROGRESS"
			s["reason"] = nil
		case "task-review":
			id := model.S(r["task"])
			task, ok := d.Symbols.ByID[id]
			if !ok || task.Kind != "tasks" {
				return nil, fault.New("UNKNOWN_TASK", "task is absent")
			}
			status := model.S(state(d, id)["state"])
			if status != "IN_PROGRESS" && status != "REVIEW" && status != "ACCEPTED" && status != "STALE" {
				return nil, fault.New("INVALID_TRANSITION", "task must have been dispatched before recording review")
			}
			scope := model.S(task.Value["checkpoint"])
			if base := model.M(model.M(ex["scopes"])[scope]); model.S(base["plan_sha256"]) != d.NormHash() {
				return nil, fault.New("SCOPE_RECONCILIATION_REQUIRED", "scope baseline must be reconciled")
			}
			vr, err := authority.Load(e.FS, model.S(r["verification_receipt"]))
			if err != nil {
				return nil, err
			}
			rr, err := authority.Load(e.FS, model.S(r["review_receipt"]))
			if err != nil {
				return nil, err
			}
			if model.S(vr.Data["kind"]) != "verification" || model.S(rr.Data["kind"]) != "spec_review" {
				return nil, fault.New("INVALID_EVIDENCE", "verification and spec review are separate required events")
			}
			for _, receipt := range []*authority.Receipt{vr, rr} {
				if err = evidence.TaskPayload(receipt, d, spec, task.Value, input); err != nil {
					return nil, err
				}
			}
			s := state(next, id)
			s["state"] = "REVIEW"
			s["reason"] = nil
			appendRefs(s, vr.Path, rr.Path)
		case "task-reconcile":
			id := model.S(r["task"])
			task, ok := d.Symbols.ByID[id]
			if !ok || task.Kind != "tasks" {
				return nil, fault.New("UNKNOWN_TASK", "task does not exist")
			}
			receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
			if err != nil {
				return nil, err
			}
			if err = receipt.Subject(d, id, "reconciliation"); err != nil {
				return nil, err
			}
			p := receipt.Payload()
			h, _ := canonical.Hash(task.Value)
			if p["input_sha256"] != input || p["task_sha256"] != h || p["target_state"] != r["state"] {
				return nil, fault.New("STALE_EVIDENCE", "reconciliation event does not match the observed state/input")
			}
			wanted := model.S(r["state"])
			if wanted == "REVIEW" {
				if err = evidence.TaskFresh(e.FS, d, spec, task.Value, input); err != nil {
					return nil, err
				}
			}
			s := state(next, id)
			s["state"] = wanted
			s["reason"] = r["reason"]
			appendRefs(s, receipt.Path)
			if wanted != "REVIEW" {
				invalidateDependents(next, id, model.S(r["reason"]))
			}
		case "scope-reconcile":
			scope := model.S(r["scope"])
			cp, ok := d.Symbols.ByID[scope]
			if !ok || cp.Kind != "checkpoints" {
				return nil, fault.New("UNKNOWN_SCOPE", "scope is absent")
			}
			receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
			if err != nil {
				return nil, err
			}
			if err = receipt.Subject(d, scope, "reconciliation"); err != nil {
				return nil, err
			}
			if receipt.Payload()["input_sha256"] != input || model.S(receipt.Payload()["assessment"]) == "" {
				return nil, fault.New("STALE_EVIDENCE", "scope reconciliation must describe the exact current input")
			}
			model.M(ex["scopes"])[scope] = object{"base_input_sha256": input, "plan_sha256": d.NormHash()}
			for _, id := range model.Strings(cp.Value["tasks"]) {
				appendRefs(state(next, id), receipt.Path)
			}
		case "accept-scope":
			scope := model.S(r["scope"])
			cp, ok := d.Symbols.ByID[scope]
			if !ok || cp.Kind != "checkpoints" {
				return nil, fault.New("UNKNOWN_SCOPE", "scope is absent")
			}
			if err = e.priorScopes(d, spec, scope, input); err != nil {
				return nil, err
			}
			receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
			if err != nil {
				return nil, err
			}
			if err = evidence.Quality(receipt, d, spec, scope, input); err != nil {
				return nil, err
			}
			for _, id := range model.Strings(cp.Value["tasks"]) {
				s := state(d, id)
				status := model.S(s["state"])
				if status != "REVIEW" && status != "ACCEPTED" {
					return nil, fault.New("SCOPE_NOT_READY", "every scope member must be reviewed before atomic acceptance")
				}
				if err = evidence.TaskFresh(e.FS, d, spec, d.Symbols.ByID[id].Value, input); err != nil {
					return nil, err
				}
			}
			for _, id := range model.Strings(cp.Value["tasks"]) {
				s := state(next, id)
				s["state"] = "ACCEPTED"
				s["reason"] = nil
				appendRefs(s, receipt.Path)
			}
		}
	}
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}
