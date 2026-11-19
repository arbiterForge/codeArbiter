//go:build linux || darwin || windows

package operations

// NT-01 journal outcome preservation contracts. They hold a real repository
// lock, so they build only where a native storage backend exists.
// Transition rows: N01:06, N02:05, N02:06, N02:07, N02:08, N03:01, N03:02.

import (
	"bytes"
	"errors"
	"maps"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// interruptedTaskStart prepares a real task-start journal that stops after
// publication, exactly as a process killed between journal and replacement
// would leave it. The after-bytes and durable result come from running the
// same request against a byte-identical twin store.
func interruptedTaskStart(t *testing.T) (f *assistiveFixture, request object, before, after []byte, result object) {
	t.Helper()
	f = newAssistiveFixture(t)
	request, before, after, result = interruptedMutation(t, f, "task-start", object{"task": "T-001"})
	return f, request, before, after, result
}

// interruptedMutation leaves a real prepared journal for op on PLAN-EXAMPLE in
// f's store: the twin store computes the exact bytes and durable result.
func interruptedMutation(t *testing.T, f *assistiveFixture, op string, fields object) (request object, before, after []byte, result object) {
	t.Helper()
	twin := filepath.Join(testutil.Root(t), "twin")
	if err := os.CopyFS(twin, os.DirFS(f.root)); err != nil {
		t.Fatal(err)
	}
	request = f.mutation("PLAN-EXAMPLE", fields)
	request["protocol"] = Protocol
	plan := filepath.Join(".codearbiter", "plans", "example.html")
	var err error
	if before, err = os.ReadFile(filepath.Join(f.root, plan)); err != nil {
		t.Fatal(err)
	}
	twinRequest, _ := canonical.Clone(request)
	out, err := Run(twin, op, twinRequest)
	if err != nil {
		t.Fatal(err)
	}
	result = model.M(out)
	if after, err = os.ReadFile(filepath.Join(twin, plan)); err != nil {
		t.Fatal(err)
	}
	hash, err := canonical.Hash(object{"operation": op, "request": request})
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
	return request, before, after, result
}

func TestScopedConflictPreservesIndependentWorkAfterJournalRecovery(t *testing.T) {
	f := newAssistiveFixture(t)
	addScopedPrerequisite(f, "decision")
	f.mutate("prerequisite", prerequisiteReport("unsatisfied", "user_statement"))
	assertScope := func() {
		t.Helper()
		advice := f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
		if advice["next_task"] != "T-003" {
			t.Fatalf("scoped conflict changed the independent task advice: %v", advice)
		}
		affected := packetFor(f, "T-001")
		independent := packetFor(f, "T-003")
		if len(model.A(affected["waiting_prerequisites"])) != 1 || len(model.A(independent["waiting_prerequisites"])) != 0 {
			t.Fatalf("task context did not keep the conflict local: %v / %v", affected, independent)
		}
	}
	assertScope()
	context := object{"artifact_id": "PLAN-EXAMPLE", "task": "T-003", "model_sha256": f.doc("PLAN-EXAMPLE").Hash()}
	request, _, _, _ := interruptedMutation(t, f, "task-block", object{"task": "T-001", "reason": "Await the local policy decision."})
	if _, err := f.request("task-context", context); fault.Code(err) != "RECOVERY_REQUIRED" {
		t.Fatalf("independent task context crossed a pending store transaction: %v", err)
	}
	if _, err := f.request("recover", object{"operation_id": request["operation_id"], "mode": "rollback"}); err != nil {
		t.Fatal(err)
	}
	assertScope()
	f.mutate("task-start", object{"task": "T-003"})
	if state(f.doc("PLAN-EXAMPLE"), "T-003")["state"] != "IN_PROGRESS" {
		t.Fatal("independent work did not resume after recovery")
	}
	f.assertNoAuthorityFiles()
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

// Acceptance "Checkpoint retirement and interruption" (journal half): a typed
// retirement interrupted after journal publication completes or rolls back
// exactly, and the exact retry then replays or reports the rollback.
func TestInterruptedRetirementRecoversExactly(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			f := newAssistiveFixture(t)
			check := reportedCommand("fail", true)
			check["task"] = "T-002"
			f.mutate("task-check", check)
			request, before, after, _ := interruptedMutation(t, f, "apply", object{"changes": []any{
				object{"op": "record.update", "symbol": "CP-01", "fields": object{"tasks": model.List("T-001")}},
				object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": model.List("T-001")}},
				object{"op": "record.retire", "symbol": "T-002", "reason": "Folded into T-001."},
			}})
			planPath := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
			if _, err := Run(f.root, "identity", object{"protocol": Protocol, "artifact_id": "PLAN-EXAMPLE"}); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("interrupted retirement did not guard the store: %v", err)
			}
			if _, err := Run(f.root, "recover", object{"protocol": Protocol, "operation_id": request["operation_id"], "mode": mode}); err != nil {
				t.Fatal(err)
			}
			got, _ := os.ReadFile(planPath)
			retry, _ := canonical.Clone(request)
			_, err := Run(f.root, "apply", retry)
			d := f.doc("PLAN-EXAMPLE")
			history := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-002"])
			if mode == "complete" {
				if string(got) != string(after) || err != nil || d.Data["schema_version"] != model.RetirementVersion || len(history) != 1 {
					t.Fatalf("completed retirement lost bytes, replay or typed history: %v", err)
				}
				return
			}
			if string(got) != string(before) || fault.Code(err) != "OPERATION_ROLLED_BACK" || d.Data["schema_version"] == model.RetirementVersion || len(history) != 1 {
				t.Fatalf("rolled-back retirement was not exact: %v", err)
			}
		})
	}
}

func TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory(t *testing.T) {
	for _, tc := range []struct {
		name, point, mode string
	}{
		{"staging", "after-stage-0", ""},
		{"complete", "after-journal", "complete"},
		{"rollback", "after-replace-0", "rollback"},
		{"independent-edit", "after-replace-0", ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newAssistiveFixture(t)
			h := &harness{t: t, root: f.root}
			scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
			h.approvePair()
			h.start("T-001")
			h.review("T-001")
			const retired, replacement, reason = "CP-01", "CP-02", "Moved this scope into CP-02."
			plan := f.doc("PLAN-EXAMPLE")
			execution := model.M(plan.Data["execution"])
			baseline := model.M(model.M(execution["scopes"])[retired])
			refs := model.Strings(state(plan, "T-001")["evidence_refs"])
			if baseline["base_input_sha256"] == nil || baseline["plan_sha256"] != plan.NormHash() || len(refs) < 2 {
				t.Fatalf("fixture lacks a real receipted scope baseline: %v %v", baseline, refs)
			}
			evidence := map[string]string{}
			for _, ref := range refs {
				source := filepath.Join(f.root, filepath.FromSlash(ref))
				raw, err := os.ReadFile(source)
				if err != nil {
					t.Fatal(err)
				}
				evidence[source] = canonical.BytesHash(raw)
			}

			changes := []any{
				object{"op": "record.update", "symbol": "T-001", "fields": object{"checkpoint": replacement, "execution_scope": replacement}},
				object{"op": "record.update", "symbol": "T-002", "fields": object{"checkpoint": replacement, "execution_scope": replacement}},
				object{"op": "record.update", "symbol": replacement, "fields": object{"tasks": model.List("T-001", "T-002", "T-003"), "depends_on": empty()}},
				object{"op": "record.retire", "symbol": retired, "reason": reason, "replacement_ref": replacement},
			}
			planPath := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
			readPlan := func() []byte {
				raw, err := os.ReadFile(planPath)
				if err != nil {
					t.Fatal(err)
				}
				return raw
			}
			before := readPlan()
			request := f.mutation(plan.ID(), object{"changes": changes})
			operationID := model.S(request["operation_id"])
			injected := false
			interruption := errors.New("fixture interrupted checkpoint retirement")
			_, err := func() (any, error) {
				original := openStore
				defer func() { openStore = original }()
				openStore = func(root string) (*store.FS, error) {
					fs, err := original(root)
					if err == nil && root == f.root {
						fs.Inject = func(step string) error {
							if step == tc.point {
								injected = true
								return interruption
							}
							return nil
						}
					}
					return fs, err
				}
				return f.request("apply", request)
			}()
			if tc.point == "after-stage-0" {
				if !errors.Is(err, interruption) || !injected || !bytes.Equal(readPlan(), before) {
					t.Fatalf("pre-journal failure changed the original plan: %v", err)
				}
				retry, err := f.request("apply", request)
				if err != nil || model.M(retry)["transaction"].(store.Outcome).Replay {
					t.Fatalf("pre-journal failure did not allow an exact fresh retry: %v", err)
				}
				retiredPlan := f.doc(plan.ID())
				if !equalValue(model.M(model.M(retiredPlan.Data["execution"])["scopes"])[retired], baseline) ||
					tombstone(retiredPlan, retired)["original_kind"] != "checkpoints" {
					t.Fatal("fresh retry lost the original baseline or checkpoint ownership")
				}
				return
			}
			if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" || !injected {
				t.Fatalf("retirement did not reach %s: %v", tc.point, err)
			}
			prepared := readPlan()
			if bytes.Equal(prepared, before) != (tc.point == "after-journal") {
				t.Fatal("the plan bytes disagree with the interrupted replacement phase")
			}
			afterImage := prepared
			if tc.point == "after-journal" {
				afterImage, err = os.ReadFile(filepath.Join(filepath.Dir(planPath), ".ca-artifact-"+operationID+"-0.new"))
				if err != nil {
					t.Fatal(err)
				}
			}
			if _, err := f.request("apply", request); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("exact retry crossed pending retirement: %v", err)
			}

			if tc.mode == "" {
				// An external editor writes a valid independent rendering after
				// replacement. Both recovery choices must preserve it and history.
				thirdParty, err := render.Parse(prepared)
				if err != nil {
					t.Fatal(err)
				}
				model.M(thirdParty.Data["presentation"])["brand_name"] = "Independent local edit"
				thirdParty.Data["revision"] = thirdParty.Revision() + 1
				thirdParty, err = render.Prepare(thirdParty.Data)
				if err != nil {
					t.Fatal(err)
				}
				raw, err := render.Render(thirdParty)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(planPath, raw, 0644); err != nil {
					t.Fatal(err)
				}
				files := readModeTree(t, f.root)
				for _, mode := range []string{"complete", "rollback"} {
					if _, err := f.request("recover", object{"operation_id": operationID, "mode": mode}); fault.Code(err) != "RECOVERY_CONFLICT" {
						t.Fatalf("%s did not refuse an independent edit: %v", mode, err)
					}
					if !bytes.Equal(readPlan(), raw) || !maps.Equal(readModeTree(t, f.root), files) {
						t.Fatalf("%s altered a document or journal input on conflict", mode)
					}
				}
				return
			}

			outcome, err := f.request("recover", object{"operation_id": operationID, "mode": tc.mode})
			if err != nil {
				t.Fatal(err)
			}
			settled := readPlan()
			after := f.doc(plan.ID())
			afterExecution := model.M(after.Data["execution"])
			if !equalValue(model.M(afterExecution["scopes"])[retired], baseline) ||
				!equalValue(state(plan, "T-001"), state(after, "T-001")) {
				t.Fatal("recovery changed the original scope baseline or receipted task history")
			}
			for path, hash := range evidence {
				raw, err := os.ReadFile(path)
				if err != nil || canonical.BytesHash(raw) != hash {
					t.Fatalf("recovery changed a retained receipt: %v", err)
				}
			}
			retried, err := f.request("apply", request)
			if tc.mode == "rollback" {
				if outcome.(store.Outcome).State != "rolled_back" || fault.Code(err) != "OPERATION_ROLLED_BACK" ||
					!bytes.Equal(settled, before) || !bytes.Equal(readPlan(), before) || tombstone(after, retired) != nil {
					t.Fatalf("rollback or retry changed the original scope: %v", err)
				}
				return
			}
			if outcome.(store.Outcome).State != "committed" || err != nil ||
				!model.M(retried)["transaction"].(store.Outcome).Replay ||
				!bytes.Equal(settled, afterImage) || !bytes.Equal(readPlan(), settled) {
				t.Fatalf("completion or exact retry did not preserve its outcome: %v", err)
			}
			stone := tombstone(after, retired)
			if stone["original_kind"] != "checkpoints" || stone["reason"] != reason ||
				stone["replacement_ref"] != replacement || stone["retired_in_revision"] != after.Revision() {
				t.Fatalf("completed retirement did not preserve typed ownership: %v", stone)
			}
			exact := f.call("read", object{"artifact_id": plan.ID(), "mode": "exact", "symbol": retired})
			if !equalValue(exact["record"], stone) ||
				f.call("validate", object{"artifact_id": plan.ID(), "gate": "structural"})["valid"] != true {
				t.Fatal("retired scope was not structurally valid and readable as a tombstone")
			}
			if _, err := f.request("accept-scope", f.mutation(plan.ID(), object{"scope": retired, "reason": "Fixture."})); fault.Code(err) != "UNKNOWN_SCOPE" {
				t.Fatalf("retired checkpoint was accepted as current scope: %v", err)
			}
		})
	}
}
