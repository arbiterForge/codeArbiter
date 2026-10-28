//go:build linux || darwin || windows

package store

import (
	"fmt"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// BenchmarkJournalScan measures the two full-history paths at bounded store sizes.
// The fixture updates one artifact so Infrastructure must verify before-images.
func BenchmarkJournalScan(b *testing.B) {
	for _, count := range []int{0, 20, 200} {
		b.Run(fmt.Sprintf("journals-%d", count), func(b *testing.B) {
			f, err := Open(testutil.Root(b))
			if err != nil {
				b.Fatal(err)
			}
			defer f.Close()
			request := canonical.BytesHash([]byte("benchmark"))
			var before []byte
			for i := 0; i < count; i++ {
				after := []byte(fmt.Sprintf("version-%03d", i))
				id := fmt.Sprintf("benchmark-%04d", i)
				if _, err := f.Commit(id, request, []Edit{{Path: "draft.html", Before: before, After: after}}); err != nil {
					b.Fatal(err)
				}
				before = after
			}
			b.Run("pending", func(b *testing.B) {
				for i := 0; i < b.N; i++ {
					if _, err := f.Pending(); err != nil {
						b.Fatal(err)
					}
				}
			})
			b.Run("infrastructure", func(b *testing.B) {
				for i := 0; i < b.N; i++ {
					if _, err := f.Infrastructure(); err != nil {
						b.Fatal(err)
					}
				}
			})
		})
	}
}
