package fault

import "testing"

func TestOperationalFaultExitClasses(t *testing.T) {
	for _, tc := range []struct {
		code string
		exit int
	}{
		{"INVALID_REQUEST", 2},
		{"REVISION_CONFLICT", 3},
		{"IO_ERROR", 5},
		{"LOCK_FAILED", 5},
		{"LOCK_TIMEOUT", 5},
		{"NO_LOCAL_STORE", 5},
		{"UNSUPPORTED_VERSION", 6},
		{"CORRUPT_JOURNAL", 7},
		{"ORPHAN_HISTORY", 7},
	} {
		t.Run(tc.code, func(t *testing.T) {
			if got := Exit(New(tc.code, "bounded")); got != tc.exit {
				t.Fatalf("%s exit = %d, want %d", tc.code, got, tc.exit)
			}
		})
	}
}
