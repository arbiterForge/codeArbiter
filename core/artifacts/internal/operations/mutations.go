package operations

import (
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"regexp"
	"sort"
	"strings"
	"time"
)

func empty() []any { return []any{} }
func New(r object, c *repository.Catalog) (*model.Document, error) {
	kind, id, slug := model.S(r["kind"]), model.S(r["artifact_id"]), model.S(r["slug"])
	if _, ok := c.Entries[id]; ok {
		return nil, fault.New("ALREADY_EXISTS", "artifact ID already exists")
	}
	baseline := r["baseline"]
	if baseline == nil {
		baseline = object{"repository": nil, "commit": nil, "observed_date": time.Now().UTC().Format("2006-01-02")}
	}
	n := object{"title": r["title"], "summary": r["summary"], "baseline": baseline, "sections": empty(), "sources": empty(), "retired_symbols": empty()}
	comp := "../plans/" + slug + ".html"
	v := object{"format": model.Format, "format_version": model.FormatVersion, "kind": kind, "schema_version": model.SchemaVersion, "artifact_id": id, "slug": slug, "revision": int64(1), "governance": object{"state": "draft", "approvals": empty(), "review_notes": empty()}, "presentation": render.Presentation(comp), "normative": n}
	if kind == "spec" {
		n["intent"] = object{"id": "INTENT-01"}
		n["approach"] = object{"id": "APPROACH-01"}
		for _, k := range []string{"constraints", "scope", "non_goals", "decisions", "criteria", "governs", "open_decisions"} {
			n[k] = empty()
		}
	} else {
		if model.S(r["spec_id"]) == "" {
			return nil, fault.New("SPEC_REQUIRED", "new plan requires spec_id")
		}
		s, e := c.Resolve(model.S(r["spec_id"]))
		if e != nil {
			return nil, e
		}
		if s.Doc.Kind() != "spec" {
			return nil, fault.New("SPEC_REQUIRED", "spec_id must name a specification")
		}
		n["spec_ref"] = object{"artifact_id": s.Doc.ID(), "normative_sha256": s.Doc.NormHash(), "binding_mode": "draft_preview"}
		for _, k := range []string{"tasks", "checkpoints", "prerequisites", "criterion_dispositions"} {
			n[k] = empty()
		}
		model.M(v["presentation"])["companion_path"] = "../specs/" + strings.TrimSuffix(strings.TrimPrefix(s.Path, ".codearbiter/specs/"), ".html") + ".html"
		v["execution"] = object{"tasks": object{}, "prerequisites": object{}, "prerequisite_evidence": object{}, "scopes": object{}}
	}
	if supplied := model.M(r["normative"]); supplied != nil {
		if model.S(supplied["title"]) != model.S(r["title"]) || model.S(supplied["summary"]) != model.S(r["summary"]) {
			return nil, fault.New("HEADER_MISMATCH", "request title/summary must match supplied normative content")
		}
		n = supplied
		v["normative"] = n
		if kind == "plan" {
			s, e := c.Resolve(model.S(r["spec_id"]))
			if e != nil {
				return nil, e
			}
			binding := model.M(n["spec_ref"])
			if model.S(binding["artifact_id"]) != s.Doc.ID() || model.S(binding["normative_sha256"]) != s.Doc.NormHash() || model.S(binding["binding_mode"]) != "draft_preview" {
				return nil, fault.New("INVALID_BINDING", "new plan must explicitly bind the selected current draft source")
			}
		}
	}
	syncExecution(v)
	return render.Prepare(v)
}
func syncExecution(v object) {
	if model.S(v["kind"]) != "plan" {
		return
	}
	ex := model.M(v["execution"])
	n := model.M(v["normative"])
	old := model.M(ex["tasks"])
	states := object{}
	for _, v := range model.A(n["tasks"]) {
		id := model.S(model.M(v)["id"])
		if state, ok := old[id]; ok {
			states[id] = state
		} else {
			states[id] = object{"state": "PENDING", "evidence_refs": empty(), "reason": nil}
		}
	}
	ex["tasks"] = states
	oldp := model.M(ex["prerequisites"])
	olde := model.M(ex["prerequisite_evidence"])
	ps, pe := object{}, object{}
	for _, v := range model.A(n["prerequisites"]) {
		id := model.S(model.M(v)["id"])
		if state, ok := oldp[id]; ok {
			ps[id] = state
		} else {
			ps[id] = "not_satisfied"
		}
		if ev, ok := olde[id]; ok {
			pe[id] = ev
		}
	}
	ex["prerequisites"], ex["prerequisite_evidence"] = ps, pe
	if ex["scopes"] == nil {
		ex["scopes"] = object{}
	}
}
func nextID(idx *symbol.Index, collection string) string {
	p := map[string]string{"criteria": "AC", "scenarios": "SCN", "scope": "SCOPE", "non_goals": "NON-GOAL", "sections": "SEC", "sources": "SRC", "decisions": "DEC", "constraints": "CONSTRAINT", "open_decisions": "CONFIRM", "tasks": "T", "checkpoints": "CP", "prerequisites": "GATE"}[collection]
	if p == "" {
		p = "RECORD"
	}
	for i := 1; i <= symbol.MaxSymbols; i++ {
		id := fmt.Sprintf("%s-%03d", p, i)
		if _, exists := idx.ByID[id]; !exists {
			return id
		}
	}
	return ""
}

