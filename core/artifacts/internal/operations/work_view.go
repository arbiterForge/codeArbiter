package operations

import (
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

func workViewAttachment(value any, kind string) (*render.WorkViewAttachment, error) {
	if value == nil {
		return nil, nil
	}
	item := model.M(value)
	p := model.S(item["path"])
	if !strings.HasPrefix(p, ".codearbiter/"+kind+"s/") || !strings.HasSuffix(p, ".html") {
		return nil, fault.New("INVALID_BINDING", "selected work attachment has no safe view link")
	}
	return &render.WorkViewAttachment{
		ID: model.S(item["artifact_id"]), Title: model.S(item["title"]),
		Summary: model.S(item["summary"]), Href: "../../" + strings.TrimPrefix(p, ".codearbiter/"),
	}, nil
}

// workView is a read-only generated page. It reuses the selected work-context
// path, including exact companion validation, and never writes a second owner.
func (e *Engine) workView(r object) (any, error) {
	selected, err := e.workContext(object{"work_id": r["work_id"], "budget": int64(16384)})
	if err != nil {
		return nil, err
	}
	context, ok := selected.(object)
	if !ok {
		return nil, fault.New("INVALID_RESPONSE", "selected work context is invalid")
	}
	work := model.M(context["work"])
	spec, err := workViewAttachment(context["spec"], "spec")
	if err != nil {
		return nil, err
	}
	plan, err := workViewAttachment(context["plan"], "plan")
	if err != nil {
		return nil, err
	}
	data := render.WorkViewData{
		ID: model.S(work["work_id"]), ProjectID: model.S(work["project_id"]), CycleID: model.S(work["cycle_id"]),
		Title: model.S(work["title"]), Intent: model.S(work["intent"]),
		WorkType: model.S(work["work_type"]), State: model.S(work["state"]),
		CheckStatus: model.S(work["check_status"]), StartedAt: model.S(work["started_at"]),
		CompletedAt: model.S(work["completed_at"]), Revision: model.I(work["revision"]),
		ModelSHA256: model.S(work["model_sha256"]), Spec: spec, Plan: plan,
	}
	if detail := model.M(context["legacy_detail"]); len(detail) != 0 {
		data.LegacyDetail = model.S(detail["text"])
		data.LegacyMore = detail["next_offset"] != nil
	}
	if selected := model.M(context["plan_task"]); len(selected) != 0 {
		data.PlanTask = &render.WorkViewTask{ID: model.S(selected["id"]), Title: model.S(selected["title"]),
			State: model.S(selected["state"]), NextAction: model.S(selected["next_action"]),
			BindingCurrent: selected["binding_current"] == true}
		if report := model.M(selected["last_reported_check"]); len(report) != 0 {
			data.PlanTask.ReportedOutcome = model.S(report["reported_outcome"])
			data.PlanTask.ReportedFreshness = model.S(report["worktree_freshness"])
		}
	}
	if effect := model.M(work["provider_effect"]); len(effect) != 0 {
		data.ProviderEffectKind = model.S(effect["kind"])
		data.ProviderEffectStatus = model.S(effect["status"])
		data.RemoteIssueURL = model.S(effect["remote_issue_url"])
		data.RemoteState = model.S(effect["remote_state"])
		data.DesiredState = model.S(effect["desired_state"])
	}
	if effect := model.M(work["project_effect"]); len(effect) != 0 {
		data.ProjectEffectKind = model.S(effect["kind"])
		data.ProjectEffectStatus = model.S(effect["status"])
	}
	if coordination := model.M(work["coordination"]); len(coordination) != 0 {
		data.CoordinationAction = model.S(coordination["action"])
		data.CoordinationIssueStatus = model.S(coordination["issue_status"])
		data.CoordinationProjectStatus = model.S(coordination["project_status"])
		data.CoordinationReason = model.S(coordination["reason"])
		data.CoordinationSendStatus = model.S(coordination["send_status"])
	}
	if delivery := model.M(work["delivery_observation"]); len(delivery) != 0 {
		data.DeliveryState = model.S(delivery["state"])
		data.DeliveryURL = model.S(delivery["pull_url"])
		data.DeliveryObservedAt = model.S(delivery["observed_at"])
	}
	html, err := render.WorkView(data)
	if err != nil {
		return nil, err
	}
	return object{"format": "codearbiter.work-view/0.1.0", "canonical": false,
		"work_id": data.ID, "revision": data.Revision, "model_sha256": data.ModelSHA256,
		"view_path": ".codearbiter/views/work/" + data.ID + ".html",
		"html":      string(html)}, nil
}
