package authority

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

func observedEvent(kind string) map[string]any {
	h := canonical.BytesHash([]byte("observation"))
	authorityKind := "review_workflow"
	if kind == "verification" {
		authorityKind = "verification_runner"
	}
	return map[string]any{
		"format": "codearbiter.workflow-event/0.2.0", "kind": kind, "authority_kind": authorityKind,
		"subject": map[string]any{"artifact_id": "PLAN-EXAMPLE", "normative_sha256": canonical.BytesHash([]byte("plan")), "record_id": "T-001"},
		"actor":   "qualified producer", "origin": "attempt/run-00000001", "verdict": "passed",
		"payload": map[string]any{}, "source_text": "Observed by the qualified producer.",
		"observation_ref": ".codearbiter/.artifacts/observations/" + h + ".json", "observation_sha256": h,
	}
}

func TestObservedEventSchemaRequiresClosedObservationLink(t *testing.T) {
	legacy := observedEvent("verification")
	legacy["format"] = "codearbiter.workflow-event/0.1.0"
	delete(legacy, "observation_ref")
	delete(legacy, "observation_sha256")
	if es := schema.ValidateWith(EventSchema(), legacy); len(es) != 0 {
		t.Fatalf("historical event is no longer readable: %v", es)
	}
	for _, kind := range []string{"verification", "spec_review", "quality_review"} {
		if es := schema.ValidateWith(EventSchema(), observedEvent(kind)); len(es) != 0 {
			t.Fatalf("%s observed event rejected: %v", kind, es)
		}
	}
	for _, mutate := range []func(map[string]any){
		func(v map[string]any) { delete(v, "observation_ref") },
		func(v map[string]any) { v["unexpected"] = true },
		func(v map[string]any) {
			v["kind"] = "unknown"
		},
	} {
		event := observedEvent("verification")
		mutate(event)
		if es := schema.ValidateWith(EventSchema(), event); len(es) == 0 {
			t.Fatal("invalid observed event accepted")
		}
	}
}
