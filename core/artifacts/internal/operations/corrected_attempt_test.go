package operations

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// NT-11 engine conformance only. These are explicitly synthetic producer
// fixtures, not evidence that an actual host launched or observed a reviewer.
func TestCorrectedFreshReviewAttemptDoesNotRewriteRejectedSource(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	startNativeV1FixtureTask(t, h, "T-001")
	base, _ := nativeProtocolReviewSource(t, h, "T-001", "spec_review")
	makeAttempt := func(runID, requestID, decision string) object {
		event := h.derived(model.S(base["source_ref"]))
		observed := h.derived(model.S(event["observation_ref"]))
		producer := model.M(observed["producer_result"])
		launch := model.M(producer["launch"])
		launch["agent_id"], launch["child_turn_id"] = runID, runID
		launch["tool_use_id"] = "synthetic-tool-" + requestID
		model.M(launch["native_child"])["thread_id"] = runID
		activity := model.M(launch["native_activity"])
		model.M(activity["item"])["agent_thread_id"] = runID
		model.M(activity["item"])["id"] = launch["tool_use_id"]
		launch["native_activity_sha256"] = mustHashFixture(t, activity)
		model.M(producer["decision"])["request_id"] = mustHashFixture(t, requestID)
		model.M(producer["decision"])["decision"] = decision
		observed["producer_run_id"] = runID
		observed["producer_result_sha256"] = mustHashFixture(t, producer)
		if decision != "pass" {
			return observed // Rejections belong to host history, never the success-only native namespace.
		}
		event["observation_ref"] = h.forge("observations", observed)
		event["observation_sha256"] = mustHashFixture(t, observed)
		return object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)}
	}
	rejected := makeAttempt("e0123456-789b-4cde-8123-456789abcdef", "rejected-attempt", "changes_requested")
	path := filepath.Join(t.TempDir(), "rejected-host-attempt.json")
	before, err := canonical.Marshal(rejected)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, before, 0600); err != nil {
		t.Fatal(err)
	}
	if es := schema.ValidateWith(observation.Schema(), rejected); len(es) == 0 {
		t.Fatal("a changes_requested result became a successful review receipt")
	}
	corrected := makeAttempt("f0123456-789b-4cde-8123-456789abcdef", "fresh-corrected-attempt", "pass")
	first := h.run("capture-observation", corrected)
	second := h.run("capture-observation", corrected)
	if first["receipt"] == nil || first["receipt"] != second["receipt"] {
		t.Fatal("fresh successful attempt was not capturable with idempotent replay")
	}
	if es := schema.ValidateWith(observation.Schema(), rejected); len(es) == 0 {
		t.Fatal("a later correction laundered the prior rejected attempt")
	}
	after, err := os.ReadFile(path)
	if err != nil || string(before) != string(after) {
		t.Fatalf("capturing correction changed rejected immutable source: %v", err)
	}
}
