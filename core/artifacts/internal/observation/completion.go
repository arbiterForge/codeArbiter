package observation

import (
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"strings"
)

// CompletionSchema is deliberately closed: retained review data is not a new
// authority producer or a generic source-snapshot exclusion.
func CompletionSchema() map[string]any {
	verification := closed(map[string]any{
		"task_id": text(), "receipt_ref": text(), "receipt_sha256": hash(),
		"source_ref": text(), "source_sha256": hash(), "event_ref": text(), "event_sha256": hash(),
		"observation_ref": text(), "observation_sha256": hash(), "context_ref": text(), "context_sha256": hash(),
		"command_bindings":         map[string]any{"type": "array", "items": commandBindingSchema(true), "minItems": int64(1)},
		"workspace_after":          map[string]any{"type": "array", "items": workspaceSchema(), "minItems": int64(1)},
		"consumer_workspace_after": map[string]any{"type": "array", "items": workspaceSchema(), "minItems": int64(1)},
	}, "task_id", "receipt_ref", "receipt_sha256", "source_ref", "source_sha256", "event_ref", "event_sha256", "observation_ref", "observation_sha256", "context_ref", "context_sha256", "command_bindings", "workspace_after", "consumer_workspace_after")
	material := closed(map[string]any{
		"source_path": text(), "sha256": hash(), "size_bytes": map[string]any{"type": "integer", "minimum": int64(0), "maximum": int64(65536)},
		"content_base64": map[string]any{"type": "string", "maxLength": int64(87384)},
	}, "source_path", "sha256", "size_bytes", "content_base64")
	return closed(map[string]any{
		"format":        map[string]any{"const": "codearbiter.completion-evidence/0.1.0"},
		"verifications": map[string]any{"type": "array", "items": verification, "minItems": int64(1), "maxItems": int64(128)},
		"materials":     map[string]any{"type": "array", "items": material, "maxItems": int64(16)},
	}, "format", "verifications", "materials")
}

func CompletionAssessmentSchema() map[string]any {
	return map[string]any{"type": "array", "minItems": int64(1), "items": closed(map[string]any{
		"task_id": text(), "obligation": text(), "status": map[string]any{"enum": model.List("substantiated", "missing")}, "assessment": text(),
		"evidence_refs": map[string]any{"type": "array", "items": text(), "minItems": int64(1)},
	}, "task_id", "obligation", "status", "assessment", "evidence_refs")}
}

func CompletionObligations(context map[string]any) map[string]map[string]bool {
	records := model.A(context["tasks"])
	if model.S(context["activity"]) == "spec_review" {
		records = []any{context["task"]}
	}
	out := map[string]map[string]bool{}
	for _, value := range records {
		task := model.M(value)
		rows := map[string]bool{}
		for _, ref := range model.Strings(task["criterion_refs"]) {
			rows["criterion:"+ref] = true
		}
		for i := range model.A(task["steps"]) {
			rows[fmt.Sprintf("step:%d", i+1)] = true
		}
		for i := range model.A(task["done_when"]) {
			rows[fmt.Sprintf("done_when:%d", i+1)] = true
		}
		out[model.S(task["id"])] = rows
	}
	return out
}

func validateCompletionDecision(context, decision, payload map[string]any) bool {
	completion := model.M(context["completion"])
	if completion == nil {
		return decision["completion_sha256"] == nil && decision["completion_assessment"] == nil && payload["completion_sha256"] == nil && payload["completion_assessment"] == nil
	}
	h, err := canonical.Hash(completion)
	if err != nil || h != model.S(context["completion_sha256"]) || h != model.S(decision["completion_sha256"]) || h != model.S(payload["completion_sha256"]) {
		return false
	}
	a, _ := canonical.Hash(decision["completion_assessment"])
	b, _ := canonical.Hash(payload["completion_assessment"])
	if a != b {
		return false
	}
	refs := map[string]map[string]bool{}
	for _, value := range model.A(completion["verifications"]) {
		row := model.M(value)
		allowed := map[string]bool{}
		for _, key := range []string{"receipt_ref", "source_ref", "event_ref", "observation_ref", "context_ref"} {
			allowed[model.S(row[key])] = true
		}
		for _, binding := range model.A(row["command_bindings"]) {
			allowed[model.S(model.M(binding)["workspace_root"])] = true
		}
		for _, material := range model.A(completion["materials"]) {
			allowed[model.S(model.M(material)["source_path"])] = true
		}
		refs[model.S(row["task_id"])] = allowed
	}
	wanted := CompletionObligations(context)
	for _, value := range model.A(decision["completion_assessment"]) {
		row := model.M(value)
		id, obligation := model.S(row["task_id"]), model.S(row["obligation"])
		if !wanted[id][obligation] || model.S(row["status"]) != "substantiated" || strings.TrimSpace(model.S(row["assessment"])) == "" {
			return false
		}
		delete(wanted[id], obligation)
		seenRefs := map[string]bool{}
		for _, ref := range model.Strings(row["evidence_refs"]) {
			if seenRefs[ref] || !refs[id][ref] {
				return false
			}
			seenRefs[ref] = true
		}
	}
	for _, obligations := range wanted {
		if len(obligations) != 0 {
			return false
		}
	}
	return true
}
