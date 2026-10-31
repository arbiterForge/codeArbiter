package operations

import (
	"encoding/json"
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

// BenchmarkCycleView measures a read of every member reference for aggregate
// progress, without conflating that scan with retained journal recovery.
func BenchmarkCycleView(b *testing.B) {
	for _, count := range []int{8, 32, 200} {
		b.Run(fmt.Sprintf("items-%d", count), func(b *testing.B) {
			root := testutil.Root(b)
			for i := 0; i < count; i++ {
				_, err := Run(root, "work-create", object{
					"protocol": Protocol, "operation_id": fmt.Sprintf("cycle-bench-%04d", i),
					"title": fmt.Sprintf("Work item %03d", i), "intent": "Measure cycle overview",
					"work_type": "chore", "cycle_id": "bench-cycle",
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
			r := object{"cycle_id": "bench-cycle", "limit": int64(16)}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := e.cycleView(r); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

// BenchmarkWorkSelectedReadWithRetainedHistory includes Run's journal recovery
// and locking path. The first create leaves one journal; each rename adds one.
// The labels count extra retained journals, never removed fixture history.
func BenchmarkWorkSelectedReadWithRetainedHistory(b *testing.B) {
	for _, updates := range []int{0, 20, 200} {
		b.Run(fmt.Sprintf("updates-%d", updates), func(b *testing.B) {
			root := testutil.Root(b)
			created, err := Run(root, "work-create", object{
				"protocol": Protocol, "operation_id": "history-bench-create-001",
				"title": "Selected work", "intent": "Measure retained history cost", "work_type": "chore",
			})
			if err != nil {
				b.Fatal(err)
			}
			current := created.(map[string]any)
			id := current["work_id"].(string)
			for i := 0; i < updates; i++ {
				next, err := Run(root, "work-update", object{
					"protocol": Protocol, "operation_id": fmt.Sprintf("history-bench-update-%04d", i),
					"work_id": id, "action": "rename", "title": fmt.Sprintf("Selected work %d", i),
					"expected": object{"revision": current["revision"], "model_sha256": current["model_sha256"]},
				})
				if err != nil {
					b.Fatal(err)
				}
				current = next.(map[string]any)
			}
			request := object{"protocol": Protocol, "work_id": id}
			value, err := Run(root, "work-get", request)
			if err != nil {
				b.Fatal(err)
			}
			encoded, err := json.Marshal(value)
			if err != nil {
				b.Fatal(err)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := Run(root, "work-get", request); err != nil {
					b.Fatal(err)
				}
			}
			b.ReportMetric(float64(len(encoded)), "result-bytes/op")
		})
	}
}
