package contextdocument

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCodeMapCurrentTargets(t *testing.T) {
	f, done := mutationFixture(t, "map-targets")
	defer done()
	if err := os.WriteFile(filepath.Join(f.Root, "source.txt"), []byte("owned\n"), 0644); err != nil {
		t.Fatal(err)
	}
	mapInput := func(path string) []byte {
		return []byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"code-map","entries":[{"id":"FIELD-MAP","kind":"map_entry","concern":"Core","paths":["` + path + `"],"role":"source owner","consumer_ref":"go.mod","evidence_refs":["CLAIM-SOURCE"]}]}`)
	}
	for _, tc := range []struct {
		path      string
		wantError bool
	}{
		{"go.mod", false},
		{"source.txt", false},
		{"moved.py", true},
	} {
		preview, err := RenderPreview(mapInput(tc.path), nil, false, nil)
		if err != nil {
			t.Fatal(err)
		}
		provenance := mutationProvenanceFor(t, "code-map", preview.Bytes, "entry:FIELD-MAP", "FIELD-MAP", "CLAIM-SOURCE")
		err = ValidateCurrentEvidence(f, provenance, preview)
		if (err != nil) != tc.wantError {
			t.Errorf("target %q: error = %v, want error %v", tc.path, err, tc.wantError)
		}
	}
	if err := os.Remove(filepath.Join(f.Root, "source.txt")); err != nil {
		t.Fatal(err)
	}
	preview, err := RenderPreview(mapInput("source.txt"), nil, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	provenance := mutationProvenanceFor(t, "code-map", preview.Bytes, "entry:FIELD-MAP", "FIELD-MAP", "CLAIM-SOURCE")
	if err := ValidateCurrentEvidence(f, provenance, preview); err == nil {
		t.Fatal("deleted target retained a current map claim")
	}
}
