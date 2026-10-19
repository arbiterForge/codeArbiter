//go:build linux || darwin

package store

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func hardeningEntry(t *testing.T, d *Dir, name string) os.DirEntry {
	t.Helper()
	entries, err := d.Entries()
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		if entry.Name() == name {
			return entry
		}
	}
	t.Fatalf("%s is not listed", name)
	return nil
}

// Current accepts the directory a name still resolves to and refuses a held
// anchor once the name has been swapped for another directory or a link (#962).
func TestDirCurrentRefusesSwappedName(t *testing.T) {
	root := testutil.Root(t)
	if err := os.MkdirAll(filepath.Join(root, "a", "b"), 0o755); err != nil {
		t.Fatal(err)
	}
	f, err := Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	parent, err := f.OpenDir("a")
	if err != nil {
		t.Fatal(err)
	}
	defer parent.Close()
	sub, err := parent.OpenSub(hardeningEntry(t, parent, "b"))
	if err != nil {
		t.Fatal(err)
	}
	defer sub.Close()
	if err := parent.Current("b", sub); err != nil {
		t.Fatalf("unchanged name: %v", err)
	}
	if err := os.Rename(filepath.Join(root, "a", "b"), filepath.Join(root, "a", "c")); err != nil {
		t.Fatal(err)
	}
	if err := parent.Current("c", sub); err != nil {
		t.Fatalf("the held directory under its new name: %v", err)
	}
	if err := os.Mkdir(filepath.Join(root, "a", "b"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := parent.Current("b", sub); fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("name swapped for another directory: got %v, want CONCURRENT_CHANGE", err)
	}
	if err := os.Remove(filepath.Join(root, "a", "b")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("c", filepath.Join(root, "a", "b")); err != nil {
		t.Fatal(err)
	}
	if err := parent.Current("b", sub); fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("name swapped for a link to the held directory: got %v, want CONCURRENT_CHANGE", err)
	}
}

// A FIFO planted where a listed regular file was must be refused, not waited on:
// opening a FIFO for reading blocks until a writer appears (#962).
func TestReadsRefuseSwappedFIFOWithoutBlocking(t *testing.T) {
	root := testutil.Root(t)
	if err := os.MkdirAll(filepath.Join(root, "a"), 0o755); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(root, "a", "x.txt")
	if err := os.WriteFile(file, []byte("x\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	d, err := f.OpenDir("a")
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	entry := hardeningEntry(t, d, "x.txt")
	if err := os.Remove(file); err != nil {
		t.Fatal(err)
	}
	if err := syscall.Mkfifo(file, 0o644); err != nil {
		t.Skipf("this host cannot create a FIFO: %v", err)
	}
	for name, read := range map[string]func() error{
		"ReadEntry": func() error { _, _, err := d.ReadEntry(entry, 1<<20); return err },
		"Read":      func() error { _, err := f.Read("a/x.txt", 1<<20); return err },
		"Stat": func() error {
			info, err := f.Stat("a/x.txt")
			if err == nil && !info.Mode().IsRegular() {
				return fault.New("UNSAFE_PATH", "not regular")
			}
			return err
		},
	} {
		done := make(chan error, 1)
		go func() { done <- read() }()
		select {
		case err := <-done:
			if err == nil {
				t.Errorf("%s: a FIFO was read as a regular file", name)
			}
		case <-time.After(10 * time.Second):
			// Unblock the stuck open so the test process can exit.
			if w, err := os.OpenFile(file, os.O_WRONLY|syscall.O_NONBLOCK, 0); err == nil {
				w.Close()
			}
			t.Fatalf("%s blocked opening a FIFO", name)
		}
	}
}
