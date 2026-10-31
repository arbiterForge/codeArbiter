package operations

import (
	"strconv"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// projectView reuses the selected work listing's membership and page bounds.
// It writes no generated file and does not inspect unrelated artifact kinds.
func (e *Engine) projectView(r object) (any, error) {
	if model.I(r["limit"]) == 0 {
		r["limit"] = int64(16)
	}
	value, err := e.workList(r)
	if err != nil {
		return nil, err
	}
	page := model.M(value)
	id := model.S(page["project_id"])
	if id == "" {
		return nil, fault.New("NOT_FOUND", "native project identity is absent")
	}
	data := render.ProjectViewData{
		ID: id, Offset: model.I(page["offset"]), Total: model.I(page["total"]),
		MembershipSHA256: model.S(page["membership_sha256"]),
		Entries:          make([]render.ProjectViewEntry, 0, len(model.A(page["entries"]))),
	}
	if page["next_offset"] != nil {
		next := model.I(page["next_offset"])
		data.NextOffset = &next
	}
	for _, value := range model.A(page["entries"]) {
		item := model.M(value)
		workID := model.S(item["work_id"])
		data.Entries = append(data.Entries, render.ProjectViewEntry{
			ID: workID, Title: model.S(item["title"]),
			WorkType: model.S(item["work_type"]), State: model.S(item["state"]),
			CheckStatus: model.S(item["check_status"]),
			Href:        "../../work/" + workID + ".html",
		})
	}
	html, err := render.ProjectView(data)
	if err != nil {
		return nil, err
	}
	return object{
		"format": "codearbiter.project-view/0.1.0", "canonical": false,
		"project_id": id, "offset": data.Offset, "total": data.Total,
		"next_offset": page["next_offset"], "membership_sha256": page["membership_sha256"],
		"content_snapshot": false,
		"view_path":        ".codearbiter/views/project/" + id + "-" + strconv.FormatInt(data.Offset, 10) + ".html",
		"html":             string(html),
	}, nil
}
