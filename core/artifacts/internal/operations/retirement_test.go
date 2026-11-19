package operations

// NT-05 / N-F10: retirement keeps typed ownership of retained history.
// Transition rows: N06:03, N06:04, N04:02, N04:03, N13:01.

import (
	"bytes"
	"maps"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func retireT002(f *assistiveFixture) (any, error) {
	return f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.update", "symbol": "CP-01", "fields": object{"tasks": model.List("T-001")}},
		object{"op": "record.update", "symbol": "T-003", "fields": object{"depends_on": model.List("T-001")}},
		object{"op": "record.retire", "symbol": "T-002", "reason": "Folded into T-001."},
	}}))
}

func tombstone(d *model.Document, id string) object {
	for _, v := range model.A(d.Norm()["retired_symbols"]) {
		if model.S(model.M(v)["id"]) == id {
			return model.M(v)
		}
	}
	return nil
}

// A criterion owns nested scenario and nullable verification records. Their
// tombstones must retain the real schema collection, including alternatives.
func TestRetiringCriterionKeepsNestedCollectionKinds(t *testing.T) {
	f := newAssistiveFixture(t)
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{
		object{"op": "record.retire", "symbol": "AC-001", "reason": "Replace this draft criterion."},
	}}))
	d := f.doc("SPEC-EXAMPLE")
	for id, kind := range map[string]string{"AC-001": "criteria", "SCN-AC-001": "scenarios", "VER-AC-001": "verification"} {
		if stone := tombstone(d, id); stone == nil || stone["original_kind"] != kind {
			t.Fatalf("retired %s lost its real collection %s: %v", id, kind, stone)
		}
	}
	if es := validateStructural(d.Data); len(es) != 0 {
		t.Fatalf("valid nested retirement rejected: %v", es)
	}
}

// Acceptance "Checked task retirement".
func TestRetiringCheckedTaskKeepsTypedHistory(t *testing.T) {
	f := newAssistiveFixture(t)
	for _, outcome := range []string{"pass", "fail"} {
		r := reportedCommand(outcome, true)
		r["task"] = "T-002"
		f.mutate("task-check", r)
	}
	before := model.A(model.M(model.M(f.doc("PLAN-EXAMPLE").Data["execution"])["task_check_observations"])["T-002"])
	if _, err := retireT002(f); err != nil {
		t.Fatalf("retiring a task with recorded checks was refused: %v", err)
	}
	d := f.doc("PLAN-EXAMPLE")
	stone := tombstone(d, "T-002")
	if stone["original_kind"] != "tasks" || d.Data["schema_version"] != model.RetirementVersion {
		t.Fatalf("tombstone lost its original kind or the version label: %v %v", stone, d.Data["schema_version"])
	}
	after := model.A(model.M(model.M(d.Data["execution"])["task_check_observations"])["T-002"])
	if !equalValue(before, after) || len(after) != 2 {
		t.Fatal("retirement deleted or changed retained check history")
	}
	html, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "plans", "example.html"))
	if err != nil || !strings.Contains(string(html), "Retained command checks of this retired task") {
		t.Fatalf("rendered plan hides the retired task's retained checks: %v", err)
	}
	if caps := f.call("capabilities", object{}); caps["retirement_schema_version"] != model.RetirementVersion {
		t.Fatalf("capabilities do not advertise the retirement schema label: %v", caps["retirement_schema_version"])
	}
	if _, live := model.M(model.M(d.Data["execution"])["tasks"])["T-002"]; live {
		t.Fatal("retired task still has live scheduling state")
	}
	for _, row := range model.A(f.call("eligible", object{"artifact_id": "PLAN-EXAMPLE"})["tasks"]) {
		if model.M(row)["task"] == "T-002" {
			t.Fatal("retired task appears in scheduling")
		}
	}
	if _, err := f.request("task-start", f.mutation("PLAN-EXAMPLE", object{"task": "T-002"})); fault.Code(err) != "UNKNOWN_TASK" {
		t.Fatalf("retired task accepted new progress: %v", err)
	}
	// Stable IDs stay reserved: no re-add, no repeated retirement.
	reused := object{}
	for key, value := range model.M(model.A(f.doc("PLAN-EXAMPLE").Norm()["tasks"])[0]) {
		reused[key] = value
	}
	reused["id"] = "T-002"
	if _, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.add", "collection": "tasks", "record": reused},
	}})); err == nil {
		t.Fatal("a duplicate/retired ID was reused")
	}
	if _, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{
		object{"op": "record.retire", "symbol": "T-002", "reason": "Again."},
	}})); err == nil {
		t.Fatal("a tombstone was retired twice")
	}
	// Later ordinary writes keep the version label and never downgrade it.
	f.mutate("task-start", object{"task": "T-001"})
	r := reportedCommand("unknown", true)
	f.mutate("task-check", r)
	f.mutate("task-review", object{"task": "T-001"})
	f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Batch implemented."})
	f.mutate("plan-bind", object{"spec_id": "SPEC-EXAMPLE"})
	if v := f.doc("PLAN-EXAMPLE").Data["schema_version"]; v != model.RetirementVersion {
		t.Fatalf("a later ordinary write relabeled the plan %v", v)
	}
	f.call("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-002", "mode": "exact"})
	f.assertNoAuthorityFiles()
}

