package symbol

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestBuildRejectsDuplicateIDAcrossNestedCollections(t *testing.T) {
	norm := map[string]any{
		"criteria": []any{map[string]any{
			"id":        "AC-001",
			"scenarios": []any{map[string]any{"id": "SHARED-001"}},
		}},
		"checkpoints": []any{map[string]any{
			"id":    "CP-001",
			"tasks": []any{map[string]any{"id": "SHARED-001"}},
		}},
	}
	index, err := Build(norm)
	if index != nil || fault.Code(err) != "DUPLICATE_ID" {
		t.Fatalf("duplicate nested ID was silently indexed: index=%+v err=%v", index, err)
	}
}
