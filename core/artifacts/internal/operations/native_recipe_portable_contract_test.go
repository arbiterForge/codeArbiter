//go:build linux || darwin || windows

package operations

// Existing exact contract assertions and only their required fixture helpers
// are shared by supported native platforms. These synthetic engine fixtures
// do not execute providers or confer real user/host approval. Linux-only mode,
// executable-bit and filesystem-specific tests remain in their original owner.
import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
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
	return captureObservedPromptFixture(
		h.t, h.root, d.ID(), record, kind, ak, verdict,
		"Synthetic workflow fixture, not an actual user or code-review approval: "+h.next(), payload,
	)
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

	if _, err = h.request("verification-status", object{"artifact_id": "PLAN-EXAMPLE"}); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("legacy evidence produced a current verification claim: %v", err)
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
	if result := h.run("verification-status", object{"artifact_id": "PLAN-EXAMPLE"}); result["all_accepted_and_current"] != true {
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

func migrationRequest(t *testing.T, h *harness) object {
	t.Helper()
	s := testutil.Seal(t, testutil.Spec())
	pn := model.M(testutil.Plan(s)["normative"])
	for _, kind := range []string{"spec", "plan"} {
		dir := filepath.Join(h.root, ".codearbiter", kind+"s")
		if e := os.MkdirAll(dir, 0755); e != nil {
			t.Fatal(e)
		}
		if e := os.WriteFile(filepath.Join(dir, "example.md"), []byte("# Legacy\nStatus: approved\nHistoric behavior\n"), 0644); e != nil {
			t.Fatal(e)
		}
	}
	mapping := func(target string) []any {
		return []any{object{"start_line": int64(1), "end_line": int64(3), "target": target, "disposition": "mapped", "reason": "Synthetic reviewed fixture mapping, not actual production migration."}}
	}
	return object{"spec": object{"source_path": ".codearbiter/specs/example.md", "artifact_id": s.ID(), "slug": "example", "normative": s.Norm(), "mappings": mapping("INTENT-01")}, "plan": object{"source_path": ".codearbiter/plans/example.md", "artifact_id": "PLAN-EXAMPLE", "slug": "example", "normative": pn, "mappings": mapping("T-001")}}
}

func TestMigrationPairAndRollback(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	preview := h.run("migration-preview", r)
	if _, e := os.Stat(filepath.Join(h.root, ".codearbiter/specs/example.html")); !os.IsNotExist(e) {
		t.Fatal("preview wrote a canonical artifact")
	}
	r["preview_sha256"] = preview["preview_sha256"]
	r["operation_id"] = "cutover-fixture-001"
	r["review"] = object{"actor": "test fixture", "origin": "unit test", "source_text": "Synthetic explicit mapping approval; not implementation approval."}
	h.run("migration-apply", r)
	journalBytes, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/.artifacts/transactions/cutover-fixture-001.json"))
	if err != nil {
		t.Fatal(err)
	}
	var journal object
	if err := json.Unmarshal(journalBytes, &journal); err != nil || len(model.A(journal["entries"])) != 4 {
		t.Fatalf("pair cutover did not journal four edits: %v", err)
	}
	for _, kind := range []string{"spec", "plan"} {
		if _, e := os.Stat(filepath.Join(h.root, ".codearbiter", kind+"s/example.md")); !os.IsNotExist(e) {
			t.Fatal("two live authorities")
		}
	}
	if model.S(model.M(h.doc("SPEC-EXAMPLE").Data["governance"])["state"]) != "draft" {
		t.Fatal("legacy approval transferred")
	}
	if h.doc("PLAN-EXAMPLE").Norm()["spec_ref"] == nil {
		t.Fatal("lost binding")
	}
	if _, e := h.request("migration-rollback", object{"operation_id": "rollback-fixture-001", "cutover_operation_id": "cutover-fixture-001"}); e != nil {
		t.Fatal(e)
	}
	for _, kind := range []string{"spec", "plan"} {
		b, e := os.ReadFile(filepath.Join(h.root, ".codearbiter", kind+"s/example.md"))
		if e != nil || string(b) != "# Legacy\nStatus: approved\nHistoric behavior\n" {
			t.Fatal("legacy bytes not restored")
		}
	}
}

func TestReviewRetryPreservesMutationResult(t *testing.T) {
	h := newHarness(t)
	req := object{"operation_id": "review-replay-001", "artifact_id": "SPEC-REPLAY", "kind": "spec", "slug": "replay", "title": "Replay", "summary": "Retry creates no duplicate."}
	first := h.run("create", req)
	value, err := h.request("create", req)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(value)
	var second object
	if err = json.Unmarshal(raw, &second); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"artifact_id", "kind", "path", "model_sha256", "normative_sha256"} {
		if second[key] != first[key] {
			t.Errorf("retry lost %s: first=%v retry=%v", key, first[key], second[key])
		}
	}
	if _, ok := second["transaction"]; !ok {
		t.Error("retry changed response shape: transaction field absent")
	}
}

