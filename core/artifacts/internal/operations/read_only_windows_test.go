//go:build windows

package operations

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestReadOnlyInitializedStoreObservations(t *testing.T) {
	var requests []observationRequest
	var expected [][]byte
	root := testutil.ReadOnlyFixture(t, func(root string) {
		n := model.M(testutil.Spec()["normative"])
		if _, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "readonly-fixture-spec", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n}); err != nil {
			t.Fatal(err)
		}
		id, err := Run(root, "identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"})
		if err != nil {
			t.Fatal(err)
		}
		pn := model.M(testutil.Plan(testutil.Seal(t, testutil.Spec()))["normative"])
		if _, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "readonly-fixture-plan", "artifact_id": "PLAN-EXAMPLE", "kind": "plan", "slug": "example", "spec_id": "SPEC-EXAMPLE", "title": pn["title"], "summary": pn["summary"], "normative": pn}); err != nil {
			t.Fatal(err)
		}
		plan, err := Run(root, "identity", object{"protocol": Protocol, "artifact_id": "PLAN-EXAMPLE"})
		if err != nil {
			t.Fatal(err)
		}
		p := model.M(plan)
		requests = []observationRequest{
			{"index", object{"protocol": Protocol, "kind": "spec"}},
			{"identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
			{"snapshot", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
			{"outline", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
			{"read", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbol": "AC-001", "mode": "exact"}},
			{"read-batch", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbols": model.List("AC-001"), "model_sha256": model.M(id)["model_sha256"]}},
			{"plan-verification", object{"protocol": Protocol, "artifact_id": "PLAN-EXAMPLE", "expected": object{"artifact_id": p["artifact_id"], "revision": p["revision"], "model_sha256": p["model_sha256"], "normative_sha256": p["normative_sha256"]}}},
		}
		for _, request := range requests {
			out, err := Run(root, request.op, request.input)
			if err != nil {
				t.Fatalf("writable baseline %s: %v", request.op, err)
			}
			b, err := canonical.Marshal(out)
			if err != nil {
				t.Fatal(err)
			}
			expected = append(expected, b)
		}
	})
	lock := filepath.Join(root, ".codearbiter", ".artifacts", "store.lock")
	if file, err := os.OpenFile(lock, os.O_RDWR, 0); err == nil {
		file.Close()
		t.Fatal("SETUP: fixture still permits lock writes")
	} else if !os.IsPermission(err) {
		t.Fatalf("SETUP: write denial has wrong cause: %v", err)
	}
	if file, err := os.OpenFile(filepath.Join(root, ".codearbiter", ".artifacts", "forbidden-create"), os.O_CREATE|os.O_WRONLY, 0600); err == nil {
		file.Close()
		t.Fatal("SETUP: fixture still permits creation")
	} else if !os.IsPermission(err) {
		t.Fatalf("SETUP: create denial has wrong cause: %v", err)
	}
	if file, err := os.Open(lock); err != nil {
		t.Fatalf("SETUP: fixture does not permit reading: %v", err)
	} else {
		file.Close()
	}
	t.Log("SETUP PROVEN: same identity can read, cannot open lock O_RDWR and cannot create a store file")
	before := testutil.Tree(t, root)
	for i, request := range requests {
		t.Run(request.op, func(t *testing.T) {
			out, err := Run(root, request.op, request.input)
			if err != nil {
				t.Fatalf("TARGET: initialized read-only %s refused: %v", request.op, err)
			}
			b, err := canonical.Marshal(out)
			if err != nil || !bytes.Equal(b, expected[i]) {
				t.Fatalf("canonical result changed for %s: %v", request.op, err)
			}
			testutil.AssertTree(t, root, before)
		})
	}
	testutil.AssertTree(t, root, before)
}

func TestIndexObservationUsesExclusiveEngineLock(t *testing.T) {
	var expected []byte
	root := testutil.ReadOnlyFixture(t, func(root string) {
		n := model.M(testutil.Spec()["normative"])
		if _, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "index-lock-fixture", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n}); err != nil {
			t.Fatal(err)
		}
		out, err := Run(root, "index", object{"protocol": Protocol, "kind": "spec"})
		if err != nil {
			t.Fatal(err)
		}
		expected, err = canonical.Marshal(out)
		if err != nil {
			t.Fatal(err)
		}
	})
	before := testutil.Tree(t, root)
	fs, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	locker, ok := any(fs).(existingStoreObservationLocker)
	if !ok {
		t.Fatal("existing-store observation capability is absent")
	}
	release, err := locker.ObservationLock(false, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	held := true
	defer func() {
		if held {
			release()
		}
	}()
	out, err := Run(root, "index", object{"protocol": Protocol, "kind": "spec"})
	if fault.Code(err) != "LOCK_TIMEOUT" || out != nil {
		t.Fatalf("engine index bypassed a held shared observation: result=%v err=%v", out, err)
	}
	release()
	held = false
	out, err = Run(root, "index", object{"protocol": Protocol, "kind": "spec"})
	if err != nil {
		t.Fatalf("engine index remained blocked after observation release: %v", err)
	}
	got, err := canonical.Marshal(out)
	if err != nil || !bytes.Equal(got, expected) {
		t.Fatalf("released index result changed: %v", err)
	}
	testutil.AssertTree(t, root, before)
}

// A fresh clone or worktree has the tracked artifacts but never the untracked
// store metadata. Reads must initialize it as a writer would, not refuse (#994).
func TestObservationsInitializeAFreshCheckoutStore(t *testing.T) {
	root := testutil.Root(t)
	n := model.M(testutil.Spec()["normative"])
	if _, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "fresh-checkout-spec", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n}); err != nil {
		t.Fatal(err)
	}
	requests := []observationRequest{
		{"identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}},
		{"index", object{"protocol": Protocol, "kind": "spec"}},
	}
	var expected [][]byte
	for _, request := range requests {
		out, err := Run(root, request.op, request.input)
		if err != nil {
			t.Fatalf("initialized baseline %s: %v", request.op, err)
		}
		b, err := canonical.Marshal(out)
		if err != nil {
			t.Fatal(err)
		}
		expected = append(expected, b)
	}
	for i, request := range requests {
		t.Run(request.op, func(t *testing.T) {
			if err := os.RemoveAll(filepath.Join(root, ".codearbiter", ".artifacts")); err != nil {
				t.Fatal(err)
			}
			out, err := Run(root, request.op, request.input)
			if err != nil {
				t.Fatalf("TARGET: %s refused on a checkout without store metadata: %v", request.op, err)
			}
			b, err := canonical.Marshal(out)
			if err != nil || !bytes.Equal(b, expected[i]) {
				t.Fatalf("result changed for %s: %v", request.op, err)
			}
			if _, err := os.Lstat(filepath.Join(root, ".codearbiter", ".artifacts", "store.lock")); err != nil {
				t.Fatalf("the read did not initialize the store lock: %v", err)
			}
		})
	}
}
