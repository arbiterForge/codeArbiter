package operations

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const projectPath = ".codearbiter/work/project.json"

var workIDPattern = regexp.MustCompile(`^WORK-[A-F0-9]{32}$`)
var projectIDPattern = regexp.MustCompile(`^PROJECT-[A-F0-9]{32}$`)

func newOpaqueID(prefix string) (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fault.New("ID_UNAVAILABLE", "could not create a stable identity")
	}
	return prefix + strings.ToUpper(hex.EncodeToString(b[:])), nil
}

func workPath(id string) string { return ".codearbiter/work/" + id + ".html" }

// Origin is a promotion correlation key, never a title lookup. It is checked
// across active and archived work so a retried promotion cannot create a twin.
func (e *Engine) workByOrigin(origin, projectID string) (*model.Document, string, error) {
	if origin == "" {
		return nil, "", nil
	}
	entries, err := e.FS.List(".codearbiter/work")
	if os.IsNotExist(err) {
		return nil, "", nil
	}
	if err != nil {
		return nil, "", err
	}
	if len(entries) > 20000 {
		return nil, "", fault.New("WORK_SCAN_LIMIT", "origin deduplication requires a bounded work directory")
	}
	var found *model.Document
	var path string
	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".html") {
			continue
		}
		id := strings.TrimSuffix(name, ".html")
		if !workIDPattern.MatchString(id) || entry.IsDir() {
			return nil, "", fault.At("INVALID_WORK", "", ".codearbiter/work/"+name, "work directory contains an invalid HTML entry")
		}
		d, _, p, err := e.readWorkWithProject(id, projectID)
		if err != nil {
			return nil, "", err
		}
		if model.S(d.Norm()["origin"]) == origin {
			if found != nil {
				return nil, "", fault.New("ORIGIN_CONFLICT", "more than one work item claims the same origin")
			}
			found, path = d, p
		}
	}
	return found, path, nil
}

// projectIdentity is portable state. The local journal alone cannot identify
// the project after a fresh clone or a different worktree is opened.
func (e *Engine) projectIdentity() (string, []byte, error) {
	b, err := e.FS.Read(projectPath, 4096)
	if os.IsNotExist(err) {
		return "", nil, nil
	}
	if err != nil {
		return "", nil, err
	}
	v, err := canonical.Object(b)
	if err != nil || len(v) != 4 || model.S(v["format"]) != "codearbiter.project" || model.I(v["version"]) != 1 || model.S(v["owner"]) != "native" || !projectIDPattern.MatchString(model.S(v["project_id"])) {
		return "", nil, fault.At("INVALID_PROJECT", "", projectPath, "portable project identity is invalid; preserve it for inspection")
	}
	return model.S(v["project_id"]), b, nil
}

func (e *Engine) refuseLegacyWorkOwner() error {
	const board = ".codearbiter/open-tasks.md"
	if _, err := e.FS.Read(board, canonical.MaxBytes); err == nil {
		return fault.At("LEGACY_CONFLICT", "", board, "legacy task board is the work owner; select an adoption before native work mutation")
	} else if !os.IsNotExist(err) {
		return err
	}
	return nil
}

