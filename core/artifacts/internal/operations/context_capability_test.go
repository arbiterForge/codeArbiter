package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestContextCapabilityUsesHostOwnedPermission(t *testing.T) {
	value, err := Run(t.TempDir(), "capabilities", object{"protocol": Protocol})
	if err != nil {
		t.Fatal(err)
	}
	capability := model.M(model.M(value)["repository_context"])
	if capability["kind_registered"] != true || capability["mutation_available"] != true {
		t.Fatalf("native context operations are not registered: %v", capability)
	}
	if capability["host_default_enabled"] != true || capability["qualification"] != "native-tested-package" || capability["permission_model"] != "host-owned" {
		t.Fatalf("ordinary context still requires workflow authority: %v", capability)
	}
}
