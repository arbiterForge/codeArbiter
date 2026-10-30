package repository

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func BenchmarkCatalogScan(b *testing.B) {
	for _, count := range []int{0, 20, 200, MaxArtifacts} {
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
			fs, err := store.Open(root)
			if err != nil {
				b.Fatal(err)
			}
			defer fs.Close()
			stats := &store.OpenStats{}
			fs.Stats = stats
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := Scan(fs); err != nil {
					b.Fatal(err)
				}
			}
			b.ReportMetric(float64(stats.DirOpens)/float64(b.N), "dir-opens/op")
			b.ReportMetric(float64(stats.FileOpens)/float64(b.N), "file-opens/op")
			b.ReportMetric(float64(stats.AncestorChecks)/float64(b.N), "ancestor-checks/op")
			b.ReportMetric(float64(stats.EntryChecks)/float64(b.N), "entry-checks/op")
		})
	}
}
