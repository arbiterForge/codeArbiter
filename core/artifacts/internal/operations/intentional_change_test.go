package operations

// NT-09 accepted intentional-change contracts. D-PROGRESS=B replaces the NT-01
// baseline's destructive STALE propagation with independent recorded progress
// and derived readiness. Preservation contracts remain in preservation_contract_test.go.
//
// Transition rows: N11:03 (STALE propagation), N09:04, N10:02.

import (
	"maps"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

// These observations are synthetic fixtures admitted by the real native receipt
// owner. They establish engine composition, never actual user/host approval.
func receiptedReconcileFixture(t *testing.T, fresh bool) (*farmHarness, *assistiveFixture) {
	t.Helper()
	h := newFarmHarness(t)
	h.createPair()
	f := &assistiveFixture{t: t, root: h.root}
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	report := reportedCommand("pass", true)
	report["task"] = "T-002"
	f.mutate("task-check", report)
	if fresh {
		source, payload := nativeV1ReviewSource(t, h, "T-001", "spec_review")
		review := h.run("capture-observation", source)["receipt"]
		commands := []any{}
		for _, value := range model.A(h.doc("PLAN-EXAMPLE").Symbols.ByID["T-001"].Value["verification"]) {
			definition := model.M(value)
			tests := []any{}
			for _, name := range model.Strings(definition["required_tests"]) {
				tests = append(tests, object{"name": name, "status": "pass"})
			}
			commands = append(commands, object{"definition_sha256": mustHashFixture(t, definition), "exit": int64(0), "tests": tests, "stdout_sha256": mustHashFixture(t, "synthetic stdout"), "stderr_sha256": mustHashFixture(t, "")})
		}
		delete(payload, "assessment")
		payload["commands"] = commands
		verification := captureObservedPromptFixture(t, h.root, "PLAN-EXAMPLE", "T-001", "verification", "verification_runner", "passed", "Synthetic reconciliation verifier fixture; no command execution is claimed.", payload)
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": review})
	}
	return h, f
}

func receiptedReconcileSource(t *testing.T, h *farmHarness, subject, target string, change func(object)) object {
	t.Helper()
	d := h.doc("PLAN-EXAMPLE")
	text := "Synthetic isolated reconciliation reply, not actual user approval."
	contextResult := h.run("evidence-context", object{"artifact_id": d.ID(), "activity": "reconciliation", "record_id": subject, "prompt_sha256": canonical.BytesHash([]byte(text))})
	context := h.derived(model.S(contextResult["context_ref"]))
	payload := object{"input_sha256": context["input_sha256"], "task_sha256": context["record_sha256"], "target_state": target}
	if change != nil {
		change(payload)
	}
	return observedSourceForContextFixture(t, h.root, model.M(context["subject"]), "reconciliation", "user_workflow", "reconciled", text, payload, contextResult)
}

func receiptedReconcileObservation(t *testing.T, h *farmHarness, subject, target string) string {
	t.Helper()
	return model.S(h.run("capture-observation", receiptedReconcileSource(t, h, subject, target, nil))["receipt"])
}

func TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence(t *testing.T) {
	for _, target := range []string{"PENDING", "BLOCKED", "REVIEW"} {
		t.Run(target, func(t *testing.T) {
			h, f := receiptedReconcileFixture(t, true)
			unselected := receiptedReconcileObservation(t, h, "T-002", target)
			selected := receiptedReconcileObservation(t, h, "T-001", target)
			before := f.doc("PLAN-EXAMPLE")
			wantedRefs := append(model.Strings(state(before, "T-001")["evidence_refs"]), selected)
			reason := "Explicit current reconciliation fixture."
			request := f.mutation(before.ID(), object{"task": "T-001", "state": target, "reason": reason, "receipt": selected})
			stale := f.mutation(before.ID(), object{"task": "T-001", "state": target, "reason": reason, "receipt": selected})
			f.call("task-reconcile", request)
			after := f.doc(before.ID())
			got := state(after, "T-001")
			if got["state"] != target || got["reason"] != reason || !equalValue(got["evidence_refs"], model.List(wantedRefs...)) {
				t.Fatalf("selected state/reason/receipt was not appended exactly: %v", got)
			}
			for _, ref := range model.Strings(got["evidence_refs"]) {
				if ref == unselected {
					t.Fatal("reconciliation attached an unselected subject receipt")
				}
			}
			if !equalValue(before.Data["normative"], after.Data["normative"]) ||
				!equalValue(state(before, "T-002"), state(after, "T-002")) ||
				!equalValue(state(before, "T-003"), state(after, "T-003")) ||
				!equalValue(model.M(before.Data["execution"])["task_check_observations"], model.M(after.Data["execution"])["task_check_observations"]) {
				t.Fatal("receipted reconciliation changed requirements, dependent progress, or check history")
			}
			if target != "REVIEW" && after.Data["schema_version"] != model.ProgressVersion {
				t.Fatal("changed progress semantics did not use the progress schema epoch")
			}
			settled := descriptorEffectSnapshot(t, f.root)
			f.call("task-reconcile", request)
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("exact request replay wrote another effect or repeated receipt append")
			}
			if _, err := f.request("task-reconcile", stale); fault.Code(err) != "REVISION_CONFLICT" {
				t.Fatalf("stale receipt writer did not refuse at CAS: %v", err)
			}
			if !maps.Equal(settled, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("stale CAS refusal changed retained files")
			}
		})
	}
}

func TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites(t *testing.T) {
	for _, mismatch := range []string{"subject", "input", "definition", "target", "capture-input-binding", "capture-task-binding", "review-without-evidence", "review-stale-evidence"} {
		t.Run(mismatch, func(t *testing.T) {
			h, f := receiptedReconcileFixture(t, mismatch == "review-stale-evidence")
			if mismatch == "review-stale-evidence" {
				writeFixture(t, f.root, "src/stage1.go", []byte("Changed after the synthetic verification and review.\n"))
			}
			subject, target := "T-001", "PENDING"
			if mismatch == "subject" {
				subject = "T-002"
			}
			if mismatch == "review-without-evidence" || mismatch == "review-stale-evidence" {
				target = "REVIEW"
			}
			if mismatch == "capture-input-binding" || mismatch == "capture-task-binding" {
				source := receiptedReconcileSource(t, h, subject, target, func(payload object) {
					field := "input_sha256"
					if mismatch == "capture-task-binding" {
						field = "task_sha256"
					}
					payload[field] = mustHashFixture(t, "different bound claim")
				})
				before := descriptorEffectSnapshot(t, f.root)
				if _, err := h.request("capture-observation", source); fault.Code(err) != "OBSERVATION_UNVERIFIED" {
					t.Fatalf("mismatched claim bypassed the real capture owner: %v", err)
				}
				if !maps.Equal(before, descriptorEffectSnapshot(t, f.root)) {
					t.Fatal("rejected capture published a receipt or changed retained files")
				}
				return
			}
			receiptTarget := target
			if mismatch == "target" {
				receiptTarget = "BLOCKED"
			}
			selected := receiptedReconcileObservation(t, h, subject, receiptTarget)
			if mismatch == "input" {
				writeFixture(t, f.root, "src/stage1.go", []byte("Changed after the authentic reconciliation observation.\n"))
			}
			if mismatch == "definition" {
				f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{"steps": model.List("A changed bounded implementation method.")}}}})
				h.approve("PLAN-EXAMPLE")
			}
			request := f.mutation("PLAN-EXAMPLE", object{"task": "T-001", "state": target, "reason": "Explicit reconciliation fixture.", "receipt": selected})
			before := descriptorEffectSnapshot(t, f.root)
			if _, err := f.request("task-reconcile", request); fault.Code(err) != "STALE_EVIDENCE" {
				t.Fatalf("%s did not refuse through the actual bound receipt owner: %v", mismatch, err)
			}
			if !maps.Equal(before, descriptorEffectSnapshot(t, f.root)) {
				t.Fatal("refused reconciliation changed retained files")
			}
		})
	}
}

// INTENTIONAL CHANGE: NT-09 under D-PROGRESS = B (progress.json later_decisions).
// Recorded progress is never overwritten by dependency invalidation;
// dependency readiness is derived.
func TestNT09TaskBlockPreservesDependentRecordedProgress(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	d := f.doc("PLAN-EXAMPLE")
	if d.Data["schema_version"] != model.ProgressVersion {
		t.Fatal("dependency semantics changed without the new schema epoch")
	}
	for _, id := range []string{"T-002", "T-003"} {
		s := state(d, id)
		if s["state"] != "REVIEW" || s["reason"] != "Implementation reported complete; verification and review are not assessed by this progress update." {
			t.Fatalf("dependency invalidation overwrote recorded progress: %s %v", id, s)
		}
	}
	// The explicit stop changes only its selected task. Dependent REVIEW labels
	// and their original reasons remain directly available.
	if state(d, "T-001")["state"] != "BLOCKED" {
		t.Fatal("blocked task lost its stop")
	}
	f.assertNoAuthorityFiles()
}

