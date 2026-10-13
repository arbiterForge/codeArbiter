//go:build !windows && !linux && !darwin

package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"os"
)

func completionNativeIdentity(path string) (string, error) {
	return "", fault.New("UNSUPPORTED_PLATFORM", "completion workspace identities are unavailable")
}
func completionReparse(info os.FileInfo) bool { return true }

func completionLegacyIdentity(path string) (string, error) { return completionNativeIdentity(path) }
