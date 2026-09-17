package operations

import (
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

type farmHarness struct {
	t    *testing.T
	root string
	n    int
}

func newFarmHarness(t *testing.T) *farmHarness {
	t.Helper()
	return &farmHarness{t: t, root: t.TempDir()}
}
func (h *farmHarness) next() string { h.n++; return fmt.Sprintf("farm-fixture-%04d", h.n) }
func (h *farmHarness) request(op string, r object) (any, error) {
	h.t.Helper()
	r["protocol"] = Protocol
	return Run(h.root, op, r)
}
func (h *farmHarness) run(op string, r object) object {
	h.t.Helper()
	v, err := h.request(op, r)
	if err != nil {
		h.t.Fatalf("%s: %v", op, err)
	}
	return model.M(v)
}
func (h *farmHarness) doc(id string) *model.Document {
	h.t.Helper()
	f, err := store.Open(h.root)
	if err != nil {
		h.t.Fatal(err)
	}
	defer f.Close()
	catalog, err := repository.Scan(f)
	if err != nil {
		h.t.Fatal(err)
	}
	entry, err := catalog.Resolve(id)
	if err != nil {
		h.t.Fatal(err)
	}
	return entry.Doc
}
func (h *farmHarness) mutate(op, id string, r object) object {
	h.t.Helper()
	d := h.doc(id)
	r["artifact_id"] = id
	r["operation_id"] = h.next()
	r["expected"] = object{"revision": d.Revision(), "model_sha256": d.Hash()}
	return h.run(op, r)
}
func (h *farmHarness) createPair() {
	h.createPairExpectedExit(0)
}
func (h *farmHarness) createPairExpectedExit(expectedExit int64) {
	h.t.Helper()
	spec := model.M(testutil.Spec()["normative"])
	h.run("create", object{"operation_id": h.next(), "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": spec["title"], "summary": spec["summary"], "normative": spec})
	s := h.doc("SPEC-EXAMPLE")
	plan := model.M(testutil.Plan(s)["normative"])
	verification := model.M(model.A(model.M(model.A(plan["tasks"])[0])["verification"])[0])
	verification["expected_exit"] = expectedExit
	h.run("create", object{"operation_id": h.next(), "artifact_id": "PLAN-EXAMPLE", "kind": "plan", "slug": "example", "title": plan["title"], "summary": plan["summary"], "spec_id": s.ID(), "normative": plan})
	h.approve("SPEC-EXAMPLE")
	h.mutate("plan-bind", "PLAN-EXAMPLE", object{"spec_id": "SPEC-EXAMPLE"})
	h.approve("PLAN-EXAMPLE")
}
func (h *farmHarness) capture(id, record, kind string, payload object) string {
	h.t.Helper()
	d := h.doc(id)
	event := object{"format": "codearbiter.workflow-event/0.1.0", "kind": kind, "authority_kind": "user_workflow", "subject": object{"artifact_id": id, "normative_sha256": d.NormHash(), "record_id": record}, "actor": "synthetic farm fixture", "origin": "isolated test " + h.next(), "verdict": "approved", "payload": payload, "source_text": "Synthetic farm authorization fixture; not production authority."}
	return model.S(h.run("capture", object{"event": event})["receipt"])
}
func (h *farmHarness) approve(id string) {
	h.t.Helper()
	receipt := h.capture(id, id, "approval", object{})
	h.mutate("approve", id, object{"receipt": receipt})
}
func (h *farmHarness) projection() object {
	return object{"meta": object{"name": "example"}, "tasks": []any{object{"id": "t-001", "description": "Implement and verify stage 1", "deps": []any{}, "filesInScope": []any{"src/stage1.go"}, "test": object{"path": "src/stage1.go"}, "gate": object{"commands": []any{"go test ./... -run TestEnvironmentOverrides"}}}}}
}
func (h *farmHarness) project() object {
	h.t.Helper()
	return h.projectSlice(h.projection(), []string{"T-001"})
}
func (h *farmHarness) projectSlice(projection object, slice []string) object {
	h.t.Helper()
	_, base, err := farmBase(projection)
	if err != nil {
		h.t.Fatal(err)
	}
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	input := model.S(h.run("snapshot", object{"artifact_id": plan.ID()})["sha256"])
	red := []any{}
	for index, id := range slice {
		task := plan.Symbols.ByID[id].Value
		definition := model.M(model.A(task["verification"])[0])
		definitionHash, _ := canonical.Hash(definition)
		projected := model.M(model.A(projection["tasks"])[index])
		red = append(red, object{"source_task": id, "farm_task": strings.ToLower(id), "test_path": model.S(model.M(projected["test"])["path"]), "definition_sha256": definitionHash, "command": "go test ./... -run TestEnvironmentOverrides", "exit": int64(1), "stdout_sha256": canonical.BytesHash([]byte("fixture RED")), "stderr_sha256": canonical.BytesHash(nil)})
	}
	payload := object{"format": "codearbiter.farm-authorization/0.1.0", "input_sha256": input, "spec_sha256": spec.NormHash(), "plan_sha256": plan.NormHash(), "scope": "CP-01", "base_sha256": base, "red_evidence": red}
	receipt := h.capture(plan.ID(), "CP-01", "farm_authorization", payload)
	values := make([]any, len(slice))
	for i := range slice {
		values[i] = slice[i]
	}
	return h.mutate("farm-project", plan.ID(), object{"scope": "CP-01", "slice": values, "target": ".codearbiter/plans/example.plan.json", "projection": projection, "receipt": receipt})
}

func (h *farmHarness) derived(pathname string) object {
	h.t.Helper()
	b, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(pathname)))
	if err != nil {
		h.t.Fatal(err)
	}
	v, err := canonical.Object(b)
	if err != nil {
		h.t.Fatal(err)
	}
	return v
}

