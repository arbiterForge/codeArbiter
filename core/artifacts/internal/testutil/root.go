package testutil

import (
	"path/filepath"
	"testing"
)

// Root returns the physical path for a temporary directory. Hosted macOS and
// Windows runners place their temporary roots below symlink/reparse aliases;
// production storage correctly rejects those aliases, so tests must pass the
// resolved directory they intend to trust.
func Root(t testing.TB) string {
	t.Helper()
	root := t.TempDir()
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		t.Fatalf("resolve temporary artifact root: %v", err)
	}
	return resolved
}
