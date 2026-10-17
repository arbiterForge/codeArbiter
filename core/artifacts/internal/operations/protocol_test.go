package operations

import (
	"strings"
	"testing"
)

func TestAllOperationSchemasClosed(t *testing.T) {
	for _, op := range Names() {
		s, e := RequestSchema(op)
		if e != nil {
			t.Fatal(e)
		}
		if s["additionalProperties"] != false {
			t.Fatal(op)
		}
		r := object{"protocol": Protocol, "unexpected": "x"}
		if CheckRequest(op, r) == nil {
			t.Fatal("unknown key", op)
		}
	}
}

func TestContextApplyRequestShapes(t *testing.T) {
	digest := strings.Repeat("a", 64)
	for _, tc := range []struct {
		name    string
		request object
		valid   bool
	}{
		{"ordinary", object{"protocol": Protocol, "preview_ref": "preview.json", "preview_sha256": digest}, true},
		{"legacy", object{"protocol": Protocol, "receipt": "receipt.json"}, true},
		{"mixed", object{"protocol": Protocol, "preview_ref": "preview.json", "preview_sha256": digest, "receipt": "receipt.json"}, false},
		{"legacy-with-preview", object{"protocol": Protocol, "receipt": "receipt.json", "preview_ref": "preview.json"}, false},
		{"legacy-with-digest", object{"protocol": Protocol, "receipt": "receipt.json", "preview_sha256": digest}, false},
		{"missing-reference", object{"protocol": Protocol, "preview_sha256": digest}, false},
		{"missing-digest", object{"protocol": Protocol, "preview_ref": "preview.json"}, false},
		{"invalid-digest", object{"protocol": Protocol, "preview_ref": "preview.json", "preview_sha256": strings.Repeat("g", 64)}, false},
		{"empty-receipt", object{"protocol": Protocol, "receipt": ""}, false},
		{"missing-protocol", object{"receipt": "receipt.json"}, false},
		{"wrong-protocol", object{"protocol": "unsupported", "receipt": "receipt.json"}, false},
		{"ordinary-unknown-key", object{"protocol": Protocol, "preview_ref": "preview.json", "preview_sha256": digest, "unexpected": "x"}, false},
		{"legacy-unknown-key", object{"protocol": Protocol, "receipt": "receipt.json", "unexpected": "x"}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := CheckRequest("context-apply", tc.request)
			if (err == nil) != tc.valid {
				t.Fatalf("valid = %v, want %v: %v", err == nil, tc.valid, err)
			}
		})
	}
}
