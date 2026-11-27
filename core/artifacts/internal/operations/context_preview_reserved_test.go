package operations

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// Malformed or unsafe entries in the registered preview directory, and any
// other unregistered reserved directory, still fail strict snapshots closed.
func TestReservedPreviewOutputsFailClosed(t *testing.T) {
	previews := filepath.Join(".codearbiter", ".artifacts", "context-previews")
	for name, damage := range map[string]func(t *testing.T, root, valid string){
		"unknown key": func(t *testing.T, root, valid string) {
			raw, err := os.ReadFile(filepath.Join(root, previews, valid))
			if err != nil {
				t.Fatal(err)
			}
			record, err := canonical.Object(raw)
			if err != nil {
				t.Fatal(err)
			}
			record["extra"] = true
			b, _ := canonical.Marshal(record)
			writeFixture(t, root, filepath.Join(previews, canonical.BytesHash(b)+".json"), b)
		},
		"not an object": func(t *testing.T, root, valid string) {
			b := []byte("[]")
			writeFixture(t, root, filepath.Join(previews, canonical.BytesHash(b)+".json"), b)
		},
		"digest mismatch": func(t *testing.T, root, valid string) {
			raw, _ := os.ReadFile(filepath.Join(root, previews, valid))
			writeFixture(t, root, filepath.Join(previews, canonical.BytesHash([]byte("other"))+".json"), raw)
		},
		"nested directory": func(t *testing.T, root, valid string) {
			if err := os.MkdirAll(filepath.Join(root, previews, "nested"), 0700); err != nil {
				t.Fatal(err)
			}
		},
		"unregistered sibling": func(t *testing.T, root, valid string) {
			writeFixture(t, root, filepath.Join(".codearbiter", ".artifacts", "context-previews-old", "x.json"), []byte("{}"))
		},
	} {
		t.Run(name, func(t *testing.T) {
			f := newAssistiveFixture(t)
			_, request := contextFixtureAt(t, f.root)
			apply := ordinaryContextPreview(t, f.root, request)
			valid := filepath.Base(model.S(apply["preview_ref"]))
			if _, err := f.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err != nil {
				t.Fatalf("valid preview fixture was not recognized: %v", err)
			}
			damage(t, f.root, valid)
			code := fault.Code(func() error { _, err := f.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); return err }())
			if code != "INVALID_OUTPUT" && code != "UNRECOGNIZED_OUTPUT" {
				t.Fatalf("damaged reserved output was admitted: %q", code)
			}
		})
	}
}
