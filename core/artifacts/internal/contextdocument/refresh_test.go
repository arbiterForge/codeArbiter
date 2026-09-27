package contextdocument

import (
	"bytes"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestContextSelectedMetadataRefreshGuards(t *testing.T) {
	const doc = ".codearbiter/CONTEXT.md"
	const prov = ".codearbiter/.provenance/CONTEXT.json"
	old := []byte("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n# Project: Old\n\n## Human\nKeep.\n")
	base := mutationProvenance(t, old, "project_name")
	withSecondField := alterMutationProvenance(t, base, func(record map[string]any) {
		fields := record["fields"].([]any)
		second := map[string]any{"id": "FIELD-OTHER", "owner_ref": "other_ref", "claims": []any{map[string]any{
			"id": "CLAIM-OTHER", "semantic_review": map[string]any{"state": "reviewed", "reference": "review:fixture"},
			"evidence": []any{map[string]any{"kind": "content", "path": "go.mod", "digest_method": "sha256-raw",
				"digest": fields[0].(map[string]any)["claims"].([]any)[0].(map[string]any)["evidence"].([]any)[0].(map[string]any)["digest"]}},
			"effective_authority_refs": []any{},
		}}}
		record["fields"] = append(fields, second)
	})
	request := func(operation string, prior, proposed []byte) Mutation {
		return Mutation{OperationID: operation, Mode: "update", Typed: mutationTyped("Old"),
			Selections:       []PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}},
			ExpectedDocument: old, ExpectedProvenance: prior, ProposedProvenance: proposed}
	}

	t.Run("missing_selection_and_true_no_op_refuse", func(t *testing.T) {
		for _, tc := range []struct {
			name   string
			change func(*Mutation)
		}{
			{"missing_selection", func(r *Mutation) { r.Selections = nil }},
			{"identical_provenance", func(_ *Mutation) {}},
			{"only_record_timestamp_changed", func(r *Mutation) {
				r.ProposedProvenance = alterMutationProvenance(t, base, func(record map[string]any) {
					record["created"] = "2026-09-28"
				})
			}},
		} {
			t.Run(tc.name, func(t *testing.T) {
				r := request("context-refresh-guard-001", base, base)
				tc.change(&r)
				if _, _, err := PreviewBinding(r); fault.Code(err) != "INVALID_CONTEXT_MUTATION" {
					t.Fatalf("unchanged selected field admitted: %v", err)
				}
			})
		}
	})

	t.Run("unselected_claim_cannot_ride_selected_metadata_change", func(t *testing.T) {
		f, done := mutationFixture(t, "unselected-metadata")
		defer done()
		mutationWrite(t, f, doc, old)
		mutationWrite(t, f, prov, withSecondField)
		proposed := alterMutationProvenance(t, withSecondField, func(record map[string]any) {
			fields := record["fields"].([]any)
			for _, field := range fields {
				claim := field.(map[string]any)["claims"].([]any)[0].(map[string]any)
				claim["semantic_review"].(map[string]any)["reference"] = "review:changed"
			}
		})
		r := request("context-refresh-guard-002", withSecondField, proposed)
		if _, _, err := PreviewBinding(r); err != nil {
			t.Fatalf("selected preview should be well formed before ownership check: %v", err)
		}
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "OWNERSHIP_REQUIRED" {
			t.Fatalf("unselected provenance claim changed: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), old) || !bytes.Equal(mutationRead(t, f, prov), withSecondField) {
			t.Fatal("refused unselected change mutated the initialized pair")
		}
	})
}
