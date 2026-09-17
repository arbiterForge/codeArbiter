// Package validate checks artifact semantics without asserting that prose is
// correct or that an approval is authentic. Workflow authority is checked by
// operations against receipt contents, never by this package.
package validate

import (
	"fmt"
	"net/url"
	"path"
	"regexp"
	"strings"
	"time"
	"unicode"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

const MaxReadyRecordBytes = 12 * 1024

var drive = regexp.MustCompile(`^[a-zA-Z]:`)

// Path accepts portable, slash-separated repository paths, not globs.
func Path(s string, allowDot bool) bool {
	if s == "." {
		return allowDot
	}
	if s == "" || strings.HasPrefix(s, "/") || drive.MatchString(s) || strings.ContainsAny(s, `\:*?<>|"`) || path.Clean(s) != s {
		return false
	}
	for _, r := range s {
		if unicode.IsControl(r) {
			return false
		}
	}
	for _, p := range strings.Split(s, "/") {
		if p == "" || p == "." || p == ".." || strings.HasSuffix(p, ".") || strings.HasSuffix(p, " ") {
			return false
		}
		u := strings.ToUpper(strings.SplitN(p, ".", 2)[0])
		if u == "CON" || u == "PRN" || u == "AUX" || u == "NUL" || regexp.MustCompile(`^(COM|LPT)[1-9]$`).MatchString(u) {
			return false
		}
	}
	return true
}
func Companion(s, kind string) bool {
	if s == "" {
		return true
	}
	if strings.HasPrefix(s, "../") {
		expected := "../plans/"
		if kind == "plan" {
			expected = "../specs/"
		}
		if !strings.HasPrefix(s, expected) {
			return false
		}
		s = strings.TrimPrefix(s, expected)
	}
	return Path(s, false) && !strings.Contains(s, "/") && strings.HasSuffix(s, ".html")
}
func Glob(s string) bool {
	if s == "" || strings.HasPrefix(s, "/") || strings.ContainsAny(s, `\:`) {
		return false
	}
	for _, p := range strings.Split(s, "/") {
		if p == ".." || p == "." || p == "" {
			return false
		}
	}
	for _, r := range s {
		if unicode.IsControl(r) {
			return false
		}
	}
	_, e := path.Match(s, "probe")
	return e == nil
}
func nonblank(v any) bool { return strings.TrimSpace(model.S(v)) != "" }
func add(es *[]fault.Error, code, id, field, msg string) {
	if len(*es) < 128 {
		*es = append(*es, fault.Error{Code: code, Symbol: id, Field: field, Message: msg})
	}
}
func first(es []fault.Error) error {
	if len(es) > 0 {
		return &es[0]
	}
	return nil
}
func Structural(d *model.Document) []fault.Error {
	var es []fault.Error
	n := d.Norm()
	ref := func(s, id, field, kind string) {
		r, ok := d.Symbols.ByID[s]
		if !ok || r.Retired || (kind != "" && r.Kind != kind) {
			add(&es, "DANGLING_REFERENCE", id, field, "reference does not name an active "+kind+" record: "+s)
		}
	}
	for _, r := range d.Symbols.ByID {
		for _, f := range []string{"source_refs", "intent_refs", "constraint_refs", "binding_decision_refs"} {
			kind := map[string]string{"source_refs": "sources", "intent_refs": "scope", "constraint_refs": "constraints", "binding_decision_refs": "decisions"}[f]
			for _, s := range model.Strings(r.Value[f]) {
				ref(s, r.ID, f, kind)
			}
		}
		for _, s := range model.Strings(r.Value["refs"]) {
			ref(s, r.ID, "refs", "")
		}
	}
	// Some blocks are not individually addressable; still validate their references.
	var visit func(any)
	visit = func(v any) {
		switch x := v.(type) {
		case map[string]any:
			if model.S(x["type"]) == "table" {
				width := len(model.A(x["columns"]))
				for _, row := range model.A(x["rows"]) {
					if len(model.A(row)) != width {
						add(&es, "INVALID_TABLE", "", "rows", "table row width must equal columns")
					}
				}
			}
			for _, s := range model.Strings(x["refs"]) {
				ref(s, "", "refs", "")
			}
			for k, v := range x {
				if k != "refs" {
					visit(v)
				}
			}
		case []any:
			for _, v := range x {
				visit(v)
			}
		}
	}
	visit(n["sections"])
	for _, v := range model.A(n["open_decisions"]) {
		r := model.M(v)
		id := model.S(r["id"])
		for _, s := range model.Strings(r["affects"]) {
			ref(s, id, "affects", "")
		}
		if model.S(r["status"]) == "resolved" && !nonblank(r["resolution"]) {
			add(&es, "INVALID_DECISION", id, "resolution", "resolved decision needs its resolution")
		}
	}
	for _, v := range model.A(n["retired_symbols"]) {
		r := model.M(v)
		id := model.S(r["id"])
		if model.I(r["retired_in_revision"]) > d.Revision() {
			add(&es, "INVALID_RETIREMENT", id, "retired_in_revision", "retirement is later than this revision")
		}
		s := model.S(r["replacement_ref"])
		if s != "" {
			if a, b, e := symbol.Split(s); e == nil {
				if a == d.ID() {
					ref(b, id, "replacement_ref", "")
				}
			} else {
				ref(s, id, "replacement_ref", "")
			}
		}
	}
	for _, s := range model.Strings(n["governs"]) {
		if !Glob(s) {
			add(&es, "INVALID_PATH", "", "governs", "invalid repository glob")
		}
	}
	for _, v := range model.A(n["constraints"]) {
		r := model.M(v)
		for _, s := range model.Strings(r["applies_to"]) {
			if s != "all" {
				ref(s, model.S(r["id"]), "applies_to", "")
			}
		}
	}
	p := model.M(d.Data["presentation"])
	if !Companion(model.S(p["companion_path"]), d.Kind()) {
		add(&es, "INVALID_PATH", "", "presentation.companion_path", "companion must be a local HTML filename or the canonical sibling directory")
	}
	for _, v := range model.A(n["sources"]) {
		r := model.M(v)
		s := model.S(r["url"])
		if s != "" {
			u, e := url.Parse(s)
			if e != nil || u.Scheme != "https" || u.Host == "" || u.User != nil {
				add(&es, "INVALID_SOURCE", model.S(r["id"]), "url", "source URL must be HTTPS without user information")
			}
		}
	}
	if date := model.S(model.M(n["baseline"])["observed_date"]); date != "" {
		if _, e := time.Parse("2006-01-02", date); e != nil {
			add(&es, "INVALID_DATE", "", "baseline.observed_date", "invalid calendar date")
		}
	}
	if d.Kind() == "plan" {
		if policy := model.M(n["verification_inputs"]); policy != nil {
			for _, p := range model.Strings(policy["roots"]) {
				if !Path(p, true) || p == ".git" || strings.HasPrefix(p, ".git/") {
					add(&es, "INVALID_INPUT_POLICY", "", "verification_inputs.roots", "unsafe input root")
				}
			}
			for _, p := range model.Strings(policy["exclude_directories"]) {
				if !Path(p, false) || p == ".codearbiter" || strings.HasPrefix(p, ".codearbiter/") {
					add(&es, "INVALID_INPUT_POLICY", "", "verification_inputs.exclude_directories", "governance cannot be excluded")
				}
			}
		}
		es = append(es, planStructure(d)...)
	}
	// Deterministic diagnostics independent of map iteration.
	sortErrors(es)
	return es
}
func sortErrors(es []fault.Error) { // insertion sort; diagnostics are capped at 128
	for i := 1; i < len(es); i++ {
		for j := i; j > 0; j-- {
			a, b := es[j-1], es[j]
			if a.Symbol+"/"+a.Field+"/"+a.Message <= b.Symbol+"/"+b.Field+"/"+b.Message {
				break
			}
			es[j-1], es[j] = b, a
		}
	}
}
func planStructure(d *model.Document) []fault.Error {
	es := []fault.Error{}
	n := d.Norm()
	tasks := map[string]map[string]any{}
	cps := map[string]map[string]any{}
	owner := map[string]string{}
	cpOrder := map[string]int{}
	for _, v := range model.A(n["tasks"]) {
		r := model.M(v)
		tasks[model.S(r["id"])] = r
	}
	for _, v := range model.A(n["checkpoints"]) {
		r := model.M(v)
		id := model.S(r["id"])
		cps[id] = r
		cpOrder[id] = len(cpOrder)
		for _, t := range model.Strings(r["tasks"]) {
			if _, ok := tasks[t]; !ok {
				add(&es, "DANGLING_REFERENCE", id, "tasks", "checkpoint references absent task")
			}
			if _, ok := owner[t]; ok {
				add(&es, "INVALID_PARTITION", t, "checkpoint", "task appears in multiple checkpoints")
			}
			owner[t] = id
		}
	}
	for id, t := range tasks {
		cp := model.S(t["checkpoint"])
		if owner[id] != cp {
			add(&es, "INVALID_PARTITION", id, "checkpoint", "task must appear exactly once in its declared checkpoint")
		}
		if model.S(t["execution_scope"]) != cp {
			add(&es, "INVALID_SCOPE", id, "execution_scope", "v0.1.0 execution scope must equal checkpoint")
		}
		for _, s := range model.Strings(t["depends_on"]) {
			if _, ok := tasks[s]; !ok {
				add(&es, "DANGLING_REFERENCE", id, "depends_on", "task dependency does not exist")
			}
		}
		for _, v := range model.A(t["paths"]) {
			p := model.M(v)
			if !Path(model.S(p["path"]), false) {
				add(&es, "INVALID_PATH", id, "paths", "task path is not a portable repository path")
			}
		}
		for _, v := range model.A(t["verification"]) {
			c := model.M(v)
			if !Path(model.S(c["cwd"]), true) {
				add(&es, "INVALID_PATH", id, "verification.cwd", "working directory must be repo relative")
			}
			for _, a := range model.Strings(c["argv"]) {
				if strings.ContainsRune(a, 0) {
					add(&es, "INVALID_COMMAND", id, "verification.argv", "NUL is not a process argument")
				}
			}
		}
	}
	for id, cp := range cps {
		for _, s := range model.Strings(cp["depends_on"]) {
			if at, ok := cpOrder[s]; ok && at >= cpOrder[id] {
				add(&es, "CHECKPOINT_ORDER", id, "depends_on", "checkpoint dependency must appear earlier in declared order")
			}
			if _, ok := cps[s]; !ok {
				add(&es, "DANGLING_REFERENCE", id, "depends_on", "checkpoint dependency does not exist")
			}
		}
	}
	checkDAG := func(records map[string]map[string]any) {
		mark := map[string]int{}
		var walk func(string)
		walk = func(id string) {
			if mark[id] == 1 {
				add(&es, "DEPENDENCY_CYCLE", id, "depends_on", "dependency graph contains a cycle")
				return
			}
			if mark[id] == 2 {
				return
			}
			mark[id] = 1
			for _, dep := range model.Strings(records[id]["depends_on"]) {
				if _, ok := records[dep]; ok {
					walk(dep)
				}
			}
			mark[id] = 2
		}
		for id := range records {
			walk(id)
		}
	}
	checkDAG(tasks)
	checkDAG(cps)
	var cpAncestor func(string, string, map[string]bool) bool
	cpAncestor = func(cp, ancestor string, seen map[string]bool) bool {
		if seen[cp] {
			return false
		}
		seen[cp] = true
		for _, dep := range model.Strings(cps[cp]["depends_on"]) {
			if dep == ancestor || cpAncestor(dep, ancestor, seen) {
				return true
			}
		}
		return false
	}
	for id, t := range tasks {
		for _, dep := range model.Strings(t["depends_on"]) {
			if other, ok := tasks[dep]; ok {
				a, b := model.S(t["checkpoint"]), model.S(other["checkpoint"])
				if a != b && !cpAncestor(a, b, map[string]bool{}) {
					add(&es, "CHECKPOINT_ORDER", id, "depends_on", "cross-scope dependency must precede this checkpoint")
				}
			}
		}
	}
	ex := model.M(d.Data["execution"])
	for id := range model.M(ex["scopes"]) {
		if _, ok := cps[id]; !ok {
			add(&es, "ORPHAN_STATE", id, "execution.scopes", "scope has no checkpoint definition")
		}
	}
	states := model.M(ex["tasks"])
	for id := range tasks {
		if _, ok := states[id]; !ok {
			add(&es, "MISSING_STATE", id, "execution.tasks", "task state is missing")
		}
	}
	for id := range states {
		if _, ok := tasks[id]; !ok {
			add(&es, "ORPHAN_STATE", id, "execution.tasks", "state has no task definition")
		}
	}
	prs := map[string]bool{}
	ps := model.M(ex["prerequisites"])
	pe := model.M(ex["prerequisite_evidence"])
	for _, v := range model.A(n["prerequisites"]) {
		id := model.S(model.M(v)["id"])
		prs[id] = true
		if _, ok := ps[id]; !ok {
			add(&es, "MISSING_STATE", id, "execution.prerequisites", "prerequisite state missing")
		}
		if model.S(ps[id]) == "satisfied" && len(model.A(pe[id])) == 0 {
			add(&es, "MISSING_EVIDENCE", id, "execution.prerequisite_evidence", "satisfied prerequisite needs a receipt reference")
		}
	}
	for id := range ps {
		if !prs[id] {
			add(&es, "ORPHAN_STATE", id, "execution.prerequisites", "unknown prerequisite")
		}
	}
	for id := range pe {
		if !prs[id] {
			add(&es, "ORPHAN_STATE", id, "execution.prerequisite_evidence", "unknown prerequisite evidence")
		}
	}
	return es
}
func Ready(d, spec *model.Document) []fault.Error {
	es := Structural(d)
	n := d.Norm()
	need := func(r map[string]any, fs ...string) {
		id := model.S(r["id"])
		for _, f := range fs {
			v := r[f]
			ok := false
			switch x := v.(type) {
			case string:
				ok = strings.TrimSpace(x) != ""
			case []any:
				ok = len(x) > 0
				for _, z := range x {
					if s, is := z.(string); is && strings.TrimSpace(s) == "" {
						ok = false
					}
				}
			case map[string]any:
				ok = len(x) > 0
			}
			if !ok {
				add(&es, "NOT_READY", id, f, "required readiness field is absent or empty")
			}
		}
	}
	need(n, "title", "summary")
	for _, r := range d.Symbols.ByID {
		if r.Retired {
			continue
		}
		// Structural drafts permit empty text; readiness must not mistake the
		// presence of a scope/task record for a usable behavioral contract.
		switch r.Kind {
		case "scope", "non_goals", "constraints":
			need(r.Value, "statement")
		case "tasks", "checkpoints", "sources":
			need(r.Value, "title")
		case "decisions":
			need(r.Value, "topic", "choice", "rationale")
		}
		b, e := canonical.Marshal(r.Value)
		if e != nil || len(b) > MaxReadyRecordBytes {
			add(&es, "RECORD_TOO_LARGE", r.ID, "", "ready record exceeds 12 KiB; split it into smaller records")
		}
	}
	for _, v := range model.A(n["open_decisions"]) {
		r := model.M(v)
		if r["blocking"] == true && model.S(r["status"]) != "resolved" {
			add(&es, "OPEN_BLOCKER", model.S(r["id"]), "status", "blocking decision is unresolved")
		}
	}
	if d.Kind() == "spec" {
		need(model.M(n["intent"]), "problem", "caller", "outcome")
		need(model.M(n["approach"]), "choice", "tradeoff")
		need(n, "scope", "criteria")
		covered := map[string]bool{}
		for _, v := range model.A(n["criteria"]) {
			r := model.M(v)
			need(r, "kind", "obligation", "statement", "intent_refs", "guarantees", "scenarios", "verification", "applicability")
			for _, s := range model.Strings(r["intent_refs"]) {
				covered[s] = true
			}
			app := model.M(r["applicability"])
			need(app, "mode", "rationale")
			mode := model.S(app["mode"])
			if mode == "conditional" {
				need(r, "preconditions", "trigger")
			}
			if mode == "not_applicable" {
				add(&es, "NOT_READY", model.S(r["id"]), "applicability", "active criterion cannot be not applicable; retire or move it out of scope explicitly")
			}
			for _, s := range model.A(r["scenarios"]) {
				need(model.M(s), "given", "when", "then")
			}
			need(model.M(r["verification"]), "method", "planned_target", "oracle", "negative_control")
		}
		for _, v := range model.A(n["scope"]) {
			r := model.M(v)
			if !covered[model.S(r["id"])] {
				add(&es, "UNCOVERED_SCOPE", model.S(r["id"]), "", "scope item has no criterion")
			}
		}
	} else {
		need(n, "tasks", "checkpoints")
		for _, v := range model.A(n["tasks"]) {
			r := model.M(v)
			need(r, "paths", "criterion_refs", "steps", "verification", "done_when", "rollback")
			for _, c := range model.A(r["verification"]) {
				def := model.M(c)
				need(def, "argv", "assertion")
				if IsTestCommand(model.Strings(def["argv"])) && len(model.Strings(def["required_tests"])) == 0 {
					add(&es, "NO_TESTS_DECLARED", model.S(r["id"]), "verification.required_tests", "test commands require named outcomes; exit zero alone is insufficient")
				}
			}
			for _, p := range model.A(r["paths"]) {
				if !InputIncludes(n, model.S(model.M(p)["path"])) {
					add(&es, "UNCOVERED_INPUT", model.S(r["id"]), "verification_inputs", "verification policy omits declared task path: "+model.S(model.M(p)["path"]))
				}
			}
		}
		es = append(es, Binding(d, spec)...)
	}
	sortErrors(es)
	return es
}
func Binding(plan, spec *model.Document) []fault.Error {
	es := []fault.Error{}
	ref := model.M(plan.Norm()["spec_ref"])
	if spec == nil {
		return []fault.Error{{Code: "SPEC_REQUIRED", Message: "plan validation requires the referenced spec"}}
	}
	if spec.Kind() != "spec" || spec.ID() != model.S(ref["artifact_id"]) || spec.NormHash() != model.S(ref["normative_sha256"]) {
		return []fault.Error{{Code: "STALE_SPEC", Message: "plan binding does not match the referenced spec"}}
	}
	covered := map[string]bool{}
	disposed := map[string]bool{}
	check := func(s, task string) {
		a, b, e := symbol.Split(s)
		r, ok := spec.Symbols.ByID[b]
		if e != nil || a != spec.ID() || !ok || r.Kind != "criteria" || r.Retired {
			add(&es, "INVALID_CRITERION_REF", task, "criterion_refs", "reference does not name an active criterion in the bound spec")
			return
		}
		covered[b] = true
	}
	for _, v := range model.A(plan.Norm()["tasks"]) {
		r := model.M(v)
		for _, s := range model.Strings(r["criterion_refs"]) {
			check(s, model.S(r["id"]))
		}
	}
	for _, v := range model.A(plan.Norm()["criterion_dispositions"]) {
		r := model.M(v)
		a, b, e := symbol.Split(model.S(r["criterion_ref"]))
		c, ok := spec.Symbols.ByID[b]
		if e != nil || a != spec.ID() || !ok || c.Kind != "criteria" || c.Retired {
			add(&es, "INVALID_CRITERION_REF", "", "criterion_dispositions", "disposition references unknown criterion")
			continue
		}
		if disposed[b] || covered[b] {
			add(&es, "DUPLICATE_DISPOSITION", b, "", "criterion cannot be both covered and disposed or disposed twice")
		}
		disposed[b] = true
		if model.S(c.Value["obligation"]) == "must" {
			add(&es, "UNCOVERED_CRITERION", b, "", "mandatory criterion cannot be disposed")
		}
		if !nonblank(r["rationale"]) {
			add(&es, "NOT_READY", b, "rationale", "disposition needs rationale")
		}
	}
	for _, v := range model.A(spec.Norm()["criteria"]) {
		r := model.M(v)
		id := model.S(r["id"])
		if !covered[id] && !disposed[id] {
			add(&es, "UNCOVERED_CRITERION", id, "", "criterion requires coverage or a permitted explicit disposition")
		}
	}
	sortErrors(es)
	return es
}
func Error(es []fault.Error) error    { return first(es) }
func Explain(es []fault.Error) string { return fmt.Sprintf("%d validation diagnostic(s)", len(es)) }