// Retiring a checkpoint with a retained scope baseline keeps the baseline as
// typed history instead of failing with ORPHAN_STATE.
func TestRetiringCheckpointKeepsScopeBaseline(t *testing.T) {
	f := newAssistiveFixture(t)
	// A baseline is written only by a receipted review; seed one through the
	// supported repair-free path: write it via a real apply is not possible, so
	// construct it on a retirement candidate document directly.
	d := f.doc("PLAN-EXAMPLE")
	next, err := d.Clone()
	if err != nil {
		t.Fatal(err)
	}
	model.M(model.M(next.Data["execution"])["scopes"])["CP-02"] = object{"base_input_sha256": strings.Repeat("a", 64), "plan_sha256": d.NormHash()}
	norm := next.Norm()
	norm["checkpoints"] = model.A(norm["checkpoints"])[:1]
	cp := model.M(model.A(norm["checkpoints"])[0])
	cp["tasks"] = model.List("T-001", "T-002", "T-003")
	task := model.M(model.A(norm["tasks"])[2])
	task["checkpoint"], task["execution_scope"] = "CP-01", "CP-01"
	norm["retired_symbols"] = append(model.A(norm["retired_symbols"]), object{"id": "CP-02", "retired_in_revision": d.Revision(), "reason": "Merged into CP-01.", "replacement_ref": "CP-01", "original_kind": "checkpoints"})
	next.Data["schema_version"] = model.RetirementVersion
	if _, err := model.Check(next.Data); err != nil {
		t.Fatalf("typed checkpoint tombstone was not admitted: %v", err)
	}
	if es := validateStructural(next.Data); len(es) != 0 {
		t.Fatalf("retained scope baseline of a typed retired checkpoint is orphaned: %v", es)
	}
	stone := model.M(model.A(norm["retired_symbols"])[len(model.A(norm["retired_symbols"]))-1])
	delete(stone, "original_kind")
	if es := validateStructural(next.Data); len(es) != 0 {
		t.Fatalf("unclassified legacy scope history could not be preserved: %v", es)
	}
	stone["original_kind"] = "tasks"
	if es := validateStructural(next.Data); len(es) == 0 || es[0].Code != "ORPHAN_STATE" {
		t.Fatalf("a known task tombstone owned a checkpoint baseline: %v", es)
	}
}

// Acceptance "Unknown legacy kind": an untyped tombstone is never resolved
// from its ID prefix, and the new field cannot ride on an old version label.
func TestUntypedTombstoneDoesNotOwnHistory(t *testing.T) {
	f := newAssistiveFixture(t)
	r := reportedCommand("pass", true)
	r["task"] = "T-002"
	f.mutate("task-check", r)
	if _, err := retireT002(f); err != nil {
		t.Fatal(err)
	}
	d := f.doc("PLAN-EXAMPLE")
	legacy, _ := d.Clone()
	stone := tombstone(legacy, "T-002")
	delete(stone, "original_kind")
	if es := validateStructural(legacy.Data); len(es) != 0 {
		t.Fatalf("unclassified command history could not be preserved: %v", es)
	}
	orphaned, _ := legacy.Clone()
	checks := model.M(model.M(orphaned.Data["execution"])["task_check_observations"])
	checks["T-MISSING"] = checks["T-002"]
	if es := validateStructural(orphaned.Data); len(es) == 0 || es[0].Code != "ORPHAN_STATE" {
		t.Fatalf("command history without a known tombstone was accepted: %v", es)
	}
	old, _ := d.Clone()
	old.Data["schema_version"] = "0.3.2"
	if _, err := model.Check(old.Data); fault.Code(err) != "UNSUPPORTED_VERSION" {
		t.Fatalf("typed tombstone was accepted under schema 0.3.2: %v", err)
	}
	bad, _ := d.Clone()
	tombstone(bad, "T-002")["original_kind"] = "retired_symbols"
	if es := validateStructural(bad.Data); len(es) == 0 {
		t.Fatal("tombstone accepted a non-record original kind")
	}
	for _, originalKind := range []string{"imaginary", "criteria", "task_check_observations"} {
		bad, _ := d.Clone()
		tombstone(bad, "T-002")["original_kind"] = originalKind
		if es := validateStructural(bad.Data); len(es) == 0 {
			t.Fatalf("plan tombstone accepted an absent record collection %q", originalKind)
		}
	}
}

