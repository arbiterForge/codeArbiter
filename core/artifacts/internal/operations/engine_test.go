//go:build linux

package operations

import (
	"bytes"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	reads "github.com/arbiterForge/codeArbiter/core/artifacts/internal/read"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func (h *harness) authoritySource(event object) object {
	h.t.Helper()
	b, err := canonical.Marshal(event)
	if err != nil {
		h.t.Fatal(err)
	}
	digest := canonical.BytesHash(b)
	dir := filepath.Join(h.root, ".codearbiter", ".artifacts", "authority-sources")
	if err = os.MkdirAll(dir, 0700); err != nil {
		h.t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(dir, digest+".json"), b, 0600); err != nil {
		h.t.Fatal(err)
	}
	return object{
		"source_ref":    ".codearbiter/.artifacts/authority-sources/" + digest + ".json",
		"source_sha256": digest,
	}
}

func (h *harness) immutableJSON(subdir string, value object) (string, string) {
	h.t.Helper()
	b, err := canonical.Marshal(value)
	if err != nil {
		h.t.Fatal(err)
	}
	digest := canonical.BytesHash(b)
	dir := filepath.Join(h.root, ".codearbiter", ".artifacts", subdir)
	if err = os.MkdirAll(dir, 0700); err != nil {
		h.t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(dir, digest+".json"), b, 0600); err != nil {
		h.t.Fatal(err)
	}
	return ".codearbiter/.artifacts/" + subdir + "/" + digest + ".json", digest
}

// Events in these fixtures simulate host attestations. They are NOT approval
// records for this package or evidence that its upstream integration has run.

func TestObservedCaptureBindsEngineContextObservationAndPayload(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	contextResult := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "verification", "record_id": "T-001"})
	contextRef, contextHash := model.S(contextResult["context_ref"]), model.S(contextResult["context_sha256"])
	contextBytes, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(contextRef)))
	if err != nil {
		t.Fatal(err)
	}
	context, err := canonical.Object(contextBytes)
	if err != nil {
		t.Fatal(err)
	}
	commands := empty()
	for _, value := range model.A(context["commands"]) {
		definition := model.M(value)
		commands = append(commands, object{
			"definition_sha256": definition["definition_sha256"], "exit": int64(0),
			"tests":         []any{object{"name": "TestEnvironmentOverrides", "status": "pass"}},
			"stdout_sha256": canonical.BytesHash(nil), "stderr_sha256": canonical.BytesHash(nil),
		})
	}
	payload := object{"input_sha256": context["input_sha256"], "spec_sha256": context["spec_sha256"], "task_sha256": context["task_sha256"], "commands": commands}
	payloadHash, _ := canonical.Hash(payload)
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	workspaceRoot := filepath.Dir(executable)
	workspace := object{"root": workspaceRoot, "filesystem_id": "fixture:workspace", "git_common_dir": workspaceRoot, "git_common_filesystem_id": "fixture:git", "head": "fixture-head", "status_sha256": canonical.BytesHash([]byte("clean")), "content_sha256": canonical.BytesHash([]byte("content"))}
	producerResult := object{
		"environment_sha256": canonical.BytesHash([]byte("fixture environment")),
		"command_bindings":   []any{object{"definition_sha256": model.M(model.A(context["commands"])[0])["definition_sha256"], "argv": []any{executable, "test", "./...", "-run", "TestEnvironmentOverrides"}, "cwd": workspaceRoot, "cwd_filesystem_id": "fixture:cwd", "workspace_root": workspaceRoot, "workspace_filesystem_id": "fixture:workspace", "git_common_dir": workspaceRoot, "git_common_filesystem_id": "fixture:git", "executable_sha256": canonical.BytesHash([]byte("fixture executable"))}},
		"workspace_before":   []any{workspace}, "workspace_after": []any{workspace}, "commands": commands,
	}
	producerResultHash, _ := canonical.Hash(producerResult)
	observed := object{
		"format": "codearbiter.observation/0.2.0", "kind": "verification", "subject": context["subject"],
		"context_ref": contextRef, "context_sha256": contextHash, "payload_sha256": payloadHash,
		"producer_profile": "declared-command/0.1.0", "producer_run_id": "fixture-run-0001", "producer_result_sha256": producerResultHash, "producer_result": producerResult,
	}
	observationRef, observationHash := h.immutableJSON("observations", observed)
	event := object{
		"format": "codearbiter.workflow-event/0.2.0", "kind": "verification", "authority_kind": "verification_runner",
		"subject": context["subject"], "actor": "qualified fixture producer", "origin": "fixture-run-0001", "verdict": "passed",
		"payload": payload, "source_text": "Observed fixture command completion.",
		"observation_ref": observationRef, "observation_sha256": observationHash,
	}
	source := h.authoritySource(event)
	result := h.run("capture-observation", source)
	if model.S(result["receipt"]) == "" {
		t.Fatal("observed capture did not produce a receipt")
	}
	replayed := h.run("capture-observation", source)
	if replayed["receipt"] != result["receipt"] {
		t.Fatal("observed capture is not idempotent")
	}
	if _, err = h.request("capture", source); fault.Code(err) != "OBSERVATION_REQUIRED" {
		t.Fatalf("observed event entered legacy capture path: %v", err)
	}
	legacyPayload := object{"input_sha256": context["input_sha256"], "spec_sha256": context["spec_sha256"], "task_sha256": context["task_sha256"], "commands": commands}
	legacyEvent := object{
		"format": "codearbiter.workflow-event/0.1.0", "kind": "verification", "authority_kind": "verification_runner",
		"subject": context["subject"], "actor": "synthetic legacy fixture", "origin": "fixture-run-legacy", "verdict": "passed",
		"payload": legacyPayload, "source_text": "Legacy fixture command completion.",
	}
	legacySource := h.authoritySource(legacyEvent)
	if _, err = h.request("capture-observation", legacySource); fault.Code(err) != "OBSERVATION_REQUIRED" {
		t.Fatalf("legacy synthetic event entered observed capture path: %v", err)
	}
}

