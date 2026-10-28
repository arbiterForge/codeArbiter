//go:build linux || darwin || windows

package store

import (
	"bytes"
	"errors"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

func fs(t *testing.T) *FS {
	t.Helper()
	f, e := Open(testutil.Root(t))
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { f.Close() })
	return f
}
func TestTransactionalCAS(t *testing.T) {
	f := fs(t)
	h := canonical.BytesHash([]byte("request"))
	p := ".codearbiter/specs/test.html"
	o, e := f.Commit("test-cas-0001", h, []Edit{{p, nil, []byte("old")}})
	if e != nil || o.State != "committed" {
		t.Fatal(o, e)
	}
	o, e = f.Commit("test-cas-0001", h, nil)
	if e != nil || !o.Replay {
		t.Fatal(o, e)
	}
	if _, e = f.Commit("test-cas-0001", canonical.BytesHash(nil), nil); fault.Code(e) != "OPERATION_ID_REUSE" {
		t.Fatal(e)
	}
	if _, e = f.Commit("test-cas-0002", h, []Edit{{p, []byte("wrong"), []byte("new")}}); fault.Code(e) != "REVISION_CONFLICT" {
		t.Fatal(e)
	}
	b, _ := f.Read(p, 100)
	if string(b) != "old" {
		t.Fatal("failed CAS changed bytes")
	}
}

func TestPartialJournalStageRequiresManualReconciliation(t *testing.T) {
	f := fs(t)
	if e := f.Mkdir(meta + "/transactions"); e != nil {
		t.Fatal(e)
	}
	stage := filepath.Join(f.Root, ".codearbiter", ".artifacts", "transactions", "partial-stage-001.json.next")
	if e := os.WriteFile(stage, []byte(`{"format":`), 0600); e != nil {
		t.Fatal(e)
	}
	_, e := f.Commit("partial-stage-001", canonical.BytesHash([]byte("request")),
		[]Edit{{Path: "a.txt", After: []byte("new")}})
	if fault.Code(e) != "RECOVERY_REQUIRED" || !strings.Contains(e.Error(), "orphan journal stage") {
		t.Fatalf("expected precise manual reconciliation state, got %v", e)
	}
	if _, e := os.Stat(filepath.Join(f.Root, "a.txt")); !os.IsNotExist(e) {
		t.Fatalf("canonical target changed: %v", e)
	}
	if b, e := os.ReadFile(stage); e != nil || string(b) != `{"format":` {
		t.Fatalf("orphan stage was not preserved: %q %v", b, e)
	}
}

func TestPreJournalIOFailureHasBoundedPublicDiagnostic(t *testing.T) {
	for _, tc := range []struct {
		name  string
		cause error
	}{
		{"EACCES", syscall.EACCES},
		{"EPERM", syscall.EPERM},
		{"EIO", syscall.EIO},
		{"ENOSPC", syscall.ENOSPC},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			const target = ".codearbiter/specs/a.html"
			f.Inject = func(step string) error {
				if step == "after-stage-0" {
					return &os.PathError{Op: "write", Path: "private/credential=do-not-echo", Err: tc.cause}
				}
				return nil
			}
			_, err := f.Commit("io-stage-0001", canonical.BytesHash([]byte("request")),
				[]Edit{{Path: target, After: []byte("new")}})
			pub := fault.Public(err)
			if pub.Code != "IO_ERROR" || fault.Exit(err) != 5 {
				t.Fatalf("want IO_ERROR and exit 5, got %v and %d", pub, fault.Exit(err))
			}
			if pub.Field != target || !strings.Contains(pub.Message, tc.name) || strings.Contains(pub.Message, "credential=do-not-echo") {
				t.Fatalf("public diagnostic lost target or leaked source: %+v", pub)
			}
			if _, err := f.Read(target, 100); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("pre-journal I/O failure wrote target: %v", err)
			}
		})
	}
}

