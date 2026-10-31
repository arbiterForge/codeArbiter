//go:build linux || darwin

package store

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestJournalScansRejectSkippedSymlinks(t *testing.T) {
	for _, dir := range []string{"transactions", "history"} {
		t.Run(dir, func(t *testing.T) {
			f := fs(t)
			if err := f.Mkdir(meta + "/" + dir); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink("missing", filepath.Join(f.Root, filepath.FromSlash(meta), dir, "ignored.next")); err != nil {
				t.Fatal(err)
			}
			if dir == "transactions" {
				if _, err := f.Pending(); fault.Code(err) != "UNSAFE_PATH" {
					t.Fatalf("pending skipped symlink: %v", err)
				}
			}
			if _, err := f.Infrastructure(); fault.Code(err) != "UNSAFE_PATH" {
				t.Fatalf("infrastructure skipped symlink: %v", err)
			}
		})
	}
}

func TestPendingRejectsSwappedTransactionDirectory(t *testing.T) {
	f := fs(t)
	id := "scan-swap-transaction-001"
	if _, err := f.Commit(id, canonical.BytesHash([]byte("request")),
		[]Edit{{Path: "draft.html", After: []byte("first")}}); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(f.Root, filepath.FromSlash(meta), "transactions")
	swapped := false
	f.SetReadHook(func(path string, anchored bool) {
		if path != journalPath(id) || !anchored {
			return
		}
		f.SetReadHook(nil)
		if err := os.Rename(dir, dir+"-old"); err != nil {
			t.Fatal(err)
		}
		if err := os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
		swapped = true
	})
	if _, err := f.Pending(); !swapped || fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("swapped transaction directory returned clean: swapped=%v err=%v", swapped, err)
	}
}

func TestInfrastructureRejectsSwappedHistoryDirectory(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit("scan-history-first", request,
		[]Edit{{Path: "draft.html", After: []byte("first")}}); err != nil {
		t.Fatal(err)
	}
	id := "scan-history-second"
	if _, err := f.Commit(id, request,
		[]Edit{{Path: "draft.html", Before: []byte("first"), After: []byte("second")}}); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(f.Root, filepath.FromSlash(meta), "history")
	backup := meta + "/history/" + id + "-0.before"
	swapped := false
	f.SetReadHook(func(path string, anchored bool) {
		if path != backup || !anchored {
			return
		}
		f.SetReadHook(nil)
		if err := os.Rename(dir, dir+"-old"); err != nil {
			t.Fatal(err)
		}
		if err := os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
		swapped = true
	})
	if _, err := f.Infrastructure(); !swapped || fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("swapped history directory returned clean: swapped=%v err=%v", swapped, err)
	}
}
