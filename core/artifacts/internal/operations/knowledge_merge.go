package operations

import (
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

var numberedID = regexp.MustCompile(`^(.*-)([0-9]{3,})$`)

// mergedCollections are merged record by record; every other normative field
// is merged as one value.
var mergedCollections = map[string]bool{"records": true, "notes": true, "sections": true, "sources": true, "retired_symbols": true}

type mergeConflict struct {
	Field, Symbol, Reason string
}

func equalJSON(a, b any) bool {
	x, e1 := canonical.Marshal(a)
	y, e2 := canonical.Marshal(b)
	return e1 == nil && e2 == nil && string(x) == string(y)
}

func recordList(v any) (map[string]any, []string, bool) {
	items, ok := v.([]any)
	if !ok {
		return nil, nil, false
	}
	out, order := map[string]any{}, []string{}
	for _, item := range items {
		id := model.S(model.M(item)["id"])
		if id == "" {
			return nil, nil, false
		}
		out[id] = item
		order = append(order, id)
	}
	return out, order, true
}

// mergeRecords merges one record collection by ID. Records changed on only
// one side take that side; the same record changed differently on both sides
// is a conflict. Two different records added under the same new ID keep
// ours and give theirs the next free ID, recorded in renamed.
func mergeRecords(field string, base, ours, theirs any, taken map[string]bool, renamed map[string]string, incoming map[string]bool, conflicts *[]mergeConflict) []any {
	b, _, _ := recordList(base)
	o, oOrder, _ := recordList(ours)
	t, tOrder, _ := recordList(theirs)
	if b == nil {
		b = map[string]any{}
	}
	out := []any{}
	for _, id := range oOrder {
		ov, bv := o[id], b[id]
		tv, inTheirs := t[id]
		_, inBase := b[id]
		switch {
		case inTheirs && inBase:
			switch {
			case equalJSON(ov, tv) || equalJSON(tv, bv):
				out = append(out, ov)
			case equalJSON(ov, bv):
				out = append(out, tv)
				incoming[id] = true
			default:
				*conflicts = append(*conflicts, mergeConflict{field, id, "changed differently on both sides"})
			}
		case inTheirs && !inBase:
			out = append(out, ov)
			if !equalJSON(ov, tv) {
				renamed[id] = ""
			}
		case !inTheirs && inBase:
			if !equalJSON(ov, bv) {
				*conflicts = append(*conflicts, mergeConflict{field, id, "changed on one side and removed on the other"})
			}
		default:
			out = append(out, ov)
		}
	}
	for _, id := range tOrder {
		tv := t[id]
		_, inOurs := o[id]
		bv, inBase := b[id]
		switch {
		case inOurs:
			if target, collided := renamed[id]; collided && target == "" {
				next := nextFree(id, taken)
				renamed[id] = next
				moved := canonicalClone(tv)
				model.M(moved)["id"] = next
				out = append(out, moved)
				incoming[next] = true
			}
		case inBase:
			if !equalJSON(tv, bv) {
				*conflicts = append(*conflicts, mergeConflict{field, id, "changed on one side and removed on the other"})
			}
		default:
			out = append(out, tv)
			incoming[id] = true
		}
	}
	return out
}

func canonicalClone(v any) any {
	c, err := canonical.Clone(map[string]any{"v": v})
	if err != nil {
		return v
	}
	return c["v"]
}

func nextFree(id string, taken map[string]bool) string {
	prefix := id + "-"
	if m := numberedID.FindStringSubmatch(id); m != nil {
		prefix = m[1]
	}
	for i := 1; i <= symbol.MaxSymbols; i++ {
		candidate := fmt.Sprintf("%s%03d", prefix, i)
		if !taken[candidate] {
			taken[candidate] = true
			return candidate
		}
	}
	return id
}

// rewriteRefs points references to a renamed record at its new ID.
func rewriteRefs(v any, docID string, renamed map[string]string) {
	switch x := v.(type) {
	case map[string]any:
		for k, value := range x {
			if strings.HasSuffix(k, "_refs") || k == "refs" {
				refs := model.A(value)
				for i, ref := range refs {
					s := model.S(ref)
					if to := renamed[s]; to != "" {
						refs[i] = to
					} else if a, b, err := symbol.Split(s); err == nil && a == docID && renamed[b] != "" {
						refs[i] = a + "#" + renamed[b]
					}
				}
				continue
			}
			rewriteRefs(value, docID, renamed)
		}
	case []any:
		for _, item := range x {
			rewriteRefs(item, docID, renamed)
		}
	}
}

// MergeKnowledge merges two edited versions of one knowledge document against
// their common base at the record level.
func MergeKnowledge(base, ours, theirs *model.Document) (*model.Document, map[string]string, []mergeConflict, error) {
	if ours.ID() != theirs.ID() || ours.Kind() != theirs.Kind() || (base != nil && base.ID() != ours.ID()) || !kind.Knowledge(ours.Kind()) {
		return nil, nil, nil, fault.New("INVALID_MERGE", "merge needs two versions of the same knowledge document")
	}
	baseNorm := map[string]any{}
	if base != nil {
		baseNorm = base.Norm()
	}
	taken := map[string]bool{}
	for _, d := range []*model.Document{base, ours, theirs} {
		if d != nil {
			for id := range d.Symbols.ByID {
				taken[id] = true
			}
		}
	}
	renamed := map[string]string{}
	conflicts := []mergeConflict{}
	merged := map[string]any{}
	incoming := map[string]map[string]bool{}
	keys := map[string]bool{}
	for k := range ours.Norm() {
		keys[k] = true
	}
	for k := range theirs.Norm() {
		keys[k] = true
	}
	names := []string{}
	for k := range keys {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		bv, ov, tv := baseNorm[k], ours.Norm()[k], theirs.Norm()[k]
		if mergedCollections[k] {
			incoming[k] = map[string]bool{}
			merged[k] = mergeRecords(k, bv, ov, tv, taken, renamed, incoming[k], &conflicts)
			continue
		}
		switch {
		case equalJSON(ov, tv) || equalJSON(tv, bv):
			merged[k] = ov
		case equalJSON(ov, bv):
			merged[k] = tv
		default:
			conflicts = append(conflicts, mergeConflict{k, "", "changed differently on both sides"})
		}
	}
	if len(conflicts) > 0 {
		return nil, nil, conflicts, nil
	}
	clean := map[string]string{}
	for from, to := range renamed {
		if to != "" {
			clean[from] = to
		}
	}
	rewriteTheirs(merged, ours.ID(), incoming, clean)
	next, err := canonical.Clone(ours.Data)
	if err != nil {
		return nil, nil, nil, err
	}
	next["normative"] = merged
	revision := ours.Revision()
	if theirs.Revision() > revision {
		revision = theirs.Revision()
	}
	next["revision"] = revision + 1
	d, err := render.Prepare(next)
	if err != nil {
		return nil, nil, nil, err
	}
	return d, clean, nil, nil
}

// rewriteTheirs updates references inside records that ours does not have,
// so a renamed incoming record keeps its links without touching ours.
func rewriteTheirs(merged map[string]any, docID string, incoming map[string]map[string]bool, renamed map[string]string) {
	if len(renamed) == 0 {
		return
	}
	for field := range mergedCollections {
		for _, v := range model.A(merged[field]) {
			if incoming[field][model.S(model.M(v)["id"])] {
				rewriteRefs(v, docID, renamed)
			}
		}
	}
}

// knowledgeMerge resolves a Git conflict in one knowledge document from its
// three index stages, writing the merged page only when no record conflicts.
func (e *Engine) knowledgeMerge(r object) (any, error) {
	p := model.S(r["path"])
	parse := func(field string) (*model.Document, error) {
		raw := model.S(r[field])
		if raw == "" {
			return nil, nil
		}
		d, err := render.Parse([]byte(raw))
		if err != nil {
			return nil, fault.At(fault.Code(err), "", field, "merge input is not a valid knowledge document")
		}
		return d, nil
	}
	base, err := parse("base")
	if err != nil {
		return nil, err
	}
	ours, err := parse("ours")
	if err != nil {
		return nil, err
	}
	theirs, err := parse("theirs")
	if err != nil {
		return nil, err
	}
	if ours == nil || theirs == nil {
		return nil, fault.New("INVALID_MERGE", "both sides are required")
	}
	expectedPath, err := repositoryPath(ours)
	if err != nil {
		return nil, err
	}
	if expectedPath != p {
		return nil, fault.New("INVALID_MERGE", "the merge target is not this document's canonical path")
	}
	current, err := e.FS.Read(p, 3*canonical.MaxBytes)
	if err != nil {
		return nil, fault.New("INVALID_MERGE", "the conflicted working-tree file is unreadable")
	}
	if canonical.BytesHash(current) != model.S(r["expected_current_sha256"]) {
		return nil, fault.New("REVISION_CONFLICT", "the working-tree file changed after inspection")
	}
	merged, renamed, conflicts, err := MergeKnowledge(base, ours, theirs)
	if err != nil {
		return nil, err
	}
	if len(conflicts) > 0 {
		list := []any{}
		for _, c := range conflicts {
			list = append(list, object{"field": c.Field, "symbol": c.Symbol, "reason": c.Reason})
		}
		return object{"merged": false, "conflicts": list, "next_action": "Resolve these records on one side, then merge again; nothing was written."}, nil
	}
	b, err := render.Render(merged)
	if err != nil {
		return nil, err
	}
	renames := object{}
	for from, to := range renamed {
		renames[from] = to
	}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: p, Before: current, After: b}},
		map[string]any{"mode": "knowledge-merge", "path": p, "renamed": renames})
	if err != nil {
		return nil, err
	}
	out := mutationResult(o)
	out["merged"] = true
	out["renamed"] = renames
	return out, nil
}

func repositoryPath(d *model.Document) (string, error) {
	contract, ok := kind.Lookup(d.Kind())
	if !ok {
		return "", fault.New("INVALID_MERGE", "unknown kind")
	}
	return contract.Directory + "/" + model.S(d.Data["slug"]) + ".html", nil
}