func TestClosedStoreIOBoundariesHaveBoundedPublicDiagnostics(t *testing.T) {
	const file = ".codearbiter/specs/a.html"
	const directory = ".codearbiter/specs"
	for _, tc := range []struct {
		name, target string
		call         func(*FS) error
	}{
		{"read", file, func(f *FS) error { _, err := f.Read(file, 100); return err }},
		{"create", file, func(f *FS) error { return f.create(file, []byte("new"), 0600) }},
		{"mkdir", directory, func(f *FS) error { return f.Mkdir(directory) }},
		{"exists", directory, func(f *FS) error { _, err := f.Exists(directory); return err }},
		{"list", directory, func(f *FS) error { _, err := f.ListUnfollowed(directory); return err }},
		{"open directory", directory, func(f *FS) error { _, err := f.OpenDir(directory); return err }},
		{"stat", directory, func(f *FS) error { _, err := f.Stat(directory); return err }},
		{"remove", file, func(f *FS) error { return f.remove(file) }},
		{"replace", file, func(f *FS) error { return f.replace("stage.html", file, false) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			if err := f.Close(); err != nil {
				t.Fatal(err)
			}
			err := tc.call(f)
			pub := fault.Public(err)
			if pub.Code != "IO_ERROR" || pub.Field != tc.target || fault.Exit(err) != 5 || strings.Contains(pub.Message, f.Root) {
				t.Fatalf("want bounded I/O diagnostic for %s, got %+v (exit %d)", tc.target, pub, fault.Exit(err))
			}
		})
	}
}

func TestClosedAnchoredDirectoryHasBoundedPublicDiagnostics(t *testing.T) {
	for _, tc := range []struct {
		name, target string
		call         func(*Dir, os.DirEntry) error
	}{
		{"entries", "anchor", func(d *Dir, _ os.DirEntry) error { _, err := d.Entries(); return err }},
		{"open subdirectory", "anchor/child", func(d *Dir, entry os.DirEntry) error { _, err := d.OpenSub(entry); return err }},
		{"has", "anchor/child", func(d *Dir, _ os.DirEntry) error { _, err := d.Has("child"); return err }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			if err := f.Mkdir("anchor/child"); err != nil {
				t.Fatal(err)
			}
			dir, err := f.OpenDir("anchor")
			if err != nil {
				t.Fatal(err)
			}
			entries, err := dir.Entries()
			if err != nil || len(entries) != 1 {
				t.Fatalf("list child fixture: %v, %d entries", err, len(entries))
			}
			if err := dir.Close(); err != nil {
				t.Fatal(err)
			}
			err = tc.call(dir, entries[0])
			pub := fault.Public(err)
			if pub.Code != "IO_ERROR" || pub.Field != tc.target || fault.Exit(err) != 5 || strings.Contains(pub.Message, f.Root) {
				t.Fatalf("want bounded anchored I/O diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
			}
		})
	}
}

