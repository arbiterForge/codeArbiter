// Package operations implements one closed, inert protocol shared by both
// artifact kinds. No operation executes commands stored in artifact content.
package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"sort"
)

const Protocol = "codearbiter.artifact-api/0.1.0"

type object = map[string]any

func text() object            { return object{"type": "string", "minLength": int64(1)} }
func idType() object          { return object{"type": "string", "pattern": "^[A-Z][A-Z0-9-]{1,79}$"} }
func digestType() object      { return object{"type": "string", "pattern": "^[0-9a-f]{64}$"} }
func enum(v ...string) object { return object{"enum": model.List(v...)} }
func closed(p object, r ...string) object {
	return object{"type": "object", "properties": p, "required": model.List(r...), "additionalProperties": false}
}
func array(v any, min int64) object {
	return object{"type": "array", "items": v, "minItems": min, "maxItems": int64(128)}
}
func common(name string) object {
	return object{"$ref": "urn:codearbiter:artifact:common:" + model.SchemaVersion + "#/$defs/" + name}
}
func changesType() object {
	add := closed(object{"op": enum("record.add"), "collection": text(), "parent_id": idType(), "record": object{"type": "object"}}, "op", "collection", "record")
	update := closed(object{"op": enum("record.update"), "symbol": idType(), "fields": object{"type": "object"}, "retirement_reason": text()}, "op", "symbol", "fields")
	retire := closed(object{"op": enum("record.retire"), "symbol": idType(), "reason": text(), "replacement_ref": text()}, "op", "symbol", "reason")
	header := closed(object{"op": enum("header.update"), "fields": closed(object{"title": text(), "summary": text(), "governs": array(text(), 0), "baseline": common("baseline"), "verification_inputs": closed(object{"roots": array(text(), 1), "exclude_directories": array(text(), 0)}, "roots", "exclude_directories")})}, "op", "fields")
	return array(object{"oneOf": []any{add, update, retire, header}}, 1)
}

var operations = []string{"capabilities", "schema", "create", "apply", "read", "outline", "validate", "index", "identity", "snapshot", "evidence-context", "rebrand", "repair-preview", "repair-apply", "approve", "plan-bind", "sprint-approval-context", "sprint-approve", "smarts-apply", "eligible", "task-start", "task-review", "task-block", "task-reconcile", "scope-reconcile", "accept-scope", "prerequisite", "farm-project", "farm-seal", "farm-verify", "recover", "diff", "capture", "capture-observation", "export", "migration-preview", "migration-apply", "migration-rollback"}

func Names() []string { x := append([]string{}, operations...); sort.Strings(x); return x }

