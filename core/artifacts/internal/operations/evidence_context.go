package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// evidenceContext publishes the exact current context consumed by a closed
// host evidence producer. The context is immutable generated output and is
// excluded from the input snapshot only after its complete schema is checked.
func (e *Engine) evidenceContext(r object, entry repository.Entry) (any, error) {
	plan := entry.Doc
	activity, recordID := model.S(r["activity"]), model.S(r["record_id"])
	var context object
	var err error
	if activity == "approval" || activity == "prerequisite" || activity == "reconciliation" || activity == "farm_authorization" {
		context, err = e.buildPromptContext(plan, activity, recordID, model.S(r["prompt_sha256"]))
	} else {
		if plan.Kind() != "plan" {
			return nil, fault.New("WRONG_KIND", "verification/review evidence context requires a plan")
		}
		context, err = e.buildEvidenceContext(plan, activity, recordID)
	}
	if err != nil {
		return nil, err
	}
	b, err := canonical.Marshal(context)
	if err != nil {
		return nil, err
	}
	h := canonical.BytesHash(b)
	if err = e.FS.PutDerived("evidence-contexts", h, b); err != nil {
		return nil, err
	}
	return object{"context_ref": observation.ContextRef(h), "context_sha256": h, "activity": activity, "subject": context["subject"], "input_sha256": context["input_sha256"]}, nil
}

func (e *Engine) buildPromptContext(d *model.Document, activity, recordID, promptHash string) (object, error) {
	validHash := len(promptHash) == 64
	for _, ch := range promptHash {
		if (ch < '0' || ch > '9') && (ch < 'a' || ch > 'f') {
			validHash = false
		}
	}
	if !validHash {
		return nil, fault.New("INVALID_REQUEST", "prompt evidence context requires a prompt digest")
	}
	if activity == "approval" && recordID != d.ID() {
		return nil, fault.New("UNKNOWN_SUBJECT", "approval context must name the artifact")
	}
	var record any
	inputHash := d.NormHash()
	if activity == "approval" {
		record = object{"artifact_id": d.ID(), "kind": d.Kind(), "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash()}
	} else {
		if d.Kind() != "plan" {
			return nil, fault.New("WRONG_KIND", "prerequisite/reconciliation context requires a plan")
		}
		if _, err := e.guards(d); err != nil {
			return nil, err
		}
		symbol, ok := d.Symbols.ByID[recordID]
		if !ok || symbol.Retired || activity == "prerequisite" && symbol.Kind != "prerequisites" || activity == "reconciliation" && symbol.Kind != "tasks" && symbol.Kind != "checkpoints" || activity == "farm_authorization" && symbol.Kind != "checkpoints" {
			return nil, fault.New("UNKNOWN_SUBJECT", "prompt evidence subject is absent or has the wrong kind")
		}
		copy, err := canonical.Clone(symbol.Value)
		if err != nil {
			return nil, err
		}
		record = copy
		snapshot, err := evidence.Snapshot(e.FS, d)
		if err != nil {
			return nil, err
		}
		inputHash = model.S(snapshot["sha256"])
	}
	recordHash, err := canonical.Hash(record)
	if err != nil {
		return nil, err
	}
	context := object{
		"format": "codearbiter.evidence-context/0.1.0", "activity": activity,
		"subject":      object{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": recordID},
		"input_sha256": inputHash, "prompt_sha256": promptHash,
		"record_sha256": recordHash, "record": record,
	}
	if es := schema.ValidateWith(observation.ContextSchema(), context); len(es) > 0 {
		return nil, &es[0]
	}
	return context, nil
}

func (e *Engine) buildEvidenceContext(plan *model.Document, activity, recordID string) (object, error) {
	spec, err := e.guards(plan)
	if err != nil {
		return nil, err
	}
	snap, err := evidence.Snapshot(e.FS, plan)
	if err != nil {
		return nil, err
	}
	subject := object{"artifact_id": plan.ID(), "normative_sha256": plan.NormHash(), "record_id": recordID}
	context := object{
		"format": "codearbiter.evidence-context/0.1.0", "activity": activity, "subject": subject,
		"input_sha256": snap["sha256"], "input_manifest": model.M(snap["manifest"]),
		"spec_sha256": spec.NormHash(), "plan_sha256": plan.NormHash(),
	}
	if activity == "verification" || activity == "spec_review" {
		task, ok := plan.Symbols.ByID[recordID]
		if !ok || task.Kind != "tasks" || task.Retired {
			return nil, fault.New("UNKNOWN_TASK", "evidence context task is absent or retired")
		}
		taskValue, cloneErr := canonical.Clone(task.Value)
		if cloneErr != nil {
			return nil, cloneErr
		}
		taskHash, _ := canonical.Hash(taskValue)
		commands := empty()
		for _, value := range model.A(taskValue["verification"]) {
			definition := model.M(value)
			definitionHash, _ := canonical.Hash(definition)
			commands = append(commands, object{"definition_sha256": definitionHash, "definition": definition})
		}
		context["task_sha256"], context["task"], context["commands"] = taskHash, taskValue, commands
	} else {
		scope, ok := plan.Symbols.ByID[recordID]
		if !ok || scope.Kind != "checkpoints" || scope.Retired {
			return nil, fault.New("UNKNOWN_SCOPE", "quality-review context scope is absent or retired")
		}
		baseline := model.M(model.M(model.M(plan.Data["execution"])["scopes"])[recordID])
		if len(baseline) == 0 || model.S(baseline["plan_sha256"]) != plan.NormHash() {
			return nil, fault.New("SCOPE_RECONCILIATION_REQUIRED", "quality-review context requires a current scope baseline")
		}
		baselineCopy, cloneErr := canonical.Clone(baseline)
		if cloneErr != nil {
			return nil, cloneErr
		}
		tasks, hashes := empty(), object{}
		for _, id := range model.Strings(scope.Value["tasks"]) {
			task := plan.Symbols.ByID[id]
			taskValue, cloneErr := canonical.Clone(task.Value)
			if cloneErr != nil {
				return nil, cloneErr
			}
			taskHash, _ := canonical.Hash(taskValue)
			tasks, hashes[id] = append(tasks, taskValue), taskHash
		}
		context["base_input_sha256"] = baselineCopy["base_input_sha256"]
		context["task_hashes"], context["scope_baseline"], context["tasks"] = hashes, baselineCopy, tasks
	}
	if es := schema.ValidateWith(observation.ContextSchema(), context); len(es) > 0 {
		return nil, &es[0]
	}
	return context, nil
}
