package operations

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func conflictsFor(f *assistiveFixture) object {
	f.t.Helper()
	d, spec := f.doc("PLAN-EXAMPLE"), f.doc("SPEC-EXAMPLE")
	fs, err := store.Open(f.root)
	if err != nil {
		f.t.Fatal(err)
	}
	defer fs.Close()
	return (&Engine{FS: fs}).checkConflicts(d, spec, "T-001", nil)
}

func TestCheckConflictsRespectDefinitionAndSourceScope(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*assistiveFixture)
		want   bool
	}{
		{"unchanged", func(f *assistiveFixture) {}, true},
		{"unrelated source", func(f *assistiveFixture) { scopedWrite(t, f.root, "src/stage2.go", "package unrelated\n") }, true},
		{"changed source", func(f *assistiveFixture) { scopedWrite(t, f.root, "src/stage1.go", "package changed\n") }, false},
		{"changed task definition", func(f *assistiveFixture) {
			f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{
				"paths": []any{object{"path": "src/replacement.go", "action": "create"}},
			}}}})
		}, false},
		{"changed criterion", func(f *assistiveFixture) {
			f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "AC-001", "fields": object{
				"statement": "Resolve a newly required input combination.",
			}}}}))
		}, false},
		{"unrelated specification prose", func(f *assistiveFixture) {
			f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{
				"summary": "Clarified overview with unchanged task requirements.",
			}}}}))
		}, true},
	} {
		for _, declared := range []bool{true, false} {
			name := tc.name
			if !declared {
				name += " unindexed"
			}
			t.Run(name, func(t *testing.T) {
				f := newAssistiveFixture(t)
				scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
				reportFor(f, "fail", declared)
				tc.change(f)
				result := conflictsFor(f)
				if result["has_conflicting_check_reports"] != tc.want {
					t.Fatalf("incorrect report applicability: %v", result)
				}
				if !tc.want && model.I(result["check_reports_ignored"]) != 1 {
					t.Fatalf("stale report not disclosed: %v", result)
				}
				f.assertNoAuthorityFiles()
			})
		}
	}
}

func TestCheckConflictsMatchEveryUnindexedCommandWithoutBindingIt(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	first := model.M(model.A(f.doc("PLAN-EXAMPLE").Symbols.ByID["T-001"].Value["verification"])[0])
	second, err := canonical.Clone(first)
	if err != nil {
		t.Fatal(err)
	}
	second["assertion"] = "A separate declared assertion for the same command."
	f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{
		"verification": []any{first, second},
	}}}})
	wrongDirectory := reportedCommand("fail", false)
	model.M(wrongDirectory["check"])["cwd"] = "src"
	f.mutate("task-check", wrongDirectory)
	if conflictsFor(f)["has_conflicting_check_reports"] != false {
		t.Fatal("different working directory was treated as an exact command match")
	}
	reportFor(f, "fail", false)
	conflicts := model.A(conflictsFor(f)["conflicting_check_reports"])
	if len(conflicts) != 2 {
		t.Fatalf("failure did not cover every matching declared command: %v", conflicts)
	}
	for index, value := range conflicts {
		conflict := model.M(value)
		if model.I(conflict["matched_command_index"]) != int64(index) || conflict["command_match"] != "exact_argv_cwd" || conflict["provenance"] != "caller_reported" {
			t.Fatalf("inexact command matching or invented provenance: %v", conflict)
		}
		if _, present := conflict["command_index"]; present {
			t.Fatal("unindexed report acquired a reported index")
		}
	}
	stored := model.A(model.M(model.M(f.doc("PLAN-EXAMPLE").Data["execution"])["task_check_observations"])["T-001"])
	if _, present := model.M(stored[len(stored)-1])["command_index"]; present {
		t.Fatal("stored report was rebound")
	}
	reportFor(f, "pass", true)
	if conflicts := model.A(conflictsFor(f)["conflicting_check_reports"]); len(conflicts) != 1 || model.I(model.M(conflicts[0])["matched_command_index"]) != 1 {
		t.Fatal("one declared success erased a different matching command's failure")
	}
	f.assertNoAuthorityFiles()
}

func TestCheckConflictsDoNotPromoteUnboundOrTrimmedHistory(t *testing.T) {
	f := newAssistiveFixture(t)
	reportFor(f, "fail", true)
	result := conflictsFor(f)
	if result["has_conflicting_check_reports"] != true || model.M(model.A(result["conflicting_check_reports"])[0])["worktree_freshness"] != "unassessed" {
		t.Fatalf("unbound failure was silently discarded: %v", result)
	}
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	for i := 0; i < 16; i++ {
		reportFor(f, "pass", false)
	}
	result = conflictsFor(f)
	if result["check_history_bounded"] != true || result["check_history_unassessed"] != true {
		t.Fatalf("trimmed history was claimed complete: %v", result)
	}
	reportFor(f, "pass", true)
	result = conflictsFor(f)
	if result["check_history_unassessed"] != false || result["has_conflicting_check_reports"] != false {
		t.Fatalf("current matching report did not resolve history uncertainty: %v", result)
	}
	f.assertNoAuthorityFiles()
}

func TestCheckReportBoundaryCannotCoverARepeatedLaterReport(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "fail", true)
	first := model.M(model.A(model.M(model.M(f.doc("PLAN-EXAMPLE").Data["execution"])["task_check_observations"])["T-001"])[0])
	boundary, _ := canonical.Hash(first)
	reportFor(f, "fail", true)
	d, spec := f.doc("PLAN-EXAMPLE"), f.doc("SPEC-EXAMPLE")
	entries := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-001"])
	// Equal wall-clock strings and content still represent different journaled
	// command observations; operation identity provides the distinction.
	model.M(entries[1])["recorded_at"] = first["recorded_at"]
	fs, err := store.Open(f.root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	result := (&Engine{FS: fs}).checkConflicts(d, spec, "T-001", map[string]bool{boundary: true})
	if result["has_conflicting_check_reports"] != true || model.I(result["check_reports_superseded"]) != 1 {
		t.Fatalf("earlier boundary covered a later identical report: %v", result)
	}
	if model.M(entries[1])["recording_operation_id"] == first["recording_operation_id"] {
		t.Fatal("distinct report mutations reused an operation identity")
	}
}