// Preserved completed work is not redispatched. Its blocked prerequisite is
// still visible independently of the retained REVIEW label.
func TestNT09PreservedProgressKeepsDependencyReadinessIndependent(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, id := range []string{"T-001", "T-002"} {
		f.mutate("task-start", object{"task": id})
		f.mutate("task-review", object{"task": id})
	}
	f.mutate("task-block", object{"task": "T-001", "reason": "Upstream input unavailable."})
	advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	second := model.M(model.A(advice["tasks"])[1])
	if second["state"] != "REVIEW" || second["diagnostic"] != "NOT_PENDING" || second["eligible"] != false || !equalValue(second["waiting_on"], model.List("T-001")) {
		t.Fatalf("recorded progress and dependency readiness were collapsed: %v", second)
	}
}

func TestNT09LegacyStaleIsUnresolvedAndRetainsRawReason(t *testing.T) {
	f := newAssistiveFixture(t)
	// A historical STALE label has no trustworthy prior progress in the live
	// state. Reconciliation may record what is known without inventing it.
	d := f.doc("PLAN-EXAMPLE")
	state(d, "T-001")["state"] = "STALE"
	state(d, "T-001")["reason"] = "Legacy dependency invalidation."
	d, err := render.Prepare(d.Data)
	if err != nil {
		t.Fatal(err)
	}
	b, err := render.Render(d)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"), b, 0600); err != nil {
		t.Fatal(err)
	}
	p := packetFor(f, "T-001")
	progress := model.M(p["progress"])
	if progress["recorded_state"] != "STALE" || progress["state"] != nil || progress["basis"] != "legacy_unresolved" || progress["recorded_reason"] != "Legacy dependency invalidation." {
		t.Fatalf("legacy progress was guessed or lost: %v", progress)
	}
	if p["state"] != "STALE" || p["checks_are_verified"] != false {
		t.Fatalf("legacy compatibility output or honest proof status lost: %v", p)
	}
	f.assertNoAuthorityFiles()
}

func TestNT09OrdinaryReviewAndDoneDoNotClaimIndependentProof(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("task-start", object{"task": "T-001"})
	f.mutate("task-review", object{"task": "T-001"})
	progress := model.M(packetFor(f, "T-001")["progress"])
	if progress["state"] != "REVIEW" || progress["basis"] != "caller_reported" || progress["evidence_assessed"] != false {
		t.Fatalf("ordinary review gained a proof claim: %v", progress)
	}
	f.mutate("task-start", object{"task": "T-002"})
	f.mutate("task-review", object{"task": "T-002"})
	f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Implementation complete; checks remain pending."})
	progress = model.M(packetFor(f, "T-001")["progress"])
	if progress["state"] != "DONE" || progress["basis"] != "caller_reported" || progress["evidence_assessed"] != false {
		t.Fatalf("DONE gained independent proof: %v", progress)
	}
}

func TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel(t *testing.T) {
	for _, label := range []string{"PENDING", "IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED", "BLOCKED", "STALE"} {
		t.Run(label, func(t *testing.T) {
			f := newAssistiveFixture(t)
			d := f.doc("PLAN-EXAMPLE")
			s := state(d, "T-002")
			s["state"], s["reason"] = label, "Retained original progress reason."
			if label == "DONE" {
				d.Data["schema_version"] = model.SchemaVersion
			}
			d, err := render.Prepare(d.Data)
			if err != nil {
				t.Fatal(err)
			}
			before := state(d, "T-002")
			b, err := render.Render(d)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"), b, 0600); err != nil {
				t.Fatal(err)
			}
			f.mutate("task-block", object{"task": "T-001", "reason": "Upstream stopped."})
			after := f.doc("PLAN-EXAMPLE")
			if !equalValue(before, state(after, "T-002")) {
				t.Fatal("dependency stop overwrote recorded history")
			}
			packet := packetFor(f, "T-002")
			if !equalValue(packet["waiting_on"], model.List("T-001")) || packet["checks_are_verified"] != false {
				t.Fatalf("dependency or proof axis collapsed: %v", packet)
			}
			f.mutate("task-reconcile", object{"task": "T-001", "state": "REVIEW", "reason": "Upstream available."})
			if !equalValue(before, state(f.doc("PLAN-EXAMPLE"), "T-002")) {
				t.Fatal("upstream recovery replaced dependent history")
			}
		})
	}
}
