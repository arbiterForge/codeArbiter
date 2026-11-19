//go:build linux || darwin || windows

package operations

import (
	"bytes"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Pure structurally checked model fixture: retained-reference strings are
// opaque test data, not receipts or evidence of approval. No store, provider,
// capture, declared command or authority operation is opened or executed.
func n19ActiveWriterModel(t *testing.T, active string) *model.Document {
	t.Helper()
	spec := testutil.Seal(t, testutil.Spec())
	data := testutil.Plan(spec)
	tasks := model.A(model.M(data["normative"])["tasks"])
	if len(tasks) != 3 {
		t.Fatal("fixture must keep exactly the existing three tasks")
	}
	// Isolate checkpoint propagation: T-002 is NOT a direct dependent of
	// selected T-001. T-003 still depends on T-002 in the later checkpoint.
	model.M(tasks[1])["depends_on"] = []any{}
	if model.S(model.M(tasks[0])["checkpoint"]) != "CP-01" || model.S(model.M(tasks[1])["checkpoint"]) != "CP-01" ||
		!bytes.Equal(canonicalFixtureBytes(t, model.M(tasks[2])["depends_on"]), canonicalFixtureBytes(t, model.List("T-002"))) || model.M(tasks[2])["checkpoint"] != "CP-02" {
		t.Fatal("fixture lost same-checkpoint sibling or transitive dependency")
	}
	seed := testutil.Seal(t, data)
	ex := model.M(seed.Data["execution"])
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		current := state(seed, id)
		current["evidence_refs"] = model.List(".codearbiter/.artifacts/receipts/" + canonical.BytesHash([]byte("opaque retained fixture "+id)) + ".json")
		if id == active {
			current["state"] = "IN_PROGRESS"
		}
	}
	input := canonical.BytesHash([]byte("in-memory input marker"))
	model.M(ex["scopes"])["CP-01"] = object{"base_input_sha256": input, "plan_sha256": seed.NormHash()}
	model.M(ex["scopes"])["CP-02"] = object{"base_input_sha256": input, "plan_sha256": seed.NormHash()}
	// Seal validates the actual supported model/structural contract after
	// fixture construction; invalid model data must fail before the oracle.
	return testutil.Seal(t, seed.Data)
}

func canonicalFixtureBytes(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := canonical.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func TestN19MethodResetRefusesAffectedActiveWriterWithoutMutation(t *testing.T) {
	for _, tc := range []struct{ name, active string }{
		{"selected-task", "T-001"},
		{"same-checkpoint-sibling", "T-002"},
		{"transitive-dependent", "T-003"},
		{"quiescent-control", ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			next := n19ActiveWriterModel(t, tc.active)
			if tc.active != "" && state(next, tc.active)["state"] != "IN_PROGRESS" {
				t.Fatal("active-writer fixture was not reached")
			}
			before := canonicalFixtureBytes(t, next.Data)
			normative := canonicalFixtureBytes(t, next.Norm())
			err := resetMethodDependents(next, "T-001")
			// Capture the entire post-call model before checking the error:
			// a broken guard must expose any partial reset or baseline loss.
			after := canonicalFixtureBytes(t, next.Data)
			if tc.active != "" {
				if err == nil || fault.Code(err) != "ACTIVE_WORK" || !bytes.Equal(before, after) {
					t.Fatalf("affected active writer must refuse before ANY model write: %v; before_sha256=%s after_sha256=%s", err, canonical.BytesHash(before), canonical.BytesHash(after))
				}
				return
			}
			if err != nil {
				t.Fatalf("quiescent reset refused: %v", err)
			}
			for _, id := range []string{"T-001", "T-002", "T-003"} {
				if state(next, id)["state"] != "PENDING" || model.S(state(next, id)["reason"]) == "" {
					t.Fatalf("quiescent affected task %s was not reset", id)
				}
			}
			if len(model.M(model.M(next.Data["execution"])["scopes"])) != 0 || !bytes.Equal(normative, canonicalFixtureBytes(t, next.Norm())) || bytes.Equal(before, after) {
				t.Fatal("healthy reset must clear affected baselines without changing requirements")
			}
		})
	}
}
