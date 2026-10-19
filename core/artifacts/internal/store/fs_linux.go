//go:build linux

package store

import (
	"errors"
	"io"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// FS keeps a repository directory descriptor as its trust anchor. Every
// descendant component is opened with O_NOFOLLOW. No shell or chdir is used.
// Locks coordinate cooperating ca-artifact processes, not arbitrary editors.
type FS struct {
	root   *os.File
	Root   string
	Inject func(string) error
	// Stats is the test-only open-counting seam (nil in production).
	Stats *OpenStats
	// memo holds one engine operation's fully validated evidence objects (DEC-07).
	// Open creates it; it is reachable only through Memo and ends with the handle.
	// Nil (a hand-built FS) disables reuse.
	memo *Memo
	// readHook is a test-only seam (nil in production); see SetReadHook.
	readHook func(rel string, anchored bool)
	// afterRead is a test-only seam (nil in production) run after a file's bytes
	// are read and before the closing identity check, so a test can change the
	// file at exactly that point. It receives the name that was read.
	afterRead func(name string)
}

const NativeWrites = true
const Backend = "linux-openat-flock"

func Open(root string) (*FS, error) {
	a, e := filepath.Abs(root)
	if e != nil {
		return nil, e
	}
	fd, e := syscall.Open(a, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, fault.New("UNSAFE_ROOT", "repository root must be an existing real directory")
	}
	return &FS{root: os.NewFile(uintptr(fd), a), Root: a, memo: newMemo()}, nil
}
func (f *FS) Close() error { return f.root.Close() }

// LockMetadataPresent reports whether the files this platform's lock needs
// exist. Linux locks the repository directory itself, so it needs none.
func (f *FS) LockMetadataPresent() (bool, error) { return true, nil }
func (f *FS) Lock(exclusive bool, timeout time.Duration) (func(), error) {
	op := syscall.LOCK_SH
	if exclusive {
		op = syscall.LOCK_EX
	}
	deadline := time.Now().Add(timeout)
	for {
		e := syscall.Flock(int(f.root.Fd()), op|syscall.LOCK_NB)
		if e == nil {
			return func() { _ = syscall.Flock(int(f.root.Fd()), syscall.LOCK_UN) }, nil
		}
		if e != syscall.EWOULDBLOCK && e != syscall.EAGAIN {
			return nil, fault.New("LOCK_FAILED", "cannot lock repository directory")
		}
		if time.Now().After(deadline) {
			return nil, fault.New("LOCK_TIMEOUT", "repository is busy; retry with a fresh read")
		}
		time.Sleep(10 * time.Millisecond)
	}
}
func (f *FS) dir(rel string, create bool) (*os.File, error) {
	if !validate.Path(rel, true) {
		return nil, fault.New("UNSAFE_PATH", "invalid repository directory path")
	}
	fd, e := syscall.Openat(int(f.root.Fd()), ".", syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, e
	}
	f.Stats.dirOpen()
	cur := os.NewFile(uintptr(fd), f.Root)
	if rel == "." {
		return cur, nil
	}
	for _, part := range strings.Split(rel, "/") {
		f.Stats.ancestor()
		n, e := syscall.Openat(int(cur.Fd()), part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		if e == syscall.ENOENT && create {
			if e = syscall.Mkdirat(int(cur.Fd()), part, 0755); e != nil && e != syscall.EEXIST {
				cur.Close()
				return nil, e
			}
			if e = cur.Sync(); e != nil {
				cur.Close()
				return nil, e
			}
			n, e = syscall.Openat(int(cur.Fd()), part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		}
		cur.Close()
		if e != nil {
			if e == syscall.ENOENT {
				return nil, os.ErrNotExist
			}
			return nil, fault.New("UNSAFE_PATH", "directory is not a safe real directory")
		}
		cur = os.NewFile(uintptr(n), part)
	}
	return cur, nil
}
func (f *FS) parent(rel string, create bool) (*os.File, string, error) {
	if !validate.Path(rel, false) {
		return nil, "", fault.New("UNSAFE_PATH", "invalid repository path")
	}
	d, e := f.dir(path.Dir(rel), create)
	return d, path.Base(rel), e
}
func (f *FS) Read(rel string, limit int64) ([]byte, error) {
	if f.readHook != nil {
		f.readHook(rel, false)
	}
	d, n, e := f.parent(rel, false)
	if e != nil {
		return nil, e
	}
	defer d.Close()
	b, _, e := f.readAt(d, n, limit)
	return b, e
}

// readAt opens name relative to the directory descriptor d exactly once and
// reads it under the size limit, returning the identity of the opened handle.
func (f *FS) readAt(d *os.File, n string, limit int64) ([]byte, os.FileInfo, error) {
	f.Stats.fileOpen()
	fd, e := syscall.Openat(int(d.Fd()), n, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if e != nil {
		if e == syscall.ENOENT {
			return nil, nil, os.ErrNotExist
		}
		return nil, nil, fault.New("UNSAFE_PATH", "file is not a safe readable regular file")
	}
	file := os.NewFile(uintptr(fd), n)
	defer file.Close()
	before, e := file.Stat()
	if e != nil || !before.Mode().IsRegular() {
		return nil, nil, fault.New("UNSAFE_PATH", "only regular files can be read")
	}
	if before.Size() > limit {
		return nil, nil, fault.New("MAX_BYTES", "file exceeds operation limit")
	}
	b, e := io.ReadAll(io.LimitReader(file, limit+1))
	if e != nil {
		return nil, nil, e
	}
	if int64(len(b)) > limit {
		return nil, nil, fault.New("MAX_BYTES", "file exceeds operation limit")
	}
	if f.afterRead != nil {
		f.afterRead(n)
	}
	after, e := file.Stat()
	if e != nil {
		return nil, nil, e
	}
	bs, as := before.Sys().(*syscall.Stat_t), after.Sys().(*syscall.Stat_t)
	if before.Size() != after.Size() || bs.Mtim != as.Mtim || bs.Ctim != as.Ctim {
		return nil, nil, fault.New("CONCURRENT_CHANGE", "file changed while being read")
	}
	// The handle alone cannot show a replacement: its descriptor always names the
	// file that was opened. Identity (device and inode) is therefore read from the
	// name, without following links, and must still be the opened file's.
	f.Stats.entryCheck()
	if !sameNamedFile(d, n, bs) {
		return nil, nil, fault.New("CONCURRENT_CHANGE", "file changed while being read")
	}
	return b, before, nil
}

// oPath is Linux O_PATH, which package syscall does not name; its value is the
// same on every architecture Go supports for Linux.
const oPath = 0x200000

// sameNamedFile reports whether name, resolved relative to d without following a
// link, is the file whose identity is want. O_PATH yields a descriptor for the
// name itself (a replacing symlink included) without opening the file's data.
func sameNamedFile(d *os.File, name string, want *syscall.Stat_t) bool {
	fd, e := syscall.Openat(int(d.Fd()), name, oPath|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return false
	}
	defer syscall.Close(fd)
	var named syscall.Stat_t
	return syscall.Fstat(fd, &named) == nil && named.Dev == want.Dev && named.Ino == want.Ino
}

func (f *FS) Exists(rel string) (bool, error) {
	d, n, e := f.parent(rel, false)
	if e != nil {
		if errors.Is(e, os.ErrNotExist) {
			return false, nil
		}
		return false, e
	}
	defer d.Close()
	fd, e := syscall.Openat(int(d.Fd()), n, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if e == syscall.ENOENT {
		return false, nil
	}
	if e != nil {
		return false, fault.New("UNSAFE_PATH", "path exists but is unsafe")
	}
	syscall.Close(fd)
	return true, nil
}

// ListUnfollowed returns directory entries without dereferencing their targets.
// Callers must apply their explicit exclusion policy before opening an entry;
// subsequent Read/dir operations still refuse every symlink component.
func (f *FS) ListUnfollowed(rel string) ([]os.DirEntry, error) {
	d, e := f.dir(rel, false)
	if e != nil {
		return nil, e
	}
	defer d.Close()
	return sortedEntries(d)
}

func sortedEntries(d *os.File) ([]os.DirEntry, error) {
	out, e := d.ReadDir(100001)
	if e != nil && e != io.EOF {
		return nil, e
	}
	if len(out) > 100000 {
		return nil, fault.New("MAX_ENTRIES", "directory entry limit exceeded")
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name() < out[j].Name() })
	return out, nil
}

// Dir is a scan-scoped directory anchor (ADR-0042 AC-08). OpenDir resolves the
// path from the repository root once; everything below an anchored directory is
// opened relative to its descriptor with O_NOFOLLOW, so opening a child costs
// one open and no ancestor re-check. The same descriptor is enumerated, so a
// directory is opened exactly once.
type Dir struct {
	f   *FS
	fd  *os.File
	rel string
}

// OpenDir anchors the real directory at rel.
func (f *FS) OpenDir(rel string) (*Dir, error) {
	fd, e := f.dir(rel, false)
	if e != nil {
		return nil, e
	}
	return &Dir{f: f, fd: fd, rel: rel}, nil
}

func (d *Dir) Close() error { return d.fd.Close() }

// Entries lists the directory without dereferencing any entry, sorted by name.
// The anchoring descriptor is rewound first, so a repeated call lists the same
// entries again instead of continuing from the previous end of directory.
func (d *Dir) Entries() ([]os.DirEntry, error) {
	if _, e := d.fd.Seek(0, io.SeekStart); e != nil {
		return nil, e
	}
	return sortedEntries(d.fd)
}

// OpenSub anchors a child directory named by a listed entry. Anything that the
// listing did not report as a real directory is refused.
func (d *Dir) OpenSub(entry os.DirEntry) (*Dir, error) {
	if !entry.IsDir() {
		return nil, fault.New("UNSAFE_PATH", "only real directories can be descended")
	}
	if e := entryName(entry.Name()); e != nil {
		return nil, e
	}
	d.f.Stats.dirOpen()
	fd, e := syscall.Openat(int(d.fd.Fd()), entry.Name(), syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		if e == syscall.ENOENT {
			return nil, os.ErrNotExist
		}
		return nil, fault.New("UNSAFE_PATH", "directory is not a safe real directory")
	}
	return &Dir{f: d.f, fd: os.NewFile(uintptr(fd), entry.Name()), rel: d.rel + "/" + entry.Name()}, nil
}

// ReadEntry opens a listed regular file once and returns its bytes together
// with the identity of the opened handle. Anything not reported as a plain
// regular file by the listing is refused; O_NOFOLLOW backs that at open time.
func (d *Dir) ReadEntry(entry os.DirEntry, limit int64) ([]byte, os.FileInfo, error) {
	if entry.Type() != 0 {
		return nil, nil, fault.New("UNSAFE_PATH", "only regular files can be read")
	}
	if e := entryName(entry.Name()); e != nil {
		return nil, nil, e
	}
	if d.f.readHook != nil {
		d.f.readHook(d.rel+"/"+entry.Name(), true)
	}
	return d.f.readAt(d.fd, entry.Name(), limit)
}

// Has reports whether name exists in the directory under any spelling the
// platform resolves, without following it. It exists only to tell a missing
// path from a non-canonical spelling of an existing one.
func (d *Dir) Has(name string) (bool, error) {
	if e := entryName(name); e != nil {
		return false, e
	}
	fd, e := syscall.Openat(int(d.fd.Fd()), name, oPath|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	switch e {
	case nil:
		syscall.Close(fd)
		return true, nil
	case syscall.ENOENT:
		return false, nil
	case syscall.ELOOP:
		return true, nil // a symlink: it exists, and is never followed
	}
	return false, e
}

// List is the strict catalog/infrastructure scan: any symlink is an error.
func (f *FS) List(rel string) ([]os.DirEntry, error) {
	out, e := f.ListUnfollowed(rel)
	if e != nil {
		return nil, e
	}
	for _, v := range out {
		if v.Type()&os.ModeSymlink != 0 {
			return nil, fault.New("UNSAFE_PATH", "symlink encountered in scanned directory")
		}
	}
	return out, nil
}
func (f *FS) Mkdir(rel string) error {
	d, e := f.dir(rel, true)
	if e == nil {
		e = d.Sync()
		d.Close()
	}
	return e
}
func (f *FS) create(rel string, b []byte, mode uint32) error {
	d, n, e := f.parent(rel, true)
	if e != nil {
		return e
	}
	defer d.Close()
	fd, e := syscall.Openat(int(d.Fd()), n, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, mode)
	if e != nil {
		if e == syscall.EEXIST {
			return fault.New("ALREADY_EXISTS", "create-only target already exists")
		}
		return e
	}
	file := os.NewFile(uintptr(fd), n)
	ok := false
	defer func() {
		file.Close()
		if !ok {
			_ = syscall.Unlinkat(int(d.Fd()), n)
		}
	}()
	if _, e = file.Write(b); e != nil {
		return e
	}
	if e = file.Sync(); e != nil {
		return e
	}
	if e = file.Close(); e != nil {
		return e
	}
	if e = d.Sync(); e != nil {
		return e
	}
	ok = true
	return nil
}
func (f *FS) remove(rel string) error {
	d, n, e := f.parent(rel, false)
	if e != nil {
		return e
	}
	defer d.Close()
	if e = syscall.Unlinkat(int(d.Fd()), n); e != nil {
		return e
	}
	return d.Sync()
}
func linkat(oldfd int, old string, newfd int, new string) error {
	a, e := syscall.BytePtrFromString(old)
	if e != nil {
		return e
	}
	b, e := syscall.BytePtrFromString(new)
	if e != nil {
		return e
	}
	_, _, errno := syscall.Syscall6(syscall.SYS_LINKAT, uintptr(oldfd), uintptr(unsafe.Pointer(a)), uintptr(newfd), uintptr(unsafe.Pointer(b)), 0, 0)
	if errno != 0 {
		return errno
	}
	return nil
}
func (f *FS) replace(stage, dest string, createOnly bool) error {
	a, an, e := f.parent(stage, false)
	if e != nil {
		return e
	}
	defer a.Close()
	b, bn, e := f.parent(dest, true)
	if e != nil {
		return e
	}
	defer b.Close()
	if createOnly {
		e = linkat(int(a.Fd()), an, int(b.Fd()), bn)
		if e == nil {
			e = syscall.Unlinkat(int(a.Fd()), an)
		}
	} else {
		e = syscall.Renameat(int(a.Fd()), an, int(b.Fd()), bn)
	}
	if e != nil {
		return e
	}
	if e = b.Sync(); e != nil {
		return e
	}
	return a.Sync()
}
func (f *FS) updateMetadata(rel string, b []byte) error {
	tmp := rel + ".next"
	if _, e := f.Read(tmp, 16<<20); e == nil {
		if e = f.remove(tmp); e != nil {
			return e
		}
	}
	if e := f.create(tmp, b, 0600); e != nil {
		return e
	}
	return f.replace(tmp, rel, false)
}

// Stat uses the anchored descriptor, never DirEntry.Info's name-based fallback.
func (f *FS) Stat(rel string) (os.FileInfo, error) {
	d, n, e := f.parent(rel, false)
	if e != nil {
		return nil, e
	}
	defer d.Close()
	f.Stats.fileOpen()
	fd, e := syscall.Openat(int(d.Fd()), n, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if e != nil {
		return nil, e
	}
	file := os.NewFile(uintptr(fd), n)
	defer file.Close()
	return file.Stat()
}