func (h *farmHarness) forge(kind string, value object) string {
	h.t.Helper()
	b, err := canonical.Marshal(value)
	if err != nil {
		h.t.Fatal(err)
	}
	digest := canonical.BytesHash(b)
	p := filepath.Join(h.root, ".codearbiter", ".artifacts", kind, digest+".json")
	if err = os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		h.t.Fatal(err)
	}
	if err = os.WriteFile(p, b, 0600); err != nil {
		h.t.Fatal(err)
	}
	return ".codearbiter/.artifacts/" + kind + "/" + digest + ".json"
}

func TestFarmProjectionBinding(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	result := h.project()
	if model.S(result["path"]) != ".codearbiter/plans/example.plan.json" || model.S(result["binding"]) == "" {
		t.Fatal(result)
	}
	verified := h.run("farm-verify", object{"projection_path": result["path"], "phase": "canary"})
	if verified["typed"] != true || model.S(verified["base_sha256"]) != model.S(result["base_sha256"]) {
		t.Fatal(verified)
	}
}

func TestFarmProjectionBindingIncludesOrderedPendingDependencies(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	projection := object{"meta": object{"name": "example"}, "tasks": []any{
		object{"id": "t-001", "description": "Implement and verify stage 1", "deps": []any{}, "filesInScope": []any{"src/stage1.go"}, "test": object{"path": "src/stage1.go"}, "gate": object{"commands": []any{"go test ./... -run TestEnvironmentOverrides"}}},
		object{"id": "t-002", "description": "Implement and verify stage 2", "deps": []any{"t-001"}, "filesInScope": []any{"src/stage2.go"}, "test": object{"path": "src/stage2.go"}, "gate": object{"commands": []any{"go test ./... -run TestEnvironmentOverrides"}}},
	}}
	result := h.projectSlice(projection, []string{"T-001", "T-002"})
	if model.S(result["binding"]) == "" {
		t.Fatal(result)
	}
}