func TestClosedParentCurrentHasBoundedPublicDiagnostic(t *testing.T) {
	f := fs(t)
	if err := f.Mkdir("anchor/child"); err != nil {
		t.Fatal(err)
	}
	parent, err := f.OpenDir("anchor")
	if err != nil {
		t.Fatal(err)
	}
	entries, err := parent.Entries()
	if err != nil || len(entries) != 1 {
		t.Fatalf("list child fixture: %v, %d entries", err, len(entries))
	}
	sub, err := parent.OpenSub(entries[0])
	if err != nil {
		t.Fatal(err)
	}
	defer sub.Close()
	if err := parent.Close(); err != nil {
		t.Fatal(err)
	}
	err = parent.Current("child", sub)
	pub := fault.Public(err)
	if pub.Code != "IO_ERROR" || pub.Field != "anchor/child" || fault.Exit(err) != 5 {
		t.Fatalf("want bounded current-directory I/O diagnostic, got %+v (exit %d)", pub, fault.Exit(err))
	}
}
func TestReplaceRecovery(t *testing.T) {
	for _, step := range []string{"after-stage-0", "after-journal", "after-replace-0", "after-replace-1", "after-complete"} {
		for _, mode := range []string{"complete", "rollback"} {
			t.Run(step+"/"+mode, func(t *testing.T) {
				f := fs(t)
				p, q := ".codearbiter/specs/a.html", ".codearbiter/plans/a.html"
				h := canonical.BytesHash([]byte("request"))
				if _, e := f.Commit("initial-0001", h, []Edit{{p, nil, []byte("a")}, {q, nil, []byte("b")}}); e != nil {
					t.Fatal(e)
				}
				f.Inject = func(s string) error {
					if s == step {
						return errors.New("injected")
					}
					return nil
				}
				_, e := f.Commit("update-0001", h, []Edit{{p, []byte("a"), []byte("A")}, {q, []byte("b"), []byte("B")}})
				if e == nil {
					t.Fatal("fault not injected")
				}
				f.Inject = nil
				if step == "after-stage-0" {
					a, _ := f.Read(p, 100)
					b, _ := f.Read(q, 100)
					if string(a) != "a" || string(b) != "b" {
						t.Fatal("precommit changed live bytes")
					}
					if _, e = f.Commit("update-0001", h, []Edit{{p, []byte("a"), []byte("A")}, {q, []byte("b"), []byte("B")}}); e != nil {
						t.Fatal(e)
					}
					return
				}
				o, e := f.Recover("update-0001", mode)
				if e != nil {
					t.Fatal(e)
				}
				a, _ := f.Read(p, 100)
				b, _ := f.Read(q, 100)
				if o.State == "committed" {
					if string(a) != "A" || string(b) != "B" {
						t.Fatal("complete failed")
					}
				} else if string(a) != "a" || string(b) != "b" {
					t.Fatal("rollback failed")
				}
			})
		}
	}
}
func TestRecoveryConflictPreservesExternalEdit(t *testing.T) {
	f := fs(t)
	h := canonical.BytesHash(nil)
	p := "a.html"
	f.Inject = func(s string) error {
		if s == "after-replace-0" {
			return errors.New("interrupt")
		}
		return nil
	}
	_, _ = f.Commit("conflict-0001", h, []Edit{{p, nil, []byte("new")}})
	f.Inject = nil
	os.WriteFile(filepath.Join(f.Root, p), []byte("external"), 0600)
	if _, e := f.Recover("conflict-0001", "rollback"); fault.Code(e) != "RECOVERY_CONFLICT" {
		t.Fatal(e)
	}
	b, _ := f.Read(p, 100)
	if string(b) != "external" {
		t.Fatal("external bytes lost")
	}
}
func TestPathEscapeAndSymlink(t *testing.T) {
	f := fs(t)
	outside := testutil.Root(t)
	os.WriteFile(filepath.Join(outside, "secret"), []byte("secret"), 0600)
	if e := os.Symlink(outside, filepath.Join(f.Root, "escape")); e != nil {
		t.Fatal(e)
	}
	for _, p := range []string{"../secret", "escape/secret"} {
		if _, e := f.Read(p, 100); e == nil {
			t.Fatal("escape accepted")
		}
	}
	if _, e := f.Commit("escape-0001", canonical.BytesHash(nil), []Edit{{"escape/new", nil, []byte("x")}}); e == nil {
		t.Fatal("symlink write accepted")
	}
	if _, e := os.Stat(filepath.Join(outside, "new")); !os.IsNotExist(e) {
		t.Fatal("escaped write")
	}
}
func TestWriterLock(t *testing.T) {
	f := fs(t)
	g, e := Open(f.Root)
	if e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	unlock, e := f.Lock(true, time.Second)
	if e != nil {
		t.Fatal(e)
	}
	defer unlock()
	if _, e = g.Lock(true, 20*time.Millisecond); fault.Code(e) != "LOCK_TIMEOUT" {
		t.Fatal(e)
	}
}
func TestCreateRaceDoesNotOverwrite(t *testing.T) {
	f := fs(t)
	f.Inject = func(s string) error {
		if s == "before-replace-0" {
			return os.WriteFile(filepath.Join(f.Root, "new.html"), []byte("external"), 0600)
		}
		return nil
	}
	_, e := f.Commit("race-create-01", canonical.BytesHash(nil), []Edit{{"new.html", nil, []byte("ours")}})
	if e == nil {
		t.Fatal("expected conflict")
	}
	b, _ := f.Read("new.html", 100)
	if !bytes.Equal(b, []byte("external")) {
		t.Fatal(fmt.Sprintf("overwrote race winner: %s", b))
	}
}

