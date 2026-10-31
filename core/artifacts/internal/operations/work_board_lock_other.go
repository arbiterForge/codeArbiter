//go:build !linux && !darwin && !windows

package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"os"
)

func singleLink(*os.File) bool { return false }

func lockLegacyBoard(string) (func(), error) {
	return nil, fault.New("UNSUPPORTED_PLATFORM", "legacy board adoption needs a tested native lock backend")
}