func TestArtifactLifecycle(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	if report := h.run("eligible", object{"artifact_id": "PLAN-EXAMPLE"}); report["next_task"] != "T-001" || report["evidence_assessed"] != false {
		t.Fatalf("draft scheduling must be advisory: %v", report)
	}
	h.approvePair()
	before := h.doc("PLAN-EXAMPLE").NormHash()
	input := h.input()
	h.start("T-001")
	h.review("T-001")
	eligible := h.run("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if eligible["next_task"] != "T-002" {
		t.Fatal(eligible)
	}
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	if model.S(state(h.doc("PLAN-EXAMPLE"), "T-001")["state"]) != "ACCEPTED" {
		t.Fatal("scope not accepted")
	}
	h.start("T-003")
	h.review("T-003")
	h.accept("CP-02")
	result := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
	if result["all_accepted_and_current"] != true {
		t.Fatal(result)
	}
	if h.doc("PLAN-EXAMPLE").NormHash() != before || h.input() != input {
		t.Fatal("progress invalidated normative/input identity")
	}
}
func TestDraftSourceRefreshPreservesHistoricalEvidence(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	h.review("T-001")
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	h.mut("task-block", "PLAN-EXAMPLE", object{"task": "T-003", "reason": "User stopped the remaining task."})
	before, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	approvals := model.M(before.Data["governance"])["approvals"]
	if len(model.A(approvals)) == 0 || len(model.A(state(before, "T-001")["evidence_refs"])) == 0 ||
		len(model.M(model.M(before.Data["execution"])["scopes"])) == 0 {
		t.Fatal("fixture lacks historical approval, task evidence or scope evidence")
	}
	h.mut("plan-bind", before.ID(), object{
		"spec_id": spec.ID(), "binding_mode": "draft_preview",
		"spec_expected": object{"revision": spec.Revision(), "model_sha256": spec.Hash()},
	})
	after := h.doc(before.ID())
	if !equalValue(before.Data["execution"], after.Data["execution"]) ||
		!equalValue(approvals, model.M(after.Data["governance"])["approvals"]) || h.doc(spec.ID()).Hash() != spec.Hash() {
		t.Fatal("ordinary draft refresh rewrote existing history or the source specification")
	}
	if model.M(after.Data["governance"])["state"] != "draft" ||
		model.M(after.Norm()["spec_ref"])["binding_mode"] != "draft_preview" {
		t.Fatal("draft refresh asserted current approval")
	}
	if _, err := h.request("verification-status", object{"artifact_id": after.ID()}); fault.Code(err) != "DRAFT_BINDING" {
		t.Fatalf("historical records became current acceptance after refresh: %v", err)
	}
}

