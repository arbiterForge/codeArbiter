//go:build linux || darwin || windows

package store

import (
	"errors"
	iofs "io/fs"
	"os"
	"runtime"
	"syscall"
)

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
