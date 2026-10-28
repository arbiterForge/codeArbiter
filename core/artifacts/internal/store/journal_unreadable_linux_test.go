//go:build linux

package store

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestUnreadableFinalJournalBlocksPendingAndRecovery(t *testing.T) {
	f := fs(t)
	const id = "unreadable-journal-001"
	if _, err := f.Commit(id, canonical.BytesHash([]byte("request")), []Edit{{Path: "draft.html", After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := journalPath(id)
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	before, err := os.ReadFile(absolute)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	if file, err := os.Open(absolute); err == nil {
		_ = file.Close()
		t.Skip("host can read mode-0000 files")
	}
	for _, check := range []struct {
		name string
		run  func() error
	}{
		{"pending", func() error { _, err := f.Pending(); return err }},
		{"recover", func() error { _, err := f.Recover(id, "rollback"); return err }},
		{"new-write", func() error {
			_, err := f.Commit("blocked-unreadable-001", canonical.BytesHash([]byte("another request")), []Edit{{Path: "draft.html", Before: []byte("new"), After: []byte("later")}})
			return err
		}},
	} {
		t.Run(check.name, func(t *testing.T) {
			if got := fault.Public(check.run()); got.Code != "IO_ERROR" || got.Field != rel {
				t.Fatalf("unreadable journal diagnostic = %+v", got)
			}
		})
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("unreadable journal changed target: %q %v", got, err)
	}
	if err := os.Chmod(absolute, 0600); err != nil {
		t.Fatal(err)
	}
	if got, err := os.ReadFile(absolute); err != nil || string(got) != string(before) {
		t.Fatalf("unreadable journal changed: %q %v", got, err)
	}
}
