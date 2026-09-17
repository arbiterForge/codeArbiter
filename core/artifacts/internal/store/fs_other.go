//go:build !linux && !darwin && !windows

package store

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"os"
	"runtime"
	"time"
)

type FS struct {
	Root   string
	Inject func(string) error
}

const NativeWrites = false

var Backend = "unsupported-" + runtime.GOOS

func unsupported() error {
	return fault.New("UNSUPPORTED_PLATFORM", "repository operations require the tested Linux openat/flock storage backend; native Windows/macOS promotion is pending")
}
func Open(root string) (*FS, error)                    { return nil, unsupported() }
func (f *FS) Close() error                             { return nil }
func (f *FS) Lock(bool, time.Duration) (func(), error) { return nil, unsupported() }
func (f *FS) Read(string, int64) ([]byte, error)       { return nil, unsupported() }
func (f *FS) Exists(string) (bool, error)              { return false, unsupported() }
func (f *FS) List(string) ([]os.DirEntry, error)       { return nil, unsupported() }
func (f *FS) Mkdir(string) error                       { return unsupported() }
func (f *FS) create(string, []byte, uint32) error      { return unsupported() }
func (f *FS) remove(string) error                      { return unsupported() }
func (f *FS) replace(string, string, bool) error       { return unsupported() }
func (f *FS) updateMetadata(string, []byte) error      { return unsupported() }
func (f *FS) Stat(string) (os.FileInfo, error)         { return nil, unsupported() }

func (f *FS) ListUnfollowed(string) ([]os.DirEntry, error) { return nil, unsupported() }