func validateStructural(v object) []fault.Error {
	d, err := model.Check(v)
	if err != nil {
		return []fault.Error{{Code: fault.Code(err), Message: err.Error()}}
	}
	return validate.Structural(d)
}

func TestRetirementKindMustNameAnActualCollection(t *testing.T) {
	f := newAssistiveFixture(t)
	d, _ := f.doc("PLAN-EXAMPLE").Clone()
	d.Data["schema_version"] = model.RetirementVersion
	d.Norm()["retired_symbols"] = append(model.A(d.Norm()["retired_symbols"]), object{
		"id": "RETIRED-EXAMPLE", "retired_in_revision": d.Revision(),
		"reason": "Historical record retired.", "replacement_ref": nil, "original_kind": "imaginary",
	})
	if es := validateStructural(d.Data); len(es) == 0 {
		t.Fatal("a typed tombstone accepted an invented record collection")
	}
}

func oldRetirementFixture(t *testing.T, attachedHistory bool) (*assistiveFixture, *model.Document, []byte) {
	t.Helper()
	seed := newAssistiveFixture(t)
	seed.mutate("task-check", reportedCommand("pass", true))
	if attachedHistory {
		check := reportedCommand("fail", true)
		check["task"] = "T-002"
		seed.mutate("task-check", check)
	}
	if _, err := retireT002(seed); err != nil {
		t.Fatal(err)
	}
	legacy := seed.doc("PLAN-EXAMPLE")
	delete(tombstone(legacy, "T-002"), "original_kind")
	legacy.Data["schema_version"] = model.SchemaVersion
	if attachedHistory {
		legacy.Norm()["retired_symbols"] = append(model.A(legacy.Norm()["retired_symbols"]), object{
			"id": "CP-OLD", "retired_in_revision": legacy.Revision(), "reason": "Historical scope.",
			"replacement_ref": nil,
		})
		model.M(model.M(legacy.Data["execution"])["scopes"])["CP-OLD"] = object{
			"base_input_sha256": strings.Repeat("a", 64), "plan_sha256": legacy.NormHash(),
		}
	}
	legacy, err := model.Seal(legacy.Data)
	if err != nil {
		t.Fatal(err)
	}
	planBytes, err := render.Render(legacy)
	if err != nil {
		t.Fatal(err)
	}
	specBytes, err := os.ReadFile(filepath.Join(seed.root, ".codearbiter", "specs", "example.html"))
	if err != nil {
		t.Fatal(err)
	}

	// Carry only the portable legacy documents into a fresh owned store.
	// The typed seed's journal and before-images are deliberately absent.
	f := &assistiveFixture{t: t, root: testutil.Root(t)}
	planPath := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
	for p, data := range map[string][]byte{
		planPath: planBytes, filepath.Join(f.root, ".codearbiter", "specs", "example.html"): specBytes,
	} {
		if err := os.MkdirAll(filepath.Dir(p), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, data, 0644); err != nil {
			t.Fatal(err)
		}
	}
	f.call("init-store", object{})
	return f, legacy, planBytes
}

func TestLegacyRetirementAmbiguityDoesNotBlockIndependentWork(t *testing.T) {
	f, legacy, planBytes := oldRetirementFixture(t, false)
	planPath := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
	current := f.call("read", object{"artifact_id": legacy.ID(), "mode": "exact", "symbol": "T-002"})
	if _, typed := model.M(current["record"])["original_kind"]; typed || current["reported_checks"] != nil {
		t.Fatal("old task-looking ID acquired live historical ownership")
	}
	if _, err := f.request("task-start", f.mutation(legacy.ID(), object{"task": "T-002"})); fault.Code(err) != "UNKNOWN_TASK" {
		t.Fatalf("untyped tombstone acquired live task authority: %v", err)
	}
	before, err := os.ReadFile(planPath)
	if err != nil || !bytes.Equal(before, planBytes) {
		t.Fatalf("inspection or refused work changed the legacy plan: %v", err)
	}
	if _, err := f.request("task-start", f.mutation(legacy.ID(), object{"task": "T-001"})); err != nil {
		t.Fatalf("unrelated current task could not start while the old history remains unclassified: %v", err)
	}
	next := f.doc(legacy.ID())
	history := func(d *model.Document) any {
		return model.M(model.M(d.Data["execution"])["task_check_observations"])["T-001"]
	}
	if _, typed := tombstone(next, "T-002")["original_kind"]; typed || !equalValue(history(legacy), history(next)) ||
		state(next, "T-001")["state"] != "IN_PROGRESS" {
		t.Fatal("independent work changed the old tombstone, existing check history or the live task outcome")
	}
}

