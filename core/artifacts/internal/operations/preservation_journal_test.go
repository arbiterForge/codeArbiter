//go:build linux || darwin || windows

package operations

// NT-01 journal outcome preservation contracts. They hold a real repository
// lock, so they build only where a native storage backend exists.
// Transition rows: N01:06, N02:05, N02:06, N02:07, N02:08, N03:01, N03:02.

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// interruptedTaskStart prepares a real task-start journal that stops after
// publication, exactly as a process killed between journal and replacement
// would leave it. The after-bytes and durable result come from running the
// same request against a byte-identical twin store.
func interruptedTaskStart(t *testing.T) (f *assistiveFixture, request object, before, after []byte, result object) {
	t.Helper()
	f = newAssistiveFixture(t)
	twin := filepath.Join(t.TempDir(), "twin")
	if err := os.CopyFS(twin, os.DirFS(f.root)); err != nil {
		t.Fatal(err)
	}
	request = f.mutation("PLAN-EXAMPLE", object{"task": "T-001"})
	request["protocol"] = Protocol
	plan := filepath.Join(".codearbiter", "plans", "example.html")
	var err error
	if before, err = os.ReadFile(filepath.Join(f.root, plan)); err != nil {
		t.Fatal(err)
	}
	twinRequest, _ := canonical.Clone(request)
	out, err := Run(twin, "task-start", twinRequest)
	if err != nil {
		t.Fatal(err)
	}
	result = model.M(out)
	if after, err = os.ReadFile(filepath.Join(twin, plan)); err != nil {
		t.Fatal(err)
	}
	hash, err := canonical.Hash(object{"operation": "task-start", "request": request})
	if err != nil {
		t.Fatal(err)
	}
	durable := object{}
	for k, v := range result {
		if k != "transaction" {
			durable[k] = v
		}
	}
	fs, release := holdRepositoryLock(t, f.root, true)
	fs.Inject = func(step string) error {
		if step == "after-journal" {
			return errors.New("fixture-only process death after journal publication")
		}
		return nil
	}
	_, err = fs.Commit(model.S(request["operation_id"]), hash,
		[]store.Edit{{Path: filepath.ToSlash(plan), Before: before, After: after}}, durable)
	fs.Inject = nil
	release()
	if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
		t.Fatalf("fixture did not leave a prepared journal: %v", err)
	}
	return f, request, before, after, result
}

// The four journal outcome codes stay distinct at the public engine boundary,
// and the Pending() integrity barrier keeps guarding the canonical store.
func TestNT01JournalOutcomeCodesStayDistinct(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			f, request, before, after, result := interruptedTaskStart(t)
			planPath := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
			current := func() []byte {
				b, err := os.ReadFile(planPath)
				if err != nil {
					t.Fatal(err)
				}
				return b
			}
			// N01:06 / N02:07: a prepared journal guards reads, unrelated writes and
			// the exact retry of the same operation until recovery runs.
			if _, err := Run(f.root, "identity", object{"protocol": Protocol, "artifact_id": "PLAN-EXAMPLE"}); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("read crossed a pending multi-file transaction: %v", err)
			}
			unrelated := object{"protocol": Protocol, "artifact_id": "PLAN-EXAMPLE", "operation_id": "nt01-unrelated-0001",
				"expected": request["expected"], "task": "T-002"}
			if _, err := Run(f.root, "task-start", unrelated); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("write crossed a pending multi-file transaction: %v", err)
			}
			retry, _ := canonical.Clone(request)
			if _, err := Run(f.root, "task-start", retry); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("exact retry of a prepared operation was not routed to recovery: %v", err)
			}
			out, err := Run(f.root, "recover", object{"protocol": Protocol, "operation_id": request["operation_id"], "mode": mode})
			if err != nil {
				t.Fatal(err)
			}
			if mode == "complete" {
				if out.(store.Outcome).State != "committed" || string(current()) != string(after) {
					t.Fatalf("recovery did not complete the interrupted write: %v", out)
				}
				// N02:05 lost acknowledgement: the exact retry replays the recorded
				// result and never writes again.
				retry, _ = canonical.Clone(request)
				replayed, err := Run(f.root, "task-start", retry)
				if err != nil {
					t.Fatal(err)
				}
				got := model.M(replayed)
				if !got["transaction"].(store.Outcome).Replay || got["revision"] != result["revision"] ||
					got["model_sha256"] != result["model_sha256"] || string(current()) != string(after) {
					t.Fatalf("exact retry did not replay the original durable result: %v", got)
				}
				// N02:06: the same ID with different input is refused unchanged.
				changed, _ := canonical.Clone(request)
				changed["task"] = "T-002"
				if _, err := Run(f.root, "task-start", changed); fault.Code(err) != "OPERATION_ID_REUSE" {
					t.Fatalf("operation ID reuse was not refused: %v", err)
				}
				if string(current()) != string(after) {
					t.Fatal("refused reuse changed bytes")
				}
				return
			}
			if out.(store.Outcome).State != "rolled_back" || string(current()) != string(before) {
				t.Fatalf("rollback did not restore the exact before-image: %v", out)
			}
			// N02:08: the rolled-back operation never reports success on retry.
			retry, _ = canonical.Clone(request)
			if _, err := Run(f.root, "task-start", retry); fault.Code(err) != "OPERATION_ROLLED_BACK" {
				t.Fatalf("retry of a rolled-back operation was not distinct: %v", err)
			}
			if string(current()) != string(before) {
				t.Fatal("rolled-back retry wrote bytes")
			}
			// Ordinary work resumes under a new operation ID once the store is safe.
			fresh, _ := canonical.Clone(request)
			fresh["operation_id"] = "nt01-after-rollback-0001"
			if _, err := Run(f.root, "task-start", fresh); err != nil {
				t.Fatalf("ordinary work did not resume after rollback: %v", err)
			}
			if state(f.doc("PLAN-EXAMPLE"), "T-001")["state"] != "IN_PROGRESS" {
				t.Fatal("resumed start was not recorded")
			}
			f.assertNoAuthorityFiles()
		})
	}
}
