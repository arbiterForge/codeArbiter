//go:build linux || darwin || windows

package store

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// These controls use the actual Commit/Recover/metadata writers.
// Intermediate fixture effects are performed through anchored FS primitives,
// leaving a valid prepared journal and known before/after targets. No process
// death, provider, permission mutation or real user store is involved.
func n03RecoveryEffectFixture(t *testing.T, mode string) (*FS, string, string, []Edit) {
	t.Helper()
	f := fs(t)
	id := "recovery-own-effects-001"
	edits := []Edit{{Path: "replace.txt", Before: []byte("old-replace"), After: []byte("new-replace")}, {Path: "created.txt", After: []byte("new-created")}, {Path: "deleted.txt", Before: []byte("old-deleted")}}
	for _, edit := range edits {
		if edit.Before != nil {
			if err := os.WriteFile(filepath.Join(f.Root, edit.Path), edit.Before, 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	request := journalBoundaryPrepared(t, f, id, "after-journal", edits)
	// Publish a valid after target but retain a byte-identical unused stage;
	// this is a legal recovery input, not a forged journal or terminal state.
	if err := f.replace(".ca-artifact-"+id+"-0.new", "replace.txt", false); err != nil {
		t.Fatal(err)
	}
	if err := f.create(".ca-artifact-"+id+"-0.new", edits[0].After, 0644); err != nil {
		t.Fatal(err)
	}
	if mode == "rollback" {
		if err := f.replace(".ca-artifact-"+id+"-1.new", "created.txt", true); err != nil {
			t.Fatal(err)
		}
		if err := f.remove("deleted.txt"); err != nil {
			t.Fatal(err)
		}
	}
	return f, id, request, edits
}

func n03AssertRecoveredEffects(t *testing.T, f *FS, id, mode string, edits []Edit) {
	t.Helper()
	for i, edit := range edits {
		want := edit.After
		if mode == "rollback" {
			want = edit.Before
		}
		got, err := f.current(edit.Path)
		if err != nil || (got == nil) != (want == nil) || string(got) != string(want) {
			t.Fatalf("wrong %s target %s: %q %v", mode, edit.Path, got, err)
		}
		if edit.Before != nil {
			backup, err := f.Read(fmt.Sprintf("%s/history/%s-%d.before", meta, id, i), 100)
			if err != nil || string(backup) != string(edit.Before) {
				t.Fatalf("original before-image changed for %s: %v", edit.Path, err)
			}
		}
	}
}

func n03AssertTerminalCleanup(t *testing.T, f *FS, id, mode string, edits []Edit, out Outcome) {
	t.Helper()
	want := "committed"
	if mode == "rollback" {
		want = "rolled_back"
	}
	journal, err := f.journal(id)
	if err != nil || journal["state"] != want || model.M(journal["result"])["marker"] != "durable-original" || out.State != want || out.OperationID != id || out.Result["marker"] != "durable-original" {
		t.Fatalf("terminal acknowledgement/history lost: %v %v %v", journal, out, err)
	}
	for i := range edits {
		for _, extension := range []string{"new", "restore"} {
			path := fmt.Sprintf(".ca-artifact-%s-%d.%s", id, i, extension)
			if data, err := f.current(path); err != nil || data != nil {
				t.Fatalf("terminal recovery left stage %s: %v", path, err)
			}
		}
	}
	pending, err := f.Pending()
	if err != nil || len(pending) != 0 {
		t.Fatalf("terminal state remained pending: %v %v", pending, err)
	}
	n03AssertRecoveredEffects(t, f, id, mode, edits)
}

func TestN03RecoveryOwnAcknowledgementFailureAndSameModeRetry(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			f, id, request, edits := n03RecoveryEffectFixture(t, mode)
			journalBefore, err := f.Read(journalPath(id), 1<<20)
			if err != nil {
				t.Fatal(err)
			}
			blocker := filepath.Join(f.Root, filepath.FromSlash(journalPath(id)+".next"))
			if err := os.Mkdir(blocker, 0700); err != nil {
				t.Fatal(err)
			}
			before := journalBoundarySnapshot(t, f.Root)
			_, recoverErr := f.Recover(id, mode)
			after := journalBoundarySnapshot(t, f.Root)
			if fault.Code(recoverErr) != "COMMIT_OUTCOME_UNKNOWN" {
				t.Fatalf("Recover's own acknowledgement failure lost uncertainty: %v; changed=%v", recoverErr, journalBoundaryChanges(before, after))
			}
			n03AssertRecoveredEffects(t, f, id, mode, edits)
			journalAfter, err := f.Read(journalPath(id), 1<<20)
			if err != nil || string(journalBefore) != string(journalAfter) {
				t.Fatalf("failed acknowledgement rewrote prepared intent: %v", err)
			}
			if _, err := f.Lookup(id, request); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("prepared recovery became a successful replay: %v", err)
			}
			// The injected .next directory itself is intentionally invalid to
			// Pending's namespace reader. Remove only that owned obstruction
			// before observing the remaining prepared-journal barrier.
			if err := os.Remove(blocker); err != nil {
				t.Fatal(err)
			}
			pending, err := f.Pending()
			if err != nil || len(pending) != 1 || pending[0] != id {
				t.Fatalf("uncertain recovery lost pending barrier: %v %v", pending, err)
			}
			// All effects have already occurred. Only terminal acknowledgement
			// may now change; retry must not recreate targets/stages/backups.
			before = journalBoundarySnapshot(t, f.Root)
			out, err := f.Recover(id, mode)
			after = journalBoundarySnapshot(t, f.Root)
			if err != nil || out.Replay {
				t.Fatalf("same-mode retry failed: %v %v; changed=%v", out, err, journalBoundaryChanges(before, after))
			}
			changes := journalBoundaryChanges(before, after)
			if len(changes) != 1 {
				t.Fatalf("retry repeated effects instead of acknowledging: %v", changes)
			}
			if _, present := changes[journalPath(id)]; !present {
				t.Fatalf("retry changed an unrelated file: %v", changes)
			}
			n03AssertTerminalCleanup(t, f, id, mode, edits, out)
			before = journalBoundarySnapshot(t, f.Root)
			repeated, err := f.Recover(id, mode)
			after = journalBoundarySnapshot(t, f.Root)
			if err != nil || !repeated.Replay || repeated.State != out.State || !reflect.DeepEqual(before, after) {
				t.Fatalf("terminal same-mode replay repeated effects: %v %v", repeated, err)
			}
		})
	}
}

func TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		for _, changed := range []bool{false, true} {
			name := mode + "-verified"
			if changed {
				name = mode + "-changed"
			}
			t.Run(name, func(t *testing.T) {
				f, id, _, edits := n03RecoveryEffectFixture(t, mode)
				stage := ".ca-artifact-" + id + "-0.new"
				journalBefore, err := f.Read(journalPath(id), 1<<20)
				if err != nil {
					t.Fatal(err)
				}
				if changed {
					if err := os.WriteFile(filepath.Join(f.Root, stage), []byte("unrelated-stage"), 0600); err != nil {
						t.Fatal(err)
					}
				}
				before := journalBoundarySnapshot(t, f.Root)
				out, recoverErr := f.Recover(id, mode)
				after := journalBoundarySnapshot(t, f.Root)
				if changed {
					if fault.Code(recoverErr) != "RECOVERY_CONFLICT" {
						t.Fatalf("changed unused stage not refused: %v; changed=%v", recoverErr, journalBoundaryChanges(before, after))
					}
					// Existing owner checks unused stages after applying target
					// effects. Do not invent an all-target no-write guarantee.
					n03AssertRecoveredEffects(t, f, id, mode, edits)
					got, err := f.Read(stage, 100)
					if err != nil || string(got) != "unrelated-stage" {
						t.Fatalf("changed unused stage was removed: %v", err)
					}
					journalAfter, err := f.Read(journalPath(id), 1<<20)
					if err != nil || string(journalBefore) != string(journalAfter) {
						t.Fatalf("cleanup refusal acknowledged prepared intent: %v", err)
					}
					pending, err := f.Pending()
					if err != nil || len(pending) != 1 || pending[0] != id {
						t.Fatalf("cleanup refusal lost pending barrier: %v %v", pending, err)
					}
					// Reconcile only the owned fixture stage back to its known
					// original bytes; actual same-mode recovery then cleans it.
					if err := os.WriteFile(filepath.Join(f.Root, stage), edits[0].After, 0600); err != nil {
						t.Fatal(err)
					}
					out, recoverErr = f.Recover(id, mode)
				}
				if recoverErr != nil || out.Replay {
					t.Fatalf("verified cleanup recovery failed: %v %v", out, recoverErr)
				}
				n03AssertTerminalCleanup(t, f, id, mode, edits, out)
			})
		}
	}
}