func TestOptionalOffsetsDefaultToZero(t *testing.T) {
	h := newHarness(t)
	h.createPair()

	outline := h.run("outline", object{"artifact_id": "SPEC-EXAMPLE", "budget": int64(4096)})
	if model.I(outline["offset"]) != 0 {
		t.Fatalf("outline without an offset did not start at zero: %v", outline["offset"])
	}
	index := h.run("index", object{"budget": int64(4096)})
	if model.I(index["offset"]) != 0 {
		t.Fatalf("index without an offset did not start at zero: %v", index["offset"])
	}
}
func TestTaskAcceptanceEvidence(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	vr, rr := h.taskReceipts("T-001")
	os.WriteFile(filepath.Join(h.root, "dirty.txt"), []byte("source changed without commit"), 0600)
	d := h.doc("PLAN-EXAMPLE")
	_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": vr, "review_receipt": rr})
	if fault.Code(err) != "STALE_EVIDENCE" {
		t.Fatal(err)
	}
	h.review("T-001")
	q := h.quality("CP-01")
	d = h.doc("PLAN-EXAMPLE")
	_, err = h.request("accept-scope", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "scope": "CP-01", "receipt": q})
	if fault.Code(err) != "SCOPE_NOT_READY" {
		t.Fatal(err)
	}
	if model.S(state(h.doc("PLAN-EXAMPLE"), "T-001")["state"]) != "REVIEW" {
		t.Fatal("partial scope acceptance")
	}
}

// legacyEngine makes the engine emit the historical 0.1.0 manifest format until
// the returned restore func runs, so receipts can be produced by the real
// capture flow and bound to a 0.1.0 identity.
func legacyEngine(t *testing.T) func() {
	t.Helper()
	current := evidence.ManifestFormat
	evidence.ManifestFormat = "codearbiter.verification-inputs/0.1.0"
	restored := false
	restore := func() {
		if !restored {
			evidence.ManifestFormat = current
			restored = true
		}
	}
	t.Cleanup(restore)
	return restore
}

