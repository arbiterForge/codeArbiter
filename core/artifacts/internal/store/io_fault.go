package store

import (
	"errors"
	iofs "io/fs"
	"os"
	"runtime"
	"syscall"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// ioFault reports a validated repository-relative target without exposing the
// underlying OS error, which may contain an absolute path or credential text.
func ioFault(operation, target string, err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, os.ErrNotExist) {
		return err
	}
	var known *fault.Error
	if errors.As(err, &known) {
		return err
	}
	kind := operationalIOKind(err)
	if kind == "" {
		return err
	}
	return fault.At("IO_ERROR", "", target, operation+" failed ("+kind+")")
}

func operationalIOKind(err error) string {
	switch {
	case errors.Is(err, syscall.EACCES):
		return "EACCES"
	case errors.Is(err, syscall.EPERM):
		return "EPERM"
	case errors.Is(err, iofs.ErrPermission):
		return "EACCES"
	case errors.Is(err, syscall.EROFS):
		return "EROFS"
	case errors.Is(err, syscall.EIO):
		return "EIO"
	case errors.Is(err, syscall.ENOSPC):
		return "ENOSPC"
	case errors.Is(err, syscall.EBADF):
		return "EBADF"
	// Go's syscall package does not name these Win32 disk-full codes.
	case runtime.GOOS == "windows" && errors.Is(err, syscall.Errno(112)):
		return "ERROR_DISK_FULL"
	case runtime.GOOS == "windows" && errors.Is(err, syscall.Errno(39)):
		return "ERROR_HANDLE_DISK_FULL"
	case errors.Is(err, os.ErrClosed):
		return "IO_FAILURE"
	}
	return ""
}

func isOperationalIO(err error) bool {
	return operationalIOKind(err) != ""
}
