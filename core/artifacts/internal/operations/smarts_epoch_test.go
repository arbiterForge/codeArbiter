package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
)

// These synthetic host observations test native composition, not actual user
// approval or host qualification. Unlike sprint_authority_test this runs on
// every supported native platform.
func approveEpochFixture(t *testing.T, f *assistiveFixture) string {
	t.Helper()
	result := f.mutate("sprint-approve", prepareEpochApprovalFixture(t, f))
	return model.S(result["grant_receipt"])
}

func prepareEpochApprovalFixture(t *testing.T, f *assistiveFixture) object {
	t.Helper()
	h := &farmHarness{t: t, root: f.root}
	prompt := "approve-sprint SPEC-EXAMPLE PLAN-EXAMPLE delegate-methods fixture-token-1234"
	ctx := h.run("sprint-approval-context", object{"artifact_id": "PLAN-EXAMPLE", "spec_id": "SPEC-EXAMPLE", "delegate_methods": true, "prompt_sha256": canonical.BytesHash([]byte(prompt))})
	sources := []object{}
	for _, key := range []string{"spec_context", "plan_context"} {
		ref := model.M(ctx[key])
		context := h.derived(model.S(ref["context_ref"]))
		payload := object{"sprint_pair": ctx["pair"]}
		producer := object{"host": "fixture", "session_id": "epoch-test", "prompt_sha256": canonical.BytesHash([]byte(prompt))}
		observed := object{"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": context["subject"], "context_ref": ref["context_ref"], "context_sha256": ref["context_sha256"], "payload_sha256": mustHashFixture(t, payload), "producer_profile": "host-user-pair/0.1.0", "producer_run_id": "fixture:epoch-test", "producer_result": producer, "producer_result_sha256": mustHashFixture(t, producer)}
		event := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "approval", "authority_kind": "user_workflow", "subject": context["subject"], "actor": "synthetic epoch fixture", "origin": "synthetic one turn", "verdict": "approved", "payload": payload, "source_text": prompt, "observation_ref": h.forge("observations", observed), "observation_sha256": mustHashFixture(t, observed)}
		sources = append(sources, object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)})
	}
	spec := f.doc("SPEC-EXAMPLE")
	return object{"spec_id": spec.ID(), "spec_expected": object{"revision": spec.Revision(), "model_sha256": spec.Hash()}, "spec_source": sources[0], "plan_source": sources[1]}
}

func TestSMARTSComposesWithActualPlanEpoch(t *testing.T) {
	for _, epoch := range []string{model.SchemaVersion, model.ProgressVersion} {
		t.Run(epoch, func(t *testing.T) {
			f := newAssistiveFixture(t)
			if epoch == model.ProgressVersion {
				f.mutate("task-block", object{"task": "T-001", "reason": "Synthetic upstream stop."})
				f.mutate("task-reconcile", object{"task": "T-001", "state": "PENDING", "reason": "Synthetic condition resolved."})
			}
			before := f.doc("PLAN-EXAMPLE")
			if before.Data["schema_version"] != epoch || len(model.A(before.Norm()["retired_symbols"])) != 0 {
				t.Fatal("fixture did not isolate progress-only schema epoch")
			}
			grant := approveEpochFixture(t, f)
			lenses := object{}
			for _, name := range []string{"Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable"} {
				lenses[name] = object{"verdict": "Adequate", "reason": "Preserves the bounded existing contract."}
			}
			decision := object{"task_id": "T-001", "options": []any{object{"label": "Explicit method", "steps": model.List("Retain the negative oracle.", "Use a bounded explicit implementation."), "lenses": lenses}}, "selected": int64(0), "strength": "moderate", "rationale": "Existing scope and proof obligations remain unchanged."}
			req := f.mutation("PLAN-EXAMPLE", object{"grant_receipt": grant, "decision": decision})
			result := f.call("smarts-apply", req)
			after := f.doc("PLAN-EXAMPLE")
			if after.Data["schema_version"] != epoch || result["acceptance_granted"] != false {
				t.Fatal("method revision downgraded schema or granted acceptance")
			}
			if f.call("validate", object{"artifact_id": after.ID(), "gate": "approved"})["valid"] != true {
				t.Fatal("produced SMARTS approval failed its own consumer")
			}
			if f.call("smarts-apply", req)["transaction"] == nil || f.doc(after.ID()).Hash() != after.Hash() {
				t.Fatal("exact replay changed the plan")
			}
			h := &farmHarness{t: t, root: f.root}
			receipt := h.derived(model.S(result["receipt"]))
			event := h.derived(model.S(receipt["authority_source_ref"]))
			record := model.M(model.M(event["payload"])["smarts"])
			if record["before_schema_version"] != epoch || record["after_schema_version"] != epoch || record["after_normative_sha256"] != after.NormHash() {
				t.Fatal("producer did not retain exact schema and normative identities")
			}
			if observation.ValidateSMARTSRecordFor(observation.SMARTSProfileV2, record) == nil {
				t.Fatal("new epoch fields were accepted under the old closed profile")
			}
			for name, change := range map[string]func(object){
				"missing epoch":   func(r object) { delete(r, "after_schema_version") },
				"work-only epoch": func(r object) { r["after_schema_version"] = model.WorkCoordinationVersion },
				"before digest":   func(r object) { r["before_normative_sha256"] = mustHashFixture(t, "wrong before") },
				"after digest":    func(r object) { r["after_normative_sha256"] = mustHashFixture(t, "wrong after") },
				"downgrade": func(r object) {
					r["before_schema_version"], r["after_schema_version"] = model.ProgressVersion, model.SchemaVersion
					for _, phase := range []string{"before", "after"} {
						r[phase+"_normative_sha256"] = mustHashFixture(t, object{"format_version": model.FormatVersion, "kind": "plan", "schema_version": r[phase+"_schema_version"], "artifact_id": after.ID(), "normative": r[phase+"_normative"]})
					}
				},
			} {
				t.Run(name, func(t *testing.T) {
					copy, err := canonical.Clone(record)
					if err != nil {
						t.Fatal(err)
					}
					change(copy)
					if observation.ValidateSMARTSRecordFor(observation.SMARTSProfileV3, copy) == nil {
						t.Fatal("invalid epoch binding admitted")
					}
				})
			}
		})
	}
}
