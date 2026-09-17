//go:build darwin

package store

import (
	"syscall"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func (f *FS) nativeLock(exclusive bool, timeout time.Duration) (func(), error) {
	file, e := f.lockFile()
	if e != nil {
		return nil, e
	}
	op := syscall.LOCK_SH
	if exclusive {
		op = syscall.LOCK_EX
	}
	deadline := time.Now().Add(timeout)
	for {
		e = syscall.Flock(int(file.Fd()), op|syscall.LOCK_NB)
		if e == nil {
			return func() { _ = syscall.Flock(int(file.Fd()), syscall.LOCK_UN); _ = file.Close() }, nil
		}
		if e != syscall.EWOULDBLOCK && e != syscall.EAGAIN {
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
