//go:build darwin || windows

package store

import (
	"errors"
	"io"
	"os"
	"path"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// FS uses Go's native directory-handle-backed os.Root containment on Windows
// and macOS. Explicit Lstat checks reject symlink/reparse components; os.Root
// remains the race-safe containment boundary if a component changes afterward.
type FS struct {
	root   *os.Root
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

var Backend = map[string]string{
	"darwin":  "darwin-osroot-flock",
	"windows": "windows-osroot-lockfileex",
}[runtime.GOOS]

func Open(root string) (*FS, error) {
	a, e := filepath.Abs(root)
	if e != nil {
		return nil, e
	}
	info, e := os.Lstat(a)
	if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return nil, fault.New("UNSAFE_ROOT", "repository root must be an existing real directory")
	}
	real, e := filepath.EvalSymlinks(a)
	if e != nil || !samePath(real, a) {
		return nil, fault.New("UNSAFE_ROOT", "repository root path must not traverse a symlink or reparse point")
	}
	r, e := os.OpenRoot(a)
	if e != nil {
		return nil, fault.New("UNSAFE_ROOT", "repository root could not be anchored")
	}
	return &FS{root: r, Root: a, memo: newMemo()}, nil
}

func samePath(a, b string) bool {
	if runtime.GOOS == "windows" {
		return strings.EqualFold(filepath.Clean(a), filepath.Clean(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}

func (f *FS) Close() error { return f.root.Close() }

func native(rel string) string { return filepath.FromSlash(rel) }

// check rejects existing symlink/reparse components. Missing tail components
// are permitted only for create paths; os.Root independently prevents escape.
func (f *FS) check(rel string, allowMissing bool) error {
	if !validate.Path(rel, true) {
		return fault.New("UNSAFE_PATH", "invalid repository path")
	}
	if rel == "." {
		return nil
	}
	cur := ""
	parts := strings.Split(rel, "/")
	for i, part := range parts {
		if cur == "" {
			cur = part
		} else {
			cur += "/" + part
		}
		f.Stats.ancestor()
		info, e := f.root.Lstat(native(cur))
		if os.IsNotExist(e) && allowMissing {
			return nil
		}
		if e != nil {
			if os.IsNotExist(e) {
				return os.ErrNotExist
			}
			return e
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return fault.New("UNSAFE_PATH", "symlink or reparse point encountered in repository path")
		}
		if i < len(parts)-1 && !info.IsDir() {
			return fault.New("UNSAFE_PATH", "non-directory repository path component")
		}
	}
	return nil
}

func (f *FS) parent(rel string, create bool) (string, string, error) {
	if !validate.Path(rel, false) {
		return "", "", fault.New("UNSAFE_PATH", "invalid repository path")
	}
	dir, name := path.Dir(rel), path.Base(rel)
	if e := f.check(dir, create); e != nil {
		return "", "", e
	}
	if create {
		if e := f.root.MkdirAll(native(dir), 0755); e != nil {
			return "", "", e
		}
		if e := f.check(dir, false); e != nil {
			return "", "", e
		}
	}
	return dir, name, nil
}

func (f *FS) Read(rel string, limit int64) ([]byte, error) {
	if f.readHook != nil {
		f.readHook(rel, false)
	}
	if e := f.check(rel, false); e != nil {
		return nil, e
	}
	f.Stats.fileOpen()
	file, e := f.root.Open(native(rel))
	if e != nil {
		if os.IsNotExist(e) {
			return nil, os.ErrNotExist
		}
		return nil, e
	}
	defer file.Close()
	b, _, e := f.readOpened(file, limit, f.root, native(rel))
	return b, e
}

// readOpened reads an already-open file under the size limit and returns its
// bytes with the identity the open handle reported before the read. The file is
// refused if it changed across the read: its size or modification time moved, or
// the name no longer resolves, without following links, to the very file that was
// opened (it was replaced or removed). The handle alone cannot show a
// replacement, so the closing identity is read from the name, relative to root.
func (f *FS) readOpened(file *os.File, limit int64, root *os.Root, name string) ([]byte, os.FileInfo, error) {
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
		f.afterRead(name)
	}
	after, e := file.Stat()
	if e != nil || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return nil, nil, fault.New("CONCURRENT_CHANGE", "file changed while being read")
	}
	f.Stats.entryCheck()
	named, e := root.Lstat(name)
	if e != nil || !os.SameFile(before, named) {
		return nil, nil, fault.New("CONCURRENT_CHANGE", "file changed while being read")
	}
	return b, before, nil
}

func (f *FS) Exists(rel string) (bool, error) {
	if e := f.check(rel, false); e != nil {
		if errors.Is(e, os.ErrNotExist) {
			return false, nil
		}
		return false, e
	}
	return true, nil
}

func (f *FS) ListUnfollowed(rel string) ([]os.DirEntry, error) {
	if e := f.check(rel, false); e != nil {
		return nil, e
	}
	f.Stats.dirOpen()
	d, e := f.root.Open(native(rel))
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

// Dir is a scan-scoped directory anchor (ADR-0042 AC-08). OpenDir validates the
// path from the repository root once; everything below an anchored directory is
// reached relative to it, so opening a child costs one handle open and no
// ancestor re-check. Symlink and reparse refusal comes from the directory
// listing's own entry types; os.Root remains the containment boundary.
type Dir struct {
	f    *FS
	root *os.Root
	rel  string
}

// OpenDir anchors the real directory at rel.
func (f *FS) OpenDir(rel string) (*Dir, error) {
	if e := f.check(rel, false); e != nil {
		return nil, e
	}
	if rel != "." {
		// The final component must itself be a real directory. Windows reports a
		// regular file opened as a directory as "not found", which would make a
		// file in a directory's place read as an absent directory.
		info, e := f.root.Lstat(native(rel))
		if e != nil {
			if os.IsNotExist(e) {
				return nil, os.ErrNotExist
			}
			return nil, e
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return nil, fault.New("UNSAFE_PATH", "repository path is not a real directory")
		}
	}
	f.Stats.dirOpen()
	r, e := f.root.OpenRoot(native(rel))
	if e != nil {
		if os.IsNotExist(e) {
			return nil, os.ErrNotExist
		}
		return nil, e
	}
	// Like OpenSub: OpenRoot follows links, so the opened directory must be the
	// very real directory the name resolves to without following.
	if rel != "." {
		f.Stats.entryCheck()
		li, e := f.root.Lstat(native(rel))
		hi, e2 := r.Stat(".")
		if e != nil || e2 != nil || !li.IsDir() || li.Mode()&os.ModeSymlink != 0 {
			r.Close()
			return nil, fault.New("UNSAFE_PATH", "repository path is not a real directory")
		}
		if !os.SameFile(hi, li) {
			r.Close()
			return nil, fault.New("CONCURRENT_CHANGE", "directory changed while being opened")
		}
	}
	return &Dir{f: f, root: r, rel: rel}, nil
}

func (d *Dir) Close() error { return d.root.Close() }

// Entries lists the directory without dereferencing any entry, sorted by name.
func (d *Dir) Entries() ([]os.DirEntry, error) {
	d.f.Stats.enumOpen()
	h, e := d.root.Open(".")
	if e != nil {
		return nil, e
	}
	defer h.Close()
	return sortedEntries(h)
}

// OpenSub anchors a child directory named by a listed entry. Anything that the
// listing did not report as a real directory (a link, reparse point or file) is
// refused.
func (d *Dir) OpenSub(entry os.DirEntry) (*Dir, error) {
	if !entry.IsDir() {
		return nil, fault.New("UNSAFE_PATH", "only real directories can be descended")
	}
	name := entry.Name()
	if e := entryName(name); e != nil {
		return nil, e
	}
	d.f.Stats.dirOpen()
	r, e := d.root.OpenRoot(name)
	if e != nil {
		if os.IsNotExist(e) {
			return nil, os.ErrNotExist
		}
		return nil, e
	}
	// The listing's type is only a hint: the name may have been swapped for a
	// link since. OpenRoot follows links, so the opened directory must be the
	// very directory the name now resolves to without following.
	d.f.Stats.entryCheck()
	li, e := d.root.Lstat(name)
	if e != nil || !li.IsDir() || li.Mode()&os.ModeSymlink != 0 {
		r.Close()
		return nil, fault.New("UNSAFE_PATH", "entry is no longer a real directory")
	}
	hi, e := r.Stat(".")
	if e != nil || !os.SameFile(hi, li) {
		r.Close()
		return nil, fault.New("UNSAFE_PATH", "entry changed while being opened")
	}
	return &Dir{f: d.f, root: r, rel: d.rel + "/" + name}, nil
}

// ReadEntry opens a listed regular file once and returns its bytes together
// with the identity of the opened handle. Anything not reported as a plain
// regular file by the listing (symlink, reparse point, device) is refused.
func (d *Dir) ReadEntry(entry os.DirEntry, limit int64) ([]byte, os.FileInfo, error) {
	if entry.Type() != 0 {
		return nil, nil, fault.New("UNSAFE_PATH", "only regular files can be read")
	}
	name := entry.Name()
	if e := entryName(name); e != nil {
		return nil, nil, e
	}
	if d.f.readHook != nil {
		d.f.readHook(d.rel+"/"+name, true)
	}
	d.f.Stats.fileOpen()
	file, e := d.root.Open(name)
	if e != nil {
		if os.IsNotExist(e) {
			return nil, nil, os.ErrNotExist
		}
		return nil, nil, e
	}
	defer file.Close()
	// The listing's type is only a hint: Open follows links, so the handle must
	// be the regular file the name resolves to without following.
	d.f.Stats.entryCheck()
	li, e := d.root.Lstat(name)
	if e != nil || !li.Mode().IsRegular() {
		return nil, nil, fault.New("UNSAFE_PATH", "entry is no longer a regular file")
	}
	hi, e := file.Stat()
	if e != nil || !os.SameFile(hi, li) {
		return nil, nil, fault.New("UNSAFE_PATH", "entry changed while being opened")
	}
	return d.f.readOpened(file, limit, d.root, name)
}

// Has reports whether name exists in the directory under any spelling the
// platform resolves, without following it. It exists only to tell a missing
// path from a non-canonical spelling of an existing one.
func (d *Dir) Has(name string) (bool, error) {
	if e := entryName(name); e != nil {
		return false, e
	}
	if _, e := d.root.Lstat(name); e != nil {
		if os.IsNotExist(e) {
			return false, nil
		}
		return false, e
	}
	return true, nil
}

func (f *FS) List(rel string) ([]os.DirEntry, error) {
	out, e := f.ListUnfollowed(rel)
	if e != nil {
		return nil, e
	}
	for _, entry := range out {
		if entry.Type()&os.ModeSymlink != 0 {
			return nil, fault.New("UNSAFE_PATH", "symlink or reparse point encountered in scanned directory")
		}
	}
	return out, nil
}

func (f *FS) Mkdir(rel string) error {
	if e := f.check(rel, true); e != nil {
		return e
	}
	if e := f.root.MkdirAll(native(rel), 0755); e != nil {
		return e
	}
	return f.syncDir(path.Dir(rel))
}

func (f *FS) create(rel string, b []byte, mode uint32) error {
	dir, name, e := f.parent(rel, true)
	if e != nil {
		return e
	}
	file, e := f.root.OpenFile(native(path.Join(dir, name)), os.O_WRONLY|os.O_CREATE|os.O_EXCL, os.FileMode(mode))
	if e != nil {
		if os.IsExist(e) {
			return fault.New("ALREADY_EXISTS", "create-only target already exists")
		}
		return e
	}
	ok := false
	defer func() {
		_ = file.Close()
		if !ok {
			_ = f.root.Remove(native(rel))
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
	if e = f.syncDir(dir); e != nil {
		return e
	}
	ok = true
	return nil
}

func (f *FS) remove(rel string) error {
	dir, _, e := f.parent(rel, false)
	if e != nil {
		return e
	}
	if e = f.check(rel, false); e != nil {
		return e
	}
	if e = f.root.Remove(native(rel)); e != nil {
		return e
	}
	return f.syncDir(dir)
}

func (f *FS) replace(stage, dest string, createOnly bool) error {
	a, _, e := f.parent(stage, false)
	if e != nil {
		return e
	}
	b, _, e := f.parent(dest, true)
	if e != nil {
		return e
	}
	if e = f.check(stage, false); e != nil {
		return e
	}
	if createOnly {
		if e = f.root.Link(native(stage), native(dest)); e == nil {
			e = f.root.Remove(native(stage))
		}
	} else {
		e = f.root.Rename(native(stage), native(dest))
	}
	if e != nil {
		return e
	}
	if e = f.syncDir(b); e != nil {
		return e
	}
	return f.syncDir(a)
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

func (f *FS) Stat(rel string) (os.FileInfo, error) {
	if e := f.check(rel, false); e != nil {
		return nil, e
	}
	f.Stats.fileOpen()
	file, e := f.root.Open(native(rel))
	if e != nil {
		return nil, e
	}
	defer file.Close()
	return file.Stat()
}

func (f *FS) syncDir(rel string) error {
	if runtime.GOOS == "windows" {
		// Windows replacement durability is supplied by the file flush and the
		// native rename implementation; directory handles cannot be Sync'ed by os.
		return nil
	}
	d, e := f.root.Open(native(rel))
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}

func (f *FS) lockFile() (*os.File, error) {
	if e := f.root.MkdirAll(native(meta), 0755); e != nil {
		return nil, e
	}
	if e := f.check(meta, false); e != nil {
		return nil, e
	}
	return f.root.OpenFile(native(meta+"/store.lock"), os.O_RDWR|os.O_CREATE, 0600)
}

// implemented by the native lock file for each supported platform.
func (f *FS) Lock(exclusive bool, timeout time.Duration) (func(), error) {
	return f.nativeLock(exclusive, timeout)
}
