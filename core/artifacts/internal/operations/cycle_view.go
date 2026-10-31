package operations

import (
	"os"
	"sort"
	"strconv"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// cycleView derives membership from canonical work references. There is no
// second writable cycle backlog or copied task state.
func (e *Engine) cycleView(r object) (any, error) {
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	if projectID == "" {
		return nil, fault.New("NOT_FOUND", "native project identity is absent")
	}
	entries, err := e.FS.List(".codearbiter/work")
	if os.IsNotExist(err) {
		return nil, fault.New("NOT_FOUND", "no work references the selected cycle")
	}
	if err != nil {
		return nil, err
	}
	if len(entries) > 20000 {
		return nil, fault.New("WORK_SCAN_LIMIT", "work directory exceeds bounded cycle listing")
	}
	cycleID := model.S(r["cycle_id"])
	ids := make([]string, 0)
	states := map[string]int64{}
	checks := map[string]int64{}
	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".html") {
			continue
		}
		id := strings.TrimSuffix(name, ".html")
		if !workIDPattern.MatchString(id) || entry.IsDir() {
			return nil, fault.At("INVALID_WORK", "", ".codearbiter/work/"+name, "work directory contains an invalid HTML entry")
		}
		d, _, _, err := e.readWorkWithProject(id, projectID)
		if err != nil {
			return nil, err
		}
		if model.S(d.Norm()["cycle_id"]) != cycleID {
			continue
		}
		ids = append(ids, id)
		ex := model.M(d.Data["execution"])
		states[model.S(ex["state"])]++
		checks[model.S(ex["check_status"])]++
	}
	if len(ids) == 0 {
		return nil, fault.New("NOT_FOUND", "no work references the selected cycle")
	}
	sort.Strings(ids)
	digest, err := canonical.Hash(model.List(ids...))
	if err != nil {
		return nil, err
	}
	offset, ok := model.NativeInt(model.I(r["offset"]))
	if !ok || offset < 0 || offset > len(ids) {
		return nil, fault.New("INVALID_OFFSET", "cycle offset is outside the current listing")
	}
	if offset > 0 && model.S(r["membership_sha256"]) != digest {
		return nil, fault.New("STALE_CURSOR", "cycle membership changed during listing")
	}
	limit := 16
	if n := model.I(r["limit"]); n != 0 {
		if n < 1 || n > 16 {
			return nil, fault.New("INVALID_LIMIT", "cycle page limit must be 1..16")
		}
		limit = int(n)
	}
	end := offset + limit
	if end > len(ids) {
		end = len(ids)
	}
	data := render.CycleViewData{ProjectID: projectID, CycleID: cycleID, Offset: int64(offset), Total: int64(len(ids)), MembershipSHA256: digest,
		Queued: states["queued"], Active: states["active"], Complete: states["complete"], Archived: states["archived"],
		UnknownChecks: checks["unknown"], PassedChecks: checks["passed"], FailedChecks: checks["failed"]}
	for _, id := range ids[offset:end] {
		d, _, _, err := e.readWorkWithProject(id, projectID)
		if err != nil {
			return nil, err
		}
		if model.S(d.Norm()["cycle_id"]) != cycleID {
			return nil, fault.New("STALE_CURSOR", "cycle membership changed during listing")
		}
		ex := model.M(d.Data["execution"])
		data.Entries = append(data.Entries, render.ProjectViewEntry{ID: id, Title: model.S(d.Norm()["title"]), WorkType: model.S(d.Norm()["work_type"]),
			State: model.S(ex["state"]), CheckStatus: model.S(ex["check_status"]), Href: "../../work/" + id + ".html"})
	}
	var next any
	if end < len(ids) {
		next = int64(end)
		value := int64(end)
		data.NextOffset = &value
	}
	html, err := render.CycleView(data)
	if err != nil {
		return nil, err
	}
	return object{"format": "codearbiter.cycle-view/0.1.0", "canonical": false, "content_snapshot": false,
		"project_id": projectID, "cycle_id": cycleID, "offset": int64(offset), "total": int64(len(ids)), "next_offset": next,
		"membership_sha256": digest, "progress": object{"queued": data.Queued, "active": data.Active, "complete": data.Complete, "archived": data.Archived},
		"checks":    object{"unknown": data.UnknownChecks, "passed": data.PassedChecks, "failed": data.FailedChecks},
		"view_path": ".codearbiter/views/cycle/" + cycleID + "-" + strconv.Itoa(offset) + ".html", "html": string(html)}, nil
}
