package validate

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

// knowledgeStructure checks the record shapes of repository knowledge and
// decomposition documents. A draft may hold unknown or proposed material
// without sources; only a source-observed claim must cite what it observed.
// Nothing here makes a record authoritative policy or proof that a command ran.
func knowledgeStructure(d *model.Document) []fault.Error {
	var es []fault.Error
	n := d.Norm()
	for _, v := range model.A(n["records"]) {
		r := model.M(v)
		id, typ := model.S(r["id"]), model.S(r["type"])
		if model.S(r["basis"]) == "source-observed" && len(model.A(r["source_refs"])) == 0 {
			add(&es, "MISSING_SOURCE", id, "source_refs", "a source-observed record must cite the source it observed")
		}
		for _, p := range model.Strings(model.M(r["scope"])["paths"]) {
			if !Glob(p) {
				add(&es, "INVALID_PATH", id, "scope.paths", "invalid repository glob")
			}
		}
		for _, ref := range model.Strings(r["related_refs"]) {
			if a, b, e := symbol.Split(ref); e == nil {
				if a == d.ID() {
					if rec, ok := d.Symbols.ByID[b]; !ok || rec.Retired {
						add(&es, "DANGLING_REFERENCE", id, "related_refs", "reference does not name an active record: "+ref)
					}
				}
				// A reference into another document is resolved when it is
				// read; a missing target is reported then, not refused here.
				continue
			}
			if rec, ok := d.Symbols.ByID[ref]; !ok || rec.Retired {
				add(&es, "DANGLING_REFERENCE", id, "related_refs", "reference does not name an active record: "+ref)
			}
		}
		command := model.M(r["command"])
		if (typ == "command") != (command != nil) {
			add(&es, "INVALID_RECORD", id, "command", "command details belong to, and are required by, command records")
		}
		if command != nil && !Path(model.S(command["cwd"]), true) {
			add(&es, "INVALID_PATH", id, "command.cwd", "command directory must be a repository-relative path")
		}
		status, statusSet := r["status"]
		if (typ == "question") != (statusSet && status != nil) {
			add(&es, "INVALID_RECORD", id, "status", "status belongs to, and is required by, question records")
		}
		if typ == "question" && model.S(status) == "answered" && !nonblank(r["answer"]) {
			add(&es, "INVALID_RECORD", id, "answer", "an answered question records its answer")
		}
		if answer, ok := r["answer"]; ok && answer != nil && typ != "question" {
			add(&es, "INVALID_RECORD", id, "answer", "only questions carry answers")
		}
		if promotion, ok := r["promotion"]; ok && promotion != nil && typ != "work_item" {
			add(&es, "INVALID_RECORD", id, "promotion", "only work items are promoted to the task board")
		}
	}
	for _, v := range model.A(n["notes"]) {
		r := model.M(v)
		origin := model.M(r["origin"])
		if origin == nil {
			continue
		}
		if !Path(model.S(origin["path"]), false) {
			add(&es, "INVALID_PATH", model.S(r["id"]), "origin.path", "note origin must be a repository-relative path")
		}
		if model.I(origin["end"]) < model.I(origin["start"]) {
			add(&es, "INVALID_RECORD", model.S(r["id"]), "origin", "note origin ends before it starts")
		}
	}
	return es
}