// TestDirScanRefusesLinksAndEscapes pins the safety the walk-relative Dir API
// must keep: links are never read or descended, only regular files are read,
// the size limit holds, and a name cannot leave the anchored directory.
func TestDirScanRefusesLinksAndEscapes(t *testing.T) {
	f := fs(t)
	outside := testutil.Root(t)
	os.WriteFile(filepath.Join(outside, "secret"), []byte("secret"), 0600)
	os.WriteFile(filepath.Join(f.Root, "plain.txt"), []byte("plain"), 0600)
	os.WriteFile(filepath.Join(f.Root, "big.txt"), []byte("0123456789"), 0600)
	os.Mkdir(filepath.Join(f.Root, "sub"), 0700)
	os.WriteFile(filepath.Join(f.Root, "sub", "in.txt"), []byte("in"), 0600)
	linked := os.Symlink(outside, filepath.Join(f.Root, "dirlink")) == nil
	if linked {
		linked = os.Symlink(filepath.Join(outside, "secret"), filepath.Join(f.Root, "filelink")) == nil
	}
	if !linked {
		t.Log("symlinks unavailable on this host; link refusal not exercised")
	}
	d, e := f.OpenDir(".")
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	entries, e := d.Entries()
	if e != nil {
		t.Fatal(e)
	}
	seen := 0
	for _, entry := range entries {
		switch entry.Name() {
		case "plain.txt":
			b, info, e := d.ReadEntry(entry, 100)
			if e != nil || string(b) != "plain" || !info.Mode().IsRegular() {
				t.Fatal(string(b), info, e)
			}
		case "big.txt":
			if _, _, e := d.ReadEntry(entry, 5); fault.Code(e) != "MAX_BYTES" {
				t.Fatal("size limit not enforced:", e)
			}
		case "sub":
			s, e := d.OpenSub(entry)
			if e != nil {
				t.Fatal(e)
			}
			if _, _, e := d.ReadEntry(entry, 100); e == nil {
				t.Fatal("a directory was read as a file")
			}
			subEntries, e := s.Entries()
			if e != nil || len(subEntries) != 1 || subEntries[0].Name() != "in.txt" {
				t.Fatal(subEntries, e)
			}
			s.Close()
		case "dirlink":
			if _, e := d.OpenSub(entry); e == nil {
				t.Fatal("a directory link was descended")
			}
			if _, _, e := d.ReadEntry(entry, 100); e == nil {
				t.Fatal("a directory link was read")
			}
		case "filelink":
			if _, _, e := d.ReadEntry(entry, 100); e == nil {
				t.Fatal("a file link was read")
			}
		}
		seen++
	}
	want := 3
	if linked {
		want = 5
	}
	if seen < want {
		t.Fatalf("listing saw %d entries, want at least %d", seen, want)
	}
	if ok, e := d.Has("plain.txt"); e != nil || !ok {
		t.Fatal(ok, e)
	}
	if ok, e := d.Has("absent.txt"); e != nil || ok {
		t.Fatal(ok, e)
	}
	if _, e := f.OpenDir("../" + filepath.Base(outside)); e == nil {
		t.Fatal("opened a directory outside the root")
	}
	if _, e := f.OpenDir("dirlink"); linked && e == nil {
		t.Fatal("OpenDir followed a link")
	}
}

// namedEntry is a synthetic listing entry: it carries the type a listing
// reported earlier, regardless of what the name is now.
type namedEntry struct {
	name string
	dir  bool
}

