package operations

import (
	"strings"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// recordTaskCheck stores an inert caller-reported command observation, never a
// host-attested verification receipt. No command is executed by this path.
// Before-images in the existing journal retain earlier observations.
func (e *Engine) recordTaskCheck(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "command observations require a plan")
	}
	id := model.S(r["task"])
	task, ok := d.Symbols.ByID[id]
	if !ok || task.Retired || task.Kind != "tasks" {
		return nil, fault.New("UNKNOWN_TASK", "cannot record a check for an absent or retired task")
	}
	check := model.M(r["check"])
	cwd := model.S(check["cwd"])
	if !validate.Path(cwd, true) || strings.TrimSpace(model.S(check["summary"])) == "" ||
		strings.TrimSpace(model.S(check["source"])) == "" {
		return nil, fault.New("INVALID_CHECK", "command observation requires a safe working directory, source and summary")
	}
	for _, arg := range model.Strings(check["argv"]) {
		if strings.ContainsRune(arg, 0) {
			return nil, fault.New("INVALID_COMMAND", "command observation cannot contain NUL arguments")
		}
	}
	// Unknown/skipped checks may not invent an exit code. Passed reported
	// commands need a concrete code; this is still not independent proof.
	outcome := model.S(check["outcome"])
	exit, hasExit := check["exit_code"]
	if (outcome == "unknown" || outcome == "skip") && hasExit {
		return nil, fault.New("INVALID_CHECK", "unrun or skipped check cannot assert an exit code")
	}
	if outcome == "pass" && !hasExit {
		return nil, fault.New("INVALID_CHECK", "reported pass needs the observed exit code")
	}
	planned := model.A(task.Value["verification"])
	if indexRaw, declared := check["command_index"]; declared {
		index, ok := model.NativeInt(model.I(indexRaw))
		if !ok || index >= len(planned) {
			return nil, fault.New("UNKNOWN_CHECK", "declared verification command index does not exist")
		}
		definition := model.M(planned[index])
		if cwd != model.S(definition["cwd"]) || !equalCheckArguments(check["argv"], definition["argv"]) {
			return nil, fault.New("CHECK_MISMATCH", "reported command does not match the selected plan verification definition")
		}
		if outcome == "pass" && model.I(exit) != model.I(definition["expected_exit"]) {
			return nil, fault.New("CHECK_MISMATCH", "reported exit code differs from the declared successful code")
		}
	} else if outcome == "pass" && model.I(exit) != 0 {
		return nil, fault.New("CHECK_MISMATCH", "an ad-hoc success needs exit code zero; failing commands remain recordable")
	}
	spec, err := e.Catalog.Spec(d)
	if err != nil {
		return nil, err
	}
	definitionHash, err := model.TaskCheckDefinition(task.Value)
	if err != nil {
		return nil, err
	}
	criteriaHash, err := model.TaskCriterionSubject(spec.Doc, task.Value)
	if err != nil {
		return nil, fault.New("DANGLING_REFERENCE", "task criterion does not resolve in the current specification")
	}
	scopedHash, scopeReason := scopedInputDigest(e.FS, task.Value)
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	ex := model.M(next.Data["execution"])
	all := model.M(ex["task_check_observations"])
	if all == nil {
		all = object{}
		ex["task_check_observations"] = all
	}
	history := model.A(all[id])
	trimmed := false
	for _, previous := range history {
		if model.M(previous)["history_trimmed"] == true {
			trimmed = true
			break
		}
	}
	if len(history) >= 16 {
		// Keep the most recent sixteen; the transaction before-image retains
		// earlier results and is not rewritten. No silent reviewer dispatch.
		history = history[len(history)-15:]
		trimmed = true
	}
	recorded := object{
		"argv": check["argv"], "cwd": cwd,
		"outcome": outcome, "summary": check["summary"],
		"source": check["source"], "origin": check["origin"],
		"provenance":               "caller_reported",
		"recorded_at":              time.Now().UTC().Format(time.RFC3339),
		"recording_operation_id":   r["operation_id"],
		"task_subject_sha256":      definitionHash,
		"source_normative_sha256":  spec.Doc.NormHash(),
		"criterion_subject_sha256": criteriaHash,
		"history_trimmed":          trimmed,
	}
	if scopedHash != "" {
		recorded["scoped_inputs_sha256"] = scopedHash
	} else {
		recorded["scope_unassessed_reason"] = scopeReason
	}
	for _, optional := range []string{"command_index", "exit_code", "output_excerpt"} {
		if v, exists := check[optional]; exists {
			recorded[optional] = v
		}
	}
	all[id] = append(history, recorded)
	next.Data["schema_version"] = model.SchemaVersion
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}

func equalCheckArguments(a, b any) bool {
	left, right := model.Strings(a), model.Strings(b)
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
}