func TestEligibleReadsLegacyManifestAsStale(t *testing.T) {
	// Receipts bound to a 0.1.0 identity make the task review stale, not invalid.
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	restore := legacyEngine(t)
	legacyInput := h.input()
	vr, rr := h.taskReceipts("T-001")
	restore()
	if h.input() == legacyInput {
		t.Fatal("0.1.0 and 0.2.0 manifests produced the same input identity")
	}
	d := h.doc("PLAN-EXAMPLE")
	_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": vr, "review_receipt": rr})
	if fault.Code(err) != "STALE_EVIDENCE" {
		t.Fatalf("0.1.0 receipts were not read as stale evidence: %v", err)
	}

	// An accepted plan whose receipts are 0.1.0 reports non-current evidence.
	h = newHarness(t)
	h.createPair()
	h.approvePair()
	restore = legacyEngine(t)
	h.start("T-001")
	h.review("T-001")
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	h.start("T-003")
	h.review("T-003")
	h.accept("CP-02")
	control := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
	if control["all_accepted_and_current"] != true {
		t.Fatalf("legacy-engine control must be current under its own format: %v", control)
	}
	restore()
	result, err := h.request("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})
	if err != nil {
		t.Fatalf("0.1.0 evidence raised an error instead of reading as stale: %v", err)
	}
	report := model.M(result)
	if report["all_accepted_and_current"] != false {
		t.Fatalf("0.1.0 evidence reported current: %v", report)
	}
	for _, v := range model.A(report["tasks"]) {
		row := model.M(v)
		if row["state"] == "ACCEPTED" && row["current_evidence"] != false {
			t.Fatalf("accepted task with 0.1.0 evidence reported current: %v", row)
		}
	}
}

func TestReadContextBounded(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	page := h.run("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(4096)})
	if page["context_complete"] == true {
		t.Fatal("expected multi-page context")
	}
	cursor := model.S(page["next_cursor"])
	if cursor == "" {
		t.Fatal("no cursor")
	}
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"summary": "A changed source definition."}}}})
	_, err := h.request("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(4096), "cursor": cursor})
	if fault.Code(err) != "STALE_CURSOR" {
		t.Fatal(err)
	}
}
func TestContextDeliveryRejectsInventedReceipts(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	d := h.doc("PLAN-EXAMPLE")
	fs, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	catalog, err := repository.Scan(fs)
	if err != nil {
		t.Fatal(err)
	}
	e := reads.CheckTicket(fs, catalog, d, "T-001", "invented")
	if fault.Code(e) != "INVALID_CURSOR" {
		t.Fatal(e)
	}
	// Knowing the public receipt format and hashing a plausible payload is not
	// enough: the engine must have written the corresponding delivery receipt.
	forged, err := canonical.Marshal(object{"format": "codearbiter.context-token/0.1.0", "artifact_id": d.ID(), "symbol": "T-001", "vector_sha256": strings.Repeat("0", 64), "manifest_sha256": strings.Repeat("0", 64), "budget": int64(65536), "offset": int64(1), "purpose": "context"})
	if err != nil {
		t.Fatal(err)
	}
	e = reads.CheckTicket(fs, catalog, d, "T-001", canonical.BytesHash(forged))
	if fault.Code(e) != "INVALID_CURSOR" {
		t.Fatal(e)
	}
}

func TestContextUsesContentAddressedCooperativeReceipts(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	ticket := h.context("T-001", 65536)
	if len(ticket) != 64 {
		t.Fatalf("context ticket is not a sha256 digest: %q", ticket)
	}
	if _, err := os.Stat(filepath.Join(h.root, ".codearbiter/.artifacts/context-key")); !os.IsNotExist(err) {
		t.Fatalf("repository-local context secret exists: %v", err)
	}
	b, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/.artifacts/context-tokens", ticket+".json"))
	if err != nil {
		t.Fatal(err)
	}
	if canonical.BytesHash(b) != ticket {
		t.Fatal("context receipt filename does not match its bytes")
	}
}
func TestGenericMutationCannotApprove(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	before := h.doc("SPEC-EXAMPLE").Hash()
	d := h.doc("SPEC-EXAMPLE")
	_, e := h.request("apply", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "changes": []any{object{"op": "header.update", "fields": object{"governance": object{"state": "approved"}}}}})
	if e == nil {
		t.Fatal("generic approval accepted")
	}
	if before != h.doc(d.ID()).Hash() {
		t.Fatal("failed mutation changed artifact")
	}
}

