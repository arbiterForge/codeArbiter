package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// These are synthetic producer fixtures against real native operations. They
// exercise the receipt/state contract, not a model-backed host or real tests.
func TestCompletionRerunReusesTaskReviewWithoutRelabellingItsEvidence(t *testing.T) {
	t.Parallel()
	h, linked := completionHarness(t)
	oldVerifications, oldReviews, reruns := []string{}, []string{}, []string{}
	for _, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		first := completionVerification(t, h, id, linked, "unchanged")
		context := completionContext(t, h, id, "spec_review", []string{first}, nil)
		source, _ := nativeV1ReviewSourceForContext(t, h, id, "spec_review", context)
		review := model.S(h.run("capture-observation", source)["receipt"])
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": first,
			"review_receipt": review, "completion_sha256": context["completion_sha256"]})
		oldVerifications, oldReviews = append(oldVerifications, first), append(oldReviews, review)
	}
	before := h.doc("PLAN-EXAMPLE").Hash()
	for i, id := range []string{"T-001", "T-002"} {
		// A second actual fixture producer invocation has a new executable
		// binding and receipt, but the same checked worktree and definitions.
		second := completionVerification(t, h, id, linked, "unchanged")
		if second == oldVerifications[i] {
			t.Fatal("fixture did not produce a distinct verification")
		}
		reruns = append(reruns, second)
	}
	// Matching the old reviewed source must not conceal a corrupt run-owned
	// closure. No task review is created as a workaround for the refusal.
	tampered := completionVerification(t, h, "T-001", linked, "tamper")
	if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "quality_review",
		"record_id": "CP-01", "completion_selection": object{"verification_receipts": model.List(tampered, reruns[1]), "supporting_files": empty()}}); err == nil {
		t.Fatal("review reuse ignored the new run's own recorded closure")
	}
	quality := completionContext(t, h, "CP-01", "quality_review", reruns, nil)
	if h.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("new run selection mutated the reviewed tasks")
	}
	context := h.derived(model.S(quality["context_ref"]))
	for i, value := range model.A(model.M(context["completion"])["verifications"]) {
		if model.M(value)["receipt_ref"] != reruns[i] {
			t.Fatal("batch context hid the selected new run")
		}
	}
	source, _ := nativeV1ReviewSourceForContext(t, h, "CP-01", "quality_review", quality)
	review := h.run("capture-observation", source)["receipt"]
	h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "receipt": review,
		"completion_sha256": context["completion_sha256"]})
	fs, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	for i, id := range []string{"T-001", "T-002"} {
		selected, err := evidence.LatestTaskCompletion(fs, plan, id)
		if err != nil || selected == nil || selected.Path != oldReviews[i] {
			t.Fatalf("batch rerun replaced the task's actual review: %v, %v", selected, err)
		}
		previous, err := evidence.ReviewContext(fs, selected)
		if err != nil {
			t.Fatal(err)
		}
		original := model.M(model.A(model.M(previous["completion"])["verifications"])[0])
		if original["receipt_ref"] != oldVerifications[i] {
			t.Fatal("historical review was relabelled as seeing the new run")
		}
		if err := evidence.AcceptedFresh(fs, plan, spec, id, model.S(context["input_sha256"])); err != nil {
			t.Fatalf("separate current task and batch assessments could not support acceptance: %v", err)
		}
	}
}

func TestCompletionRerunCannotReuseReviewAfterItsSubjectChanges(t *testing.T) {
	t.Parallel()
	h, linked := completionHarness(t)
	for _, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		verification := completionVerification(t, h, id, linked, "unchanged")
		context := completionContext(t, h, id, "spec_review", []string{verification}, nil)
		source, _ := nativeV1ReviewSourceForContext(t, h, id, "spec_review", context)
		review := h.run("capture-observation", source)["receipt"]
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": verification,
			"review_receipt": review, "completion_sha256": context["completion_sha256"]})
	}
	writeFixture(t, linked, "src/stage1.go", []byte("package changed_after_review\n"))
	reruns := []string{}
	for _, id := range []string{"T-001", "T-002"} {
		reruns = append(reruns, completionVerification(t, h, id, linked, "unchanged"))
	}
	before := h.doc("PLAN-EXAMPLE").Hash()
	if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "quality_review",
		"record_id": "CP-01", "completion_selection": object{"verification_receipts": model.List(reruns...), "supporting_files": empty()}}); err == nil {
		t.Fatal("passing reruns laundered a review of different source bytes")
	}
	if h.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("failed reuse changed task history")
	}
}
