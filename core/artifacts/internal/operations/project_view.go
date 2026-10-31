package operations

import (
	"os"
	"strconv"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

const projectCodeMapPath = ".codearbiter/context/code-map.html"

// projectArchitecture reads only the existing code-map owner. A missing or
// malformed page is described in the view without concealing selected work.
func (e *Engine) projectArchitecture() ([]render.ProjectArchitectureEntry, int64, string, error) {
	b, err := e.FS.Read(projectCodeMapPath, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, 0, "unrecorded", nil
	}
	if err != nil {
		return nil, 0, "", err
	}
	d, err := render.Parse(b)
	if err != nil || d.Kind() != "knowledge" || d.ID() != "CTX-CODE-MAP" || model.S(d.Data["slug"]) != "code-map" {
		return nil, 0, "unavailable", nil
	}
	entries := []render.ProjectArchitectureEntry{}
	omitted := int64(0)
	for _, value := range model.A(d.Norm()["records"]) {
		record := model.M(value)
		typ := model.S(record["type"])
		if typ != "component" && typ != "interface" {
			continue
		}
		if len(entries) == 4 {
			omitted++
			continue
		}
		entries = append(entries, render.ProjectArchitectureEntry{
			Title: model.S(record["title"]), Statement: boundedText(model.S(record["statement"]), 240),
			Kind: typ, Basis: model.S(record["basis"]),
		})
	}
	return entries, omitted, "recorded", nil
}

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
	data.Architecture, data.ArchitectureOmitted, data.ArchitectureState, err = e.projectArchitecture()
	if err != nil {
		return nil, err
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
			WorkType: model.S(item["work_type"]), CycleID: model.S(item["cycle_id"]), State: model.S(item["state"]),
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
		"content_snapshot":     false,
		"architecture_omitted": data.ArchitectureOmitted,
		"architecture_state":   data.ArchitectureState,
		"view_path":            ".codearbiter/views/project/" + id + "-" + strconv.FormatInt(data.Offset, 10) + ".html",
		"html":                 string(html),
	}, nil
}