func (e *Engine) workCreate(r object) (any, error) {
	projectID, projectBefore, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	projectAfter := projectBefore
	if projectBefore != nil && model.S(r["origin"]) != "" {
		prior, path, err := e.workByOrigin(model.S(r["origin"]), projectID)
		if err != nil {
			return nil, err
		}
		if prior != nil {
			n := prior.Norm()
			if model.S(n["project_id"]) != projectID {
				return nil, fault.At("INVALID_PROJECT", prior.ID(), path, "origin belongs to a different project identity")
			}
			requestedSpec, requestedPlan := model.S(r["spec_id"]), model.S(r["plan_id"])
			currentSpec, currentPlan := model.S(n["spec_id"]), model.S(n["plan_id"])
			matchingIntent := model.S(n["title"]) == model.S(r["title"]) && model.S(n["summary"]) == model.S(r["intent"]) && model.S(n["work_type"]) == model.S(r["work_type"])
			canRepair := matchingIntent && (requestedSpec != "" || requestedPlan != "") &&
				(currentSpec == "" || requestedSpec == "" || currentSpec == requestedSpec) &&
				(currentPlan == "" || requestedPlan == "" || currentPlan == requestedPlan) &&
				((currentSpec == "" && requestedSpec != "") || (currentPlan == "" && requestedPlan != ""))
			if canRepair {
				if err := e.refuseLegacyWorkOwner(); err != nil {
					return nil, err
				}
				if requestedSpec == "" {
					requestedSpec = currentSpec
				}
				if requestedPlan == "" {
					requestedPlan = currentPlan
				}
				specPath, planPath, err := e.checkWorkBinding(requestedSpec, requestedPlan)
				if err != nil {
					return nil, err
				}
				_, before, selectedPath, err := e.readWork(prior.ID())
				if err != nil {
					return nil, err
				}
				next, err := prior.Clone()
				if err != nil {
					return nil, err
				}
				norm := next.Norm()
				norm["spec_id"], norm["spec_path"] = requestedSpec, specPath
				if requestedPlan != "" {
					norm["plan_id"], norm["plan_path"] = requestedPlan, planPath
				}
				next.Data["revision"] = prior.Revision() + 1
				next, err = render.Prepare(next.Data)
				if err != nil {
					return nil, err
				}
				after, err := render.Render(next)
				if err != nil {
					return nil, err
				}
				result := workSummary(next, selectedPath)
				result["reused"], result["attachment_repaired"] = true, true
				o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: selectedPath, Before: before, After: after}}, result)
				if err != nil {
					return nil, err
				}
				return mutationResult(o), nil
			}
			out := workSummary(prior, path)
			out["reused"] = true
			out["input_differs"] = model.S(n["title"]) != model.S(r["title"]) || model.S(n["summary"]) != model.S(r["intent"]) || model.S(n["work_type"]) != model.S(r["work_type"]) || model.S(n["spec_id"]) != model.S(r["spec_id"]) || model.S(n["plan_id"]) != model.S(r["plan_id"])
			return out, nil
		}
	}
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	if projectID == "" {
		entries, err := e.FS.List(".codearbiter/work")
		if err != nil && !os.IsNotExist(err) {
			return nil, err
		}
		if len(entries) != 0 {
			return nil, fault.At("INVALID_PROJECT", "", projectPath, "work files exist without a portable project identity; preserve them for inspection")
		}
		projectID, err = newOpaqueID("PROJECT-")
		if err != nil {
			return nil, err
		}
		projectAfter, err = canonical.Marshal(object{"format": "codearbiter.project", "version": int64(1), "owner": "native", "project_id": projectID})
		if err != nil {
			return nil, err
		}
	}
	specPath, planPath, err := e.checkWorkBinding(model.S(r["spec_id"]), model.S(r["plan_id"]))
	if err != nil {
		return nil, err
	}
	id, err := newOpaqueID("WORK-")
	if err != nil {
		return nil, err
	}
	slug := "work-" + strings.ToLower(strings.TrimPrefix(id, "WORK-"))
	norm := object{"project_id": projectID, "title": r["title"], "summary": r["intent"], "work_type": r["work_type"], "spec_id": nil, "plan_id": nil, "spec_path": nil, "plan_path": nil, "origin": nil, "aliases": []any{}}
	if specPath != "" {
		norm["spec_path"] = specPath
	}
	if planPath != "" {
		norm["plan_path"] = planPath
	}
	for _, k := range []string{"spec_id", "plan_id", "origin"} {
		if s := model.S(r[k]); s != "" {
			norm[k] = s
		}
	}
	v := object{"format": model.Format, "format_version": model.FormatVersion, "kind": "work", "schema_version": model.SchemaVersion, "artifact_id": id, "slug": slug, "revision": int64(1), "presentation": render.Presentation(""), "normative": norm, "execution": object{"state": "queued", "check_status": "unknown", "started_at": nil, "completed_at": nil}}
	d, err := render.Prepare(v)
	if err != nil {
		return nil, err
	}
	b, err := render.Render(d)
	if err != nil {
		return nil, err
	}
	if err := e.FS.Mkdir(".codearbiter/work"); err != nil {
		return nil, err
	}
	edits := []store.Edit{}
	if projectBefore == nil {
		edits = append(edits, store.Edit{Path: projectPath, Before: nil, After: projectAfter})
	}
	p := workPath(id)
	edits = append(edits, store.Edit{Path: p, Before: nil, After: b})
	result := workSummary(d, p)
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, edits, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}

