package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func object(p map[string]any, r ...string) map[string]any {
	return map[string]any{"type": "object", "properties": p, "required": model.List(r...), "additionalProperties": false}
}
func hashSchema() map[string]any {
	return map[string]any{"type": "string", "pattern": "^[0-9a-f]{64}$"}
}
func textSchema() map[string]any { return map[string]any{"type": "string", "minLength": int64(1)} }
func PayloadSchema(kind string) map[string]any {
	p := map[string]any{"input_sha256": hashSchema(), "spec_sha256": hashSchema()}
	r := []string{"input_sha256", "spec_sha256"}
	if kind == "quality_review" {
		p["base_input_sha256"] = hashSchema()
		p["task_hashes"] = map[string]any{"type": "object", "additionalProperties": hashSchema()}
		p["assessment"] = textSchema()
		r = append(r, "base_input_sha256", "task_hashes", "assessment")
	} else {
		p["task_sha256"] = hashSchema()
		r = append(r, "task_sha256")
		if kind == "spec_review" {
			p["assessment"] = textSchema()
			r = append(r, "assessment")
		} else {
			test := object(map[string]any{"name": textSchema(), "status": map[string]any{"enum": model.List("pass", "fail", "skip")}}, "name", "status")
			command := object(map[string]any{"definition_sha256": hashSchema(), "exit": map[string]any{"type": "integer", "minimum": int64(0), "maximum": int64(255)}, "tests": map[string]any{"type": "array", "items": test}, "stdout_sha256": hashSchema(), "stderr_sha256": hashSchema()}, "definition_sha256", "exit", "tests", "stdout_sha256", "stderr_sha256")
			p["commands"] = map[string]any{"type": "array", "items": command, "minItems": int64(1)}
			r = append(r, "commands")
		}
	}
	return object(p, r...)
}
func TaskPayload(r *authority.Receipt, plan, spec *model.Document, task map[string]any, inputHash string) error {
	kind := model.S(r.Data["kind"])
	if kind != "verification" && kind != "spec_review" {
		return fault.New("INVALID_EVIDENCE", "expected task verification or spec review")
	}
	if e := r.Subject(plan, model.S(task["id"]), kind); e != nil {
		return e
	}
	p := r.Payload()
	if es := schema.ValidateWith(PayloadSchema(kind), p); len(es) > 0 {
		return &es[0]
	}
	th, _ := canonical.Hash(task)
	if model.S(p["input_sha256"]) != inputHash || model.S(p["spec_sha256"]) != spec.NormHash() || model.S(p["task_sha256"]) != th {
		return fault.New("STALE_EVIDENCE", "task verification/review does not match current inputs")
	}
	if kind == "spec_review" {
		return nil
	}
	defs := model.A(task["verification"])
	results := model.A(p["commands"])
	if len(defs) != len(results) {
		return fault.New("INCOMPLETE_VERIFICATION", "every declared verification command needs an outcome")
	}
	for i, v := range defs {
		def := model.M(v)
		got := model.M(results[i])
		h, _ := canonical.Hash(def)
		if model.S(got["definition_sha256"]) != h || model.I(got["exit"]) != model.I(def["expected_exit"]) {
			return fault.New("FAILED_VERIFICATION", "command definition or exit does not match the plan")
		}
		tests := map[string]string{}
		for _, v := range model.A(got["tests"]) {
			test := model.M(v)
			name := model.S(test["name"])
			if _, ok := tests[name]; ok {
				return fault.New("INVALID_EVIDENCE", "duplicate test result")
			}
			tests[name] = model.S(test["status"])
			if tests[name] != "pass" {
				return fault.New("FAILED_VERIFICATION", "failed or skipped test cannot satisfy task verification")
			}
		}
		required := model.Strings(def["required_tests"])
		argv := model.Strings(def["argv"])
		if validate.IsTestCommand(argv) && len(required) == 0 {
			return fault.New("NO_TESTS_DECLARED", "test commands must declare at least one required test name")
		}
		for _, name := range required {
			if tests[name] != "pass" {
				return fault.New("MISSING_TEST", "required named test did not run and pass: "+name)
			}
		}
	}
	return nil
}
func TaskFresh(f *store.FS, plan, spec *model.Document, task map[string]any, inputHash string) error {
	state := model.M(model.M(model.M(plan.Data["execution"])["tasks"])[model.S(task["id"])])
	found := map[string]bool{}
	for _, p := range model.Strings(state["evidence_refs"]) {
		r, e := authority.Load(f, p)
		if e != nil {
			continue
		}
		kind := model.S(r.Data["kind"])
		if kind != "verification" && kind != "spec_review" {
			continue
		}
		if e = TaskPayload(r, plan, spec, task, inputHash); e == nil {
			found[kind] = true
		}
	}
	if !found["verification"] || !found["spec_review"] {
		return fault.New("STALE_EVIDENCE", "task needs current verification and spec-review receipts")
	}
	return nil
}
func Quality(r *authority.Receipt, plan, spec *model.Document, scope string, inputHash string) error {
	if e := r.Subject(plan, scope, "quality_review"); e != nil {
		return e
	}
	p := r.Payload()
	if es := schema.ValidateWith(PayloadSchema("quality_review"), p); len(es) > 0 {
		return &es[0]
	}
	base := model.M(model.M(model.M(plan.Data["execution"])["scopes"])[scope])
	if model.S(base["plan_sha256"]) != plan.NormHash() || model.S(base["base_input_sha256"]) != model.S(p["base_input_sha256"]) {
		return fault.New("SCOPE_RECONCILIATION_REQUIRED", "quality review lacks the recorded current scope baseline")
	}
	if model.S(p["input_sha256"]) != inputHash || model.S(p["spec_sha256"]) != spec.NormHash() {
		return fault.New("STALE_EVIDENCE", "quality review input identity is stale")
	}
	cp, ok := plan.Symbols.ByID[scope]
	if !ok || cp.Kind != "checkpoints" {
		return fault.New("UNKNOWN_SCOPE", "scope does not exist")
	}
	hashes := model.M(p["task_hashes"])
	ids := model.Strings(cp.Value["tasks"])
	if len(hashes) != len(ids) {
		return fault.New("INCOMPLETE_REVIEW", "quality review must cover the complete scope")
	}
	for _, id := range ids {
		task := plan.Symbols.ByID[id].Value
		h, _ := canonical.Hash(task)
		if hashes[id] != h {
			return fault.New("STALE_EVIDENCE", "quality review task identity is stale")
		}
	}
	return nil
}
func AcceptedFresh(f *store.FS, plan, spec *model.Document, id, inputHash string) error {
	task, ok := plan.Symbols.ByID[id]
	if !ok || task.Kind != "tasks" {
		return fault.New("UNKNOWN_TASK", "task is absent")
	}
	s := model.M(model.M(model.M(plan.Data["execution"])["tasks"])[id])
	if model.S(s["state"]) != "ACCEPTED" {
		return fault.New("DEPENDENCY_NOT_ACCEPTED", "external dependency is not accepted")
	}
	if e := TaskFresh(f, plan, spec, task.Value, inputHash); e != nil {
		return e
	}
	scope := model.S(task.Value["checkpoint"])
	for _, ref := range model.Strings(s["evidence_refs"]) {
		r, e := authority.Load(f, ref)
		if e == nil && model.S(r.Data["kind"]) == "quality_review" {
			if e = Quality(r, plan, spec, scope, inputHash); e == nil {
				return nil
			}
		}
	}
	return fault.New("STALE_EVIDENCE", "accepted task has no current scope quality review")
}