// assessTaskChecks applies the same partial source scope to context and
// verification summaries. It does not turn caller reports into attestations.
func (e *Engine) assessTaskChecks(d, spec *model.Document, id string) ([]any, bool) {
	checks, trimmed := model.TaskCheckAssessments(d, spec, id)
	if len(checks) == 0 {
		return checks, trimmed
	}
	digest, reason := scopedInputDigest(e.FS, d.Symbols.ByID[id].Value)
	for _, value := range checks {
		note := model.M(value)
		stored := model.S(note["recorded_scoped_inputs_sha256"])
		status := "unassessed"
		switch {
		case stored == "":
			if model.S(note["scope_reason"]) == "" {
				note["scope_reason"] = "historical_unbound_report"
			}
		case digest == "":
			note["scope_reason"] = reason
		case stored != digest:
			status = "scoped_changed"
		default:
			status = "scoped_unchanged"
		}
		note["worktree_freshness"] = status
		note["scope_complete"] = false
	}
	return checks, trimmed
}

// checkConflicts keeps failures until a later applicable pass for the same
// declared command. Skips, unknown outcomes and ad-hoc checks do not resolve
// them. Unbound failures are disclosed as uncertain, never silently passed.
func (e *Engine) checkConflicts(d, spec *model.Document, id string, covered map[string]bool) object {
	checks, trimmed := e.assessTaskChecks(d, spec, id)
	entries := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])[id])
	failures := map[int64]object{}
	decisive := map[int64]bool{}
	ignored, superseded := 0, 0
	for position, value := range checks {
		hash, _ := canonical.Hash(entries[position])
		if covered[hash] {
			// The attested full command result followed this captured report
			// boundary. It also covers any older trimmed report history.
			failures = map[int64]object{}
			trimmed = false
			superseded++
			continue
		}
		note := model.M(value)
		if note["definition_current"] != true || note["worktree_freshness"] == "scoped_changed" {
			ignored++
			continue
		}
		indices := []int64{}
		declared := note["declared_command"] == true
		if declared {
			indices = append(indices, model.I(note["command_index"]))
		} else if note["reported_outcome"] == "fail" {
			for index, definition := range model.A(d.Symbols.ByID[id].Value["verification"]) {
				command := model.M(definition)
				if note["cwd"] == command["cwd"] && equalCheckArguments(note["argv"], command["argv"]) {
					indices = append(indices, int64(index))
				}
			}
		}
		if len(indices) == 0 {
			ignored++
			continue
		}
		for _, index := range indices {
			switch note["reported_outcome"] {
			case "fail":
				failure := object{
					"reported_outcome": "fail", "recorded_at": note["recorded_at"],
					"worktree_freshness": note["worktree_freshness"], "scope_reason": note["scope_reason"],
					"provenance": "caller_reported", "evidence_assessed": false, "scope_complete": false,
				}
				if declared {
					failure["command_index"] = index
				} else {
					failure["matched_command_index"], failure["command_match"] = index, "exact_argv_cwd"
				}
				failures[index] = failure
				decisive[index] = true
			case "pass":
				if note["worktree_freshness"] == "scoped_unchanged" {
					delete(failures, index)
					decisive[index] = true
				}
			}
		}
	}
	conflicts := []any{}
	unassessedHistory := false
	for index := range model.A(d.Symbols.ByID[id].Value["verification"]) {
		if failure, ok := failures[int64(index)]; ok {
			conflicts = append(conflicts, failure)
		}
		unassessedHistory = unassessedHistory || (trimmed && !decisive[int64(index)])
	}
	return object{"has_conflicting_check_reports": len(conflicts) != 0,
		"conflicting_check_reports": conflicts, "check_reports_total": int64(len(checks)),
		"check_reports_ignored": int64(ignored), "check_reports_superseded": int64(superseded),
		"check_history_bounded":    len(checks) > 0 && model.M(checks[len(checks)-1])["history_trimmed"] == true,
		"check_history_unassessed": unassessedHistory}
}

// verifiedReportBoundary uses only a retained, currently applicable successful
// verification. Older receipt formats without a report boundary remain valid
// evidence but do not establish an ordering against caller-reported checks.
func (e *Engine) verifiedReportBoundary(d, spec *model.Document, id, input string) map[string]bool {
	covered := map[string]bool{}
	for _, ref := range model.Strings(state(d, id)["evidence_refs"]) {
		r, err := authority.Load(e.FS, ref)
		if err != nil || model.S(r.Data["kind"]) != "verification" || evidence.TaskPayload(r, d, spec, d.Symbols.ByID[id].Value, input) != nil {
			continue
		}
		context, err := evidence.ReviewContext(e.FS, r)
		if err != nil {
			continue
		}
		for _, hash := range model.Strings(context["task_check_report_sha256"]) {
			covered[hash] = true
		}
	}
	return covered
}