func TestCallerAuthorityLabelsCannotWidenWorkflowAuthority(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	d := h.doc("PLAN-EXAMPLE")
	tests := []struct {
		name          string
		kind          string
		authorityKind string
		verdict       string
	}{
		{"runner cannot satisfy prerequisite", "prerequisite", "verification_runner", "satisfied"},
		{"reviewer cannot reconcile task state", "reconciliation", "review_workflow", "reconciled"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			event := object{
				"format":         "codearbiter.workflow-event/0.1.0",
				"kind":           tc.kind,
				"authority_kind": tc.authorityKind,
				"subject": object{
					"artifact_id":      d.ID(),
					"normative_sha256": d.NormHash(),
					"record_id":        "T-001",
				},
				"actor":       "caller supplied label",
				"origin":      "untrusted request field",
				"verdict":     tc.verdict,
				"payload":     object{},
				"source_text": "A caller label is not workflow authority.",
			}
			if _, err := h.request("capture", h.authoritySource(event)); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
				t.Fatalf("caller authority label was accepted: %v", err)
			}
		})
	}
}
func TestSymbolRetirement(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.retire", "symbol": "AC-001", "reason": "Draft contract replaced by reviewed follow-up."}}})
	d := h.doc("SPEC-EXAMPLE")
	for _, id := range []string{"AC-001", "SCN-AC-001", "VER-AC-001"} {
		if !d.Symbols.ByID[id].Retired {
			t.Fatal("missing tombstone", id)
		}
	}
	_, e := h.request("apply", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "changes": []any{object{"op": "record.add", "collection": "criteria", "record": testutil.Criterion("AC-001")}}})
	if fault.Code(e) != "DUPLICATE_ID" {
		t.Fatal(e)
	}
}
func TestRenderDriftRejectedByEveryRead(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	p := filepath.Join(h.root, ".codearbiter/specs/example.html")
	b, _ := os.ReadFile(p)
	b = bytes.Replace(b, []byte("Configuration precedence"), []byte("Misleading replacement"), 1)
	os.WriteFile(p, b, 0644)
	for _, op := range []string{"identity", "outline", "read", "validate"} {
		r := object{"artifact_id": "SPEC-EXAMPLE"}
		if op == "read" {
			r["symbol"] = "AC-001"
		}
		if _, e := h.request(op, r); fault.Code(e) != "RENDER_DRIFT" || fault.Public(e).Field != ".codearbiter/specs/example.html" {
			t.Fatalf("%s: damaged artifact path missing from drift diagnostic: %v", op, fault.Public(e))
		}
	}
	if _, e := h.request("identity", object{"artifact_id": "PLAN-EXAMPLE"}); fault.Code(e) != "RENDER_DRIFT" || fault.Public(e).Field != ".codearbiter/specs/example.html" {
		t.Fatalf("unrelated read should identify the damaged artifact: %v", fault.Public(e))
	}
	preview := h.run("repair-preview", object{"path": ".codearbiter/specs/example.html"})
	h.run("repair-apply", object{"operation_id": h.next(), "path": preview["path"], "expected_bytes_sha256": preview["expected_bytes_sha256"], "preview_sha256": preview["preview_sha256"]})
	h.doc("SPEC-EXAMPLE")
}
func TestInputManifestIncludesPolicyAndMembership(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	first := h.input()
	os.WriteFile(filepath.Join(h.root, ".codearbiter/security-controls.md"), []byte("policy"), 0600)
	if h.input() == first {
		t.Fatal("governance file excluded")
	}
	second := h.input()
	os.Mkdir(filepath.Join(h.root, "src"), 0755)
	os.WriteFile(filepath.Join(h.root, "src/code.go"), []byte("one"), 0644)
	third := h.input()
	if third == second {
		t.Fatal("directory membership ignored")
	}
	info, _ := os.Stat(filepath.Join(h.root, "src/code.go"))
	os.WriteFile(filepath.Join(h.root, "src/code.go"), []byte("two"), 0644)
	os.Chtimes(filepath.Join(h.root, "src/code.go"), info.ModTime(), info.ModTime())
	if h.input() == third {
		t.Fatal("same-size same-mtime change ignored")
	}
}
func TestNoAuthorityFromHTMLFlag(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	d := h.doc("SPEC-EXAMPLE")
	model.M(d.Data["governance"])["state"] = "approved"
	d = testutil.Seal(t, d.Data)
	b, _ := render.Render(d)
	os.WriteFile(filepath.Join(h.root, ".codearbiter/specs/example.html"), b, 0644)
	out := h.run("identity", object{"artifact_id": d.ID()})
	if model.M(out["authority"])["authority_verified"] != false {
		t.Fatal("approved flag was trusted")
	}
}
func TestStoredCommandIsInert(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	p := h.doc("PLAN-EXAMPLE")
	command := model.M(model.A(p.Symbols.ByID["T-001"].Value["verification"])[0])
	command["argv"] = model.List("sh", "-c", "touch SHOULD_NOT_EXIST")
	p = testutil.Seal(t, p.Data)
	b, _ := render.Render(p)
	os.WriteFile(filepath.Join(h.root, ".codearbiter/plans/example.html"), b, 0644)
	h.run("read", object{"artifact_id": p.ID(), "symbol": "T-001", "mode": "exact"})
	if _, e := os.Stat(filepath.Join(h.root, "SHOULD_NOT_EXIST")); !os.IsNotExist(e) {
		t.Fatal("command executed")
	}
}
func TestPostSourceChangeRevalidation(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	h.review("T-001")
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	h.start("T-003")
	os.WriteFile(filepath.Join(h.root, "later-source.go"), []byte("later implementation"), 0600)
	h.review("T-003")
	h.review("T-001")
	h.review("T-002")
	h.accept("CP-01")
	h.accept("CP-02")
	if h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"})["all_accepted_and_current"] != true {
		t.Fatal("reverification required needless implementation")
	}
}

