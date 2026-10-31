package operations

import (
	"encoding/json"
	"path"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

// globalKnowledge lists record types that apply across the repository when
// they declare no path scope: a test command, a project-wide exclusion or
// convention. Unscoped facts and components stay out unless a task asks.
var globalKnowledge = map[string]bool{"command": true, "constraint": true, "exclusion": true, "convention": true}

// selectionRank orders what a task sees first when the budget is tight:
// constraints and exclusions before path matches, then commands and links.
var selectionRank = map[string]int{"constraint": 0, "exclusion": 0, "path": 1, "global": 2, "linked": 3}

// segmentsMatch matches slash paths with path.Match per segment, where a "**"
// segment matches any number of segments.
func segmentsMatch(pattern, name []string) bool {
	if len(pattern) == 0 {
		return len(name) == 0
	}
	if pattern[0] == "**" {
		for i := 0; i <= len(name); i++ {
			if segmentsMatch(pattern[1:], name[i:]) {
				return true
			}
		}
		return false
	}
	if len(name) == 0 {
		return false
	}
	if ok, _ := path.Match(pattern[0], name[0]); !ok {
		return false
	}
	return segmentsMatch(pattern[1:], name[1:])
}

func literalPrefix(p string) string {
	if i := strings.IndexAny(p, "*?["); i >= 0 {
		p = p[:i]
	}
	return p
}

// scopeOverlaps reports whether a knowledge scope and a task path can name the
// same file. Either side may be a glob; a plain directory covers its contents.
func scopeOverlaps(scope, task string) bool {
	s, t := strings.Split(scope, "/"), strings.Split(task, "/")
	if segmentsMatch(s, t) || segmentsMatch(t, s) {
		return true
	}
	if !strings.ContainsAny(scope, "*?[") && strings.HasPrefix(task, strings.TrimSuffix(scope, "/")+"/") {
		return true
	}
	if !strings.ContainsAny(task, "*?[") && strings.HasPrefix(scope, strings.TrimSuffix(task, "/")+"/") {
		return true
	}
	// Two globs overlap when one literal prefix contains the other.
	a, b := literalPrefix(scope), literalPrefix(task)
	return strings.ContainsAny(scope, "*?[") && strings.ContainsAny(task, "*?[") && (strings.HasPrefix(a, b) || strings.HasPrefix(b, a))
}

type knowledgeCandidate struct {
	ref, reason string
	record      map[string]any
}

// taskKnowledge selects knowledge records relevant to a task: records scoped
// to the task's paths, global constraints and commands, and one explicit hop
// of their related references. It reads stored records only. It does not run
// commands, scan source files, or decide whether the task may proceed.
func (e *Engine) taskKnowledge(task map[string]any, budget int) object {
	entries, unreadable, err := repository.LoadKnowledge(e.FS)
	out := object{"knowledge": []any{}, "knowledge_omitted": []any{}, "knowledge_omitted_count": int64(0),
		"knowledge_unreadable": []any{}, "knowledge_unresolved_references": []any{},
		"knowledge_unresolved_references_count": int64(0), "knowledge_unmatched_records": int64(0)}
	if err != nil {
		out["knowledge_unreadable"] = []any{object{"path": ".codearbiter/context", "code": "LIST_FAILED"}}
		return out
	}
	for _, u := range unreadable {
		out["knowledge_unreadable"] = append(model.A(out["knowledge_unreadable"]), object{"path": u.Path, "code": u.Code})
	}
	docs := map[string]repository.Entry{}
	for _, entry := range entries {
		docs[entry.Doc.ID()] = entry
	}
	taskPaths := []string{}
	for _, p := range model.A(task["paths"]) {
		taskPaths = append(taskPaths, model.S(model.M(p)["path"]))
	}
	explicit := map[string]bool{}
	for _, ref := range model.Strings(task["knowledge_refs"]) {
		explicit[ref] = true
	}
	foundExplicit := map[string]bool{}
	selected := map[string]bool{}
	candidates := []knowledgeCandidate{}
	unmatched := int64(0)
	for _, entry := range entries {
		for _, v := range model.A(entry.Doc.Norm()["records"]) {
			r := model.M(v)
			ref := entry.Doc.ID() + "#" + model.S(r["id"])
			if explicit[ref] {
				foundExplicit[ref] = true
			}
			typ := model.S(r["type"])
			scope := model.Strings(model.M(r["scope"])["paths"])
			reason := ""
			for _, s := range scope {
				for _, t := range taskPaths {
					if scopeOverlaps(s, t) {
						reason = "path"
					}
				}
			}
			if reason == "" && len(scope) == 0 && globalKnowledge[typ] {
				reason = "global"
			}
			if reason == "" && explicit[ref] {
				reason = "linked"
			}
			if reason != "" && (typ == "constraint" || typ == "exclusion") {
				reason = typ
			}
			if reason == "" {
				unmatched++
				continue
			}
			selected[ref] = true
			candidates = append(candidates, knowledgeCandidate{ref, reason, r})
		}
	}
	// One explicit hop: follow related references of selected records only.
	unresolved := []any{}
	for ref := range explicit {
		if !foundExplicit[ref] {
			unresolved = append(unresolved, ref)
			selected[ref] = true
		}
	}
	for _, c := range append([]knowledgeCandidate{}, candidates...) {
		home, _, _ := symbol.Split(c.ref)
		for _, rel := range model.Strings(c.record["related_refs"]) {
			target := rel
			if _, _, e := symbol.Split(rel); e != nil {
				target = home + "#" + rel
			}
			if selected[target] {
				continue
			}
			a, b, _ := symbol.Split(target)
			entry, ok := docs[a]
			rec, found := symbol.Record{}, false
			if ok {
				rec, found = entry.Doc.Symbols.ByID[b]
			}
			if !found || rec.Retired || rec.Kind != "records" {
				unresolved = append(unresolved, target)
				selected[target] = true
				continue
			}
			selected[target] = true
			candidates = append(candidates, knowledgeCandidate{target, "linked", rec.Value})
			unmatched--
		}
	}
	sort.Slice(unresolved, func(i, j int) bool { return model.S(unresolved[i]) < model.S(unresolved[j]) })
	// Stable order: rank, then reference.
	sort.SliceStable(candidates, func(i, j int) bool {
		a, b := candidates[i], candidates[j]
		if selectionRank[a.reason] != selectionRank[b.reason] {
			return selectionRank[a.reason] < selectionRank[b.reason]
		}
		return a.ref < b.ref
	})
	initial, _ := json.Marshal(out)
	used := len(initial)
	// Leave room for counts growing in decimal and for the caller's wrapper.
	limit := budget - 64
	for _, c := range candidates {
		item := object{"ref": c.ref, "selection_reason": c.reason}
		for k, v := range c.record {
			item[k] = v
		}
		b, _ := json.Marshal(item)
		separator := 0
		if len(model.A(out["knowledge"])) > 0 {
			separator = 1
		}
		if used+len(b)+separator > limit {
			// Never truncate a record: name it so it can be read on its own.
			out["knowledge_omitted_count"] = model.I(out["knowledge_omitted_count"]) + 1
			omitted := object{"ref": c.ref, "title": c.record["title"], "reason": "response budget"}
			short, _ := json.Marshal(omitted)
			separator = 0
			if len(model.A(out["knowledge_omitted"])) > 0 {
				separator = 1
			}
			if used+len(short)+separator <= limit {
				used += len(short) + separator
				out["knowledge_omitted"] = append(model.A(out["knowledge_omitted"]), omitted)
			}
			continue
		}
		used += len(b) + separator
		out["knowledge"] = append(model.A(out["knowledge"]), item)
	}
	for _, ref := range unresolved {
		out["knowledge_unresolved_references_count"] = model.I(out["knowledge_unresolved_references_count"]) + 1
		b, _ := json.Marshal(ref)
		separator := 0
		if len(model.A(out["knowledge_unresolved_references"])) > 0 {
			separator = 1
		}
		if used+len(b)+separator <= limit {
			used += len(b) + separator
			out["knowledge_unresolved_references"] = append(model.A(out["knowledge_unresolved_references"]), ref)
		}
	}
	if unmatched < 0 {
		unmatched = 0
	}
	out["knowledge_unmatched_records"] = unmatched
	return out
}
