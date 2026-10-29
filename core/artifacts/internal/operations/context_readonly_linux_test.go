//go:build linux

package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestContextualReadRequiresWritableReceiptStore(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("privileged runner can write through mode bits")
	}
	h := newHarness(t)
	h.createPair()
	metadata := filepath.Join(h.root, ".codearbiter", ".artifacts")
	if err := os.Chmod(metadata, 0500); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(metadata, 0700) })
	if _, err := h.request("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "mode": "exact"}); err != nil {
		t.Fatalf("exact read should work without receipt writes: %v", err)
	}
	if _, err := h.request("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "mode": "contextual"}); fault.Code(err) != "IO_ERROR" || !strings.Contains(fault.Public(err).Field, "context-tokens") {
		t.Fatalf("contextual read should identify unwritable receipt store: %v", fault.Public(err))
	}
	if _, err := h.request("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "mode": "exact"}); err != nil {
		t.Fatalf("failed contextual read should leave exact reads usable: %v", err)
	}
}
