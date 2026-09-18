package operations

import (
	"runtime"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	artifactSchema "github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
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

func TestWorkflowStateEventsRequireUserOrSMARTSAuthority(t *testing.T) {
	tests := []map[string]any{
		{"kind": "prerequisite", "authority_kind": "verification_runner", "verdict": "satisfied"},
		{"kind": "reconciliation", "authority_kind": "review_workflow", "verdict": "reconciled"},
	}
	for _, values := range tests {
		event := map[string]any{
			"format":         "codearbiter.workflow-event/0.1.0",
			"kind":           values["kind"],
			"authority_kind": values["authority_kind"],
			"subject": map[string]any{
				"artifact_id":      "PLAN-EXAMPLE",
				"normative_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
				"record_id":        "T-001",
			},
			"actor":       "caller supplied label",
			"origin":      "untrusted request field",
			"verdict":     values["verdict"],
			"payload":     map[string]any{},
			"source_text": "A caller label is not workflow authority.",
		}
		if err := authority.ValidateEvent(event); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
			t.Fatalf("caller authority label was accepted: %v", err)
		}
	}
}

func TestCaptureRequestRequiresBoundAuthoritySource(t *testing.T) {
	requestSchema, err := RequestSchema("capture")
	if err != nil {
		t.Fatal(err)
	}
	inline := map[string]any{
		"protocol": Protocol,
		"event": map[string]any{
			"format":         "codearbiter.workflow-event/0.1.0",
			"kind":           "approval",
			"authority_kind": "user_workflow",
			"subject": map[string]any{
				"artifact_id":      "SPEC-EXAMPLE",
				"normative_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
				"record_id":        "SPEC-EXAMPLE",
			},
			"actor":       "caller supplied label",
			"origin":      "untrusted request field",
			"verdict":     "approved",
			"payload":     map[string]any{},
			"source_text": "A caller label is not workflow authority.",
		},
	}
	if errors := artifactSchema.ValidateWith(requestSchema, inline); len(errors) == 0 {
		t.Fatal("inline caller event satisfies the capture request schema")
	}
	bound := map[string]any{
		"protocol":      Protocol,
		"source_ref":    ".codearbiter/.artifacts/authority-sources/0000000000000000000000000000000000000000000000000000000000000000.json",
		"source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
	}
	if errors := artifactSchema.ValidateWith(requestSchema, bound); len(errors) != 0 {
		t.Fatalf("bound authority source is not the capture request contract: %v", errors)
	}
}