// JournaledMutation identifies CAS/recoverable artifact writes. It is NOT a permission classifier: capture also writes immutable events and receipts.
func JournaledMutation(op string) bool {
	switch op {
	case "migration-rollback", "export", "migration-apply", "create", "apply", "rebrand", "repair-apply", "approve", "plan-bind", "sprint-approve", "smarts-apply", "task-start", "task-review", "task-block", "task-reconcile", "scope-reconcile", "accept-scope", "prerequisite", "farm-project", "recover":
		return true
	}
	return false
}
func RequestSchema(op string) (object, error) {
	p := object{"protocol": enum(Protocol)}
	required := []string{"protocol"}
	add := func(k string, v any, req bool) {
		p[k] = v
		if req {
			required = append(required, k)
		}
	}
	artifact := func() { add("artifact_id", idType(), true) }
	cas := func() {
		artifact()
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		add("expected", closed(object{"revision": object{"type": "integer", "minimum": int64(1)}, "model_sha256": digestType()}, "revision", "model_sha256"), true)
	}
	budget := func() {
		add("budget", object{"type": "integer", "minimum": int64(4096), "maximum": int64(65536)}, false)
	}
	switch op {
	case "capture", "capture-observation":
		add("source_ref", text(), true)
		add("source_sha256", digestType(), true)
	case "evidence-context":
		artifact()
		add("activity", enum("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization"), true)
		add("record_id", idType(), true)
		add("prompt_sha256", digestType(), false)
	case "migration-preview", "migration-apply":
		mapping := closed(object{"start_line": object{"type": "integer", "minimum": int64(1)}, "end_line": object{"type": "integer", "minimum": int64(1)}, "target": idType(), "disposition": enum("mapped", "historical", "out_of_scope"), "reason": text()}, "start_line", "end_line", "target", "disposition", "reason")
		item := closed(object{"source_path": text(), "artifact_id": idType(), "slug": object{"type": "string", "pattern": "^[a-z][a-z0-9-]*$", "maxLength": int64(100)}, "normative": object{"type": "object"}, "mappings": object{"type": "array", "items": mapping, "minItems": int64(1), "maxItems": int64(4096)}}, "source_path", "artifact_id", "slug", "normative", "mappings")
		add("spec", item, true)
		add("plan", item, false)
		if op == "migration-apply" {
			add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
			add("preview_sha256", digestType(), true)
			add("review", closed(object{"actor": text(), "origin": text(), "source_text": text()}, "actor", "origin", "source_text"), true)
		}
	case "export":
		artifact()
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		add("model_sha256", digestType(), true)
		add("target", text(), true)
	case "capabilities":
	case "schema":
		schemaNames := append([]string{"common"}, kind.Names()...)
		schemaNames = append(schemaNames, "operation", "receipt", "event", "evidence_context", "observation", "verification", "spec_review", "quality_review")
		add("name", enum(schemaNames...), true)
		add("fragment", text(), false)
		add("operation", text(), false)
	case "create":
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		artifact()
		add("kind", enum(kind.Names()...), true)
		add("slug", object{"type": "string", "pattern": "^[a-z][a-z0-9-]*$", "maxLength": int64(100)}, true)
		add("title", text(), true)
		add("summary", text(), true)
		add("baseline", common("baseline"), false)
		add("spec_id", idType(), false)
		add("normative", object{"type": "object"}, false)
	case "apply":
		cas()
		add("changes", changesType(), true)
	case "read":
		artifact()
		add("symbol", idType(), true)
		add("mode", enum("exact", "contextual"), false)
		add("cursor", text(), false)
		budget()
	case "outline":
		artifact()
		add("offset", object{"type": "integer", "minimum": int64(0)}, false)
		add("model_sha256", digestType(), false)
		budget()
	case "identity":
		artifact()
	case "validate":
		artifact()
		add("gate", enum("structural", "ready", "approved"), false)
	case "index":
		add("kind", enum(kind.Names()...), false)
		add("offset", object{"type": "integer", "minimum": int64(0)}, false)
		add("catalog_sha256", digestType(), false)
		budget()
	case "snapshot":
		artifact()
	case "rebrand":
		cas()
		add("name", object{"type": "string", "minLength": int64(1), "maxLength": int64(120)}, false)
		add("logo_path", text(), false)
		add("mime", enum("image/svg+xml", "image/png", "image/jpeg"), false)
	case "repair-preview":
		add("path", text(), true)
	case "repair-apply":
		add("path", text(), true)
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		add("expected_bytes_sha256", digestType(), true)
		add("preview_sha256", digestType(), true)
	case "sprint-approval-context":
		artifact()
		add("spec_id", idType(), true)
		add("prompt_sha256", digestType(), true)
		add("delegate_methods", object{"type": "boolean"}, true)
	case "sprint-approve":
		cas()
		add("spec_id", idType(), true)
		add("spec_expected", closed(object{"revision": object{"type": "integer", "minimum": int64(1)}, "model_sha256": digestType()}, "revision", "model_sha256"), true)
		source := closed(object{"source_ref": text(), "source_sha256": digestType()}, "source_ref", "source_sha256")
		add("spec_source", source, true)
		add("plan_source", source, true)
	case "smarts-apply":
		cas()
		add("grant_receipt", text(), true)
		add("decision", observation.DecisionSchema(), true)
	case "approve":
		cas()
		add("receipt", text(), true)
	case "plan-bind":
		cas()
		add("spec_id", idType(), true)
		add("changes", changesType(), false)
	case "eligible":
		artifact()
	case "task-start":
		cas()
		add("task", idType(), true)
		add("context_ticket", text(), true)
	case "task-review":
		cas()
		add("task", idType(), true)
		add("verification_receipt", text(), true)
		add("review_receipt", text(), true)
	case "task-block":
		cas()
		add("task", idType(), true)
		add("reason", text(), true)
	case "task-reconcile":
		cas()
		add("task", idType(), true)
		add("receipt", text(), true)
		add("state", enum("PENDING", "REVIEW", "BLOCKED"), true)
		add("reason", text(), true)
	case "scope-reconcile":
		cas()
		add("scope", idType(), true)
		add("receipt", text(), true)
	case "accept-scope":
		cas()
		add("scope", idType(), true)
		add("receipt", text(), true)
	case "prerequisite":
		cas()
		add("prerequisite", idType(), true)
		add("receipt", text(), true)
	case "farm-project":
		cas()
		add("scope", idType(), true)
		add("slice", array(idType(), 1), true)
		add("target", text(), true)
		add("projection", object{"type": "object"}, true)
		add("receipt", text(), true)
	case "farm-seal":
		add("projection_path", text(), true)
		add("provenance", closed(object{"model": text(), "api_base_url": text(), "selection_source": enum("canary", "cache", "websearch", "environment", "manual"), "origin": text()}, "model", "api_base_url", "selection_source", "origin"), true)
	case "farm-verify":
		add("projection_path", text(), true)
		add("phase", enum("canary", "dispatch"), true)
		add("effective_model", text(), false)
		add("effective_api_base_url", text(), false)
	case "migration-rollback":
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		add("cutover_operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
	case "recover":
		add("operation_id", object{"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$"}, true)
		add("mode", enum("complete", "rollback"), true)
	case "diff":
		artifact()
		add("changes", changesType(), true)
		budget()
	default:
		return nil, fault.New("UNKNOWN_OPERATION", "operation is not implemented; request capabilities for the supported index")
	}
	return closed(p, required...), nil
}
func CheckRequest(op string, r object) error {
	s, e := RequestSchema(op)
	if e != nil {
		return e
	}
	if es := schema.ValidateWith(s, r); len(es) > 0 {
		return &es[0]
	}
	return nil
}
