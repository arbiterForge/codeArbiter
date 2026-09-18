//go:build linux

package operations

import (
	"bytes"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type harness struct {
	t    *testing.T
	root string
	n    int
}

func newHarness(t *testing.T) *harness { t.Helper(); return &harness{t: t, root: testutil.Root(t)} }
func (h *harness) request(op string, r object) (any, error) {
	h.t.Helper()
	if r == nil {
		r = object{}
	}
	r["protocol"] = Protocol
	return Run(h.root, op, r)
}
func (h *harness) run(op string, r object) object {
	h.t.Helper()
	v, e := h.request(op, r)
	if e != nil {
		h.t.Fatalf("%s: %v", op, e)
	}
	m, ok := v.(map[string]any)
	if !ok {
		h.t.Fatalf("%s result %T", op, v)
	}
	return m
}
func (h *harness) next() string { h.n++; return fmt.Sprintf("fixture-op-%04d", h.n) }
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
func (h *harness) doc(id string) *model.Document {
	h.t.Helper()
	f, e := store.Open(h.root)
	if e != nil {
		h.t.Fatal(e)
	}
	defer f.Close()
	c, e := repository.Scan(f)
	if e != nil {
		h.t.Fatal(e)
	}
	r, e := c.Resolve(id)
	if e != nil {
		h.t.Fatal(e)
	}
	return r.Doc
}
func (h *harness) mut(op, id string, r object) object {
	h.t.Helper()
	d := h.doc(id)
	r["artifact_id"] = id
	r["operation_id"] = h.next()
	r["expected"] = object{"revision": d.Revision(), "model_sha256": d.Hash()}
	return h.run(op, r)
}
func (h *harness) createPair() {
	h.t.Helper()
	spec := testutil.Spec()
	n := model.M(spec["normative"])
	h.run("create", object{"operation_id": h.next(), "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n})
	s := h.doc("SPEC-EXAMPLE")
	plan := testutil.Plan(s)
	pn := model.M(plan["normative"])
	h.run("create", object{"operation_id": h.next(), "artifact_id": "PLAN-EXAMPLE", "kind": "plan", "slug": "example", "title": pn["title"], "summary": pn["summary"], "spec_id": s.ID(), "normative": pn})
}

// Events in these fixtures simulate host attestations. They are NOT approval
// records for this package or evidence that its upstream integration has run.
func (h *harness) receipt(d *model.Document, record, kind string, payload object) string {
	h.t.Helper()
	ak, verdict := "review_workflow", "passed"
	switch kind {
	case "approval", "farm_authorization":
		ak, verdict = "user_workflow", "approved"
	case "verification":
		ak = "verification_runner"
	case "prerequisite":
		verdict = "satisfied"
	case "reconciliation":
		verdict = "reconciled"
	}
	subject := object{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": record}
	event := object{"format": "codearbiter.workflow-event/0.1.0", "kind": kind, "authority_kind": ak, "subject": subject, "actor": "synthetic test fixture", "origin": "isolated test: " + h.next(), "verdict": verdict, "payload": payload, "source_text": "Synthetic workflow fixture, not an actual user or code-review approval."}
	eb, e := canonical.Marshal(event)
	if e != nil {
		h.t.Fatal(e)
	}
	eh := canonical.BytesHash(eb)
	sourcePath := authority.SourceRef(eh)
	sourceDir := filepath.Join(h.root, filepath.FromSlash(filepath.Dir(sourcePath)))
	if e = os.MkdirAll(sourceDir, 0700); e != nil {
		h.t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(h.root, filepath.FromSlash(sourcePath)), eb, 0600); e != nil {
		h.t.Fatal(e)
	}
	receipt := object{"format": "codearbiter.receipt/0.2.0", "kind": kind, "authority_kind": ak, "subject": subject, "event_sha256": eh, "authority_source_ref": sourcePath, "authority_source_sha256": eh}
	rb, e := canonical.Marshal(receipt)
	if e != nil {
		h.t.Fatal(e)
	}
	rh := canonical.BytesHash(rb)
	f, e := store.Open(h.root)
	if e != nil {
		h.t.Fatal(e)
	}
	defer f.Close()
	if e = f.PutEvent(eh, eb); e != nil {
		h.t.Fatal(e)
	}
	if e = f.PutReceipt(rh+".json", rb); e != nil {
		h.t.Fatal(e)
	}
	return authority.Ref(rh)
}

func TestLegacyReceiptIsInspectableButCannotConferAuthority(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	h.review("T-001")
	h.start("T-002")
	h.review("T-002")
	h.accept("CP-01")
	h.start("T-003")
	h.review("T-003")
	h.accept("CP-02")

	// Rewrite every referenced current receipt as its v0.1 equivalent to model
	// a real pre-upgrade artifact: legacy approvals, task verification/review,
	// and quality acceptance all remain attached to their workflow records.
	docs := []*model.Document{h.doc("SPEC-EXAMPLE"), h.doc("PLAN-EXAMPLE")}
	refs := map[string]bool{}
	var collect func(any)
	collect = func(v any) {
		switch value := v.(type) {
		case map[string]any:
			for _, child := range value {
				collect(child)
			}
		case []any:
			for _, child := range value {
				collect(child)
			}
		case string:
			if strings.HasPrefix(value, authority.Root+"/receipts/") {
				refs[value] = true
			}
		}
	}
	for _, d := range docs {
		collect(d.Data)
	}

	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	replacements := map[string]string{}
	legacyRefs := []string{}
	for ref := range refs {
		current, loadErr := authority.Load(f, ref)
		if loadErr != nil {
			t.Fatal(loadErr)
		}
		legacy := object{
			"format":         "codearbiter.receipt/0.1.0",
			"kind":           current.Data["kind"],
			"authority_kind": current.Data["authority_kind"],
			"subject":        current.Data["subject"],
			"event_sha256":   current.Data["event_sha256"],
		}
		legacyBytes, marshalErr := canonical.Marshal(legacy)
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		legacyHash := canonical.BytesHash(legacyBytes)
		legacyRef := authority.Ref(legacyHash)
		if err = f.PutReceipt(legacyHash+".json", legacyBytes); err != nil {
			t.Fatal(err)
		}
		replacements[ref] = legacyRef
		replacements[current.Hash] = legacyHash
		legacyRefs = append(legacyRefs, legacyRef)
	}
	f.Close()

	var replace func(any)
	replace = func(v any) {
		switch value := v.(type) {
		case map[string]any:
			for key, child := range value {
				if text, ok := child.(string); ok {
					if replacement, found := replacements[text]; found {
						value[key] = replacement
					}
				} else {
					replace(child)
				}
			}
		case []any:
			for index, child := range value {
				if text, ok := child.(string); ok {
					if replacement, found := replacements[text]; found {
						value[index] = replacement
					}
				} else {
					replace(child)
				}
			}
		}
	}
	for _, d := range docs {
		replace(d.Data)
		legacyDoc := testutil.Seal(t, d.Data)
		body, renderErr := render.Render(legacyDoc)
		if renderErr != nil {
			t.Fatal(renderErr)
		}
		dir := "specs"
		if d.Kind() == "plan" {
			dir = "plans"
		}
		if err = os.WriteFile(filepath.Join(h.root, ".codearbiter", dir, "example.html"), body, 0600); err != nil {
			t.Fatal(err)
		}
	}

	f, err = store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	for _, ref := range legacyRefs {
		if _, err = authority.Inspect(f, ref); err != nil {
			t.Fatalf("legacy receipt is not inspectable: %v", err)
		}
		if _, err = authority.Load(f, ref); fault.Code(err) != "AUTHORITY_UNVERIFIED" || !strings.Contains(err.Error(), "fresh policy-owned attestation") {
			t.Fatalf("legacy receipt conferred authority or lacked upgrade guidance: %v", err)
		}
	}
	if _, err = authority.Approved(f, h.doc("SPEC-EXAMPLE")); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("legacy approval conferred current authority: %v", err)
	}
	if _, err = evidence.Snapshot(f, h.doc("PLAN-EXAMPLE")); err != nil {
		t.Fatalf("legacy receipt prevented evidence snapshot: %v", err)
	}
	f.Close()

	if _, err = h.request("eligible", object{"artifact_id": "PLAN-EXAMPLE"}); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("legacy workflow remained dispatchable: %v", err)
	}
	spec := h.doc("SPEC-EXAMPLE")
	h.mut("approve", spec.ID(), object{"receipt": h.receipt(spec, spec.ID(), "approval", object{})})
	plan := h.doc("PLAN-EXAMPLE")
	h.mut("approve", plan.ID(), object{"receipt": h.receipt(plan, plan.ID(), "approval", object{})})

	// The tasks were accepted before upgrade. Fresh v0.2 reviews and quality
	// evidence replace their authority without deleting any v0.1 history.
	h.review("T-001")
	h.review("T-002")
	h.accept("CP-01")
	h.review("T-003")
	h.accept("CP-02")
	if result := h.run("eligible", object{"artifact_id": "PLAN-EXAMPLE"}); result["all_accepted_and_current"] != true {
		t.Fatalf("fresh attestation did not restore current acceptance: %v", result)
	}
	if ticket := h.context("T-001", 65536); len(ticket) != 64 {
		t.Fatalf("freshly attested workflow did not restore contextual reads: %q", ticket)
	}
	for _, ref := range legacyRefs {
		if _, err = os.Stat(filepath.Join(h.root, filepath.FromSlash(ref))); err != nil {
			t.Fatalf("legacy receipt was not preserved: %v", err)
		}
	}
}
func (h *harness) approvePair() {
	h.t.Helper()
	s := h.doc("SPEC-EXAMPLE")
	sr := h.receipt(s, s.ID(), "approval", object{})
	h.mut("approve", s.ID(), object{"receipt": sr})
	h.mut("plan-bind", "PLAN-EXAMPLE", object{"spec_id": s.ID()})
	p := h.doc("PLAN-EXAMPLE")
	pr := h.receipt(p, p.ID(), "approval", object{})
	h.mut("approve", p.ID(), object{"receipt": pr})
}
func (h *harness) input() string {
	h.t.Helper()
	return model.S(h.run("snapshot", object{"artifact_id": "PLAN-EXAMPLE"})["sha256"])
}
func (h *harness) context(id string, budget int64) string {
	h.t.Helper()
	cursor := ""
	for i := 0; i < 200; i++ {
		r := object{"artifact_id": "PLAN-EXAMPLE", "symbol": id, "budget": budget}
		if cursor != "" {
			r["cursor"] = cursor
		}
		p := h.run("read", r)
		if p["context_complete"] == true {
			return model.S(p["context_ticket"])
		}
		cursor = model.S(p["next_cursor"])
		if cursor == "" {
			h.t.Fatal("no continuation")
		}
	}
	h.t.Fatal("too many pages")
	return ""
}
func (h *harness) start(id string) {
	h.t.Helper()
	ticket := h.context(id, 65536)
	h.mut("task-start", "PLAN-EXAMPLE", object{"task": id, "context_ticket": ticket})
}
func (h *harness) taskReceipts(id string) (string, string) {
	h.t.Helper()
	p := h.doc("PLAN-EXAMPLE")
	s := h.doc("SPEC-EXAMPLE")
	task := p.Symbols.ByID[id].Value
	th, _ := canonical.Hash(task)
	input := h.input()
	payload := object{"input_sha256": input, "spec_sha256": s.NormHash(), "task_sha256": th}
	results := empty()
	for _, v := range model.A(task["verification"]) {
		def := model.M(v)
		dh, _ := canonical.Hash(def)
		tests := empty()
		for _, name := range model.Strings(def["required_tests"]) {
			tests = append(tests, object{"name": name, "status": "pass"})
		}
		results = append(results, object{"definition_sha256": dh, "exit": int64(0), "tests": tests, "stdout_sha256": canonical.BytesHash([]byte("fixture PASS")), "stderr_sha256": canonical.BytesHash(nil)})
	}
	vp, _ := canonical.Clone(payload)
	vp["commands"] = results
	vr := h.receipt(p, id, "verification", vp)
	rp, _ := canonical.Clone(payload)
	rp["assessment"] = "Synthetic fixture checks specification compliance."
	rr := h.receipt(p, id, "spec_review", rp)
	return vr, rr
}
func (h *harness) review(id string) {
	h.t.Helper()
	vr, rr := h.taskReceipts(id)
	h.mut("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": vr, "review_receipt": rr})
}
func (h *harness) quality(scope string) string {
	h.t.Helper()
	p := h.doc("PLAN-EXAMPLE")
	s := h.doc("SPEC-EXAMPLE")
	hashes := object{}
	for _, id := range model.Strings(p.Symbols.ByID[scope].Value["tasks"]) {
		hashes[id], _ = canonical.Hash(p.Symbols.ByID[id].Value)
	}
	base := model.M(model.M(model.M(p.Data["execution"])["scopes"])[scope])
	return h.receipt(p, scope, "quality_review", object{"input_sha256": h.input(), "spec_sha256": s.NormHash(), "base_input_sha256": base["base_input_sha256"], "task_hashes": hashes, "assessment": "Synthetic combined-scope review fixture."})
}
func (h *harness) accept(scope string) {
	h.t.Helper()
	r := h.quality(scope)
	h.mut("accept-scope", "PLAN-EXAMPLE", object{"scope": scope, "receipt": r})
}
func TestArtifactLifecycle(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	if _, e := h.request("eligible", object{"artifact_id": "PLAN-EXAMPLE"}); e == nil {
		t.Fatal("draft dispatch admitted")
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
	result := h.run("eligible", object{"artifact_id": "PLAN-EXAMPLE"})
	if result["all_accepted_and_current"] != true {
		t.Fatal(result)
	}
	if h.doc("PLAN-EXAMPLE").NormHash() != before || h.input() != input {
		t.Fatal("progress invalidated normative/input identity")
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
func TestContextTicketRequired(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	d := h.doc("PLAN-EXAMPLE")
	_, e := h.request("task-start", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "context_ticket": "invented"})
	if fault.Code(e) != "INVALID_CURSOR" {
		t.Fatal(e)
	}
	// Knowing the public receipt format and hashing a plausible payload is not
	// enough: the engine must have written the corresponding delivery receipt.
	forged, err := canonical.Marshal(object{"format": "codearbiter.context-token/0.1.0", "artifact_id": d.ID(), "symbol": "T-001", "vector_sha256": strings.Repeat("0", 64), "manifest_sha256": strings.Repeat("0", 64), "budget": int64(65536), "offset": int64(1), "purpose": "context"})
	if err != nil {
		t.Fatal(err)
	}
	_, e = h.request("task-start", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "context_ticket": canonical.BytesHash(forged)})
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
		if _, e := h.request(op, r); fault.Code(e) != "RENDER_DRIFT" {
			t.Fatalf("%s: %v", op, e)
		}
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
func TestAllOperationSchemasClosed(t *testing.T) {
	for _, op := range Names() {
		s, e := RequestSchema(op)
		if e != nil {
			t.Fatal(e)
		}
		if s["additionalProperties"] != false {
			t.Fatal(op)
		}
		r := object{"protocol": Protocol, "unexpected": "x"}
		if CheckRequest(op, r) == nil {
			t.Fatal("unknown key", op)
		}
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
	if h.run("eligible", object{"artifact_id": "PLAN-EXAMPLE"})["all_accepted_and_current"] != true {
		t.Fatal("reverification required needless implementation")
	}
}
func TestMissingOrSkippedNamedTests(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.approvePair()
	h.start("T-001")
	vr, _ := h.taskReceipts("T-001")
	f, _ := store.Open(h.root)
	defer f.Close()
	r, e := authority.Load(f, vr)
	if e != nil {
		t.Fatal(e)
	}
	p := h.doc("PLAN-EXAMPLE")
	s := h.doc("SPEC-EXAMPLE")
	task := p.Symbols.ByID["T-001"].Value
	payload := r.Payload()
	model.M(model.A(payload["commands"])[0])["tests"] = empty()
	r.Event["payload"] = payload
	if e = evidence.TaskPayload(r, p, s, task, h.input()); fault.Code(e) != "MISSING_TEST" {
		t.Fatal(e)
	}
	model.M(model.A(payload["commands"])[0])["tests"] = []any{object{"name": "TestEnvironmentOverrides", "status": "skip"}}
	if e = evidence.TaskPayload(r, p, s, task, h.input()); fault.Code(e) != "FAILED_VERIFICATION" {
		t.Fatal(e)
	}
}
func TestUnknownVersionFailsClosed(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	p := filepath.Join(h.root, ".codearbiter/specs/example.html")
	b, _ := os.ReadFile(p)
	b = []byte(strings.ReplaceAll(string(b), `"schema_version": "`+model.SchemaVersion+`"`, `"schema_version": "99.0.0"`))
	os.WriteFile(p, b, 0644)
	if _, e := h.request("identity", object{"artifact_id": "SPEC-EXAMPLE"}); fault.Code(e) != "UNSUPPORTED_VERSION" {
		t.Fatal(e)
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