func TestRebrandAndStandaloneExport(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	before := h.doc("SPEC-EXAMPLE").NormHash()
	svg := []byte(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><rect width="100" height="20" fill="#334455"/></svg>`)
	if err := os.MkdirAll(filepath.Join(h.root, "brand"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(h.root, "brand/logo.svg"), svg, 0600); err != nil {
		t.Fatal(err)
	}
	h.mut("rebrand", "SPEC-EXAMPLE", object{"name": "Repository Brand", "logo_path": "brand/logo.svg", "mime": "image/svg+xml"})
	d := h.doc("SPEC-EXAMPLE")
	if d.NormHash() != before || model.S(model.M(d.Data["presentation"])["brand_name"]) != "Repository Brand" {
		t.Fatal("branding changed contract or failed to apply")
	}
	result := h.run("export", object{"artifact_id": d.ID(), "operation_id": h.next(), "model_sha256": d.Hash(), "target": ".codearbiter/exports/example.html"})
	if result["canonical"] != false || result["standalone"] != true {
		t.Fatal(result)
	}
	b, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/exports/example.html"))
	if err != nil {
		t.Fatal(err)
	}
	exported, err := render.Parse(b)
	if err != nil || exported.NormHash() != before {
		t.Fatal("export is not a valid standalone rendering", err)
	}
	if _, err := h.request("export", object{"artifact_id": d.ID(), "operation_id": h.next(), "model_sha256": d.Hash(), "target": "../../outside.html"}); err == nil {
		t.Fatal("escaped export admitted")
	}
}

func TestExplicitFileInputRootTracksExecutableBit(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	p := filepath.Join(h.root, "input.go")
	if err := os.WriteFile(p, []byte("package fixture\n"), 0600); err != nil {
		t.Fatal(err)
	}
	h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"verification_inputs": object{"roots": model.List("input.go"), "exclude_directories": empty()}}}}})
	one := h.input()
	if err := os.Chmod(p, 0700); err != nil {
		t.Fatal(err)
	}
	if one == h.input() {
		t.Fatal("explicit input executable change not captured")
	}
}