func TestAuthorizedFarmEnrichment(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	result := h.project()
	projectionPath := filepath.Join(h.root, filepath.FromSlash(model.S(result["path"])))
	projection := h.projection()
	meta := model.M(projection["meta"])
	meta["model"] = "fixture/model"
	meta["apiBaseUrl"] = "https://example.invalid/v1"
	bytesValue, err := canonical.Marshal(projection)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(projectionPath, append(bytesValue, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	h.run("farm-seal", object{"projection_path": result["path"], "provenance": object{"model": "fixture/model", "api_base_url": "https://example.invalid/v1", "selection_source": "canary", "origin": "synthetic selection fixture"}})
	verified := h.run("farm-verify", object{"projection_path": result["path"], "phase": "dispatch", "effective_model": "fixture/model", "effective_api_base_url": "https://example.invalid/v1"})
	if verified["typed"] != true || model.S(verified["seal"]) == "" {
		t.Fatal(verified)
	}
	model.M(model.A(projection["tasks"])[0])["description"] = "tampered"
	tampered, _ := canonical.Marshal(projection)
	if err = os.WriteFile(projectionPath, append(tampered, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	_, err = h.request("farm-verify", object{"projection_path": result["path"], "phase": "dispatch", "effective_model": "fixture/model", "effective_api_base_url": "https://example.invalid/v1"})
	if fault.Code(err) != "FARM_BINDING_MISSING" {
		t.Fatalf("expected changed task bytes to invalidate base binding, got %v", err)
	}
}

func TestCanaryPreflightBinding(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	projection := h.projection()
	b, _ := canonical.Marshal(projection)
	projectionPath := filepath.Join(h.root, ".codearbiter", "plans", "example.plan.json")
	if err := os.WriteFile(projectionPath, append(b, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := h.request("farm-verify", object{"projection_path": ".codearbiter/plans/example.plan.json", "phase": "canary"})
	if fault.Code(err) != "FARM_BINDING_MISSING" {
		t.Fatalf("expected unbound HTML projection to fail before canary, got %v", err)
	}
}

func TestCanaryPreflightRequiresExactBaseBytes(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	result := h.project()
	projectionPath := filepath.Join(h.root, filepath.FromSlash(model.S(result["path"])))
	b, err := canonical.Marshal(h.projection())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(projectionPath, b, 0600); err != nil { // remove the engine-written newline only
		t.Fatal(err)
	}
	_, err = h.request("farm-verify", object{"projection_path": result["path"], "phase": "canary"})
	if fault.Code(err) != "INVALID_FARM_PROJECTION" {
		t.Fatalf("expected byte-level base drift to block canary, got %v", err)
	}
}

func TestFarmBindingRevalidatesCompleteAuthorizationReceipt(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	result := h.project()
	malformed := h.capture("PLAN-EXAMPLE", "CP-01", "farm_authorization", object{
		"format": "codearbiter.farm-authorization/0.1.0",
	})
	forged := h.derived(model.S(result["binding"]))
	forged["authorization_receipt"] = malformed
	forged["authorization_sha256"] = strings.TrimSuffix(path.Base(malformed), ".json")
	h.forge("farm-bindings", forged)
	_, err := h.request("farm-verify", object{"projection_path": result["path"], "phase": "canary"})
	if fault.Code(err) != "STALE_EVIDENCE" {
		t.Fatalf("expected reused but incomplete authorization to be rejected, got %v", err)
	}
}

func TestFarmProjectionRefreshSelectsCurrentBinding(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	first := h.project()
	if err := os.MkdirAll(filepath.Join(h.root, "src"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(h.root, "src", "stage1.go"), []byte("package stage1\n"), 0600); err != nil {
		t.Fatal(err)
	}
	second := h.project()
	if model.S(first["binding"]) == model.S(second["binding"]) {
		t.Fatal("source refresh must produce a new binding")
	}
	verified := h.run("farm-verify", object{"projection_path": second["path"], "phase": "canary"})
	if model.S(verified["binding"]) != model.S(second["binding"]) {
		t.Fatalf("verification selected stale binding: %v", verified)
	}
}

func TestFarmProjectionReauthorizationOfCurrentSourceIsDeterministic(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	first := h.project()
	second := h.project()
	if model.S(first["binding"]) == model.S(second["binding"]) {
		t.Fatal("fresh reauthorization must retain its distinct immutable receipt")
	}
	verified := h.run("farm-verify", object{"projection_path": second["path"], "phase": "canary"})
	want := model.S(first["binding"])
	if candidate := model.S(second["binding"]); candidate < want {
		want = candidate
	}
	if model.S(verified["binding"]) != want {
		t.Fatalf("equivalent current bindings were not selected deterministically: %v", verified)
	}
}

func TestFarmAuthorizationRequiresTypedExitField(t *testing.T) {
	h := newFarmHarness(t)
	h.createPairExpectedExit(7)
	projection := h.projection()
	_, base, err := farmBase(projection)
	if err != nil {
		t.Fatal(err)
	}
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	input := model.S(h.run("snapshot", object{"artifact_id": plan.ID()})["sha256"])
	task := plan.Symbols.ByID["T-001"].Value
	definition := model.M(model.A(task["verification"])[0])
	definitionHash, _ := canonical.Hash(definition)
	row := object{
		"source_task": "T-001", "farm_task": "t-001", "test_path": "src/stage1.go",
		"definition_sha256": definitionHash, "command": "go test ./... -run TestEnvironmentOverrides",
		"stdout_sha256": canonical.BytesHash([]byte("fixture RED")), "stderr_sha256": canonical.BytesHash(nil),
		"unknown": "occupies the omitted exit slot",
	}
	payload := object{"format": "codearbiter.farm-authorization/0.1.0", "input_sha256": input, "spec_sha256": spec.NormHash(), "plan_sha256": plan.NormHash(), "scope": "CP-01", "base_sha256": base, "red_evidence": []any{row}}
	receipt := h.capture(plan.ID(), "CP-01", "farm_authorization", payload)
	_, err = h.request("farm-project", object{
		"artifact_id": plan.ID(), "operation_id": h.next(),
		"expected": object{"revision": plan.Revision(), "model_sha256": plan.Hash()},
		"scope":    "CP-01", "slice": []any{"T-001"}, "target": ".codearbiter/plans/example.plan.json",
		"projection": projection, "receipt": receipt,
	})
	if fault.Code(err) != "STALE_EVIDENCE" {
		t.Fatalf("expected omitted typed exit to fail closed, got %v", err)
	}
}

func TestFarmSealRejectsMatchingOpenShapeForgery(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	result := h.project()
	projectionPath := filepath.Join(h.root, filepath.FromSlash(model.S(result["path"])))
	projection := h.projection()
	model.M(projection["meta"])["model"] = "fixture/model"
	model.M(projection["meta"])["apiBaseUrl"] = "https://example.invalid/v1"
	b, _ := canonical.Marshal(projection)
	if err := os.WriteFile(projectionPath, append(b, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	sealed := h.run("farm-seal", object{"projection_path": result["path"], "provenance": object{"model": "fixture/model", "api_base_url": "https://example.invalid/v1", "selection_source": "canary", "origin": "synthetic selection fixture"}})
	forged := h.derived(model.S(sealed["seal"]))
	delete(forged, "origin")
	h.forge("farm-seals", forged)
	_, err := h.request("farm-verify", object{"projection_path": result["path"], "phase": "dispatch", "effective_model": "fixture/model", "effective_api_base_url": "https://example.invalid/v1"})
	if fault.Code(err) != "INVALID_OUTPUT" {
		t.Fatalf("expected open-shape matching seal to be rejected, got %v", err)
	}
}
