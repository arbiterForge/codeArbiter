//go:build windows

package operations

import (
	"os"
	"runtime"
	"syscall"
	"time"
	"unsafe"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func singleLink(file *os.File) bool {
	var info syscall.ByHandleFileInformation
	return syscall.GetFileInformationByHandle(syscall.Handle(file.Fd()), &info) == nil && info.NumberOfLinks == 1
}

var boardLockDLL = syscall.NewLazyDLL("kernel32.dll")
var boardLockProc = boardLockDLL.NewProc("LockFileEx")
var boardUnlockProc = boardLockDLL.NewProc("UnlockFileEx")

func lockLegacyBoard(root string) (func(), error) {
	file, err := openLegacyBoardLock(root)
	if err != nil {
		return nil, err
	}
	var overlap syscall.Overlapped
	deadline := time.Now().Add(2 * time.Second)
	for {
		// LOCKFILE_FAIL_IMMEDIATELY | LOCKFILE_EXCLUSIVE_LOCK, byte 0 length 1.
		r, _, callErr := boardLockProc.Call(file.Fd(), 3, 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
		runtime.KeepAlive(file)
		if r != 0 {
			return func() {
				_, _, _ = boardUnlockProc.Call(file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
				_ = file.Close()
			}, nil
		}
		if callErr != syscall.Errno(33) { // ERROR_LOCK_VIOLATION
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