// Attachments name exact artifact identities. The catalog is used only when
// attaching, never for a selected work read or ordinary progress update.
func (e *Engine) checkWorkBinding(specID, planID string) (string, string, error) {
	if specID == "" && planID == "" {
		return "", "", nil
	}
	if planID != "" && specID == "" {
		return "", "", fault.New("SPEC_REQUIRED", "a plan attachment also needs its specification ID")
	}
	c, err := repository.ScanFor(e.FS, "")
	if err != nil {
		return "", "", err
	}
	spec, err := c.Resolve(specID)
	if err != nil {
		return "", "", err
	}
	if spec.Doc.Kind() != "spec" {
		return "", "", fault.New("INVALID_BINDING", "spec_id does not name a specification")
	}
	if planID == "" {
		return spec.Path, "", nil
	}
	plan, err := c.Resolve(planID)
	if err != nil {
		return "", "", err
	}
	if plan.Doc.Kind() != "plan" || model.S(model.M(plan.Doc.Norm()["spec_ref"])["artifact_id"]) != specID {
		return "", "", fault.New("INVALID_BINDING", "plan does not bind the selected specification")
	}
	return spec.Path, plan.Path, nil
}

func (e *Engine) readWork(id string) (*model.Document, []byte, string, error) {
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, nil, "", err
	}
	if projectID == "" {
		return nil, nil, "", fault.At("INVALID_PROJECT", id, projectPath, "portable project identity is absent")
	}
	return e.readWorkWithProject(id, projectID)
}

func (e *Engine) readWorkWithProject(id, projectID string) (*model.Document, []byte, string, error) {
	if !workIDPattern.MatchString(id) {
		return nil, nil, "", fault.New("INVALID_ID", "work ID is malformed")
	}
	p := workPath(id)
	b, err := e.FS.Read(p, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, nil, p, fault.At("NOT_FOUND", id, p, "selected work item is absent")
	}
	if err != nil {
		return nil, nil, p, err
	}
	d, err := render.Parse(b)
	if err != nil {
		return nil, nil, p, fault.At("INVALID_WORK", id, p, "selected work item is invalid: "+err.Error())
	}
	if d.Kind() != "work" || d.ID() != id {
		return nil, nil, p, fault.At("INVALID_WORK", id, p, "selected work identity does not match its canonical path")
	}
	if projectID != model.S(d.Norm()["project_id"]) {
		return nil, nil, p, fault.At("INVALID_PROJECT", id, projectPath, "selected work does not match the portable project identity")
	}
	return d, b, p, nil
}

func workSummary(d *model.Document, p string) object {
	n, ex := d.Norm(), model.M(d.Data["execution"])
	return object{"work_id": d.ID(), "project_id": n["project_id"], "path": p, "revision": d.Revision(), "model_sha256": d.Hash(), "title": n["title"], "intent": n["summary"], "work_type": n["work_type"], "spec_id": n["spec_id"], "plan_id": n["plan_id"], "spec_path": n["spec_path"], "plan_path": n["plan_path"], "origin": n["origin"], "aliases": n["aliases"], "state": ex["state"], "check_status": ex["check_status"], "started_at": ex["started_at"], "completed_at": ex["completed_at"]}
}

func (e *Engine) workGet(r object) (any, error) {
	id := model.S(r["work_id"])
	d, _, p, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	return workSummary(d, p), nil
}

