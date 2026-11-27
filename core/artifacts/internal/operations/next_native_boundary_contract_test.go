package operations

// Ordinary native admission and advisory-report boundary assertions.
import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func TestN01AdmissionHasNoRepositoryEffects(t *testing.T) {
	for _, tc := range []struct {
		name, op string
		request  object
		wantCode string
	}{
		{"capabilities", "capabilities", object{"protocol": Protocol}, ""},
		{"schema", "schema", object{"protocol": Protocol, "name": "operation", "operation": "read"}, ""},
		{"unknown-operation", "not-an-operation", object{"protocol": Protocol}, "UNKNOWN_OPERATION"},
		{"unknown-field", "capabilities", object{"protocol": Protocol, "unexpected": true}, "INVALID_MODEL"},
		{"wrong-protocol", "capabilities", object{"protocol": "wrong"}, "INVALID_MODEL"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			parent := t.TempDir()
			root := filepath.Join(parent, "absent-repository")
			result, err := Run(root, tc.op, tc.request)
			if tc.wantCode == "" {
				if err != nil {
					t.Fatalf("admission: result=%v error=%v", result, err)
				}
			} else if err == nil || fault.Code(err) != tc.wantCode {
				t.Fatalf("admission: result=%v error=%v", result, err)
			}
			entries, readErr := os.ReadDir(parent)
			if readErr != nil || len(entries) != 0 {
				t.Fatalf("admission opened or created repository state: %v %v", entries, readErr)
			}
			if tc.wantCode == "" {
				// A NUL root cannot be opened by any supported filesystem backend.
				if _, err := Run("\x00", tc.op, tc.request); err != nil {
					t.Fatalf("repository-free operation consulted invalid root: %v", err)
				}
			}
		})
	}
}

func TestN13CallerReportBindsOperationTimeAndSubjects(t *testing.T) {
	for _, outcome := range []string{"pass", "fail", "skip", "unknown"} {
		t.Run(outcome, func(t *testing.T) {
			f := newAssistiveFixture(t)
			scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
			before := f.doc("PLAN-EXAMPLE")
			definition, err := model.TaskCheckDefinition(before.Symbols.ByID["T-001"].Value)
			if err != nil {
				t.Fatal(err)
			}
			criterion, err := model.TaskCriterionSubject(f.doc("SPEC-EXAMPLE"), before.Symbols.ByID["T-001"].Value)
			if err != nil {
				t.Fatal(err)
			}
			fs, err := store.Open(f.root)
			if err != nil {
				t.Fatal(err)
			}
			scoped, reason := scopedInputDigest(fs, before.Symbols.ByID["T-001"].Value)
			fs.Close()
			if scoped == "" || reason != "" {
				t.Fatalf("fixture has no bounded subject: %q %q", scoped, reason)
			}
			request := f.mutation("PLAN-EXAMPLE", reportedCommand(outcome, true))
			earliest := time.Now().UTC().Truncate(time.Second)
			f.call("task-check", request)
			latest := time.Now().UTC()
			after := f.doc("PLAN-EXAMPLE")
			rows := model.A(model.M(model.M(after.Data["execution"])["task_check_observations"])["T-001"])
			if len(rows) != 1 {
				t.Fatalf("report was not appended exactly once: %d", len(rows))
			}
			row := model.M(rows[0])
			recorded, err := time.Parse(time.RFC3339, model.S(row["recorded_at"]))
			if err != nil || recorded.Before(earliest) || recorded.After(latest) {
				t.Fatalf("invalid operation time: %v %v", recorded, err)
			}
			if row["recording_operation_id"] != request["operation_id"] || row["task_subject_sha256"] != definition || row["criterion_subject_sha256"] != criterion || row["scoped_inputs_sha256"] != scoped || row["provenance"] != "caller_reported" || row["outcome"] != outcome {
				t.Fatalf("report subject/operation was not retained: %v", row)
			}
			if before.NormHash() != after.NormHash() || state(after, "T-001")["state"] != "PENDING" || len(model.A(state(after, "T-001")["evidence_refs"])) != 0 {
				t.Fatal("caller report changed requirements or authority")
			}
			f.assertNoAuthorityFiles()
		})
	}
}

