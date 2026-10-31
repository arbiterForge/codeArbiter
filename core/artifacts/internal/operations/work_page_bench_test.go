package operations

import (
	"fmt"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// BenchmarkWorkListPage measures selected work reads and bounded page assembly
// without the unrelated per-operation journal and lock checks in Run.
func BenchmarkWorkListPage(b *testing.B) {
	for _, count := range []int{8, 32, 64} {
		b.Run(fmt.Sprintf("items-%d", count), func(b *testing.B) {
			root := testutil.Root(b)
			if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
				b.Fatal(err)
			}
			for i := 0; i < count; i++ {
				_, err := Run(root, "work-create", object{
					"protocol": Protocol, "operation_id": fmt.Sprintf("page-bench-%04d", i),
					"title": fmt.Sprintf("Work item %02d", i), "intent": "Measure selected page assembly",
					"work_type": "chore",
				})
				if err != nil {
					b.Fatal(err)
				}
			}
			f, err := store.Open(root)
			if err != nil {
				b.Fatal(err)
			}
			defer f.Close()
			e := &Engine{FS: f}
			r := object{"limit": int64(64), "budget": int64(65536)}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := e.workList(r); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
