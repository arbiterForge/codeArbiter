package operations

import (
	"strings"
	"time"

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
		"provenance":              "caller_reported",
		"recorded_at":             time.Now().UTC().Format(time.RFC3339),
		"task_subject_sha256":     definitionHash,
		"source_normative_sha256": spec.Doc.NormHash(),
		"history_trimmed":         trimmed,
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
