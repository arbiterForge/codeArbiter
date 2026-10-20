package schema

import (
	"fmt"
	"strings"
	"testing"
)

// A refused value names what the schema accepts, so a caller can correct it
// without reading the schema files.
func TestEnumRefusalNamesAllowedValues(t *testing.T) {
	s := map[string]any{"enum": []any{"conditional", "unconditional", "invariant"}}
	es := ValidateWith(s, "always")
	want := `value outside closed enumeration; allowed: "conditional", "unconditional", "invariant"`
	if len(es) != 1 || es[0].Code != "INVALID_MODEL" || es[0].Message != want {
		t.Fatalf("got %+v, want message %q", es, want)
	}
	if es := ValidateWith(s, "invariant"); len(es) != 0 {
		t.Fatal(es)
	}
}

func TestUnknownFieldRefusalNamesAllowedFields(t *testing.T) {
	s := map[string]any{
		"type":                 "object",
		"properties":           map[string]any{"mode": map[string]any{"type": "string"}, "rationale": map[string]any{"type": "string"}},
		"additionalProperties": false,
	}
	es := ValidateWith(s, map[string]any{"mode": "x", "reason": "y"})
	want := "additional value not permitted; allowed fields: mode, rationale"
	if len(es) != 1 || es[0].Field != "/reason" || es[0].Message != want {
		t.Fatalf("got %+v, want %q at /reason", es, want)
	}
	// A schema-valued additionalProperties still validates the extra value.
	s["additionalProperties"] = map[string]any{"type": "integer"}
	es = ValidateWith(s, map[string]any{"mode": "x", "reason": "y"})
	if len(es) != 1 || es[0].Field != "/reason" || es[0].Message != "incorrect value type" {
		t.Fatalf("got %+v", es)
	}
}

func TestLongAllowedListStaysWithinPublicLimit(t *testing.T) {
	values := make([]any, 200)
	for i := range values {
		values[i] = fmt.Sprintf("value-%03d", i)
	}
	es := ValidateWith(map[string]any{"enum": values}, "missing")
	if len(es) != 1 || len(es[0].Message) > 480 || !strings.Contains(es[0].Message, "more)") ||
		!strings.Contains(es[0].Message, `"value-000"`) {
		t.Fatalf("listing not bounded: %d bytes: %q", len(es[0].Message), es[0].Message)
	}
}
