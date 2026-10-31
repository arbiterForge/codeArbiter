//go:build linux || darwin

package operations

import (
	"os"
	"syscall"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func singleLink(file *os.File) bool {
	info, err := file.Stat()
	if err != nil {
		return false
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && stat.Nlink == 1
}

func lockLegacyBoard(root string) (func(), error) {
	file, err := openLegacyBoardLock(root)
	if err != nil {
		return nil, err
	}
	deadline := time.Now().Add(2 * time.Second)
	for {
		err = syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			return func() { _ = syscall.Flock(int(file.Fd()), syscall.LOCK_UN); _ = file.Close() }, nil
		}
		if err != syscall.EWOULDBLOCK && err != syscall.EAGAIN {
			file.Close()
			return nil, fault.New("LEGACY_LOCK_FAILED", "cannot lock legacy board")
		}
		if time.Now().After(deadline) {
			file.Close()
			return nil, fault.New("LEGACY_LOCK_TIMEOUT", "legacy board writer is busy; retry cutover")
		}
		time.Sleep(5 * time.Millisecond)
	}
}
