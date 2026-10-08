//go:build linux || darwin || windows

package operations

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

type observationRequest struct {
	op    string
	input object
}

func concurrentReaderFixture(t *testing.T) (string, object, []observationRequest) {
	t.Helper()
	root := testutil.Root(t)
	n := model.M(testutil.Spec()["normative"])
	_, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "reader-fixture-0001", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n})
	if err != nil {
		t.Fatal(err)
	}
	identity, err := Run(root, "identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"})
	if err != nil {
		t.Fatal(err)
	}
	id := model.M(identity)
	return root, id, []observationRequest{
		{"identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
		{"snapshot", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
		{"outline", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
		{"read", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbol": "AC-001", "mode": "exact"}},
		{"read-batch", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbols": model.List("AC-001"), "model_sha256": id["model_sha256"]}},
	}
}

func holdRepositoryLock(t *testing.T, root string, exclusive bool) (*store.FS, func()) {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = f.Close() })
	unlock, err := f.Lock(exclusive, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	release := sync.OnceFunc(unlock)
	t.Cleanup(release)
	return f, release
}

func TestConcurrentObservationsShareRepositoryLock(t *testing.T) {
	root, _, requests := concurrentReaderFixture(t)
	expected := make([][]byte, len(requests))
	for i, request := range requests {
		out, err := Run(root, request.op, request.input)
		if err != nil {
			t.Fatalf("standalone %s: %v", request.op, err)
		}
		expected[i], err = canonical.Marshal(out)
		if err != nil {
			t.Fatal(err)
		}
	}
	// A separate handle deterministically represents a still-running observation.
	// Keep it held until all concurrent Run calls finish, with no timing guess.
	holdRepositoryLock(t, root, false)
	for i, request := range requests {
		t.Run(request.op, func(t *testing.T) {
			t.Parallel()
			out, err := Run(root, request.op, request.input)
			if err != nil {
				t.Fatalf("observation blocked by shared reader: %s: %v", fault.Code(err), err)
			}
			actual, err := canonical.Marshal(out)
			if err != nil || !bytes.Equal(actual, expected[i]) {
				t.Fatalf("concurrent output differs from standalone: %s, %v", actual, err)
			}
		})
	}
}

func readerWriterRequest(id object) object {
	return object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "operation_id": "reader-writer-0001", "expected": object{"revision": id["revision"], "model_sha256": id["model_sha256"]}, "name": "Concurrent fixture"}
}

func TestConcurrentReadersPreserveExclusiveOperations(t *testing.T) {
	for _, name := range []string{"writer", "default-read", "contextual-read", "capture", "capture-observation", "recover", "exclusive-holder"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			root, id, requests := concurrentReaderFixture(t)
			op, request := "rebrand", readerWriterRequest(id)
			switch name {
			case "default-read", "contextual-read":
				op = "read"
				request = object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbol": "AC-001"}
				if name == "contextual-read" {
					request["mode"] = "contextual"
				}
			case "capture", "capture-observation":
				op = name
				request = object{"protocol": Protocol, "source_ref": "fixture-only.json", "source_sha256": canonical.BytesHash(nil)}
			case "recover":
				op = name
				request = object{"protocol": Protocol, "operation_id": "reader-writer-0001", "mode": "complete"}
			case "exclusive-holder":
				op, request = requests[0].op, requests[0].input
			}
			holdRepositoryLock(t, root, name == "exclusive-holder")
			if _, err := Run(root, op, request); fault.Code(err) != "LOCK_TIMEOUT" {
				t.Fatalf("%s bypassed exclusive lock boundary: %v", name, err)
			}
		})
	}
}

func TestConcurrentReadersPreserveWriterRetry(t *testing.T) {
	root, id, _ := concurrentReaderFixture(t)
	request := readerWriterRequest(id)
	f, release := holdRepositoryLock(t, root, false)
	if _, err := Run(root, "rebrand", request); fault.Code(err) != "LOCK_TIMEOUT" {
		t.Fatalf("writer overlapped active observation: %v", err)
	}
	if pending, err := f.Pending(); err != nil || len(pending) != 0 {
		t.Fatalf("blocked writer left pending work: %v, %v", pending, err)
	}
	release()
	out, err := Run(root, "rebrand", request)
	if err != nil || model.M(out)["transaction"].(store.Outcome).State != "committed" {
		t.Fatalf("writer retry did not commit: %v, %v", out, err)
	}
	replay, err := Run(root, "rebrand", request)
	if err != nil || !model.M(replay)["transaction"].(store.Outcome).Replay {
		t.Fatalf("writer replay was not idempotent: %v, %v", replay, err)
	}
	request["operation_id"] = "reader-writer-0002"
	if _, err := Run(root, "rebrand", request); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale expected identity accepted: %v", err)
	}
}

func TestConcurrentReadersPreserveAdmission(t *testing.T) {
	for _, state := range []string{"pending", "duplicate"} {
		t.Run(state, func(t *testing.T) {
			root, _, requests := concurrentReaderFixture(t)
			f, release := holdRepositoryLock(t, root, true)
			want := "AMBIGUOUS_ARTIFACT"
			if state == "pending" {
				f.Inject = func(step string) error {
					if step == "after-journal" {
						return errors.New("fixture-only interrupted commit")
					}
					return nil
				}
				_, err := f.Commit("reader-pending-0001", canonical.BytesHash([]byte("pending fixture")), []store.Edit{{Path: "fixture.txt", After: []byte("pending")}})
				if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
					t.Fatal(err)
				}
				want = "RECOVERY_REQUIRED"
			} else {
				data, err := os.ReadFile(filepath.Join(root, ".codearbiter/specs/example.html"))
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(root, ".codearbiter/specs/duplicate.html"), data, 0600); err != nil {
					t.Fatal(err)
				}
			}
			release()
			for _, request := range requests {
				if _, err := Run(root, request.op, request.input); fault.Code(err) != want {
					t.Fatalf("%s admitted %s state: want %s, got %v", request.op, state, want, err)
				}
			}
			if state == "pending" {
				out, err := Run(root, "recover", object{"protocol": Protocol, "operation_id": "reader-pending-0001", "mode": "complete"})
				if err != nil || out.(store.Outcome).State != "committed" {
					t.Fatalf("pending transaction could not recover: %v, %v", out, err)
				}
				if _, err := Run(root, "identity", requests[0].input); err != nil {
					t.Fatalf("reader refused after recovery: %v", err)
				}
			}
		})
	}
}
