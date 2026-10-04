package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestContextCapabilityRequiresPackageEvidence(t *testing.T) {
	value, err := Run(t.TempDir(), "capabilities", object{"protocol": Protocol})
	if err != nil {
		t.Fatal(err)
	}
	capability := model.M(model.M(value)["repository_context"])
	if capability["kind_registered"] != true || capability["mutation_available"] != true {
		t.Fatalf("native context operations are not registered: %v", capability)
	}
	if capability["host_default_enabled"] != false || capability["qualification"] != "package-required" {
		t.Fatalf("source capability claimed package qualification: %v", capability)
	}
}
