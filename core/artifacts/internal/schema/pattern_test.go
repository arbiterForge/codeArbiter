package schema

import (
	"fmt"
	"strings"
	"testing"
)

func patternArray() map[string]any {
	return map[string]any{"type": "array", "items": map[string]any{"type": "string", "pattern": "^[A-Z][A-Z0-9-]{1,79}$"}}
}

func TestPatternsMatchEveryValue(t *testing.T) {
	values := []any{"T-001", "T-002", "T-003"}
	if es := ValidateWith(patternArray(), values); len(es) != 0 {
		t.Fatal(es)
	}
	values[1] = "not-an-id"
	values[2] = "also-invalid"
	es := ValidateWith(patternArray(), values)
	if len(es) != 2 || es[0].Code != "INVALID_MODEL" || es[0].Field != "/1" || es[1].Field != "/2" || es[0].Message != "string fails pattern" {
		t.Fatalf("repeated pattern lost individual refusals: %+v", es)
	}
}

func TestPatternsRemainIndependentAcrossAlternatives(t *testing.T) {
	for _, row := range []struct {
		kind, value string
		valid       bool
	}{
		{"oneOf", "ABC", true}, {"oneOf", "XYZ", true}, {"oneOf", "AZ", false}, {"oneOf", "middle", false},
		{"anyOf", "AZ", true}, {"anyOf", "XYZ", true}, {"anyOf", "middle", false},
		{"allOf", "AZ", true}, {"allOf", "ABC", false},
	} {
		t.Run(row.kind+"-"+row.value, func(t *testing.T) {
			s := map[string]any{row.kind: []any{map[string]any{"pattern": "^A"}, map[string]any{"pattern": "Z$"}}}
			es := ValidateWith(s, row.value)
			if (len(es) == 0) != row.valid {
				t.Fatalf("unexpected alternative result: %+v", es)
			}
			if !row.valid && (len(es) != 1 || es[0].Message != "value fails "+row.kind+" alternatives") {
				t.Fatalf("alternative diagnostic changed: %+v", es)
			}
		})
	}
}

func TestPatternsCheckPropertyNamesAndValues(t *testing.T) {
	s := map[string]any{"type": "object", "propertyNames": map[string]any{"pattern": "^[A-Z]+$"}, "additionalProperties": map[string]any{"pattern": "^[0-9]+$"}}
	if es := ValidateWith(s, map[string]any{"A": "1", "B": "2"}); len(es) != 0 {
		t.Fatal(es)
	}
	es := ValidateWith(s, map[string]any{"A": "bad", "bad": "2"})
	if len(es) != 2 || es[0].Field != "/A" || es[1].Field != "/bad" {
		t.Fatalf("property and value patterns were confused: %+v", es)
	}
}

func TestPatternsFollowChangedSchemaBetweenCalls(t *testing.T) {
	s := map[string]any{"pattern": "^old$"}
	if es := ValidateWith(s, "old"); len(es) != 0 {
		t.Fatal(es)
	}
	s["pattern"] = "^new$"
	if es := ValidateWith(s, "new"); len(es) != 0 {
		t.Fatal(es)
	}
	if es := ValidateWith(s, "old"); len(es) != 1 || es[0].Message != "string fails pattern" {
		t.Fatalf("old schema accepted after replacement: %+v", es)
	}
}

func TestInvalidPatternRejectedBeforeValues(t *testing.T) {
	s := map[string]any{"type": "array", "items": map[string]any{"pattern": "["}}
	for _, values := range [][]any{{}, {"x", "x"}} {
		if es := ValidateWith(s, values); len(es) != 1 || es[0].Code != "SCHEMA_PACKAGE_INVALID" {
			t.Fatalf("invalid pattern escaped schema validation: %+v", es)
		}
	}
}

func TestPatternRefusalsKeepErrorBudget(t *testing.T) {
	values := make([]any, 140)
	for i := range values {
		values[i] = "invalid"
	}
	es := ValidateWith(patternArray(), values)
	if len(es) != 128 {
		t.Fatalf("got %d refusals, want 128", len(es))
	}
	for i, e := range es {
		if e.Field != fmt.Sprintf("/%d", i) || e.Code != "INVALID_MODEL" || e.Message != "string fails pattern" {
			t.Fatalf("refusal %d changed: %+v", i, e)
		}
	}
}

func BenchmarkPatternValidation(b *testing.B) {
	for _, count := range []int{1, 128, 1024} {
		b.Run(fmt.Sprintf("values-%d", count), func(b *testing.B) {
			s := patternArray()
			values := make([]any, count)
			for i := range values {
				values[i] = "T-" + strings.Repeat("0", 32)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if es := ValidateWith(s, values); len(es) != 0 {
					b.Fatal(es)
				}
			}
		})
	}
}
