package operations

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Synthetic contract fixtures only, never live host observations or authority.
func nativeV2ReviewSource(t *testing.T, h *farmHarness, record, kind string, contexts ...object) (object, object) {
	t.Helper()
	var source, payload object
	if len(contexts) == 0 {
		source, payload = nativeV1ReviewSource(t, h, record, kind)
	} else {
		source, payload = nativeV1ReviewSourceForContext(t, h, record, kind, contexts[0])
	}
	event := h.derived(model.S(source["source_ref"]))
	observed := h.derived(model.S(event["observation_ref"]))
	observed["producer_profile"] = "codex-native-v2/0.162.0-alpha.2"
	launch := model.M(model.M(observed["producer_result"])["launch"])
	launch["codex_review_profile"] = observed["producer_profile"]
	delete(launch, "fork_context")
	launch["fork_turns"] = "none"
	launch["parent_thread_id"] = "d0123456-789b-4cde-8123-456789abcdef"
	launch["task_name"] = "/root/authority_example"
	launch["native_activity"] = object{
		"type": "item_completed", "thread_id": launch["parent_thread_id"], "turn_id": launch["parent_turn_id"],
		"item":          object{"type": "SubAgentActivity", "id": launch["tool_use_id"], "kind": "started", "agent_thread_id": launch["agent_id"], "agent_path": launch["task_name"]},
		"started_at_ms": int64(1791601481147), "completed_at_ms": int64(1791601481147),
	}
	launch["native_activity_sha256"] = mustHashFixture(t, launch["native_activity"])
	launch["native_child"] = object{"cli_version": "0.162.0-alpha.2", "thread_id": launch["agent_id"], "parent_thread_id": launch["parent_thread_id"], "session_id": launch["parent_session_id"], "agent_path": launch["task_name"], "metadata_sha256": mustHashFixture(t, "synthetic child metadata")}
	observed["producer_result_sha256"] = mustHashFixture(t, observed["producer_result"])
	event["observation_ref"], event["observation_sha256"] = h.forge("observations", observed), mustHashFixture(t, observed)
	return object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)}, payload
}

func TestCodexNativeV2CaptureAndPublication(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	for _, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		source, payload := nativeV2ReviewSource(t, h, id, "spec_review")
		capture := h.run("capture-observation", source)
		reviewReceipt := model.S(capture["receipt"])
		if reviewReceipt == "" || capture["artifact_approval_changed"] != false {
			t.Fatalf("unexpected review capture: %v", capture)
		}
		if model.S(h.run("capture-observation", source)["receipt"]) != reviewReceipt {
			t.Fatal("review capture replay changed the receipt")
		}
		commands := []any{}
		for _, value := range model.A(h.doc("PLAN-EXAMPLE").Symbols.ByID[id].Value["verification"]) {
			definition := model.M(value)
			tests := []any{}
			for _, name := range model.Strings(definition["required_tests"]) {
				tests = append(tests, object{"name": name, "status": "pass"})
			}
			commands = append(commands, object{"definition_sha256": mustHashFixture(t, definition), "exit": int64(0), "tests": tests, "stdout_sha256": mustHashFixture(t, "synthetic stdout"), "stderr_sha256": mustHashFixture(t, "")})
		}
		delete(payload, "assessment")
		payload["commands"] = commands
		verificationReceipt := captureObservedPromptFixture(t, h.root, "PLAN-EXAMPLE", id, "verification", "verification_runner", "passed", "Synthetic verification fixture; not executed tests.", payload)
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": verificationReceipt, "review_receipt": reviewReceipt})
		if model.S(state(h.doc("PLAN-EXAMPLE"), id)["state"]) != "REVIEW" {
			t.Fatal("native-v2 task review was not published")
		}
	}
	qualitySource, _ := nativeV2ReviewSource(t, h, "CP-01", "quality_review")
	qualityReceipt := h.run("capture-observation", qualitySource)["receipt"]
	h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "receipt": qualityReceipt})
	for _, id := range []string{"T-001", "T-002"} {
		if model.S(state(h.doc("PLAN-EXAMPLE"), id)["state"]) != "ACCEPTED" {
			t.Fatal("native-v2 quality review was not published")
		}
	}
}