var specCollections = map[string]bool{"criteria": true, "scope": true, "non_goals": true, "sections": true, "sources": true, "decisions": true, "constraints": true, "open_decisions": true}
var planCollections = map[string]bool{"tasks": true, "checkpoints": true, "prerequisites": true, "sections": true, "sources": true, "criterion_dispositions": true}

func RemoveRecord(v any, id string) bool {
	switch x := v.(type) {
	case map[string]any:
		for k, v := range x {
			if m := model.M(v); m != nil && model.S(m["id"]) == id {
				x[k] = nil
				return true
			}
			if a, ok := v.([]any); ok {
				for i, z := range a {
					if model.S(model.M(z)["id"]) == id {
						x[k] = append(a[:i], a[i+1:]...)
						return true
					}
				}
			}
			if RemoveRecord(v, id) {
				return true
			}
		}
	case []any:
		for _, v := range x {
			if RemoveRecord(v, id) {
				return true
			}
		}
	}
	return false
}
func Changes(d *model.Document, changes []any) (*model.Document, []string, error) {
	copy, e := d.Clone()
	if e != nil {
		return nil, nil, e
	}
	n := copy.Norm()
	retireReasons := map[string]string{}
	replacements := map[string]any{}
	created := []string{}
	reserved := map[string]bool{}
	for id := range d.Symbols.ByID {
		reserved[id] = true
	}
	introduced := map[string]string{}
	// Track every ID observed during the batch, including nested additions.
	// A record created and retired in one transaction still reserves its ID.
	observed := map[string]symbol.Record{}
	for id, record := range d.Symbols.ByID {
		observed[id] = record
	}
	for _, v := range changes {
		change := model.M(v)
		idx, e := symbol.Build(n)
		if e != nil {
			return nil, nil, e
		}
		op := model.S(change["op"])
		switch op {
		case "header.update":
			for k, v := range model.M(change["fields"]) {
				if k == "governs" && copy.Kind() != "spec" || k == "verification_inputs" && copy.Kind() != "plan" {
					return nil, nil, fault.New("INVALID_FIELD", "header field does not apply to this kind")
				}
				n[k] = v
			}
		case "record.add":
			collection := model.S(change["collection"])
			parent := n
			if id := model.S(change["parent_id"]); id != "" {
				r, ok := idx.ByID[id]
				if !ok || r.Retired {
					return nil, nil, fault.New("SYMBOL_NOT_FOUND", "parent record is absent or retired")
				}
				if r.Kind != "criteria" || collection != "scenarios" {
					return nil, nil, fault.New("INVALID_COLLECTION", "only criterion scenarios support nested append")
				}
				parent = r.Value
			} else {
				allowed := specCollections
				if copy.Kind() == "plan" {
					allowed = planCollections
				}
				if !allowed[collection] {
					return nil, nil, fault.New("INVALID_COLLECTION", "collection is not mutable through record.add")
				}
			}
			record := model.M(change["record"])
			if collection != "criterion_dispositions" {
				if model.S(record["id"]) == "" {
					for rid := range reserved {
						if _, ok := idx.ByID[rid]; !ok {
							idx.ByID[rid] = symbol.Record{ID: rid, Retired: true}
						}
					}
					record["id"] = nextID(idx, collection)
				}
				rid := model.S(record["id"])
				if _, ok := idx.ByID[rid]; ok || reserved[rid] {
					return nil, nil, fault.New("DUPLICATE_ID", "record IDs, including retired IDs, cannot be reused")
				}
				created = append(created, rid)
				reserved[rid] = true
				introduced[rid] = collection
			}
			parent[collection] = append(model.A(parent[collection]), record)
		case "record.update":
			id := model.S(change["symbol"])
			r, ok := idx.ByID[id]
			if !ok || r.Retired {
				return nil, nil, fault.New("SYMBOL_NOT_FOUND", "record is absent or retired")
			}
			for k, v := range model.M(change["fields"]) {
				if k == "id" {
					return nil, nil, fault.New("IMMUTABLE_ID", "record identity cannot be edited")
				}
				r.Value[k] = v
			}
			if reason := model.S(change["retirement_reason"]); reason != "" {
				for old := range idx.ByID {
					retireReasons[old] = reason
				}
			}
		case "record.retire":
			id := model.S(change["symbol"])
			r, ok := idx.ByID[id]
			if !ok || r.Retired {
				return nil, nil, fault.New("SYMBOL_NOT_FOUND", "record is absent or already retired")
			}
			if r.Kind == "intent" || r.Kind == "approach" {
				return nil, nil, fault.New("REQUIRED_RECORD", "required singleton may be edited but not removed")
			}
			nested, e := symbol.Build(r.Value)
			if e != nil {
				return nil, nil, e
			}
			for sid := range nested.ByID {
				retireReasons[sid] = model.S(change["reason"])
			}
			if repl := model.S(change["replacement_ref"]); repl != "" {
				replacements[id] = repl
			}
			if !RemoveRecord(n, id) {
				return nil, nil, fault.New("SYMBOL_NOT_FOUND", "record location is unavailable")
			}
		default:
			return nil, nil, fault.New("INVALID_CHANGE", "unknown typed mutation")
		}

		interim, err := symbol.Build(n)
		if err != nil {
			return nil, nil, err
		}
		for id, record := range interim.ByID {
			if previous, exists := observed[id]; exists {
				if previous.Kind != record.Kind || previous.Retired != record.Retired {
					return nil, nil, fault.New("IMMUTABLE_ID", "record identity cannot change kind or retirement status")
				}
				if _, existedBeforeOperation := idx.ByID[id]; !existedBeforeOperation {
					return nil, nil, fault.New("DUPLICATE_ID", "a removed ID cannot be reintroduced within a batch")
				}
			} else {
				observed[id] = record
				introduced[id] = record.Kind
				reserved[id] = true
			}
		}
	}
	after, e := symbol.Build(n)
	if e != nil {
		return nil, nil, e
	}
	for id, r := range after.ByID {
		if old, ok := d.Symbols.ByID[id]; ok && (old.Kind != r.Kind || old.Retired != r.Retired) {
			return nil, nil, fault.New("IMMUTABLE_ID", "record identity cannot change its kind or retired status")
		}
		if expectedKind, ok := introduced[id]; ok && r.Kind != expectedKind {
			return nil, nil, fault.New("IMMUTABLE_ID", "new record changed kind within batch")
		}
	}
	removed := []string{}
	for id, r := range observed {
		if _, ok := after.ByID[id]; !ok {
			if r.Retired {
				return nil, nil, fault.New("IMMUTABLE_TOMBSTONE", "retired record cannot be removed")
			}
			removed = append(removed, id)
		}
	}
	sort.Strings(removed)
	for _, id := range removed {
		reason := retireReasons[id]
		if strings.TrimSpace(reason) == "" {
			return nil, nil, fault.New("RETIREMENT_REASON_REQUIRED", "removing nested records requires an explicit retirement reason")
		}
		n["retired_symbols"] = append(model.A(n["retired_symbols"]), object{"id": id, "retired_in_revision": d.Revision() + 1, "reason": reason, "replacement_ref": replacements[id]})
	}
	syncExecution(copy.Data)
	copy.Data["revision"] = d.Revision() + 1
	sealed, e := render.Prepare(copy.Data)
	if e != nil {
		return nil, nil, e
	}
	if sealed.NormHash() != d.NormHash() {
		model.M(sealed.Data["governance"])["state"] = "draft"
		sealed, e = render.Prepare(sealed.Data)
	}
	return sealed, created, e
}
func ChangeSummary(a, b *model.Document) []any {
	out := []any{}
	// Records do not cover root-level fields such as title, governs, spec_ref
	// and verification_inputs. Include these changes rather than returning an
	// empty review diff for a changed normative contract.
	collections := map[string]bool{}
	for _, key := range []string{"intent", "approach", "criteria", "scope", "non_goals", "sections", "sources", "decisions", "constraints", "open_decisions", "tasks", "checkpoints", "prerequisites", "retired_symbols"} {
		collections[key] = true
	}
	fields := map[string]any{}
	for key := range a.Norm() {
		fields[key] = nil
	}
	for key := range b.Norm() {
		fields[key] = nil
	}
	for _, key := range canonical.Keys(fields) {
		if collections[key] {
			continue
		}
		before, beforePresent := a.Norm()[key]
		after, afterPresent := b.Norm()[key]
		x, _ := canonical.Hash(before)
		y, _ := canonical.Hash(after)
		if beforePresent != afterPresent || x != y {
			change := "updated"
			if !beforePresent {
				change = "added"
			}
			if !afterPresent {
				change = "removed"
			}
			out = append(out, object{"field": "normative." + key, "change": change, "before_sha256": x, "after_sha256": y})
		}
	}

	keys := map[string]bool{}
	for id := range a.Symbols.ByID {
		keys[id] = true
	}
	for id := range b.Symbols.ByID {
		keys[id] = true
	}
	ids := []string{}
	for id := range keys {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		x, xok := a.Symbols.ByID[id]
		y, yok := b.Symbols.ByID[id]
		hx, _ := canonical.Hash(x.Value)
		hy, _ := canonical.Hash(y.Value)
		if !xok || !yok || hx != hy {
			kind := "updated"
			if !xok {
				kind = "added"
			} else if y.Retired {
				kind = "retired"
			}
			out = append(out, object{"symbol": id, "change": kind, "before_sha256": hx, "after_sha256": hy})
		}
	}
	return out
}
func canonicalArtifactPath(p string) bool {
	return validate.Path(p, false) && regexp.MustCompile(`^\.codearbiter/(specs|plans)/[A-Za-z0-9][A-Za-z0-9._-]*\.html$`).MatchString(p)
}
