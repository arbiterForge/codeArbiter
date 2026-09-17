package operations

import (
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"strings"
	"unicode/utf8"
)

type migrationItem struct {
	Source, Target string
	Before, After  []byte
	Doc            *model.Document
}

// Migration deliberately does not infer requirements, IDs, dependencies or
// approval from arbitrary Markdown. The caller supplies a reviewed typed model
// AND a complete, nonoverlapping line disposition. The engine proves coverage
// of bytes/lines, not the truth of the caller's interpretation.
func (e *Engine) migration(r object) ([]migrationItem, object, error) {
	c := &repository.Catalog{Entries: map[string]repository.Entry{}, Order: []string{}}
	for k, v := range e.Catalog.Entries {
		c.Entries[k] = v
		c.Order = append(c.Order, k)
	}
	items := []migrationItem{}
	manifest := object{"format": "codearbiter.migration-preview/0.1.0", "items": empty()}
	var spec *model.Document
	for _, kind := range []string{"spec", "plan"} {
		item := model.M(r[kind])
		if item == nil {
			continue
		}
		source := model.S(item["source_path"])
		slug := model.S(item["slug"])
		if source != ".codearbiter/"+kind+"s/"+slug+".md" || !validate.Path(source, false) {
			return nil, nil, fault.New("UNSAFE_PATH", "legacy source must be the canonical kind/slug Markdown path")
		}
		before, err := e.FS.Read(source, 512<<10)
		if err != nil {
			return nil, nil, err
		}
		if !utf8.Valid(before) || strings.ContainsRune(string(before), 0) {
			return nil, nil, fault.New("INVALID_LEGACY", "legacy input must be bounded UTF-8 text without NUL")
		}
		n, err := canonical.Clone(model.M(item["normative"]))
		if err != nil {
			return nil, nil, err
		}
		rows := empty()
		lines := strings.Split(strings.TrimSuffix(string(before), "\n"), "\n")
		covered := make([]bool, len(lines))
		// New() validates all existing caller references before provenance is added.
		request := object{"kind": kind, "artifact_id": item["artifact_id"], "slug": slug, "title": n["title"], "summary": n["summary"], "normative": n}
		if kind == "plan" {
			if spec == nil {
				return nil, nil, fault.New("SPEC_REQUIRED", "paired plan conversion requires spec mapping")
			}
			request["spec_id"] = spec.ID()
			n["spec_ref"] = object{"artifact_id": spec.ID(), "normative_sha256": spec.NormHash(), "binding_mode": "draft_preview"}
		}
		d, err := New(request, c)
		if err != nil {
			return nil, nil, err
		}
		for _, v := range model.A(item["mappings"]) {
			m := model.M(v)
			a, b := int(model.I(m["start_line"])), int(model.I(m["end_line"]))
			if a < 1 || b < a || b > len(lines) {
				return nil, nil, fault.New("INVALID_LINE_MAPPING", "mapping range is outside the legacy source")
			}
			target := model.S(m["target"])
			rec, ok := d.Symbols.ByID[target]
			if !ok || rec.Retired {
				return nil, nil, fault.New("DANGLING_REFERENCE", "migration target must be an active mapped record")
			}
			for i := a - 1; i < b; i++ {
				if covered[i] {
					return nil, nil, fault.New("OVERLAPPING_MAPPING", "legacy source line is mapped twice")
				}
				covered[i] = true
			}
			rows = append(rows, model.List(fmt.Sprintf("%d–%d", a, b), target, model.S(m["disposition"]), model.S(m["reason"])))
		}
		for _, ok := range covered {
			if !ok {
				return nil, nil, fault.New("UNMAPPED_LEGACY", "every legacy line requires an explicit mapped/historical/out-of-scope disposition")
			}
		}
		for _, id := range []string{"SRC-LEGACY-IMPORT", "SEC-LEGACY-MAPPING"} {
			if _, ok := d.Symbols.ByID[id]; ok {
				return nil, nil, fault.New("RESERVED_MIGRATION_ID", "migration provenance IDs already exist")
			}
		}
		n = d.Norm()
		n["sources"] = append(model.A(n["sources"]), object{"id": "SRC-LEGACY-IMPORT", "title": "Original Markdown source", "type": "local_document", "url": nil, "locator": source, "note": "Exact source SHA-256: " + canonical.BytesHash(before) + ". Original bytes are retained in the cutover transaction history. Original approval/status prose is historical, not current authority."})
		n["sections"] = append(model.A(n["sections"]), object{"id": "SEC-LEGACY-MAPPING", "title": "Reviewed legacy conversion map", "blocks": []any{object{"type": "table", "columns": model.List("Legacy lines", "Target symbol", "Disposition", "Reason"), "rows": rows, "refs": model.List("SRC-LEGACY-IMPORT")}}})
		d, err = render.Prepare(d.Data)
		if err != nil {
			return nil, nil, err
		}
		if spec != nil && kind == "plan" {
			if es := validate.Binding(d, spec); len(es) > 0 {
				return nil, nil, &es[0]
			}
		}
		after, err := render.Render(d)
		if err != nil {
			return nil, nil, err
		}
		target, err := repository.NewPath(kind, slug)
		if err != nil {
			return nil, nil, err
		}
		c.Entries[d.ID()] = repository.Entry{Path: target, Bytes: after, Doc: d}
		c.Order = append(c.Order, d.ID())
		items = append(items, migrationItem{source, target, before, after, d})
		model.M(manifest)["items"] = append(model.A(manifest["items"]), object{"source_path": source, "source_sha256": canonical.BytesHash(before), "source_lines": int64(len(lines)), "target_path": target, "artifact_id": d.ID(), "normative_sha256": d.NormHash(), "model_sha256": d.Hash(), "mapping": item["mappings"]})
		if kind == "spec" {
			spec = d
		}
	}
	hash, err := canonical.Hash(manifest)
	if err != nil {
		return nil, nil, err
	}
	return items, object{"preview_sha256": hash, "manifest": manifest, "all_targets_are_drafts": true, "semantic_mapping_verified": false, "old_approval_transferred": false}, nil
}
func (e *Engine) migrate(op string, r object) (any, error) {
	items, preview, err := e.migration(r)
	if err != nil {
		return nil, err
	}
	if op == "migration-preview" {
		return preview, nil
	}
	if model.S(r["preview_sha256"]) != model.S(preview["preview_sha256"]) {
		return nil, fault.New("STALE_PREVIEW", "legacy bytes or supplied mapping changed since review")
	}
	review := model.M(r["review"])
	edits := []store.Edit{}
	for _, item := range items {
		gov := model.M(item.Doc.Data["governance"])
		gov["review_notes"] = append(model.A(gov["review_notes"]), "Migration mapping attestation by "+model.S(review["actor"])+" at "+model.S(review["origin"])+": "+model.S(review["source_text"])+"; preview "+model.S(preview["preview_sha256"])+". This is not implementation approval.")
		// First persisted revision remains 1; the preview was never canonical.
		d, er := render.Prepare(item.Doc.Data)
		if er != nil {
			return nil, er
		}
		after, er := render.Render(d)
		if er != nil {
			return nil, er
		}
		edits = append(edits, store.Edit{Path: item.Target, After: after}, store.Edit{Path: item.Source, Before: item.Before})
	}
	result := object{"preview_sha256": preview["preview_sha256"], "state": "draft", "old_approvals_transferred": false, "rollback": "Use migration-rollback with a new operation_id and this cutover_operation_id before any candidate edits. For an uncertain transaction use recover."}
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, edits, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}
