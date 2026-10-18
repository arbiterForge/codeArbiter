package operations

import (
	"strings"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
)

// recordPrerequisite stores the caller's account of an ordinary tool result or
// conversation. It does not execute the source, claim host attestation, update
// legacy authority flags, or dispatch reviewers. Older observations remain in
// the existing transaction before-images rather than a second history store.
func (e *Engine) recordPrerequisite(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	id := model.S(r["prerequisite"])
	record, ok := d.Symbols.ByID[id]
	if !ok || record.Retired || record.Kind != "prerequisites" {
		return nil, fault.New("UNKNOWN_PREREQUISITE", "prerequisite is absent or retired")
	}
	kind := model.S(record.Value["kind"])
	if kind != "fact" && kind != "decision" {
		return nil, fault.New("PREREQUISITE_KIND_REQUIRED", "classify this prerequisite as a fact or decision before recording its result")
	}
	reported := model.M(r["observation"])
	if strings.TrimSpace(model.S(reported["summary"])) == "" || strings.TrimSpace(model.S(reported["source"])) == "" {
		return nil, fault.New("INVALID_OBSERVATION", "record a nonblank result and where it came from")
	}
	if kind == "decision" && model.S(reported["outcome"]) != "unknown" && model.S(reported["origin"]) != "user_statement" {
		return nil, fault.New("DECISION_SOURCE_REQUIRED", "a tool result or agent opinion cannot be recorded as the user's resolved choice")
	}
	hash, err := model.PrerequisiteDefinition(record.Value)
	if err != nil {
		return nil, err
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	ex := model.M(next.Data["execution"])
	observations := model.M(ex["prerequisite_observations"])
	if observations == nil {
		observations = object{}
		ex["prerequisite_observations"] = observations
	}
	observations[id] = object{
		"outcome": reported["outcome"], "summary": reported["summary"], "source": reported["source"],
		"origin": reported["origin"], "provenance": "caller_reported",
		"recorded_at": time.Now().UTC().Format(time.RFC3339), "definition_sha256": hash,
	}
	next.Data["schema_version"] = model.SchemaVersion
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}

// finishScope records a completed implementation batch, independently of any
// test/review claim. Real unfinished work and recorded stops cannot disappear
// under a completion label. Actual evidence remains separately assessable.
func (e *Engine) finishScope(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	id := model.S(r["scope"])
	cp, ok := d.Symbols.ByID[id]
	if !ok || cp.Retired || cp.Kind != "checkpoints" {
		return nil, fault.New("UNKNOWN_SCOPE", "scope is absent or retired")
	}
	if strings.TrimSpace(model.S(r["reason"])) == "" {
		return nil, fault.New("REASON_REQUIRED", "describe the completed implementation batch")
	}
	ids := model.Strings(cp.Value["tasks"])
	if len(ids) == 0 {
		return nil, fault.New("SCOPE_EMPTY", "there is no implementation work to mark complete")
	}
	for _, task := range ids {
		switch model.S(state(d, task)["state"]) {
		case "IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED":
		default:
			return nil, fault.New("SCOPE_UNFINISHED", "scope member has unfinished or stopped work: "+task)
		}
	}
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	for _, task := range ids {
		s := state(next, task)
		if model.S(s["state"]) == "ACCEPTED" {
			continue
		}
		s["state"] = "DONE"
		s["reason"] = model.S(r["reason"]) + " Implementation completion only; verification and review are not assessed."
	}
	next.Data["schema_version"] = model.SchemaVersion
	next.Data["revision"] = d.Revision() + 1
	next, err = render.Prepare(next.Data)
	if err != nil {
		return nil, err
	}
	return e.save(r, entry, next)
}
