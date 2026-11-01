package operations

import (
	"fmt"
	"os"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const workCoordinationLimit = 4 << 10

func mappedIntentID(transitionID, target string) string {
	return canonical.BytesHash([]byte("codearbiter-mapped-intent-v1\x00" + transitionID + "\x00" + target))
}

func (e *Engine) checkMappedClaim(ex object, effect object, target string) error {
	sourceID := model.S(effect["source_transition_id"])
	if sourceID == "" {
		return nil
	}
	coordination := model.M(ex["coordination"])
	mapping, _, generation, err := e.workTransitionMapConfig()
	if err != nil || mapping["enabled"] != true || generation != model.S(coordination["mapping_generation"]) {
		if err != nil && !os.IsNotExist(err) && !optionalProviderFailure(err) &&
			fault.Code(err) != "INVALID_TRANSITION_MAP" && fault.Code(err) != "TRANSITION_MAP_BINDING_CHANGED" {
			return err
		}
		return fault.New("EFFECT_PAUSED", "mapped intent is paused or its configuration changed; reconcile it before sending")
	}
	if sourceID != model.S(coordination["transition_id"]) ||
		model.S(effect["intent_id"]) != mappedIntentID(sourceID, target) {
		return fault.New("MAPPED_INTENT_CHANGED", "mapped intent no longer matches the latest saved transition")
	}
	if target == "issue_state" {
		if model.S(coordination["issue_intent_id"]) != model.S(effect["intent_id"]) ||
			model.S(coordination["issue_status"]) != "pending" ||
			coordination["desired_issue_state"] != effect["desired_state"] ||
			coordination["issue_generation"] != effect["binding_generation"] {
			return fault.New("MAPPED_INTENT_CHANGED", "saved issue intent changed before send")
		}
	} else if model.S(coordination["project_intent_id"]) != model.S(effect["intent_id"]) ||
		model.S(coordination["project_status"]) != "pending" ||
		coordination["desired_project_option_id"] != effect["desired_option_id"] ||
		coordination["project_field_id"] != effect["field_id"] ||
		coordination["project_generation"] != effect["binding_generation"] {
		return fault.New("MAPPED_INTENT_CHANGED", "saved Project intent changed before send")
	}
	return nil
}

// workCoordinateResume materializes a saved desire after a verified binding or
// a first selected field observation. It never creates another transition.
func (e *Engine) workCoordinateResume(r object) (any, error) {
	id := model.S(r["work_id"])
	d, before, path, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	if err := workEffectExpected(r, d, path); err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	ex := model.M(next.Data["execution"])
	coordination := model.M(ex["coordination"])
	if len(coordination) == 0 {
		return nil, fault.New("NO_MAPPED_INTENT", "selected work has no saved transition mapping")
	}
	mapping, _, generation, err := e.workTransitionMapConfig()
	if err != nil || mapping["enabled"] != true || generation != model.S(coordination["mapping_generation"]) {
		if err != nil && !os.IsNotExist(err) && fault.Code(err) != "INVALID_TRANSITION_MAP" &&
			fault.Code(err) != "TRANSITION_MAP_BINDING_CHANGED" {
			return nil, err
		}
		return nil, fault.New("EFFECT_PAUSED", "mapped intent is paused or configuration changed")
	}
	if r["observed_item_id"] != nil {
		if _, supplied := r["observed_option_id"]; !supplied {
			return nil, fault.New("INVALID_PROJECT_OBSERVATION", "bound item observation needs an explicit option value or null")
		}
		current := model.M(ex["project_effect"])
		if model.S(coordination["project_status"]) != "awaiting_observation" ||
			model.S(current["remote_item_id"]) != model.S(r["observed_item_id"]) ||
			model.S(current["binding_generation"]) != model.S(coordination["project_generation"]) ||
			model.S(coordination["project_field_id"]) == "" ||
			model.S(current["status"]) != "synchronized" || model.S(current["kind"]) != "add_item" {
			return nil, fault.New("INVALID_PROJECT_OBSERVATION", "first field observation does not match the frozen bound item")
		}
		current["kind"], current["field_id"] = "set_single_select", coordination["project_field_id"]
		current["observed_option_id"] = r["observed_option_id"]
	} else if _, supplied := r["observed_option_id"]; supplied {
		return nil, fault.New("INVALID_PROJECT_OBSERVATION", "option observation requires the exact bound Project item")
	}
	if coordination["desired_issue_state"] != nil {
		switch model.S(coordination["issue_status"]) {
		case "waiting_binding", "waiting_reconciliation":
			if err := e.stageMappedIssue(next, coordination); err != nil {
				return nil, err
			}
		}
	}
	if coordination["desired_project_option_id"] != nil {
		switch model.S(coordination["project_status"]) {
		case "waiting_binding", "waiting_reconciliation", "awaiting_observation":
			if err := e.stageMappedProject(next, coordination); err != nil {
				return nil, err
			}
		}
	}
	original, _ := canonical.Marshal(d.Data["execution"])
	updated, err := canonical.Marshal(ex)
	if err != nil {
		return nil, err
	}
	if string(original) == string(updated) {
		return nil, fault.New("COORDINATION_WAITING", "saved mapped target still awaits its binding or prior outcome")
	}
	if b, err := canonical.Marshal(coordination); err != nil || len(b) > workCoordinationLimit {
		return nil, fault.New("COORDINATION_TOO_LARGE", "bounded work coordination exceeds 4 KiB")
	}
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	after, err := render.Render(next)
	if err != nil {
		return nil, err
	}
	result := workSummary(next, path)
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash,
		[]store.Edit{{Path: path, Before: before, After: after}}, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}

// coordinateWorkTransition changes only the cloned work document. The caller
// renders and commits progress, coordination and eligible effects together.
func (e *Engine) coordinateWorkTransition(next *model.Document, operationID, action string, priorRevision int64) error {
	mapping, _, generation, err := e.workTransitionMapConfig()
	if os.IsNotExist(err) {
		return nil
	}
	ex := model.M(next.Data["execution"])
	if err == nil && mapping["enabled"] == false && ex["coordination"] == nil {
		return nil
	}
	id := canonical.BytesHash([]byte(fmt.Sprintf("codearbiter-work-transition-v1\x00%s\x00%s\x00%s\x00%d",
		model.S(next.Norm()["project_id"]), next.ID(), operationID, priorRevision)))
	coordination := object{"transition_id": id, "action": action, "mapping_generation": nil,
		"issue_generation": nil, "project_generation": nil, "project_field_id": nil,
		"desired_issue_state": nil, "desired_project_option_id": nil,
		"issue_status": "none", "project_status": "none", "issue_intent_id": nil,
		"project_intent_id": nil, "reason": nil, "superseded_transition_id": nil}
	if previous := model.M(ex["coordination"]); len(previous) != 0 {
		coordination["superseded_transition_id"] = previous["transition_id"]
	}
	if err != nil {
		if fault.Code(err) != "INVALID_TRANSITION_MAP" && fault.Code(err) != "TRANSITION_MAP_BINDING_CHANGED" {
			return err
		}
		coordination["issue_status"], coordination["project_status"] = "unavailable", "unavailable"
		coordination["reason"] = "Optional transition mapping is unusable; inspect and repair its saved configuration."
	} else if mapping["enabled"] == false {
		coordination["mapping_generation"] = generation
		if previous := model.M(ex["coordination"]); len(previous) != 0 {
			coordination["desired_issue_state"] = previous["desired_issue_state"]
			coordination["desired_project_option_id"] = previous["desired_project_option_id"]
			if previous["desired_issue_state"] != nil {
				coordination["issue_status"] = "paused"
			}
			if previous["desired_project_option_id"] != nil {
				coordination["project_status"] = "paused"
			}
		}
		coordination["reason"] = "Transition mapping is disabled; pending mapped effects are paused."
	} else {
		coordination["mapping_generation"] = generation
		coordination["issue_generation"] = mapping["issue_generation"]
		coordination["project_generation"] = mapping["project_generation"]
		coordination["project_field_id"] = mapping["project_field_id"]
		target := model.M(model.M(mapping["actions"])[action])
		coordination["desired_issue_state"] = target["issue_state"]
		coordination["desired_project_option_id"] = target["project_option_id"]
		if target["issue_state"] == nil {
			retireUnsentMappedEffect(ex, coordination, "issue_state")
		}
		if target["project_option_id"] == nil {
			retireUnsentMappedEffect(ex, coordination, "project_field")
		}
		if target["issue_state"] != nil {
			if err := e.stageMappedIssue(next, coordination); err != nil {
				return err
			}
		}
		if target["project_option_id"] != nil {
			if err := e.stageMappedProject(next, coordination); err != nil {
				return err
			}
		}
	}
	b, marshalErr := canonical.Marshal(coordination)
	if marshalErr != nil {
		return marshalErr
	}
	if len(b) > workCoordinationLimit {
		return fault.New("COORDINATION_TOO_LARGE", "bounded work coordination exceeds 4 KiB")
	}
	ex["coordination"] = coordination
	next.Data["schema_version"] = model.WorkCoordinationVersion
	return nil
}

// A null action target cancels only an unclaimed effect owned by the prior
// transition. A claimed or uncertain attempt remains available for readback.
func retireUnsentMappedEffect(ex object, next object, target string) {
	previous := model.M(ex["coordination"])
	key, intentKey := "provider_effect", "issue_intent_id"
	if target == "project_field" {
		key, intentKey = "project_effect", "project_intent_id"
	}
	current := model.M(ex[key])
	if model.S(previous["mapping_generation"]) != model.S(next["mapping_generation"]) ||
		model.S(current["source_transition_id"]) == "" ||
		model.S(current["source_transition_id"]) != model.S(previous["transition_id"]) ||
		model.S(current["intent_id"]) != model.S(previous[intentKey]) ||
		model.S(current["status"]) != "pending" || current["attempt_id"] != nil {
		return
	}
	if target == "issue_state" {
		current["status"] = "synchronized"
		delete(current, "desired_state")
	} else {
		current["status"] = "synchronized"
		current["observed_option_id"] = current["expected_remote_option_id"]
		delete(current, "desired_option_id")
		delete(current, "expected_remote_option_id")
	}
	delete(current, "intent_id")
	delete(current, "source_transition_id")
}

func optionalProviderFailure(err error) bool {
	switch fault.Code(err) {
	case "PROVIDER_UNCONFIGURED", "INVALID_PROVIDER_CONFIG", "PROVIDER_BINDING_CHANGED",
		"PROJECT_UNCONFIGURED", "INVALID_PROJECT_CONFIG", "PROJECT_BINDING_CHANGED":
		return true
	default:
		return false
	}
}

func (e *Engine) stageMappedIssue(next *model.Document, coordination object) error {
	ex := model.M(next.Data["execution"])
	current := model.M(ex["provider_effect"])
	_, _, generation, err := e.workProviderConfig()
	if err != nil && !optionalProviderFailure(err) {
		return err
	}
	if err != nil || generation != model.S(coordination["issue_generation"]) {
		coordination["issue_status"] = "binding_changed"
		return nil
	}
	if model.S(current["binding_generation"]) != generation ||
		model.I(current["remote_issue_number"]) < 1 || model.S(current["remote_issue_url"]) == "" {
		if model.S(current["kind"]) == "create_issue" && model.S(current["status"]) == "pending" {
			coordination["predecessor_issue_intent_id"] = current["intent_id"]
		}
		coordination["issue_status"] = "waiting_binding"
		return nil
	}
	switch model.S(current["status"]) {
	case "outcome_unknown":
		coordination["issue_status"] = "waiting_reconciliation"
		return nil
	case "pending":
		if model.S(current["source_transition_id"]) == "" || current["attempt_id"] != nil {
			coordination["issue_status"] = "waiting_manual"
			return nil
		}
		previous := model.M(ex["coordination"])
		if model.S(previous["transition_id"]) != model.S(current["source_transition_id"]) ||
			model.S(previous["mapping_generation"]) != model.S(coordination["mapping_generation"]) {
			coordination["issue_status"] = "binding_changed"
			return nil
		}
	case "synchronized":
		// The saved value may be stale. Stage a readback intent even when
		// the desired state matches the last recorded observation.
	case "conflict":
		coordination["issue_status"] = "waiting_manual"
		return nil
	default:
		coordination["issue_status"] = "waiting_binding"
		return nil
	}
	if model.S(current["remote_state"]) != "open" && model.S(current["remote_state"]) != "closed" {
		coordination["issue_status"] = "waiting_binding"
		return nil
	}
	intentID := mappedIntentID(model.S(coordination["transition_id"]), "issue_state")
	current["kind"], current["status"], current["attempt_id"] = "status_update", "pending", nil
	current["desired_state"], current["intent_id"] = coordination["desired_issue_state"], intentID
	current["source_transition_id"] = coordination["transition_id"]
	delete(current, "merge_pull_number")
	delete(current, "merge_commit_sha")
	coordination["issue_status"], coordination["issue_intent_id"] = "pending", intentID
	return nil
}

func (e *Engine) stageMappedProject(next *model.Document, coordination object) error {
	ex := model.M(next.Data["execution"])
	current := model.M(ex["project_effect"])
	issue := model.M(ex["provider_effect"])
	_, _, generation, err := e.workProjectConfig()
	if err != nil && !optionalProviderFailure(err) {
		return err
	}
	if err != nil || generation != model.S(coordination["project_generation"]) {
		coordination["project_status"] = "binding_changed"
		return nil
	}
	if model.S(current["binding_generation"]) != generation ||
		model.S(current["remote_item_id"]) == "" ||
		model.I(current["remote_issue_number"]) != model.I(issue["remote_issue_number"]) {
		coordination["project_status"] = "waiting_binding"
		return nil
	}
	switch model.S(current["status"]) {
	case "outcome_unknown":
		coordination["project_status"] = "waiting_reconciliation"
		return nil
	case "pending":
		if model.S(current["source_transition_id"]) == "" || current["attempt_id"] != nil {
			coordination["project_status"] = "waiting_manual"
			return nil
		}
		previous := model.M(ex["coordination"])
		if model.S(previous["transition_id"]) != model.S(current["source_transition_id"]) ||
			model.S(previous["mapping_generation"]) != model.S(coordination["mapping_generation"]) {
			coordination["project_status"] = "binding_changed"
			return nil
		}
	case "synchronized":
		if model.S(current["kind"]) != "set_single_select" ||
			model.S(current["field_id"]) != model.S(coordination["project_field_id"]) ||
			!hasObjectKey(current, "observed_option_id") {
			coordination["project_status"] = "awaiting_observation"
			return nil
		}
		// A matching saved option still needs a fresh explicit readback.
	case "conflict":
		coordination["project_status"] = "waiting_manual"
		return nil
	default:
		coordination["project_status"] = "waiting_binding"
		return nil
	}
	baseline, known := current["observed_option_id"]
	if model.S(current["kind"]) == "set_single_select" && model.S(current["status"]) == "pending" {
		baseline, known = current["expected_remote_option_id"]
	}
	if !known {
		coordination["project_status"] = "awaiting_observation"
		return nil
	}
	intentID := mappedIntentID(model.S(coordination["transition_id"]), "project_field")
	current["kind"], current["status"], current["attempt_id"] = "set_single_select", "pending", nil
	current["field_id"], current["desired_option_id"] = coordination["project_field_id"], coordination["desired_project_option_id"]
	current["expected_remote_option_id"] = baseline
	current["intent_id"], current["source_transition_id"] = intentID, coordination["transition_id"]
	delete(current, "observed_option_id")
	coordination["project_status"], coordination["project_intent_id"] = "pending", intentID
	return nil
}
