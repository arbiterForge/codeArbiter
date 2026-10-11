//go:build !windows

package evidence

import "testing"

// shortNameOf: only Windows volumes have 8.3 short names.
func shortNameOf(t *testing.T, full string) string { return "" }
