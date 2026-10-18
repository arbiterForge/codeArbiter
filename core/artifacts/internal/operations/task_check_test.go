package operations

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestTaskCheckPreservesNativeFailureExitCodes(t *testing.T) {
	for _, exit := range []int64{-2147483648, -15, 256, 3221225477, 4294967295} {
		t.Run(fmt.Sprint(exit), func(t *testing.T) {
			f := newAssistiveFixture(t)
			report := reportedCommand("fail", true)
			model.M(report["check"])["exit_code"] = exit
			f.mutate("task-check", report)
			got := model.M(reportedChecks(f)[0])
			if got["exit_code"] != exit || got["reported_outcome"] != "fail" {
				t.Fatalf("native failure code was changed or hidden: %v", got)
			}
			if _, err := model.Check(f.doc("PLAN-EXAMPLE").Data); err != nil {
				t.Fatalf("stored native failure code rejected: %v", err)
			}
			f.assertNoAuthorityFiles()
		})
	}
}

func TestTaskCheckNativeExitBoundsAndOutcomeSemantics(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, tc := range []struct {
		outcome  string
		exit     int64
		declared bool
	}{
		{"fail", -2147483649, true}, {"fail", 4294967296, true},
		{"pass", -15, true}, {"pass", 3221225477, true},
		{"pass", -15, false}, {"pass", 3221225477, false},
		{"unknown", -15, false}, {"skip", 3221225477, false},
	} {
		report := reportedCommand(tc.outcome, tc.declared)
		model.M(report["check"])["exit_code"] = tc.exit
		before := f.doc("PLAN-EXAMPLE").Hash()
		if _, err := f.request("task-check", f.mutation("PLAN-EXAMPLE", report)); err == nil {
			t.Errorf("accepted invalid %s exit=%d declared=%v", tc.outcome, tc.exit, tc.declared)
		}
		if f.doc("PLAN-EXAMPLE").Hash() != before {
			t.Fatal("rejected exit code changed persisted state")
		}
	}
	reportFor(f, "fail", true)
	for _, exit := range []int64{-2147483649, 4294967296} {
		d := f.doc("PLAN-EXAMPLE")
		stored := model.M(model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-001"])[0])
		stored["exit_code"] = exit
		if _, err := model.Check(d.Data); err == nil {
			t.Errorf("stored schema accepted out-of-range exit %d", exit)
		}
	}
}

// The fixture's plan declares this check, but the test does not actually run
// it. These are caller-reported results, never host-attested proof.
func reportedCommand(outcome string, declared bool) object {
	check := object{
		"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"),
		"cwd":  ".", "outcome": outcome,
		"summary": "Reported observed status: " + outcome,
		"source":  "current session output: test command reported by the caller",
		"origin":  "tool_result",
	}
	if declared {
		check["command_index"] = int64(0)
	}
	if outcome == "pass" {
		check["exit_code"] = int64(0)
	}
	if outcome == "fail" {
		check["exit_code"] = int64(1)
	}
	return object{"task": "T-001", "check": check}
}

func reportFor(f *assistiveFixture, outcome string, declared bool) object {
	f.t.Helper()
	return f.mutate("task-check", reportedCommand(outcome, declared))
}

func reportedChecks(f *assistiveFixture) []any {
	f.t.Helper()
	return model.A(f.call("task-context", object{
		"artifact_id": "PLAN-EXAMPLE", "task": "T-001",
		"model_sha256": f.doc("PLAN-EXAMPLE").Hash(),
	})["reported_checks"])
}

func TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority(t *testing.T) {
	f := newAssistiveFixture(t)
	before := f.doc("PLAN-EXAMPLE")
	for _, outcome := range []string{"pass", "fail", "skip", "unknown"} {
		reportFor(f, outcome, true)
		got := reportedChecks(f)
		packet := f.call("task-context", object{"artifact_id": "PLAN-EXAMPLE",
			"task": "T-001", "model_sha256": f.doc("PLAN-EXAMPLE").Hash()})
		if outcome == "fail" && !strings.Contains(model.S(packet["next_action"]), "reported failing") {
			t.Fatal("task packet hid most recent failed check")
		}
		if packet["checks_are_verified"] != false {
			t.Fatal("task packet promoted a reported outcome to proof")
		}
		latest := model.M(got[len(got)-1])
		if latest["reported_outcome"] != outcome || latest["evidence_assessed"] != false ||
			latest["provenance"] != "caller_reported" || latest["worktree_freshness"] != "unassessed" ||
			latest["declared_command"] != true || latest["named_tests_verified"] != false ||
			latest["definition_current"] != true {
			t.Fatalf("report %s was presented as verification or became stale without changes: %v", outcome, latest)
		}
	}
	after := f.doc("PLAN-EXAMPLE")
	if after.NormHash() != before.NormHash() || after.Data["schema_version"] != model.SchemaVersion {
		t.Fatal("ordinary check changed requirements or lost schema identity")
	}
	if state(after, "T-001")["state"] != "PENDING" {
		t.Fatal("reported command result promoted task implementation progress")
	}
	if len(model.A(state(after, "T-001")["evidence_refs"])) != 0 {
		t.Fatal("reported command result invented verified evidence")
	}
	if _, err := f.request("verification-status", object{"artifact_id": "PLAN-EXAMPLE"}); err == nil {
		t.Fatal("ordinary check note became acceptance evidence")
	}
	if _, err := f.request("task-check", object{
		"artifact_id": "PLAN-EXAMPLE", "task": "T-001",
		"check": object{"argv": model.List("go", "test"), "cwd": "."},
	}); err == nil {
		t.Fatal("malformed check bypassed closed request schema")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckLatestFailureOverridesPriorPassAndSkipsUnknown(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, outcome := range []string{"pass", "fail", "unknown", "skip", "pass"} {
		reportFor(f, outcome, false)
		items := reportedChecks(f)
		got := model.M(items[len(items)-1])
		if got["declared_command"] != false || got["named_tests_verified"] != false {
			t.Fatal("ad-hoc command was presented as independently verified named tests")
		}
		if got["reported_outcome"] != outcome {
			t.Fatalf("latest check did not override previous report: %v", items)
		}
	}
	reported := model.A(model.M(model.M(f.doc("PLAN-EXAMPLE").Data["execution"])["task_check_observations"])["T-001"])
	if len(reported) != 5 {
		t.Fatalf("latest outcome overwrote historical reports: %d", len(reported))
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckCASReplaySourceChangesAndPresentationEdits(t *testing.T) {
	f := newAssistiveFixture(t)
	request := f.mutation("PLAN-EXAMPLE", reportedCommand("pass", true))
	f.call("task-check", request)
	identity := f.doc("PLAN-EXAMPLE").Hash()
	f.call("task-check", request)
	if f.doc("PLAN-EXAMPLE").Hash() != identity {
		t.Fatal("replayed report added another observation")
	}
	request["operation_id"] = f.next()
	if _, err := f.request("task-check", request); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale mutation passed CAS: %v", err)
	}
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001",
		"fields": object{"steps": model.List("A more focused implementation step.")},
	}}})
	if model.M(reportedChecks(f)[0])["definition_current"] != true {
		t.Fatal("an implementation-method-only edit invalidated unchanged check definitions")
	}
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001",
		"fields": object{"verification": []any{object{
			"availability": "proposed", "cwd": ".", "argv": model.List("go", "test", "./...", "-run", "TestAnother"),
			"expected_exit": int64(0), "assertion": "Different named test.",
			"required_tests": model.List("TestAnother"),
		}}},
	}}})
	if note := model.M(reportedChecks(f)[0]); note["definition_current"] != false ||
		note["reported_outcome"] != "pass" {
		t.Fatalf("changed check was considered current or history was overwritten: %v", note)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands(t *testing.T) {
	f := newAssistiveFixture(t)
	before := f.doc("PLAN-EXAMPLE").Hash()
	rejects := []object{
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": ".", "outcome": "pass", "summary": "claim", "source": "notes", "origin": "agent_report", "command_index": int64(0)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": ".", "outcome": "skip", "exit_code": int64(0), "summary": "claim", "source": "notes", "origin": "tool_result", "command_index": int64(0)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestWrong"), "cwd": ".", "outcome": "pass", "exit_code": int64(0), "summary": "claim", "source": "notes", "origin": "tool_result", "command_index": int64(0)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": "../escape", "outcome": "pass", "exit_code": int64(0), "summary": "claim", "source": "notes", "origin": "tool_result", "command_index": int64(0)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": ".", "outcome": "pass", "exit_code": int64(2), "summary": "claim", "source": "notes", "origin": "tool_result", "command_index": int64(0)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": ".", "outcome": "fail", "exit_code": int64(1), "summary": "claim", "source": "notes", "origin": "tool_result", "command_index": int64(7)}},
		{"task": "T-001", "check": object{"argv": model.List("go", "test", "./...", "-run", "TestEnvironmentOverrides"), "cwd": ".", "outcome": "fail", "exit_code": int64(1), "summary": " ", "source": "notes", "origin": "tool_result", "command_index": int64(0)}},
	}
	for i, req := range rejects {
		if _, err := f.request("task-check", f.mutation("PLAN-EXAMPLE", req)); err == nil {
			t.Fatalf("invalid input %d accepted", i)
		}
		if f.doc("PLAN-EXAMPLE").Hash() != before {
			t.Fatal("failed check changed state")
		}
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability(t *testing.T) {
	f := newAssistiveFixture(t)
	reportFor(f, "pass", true)
	original := model.M(reportedChecks(f)[0])
	if original["definition_current"] != true {
		t.Fatal("initial task check was not applicable")
	}
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001",
		"fields": object{"paths": []any{object{"path": "src/replacement.go", "action": "modify"}}},
	}}})
	changed := model.M(reportedChecks(f)[0])
	if changed["definition_current"] != false || changed["reported_outcome"] != "pass" {
		t.Fatalf("task subject path change laundered old reported coverage: %v", changed)
	}
	reportFor(f, "unknown", true)
	after := reportedChecks(f)
	if model.M(after[len(after)-1])["definition_current"] != true ||
		model.M(after[len(after)-1])["reported_outcome"] != "unknown" {
		t.Fatal("later observation did not capture the new subject definition")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckNeverExecutesItsSourceAndEscapesHTML(t *testing.T) {
	f := newAssistiveFixture(t)
	report := reportedCommand("fail", false)
	check := model.M(report["check"])
	check["source"] = "<script>intrusion()</script>; $(touch should-not-exist)"
	check["output_excerpt"] = "Unicode 日本語; <img src=x onerror=alert(1)>"
	f.mutate("task-check", report)
	got := model.M(reportedChecks(f)[0])
	if got["reported_outcome"] != "fail" || got["source"] != check["source"] {
		t.Fatal("command-level failed result lost its source")
	}
	bytes, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"))
	if err != nil {
		t.Fatal(err)
	}
	html := string(bytes)
	if strings.Contains(html, "<script>intrusion()</script>") ||
		strings.Contains(html, "<img src=x onerror=alert(1)>") ||
		!strings.Contains(html, "Reported command checks") {
		t.Fatal("HTML did not safely render the reported check")
	}
	if _, err := os.Stat(filepath.Join(f.root, "should-not-exist")); !os.IsNotExist(err) {
		t.Fatal("inert observation source executed a command")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckBoundedRecentViewKeepsHistoryInJournal(t *testing.T) {
	f := newAssistiveFixture(t)
	for i := 0; i < 18; i++ {
		reportFor(f, "fail", false)
	}
	d := f.doc("PLAN-EXAMPLE")
	kept := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-001"])
	if len(kept) != 16 || model.M(kept[len(kept)-1])["history_trimmed"] != true {
		t.Fatalf("bounded reported history did not preserve retention marker: %v", len(kept))
	}
	packet := f.call("task-context", object{"artifact_id": d.ID(), "task": "T-001", "model_sha256": d.Hash()})
	if len(model.A(packet["reported_checks"])) != 3 || model.I(packet["check_reports_omitted"]) != 13 ||
		packet["check_history_bounded"] != true || packet["checks_are_verified"] != false {
		t.Fatalf("packet does not disclose its bounded report window: %v", packet)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree(t *testing.T) {
	f := newAssistiveFixture(t)
	reportFor(f, "fail", true)
	d := f.doc("PLAN-EXAMPLE")
	exact := f.call("read", object{"artifact_id": d.ID(), "mode": "exact", "symbol": "T-001"})
	checks := model.A(exact["reported_checks"])
	if len(checks) != 1 || model.M(checks[0])["reported_outcome"] != "fail" ||
		model.M(checks[0])["definition_current"] != nil {
		t.Fatalf("exact read claimed current source applicability without an external spec: %v", exact)
	}
	batch := f.call("read-batch", object{"artifact_id": d.ID(),
		"symbols": model.List("T-001"), "model_sha256": d.Hash()})
	got := model.M(model.A(batch["records"])[0])
	if len(model.A(got["reported_checks"])) != 1 {
		t.Fatal("batch read discarded a task check observation")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckOldSchemaCannotSilentlyContainNewObservations(t *testing.T) {
	f := newAssistiveFixture(t)
	reportFor(f, "unknown", false)
	old := f.doc("PLAN-EXAMPLE")
	if old.Data["schema_version"] != "0.3.2" {
		t.Fatal("unexpected candidate schema")
	}
	old.Data["schema_version"] = "0.3.1"
	if _, err := model.Check(old.Data); fault.Code(err) != "UNSUPPORTED_VERSION" {
		t.Fatalf("old schema silently accepted command observations: %v", err)
	}
}
