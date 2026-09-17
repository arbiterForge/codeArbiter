//go:build windows

package store

import (
	"syscall"
	"time"
	"unsafe"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

const (
	lockfileFailImmediately = 0x00000001
	lockfileExclusiveLock   = 0x00000002
	errorLockViolation      = syscall.Errno(33)
)

var (
	kernel32         = syscall.NewLazyDLL("kernel32.dll")
	procLockFileEx   = kernel32.NewProc("LockFileEx")
	procUnlockFileEx = kernel32.NewProc("UnlockFileEx")
)

func (f *FS) nativeLock(exclusive bool, timeout time.Duration) (func(), error) {
	file, e := f.lockFile()
	if e != nil {
		return nil, e
	}
	flags := uint32(lockfileFailImmediately)
	if exclusive {
		flags |= lockfileExclusiveLock
	}
	var overlap syscall.Overlapped
	deadline := time.Now().Add(timeout)
	for {
		r, _, callErr := procLockFileEx.Call(file.Fd(), uintptr(flags), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
		if r != 0 {
			return func() {
				_, _, _ = procUnlockFileEx.Call(file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
				_ = file.Close()
			}, nil
		}
		if callErr != errorLockViolation {
			_ = file.Close()
			return nil, fault.New("LOCK_FAILED", "cannot lock repository")
		}
		if time.Now().After(deadline) {
			_ = file.Close()
			return nil, fault.New("LOCK_TIMEOUT", "repository is busy; retry with a fresh read")
		}
		time.Sleep(10 * time.Millisecond)
	}
}
