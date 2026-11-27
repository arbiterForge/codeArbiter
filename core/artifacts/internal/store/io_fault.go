package store

import (
	"errors"
	"os"

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

func isOperationalIO(err error) bool {
	return operationalIOKind(err) != ""
}