// N10:03 and N12:04 use the real public operations and existing observed
// fixture capture. Every authority event here is explicitly synthetic; these
// tests do not grant actual user/host authority or execute stored commands.
func receiptTransitionRequest(h *harness, fields object) object {
	h.t.Helper()
	d := h.doc("PLAN-EXAMPLE")
	fields["artifact_id"], fields["operation_id"] = d.ID(), h.next()
	fields["expected"] = object{"revision": d.Revision(), "model_sha256": d.Hash()}
	return fields
}

func receiptTransitionSource(t *testing.T, h *harness, record, kind string, payload object, authorityKind string) object {
	t.Helper()
	d := h.doc("PLAN-EXAMPLE")
	text := "Synthetic isolated receipt-transition fixture, not actual user approval: " + h.next()
	context := h.run("evidence-context", object{"artifact_id": d.ID(), "activity": kind, "record_id": record, "prompt_sha256": canonical.BytesHash([]byte(text))})
	verdict := "reconciled"
	if kind == "prerequisite" {
		verdict = "satisfied"
	}
	return observedSourceForContextFixture(t, h.root,
		object{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": record},
		kind, authorityKind, verdict, text, payload, context)
}

func receiptTransitionCapture(t *testing.T, h *harness, record, kind string, payload object) string {
	t.Helper()
	source := receiptTransitionSource(t, h, record, kind, payload, "user_workflow")
	return model.S(h.run("capture-observation", source)["receipt"])
}

func receiptTransitionRefuse(t *testing.T, h *harness, op string, request object, code string) {
	t.Helper()
	before := readModeTree(t, h.root)
	if _, err := h.request(op, request); fault.Code(err) != code {
		t.Fatalf("%s: expected %s without effects, got %v", op, code, err)
	}
	if !maps.Equal(before, readModeTree(t, h.root)) {
		t.Fatal("refused receipt operation changed owned source, canonical data or retained artifacts")
	}
}

func TestN10ScopeReconcileUpdatesBaselineAndPreservesEveryMemberHistory(t *testing.T) {
	for _, initial := range []string{"missing", "stale"} {
		t.Run(initial, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			h.approvePair()
			if initial == "stale" {
				h.start("T-001")
				h.review("T-001")
				h.start("T-002")
				h.review("T-002")
				// A real ordinary plan edit makes the old scope baseline stale;
				// a fresh synthetic approval restores only artifact authority.
				h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "T-003", "fields": object{"steps": model.List("A revised independent method.")}}}})
				p := h.doc("PLAN-EXAMPLE")
				h.mut("approve", p.ID(), object{"receipt": h.receipt(p, p.ID(), "approval", object{})})
			}
			before := h.doc("PLAN-EXAMPLE")
			oldBase := model.M(model.M(model.M(before.Data["execution"])["scopes"])["CP-01"])
			if initial == "missing" && oldBase != nil || initial == "stale" && (oldBase == nil || oldBase["plan_sha256"] == before.NormHash()) {
				t.Fatal("fixture did not reach the named missing/stale baseline boundary")
			}
			input := h.input()
			receipt := receiptTransitionCapture(t, h, "CP-01", "reconciliation", object{"input_sha256": input, "assessment": "Synthetic scope reconciliation of the exact current input."})
			retained := descriptorEffectSnapshot(t, h.root)
			request := receiptTransitionRequest(h, object{"scope": "CP-01", "receipt": receipt})
			staleWriter := receiptTransitionRequest(h, object{"scope": "CP-01", "receipt": receipt})
			h.run("scope-reconcile", request)
			after := h.doc(before.ID())
			base := model.M(model.M(model.M(after.Data["execution"])["scopes"])["CP-01"])
			if !equalValue(base, object{"base_input_sha256": input, "plan_sha256": before.NormHash()}) || after.Revision() != before.Revision()+1 {
				t.Fatalf("scope baseline was not replaced with the exact current identity: %v", base)
			}
			for _, id := range []string{"T-001", "T-002"} {
				want, err := canonical.Clone(state(before, id))
				if err != nil {
					t.Fatal(err)
				}
				want["evidence_refs"] = model.List(append(model.Strings(state(before, id)["evidence_refs"]), receipt)...)
				if !equalValue(want, state(after, id)) {
					t.Fatalf("scope member %s lost progress/history or the selected receipt", id)
				}
			}
			if !equalValue(before.Norm(), after.Norm()) || !equalValue(state(before, "T-003"), state(after, "T-003")) ||
				!equalValue(model.M(model.M(before.Data["execution"])["scopes"])["CP-02"], model.M(model.M(after.Data["execution"])["scopes"])["CP-02"]) {
				t.Fatal("scope reconciliation changed requirements or a different scope/member")
			}
			currentFiles := descriptorEffectSnapshot(t, h.root)
			for path, hash := range retained {
				if strings.HasPrefix(path, ".artifacts/") && currentFiles[path] != hash {
					t.Fatalf("scope reconciliation rewrote or removed retained evidence %s", path)
				}
			}
			settled := readModeTree(t, h.root)
			h.run("scope-reconcile", request)
			if !maps.Equal(settled, readModeTree(t, h.root)) {
				t.Fatal("exact replay duplicated a member receipt or journal effect")
			}
			receiptTransitionRefuse(t, h, "scope-reconcile", staleWriter, "REVISION_CONFLICT")
		})
	}
}

func TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites(t *testing.T) {
	for _, mismatch := range []string{"subject", "input", "definition", "changed-source", "empty-assessment", "authority"} {
		t.Run(mismatch, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			h.approvePair()
			subject := "CP-01"
			if mismatch == "subject" {
				subject = "CP-02"
			}
			payload := object{"input_sha256": h.input(), "assessment": "Synthetic current-scope assessment."}
			if mismatch == "empty-assessment" {
				payload["assessment"] = ""
			}
			authorityKind := "user_workflow"
			if mismatch == "authority" {
				authorityKind = "review_workflow"
			}
			source := receiptTransitionSource(t, h, subject, "reconciliation", payload, authorityKind)
			if mismatch == "empty-assessment" || mismatch == "authority" {
				code := "OBSERVATION_UNVERIFIED"
				if mismatch == "authority" {
					code = "AUTHORITY_UNVERIFIED"
				}
				receiptTransitionRefuse(t, h, "capture-observation", source, code)
				return
			}
			receipt := model.S(h.run("capture-observation", source)["receipt"])
			if mismatch == "input" {
				writeFixture(t, h.root, "src/stage1.go", []byte("Changed after the current scope reply.\n"))
			}
			if mismatch == "definition" {
				h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "CP-01", "fields": object{"exit": "A newly specified scope exit."}}}})
				p := h.doc("PLAN-EXAMPLE")
				h.mut("approve", p.ID(), object{"receipt": h.receipt(p, p.ID(), "approval", object{})})
			}
			code := "STALE_EVIDENCE"
			if mismatch == "changed-source" {
				// Preserve the original content-addressed name: the actual input
				// inventory must refuse changed authority bytes, not silently bless it.
				writeFixture(t, h.root, model.S(source["source_ref"]), []byte("{}"))
				code = "INVALID_OUTPUT"
			}
			receiptTransitionRefuse(t, h, "scope-reconcile", receiptTransitionRequest(h, object{"scope": "CP-01", "receipt": receipt}), code)
		})
	}
}

func receiptTransitionPrerequisiteFixture(t *testing.T) (*harness, *assistiveFixture) {
	t.Helper()
	h := newHarness(t)
	h.createPair()
	f := &assistiveFixture{t: t, root: h.root}
	addScopedPrerequisite(f, "fact")
	h.approvePair()
	return h, f
}

func TestN12ReceiptedPrerequisiteReplacesObservationWithoutLosingHistory(t *testing.T) {
	h, f := receiptTransitionPrerequisiteFixture(t)
	var priorReceipt string
	var priorBytes []byte
	for _, outcome := range []string{"unsatisfied", "unknown"} {
		f.mutate("prerequisite", prerequisiteReport(outcome, "tool_result"))
		before := h.doc("PLAN-EXAMPLE")
		if model.M(model.M(before.Data["execution"])["prerequisite_observations"])["GATE-LOCAL"] == nil {
			t.Fatal("fixture did not contain the ordinary observation to replace")
		}
		receiptTransitionRefuse(t, h, "verification-status", object{"artifact_id": before.ID()}, "AUTHORITY_UNVERIFIED")
		receipt := receiptTransitionCapture(t, h, "GATE-LOCAL", "prerequisite", object{"prerequisite": before.Symbols.ByID["GATE-LOCAL"].Value})
		request := receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": receipt})
		stale := receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": receipt})
		h.run("prerequisite", request)
		after := h.doc(before.ID())
		ex := model.M(after.Data["execution"])
		want := append(model.Strings(model.M(model.M(before.Data["execution"])["prerequisite_evidence"])["GATE-LOCAL"]), receipt)
		if _, present := model.M(ex["prerequisite_observations"])["GATE-LOCAL"]; present ||
			model.M(ex["prerequisites"])["GATE-LOCAL"] != "satisfied" ||
			!equalValue(model.M(ex["prerequisite_evidence"])["GATE-LOCAL"], model.List(want...)) {
			t.Fatal("receipted prerequisite did not delete only the observation, satisfy, and append exact retained history")
		}
		if !equalValue(before.Norm(), after.Norm()) || !equalValue(model.M(before.Data["execution"])["tasks"], ex["tasks"]) ||
			!equalValue(model.M(before.Data["execution"])["scopes"], ex["scopes"]) || after.Revision() != before.Revision()+1 {
			t.Fatal("prerequisite changed requirements, independent work, scope proof or revision incorrectly")
		}
		if priorReceipt != "" {
			currentBytes, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(priorReceipt)))
			if err != nil || string(currentBytes) != string(priorBytes) {
				t.Fatal("replacement rewrote or removed the previous receipt")
			}
		}
		priorReceipt = receipt
		var err error
		priorBytes, err = os.ReadFile(filepath.Join(h.root, filepath.FromSlash(receipt)))
		if err != nil {
			t.Fatal(err)
		}
		status := h.run("verification-status", object{"artifact_id": after.ID()})
		if status["all_accepted_and_current"] != false {
			t.Fatal("one prerequisite receipt became a whole-plan verification claim")
		}
		settled := readModeTree(t, h.root)
		h.run("prerequisite", request)
		if !maps.Equal(settled, readModeTree(t, h.root)) {
			t.Fatal("prerequisite replay appended the receipt twice or wrote another effect")
		}
		receiptTransitionRefuse(t, h, "prerequisite", stale, "REVISION_CONFLICT")
	}
}

func TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions(t *testing.T) {
	for _, mismatch := range []string{"subject", "definition", "changed-source", "authority", "missing-receipt-structural-refusal", "stale-consumer-receipt"} {
		t.Run(mismatch, func(t *testing.T) {
			h, f := receiptTransitionPrerequisiteFixture(t)
			if mismatch == "missing-receipt-structural-refusal" {
				// An incomplete historical claim must be refused by the writer;
				// do not serialize invalid canonical bytes to reach a later consumer.
				before := readModeTree(t, h.root)
				d := h.doc("PLAN-EXAMPLE")
				model.M(model.M(d.Data["execution"])["prerequisites"])["GATE-LOCAL"] = "satisfied"
				d.Data["revision"] = d.Revision() + 1
				if _, err := render.Prepare(d.Data); fault.Code(err) != "MISSING_EVIDENCE" {
					t.Fatalf("satisfied flag without receipt bypassed the structural writer guard: %v", err)
				}
				if !maps.Equal(before, readModeTree(t, h.root)) {
					t.Fatal("structural receipt refusal changed the owned tree")
				}
				return
			}
			if mismatch == "subject" {
				f.mutate("apply", object{"changes": []any{object{"op": "record.add", "collection": "prerequisites", "record": object{
					"id": "GATE-OTHER", "title": "Other local service", "kind": "fact", "requirement": "A separate bounded fact.", "task_refs": model.List("T-002"), "source_refs": empty(),
				}}}})
				p := h.doc("PLAN-EXAMPLE")
				h.mut("approve", p.ID(), object{"receipt": h.receipt(p, p.ID(), "approval", object{})})
			}
			f.mutate("prerequisite", prerequisiteReport("unknown", "tool_result"))
			subject := "GATE-LOCAL"
			if mismatch == "subject" {
				subject = "GATE-OTHER"
			}
			d := h.doc("PLAN-EXAMPLE")
			authorityKind := "user_workflow"
			if mismatch == "authority" {
				authorityKind = "review_workflow"
			}
			source := receiptTransitionSource(t, h, subject, "prerequisite", object{"prerequisite": d.Symbols.ByID[subject].Value}, authorityKind)
			if mismatch == "authority" {
				receiptTransitionRefuse(t, h, "capture-observation", source, "AUTHORITY_UNVERIFIED")
				return
			}
			receipt := model.S(h.run("capture-observation", source)["receipt"])
			if mismatch == "stale-consumer-receipt" {
				h.run("prerequisite", receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": receipt}))
			}
			if mismatch == "definition" || mismatch == "stale-consumer-receipt" {
				f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "GATE-LOCAL", "fields": object{"requirement": "A changed prerequisite definition."}}}})
				p := h.doc("PLAN-EXAMPLE")
				h.mut("approve", p.ID(), object{"receipt": h.receipt(p, p.ID(), "approval", object{})})
			}
			if mismatch == "stale-consumer-receipt" {
				receiptTransitionRefuse(t, h, "verification-status", object{"artifact_id": "PLAN-EXAMPLE"}, "STALE_EVIDENCE")
				return
			}
			code := "STALE_EVIDENCE"
			if mismatch == "changed-source" {
				writeFixture(t, h.root, model.S(source["source_ref"]), []byte("{}"))
				code = "INVALID_OUTPUT"
			}
			receiptTransitionRefuse(t, h, "prerequisite", receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": receipt}), code)
		})
	}
}