// workList pages by stable opaque IDs. It reads only the selected page's
// models; the digest detects membership changes between pages without
// implying that the listed progress is a frozen project snapshot.
func (e *Engine) workList(r object) (any, error) {
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	if projectID == "" {
		return nil, fault.At("NOT_INITIALIZED", "", projectPath, "native work has no portable project identity")
	}
	entries, err := e.FS.List(".codearbiter/work")
	if err != nil {
		return nil, err
	}
	if len(entries) > 20000 {
		return nil, fault.New("WORK_SCAN_LIMIT", "work directory exceeds bounded listing")
	}
	ids := []string{}
	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".html") {
			continue
		}
		id := strings.TrimSuffix(name, ".html")
		if !workIDPattern.MatchString(id) || entry.IsDir() {
			return nil, fault.At("INVALID_WORK", "", ".codearbiter/work/"+name, "work directory contains an invalid HTML entry")
		}
		ids = append(ids, id)
	}
	sort.Strings(ids)
	digest, err := canonical.Hash(model.List(ids...))
	if err != nil {
		return nil, err
	}
	offset, ok := model.NativeInt(model.I(r["offset"]))
	if !ok || offset < 0 {
		return nil, fault.New("INVALID_OFFSET", "work offset is outside the native integer range")
	}
	if offset > 0 && model.S(r["membership_sha256"]) != digest {
		return nil, fault.New("STALE_CURSOR", "work membership changed during listing")
	}
	if offset > len(ids) {
		return nil, fault.New("INVALID_OFFSET", "work offset is outside the current listing")
	}
	limit := 32
	if n := model.I(r["limit"]); n != 0 {
		limit = int(n)
	}
	budget := int64(16384)
	if n := model.I(r["budget"]); n != 0 {
		budget = n
	}
	out := object{"project_id": projectID, "membership_sha256": digest, "entries": []any{}, "offset": int64(offset), "total": int64(len(ids)), "next_offset": nil, "content_snapshot": false}
	items := []any{}
	next := offset
	for next < len(ids) && len(items) < limit {
		d, _, p, err := e.readWorkWithProject(ids[next], projectID)
		if err != nil {
			return nil, err
		}
		n := d.Norm()
		item := object{"work_id": d.ID(), "path": p, "revision": d.Revision(), "title": n["title"], "work_type": n["work_type"], "state": model.M(d.Data["execution"])["state"], "check_status": model.M(d.Data["execution"])["check_status"], "spec_id": n["spec_id"], "plan_id": n["plan_id"]}
		candidate := append(append([]any{}, items...), item)
		out["entries"] = candidate
		out["next_offset"] = int64(next + 1)
		encoded, err := json.Marshal(out)
		if err != nil {
			return nil, err
		}
		if int64(len(encoded))+512 > budget {
			break
		}
		items = candidate
		next++
	}
	if len(items) == 0 && next < len(ids) {
		return nil, fault.New("RESPONSE_TOO_LARGE", "one work listing entry exceeds response budget")
	}
	out["entries"] = items
	if next < len(ids) {
		out["next_offset"] = int64(next)
	} else {
		out["next_offset"] = nil
	}
	return out, nil
}

func boundedText(s string, maxRunes int) string {
	r := []rune(s)
	if len(r) <= maxRunes {
		return s
	}
	return string(r[:maxRunes]) + "…"
}

// workContext provides a compact, selected orientation. It reports current
// attached identities but does not imply that a plan's checks passed or that
// omitted source detail has been read.
func (e *Engine) workContext(r object) (any, error) {
	id := model.S(r["work_id"])
	d, _, p, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	budget := int64(16384)
	if b := model.I(r["budget"]); b != 0 {
		budget = b
	}
	n := d.Norm()
	w := workSummary(d, p)
	w["intent"] = boundedText(model.S(w["intent"]), 1024)
	if aliases := model.A(w["aliases"]); len(aliases) > 16 {
		w["aliases"] = aliases[:16]
		w["aliases_omitted"] = int64(len(aliases) - 16)
	}
	out := object{"work": w, "spec": nil, "plan": nil, "context_complete": false, "assessment": "advisory"}
	for _, pair := range []struct{ name, kind string }{{"spec", "spec"}, {"plan", "plan"}} {
		artifactID := model.S(n[pair.name+"_id"])
		if artifactID == "" {
			continue
		}
		attachedPath := model.S(n[pair.name+"_path"])
		b, err := e.FS.Read(attachedPath, canonical.MaxBytes)
		if os.IsNotExist(err) {
			return nil, fault.At("STALE_BINDING", id, attachedPath, "attached "+pair.name+" is absent")
		}
		if err != nil {
			return nil, err
		}
		attached, err := render.Parse(b)
		if err != nil {
			return nil, fault.At("INVALID_BINDING", id, attachedPath, "attached "+pair.name+" is invalid: "+err.Error())
		}
		if attached.Kind() != pair.kind || attached.ID() != artifactID {
			return nil, fault.At("STALE_BINDING", id, attachedPath, "attached "+pair.name+" identity changed")
		}
		if pair.kind == "plan" && model.S(model.M(attached.Norm()["spec_ref"])["artifact_id"]) != model.S(n["spec_id"]) {
			return nil, fault.At("STALE_BINDING", id, attachedPath, "attached plan now points to a different specification")
		}
		out[pair.name] = object{"artifact_id": attached.ID(), "path": attachedPath, "revision": attached.Revision(), "model_sha256": attached.Hash(), "normative_sha256": attached.NormHash(), "title": boundedText(model.S(attached.Norm()["title"]), 240), "summary": boundedText(model.S(attached.Norm()["summary"]), 512)}
	}
	b, err := json.Marshal(out)
	if err != nil {
		return nil, err
	}
	if int64(len(b))+512 > budget {
		return nil, fault.New("RESPONSE_TOO_LARGE", "selected work context exceeds budget; request a larger budget or read the work item alone")
	}
	return out, nil
}

