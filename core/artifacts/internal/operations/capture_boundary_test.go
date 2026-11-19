//go:build linux

package operations

import (
	"maps"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func pendingVerificationSource(t *testing.T, h *harness, legacy bool) (object, object) {
	t.Helper()
	issued := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "verification", "record_id": "T-001"})
	bytes, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(model.S(issued["context_ref"]))))
	if err != nil {
		t.Fatal(err)
	}
	context, err := canonical.Object(bytes)
	if err != nil {
		t.Fatal(err)
	}
	if legacy {
		delete(context, "task_check_report_sha256")
		issued["context_ref"], issued["context_sha256"] = h.immutableJSON("evidence-contexts", context)
	}
	commands := []any{}
	for _, value := range model.A(context["commands"]) {
		command := model.M(value)
		definition := model.M(command["definition"])
		tests := []any{}
		for _, name := range model.Strings(definition["required_tests"]) {
			tests = append(tests, object{"name": name, "status": "pass"})
		}
		commands = append(commands, object{"definition_sha256": command["definition_sha256"], "exit": definition["expected_exit"], "tests": tests,
			"stdout_sha256": canonical.BytesHash([]byte("synthetic fixture output")), "stderr_sha256": canonical.BytesHash(nil)})
	}
	payload := object{"input_sha256": context["input_sha256"], "spec_sha256": context["spec_sha256"], "task_sha256": context["task_sha256"], "commands": commands}
	source := observedSourceForContextFixture(t, h.root, model.M(context["subject"]), "verification", "verification_runner", "passed",
		"Synthetic pending-capture fixture, not actual command evidence.", payload, issued)
	return source, context
}

func TestLegacyCaptureRefusalMatchesDiscoveryDescriptor(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
	h.approvePair()
	h.start("T-001")
	h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", true))
	observed, _ := pendingVerificationSource(t, h, false)
	raw, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(model.S(observed["source_ref"]))))
	if err != nil {
		t.Fatal(err)
	}
	legacy, err := canonical.Object(raw)
	if err != nil {
		t.Fatal(err)
	}
	legacy["format"] = "codearbiter.workflow-event/0.1.0"
	delete(legacy, "observation_ref")
	delete(legacy, "observation_sha256")
	legacySource := h.authoritySource(legacy)

	before := descriptorEffectSnapshot(t, h.root)
	for _, source := range []object{legacySource, observed} {
		if _, err := h.request("capture", source); fault.Code(err) != "OBSERVATION_REQUIRED" {
			t.Fatalf("deprecated capture did not refuse a bound event: %v", err)
		}
	}
	if after := descriptorEffectSnapshot(t, h.root); !maps.Equal(after, before) {
		t.Fatal("deprecated capture wrote repository state on refusal")
	}

	// Demonstrate that the observed source is valid and the current handler
	// really emits the evidence classes that discovery advertises for it.
	captured := h.run("capture-observation", observed)
	for _, field := range []string{"event", "receipt"} {
		ref := model.S(captured[field])
		if bytes, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(ref))); err != nil || len(bytes) == 0 {
			t.Fatalf("capture-observation did not retain %s: %v", field, err)
		}
	}
	caps := h.run("capabilities", object{})
	rows := model.A(model.M(caps["operation_contract"])["operations"])
	for _, item := range rows {
		row := model.M(item)
		if row["name"] == "capture" {
			if row["effect"] != "observation" || row["lock"] != "exclusive" || row["evidence"] != "none" ||
				row["journaled"] != false || len(model.A(row["writes"])) != 0 {
				t.Fatalf("deprecated capture descriptor disagrees with its refusal behavior: %v", row)
			}
			return
		}
	}
	t.Fatal("discovery lost the compatibility operation")
}

func TestCapturePreservesIssuedCheckBoundary(t *testing.T) {
	for _, legacy := range []bool{false, true} {
		name := "issued boundary"
		if legacy {
			name = "legacy pending context"
		}
		t.Run(name, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
			h.approvePair()
			h.start("T-001")
			h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", true))
			source, issued := pendingVerificationSource(t, h, legacy)
			h.mut("task-check", "PLAN-EXAMPLE", reportedCommand("fail", true))
			captured := h.run("capture-observation", source)
			plan := h.doc("PLAN-EXAMPLE")
			taskHash, _ := canonical.Hash(plan.Symbols.ByID["T-001"].Value)
			review := h.receipt(plan, "T-001", "spec_review", object{"input_sha256": issued["input_sha256"], "spec_sha256": issued["spec_sha256"],
				"task_sha256": taskHash, "assessment": "Synthetic specification review fixture."})
			h.mut("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": captured["receipt"], "review_receipt": review})
			h.start("T-002")
			h.review("T-002")
			h.accept("CP-01")
			h.start("T-003")
			h.review("T-003")
			h.accept("CP-02")
			result := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
			row := model.M(model.A(result["tasks"])[0])
			if result["all_accepted_and_current"] != false || row["current_evidence"] != true || row["has_conflicting_check_reports"] != true {
				t.Fatalf("capture replaced the issued boundary with later reports: %v", result)
			}
			wantSuperseded := int64(1)
			if legacy {
				wantSuperseded = 0
			}
			if model.I(row["check_reports_superseded"]) != wantSuperseded {
				t.Fatalf("issued report ordering was changed: %v", row)
			}
		})
	}
}

func TestCaptureCheckBoundaryStillRejectsChangedInputs(t *testing.T) {
	for _, changeSource := range []bool{true, false} {
		name := "normative"
		if changeSource {
			name = "source"
		}
		t.Run(name, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			scopedWrite(t, h.root, "src/stage1.go", "package stage1\n")
			h.approvePair()
			source, _ := pendingVerificationSource(t, h, false)
			if changeSource {
				scopedWrite(t, h.root, "src/stage1.go", "package changed\n")
			} else {
				h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{"steps": model.List("Changed implementation step.")}}}})
			}
			if _, err := h.request("capture-observation", source); fault.Code(err) != "STALE_EVIDENCE" {
				t.Fatalf("changed %s accepted by capture: %v", name, err)
			}
		})
	}
}
