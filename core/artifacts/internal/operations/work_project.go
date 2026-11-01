package operations

import (
	"os"
	"regexp"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const workProjectPath = ".codearbiter/work/project-provider.json"

var projectNodePattern = regexp.MustCompile(`^[A-Za-z0-9_+/=-]{8,256}$`)
var projectItemPattern = projectNodePattern
var projectFieldPattern = projectNodePattern
var projectOptionPattern = regexp.MustCompile(`^[A-Za-z0-9_+/=-]{1,128}$`)
var projectDigestPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

// Projects have a separate generation: configuring an optional board must not
// invalidate the existing issue binding or a pending issue send.
func (e *Engine) workProjectConfig() (object, []byte, string, error) {
	issue, _, issueGeneration, err := e.workProviderConfig()
	if err != nil {
		return nil, nil, "", err
	}
	b, err := e.FS.Read(workProjectPath, 4096)
	if os.IsNotExist(err) {
		return nil, nil, "", fault.At("PROJECT_UNCONFIGURED", "", workProjectPath, "no GitHub Project is configured")
	}
	if err != nil {
		return nil, nil, "", err
	}
	v, err := canonical.Object(b)
	if err != nil || len(v) != 7 || model.S(v["format"]) != "codearbiter.work-project-provider" ||
		model.I(v["version"]) != 1 || model.S(v["adapter"]) != "github" ||
		!projectIDPattern.MatchString(model.S(v["project_id"])) ||
		!workRepositoryPattern.MatchString(model.S(v["repository"])) ||
		!projectNodePattern.MatchString(model.S(v["project_node_id"])) ||
		!projectDigestPattern.MatchString(model.S(v["issue_generation"])) {
		return nil, nil, "", fault.At("INVALID_PROJECT_CONFIG", "", workProjectPath, "Project configuration is invalid; preserve it for inspection")
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, nil, "", err
	}
	if model.S(v["project_id"]) != projectID ||
		model.S(v["issue_generation"]) != issueGeneration ||
		model.S(v["repository"]) != model.S(issue["repository"]) {
		return nil, nil, "", fault.At("PROJECT_BINDING_CHANGED", "", workProjectPath, "Project binding differs from the selected issue provider")
	}
	return v, b, canonical.BytesHash(b), nil
}

func (e *Engine) workProjectGet(_ object) (any, error) {
	config, _, generation, err := e.workProjectConfig()
	if err != nil {
		return nil, err
	}
	issue, _, _, err := e.workProviderConfig()
	if err != nil {
		return nil, err
	}
	return object{"config_path": workProjectPath, "repository": config["repository"],
		"project_node_id": config["project_node_id"], "binding_generation": generation,
		"credential_ref": issue["credential_ref"]}, nil
}

func (e *Engine) workProjectConfigure(r object) (any, error) {
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	issue, _, issueGeneration, err := e.workProviderConfig()
	if err != nil {
		return nil, err
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	before, err := e.FS.Read(workProjectPath, 4096)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if os.IsNotExist(err) {
		before = nil
	}
	if before == nil && model.S(r["expected_config_sha256"]) != "" ||
		before != nil && model.S(r["expected_config_sha256"]) != canonical.BytesHash(before) {
		return nil, fault.At("REVISION_CONFLICT", "", workProjectPath, "Project configuration changed; refresh before retrying")
	}
	after, err := canonical.Marshal(object{"format": "codearbiter.work-project-provider", "version": int64(1),
		"adapter": "github", "project_id": projectID, "repository": issue["repository"],
		"issue_generation": issueGeneration, "project_node_id": r["project_node_id"]})
	if err != nil {
		return nil, err
	}
	result := object{"config_path": workProjectPath, "repository": issue["repository"],
		"project_node_id": r["project_node_id"], "binding_generation": canonical.BytesHash(after),
		"credential_ref": issue["credential_ref"]}
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash,
		[]store.Edit{{Path: workProjectPath, Before: before, After: after}}, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}

func (e *Engine) workProjectMutation(r object, action string) (any, error) {
	id := model.S(r["work_id"])
	d, before, path, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	config, _, generation, err := e.workProjectConfig()
	if err != nil {
		return nil, err
	}
	if model.S(r["binding_generation"]) != generation {
		return nil, fault.At("PROJECT_BINDING_CHANGED", id, workProjectPath, "Project binding changed; refresh before an external effect")
	}
	if err := workEffectExpected(r, d, path); err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	ex := model.M(next.Data["execution"])
	issue := model.M(ex["provider_effect"])
	if model.S(issue["binding_generation"]) != model.S(config["issue_generation"]) ||
		model.I(issue["remote_issue_number"]) < 1 ||
		model.S(issue["remote_issue_url"]) == "" {
		return nil, fault.At("EFFECT_NOT_BOUND", id, path, "Project effect requires a verified issue binding")
	}
	current := model.M(ex["project_effect"])
	switch action {
	case "stage":
		if model.S(issue["status"]) != "synchronized" {
			return nil, fault.At("EFFECT_NOT_BOUND", id, path, "Project attachment requires a synchronized issue")
		}
		if len(current) != 0 {
			return nil, fault.At("EFFECT_ALREADY_SENT", id, path, "existing Project item intent or binding cannot be replaced")
		}
		ex["project_effect"] = object{"kind": "add_item", "status": "pending", "binding_generation": generation,
			"attempt_id": nil, "remote_issue_number": issue["remote_issue_number"], "remote_item_id": nil}
	case "stage-field":
		unsentMapped := model.S(current["status"]) == "pending" &&
			model.S(current["source_transition_id"]) != "" && current["attempt_id"] == nil
		if !projectItemPattern.MatchString(model.S(current["remote_item_id"])) ||
			(model.S(current["status"]) != "synchronized" && model.S(current["status"]) != "conflict" && !unsentMapped) ||
			model.S(current["binding_generation"]) != generation ||
			model.I(current["remote_issue_number"]) != model.I(issue["remote_issue_number"]) ||
			!projectFieldPattern.MatchString(model.S(r["field_id"])) ||
			!projectOptionPattern.MatchString(model.S(r["desired_option_id"])) {
			return nil, fault.At("EFFECT_NOT_BOUND", id, path, "field update requires a synchronized item in this Project")
		}
		oldMappedIntent := model.S(current["intent_id"])
		current["kind"], current["status"], current["attempt_id"] = "set_single_select", "pending", nil
		current["field_id"], current["desired_option_id"] = r["field_id"], r["desired_option_id"]
		current["expected_remote_option_id"] = r["expected_remote_option_id"]
		if current["source_transition_id"] != nil {
			delete(current, "source_transition_id")
			delete(current, "intent_id")
			if coordination := model.M(ex["coordination"]); len(coordination) != 0 {
				coordination["project_status"], coordination["project_intent_id"] = "waiting_manual", nil
				coordination["superseded_project_intent_id"] = oldMappedIntent
			}
		}
		delete(current, "observed_option_id")
	case "claim":
		if model.S(current["status"]) == "outcome_unknown" {
			return nil, fault.At("EFFECT_UNKNOWN", id, path, "a Project send may have succeeded; reconcile before retrying")
		}
		if model.S(current["status"]) != "pending" {
			return nil, fault.At("EFFECT_NOT_PENDING", id, path, "no pending Project effect can be claimed")
		}
		if err := e.checkMappedClaim(ex, current, "project_field"); err != nil {
			return nil, err
		}
		if current["source_transition_id"] != nil {
			issueConfig, _, _, err := e.workProviderConfig()
			if err != nil {
				return nil, err
			}
			if model.S(issueConfig["effect_timing"]) == "after_merge" {
				if model.I(r["merge_pull_number"]) < 1 || !mergeCommitPattern.MatchString(model.S(r["merge_commit_sha"])) {
					return nil, fault.At("EFFECT_WAITING_FOR_MERGE", id, path, "mapped Project effect requires a verified merged PR")
				}
				current["merge_pull_number"], current["merge_commit_sha"] = r["merge_pull_number"], r["merge_commit_sha"]
			} else if r["merge_pull_number"] != nil || r["merge_commit_sha"] != nil {
				return nil, fault.At("INVALID_MERGE_PROOF", id, path, "immediate mapped effect cannot carry merge proof")
			}
		}
		if model.S(current["binding_generation"]) != generation ||
			model.I(current["remote_issue_number"]) != model.I(issue["remote_issue_number"]) {
			return nil, fault.At("PROJECT_BINDING_CHANGED", id, path, "pending Project item belongs to another binding")
		}
		current["status"], current["attempt_id"] = "outcome_unknown", r["attempt_id"]
		if coordination := model.M(ex["coordination"]); model.S(coordination["transition_id"]) == model.S(current["source_transition_id"]) &&
			model.S(current["source_transition_id"]) != "" {
			coordination["project_status"] = "waiting_reconciliation"
		}
	case "record":
		if model.S(current["status"]) != "outcome_unknown" ||
			model.S(current["attempt_id"]) != model.S(r["attempt_id"]) {
			return nil, fault.At("EFFECT_CLAIM_CHANGED", id, path, "Project result does not match the pre-send claim")
		}
		if model.S(current["binding_generation"]) != generation ||
			model.I(current["remote_issue_number"]) != model.I(issue["remote_issue_number"]) ||
			!projectItemPattern.MatchString(model.S(r["remote_item_id"])) {
			return nil, fault.At("PROJECT_BINDING_CHANGED", id, path, "Project readback does not match the selected issue and item")
		}
		if model.S(current["kind"]) == "set_single_select" {
			if model.S(r["remote_item_id"]) != model.S(current["remote_item_id"]) ||
				model.S(r["observed_option_id"]) != model.S(current["desired_option_id"]) {
				return nil, fault.At("INVALID_REMOTE_BINDING", id, path, "field readback differs from the selected item and desired option")
			}
			current["observed_option_id"] = r["observed_option_id"]
		} else {
			current["remote_item_id"] = r["remote_item_id"]
		}
		current["status"] = "synchronized"
		if coordination := model.M(ex["coordination"]); model.S(coordination["transition_id"]) == model.S(current["source_transition_id"]) &&
			model.S(current["source_transition_id"]) != "" {
			coordination["project_status"] = "synchronized"
		}
	case "conflict":
		if model.S(current["kind"]) != "set_single_select" ||
			(model.S(current["status"]) != "pending" && model.S(current["status"]) != "outcome_unknown") {
			return nil, fault.At("EFFECT_NOT_PENDING", id, path, "no selected field update can be marked conflicted")
		}
		if model.S(current["status"]) == "outcome_unknown" &&
			model.S(current["attempt_id"]) != model.S(r["attempt_id"]) {
			return nil, fault.At("EFFECT_CLAIM_CHANGED", id, path, "field conflict does not match the selected send")
		}
		if model.S(current["status"]) == "pending" && r["attempt_id"] != nil {
			return nil, fault.At("EFFECT_NOT_PENDING", id, path, "unsent field conflict has no send attempt")
		}
		if r["observed_option_id"] == current["expected_remote_option_id"] ||
			model.S(r["observed_option_id"]) == model.S(current["desired_option_id"]) {
			return nil, fault.At("INVALID_REMOTE_BINDING", id, path, "matching field value is not a conflict")
		}
		current["status"], current["observed_option_id"] = "conflict", r["observed_option_id"]
		if coordination := model.M(ex["coordination"]); model.S(coordination["transition_id"]) == model.S(current["source_transition_id"]) &&
			model.S(current["source_transition_id"]) != "" {
			coordination["project_status"] = "waiting_manual"
		}
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
