package render_test

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// Frozen prior-version fixtures exercise byte-preserving reads. They are not
// approval evidence or a statement that the implementation plan is complete.
func TestReviewReadPriorSchemaPreservesBytes(t *testing.T) {
	for _, name := range []string{"spec", "plan"} {
		t.Run(name, func(t *testing.T) {
			b, err := os.ReadFile(filepath.Join("..", "..", "testdata", "compat", name+"-0.3.0.html"))
			if err != nil {
				t.Fatal(err)
			}
			d, err := render.Parse(b)
			if err != nil {
				t.Fatal(err)
			}
			if d.Data["schema_version"] != "0.3.0" {
				t.Fatal("prior-schema fixture changed")
			}
			out, err := render.Render(d)
			if err != nil || !bytes.Equal(out, b) {
				t.Fatal("reading prior candidate rewrote its bytes", err)
			}
		})
	}
}
