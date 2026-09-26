package operations

import (
	"sort"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// Native-v1 fixtures prove engine admission/publication only. They never claim
// that a host launched or observed these synthetic reviewers.
func nativeV1ReviewSource(t *testing.T, h *farmHarness, record, kind string) (object, object) {
	t.Helper()
	contextResult := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": kind, "record_id": record})
	context := h.derived(model.S(contextResult["context_ref"]))
	payload := object{"input_sha256": context["input_sha256"], "spec_sha256": context["spec_sha256"], "assessment": "Synthetic native-v1 engine fixture; not live review authority."}
	records := model.A(context["tasks"])
	if kind == "spec_review" {
		payload["task_sha256"] = context["task_sha256"]
		records = []any{context["task"]}
	} else {
		payload["base_input_sha256"], payload["task_hashes"] = context["base_input_sha256"], context["task_hashes"]
	}
	set := map[string]bool{}
	for _, task := range records {
		for _, criterion := range model.Strings(model.M(task)["criterion_refs"]) {
			set[criterion] = true
		}
	}
	coverage := make([]string, 0, len(set))
	for criterion := range set {
		coverage = append(coverage, criterion)
	}
	sort.Strings(coverage)
	runID := "a0123456-789b-4cde-8123-456789abcdef"
	launch := object{
		"parent_session_id": "synthetic-parent", "parent_turn_id": "b0123456-789b-4cde-8123-456789abcdef", "tool_use_id": "synthetic-tool",
		"post_confirmed": true, "agent_id": runID, "agent_type": "default", "codex_review_profile": "codex-native-v1/0.145.0",
		"child_turn_id": "c0123456-789b-4cde-8123-456789abcdef", "fork_context": false, "first_stop": true,
	}
	contract := object{"format": "codearbiter.review-decision/0.1.0", "decision": model.List("pass", "changes_requested"), "finding_severity": model.List("BLOCK", "WARN", "INFO"), "required_fields": model.List("format", "request_id", "target_sha256", "contract_sha256", "decision", "coverage", "findings", "assessment")}
	decision := object{"format": "codearbiter.review-decision/0.1.0", "request_id": mustHashFixture(t, "synthetic native-v1 request"), "target_sha256": context["input_sha256"], "contract_sha256": mustHashFixture(t, contract), "decision": "pass", "coverage": model.List(coverage...), "findings": []any{}, "assessment": payload["assessment"]}
	producer := object{"launch": launch, "decision": decision}
	observed := object{
		"format": "codearbiter.observation/0.2.0", "kind": kind, "subject": context["subject"],
		"context_ref": contextResult["context_ref"], "context_sha256": contextResult["context_sha256"],
		"payload_sha256": mustHashFixture(t, payload), "producer_profile": "codex-native-v1/0.145.0", "producer_run_id": runID,
		"producer_result": producer, "producer_result_sha256": mustHashFixture(t, producer),
	}
	event := object{
		"format": "codearbiter.workflow-event/0.2.0", "kind": kind, "authority_kind": "review_workflow", "subject": context["subject"],
		"actor": "synthetic test fixture", "origin": "isolated native-v1 fixture", "verdict": "passed", "payload": payload,
		"source_text":     "Synthetic decision used only by the temporary Go test root.",
		"observation_ref": h.forge("observations", observed), "observation_sha256": mustHashFixture(t, observed),
	}
	return object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)}, payload
}

func startNativeV1FixtureTask(t *testing.T, h *farmHarness, id string) {
	t.Helper()
	request := object{"artifact_id": "PLAN-EXAMPLE", "symbol": id, "budget": int64(65536)}
	for i := 0; i < 200; i++ {
		page := h.run("read", request)
		if page["context_complete"] == true {
			h.mutate("task-start", "PLAN-EXAMPLE", object{"task": id, "context_ticket": page["context_ticket"]})
			return
		}
		if model.S(page["next_cursor"]) == "" {
			t.Fatal("review fixture read lacked a continuation")
		}
		request["cursor"] = page["next_cursor"]
	}
	t.Fatal("review fixture context did not complete")
}

func TestCodexNativeV1CaptureAndPublication(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	for _, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		source, payload := nativeV1ReviewSource(t, h, id, "spec_review")
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
			t.Fatal("native-v1 task review was not published")
		}
	}
	qualitySource, _ := nativeV1ReviewSource(t, h, "CP-01", "quality_review")
	qualityReceipt := h.run("capture-observation", qualitySource)["receipt"]
	h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "receipt": qualityReceipt})
	for _, id := range []string{"T-001", "T-002"} {
		if model.S(state(h.doc("PLAN-EXAMPLE"), id)["state"]) != "ACCEPTED" {
			t.Fatal("native-v1 quality review was not published")
		}
	}
}
