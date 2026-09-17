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
	return &FS{root: r, Root: a}, nil
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
	if e := f.check(rel, false); e != nil {
		return nil, e
	}
	file, e := f.root.Open(native(rel))
	if e != nil {
		if os.IsNotExist(e) {
			return nil, os.ErrNotExist
		}
		return nil, e
	}
	defer file.Close()
	before, e := file.Stat()
	if e != nil || !before.Mode().IsRegular() {
		return nil, fault.New("UNSAFE_PATH", "only regular files can be read")
	}
	if before.Size() > limit {
		return nil, fault.New("MAX_BYTES", "file exceeds operation limit")
	}
	b, e := io.ReadAll(io.LimitReader(file, limit+1))
	if e != nil {
		return nil, e
	}
	if int64(len(b)) > limit {
		return nil, fault.New("MAX_BYTES", "file exceeds operation limit")
	}
	after, e := file.Stat()
	if e != nil || !os.SameFile(before, after) || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return nil, fault.New("CONCURRENT_CHANGE", "file changed while being read")
	}
	return b, nil
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
	d, e := f.root.Open(native(rel))
	if e != nil {
		return nil, e
	}
	defer d.Close()
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
