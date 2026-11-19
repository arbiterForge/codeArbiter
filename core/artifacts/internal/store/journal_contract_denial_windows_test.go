//go:build windows

package store

import (
	"errors"
	"os"
	"syscall"
	"testing"
)

// Deny only new read opens of this newly owned fixture file. No ACL, process,
// global setting or external dependency is changed.
func journalBoundaryDenyRead(t *testing.T, path string) func() {
	t.Helper()
	name, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		t.Fatal(err)
	}
	handle, err := syscall.CreateFile(name, syscall.GENERIC_WRITE,
		syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil,
		syscall.OPEN_EXISTING, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		t.Fatalf("owned read-denial fixture setup: %v", err)
	}
	closed := false
	restore := func() {
		if !closed {
			if err := syscall.CloseHandle(handle); err != nil {
				t.Errorf("close owned denial handle: %v", err)
			}
			closed = true
		}
	}
	t.Cleanup(restore)
	probe, err := os.Open(path)
	if err == nil {
		probe.Close()
		restore()
		t.Fatal("owned Windows sharing restriction did not deny read")
	}
	if !errors.Is(err, syscall.Errno(32)) {
		restore()
		t.Fatalf("owned denial was not ERROR_SHARING_VIOLATION: %v", err)
	}
	if info, err := os.Stat(path); err != nil || !info.Mode().IsRegular() {
		restore()
		t.Fatalf("denial fixture ceased to be an existing regular file: %v", err)
	}
	return restore
}