func (e namedEntry) Name() string { return e.name }
func (e namedEntry) IsDir() bool  { return e.dir }
func (e namedEntry) Type() os.FileMode {
	if e.dir {
		return os.ModeDir
	}
	return 0
}
func (e namedEntry) Info() (os.FileInfo, error) { return nil, errors.New("synthetic entry") }

func entryNamed(t *testing.T, entries []os.DirEntry, name string) os.DirEntry {
	t.Helper()
	for _, entry := range entries {
		if entry.Name() == name {
			return entry
		}
	}
	t.Fatalf("listing has no %q", name)
	return nil
}

func linkOrSkip(t *testing.T, target, link string) {
	t.Helper()
	if e := os.Symlink(target, link); e != nil {
		t.Fatalf("symlink unavailable, swap condition cannot be injected: %v", e)
	}
}

// TestDirEntryTypeSwappedAfterListing injects the condition a listing cannot
// see: a regular file or directory replaced by an in-tree link after Entries().
func TestDirEntryTypeSwappedAfterListing(t *testing.T) {
	f := fs(t)
	os.MkdirAll(filepath.Join(f.Root, "inner"), 0700)
	os.WriteFile(filepath.Join(f.Root, "inner", "b.txt"), []byte("B"), 0600)
	os.WriteFile(filepath.Join(f.Root, "slin"), []byte("A"), 0600)
	os.Mkdir(filepath.Join(f.Root, "sldir"), 0700)
	d, e := f.OpenDir(".")
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	entries, e := d.Entries()
	if e != nil {
		t.Fatal(e)
	}
	fileEntry, dirEntry := entryNamed(t, entries, "slin"), entryNamed(t, entries, "sldir")
	os.Remove(filepath.Join(f.Root, "slin"))
	os.Remove(filepath.Join(f.Root, "sldir"))
	linkOrSkip(t, filepath.Join("inner", "b.txt"), filepath.Join(f.Root, "slin"))
	linkOrSkip(t, "inner", filepath.Join(f.Root, "sldir"))
	if b, _, e := d.ReadEntry(fileEntry, 100); e == nil {
		t.Fatalf("ReadEntry followed a link swapped in after listing: %q", b)
	}
	if s, e := d.OpenSub(dirEntry); e == nil {
		s.Close()
		t.Fatal("OpenSub followed a link swapped in after listing")
	}
}

// TestDirRejectsNonSingleComponentNames pins the shared name guard: a name that
// is not one component of the anchored directory must be refused by every
// backend before it reaches the filesystem, even when it would resolve.
func TestDirRejectsNonSingleComponentNames(t *testing.T) {
	f := fs(t)
	os.MkdirAll(filepath.Join(f.Root, "anchor", "sub"), 0700)
	os.WriteFile(filepath.Join(f.Root, "anchor", "sub", "b"), []byte("b"), 0600)
	os.WriteFile(filepath.Join(f.Root, "x"), []byte("x"), 0600)
	d, e := f.OpenDir("anchor")
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	names := []string{"", ".", "..", "../x", "/etc/hostname", "sub/b", "sub/..", "a\x00b"}
	if runtime.GOOS == "windows" {
		names = append(names, "sub\\b", "..\\x")
	}
	for _, name := range names {
		if _, _, e := d.ReadEntry(namedEntry{name: name}, 100); fault.Code(e) != "UNSAFE_PATH" {
			t.Errorf("ReadEntry(%q) = %v, want UNSAFE_PATH", name, e)
		}
		if s, e := d.OpenSub(namedEntry{name: name, dir: true}); fault.Code(e) != "UNSAFE_PATH" {
			if s != nil {
				s.Close()
			}
			t.Errorf("OpenSub(%q) = %v, want UNSAFE_PATH", name, e)
		}
		if ok, e := d.Has(name); fault.Code(e) != "UNSAFE_PATH" || ok {
			t.Errorf("Has(%q) = %v, %v, want UNSAFE_PATH", name, ok, e)
		}
	}
}