func (e *Engine) workUpdate(r object) (any, error) {
	id := model.S(r["work_id"])
	d, before, p, err := e.readWork(id)
	if err != nil {
		return nil, err
	}
	if err := e.refuseLegacyWorkOwner(); err != nil {
		return nil, err
	}
	expected := model.M(r["expected"])
	if model.I(expected["revision"]) != d.Revision() || model.S(expected["model_sha256"]) != d.Hash() {
		return nil, fault.At("REVISION_CONFLICT", id, p, "selected work changed; refresh its identity before retrying")
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	norm, ex := next.Norm(), model.M(next.Data["execution"])
	switch model.S(r["action"]) {
	case "rename":
		if title := model.S(r["title"]); title != "" {
			norm["title"] = title
		} else {
			return nil, fault.New("INVALID_WORK_UPDATE", "rename needs a title")
		}
	case "attach":
		if model.S(r["spec_id"]) == "" && model.S(r["plan_id"]) == "" {
			return nil, fault.New("INVALID_WORK_UPDATE", "attach needs a spec or plan ID")
		}
		specID, planID := model.S(r["spec_id"]), model.S(r["plan_id"])
		if specID == "" {
			specID = model.S(norm["spec_id"])
		}
		if planID == "" {
			planID = model.S(norm["plan_id"])
		}
		if specID == "" && planID == "" {
			return nil, fault.New("INVALID_WORK_UPDATE", "attach needs a spec or plan ID")
		}
		specPath, planPath, err := e.checkWorkBinding(specID, planID)
		if err != nil {
			return nil, err
		}
		norm["spec_id"], norm["spec_path"], norm["plan_id"], norm["plan_path"] = specID, specPath, nil, nil
		if planID != "" {
			norm["plan_id"] = planID
			norm["plan_path"] = planPath
		}
	case "start":
		if model.S(ex["state"]) != "queued" {
			return nil, fault.New("INVALID_WORK_TRANSITION", "only queued work can start")
		}
		ex["state"], ex["started_at"] = "active", time.Now().UTC().Format("2006-01-02")
	case "complete":
		if s := model.S(ex["state"]); s != "active" && s != "queued" {
			return nil, fault.New("INVALID_WORK_TRANSITION", "only queued or active work can record completion")
		}
		ex["state"], ex["completed_at"] = "complete", time.Now().UTC().Format("2006-01-02")
	case "reopen":
		if model.S(ex["state"]) != "complete" {
			return nil, fault.New("INVALID_WORK_TRANSITION", "only completed work can reopen")
		}
		ex["state"], ex["completed_at"] = "active", nil
		if ex["started_at"] == nil {
			ex["started_at"] = time.Now().UTC().Format("2006-01-02")
		}
	case "archive":
		if model.S(ex["state"]) == "archived" {
			return nil, fault.New("INVALID_WORK_TRANSITION", "work is already archived")
		}
		ex["state"] = "archived"
	default:
		return nil, fault.New("INVALID_WORK_UPDATE", "unknown work action")
	}
	// Work completion is a progress report. No operation here can manufacture
	// a passing check without recorded check evidence.
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
