package operations

import (
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const workProviderPath = ".codearbiter/work/provider.json"

var workRepositoryPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$`)
var mergeCommitPattern = regexp.MustCompile(`^[a-f0-9]{40}$`)

// Provider configuration is portable, finite and separate from the four-key
// project identity. The credential reference names an owning-process secret;
// no secret value is stored here.
func (e *Engine) workProviderConfig() (object, []byte, string, error) {
	b, err := e.FS.Read(workProviderPath, 4096)
	if os.IsNotExist(err) {
		return nil, nil, "", fault.At("PROVIDER_UNCONFIGURED", "", workProviderPath, "no native work provider is configured")
	}
	if err != nil {
		return nil, nil, "", err
	}
	v, err := canonical.Object(b)
	if err != nil || len(v) != 7 || model.S(v["format"]) != "codearbiter.work-provider" ||
		model.I(v["version"]) != 1 || model.S(v["adapter"]) != "github" ||
		!projectIDPattern.MatchString(model.S(v["project_id"])) ||
		!workRepositoryPattern.MatchString(model.S(v["repository"])) ||
		!workCredentialReference(model.S(v["credential_ref"])) ||
		(model.S(v["effect_timing"]) != "after_merge" && model.S(v["effect_timing"]) != "immediate") {
		return nil, nil, "", fault.At("INVALID_PROVIDER_CONFIG", "", workProviderPath, "provider configuration is invalid; preserve it for inspection")
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, nil, "", err
	}
	if projectID == "" || model.S(v["project_id"]) != projectID {
		return nil, nil, "", fault.At("PROVIDER_BINDING_CHANGED", "", workProviderPath, "provider configuration belongs to a different project identity")
	}
	return v, b, canonical.BytesHash(b), nil
}

func workCredentialReference(value string) bool {
	switch value {
	case "GH_TOKEN", "GITHUB_TOKEN", "CODEARBITER_GITHUB_TOKEN":
		return true
	default:
		return false
	}
}

func (e *Engine) workProviderGet(_ object) (any, error) {
	config, _, generation, err := e.workProviderConfig()
	if err != nil {
		return nil, err
	}
	return object{"config_path": workProviderPath, "adapter": config["adapter"],
		"repository": config["repository"], "credential_ref": config["credential_ref"],
		"effect_timing": config["effect_timing"], "binding_generation": generation}, nil
}

func (e *Engine) workProviderConfigure(r object) (any, error) {
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	if projectID == "" {
		return nil, fault.At("NOT_FOUND", "", projectPath, "create a native work item before configuring a provider")
	}
	before, err := e.FS.Read(workProviderPath, 4096)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if os.IsNotExist(err) {
		before = nil
	}
	if before == nil && model.S(r["expected_config_sha256"]) != "" ||
		before != nil && model.S(r["expected_config_sha256"]) != canonical.BytesHash(before) {
		return nil, fault.At("REVISION_CONFLICT", "", workProviderPath, "provider configuration changed; refresh its identity before retrying")
	}
	after, err := canonical.Marshal(object{"format": "codearbiter.work-provider", "version": int64(1),
		"project_id": projectID, "adapter": "github", "repository": r["repository"],
		"credential_ref": r["credential_ref"], "effect_timing": r["effect_timing"]})
	if err != nil {
		return nil, err
	}
	result := object{"config_path": workProviderPath, "adapter": "github", "repository": r["repository"],
		"credential_ref": r["credential_ref"], "effect_timing": r["effect_timing"],
		"binding_generation": canonical.BytesHash(after)}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: workProviderPath, Before: before, After: after}}, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}

func workEffectExpected(r object, d *model.Document, p string) error {
	expected := model.M(r["expected"])
	if model.I(expected["revision"]) != d.Revision() || model.S(expected["model_sha256"]) != d.Hash() {
		return fault.At("REVISION_CONFLICT", d.ID(), p, "selected work changed; refresh its identity before retrying")
	}
	return nil
}

func (e *Engine) workEffectMutation(r object, action string) (any, error) {
	id := model.S(r["work_id"])
	d, before, p, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	config, _, generation, err := e.workProviderConfig()
	if err != nil {
		return nil, err
	}
	if model.S(r["binding_generation"]) != generation {
		return nil, fault.At("PROVIDER_BINDING_CHANGED", id, workProviderPath, "provider binding changed; refresh before an external effect")
	}
	if err := workEffectExpected(r, d, p); err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	ex := model.M(next.Data["execution"])
	current := model.M(ex["provider_effect"])
	switch action {
	case "adopt":
		if len(current) != 0 && (model.S(current["kind"]) != "create_issue" || model.S(current["status"]) != "pending") {
			return nil, fault.At("EFFECT_ALREADY_SENT", id, p, "an existing send or issue binding cannot be replaced by adoption")
		}
		number := model.I(r["remote_issue_number"])
		url := model.S(r["remote_issue_url"])
		want := fmt.Sprintf("https://github.com/%s/issues/%d", model.S(config["repository"]), number)
		if !strings.EqualFold(url, want) {
			return nil, fault.At("INVALID_REMOTE_BINDING", id, p, "remote issue URL does not match the configured GitHub repository and number")
		}
		ex["provider_effect"] = object{"kind": "create_issue", "status": "synchronized", "binding_generation": generation,
			"attempt_id": nil, "remote_issue_number": number, "remote_issue_url": url, "remote_state": r["remote_state"]}
	case "stage":
		kind := model.S(r["kind"])
		if kind == "" {
			kind = "create_issue"
		}
		if kind == "create_issue" {
			if r["desired_state"] != nil || len(current) != 0 && (model.S(current["kind"]) != "create_issue" || model.S(current["status"]) != "pending") {
				return nil, fault.At("EFFECT_ALREADY_SENT", id, p, "an existing issue binding cannot be replaced by another create")
			}
			ex["provider_effect"] = object{"kind": "create_issue", "status": "pending", "binding_generation": generation,
				"attempt_id": nil, "remote_issue_number": nil, "remote_issue_url": nil}
		} else {
			if model.S(r["desired_state"]) == "" ||
				(model.S(current["status"]) != "synchronized" && model.S(current["status"]) != "conflict" && model.S(current["status"]) != "pending") ||
				model.I(current["remote_issue_number"]) < 1 || model.S(current["remote_issue_url"]) == "" ||
				(model.S(current["remote_state"]) != "open" && model.S(current["remote_state"]) != "closed") {
				return nil, fault.At("EFFECT_NOT_BOUND", id, p, "status update requires a verified issue and remote state")
			}
			if model.S(current["binding_generation"]) != generation {
				return nil, fault.At("PROVIDER_BINDING_CHANGED", id, p, "issue binding belongs to an older provider configuration")
			}
			current["kind"], current["status"], current["attempt_id"] = "status_update", "pending", nil
			current["desired_state"] = r["desired_state"]
			delete(current, "merge_pull_number")
			delete(current, "merge_commit_sha")
		}
	case "claim":
		if model.S(config["effect_timing"]) == "after_merge" {
			if model.I(r["merge_pull_number"]) < 1 || !mergeCommitPattern.MatchString(model.S(r["merge_commit_sha"])) {
				return nil, fault.At("EFFECT_WAITING_FOR_MERGE", id, p, "merge-observed effects require a verified merged PR and commit")
			}
		} else if r["merge_pull_number"] != nil || r["merge_commit_sha"] != nil {
			return nil, fault.At("INVALID_MERGE_PROOF", id, p, "immediate effects cannot carry a merge observation")
		}
		if model.S(current["status"]) == "outcome_unknown" {
			return nil, fault.At("EFFECT_UNKNOWN", id, p, "a prior send may have succeeded; reconcile its remote outcome before retrying")
		}
		if model.S(current["status"]) != "pending" {
			return nil, fault.At("EFFECT_NOT_PENDING", id, p, "no pending provider effect can be claimed")
		}
		if model.S(current["binding_generation"]) != generation {
			return nil, fault.At("PROVIDER_BINDING_CHANGED", id, p, "pending effect belongs to an older provider binding")
		}
		current["status"], current["attempt_id"] = "outcome_unknown", r["attempt_id"]
		if model.S(config["effect_timing"]) == "after_merge" {
			current["merge_pull_number"], current["merge_commit_sha"] = r["merge_pull_number"], r["merge_commit_sha"]
		}
	case "record":
		if model.S(current["status"]) != "outcome_unknown" || model.S(current["attempt_id"]) != model.S(r["attempt_id"]) {
			return nil, fault.At("EFFECT_CLAIM_CHANGED", id, p, "provider result does not match the selected pre-send claim")
		}
		if model.S(current["binding_generation"]) != generation {
			return nil, fault.At("PROVIDER_BINDING_CHANGED", id, p, "provider binding changed before result recording")
		}
		number := model.I(r["remote_issue_number"])
		url := model.S(r["remote_issue_url"])
		want := fmt.Sprintf("https://github.com/%s/issues/%d", model.S(config["repository"]), number)
		if !strings.EqualFold(url, want) {
			return nil, fault.At("INVALID_REMOTE_BINDING", id, p, "remote issue URL does not match the configured GitHub repository and number")
		}
		if model.S(current["kind"]) == "status_update" {
			if number != model.I(current["remote_issue_number"]) || !strings.EqualFold(url, model.S(current["remote_issue_url"])) || model.S(r["remote_state"]) != model.S(current["desired_state"]) {
				return nil, fault.At("INVALID_REMOTE_BINDING", id, p, "status readback does not match the bound issue and desired state")
			}
		}
		current["status"], current["remote_issue_number"], current["remote_issue_url"] = "synchronized", number, url
		if r["remote_state"] != nil {
			current["remote_state"] = r["remote_state"]
		}
	case "conflict":
		status := model.S(current["status"])
		if model.S(current["kind"]) != "status_update" || (status != "pending" && status != "outcome_unknown") {
			return nil, fault.At("EFFECT_NOT_PENDING", id, p, "no remote status conflict is available to record")
		}
		if status == "outcome_unknown" {
			if model.S(r["attempt_id"]) != model.S(current["attempt_id"]) {
				return nil, fault.At("EFFECT_CLAIM_CHANGED", id, p, "uncertain status resolution does not match the selected send attempt")
			}
			if model.S(r["remote_state"]) == model.S(current["desired_state"]) {
				return nil, fault.At("INVALID_REMOTE_BINDING", id, p, "matching status must be recorded as a verified result, not a conflict")
			}
		} else if r["attempt_id"] != nil || model.S(current["remote_state"]) == model.S(r["remote_state"]) {
			return nil, fault.At("EFFECT_NOT_PENDING", id, p, "pre-send remote status has not changed")
		}
		current["status"], current["remote_state"] = "conflict", r["remote_state"]
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
	result := workSummary(next, p)
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: p, Before: before, After: after}}, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}