// TestDirEntriesIsIdempotent: listing the same anchored directory twice yields
// the same entries.
func TestDirEntriesIsIdempotent(t *testing.T) {
	f := fs(t)
	os.WriteFile(filepath.Join(f.Root, "a.txt"), []byte("a"), 0600)
	os.WriteFile(filepath.Join(f.Root, "b.txt"), []byte("b"), 0600)
	d, e := f.OpenDir(".")
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	first, e := d.Entries()
	if e != nil || len(first) == 0 {
		t.Fatal(first, e)
	}
	for i := 0; i < 2; i++ {
		again, e := d.Entries()
		if e != nil || len(again) != len(first) {
			t.Fatalf("repeat listing %d returned %d entries (%v), want %d", i, len(again), e, len(first))
		}
		for j := range first {
			if again[j].Name() != first[j].Name() {
				t.Fatalf("repeat listing differs at %d: %q vs %q", j, again[j].Name(), first[j].Name())
			}
		}
	}
}

// TestOpenDirRegularFileIsUnsafeNotAbsent: a regular file where a directory is
// expected is an unsafe path on every backend, never an absent directory.
func TestOpenDirRegularFileIsUnsafeNotAbsent(t *testing.T) {
	f := fs(t)
	os.WriteFile(filepath.Join(f.Root, "specs"), []byte("not a dir"), 0600)
	d, e := f.OpenDir("specs")
	if e == nil {
		d.Close()
		t.Fatal("OpenDir accepted a regular file")
	}
	if errors.Is(e, os.ErrNotExist) || fault.Code(e) != "UNSAFE_PATH" {
		t.Fatalf("OpenDir(file) = %v, want UNSAFE_PATH and not ErrNotExist", e)
	}
	if _, e := f.OpenDir("absent"); !errors.Is(e, os.ErrNotExist) {
		t.Fatalf("OpenDir(absent) = %v, want ErrNotExist", e)
	}
}

// TestPortableReadRefusesSymlink: a symlink (and on Windows a junction) that a
// listing reports is refused with UNSAFE_PATH by every read path, never read
// through to its target.
func TestPortableReadRefusesSymlink(t *testing.T) {
	f := fs(t)
	os.MkdirAll(filepath.Join(f.Root, "inner"), 0700)
	os.WriteFile(filepath.Join(f.Root, "inner", "target.txt"), []byte("target"), 0600)
	linkOrSkip(t, filepath.Join("inner", "target.txt"), filepath.Join(f.Root, "filelink"))
	linkOrSkip(t, "inner", filepath.Join(f.Root, "dirlink"))
	links := []string{"filelink", "dirlink"}
	if runtime.GOOS == "windows" {
		out, e := exec.Command("cmd", "/c", "mklink", "/J", filepath.Join(f.Root, "junction"), filepath.Join(f.Root, "inner")).CombinedOutput()
		if e != nil {
			t.Logf("junction not creatable on this host, skipped: %v %s", e, out)
		} else {
			links = append(links, "junction")
		}
	}
	d, e := f.OpenDir(".")
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	entries, e := d.Entries()
	if e != nil {
		t.Fatal(e)
	}
	for _, name := range links {
		entry := entryNamed(t, entries, name)
		if b, _, e := d.ReadEntry(entry, 100); fault.Code(e) != "UNSAFE_PATH" {
			t.Errorf("ReadEntry(%s) = %q, %v, want UNSAFE_PATH", name, b, e)
		}
		if s, e := d.OpenSub(entry); fault.Code(e) != "UNSAFE_PATH" {
			if s != nil {
				s.Close()
			}
			t.Errorf("OpenSub(%s) = %v, want UNSAFE_PATH", name, e)
		}
	}
	if b, e := f.Read("filelink", 100); fault.Code(e) != "UNSAFE_PATH" {
		t.Errorf("FS.Read(filelink) = %q, %v, want UNSAFE_PATH", b, e)
	}
}

