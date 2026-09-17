package operations

import (
	"runtime"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestCapabilitiesReportActualStorageBackend(t *testing.T) {
	result, err := Run(".", "capabilities", object{"protocol": Protocol})
	if err != nil {
		t.Fatal(err)
	}
	capabilities := result.(object)
	backend := model.S(capabilities["storage_backend"])
	want := map[string]string{
		"linux":   "linux-openat-flock",
		"darwin":  "darwin-osroot-flock",
		"windows": "windows-osroot-lockfileex",
	}[runtime.GOOS]
	if want != "" {
		if backend != want || capabilities["repository_operations_available"] != true {
			t.Fatalf("native capabilities are inaccurate: %#v", capabilities)
		}
		return
	}
	if backend != "unsupported-"+runtime.GOOS || capabilities["repository_operations_available"] != false {
		t.Fatalf("unsupported-platform capabilities are inaccurate: %#v", capabilities)
	}
}
