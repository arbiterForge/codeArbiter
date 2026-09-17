// Package read returns whole records with dependency-bound, content-addressed
// cooperative continuation receipts. A completion ticket proves engine delivery,
// not human or agent comprehension, and grants no approval or permission.
package read

import (
	"encoding/json"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"sort"
)

const DefaultBudget = 16 * 1024
const MaxBudget = 64 * 1024

type Selection struct {
	Items                    []any
	Vector                   map[string]any
	VectorHash, ManifestHash string
}

func issue(f *store.FS, p map[string]any) (string, error) {
	b, e := canonical.Marshal(p)
	if e != nil {
		return "", e
	}
	sha := canonical.BytesHash(b)
	if e = f.PutContextToken(sha, b); e != nil {
		return "", e
	}
	return sha, nil
}
func load(f *store.FS, digest string) (map[string]any, error) {
	b, e := f.ContextToken(digest)
	if e != nil {
		return nil, e
	}
	p, e := canonical.Object(b)
	if e != nil {
		return nil, fault.New("CORRUPT_CONTEXT_TOKEN", "context receipt is not a canonical object")
	}
	return p, nil
}
func contains(v any, id string) bool {
	switch x := v.(type) {
	case map[string]any:
		if model.S(x["id"]) == id {
			return true
		}
		for _, v := range x {
			if contains(v, id) {
				return true
			}
		}
	case []any:
		for _, v := range x {
			if contains(v, id) {
				return true
			}
		}
	}
	return false
}
func Context(f *store.FS, c *repository.Catalog, d *model.Document, id string) (*Selection, error) {
	r, ok := d.Symbols.ByID[id]
	if !ok {
		return nil, fault.New("SYMBOL_NOT_FOUND", "record does not exist")
	}
	docs := []*model.Document{d}
	if d.Kind() == "plan" {
		s, e := c.Spec(d)
		if e != nil {
			return nil, e
		}
		docs = append(docs, s.Doc)
	}
	docmap := map[string]*model.Document{}
	for _, x := range docs {
		docmap[x.ID()] = x
	}
	selected := map[string]any{}
	order := []string{}
	addValue := func(key string, value any) {
		if _, ok := selected[key]; !ok {
			selected[key] = value
			order = append(order, key)
		}
	}
	var add func(*model.Document, string) error
	add = func(doc *model.Document, rid string) error {
		key := doc.ID() + "#" + rid
		if _, ok := selected[key]; ok {
			return nil
		}
		r, ok := doc.Symbols.ByID[rid]
		if !ok {
			return fault.New("DANGLING_REFERENCE", "context requires an absent record")
		}
		addValue(key, map[string]any{"key": key, "artifact_id": doc.ID(), "symbol": rid, "kind": r.Kind, "record": r.Value})
		for _, field := range []string{"depends_on", "criterion_refs", "intent_refs", "constraint_refs", "binding_decision_refs", "source_refs", "refs"} {
			for _, ref := range model.Strings(r.Value[field]) {
				target, sub := doc, ref
				if a, b, e := symbol.Split(ref); e == nil {
					target = docmap[a]
					sub = b
					if target == nil {
						return fault.New("UNRESOLVED_CONTEXT", "context reference points outside the current spec/plan pair")
					}
				}
				if e := add(target, sub); e != nil {
					return e
				}
			}
		}
		return nil
	}
	if e := add(d, id); e != nil {
		return nil, e
	}
	// A scenario or verification record cannot be interpreted without its parent
	// criterion/task contract. Include that parent without requiring full documents.
	for _, field := range []string{"criteria", "tasks"} {
		for _, v := range model.A(d.Norm()[field]) {
			if contains(v, id) {
				if e := add(d, model.S(model.M(v)["id"])); e != nil {
					return nil, e
				}
			}
		}
	}
	_ = r
	for _, doc := range docs {
		header := map[string]any{"title": doc.Norm()["title"], "summary": doc.Norm()["summary"], "baseline": doc.Norm()["baseline"], "governance": doc.Data["governance"], "authority": authority.Status(f, doc)}
		for _, k := range []string{"governs", "spec_ref", "criterion_dispositions", "verification_inputs"} {
			if v, ok := doc.Norm()[k]; ok {
				header[k] = v
			}
		}
		addValue(doc.ID()+"#@context", map[string]any{"key": doc.ID() + "#@context", "artifact_id": doc.ID(), "kind": "document_context", "record": header})
		for _, field := range []string{"intent", "approach"} {
			if v := model.M(doc.Norm()[field]); v != nil {
				if e := add(doc, model.S(v["id"])); e != nil {
					return nil, e
				}
			}
		}
		for _, field := range []string{"sections", "scope", "non_goals", "constraints", "decisions", "open_decisions", "prerequisites", "checkpoints", "sources"} {
			for _, v := range model.A(doc.Norm()[field]) {
				if e := add(doc, model.S(model.M(v)["id"])); e != nil {
					return nil, e
				}
			}
		}
		for _, v := range model.A(doc.Norm()["criteria"]) {
			x := model.M(v)
			if model.S(x["kind"]) == "invariant" {
				if e := add(doc, model.S(x["id"])); e != nil {
					return nil, e
				}
			}
		}
	}
	vector, e := authority.Vector(f, docs...)
	if e != nil {
		return nil, e
	}
	for _, doc := range docs {
		entry, _ := c.Resolve(doc.ID())
		vector[doc.ID()] = map[string]any{"path": entry.Path, "model_sha256": doc.Hash()}
	}
	vh, e := canonical.Hash(vector)
	if e != nil {
		return nil, e
	}
	items := []any{}
	manifest := []any{}
	for _, key := range order {
		v := selected[key]
		h, e := canonical.Hash(v)
		if e != nil {
			return nil, e
		}
		items = append(items, v)
		manifest = append(manifest, map[string]any{"key": key, "sha256": h})
	}
	mh, e := canonical.Hash(manifest)
	if e != nil {
		return nil, e
	}
	return &Selection{items, vector, vh, mh}, nil
}
func Exact(d *model.Document, id string, budget int) (map[string]any, error) {
	r, ok := d.Symbols.ByID[id]
	if !ok {
		return nil, fault.New("SYMBOL_NOT_FOUND", "record does not exist")
	}
	out := map[string]any{"artifact_id": d.ID(), "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash(), "mode": "exact", "context_complete": false, "record": r.Value}
	b, _ := json.Marshal(out)
	if len(b)+1024 > budget {
		return nil, fault.At("RECORD_TOO_LARGE", id, "", "whole record does not fit response budget; no partial record returned")
	}
	return out, nil
}
func Page(f *store.FS, c *repository.Catalog, d *model.Document, id, cursor string, budget int) (map[string]any, error) {
	if budget < 4096 || budget > MaxBudget {
		return nil, fault.New("INVALID_BUDGET", "response budget must be 4096..65536 bytes")
	}
	sel, e := Context(f, c, d, id)
	if e != nil {
		return nil, e
	}
	offset := 0
	if cursor != "" {
		p, e := load(f, cursor)
		if e != nil {
			return nil, e
		}
		if model.S(p["purpose"]) != "page" || model.S(p["artifact_id"]) != d.ID() || model.S(p["symbol"]) != id || model.I(p["budget"]) != int64(budget) {
			return nil, fault.New("INVALID_CURSOR", "cursor selection differs from request")
		}
		if model.S(p["vector_sha256"]) != sel.VectorHash || model.S(p["manifest_sha256"]) != sel.ManifestHash {
			return nil, fault.New("STALE_CURSOR", "a contributing artifact or receipt changed")
		}
		var ok bool
		offset, ok = model.NativeInt(p["offset"])
		if !ok || offset < 0 || offset >= len(sel.Items) {
			return nil, fault.New("INVALID_CURSOR", "cursor offset is outside selection")
		}
	}
	out := map[string]any{"artifact_id": d.ID(), "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash(), "mode": "contextual", "vector_sha256": sel.VectorHash, "manifest_sha256": sel.ManifestHash, "total_records": int64(len(sel.Items)), "offset": int64(offset), "items": []any{}, "context_complete": false, "next_cursor": nil, "context_ticket": nil}
	selected := []any{}
	next := offset
	// Reserve enough space for the envelope and a continuation/completion receipt.
	for next < len(sel.Items) {
		candidate := append(append([]any{}, selected...), sel.Items[next])
		out["items"] = candidate
		b, _ := json.Marshal(out)
		if len(b)+2048 > budget {
			break
		}
		selected = candidate
		next++
	}
	if len(selected) == 0 {
		return nil, fault.New("RECORD_TOO_LARGE", "whole contextual record exceeds this page budget; increase budget or revise the draft")
	}
	out["items"] = selected
	payload := map[string]any{"format": "codearbiter.context-token/0.1.0", "artifact_id": d.ID(), "symbol": id, "vector_sha256": sel.VectorHash, "manifest_sha256": sel.ManifestHash, "budget": int64(budget), "offset": int64(next), "purpose": "page"}
	if next < len(sel.Items) {
		s, e := issue(f, payload)
		if e != nil {
			return nil, e
		}
		out["next_cursor"] = s
	} else {
		payload["purpose"] = "context"
		s, e := issue(f, payload)
		if e != nil {
			return nil, e
		}
		out["context_ticket"] = s
		out["context_complete"] = true
	}
	out["returned_records"] = int64(len(selected))
	return out, nil
}
func CheckTicket(f *store.FS, c *repository.Catalog, d *model.Document, id, ticket string) error {
	p, e := load(f, ticket)
	if e != nil {
		return e
	}
	if model.S(p["purpose"]) != "context" || model.S(p["artifact_id"]) != d.ID() || model.S(p["symbol"]) != id {
		return fault.New("INCOMPLETE_CONTEXT", "a completed contextual read of this task is required")
	}
	s, e := Context(f, c, d, id)
	if e != nil {
		return e
	}
	if model.S(p["vector_sha256"]) != s.VectorHash || model.S(p["manifest_sha256"]) != s.ManifestHash || model.I(p["offset"]) != int64(len(s.Items)) {
		return fault.New("STALE_CONTEXT", "context changed since its last complete delivery")
	}
	return nil
}
func Outline(d *model.Document, offset, budget int) (map[string]any, error) {
	ids := append([]string{}, d.Symbols.Order...)
	sort.Strings(ids)
	if offset < 0 || offset > len(ids) {
		return nil, fault.New("INVALID_OFFSET", "outline offset outside record set")
	}
	out := map[string]any{"artifact_id": d.ID(), "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash(), "offset": int64(offset), "total": int64(len(ids)), "records": []any{}, "next_offset": nil}
	items := []any{}
	next := offset
	for next < len(ids) {
		r := d.Symbols.ByID[ids[next]]
		item := map[string]any{"id": r.ID, "kind": r.Kind, "retired": r.Retired, "title": r.Value["title"]}
		candidate := append(append([]any{}, items...), item)
		out["records"] = candidate
		b, _ := json.Marshal(out)
		if len(b)+512 > budget {
			break
		}
		items = candidate
		next++
	}
	if len(items) == 0 && next < len(ids) {
		return nil, fault.At("RECORD_TOO_LARGE", ids[next], "title", "whole outline row does not fit response budget; no non-advancing page returned")
	}
	out["records"] = items
	if next < len(ids) {
		out["next_offset"] = int64(next)
	}
	return out, nil
}
