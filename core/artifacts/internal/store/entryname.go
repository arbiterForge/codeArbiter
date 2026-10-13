package store

import (
	"runtime"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// entryName is the single-component guard shared by every Dir backend. Dir
// methods take a name relative to the anchored directory, so a name that is
// empty, a dot component, or carries a separator would leave that directory.
func entryName(name string) error {
	if name == "" || name == "." || name == ".." || strings.ContainsAny(name, "/\x00") ||
		(runtime.GOOS == "windows" && strings.Contains(name, "\\")) {
		return fault.New("UNSAFE_PATH", "entry name must be a single path component")
	}
	return nil
}
