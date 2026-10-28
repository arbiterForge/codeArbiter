package store

import (
	"errors"
	"os"
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
	kind := "IO_FAILURE"
	switch {
	case errors.Is(err, syscall.EACCES):
		kind = "EACCES"
	case errors.Is(err, syscall.EPERM):
		kind = "EPERM"
	case errors.Is(err, syscall.EIO):
		kind = "EIO"
	case errors.Is(err, syscall.ENOSPC):
		kind = "ENOSPC"
	case errors.Is(err, syscall.EBADF):
		kind = "EBADF"
	case !errors.Is(err, os.ErrClosed):
		return err
	}
	return fault.At("IO_ERROR", "", target, operation+" failed ("+kind+")")
}

func isOperationalIO(err error) bool {
	return errors.Is(err, syscall.EACCES) || errors.Is(err, syscall.EPERM) ||
		errors.Is(err, syscall.EIO) || errors.Is(err, syscall.ENOSPC) ||
		errors.Is(err, syscall.EBADF) || errors.Is(err, os.ErrClosed)
}
