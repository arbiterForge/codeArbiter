package operations

// NT-02 / N-F01: an ordinary context preview is a registered, validated
// reserved output. Strict consumers (snapshot and normalized completion) must
// recognize it, and a preview that is stale for application is still a valid
// retained output. Transition rows: N16:01, N16:04, N21:01, N21:04, N21:05,
// N17:01.

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func TestContextPreviewComposesWithStrictConsumers(t *testing.T) {
	h, _ := completionHarness(t)
	_, request := contextFixtureAt(t, h.root)
	apply := ordinaryContextPreview(t, h.root, request)

	// N16:04 was UNRECOGNIZED_OUTPUT before NT-02.
	if _, err := h.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err != nil {
		t.Fatalf("a valid ordinary preview broke the strict snapshot: %v", err)
	}
	// Normalized completion closure shares the output recognizer.
	completionVerification(t, h, "T-001", h.root, "normalized")

	target := filepath.Join(h.root, ".codearbiter", "CONTEXT.md")
	out, err := Run(h.root, "context-apply", apply)
	if err != nil {
		t.Fatalf("unchanged preview did not apply: %v", err)
	}
	applied, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := Run(h.root, "context-apply", apply)
	if err != nil || !model.M(replay)["transaction"].(store.Outcome).Replay {
		t.Fatalf("repeated apply did not replay its durable result: %v, %v", replay, err)
	}
	if again, _ := os.ReadFile(target); !bytes.Equal(again, applied) {
		t.Fatal("replayed apply rewrote the document")
	}
	if model.M(out)["transaction"].(store.Outcome).Replay {
		t.Fatal("first apply reported replay")
	}
	// The applied preview remains a recognized historical output.
	if _, err := h.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err != nil {
		t.Fatalf("applied preview became an unrecognized output: %v", err)
	}
}

func TestStaleContextPreviewRemainsRecognizedButCannotApply(t *testing.T) {
	h, _ := completionHarness(t)
	_, request := contextFixtureAt(t, h.root)
	request["operation_id"] = "context-stale-0001"
	request = wholeDocumentRequest(t, h.root, request, "tech-stack", "create", nil, nil, []byte("# Tech stack\n\nRetained preview.\n"))
	apply := ordinaryContextPreview(t, h.root, request)
	writeFixture(t, h.root, ".codearbiter/tech-stack.md", []byte("# Tech stack\n\nIntervening user edit.\n"))
	if _, err := h.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err != nil {
		t.Fatalf("a preview that is stale for application stopped being a valid output: %v", err)
	}
	if _, err := Run(h.root, "context-apply", apply); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale preview applied over an intervening edit: %v", err)
	}
	if b, _ := os.ReadFile(filepath.Join(h.root, ".codearbiter", "tech-stack.md")); string(b) != "# Tech stack\n\nIntervening user edit.\n" {
		t.Fatal("refused apply changed the intervening edit")
	}
}