// TestPortableReadDetectsMidReadChange: a file that changes after its bytes are
// read but before the closing check fails with CONCURRENT_CHANGE. The store's
// test-only afterRead seam runs at exactly that point, so each change is made
// deterministically: no timing, goroutine or sleep is involved. The identity-only
// case replaces the file with a different one of the same size and modification
// time, which only a comparison of file identity can see.
func TestPortableReadDetectsMidReadChange(t *testing.T) {
	const content = "0123456789abcdef"
	cases := []struct {
		name   string
		change func(t *testing.T, path string, old os.FileInfo)
		want   string
	}{
		{"unchanged", func(*testing.T, string, os.FileInfo) {}, ""},
		{"mtime only", func(t *testing.T, p string, old os.FileInfo) {
			if e := os.Chtimes(p, old.ModTime(), old.ModTime().Add(5*time.Second)); e != nil {
				t.Fatal(e)
			}
		}, "CONCURRENT_CHANGE"},
		{"size", func(t *testing.T, p string, old os.FileInfo) {
			h, e := os.OpenFile(p, os.O_APPEND|os.O_WRONLY, 0)
			if e != nil {
				t.Fatal(e)
			}
			defer h.Close()
			if _, e = h.WriteString("x"); e != nil {
				t.Fatal(e)
			}
			os.Chtimes(p, old.ModTime(), old.ModTime()) // size is the only difference left
		}, "CONCURRENT_CHANGE"},
		{"identity only", func(t *testing.T, p string, old os.FileInfo) {
			// The opened file stays alive through the reader's handle, so the
			// replacement is necessarily a different file.
			if e := os.Remove(p); e != nil {
				t.Fatalf("cannot remove the file under read: %v", e)
			}
			if e := os.WriteFile(p, []byte(content), 0600); e != nil {
				t.Fatal(e)
			}
			if e := os.Chtimes(p, old.ModTime(), old.ModTime()); e != nil {
				t.Fatal(e)
			}
			now, e := os.Stat(p)
			if e != nil {
				t.Fatal(e)
			}
			if now.Size() != old.Size() || !now.ModTime().Equal(old.ModTime()) || os.SameFile(now, old) {
				t.Fatalf("fixture is not an identity-only change: size %d/%d, mtime %v/%v, same file %v", now.Size(), old.Size(), now.ModTime(), old.ModTime(), os.SameFile(now, old))
			}
		}, "CONCURRENT_CHANGE"},
	}
	for _, c := range cases {
		for _, via := range []string{"ReadEntry", "Read"} {
			t.Run(c.name+"/"+via, func(t *testing.T) {
				f := fs(t)
				p := filepath.Join(f.Root, "busy.bin")
				if e := os.WriteFile(p, []byte(content), 0600); e != nil {
					t.Fatal(e)
				}
				old, e := os.Stat(p)
				if e != nil {
					t.Fatal(e)
				}
				// A path-based stat resolves its file identity lazily, at the first
				// comparison. Compare it with itself now, so the identity recorded
				// is the original file's and not the replacement's.
				if !os.SameFile(old, old) {
					t.Fatal("a file is not the same file as itself")
				}
				fired := 0
				f.afterRead = func(name string) {
					if name != "busy.bin" {
						t.Errorf("seam saw %q", name)
					}
					fired++
					c.change(t, p, old)
				}
				var got error
				if via == "Read" {
					_, got = f.Read("busy.bin", 1<<20)
				} else {
					d, e := f.OpenDir(".")
					if e != nil {
						t.Fatal(e)
					}
					defer d.Close()
					entries, e := d.Entries()
					if e != nil {
						t.Fatal(e)
					}
					_, _, got = d.ReadEntry(entryNamed(t, entries, "busy.bin"), 1<<20)
				}
				if fired != 1 {
					t.Fatalf("the seam ran %d times, want once per read", fired)
				}
				if c.want == "" && got != nil {
					t.Fatalf("an unchanged file failed: %v", got)
				}
				if c.want != "" && fault.Code(got) != c.want {
					t.Fatalf("%s change was not refused: %v, want %s", c.name, got, c.want)
				}
			})
		}
	}
}