// Substantive completion fixtures retain real immutable contexts and exact selected facts.
func TestCodexNativeV2CompletionCapturePublicationAndScope(t *testing.T) {
	h, linked := completionHarness(t)
	material := filepath.Join(testutil.Root(t), "matrix.txt")
	if err := os.WriteFile(material, []byte("Task completion evidence matrix\n"), 0600); err != nil {
		t.Fatal(err)
	}
	receipts := []string{}
	for i, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		root := h.root
		if i == 1 {
			root = linked
		}
		verification := completionVerification(t, h, id, root)
		receipts = append(receipts, verification)
		cr := completionContext(t, h, id, "spec_review", []string{verification}, []string{material})
		context := h.derived(model.S(cr["context_ref"]))
		packet := model.M(context["completion"])
		rows := model.A(packet["verifications"])
		materials := model.A(packet["materials"])
		if len(rows) != 1 || model.S(model.M(rows[0])["receipt_ref"]) != verification || len(materials) != 1 || model.S(model.M(materials[0])["source_path"]) != material || model.S(model.M(materials[0])["content_base64"]) == "" {
			t.Fatalf("selected evidence omitted: %v", packet)
		}
		if model.S(model.M(model.A(model.M(rows[0])["workspace_after"])[0])["root"]) != root {
			t.Fatal("mapped verifier workspace omitted")
		}
		source, _ := nativeV2ReviewSource(t, h, id, "spec_review", cr)
		review := h.run("capture-observation", source)["receipt"]
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
		f, err := store.Open(h.root)
		if err != nil {
			t.Fatal(err)
		}
		plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
		err = evidence.TaskFresh(f, plan, spec, plan.Symbols.ByID[id].Value, model.S(context["input_sha256"]))
		f.Close()
		if err != nil {
			t.Fatalf("native task-review state update invalidated completed evidence: %v", err)
		}
		resume := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": id, "completion_context_ref": cr["context_ref"], "completion_context_sha256": cr["context_sha256"]})
		if resume["context_sha256"] != cr["context_sha256"] {
			t.Fatal("state-only update changed resumed completion context")
		}
	}
	quality := completionContext(t, h, "CP-01", "quality_review", receipts, []string{material})
	qcontext := h.derived(model.S(quality["context_ref"]))
	if len(model.A(model.M(qcontext["completion"])["verifications"])) != 2 {
		t.Fatal("quality omitted a selected task")
	}
	source, _ := nativeV2ReviewSource(t, h, "CP-01", "quality_review", quality)
	review := h.run("capture-observation", source)["receipt"]
	h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "receipt": review, "completion_sha256": qcontext["completion_sha256"]})
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	for _, id := range []string{"T-001", "T-002"} {
		if err = evidence.AcceptedFresh(f, plan, spec, id, model.S(qcontext["input_sha256"])); err != nil {
			t.Fatalf("accepted completion is stale after typed publication: %v", err)
		}
	}
}

func TestCodexNativeV2CompletionRejectsSelectedEvidenceDrift(t *testing.T) {
	for _, mode := range []string{"mapped-before-capture", "material-before-capture", "mapped-before-consume", "material-before-consume", "mapped-after-publish", "material-after-publish"} {
		t.Run(mode, func(t *testing.T) {
			h, linked := completionHarness(t)
			startNativeV1FixtureTask(t, h, "T-001")
			material := filepath.Join(testutil.Root(t), "matrix.txt")
			if err := os.WriteFile(material, []byte("exact selected evidence"), 0600); err != nil {
				t.Fatal(err)
			}
			verification := completionVerification(t, h, "T-001", linked)
			cr := completionContext(t, h, "T-001", "spec_review", []string{verification}, []string{material})
			context := h.derived(model.S(cr["context_ref"]))
			source, _ := nativeV2ReviewSource(t, h, "T-001", "spec_review", cr)
			mutate := func() {
				path := material
				if mode[:6] == "mapped" {
					path = filepath.Join(linked, "src", "stage1.go")
				}
				if err := os.WriteFile(path, []byte("changed after selected evidence"), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "mapped-before-capture" || mode == "material-before-capture" {
				mutate()
				if _, err := h.request("capture-observation", source); err == nil {
					t.Fatal("capture accepted drift in selected completed evidence")
				}
				return
			}
			review := h.run("capture-observation", source)["receipt"]
			if mode == "mapped-before-consume" || mode == "material-before-consume" {
				mutate()
				d := h.doc("PLAN-EXAMPLE")
				_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
				if err == nil {
					t.Fatal("task-review consumed stale selected evidence")
				}
				return
			}
			h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
			mutate()
			f, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
			if err = evidence.TaskFresh(f, plan, spec, plan.Symbols.ByID["T-001"].Value, model.S(context["input_sha256"])); err == nil {
				t.Fatal("task freshness accepted drift in completed evidence")
			}
		})
	}
}
