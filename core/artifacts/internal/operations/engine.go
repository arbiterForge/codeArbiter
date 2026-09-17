package operations

import (
	"encoding/json"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	reads "github.com/arbiterForge/codeArbiter/core/artifacts/internal/read"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"os"
	"runtime"
	"strings"
	"time"
)

type Engine struct {
	FS          *store.FS
	Catalog     *repository.Catalog
	RequestHash string
}

func Identity(d *model.Document, p string) object {
	return object{"artifact_id": d.ID(), "kind": d.Kind(), "path": p, "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash(), "symbol_count": int64(len(d.Symbols.ByID))}
}
func Run(root, op string, input object) (any, error) {
	if e := CheckRequest(op, input); e != nil {
		return nil, e
	}
	r, e := canonical.Clone(input)
	if e != nil {
		return nil, e
	}
	if op == "capabilities" {
		return object{"binary": "ca-artifact", "version": "0.1.0", "protocol": Protocol, "schema_version": model.SchemaVersion, "renderer": render.Version, "operations": Names(), "storage_backend": store.Backend, "repository_operations_available": store.NativeWrites, "platform": runtime.GOOS + "/" + runtime.GOARCH, "public_registrations_added": int64(0), "host_default_enabled": false, "runtime_downloads": false, "threat_model": "cooperating workflow; not a sandbox against unrestricted same-user writes"}, nil
	}
	if op == "schema" {
		switch model.S(r["name"]) {
		case "operation":
			return RequestSchema(model.S(r["operation"]))
		case "receipt":
			return authority.ReceiptSchema(), nil
		case "event":
			return authority.EventSchema(), nil
		case "verification", "spec_review", "quality_review":
			return evidence.PayloadSchema(model.S(r["name"])), nil
		default:
			return schema.Get(model.S(r["name"]), model.S(r["fragment"]))
		}
	}
	f, e := store.Open(root)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	unlock, e := f.Lock(true, 2*time.Second)
	if e != nil {
		return nil, e
	}
	defer unlock()
	h, e := canonical.Hash(object{"operation": op, "request": r})
	if e != nil {
		return nil, e
	}
	engine := &Engine{FS: f, RequestHash: h}
	if op == "recover" {
		return f.Recover(model.S(r["operation_id"]), model.S(r["mode"]))
	}
	if JournaledMutation(op) {
		if replay, e := f.Lookup(model.S(r["operation_id"]), h); e != nil {
			return nil, e
		} else if replay != nil {
			if replay.State != "committed" {
				return nil, fault.New("OPERATION_ROLLED_BACK", "this operation was rolled back; inspect current identity before issuing a new operation")
			}
			return mutationResult(*replay), nil
		}
	}
	if pending, e := f.Pending(); e != nil {
		return nil, e
	} else if len(pending) > 0 {
		return nil, fault.New("RECOVERY_REQUIRED", "a pending multi-file operation blocks canonical reads and writes")
	}
	if op == "migration-rollback" {
		outcome, err := f.RollbackMigration(model.S(r["operation_id"]), h, model.S(r["cutover_operation_id"]))
		if err != nil {
			return nil, err
		}
		return mutationResult(outcome), nil
	}
	if op == "repair-preview" || op == "repair-apply" {
		return engine.repair(op, r)
	}
	c, e := repository.Scan(f)
	if e != nil {
		return nil, e
	}
	engine.Catalog = c
	if op == "capture" {
		return engine.capture(model.M(r["event"]))
	}
	if op == "migration-preview" || op == "migration-apply" {
		return engine.migrate(op, r)
	}
	if op == "farm-seal" {
		return engine.farmSeal(r)
	}
	if op == "farm-verify" {
		return engine.farmVerify(r)
	}
	if op == "create" {
		d, e := New(r, c)
		if e != nil {
			return nil, e
		}
		p, e := repository.NewPath(d.Kind(), model.S(d.Data["slug"]))
		if e != nil {
			return nil, e
		}
		if _, er := f.Read(strings.TrimSuffix(p, ".html")+".md", canonical.MaxBytes); er == nil {
			return nil, fault.New("LEGACY_CONFLICT", "canonical Markdown already exists; use reviewed migration")
		} else if !os.IsNotExist(er) {
			return nil, er
		}
		if b, e := f.Read(p, canonical.MaxBytes); e == nil && b != nil {
			return nil, fault.New("ALREADY_EXISTS", "canonical target already exists")
		}
		return engine.save(r, repository.Entry{Path: p}, d)
	}
	budget := reads.DefaultBudget
	if b := model.I(r["budget"]); b != 0 {
		budget = int(b)
	}
	if op == "index" {
		return engine.index(r, budget)
	}
	entry, e := c.Resolve(model.S(r["artifact_id"]))
	if e != nil {
		return nil, e
	}
	d := entry.Doc
	if JournaledMutation(op) && op != "export" {
		expected := model.M(r["expected"])
		if model.I(expected["revision"]) != d.Revision() || model.S(expected["model_sha256"]) != d.Hash() {
			return nil, fault.New("REVISION_CONFLICT", "expected revision AND model identity must match the current artifact")
		}
	}
	switch op {
	case "export":
		return engine.export(r, entry)
	case "identity":
		out := Identity(d, entry.Path)
		out["authority"] = authority.Status(f, d)
		return out, nil
	case "read":
		if model.S(r["mode"]) == "exact" {
			if model.S(r["cursor"]) != "" {
				return nil, fault.New("INVALID_CURSOR", "exact reads do not accept a cursor")
			}
			return reads.Exact(d, model.S(r["symbol"]), budget)
		}
		return reads.Page(f, c, d, model.S(r["symbol"]), model.S(r["cursor"]), budget)
	case "outline":
		offset := int(model.I(r["offset"]))
		if offset > 0 && model.S(r["model_sha256"]) != d.Hash() {
			return nil, fault.New("STALE_CURSOR", "outline continuation requires the same model identity")
		}
		return reads.Outline(d, offset, budget)
	case "validate":
		gate := model.S(r["gate"])
		es := validate.Structural(d)
		var spec *model.Document
		if d.Kind() == "plan" && (gate == "ready" || gate == "approved") {
			s, e := c.Spec(d)
			if e != nil {
				return nil, e
			}
			spec = s.Doc
		}
		if gate == "ready" || gate == "approved" {
			es = validate.Ready(d, spec)
		}
		out := Identity(d, entry.Path)
		out["gate"] = gate
		out["valid"] = len(es) == 0
		out["diagnostics"] = es
		out["authority"] = authority.Status(f, d)
		if gate == "approved" {
			if _, e := engine.guards(d); e != nil {
				out["valid"] = false
				out["authority_diagnostic"] = fault.Public(e)
			}
		}
		return out, nil
	case "snapshot":
		snap, e := evidence.Snapshot(f, d)
		if e != nil {
			return nil, e
		}
		return object{"sha256": snap["sha256"], "entry_count": int64(len(model.M(model.M(snap["manifest"])["entries"]))), "platform": model.M(snap["manifest"])["platform"], "roots": model.M(snap["manifest"])["roots"], "exclude_directories": model.M(snap["manifest"])["exclude_directories"]}, nil
	case "apply", "diff":
		next, ids, e := Changes(d, model.A(r["changes"]))
		if e != nil {
			return nil, e
		}
		if op == "diff" {
			out := object{"artifact_id": d.ID(), "before_normative_sha256": d.NormHash(), "after_normative_sha256": next.NormHash(), "changes": ChangeSummary(d, next), "created_symbols": ids, "approval_becomes_stale": d.NormHash() != next.NormHash()}
			b, _ := json.Marshal(out)
			if len(b)+1024 > budget {
				return nil, fault.New("RESPONSE_TOO_LARGE", "semantic diff exceeds budget; split the proposed batch")
			}
			return out, nil
		}
		return engine.save(r, entry, next)
	case "rebrand":
		next, e := d.Clone()
		if e != nil {
			return nil, e
		}
		p := model.M(next.Data["presentation"])
		if name := model.S(r["name"]); name != "" {
			p["brand_name"] = name
		}
		if logo := model.S(r["logo_path"]); logo != "" {
			b, e := f.Read(logo, render.MaxLogoBytes)
			if e != nil {
				return nil, e
			}
			uri, e := render.Logo(model.S(r["mime"]), b)
			if e != nil {
				return nil, e
			}
			p["logo_data_uri"] = uri
			p["logo_origin"] = logo
			p["logo_git_blob"] = nil
		}
		next.Data["revision"] = d.Revision() + 1
		next, e = render.Prepare(next.Data)
		if e != nil {
			return nil, e
		}
		return engine.save(r, entry, next)
	case "approve":
		return engine.approve(r, entry)
	case "plan-bind":
		return engine.bind(r, entry)
	case "eligible":
		return engine.eligible(d)
	case "task-start", "task-review", "task-block", "task-reconcile", "scope-reconcile", "accept-scope", "prerequisite":
		return engine.progress(op, r, entry)
	case "farm-project":
		return engine.farmProject(r, entry)
	}
	return nil, fault.New("UNKNOWN_OPERATION", "operation has no implementation")
}
func (e *Engine) save(r object, old repository.Entry, next *model.Document) (any, error) {
	b, err := render.Render(next)
	if err != nil {
		return nil, err
	}
	out := Identity(next, old.Path)
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: old.Path, Before: old.Bytes, After: b}}, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}
func (e *Engine) index(r object, budget int) (any, error) {
	c := e.Catalog
	vector := c.Vector()
	for _, id := range c.Order {
		entry := c.Entries[id]
		model.M(vector[id])["authority_sources"] = authority.InspectionVector(e.FS, entry.Doc)
	}
	h, err := canonical.Hash(vector)
	if err != nil {
		return nil, err
	}
	offset := int(model.I(r["offset"]))
	if offset < 0 || offset > len(c.Order) {
		return nil, fault.New("INVALID_OFFSET", "index offset is outside the catalog")
	}
	if offset > 0 && model.S(r["catalog_sha256"]) != h {
		return nil, fault.New("STALE_CURSOR", "catalog changed during index paging")
	}
	out := object{"catalog_sha256": h, "entries": empty(), "next_offset": nil, "total": int64(len(c.Order))}
	items := empty()
	next := offset
	for next < len(c.Order) {
		entry := c.Entries[c.Order[next]]
		next++
		if k := model.S(r["kind"]); k != "" && entry.Doc.Kind() != k {
			continue
		}
		item := Identity(entry.Doc, entry.Path)
		item["title"] = entry.Doc.Norm()["title"]
		item["governs"] = entry.Doc.Norm()["governs"]
		item["authority"] = authority.Status(e.FS, entry.Doc)
		candidate := append(append([]any{}, items...), item)
		out["entries"] = candidate
		b, _ := json.Marshal(out)
		if len(b)+1024 > budget {
			next--
			break
		}
		items = candidate
	}
	if len(items) == 0 && next < len(c.Order) {
		return nil, fault.New("RESPONSE_TOO_LARGE", "catalog record exceeds response budget")
	}
	out["entries"] = items
	if next < len(c.Order) {
		out["next_offset"] = int64(next)
	}
	return out, nil
}
func (e *Engine) repair(op string, r object) (any, error) {
	p := model.S(r["path"])
	if !canonicalArtifactPath(p) {
		return nil, fault.New("UNSAFE_PATH", "repair target must be a canonical HTML artifact")
	}
	b, err := e.FS.Read(p, canonical.MaxBytes)
	if err != nil {
		return nil, err
	}
	v, err := render.DecodeModel(b)
	if err != nil {
		return nil, err
	}
	d, err := model.Check(v)
	if err != nil {
		return nil, err
	}
	candidate, err := render.Render(d)
	if err != nil {
		return nil, err
	}
	oldh, newh := canonical.BytesHash(b), canonical.BytesHash(candidate)
	out := object{"path": p, "artifact_id": d.ID(), "model_sha256": d.Hash(), "expected_bytes_sha256": oldh, "preview_sha256": newh, "changes_normative_content": false, "will_discard_view_only_edits": oldh != newh, "warning": "Only the embedded model is authoritative. Existing bytes are archived before explicit repair."}
	if op == "repair-preview" {
		return out, nil
	}
	if model.S(r["expected_bytes_sha256"]) != oldh || model.S(r["preview_sha256"]) != newh {
		return nil, fault.New("REVISION_CONFLICT", "repair preview no longer matches current bytes")
	}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: p, Before: b, After: candidate}}, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}

// No capability discovery or operation ever downloads code or invokes a stored command.

// mutationResult has the same shape on first completion and retry. The stored
// response identifies the original completed revision, never a later edit.
func mutationResult(o store.Outcome) object {
	out := object{}
	if o.Result != nil {
		for key, value := range o.Result {
			out[key] = value
		}
	} else {
		// Journals from the earlier candidate did not retain response metadata.
		// A terminal receipt is useful, but must not impersonate current identity.
		out["refresh_required"] = true
	}
	out["transaction"] = o
	return out
}