func TestN13TrimRetainsActualJournalBeforeImage(t *testing.T) {
	f := newAssistiveFixture(t)
	for i := 0; i < 16; i++ {
		reportFor(f, "fail", false)
	}
	fs, err := store.Open(f.root)
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := repository.Scan(fs)
	if err != nil {
		fs.Close()
		t.Fatal(err)
	}
	entry, err := catalog.Resolve("PLAN-EXAMPLE")
	fs.Close()
	if err != nil {
		t.Fatal(err)
	}
	before := append([]byte(nil), entry.Bytes...)
	previous := model.A(model.M(model.M(entry.Doc.Data["execution"])["task_check_observations"])["T-001"])
	firstID := model.M(previous[0])["recording_operation_id"]
	request := f.mutation("PLAN-EXAMPLE", reportedCommand("fail", false))
	f.call("task-check", request)
	journalBytes, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", ".artifacts", "transactions", model.S(request["operation_id"])+".json"))
	if err != nil {
		t.Fatal(err)
	}
	var journal object
	if err := json.Unmarshal(journalBytes, &journal); err != nil {
		t.Fatal(err)
	}
	if journal["operation_id"] != request["operation_id"] || journal["state"] != "committed" {
		t.Fatalf("not the selected committed journal: %v", journal)
	}
	found := false
	for _, value := range model.A(journal["entries"]) {
		row := model.M(value)
		if row["path"] != entry.Path {
			continue
		}
		expected := ".codearbiter/.artifacts/history/" + model.S(request["operation_id"]) + "-0.before"
		if row["backup"] != expected || row["before_sha256"] != canonical.BytesHash(before) {
			t.Fatalf("journal does not bind actual old document: %v", row)
		}
		backup, err := os.ReadFile(filepath.Join(f.root, filepath.FromSlash(expected)))
		if err != nil || !bytes.Equal(backup, before) {
			t.Fatalf("selected before-image lost old reports: %v", err)
		}
		found = true
	}
	if !found {
		t.Fatal("selected journal has no plan before-image")
	}
	after := f.doc("PLAN-EXAMPLE")
	kept := model.A(model.M(model.M(after.Data["execution"])["task_check_observations"])["T-001"])
	if len(kept) != 16 || model.M(kept[0])["recording_operation_id"] == firstID || model.M(kept[15])["recording_operation_id"] != request["operation_id"] || model.M(kept[15])["history_trimmed"] != true {
		t.Fatal("current view did not trim exactly the oldest report")
	}
	f.assertNoAuthorityFiles()
}

func TestN13UnavailableScopesRemainReportableWithoutReadMutation(t *testing.T) {
	for _, mode := range []string{"missing", "oversized", "unsafe"} {
		t.Run(mode, func(t *testing.T) {
			f := newAssistiveFixture(t)
			if mode == "oversized" {
				scopedWrite(t, f.root, "src/stage1.go", string(bytes.Repeat([]byte{'x'}, maxScopedFileBytes+1)))
			}
			if mode == "unsafe" {
				scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
				// Primary task paths accept portable .git lexically; advisory scope
				// assessment deliberately refuses repository internals. Shared inputs
				// reject .git earlier and would be the wrong fixture for this edge.
				f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{"paths": []any{object{"path": ".git", "action": "modify"}}}}}})
			}
			reportFor(f, "pass", true)
			before := f.doc("PLAN-EXAMPLE")
			packet := packetFor(f, "T-001")
			note := model.M(model.A(packet["reported_checks"])[0])
			if note["worktree_freshness"] != "unassessed" || note["scope_complete"] != false || note["evidence_assessed"] != false || packet["checks_are_verified"] != false || note["reported_outcome"] != "pass" {
				t.Fatalf("unavailable scope blocked or promoted ordinary report: %v", packet)
			}
			if model.S(note["scope_reason"]) == "" || f.doc("PLAN-EXAMPLE").Hash() != before.Hash() {
				t.Fatal("assessment omitted uncertainty or rewrote stored report")
			}
			if state(before, "T-001")["state"] != "PENDING" {
				t.Fatal("assessment changed implementation state")
			}
			f.assertNoAuthorityFiles()
		})
	}
}
