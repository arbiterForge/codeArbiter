//go:build linux

package store

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func requireDeniedFile(t *testing.T, absolute string) {
	t.Helper()
	file, err := os.Open(absolute)
	if err == nil {
		file.Close()
		t.Skip("runner can read chmod-denied files")
	}
	if !errors.Is(err, os.ErrPermission) {
		t.Fatalf("permission fixture failed unexpectedly: %v", err)
	}
}

func TestDeniedReadReportsIOErrorWithoutAbsolutePath(t *testing.T) {
	f := fs(t)
	const target = "denied.txt"
	absolute := filepath.Join(f.Root, target)
	if err := os.WriteFile(absolute, []byte("private contents"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	requireDeniedFile(t, absolute)
	_, err := f.Read(target, 100)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != target || !strings.Contains(pub.Message, "EACCES") || fault.Exit(err) != 5 {
		t.Fatalf("want bounded EACCES read diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
	}
	if strings.Contains(pub.Message, f.Root) || strings.Contains(pub.Message, "private contents") {
		t.Fatalf("read diagnostic disclosed private filesystem data: %+v", pub)
	}
}

func TestDeniedAnchoredReadReportsIOError(t *testing.T) {
	f := fs(t)
	const directory = "files"
	const target = "files/denied.txt"
	if err := f.Mkdir(directory); err != nil {
		t.Fatal(err)
	}
	absolute := filepath.Join(f.Root, target)
	if err := os.WriteFile(absolute, []byte("private contents"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	requireDeniedFile(t, absolute)
	dir, err := f.OpenDir(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer dir.Close()
	entries, err := dir.Entries()
	if err != nil || len(entries) != 1 {
		t.Fatalf("list denied fixture: %v, %d entries", err, len(entries))
	}
	_, _, err = dir.ReadEntry(entries[0], 100)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != target || !strings.Contains(pub.Message, "EACCES") || fault.Exit(err) != 5 {
		t.Fatalf("want bounded anchored EACCES diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
	}
}

func TestDeniedBeforeImageReportsIOError(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit("io-history-seed-001", request, []Edit{{Path: "draft.html", After: []byte("old")}}); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Commit("io-history-next-001", request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := meta + "/history/io-history-next-001-0.before"
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	requireDeniedFile(t, absolute)
	_, err := f.Infrastructure()
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != rel || fault.Exit(err) != 5 {
		t.Fatalf("want bounded before-image I/O diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
	}
}

func TestDeniedFinalJournalReportsIOError(t *testing.T) {
	f := fs(t)
	id := "io-denied-journal-001"
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit(id, request, []Edit{{Path: "draft.html", After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := journalPath(id)
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	requireDeniedFile(t, absolute)
	for _, check := range []struct {
		name string
		run  func() error
	}{
		{"pending", func() error { _, err := f.Pending(); return err }},
		{"recover", func() error { _, err := f.Recover(id, "rollback"); return err }},
	} {
		t.Run(check.name, func(t *testing.T) {
			err := check.run()
			pub := fault.Public(err)
			if pub.Code != "IO_ERROR" || pub.Field != rel || fault.Exit(err) != 5 {
				t.Fatalf("want bounded final-journal I/O diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
			}
		})
	}
}

func TestDeniedExistsReportsIOError(t *testing.T) {
	f := fs(t)
	const rel = "denied-exists.txt"
	absolute := filepath.Join(f.Root, rel)
	if err := os.WriteFile(absolute, []byte("private contents"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(absolute, 0000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(absolute, 0600) })
	requireDeniedFile(t, absolute)
	exists, err := f.Exists(rel)
	pub := fault.Public(err)
	if exists || pub.Code != "IO_ERROR" || pub.Field != rel || !strings.Contains(pub.Message, "EACCES") {
		t.Fatalf("want bounded existence I/O diagnostic, got exists=%t %+v", exists, pub)
	}
}

func TestClosedAnchoredReadEntryReportsIOError(t *testing.T) {
	f := fs(t)
	const rel = "closed-entry.txt"
	if err := os.WriteFile(filepath.Join(f.Root, rel), []byte("contents"), 0600); err != nil {
		t.Fatal(err)
	}
	dir, err := f.OpenDir(".")
	if err != nil {
		t.Fatal(err)
	}
	entries, err := dir.Entries()
	if err != nil {
		t.Fatal(err)
	}
	var entry os.DirEntry
	for _, candidate := range entries {
		if candidate.Name() == rel {
			entry = candidate
			break
		}
	}
	if entry == nil {
		t.Fatal("regular entry missing from fixture")
	}
	if err := dir.Close(); err != nil {
		t.Fatal(err)
	}
	_, _, err = dir.ReadEntry(entry, 100)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != "./"+rel || !strings.Contains(pub.Message, "EBADF") {
		t.Fatalf("want bounded closed anchored read diagnostic, got %+v", pub)
	}
}

func TestClosedAnchorDuringReadReportsIOError(t *testing.T) {
	f := fs(t)
	const rel = "closed-during-read.txt"
	if err := os.WriteFile(filepath.Join(f.Root, rel), []byte("contents"), 0600); err != nil {
		t.Fatal(err)
	}
	dir, err := f.OpenDir(".")
	if err != nil {
		t.Fatal(err)
	}
	entries, err := dir.Entries()
	if err != nil {
		t.Fatal(err)
	}
	var entry os.DirEntry
	for _, candidate := range entries {
		if candidate.Name() == rel {
			entry = candidate
			break
		}
	}
	if entry == nil {
		t.Fatal("regular entry missing from fixture")
	}
	f.afterRead = func(string) { _ = dir.Close() }
	_, _, err = dir.ReadEntry(entry, 100)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != "./"+rel || !strings.Contains(pub.Message, "EBADF") {
		t.Fatalf("want bounded post-read identity I/O diagnostic, got %+v", pub)
	}
}

func TestClosedParentCurrentReportsIOError(t *testing.T) {
	f := fs(t)
	if err := f.Mkdir("sub"); err != nil {
		t.Fatal(err)
	}
	parent, err := f.OpenDir(".")
	if err != nil {
		t.Fatal(err)
	}
	entries, err := parent.Entries()
	if err != nil {
		t.Fatal(err)
	}
	var entry os.DirEntry
	for _, candidate := range entries {
		if candidate.Name() == "sub" {
			entry = candidate
			break
		}
	}
	if entry == nil {
		t.Fatal("subdirectory missing from fixture")
	}
	sub, err := parent.OpenSub(entry)
	if err != nil {
		t.Fatal(err)
	}
	defer sub.Close()
	if err := parent.Close(); err != nil {
		t.Fatal(err)
	}
	err = parent.Current("sub", sub)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != "./sub" || !strings.Contains(pub.Message, "EBADF") {
		t.Fatalf("want bounded current-directory I/O diagnostic, got %+v", pub)
	}
}
