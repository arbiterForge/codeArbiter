//go:build linux || darwin || windows

package store

import (
	"fmt"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
)

func TestJournalScansBoundAncestorChecks(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("journal scan fixture"))
	var before []byte
	const count = 32
	for i := 0; i < count; i++ {
		after := []byte(fmt.Sprintf("version-%03d", i))
		if _, err := f.Commit(fmt.Sprintf("scan-open-%04d", i), request,
			[]Edit{{Path: "draft.html", Before: before, After: after}}); err != nil {
			t.Fatal(err)
		}
		before = after
	}

	stats := &OpenStats{}
	f.Stats = stats
	if pending, err := f.Pending(); err != nil || len(pending) != 0 {
		t.Fatalf("pending = %v, %v", pending, err)
	}
	if stats.FileOpens != count || stats.AncestorChecks > 12 {
		t.Fatalf("pending scan repeated path descent: %+v", *stats)
	}

	stats = &OpenStats{}
	f.Stats = stats
	if _, err := f.Infrastructure(); err != nil {
		t.Fatal(err)
	}
	if stats.FileOpens != 2*count-1 || stats.AncestorChecks > 20 {
		t.Fatalf("infrastructure scan repeated path descent: %+v", *stats)
	}
}