func TestLegacyNativeRetirementPreviewBindsPreimageAndRefusesDrift(t *testing.T) {
	for _, tc := range []struct {
		name    string
		history bool
	}{{"old-tombstone", false}, {"retained-unclassified-history", true}} {
		t.Run(tc.name, func(t *testing.T) {
			f, legacy, planBytes := oldRetirementFixture(t, tc.history)
			preimage := canonical.BytesHash(planBytes)
			request := object{"native_retirement": object{
				"artifact_id": legacy.ID(), "expected_bytes_sha256": preimage,
			}}
			treeBefore := descriptorEffectSnapshot(t, f.root)
			preview := f.call("migration-preview", request)
			manifest := model.M(preview["manifest"])
			source := model.M(manifest["source"])
			if manifest["format"] != "codearbiter.native-retirement-preview/1" ||
				source["artifact_id"] != legacy.ID() || source["path"] != ".codearbiter/plans/example.html" ||
				source["bytes_sha256"] != preimage || source["model_sha256"] != legacy.Hash() ||
				source["normative_sha256"] != legacy.NormHash() || source["schema_version"] != model.SchemaVersion {
				t.Fatalf("preview lost the exact selected legacy source: %v", manifest)
			}
			wantHistory := []any{object{"id": "T-002", "reported_check_count": int64(0), "scope_baseline_retained": false}}
			if tc.history {
				wantHistory = []any{
					object{"id": "CP-OLD", "reported_check_count": int64(0), "scope_baseline_retained": true},
					object{"id": "T-002", "reported_check_count": int64(1), "scope_baseline_retained": false},
				}
			}
			hash, err := canonical.Hash(manifest)
			if err != nil || preview["preview_sha256"] != hash || !equalValue(manifest["unclassified_history"], wantHistory) {
				t.Fatalf("preview did not bind the unresolved history as historical: %v", manifest)
			}
			current := f.call("read", object{"artifact_id": legacy.ID(), "mode": "exact", "symbol": "T-002"})
			if current["history_classification"] != "unclassified" || current["reported_checks"] != nil ||
				!equalValue(current["record"], tombstone(legacy, "T-002")) {
				t.Fatalf("ordinary exact read classified retained history as task proof: %v", current)
			}
			if _, err := f.request("task-context", object{"artifact_id": legacy.ID(), "task": "T-002", "model_sha256": legacy.Hash()}); fault.Code(err) != "UNKNOWN_TASK" {
				t.Fatalf("unclassified tombstone became current task proof: %v", err)
			}
			if _, err := f.request("migration-apply", request); err == nil {
				t.Fatal("read-only native preview request was admitted to apply")
			}
			mixed := object{"native_retirement": request["native_retirement"], "spec": object{}}
			if _, err := f.request("migration-preview", mixed); fault.Code(err) != "INVALID_MODEL" || fault.Public(err).Field != "/spec" {
				t.Fatalf("mixed preview lost the closed native shape diagnostic: %v", err)
			}
			if !maps.Equal(descriptorEffectSnapshot(t, f.root), treeBefore) {
				t.Fatal("preview, exact read or refused apply changed the source store")
			}

			f.mutate("task-start", object{"task": "T-001"})
			after := f.doc(legacy.ID())
			original := model.M(legacy.Data["execution"])
			settled := model.M(after.Data["execution"])
			if !equalValue(original["task_check_observations"], settled["task_check_observations"]) ||
				!equalValue(original["scopes"], settled["scopes"]) ||
				!equalValue(legacy.Norm()["retired_symbols"], after.Norm()["retired_symbols"]) {
				t.Fatal("unrelated current work changed unclassified history")
			}
			treeAfter := descriptorEffectSnapshot(t, f.root)
			if _, err := f.request("migration-preview", request); fault.Code(err) != "STALE_PREVIEW" ||
				!maps.Equal(descriptorEffectSnapshot(t, f.root), treeAfter) {
				t.Fatalf("preview accepted stale original bytes or modified the valid edit: %v", err)
			}
			path := filepath.Join(f.root, ".codearbiter", "plans", "example.html")
			bytesAfter, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			viewDrift := bytes.Replace(bytesAfter, []byte("<main class="), []byte("<main data-unrelated=\"drift\" class="), 1)
			if bytes.Equal(bytesAfter, viewDrift) {
				t.Fatal("fixture did not introduce unrelated HTML drift")
			}
			if err := os.WriteFile(path, viewDrift, 0644); err != nil {
				t.Fatal(err)
			}
			driftTree := descriptorEffectSnapshot(t, f.root)
			model.M(request["native_retirement"])["expected_bytes_sha256"] = canonical.BytesHash(viewDrift)
			if _, err := f.request("migration-preview", request); fault.Code(err) != "RENDER_DRIFT" ||
				!maps.Equal(descriptorEffectSnapshot(t, f.root), driftTree) {
				t.Fatalf("preview admitted or changed unrelated view drift: %v", err)
			}
		})
	}
}
