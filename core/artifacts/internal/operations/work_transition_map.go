package operations

import (
	"os"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const workTransitionMapPath = ".codearbiter/work/transition-map.json"
const workTransitionMapLimit = 16 << 10

func validTransitionTargets(actions object, project bool) bool {
	if len(actions) != 3 {
		return false
	}
	for _, action := range []string{"start", "complete", "reopen"} {
		target := model.M(actions[action])
		if len(target) != 2 || !hasObjectKey(target, "issue_state") || !hasObjectKey(target, "project_option_id") {
			return false
		}
		if target["issue_state"] != nil && model.S(target["issue_state"]) != "open" && model.S(target["issue_state"]) != "closed" {
			return false
		}
		if target["project_option_id"] != nil && (!project || !projectOptionPattern.MatchString(model.S(target["project_option_id"]))) {
			return false
		}
	}
	return true
}

func hasObjectKey(v object, key string) bool {
	_, ok := v[key]
	return ok
}

func (e *Engine) workTransitionMapConfig() (object, []byte, string, error) {
	b, err := e.FS.Read(workTransitionMapPath, workTransitionMapLimit+1)
	if err != nil {
		if fault.Code(err) == "MAX_BYTES" {
			return nil, nil, "", fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map exceeds 16 KiB")
		}
		return nil, nil, "", err
	}
	if len(b) > workTransitionMapLimit {
		return nil, nil, "", fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map exceeds 16 KiB")
	}
	v, err := canonical.Object(b)
	if err != nil || len(v) != 8 || !hasObjectKey(v, "format") || !hasObjectKey(v, "version") ||
		!hasObjectKey(v, "enabled") || !hasObjectKey(v, "project_id") || !hasObjectKey(v, "issue_generation") ||
		!hasObjectKey(v, "project_generation") || !hasObjectKey(v, "project_field_id") || !hasObjectKey(v, "actions") ||
		model.S(v["format"]) != "codearbiter.work-transition-map" ||
		model.I(v["version"]) != 1 || !projectIDPattern.MatchString(model.S(v["project_id"])) ||
		!projectDigestPattern.MatchString(model.S(v["issue_generation"])) {
		return nil, nil, "", fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map is invalid; preserve it for inspection")
	}
	if _, ok := v["enabled"].(bool); !ok {
		return nil, nil, "", fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map enabled flag is invalid")
	}
	projectGeneration, hasProject := v["project_generation"].(string)
	fieldID, hasField := v["project_field_id"].(string)
	if (v["project_generation"] != nil && !hasProject) ||
		(v["project_field_id"] != nil && !hasField) ||
		(hasProject && !projectDigestPattern.MatchString(projectGeneration)) ||
		(hasField && !projectFieldPattern.MatchString(fieldID)) || hasProject != hasField ||
		!validTransitionTargets(model.M(v["actions"]), hasProject) {
		return nil, nil, "", fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map targets are invalid")
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, nil, "", err
	}
	if model.S(v["project_id"]) != projectID {
		return nil, nil, "", fault.At("TRANSITION_MAP_BINDING_CHANGED", "", workTransitionMapPath, "transition map belongs to a different project")
	}
	return v, b, canonical.BytesHash(b), nil
}

func (e *Engine) workTransitionMapGet(_ object) (any, error) {
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	v, _, generation, err := e.workTransitionMapConfig()
	if os.IsNotExist(err) {
		return object{"configured": false, "enabled": false}, nil
	}
	if err != nil {
		return nil, err
	}
	return object{"configured": true, "enabled": v["enabled"], "project_id": v["project_id"],
		"issue_generation": v["issue_generation"], "project_generation": v["project_generation"],
		"project_field_id": v["project_field_id"], "actions": v["actions"], "binding_generation": generation}, nil
}

func (e *Engine) workTransitionMapConfigure(r object) (any, error) {
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	if projectID == "" {
		return nil, fault.At("NOT_FOUND", "", projectPath, "create native work before configuring transition mapping")
	}
	before, err := e.FS.Read(workTransitionMapPath, 1<<20)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if os.IsNotExist(err) {
		before = nil
	}
	if before == nil && model.S(r["expected_config_sha256"]) != "" ||
		before != nil && model.S(r["expected_config_sha256"]) != canonical.BytesHash(before) {
		return nil, fault.At("REVISION_CONFLICT", "", workTransitionMapPath, "transition map changed; refresh its identity before retrying")
	}
	projectGeneration, hasProject := r["project_generation"].(string)
	fieldID, hasField := r["project_field_id"].(string)
	if hasProject != hasField || !validTransitionTargets(model.M(r["actions"]), hasProject) {
		return nil, fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map targets require one bound Project field")
	}
	if enabled, _ := r["enabled"].(bool); enabled {
		_, _, issueGeneration, err := e.workProviderConfig()
		if err != nil {
			return nil, err
		}
		if model.S(r["issue_generation"]) != issueGeneration {
			return nil, fault.At("PROVIDER_BINDING_CHANGED", "", workTransitionMapPath, "transition map issue generation differs from the provider")
		}
		if hasProject {
			_, _, actual, err := e.workProjectConfig()
			if err != nil {
				return nil, err
			}
			if projectGeneration != actual || !projectFieldPattern.MatchString(fieldID) {
				return nil, fault.At("PROJECT_BINDING_CHANGED", "", workTransitionMapPath, "transition map Project generation differs from the bound Project")
			}
		}
	}
	after, err := canonical.Marshal(object{"format": "codearbiter.work-transition-map", "version": int64(1),
		"enabled": r["enabled"], "project_id": projectID, "issue_generation": r["issue_generation"],
		"project_generation": r["project_generation"], "project_field_id": r["project_field_id"], "actions": r["actions"]})
	if err != nil {
		return nil, err
	}
	if len(after) > workTransitionMapLimit {
		return nil, fault.At("INVALID_TRANSITION_MAP", "", workTransitionMapPath, "transition map exceeds 16 KiB")
	}
	result := object{"configured": true, "enabled": r["enabled"], "project_id": projectID,
		"issue_generation": r["issue_generation"], "project_generation": r["project_generation"],
		"project_field_id": r["project_field_id"], "actions": r["actions"], "binding_generation": canonical.BytesHash(after)}
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash,
		[]store.Edit{{Path: workTransitionMapPath, Before: before, After: after}}, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}
