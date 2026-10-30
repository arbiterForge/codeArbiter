package operations

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// BenchmarkArtifactReadCatalog includes lock admission, journal checks and
// strict catalog validation, rather than timing the parser in isolation.
func BenchmarkArtifactReadCatalog(b *testing.B) {
	for _, count := range []int{1, 20, 200, repository.MaxArtifacts} {
		b.Run(fmt.Sprintf("artifacts-%d", count), func(b *testing.B) {
			root := testutil.Root(b)
			dir := filepath.Join(root, ".codearbiter", "specs")
			if err := os.MkdirAll(dir, 0700); err != nil {
				b.Fatal(err)
			}
			for i := 0; i < count; i++ {
				slug := fmt.Sprintf("bench-%04d", i)
				v := testutil.Spec()
				v["artifact_id"] = fmt.Sprintf("SPEC-BENCH-%04d", i)
				v["slug"] = slug
				body, err := render.Render(testutil.Seal(b, v))
				if err != nil {
					b.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(dir, slug+".html"), body, 0600); err != nil {
					b.Fatal(err)
				}
			}
			if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
				b.Fatal(err)
			}
			request := object{"protocol": Protocol, "artifact_id": "SPEC-BENCH-0000", "offset": int64(0), "budget": int64(4096)}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := Run(root, "outline", request); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
