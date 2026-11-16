//go:build linux || darwin

package store

import (
	"os"
	"testing"
)

func journalBoundaryDenyRead(t *testing.T, path string) func() {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(path, 0000); err != nil {
		t.Fatal(err)
	}
	restored := false
	restore := func() {
		if !restored {
			if err := os.Chmod(path, info.Mode().Perm()); err != nil {
				t.Errorf("restore owned denial mode: %v", err)
			}
			restored = true
		}
	}
	t.Cleanup(restore)
	probe, err := os.Open(path)
	if err == nil {
		probe.Close()
		restore()
		t.Skip("owned mode-0000 file remains readable to this host identity; no unreadable-file qualification")
	}
	if !os.IsPermission(err) {
		restore()
		t.Fatalf("owned denial was not a permission failure: %v", err)
	}
	return restore
}
