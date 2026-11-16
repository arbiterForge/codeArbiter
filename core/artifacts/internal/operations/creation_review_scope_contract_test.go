//go:build linux || darwin || windows

package operations

// These characterizations call the actual in-process owners. Any approval,
// verification or review receipt is an explicitly synthetic existing fixture,
// never actual user/host approval or execution of a stored verification command.
import (
	"fmt"
	"maps"
	"os"
	"path/filepath"
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

func nativeThreeCreateRequest(t *testing.T, h *harness, kind string) object {
	t.Helper()
	id := map[string]string{"spec": "SPEC-CREATE", "plan": "PLAN-CREATE", "knowledge": "CTX-CREATE", "decomposition": "DECOMP-CREATE"}[kind]
	var n object
	if kind == "spec" {
		n = model.M(testutil.Spec()["normative"])
	} else if kind == "plan" {
		sn := model.M(testutil.Spec()["normative"])
		h.run("create", object{"operation_id": h.next(), "kind": "spec", "artifact_id": "SPEC-EXAMPLE", "slug": "example", "title": sn["title"], "summary": sn["summary"], "normative": sn})
		n = model.M(testutil.Plan(h.doc("SPEC-EXAMPLE"))["normative"])
	} else {
		n = model.M(testutil.Base(kind, id)["normative"])
		n["records"] = empty()
		if kind == "knowledge" {
			n["notes"] = empty()
		}
	}
	r := object{"operation_id": h.next(), "kind": kind, "artifact_id": id, "slug": "create", "title": n["title"], "summary": n["summary"], "normative": n}
	if kind == "plan" {
		r["spec_id"] = "SPEC-EXAMPLE"
	}
	return r
}

func TestN04CreateInitialTypedStateAndDuplicateRefusals(t *testing.T) {
	for _, kind := range []string{"spec", "plan", "knowledge", "decomposition"} {
		t.Run(kind, func(t *testing.T) {
			h := newHarness(t)
			r := nativeThreeCreateRequest(t, h, kind)
			wantNorm, err := canonical.Clone(model.M(r["normative"]))
			if err != nil {
				t.Fatal(err)
			}
			result := h.run("create", r)
			dir := map[string]string{"spec": "specs", "plan": "plans", "knowledge": "context", "decomposition": "decomposition"}[kind]
			path := ".codearbiter/" + dir + "/create.html"
			body, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(path)))
			if err != nil {
				t.Fatal(err)
			}
			d, err := render.Parse(body)
			if err != nil {
				t.Fatal(err)
			}
			wantHash, err := canonical.Hash(object{"format_version": model.FormatVersion, "kind": kind, "schema_version": model.SchemaVersion, "artifact_id": r["artifact_id"], "normative": wantNorm})
			if err != nil {
				t.Fatal(err)
			}
			if d.ID() != r["artifact_id"] || d.Kind() != kind || d.Revision() != 1 || d.Data["schema_version"] != model.SchemaVersion ||
				!equalValue(d.Norm(), wantNorm) || d.NormHash() != wantHash || result["path"] != path || result["model_sha256"] != d.Hash() {
				t.Fatal("public create did not persist the declared revision-one typed identity/normative checksum")
			}
			withoutIntegrity, err := canonical.Clone(d.Data)
			if err != nil {
				t.Fatal(err)
			}
			delete(withoutIntegrity, "integrity")
			modelHash, err := canonical.Hash(withoutIntegrity)
			if err != nil || modelHash != d.Hash() {
				t.Fatal("persisted model checksum does not bind its complete non-integrity data")
			}
			companion := ""
			if kind == "spec" {
				companion = "../plans/create.html"
			} else if kind == "plan" {
				companion = "../specs/example.html"
			}
			p := model.M(d.Data["presentation"])
			g := model.M(d.Data["governance"])
			if p["renderer"] != render.Version || p["stylesheet_sha256"] != canonical.BytesHash(render.CSS()) || p["companion_path"] != companion || model.S(p["logo_data_uri"]) == "" ||
				g["state"] != "draft" || len(model.A(g["approvals"])) != 0 || len(model.A(g["review_notes"])) != 0 {
				t.Fatal("initial presentation/checksum or draft governance differs from the create contract")
			}
			if kind == "plan" {
				for _, task := range model.A(wantNorm["tasks"]) {
					if !equalValue(state(d, model.S(model.M(task)["id"])), object{"state": "PENDING", "evidence_refs": empty(), "reason": nil}) {
						t.Fatal("new plan task did not begin PENDING with empty evidence and no reason")
					}
				}
				if len(model.M(model.M(d.Data["execution"])["scopes"])) != 0 || len(model.M(model.M(d.Data["execution"])["prerequisite_evidence"])) != 0 {
					t.Fatal("new plan manufactured scope/prerequisite evidence")
				}
			}
			(&assistiveFixture{t: t, root: h.root}).assertNoAuthorityFiles()
			settled := readModeTree(t, h.root)
			h.run("create", r)
			if !maps.Equal(settled, readModeTree(t, h.root)) {
				t.Fatal("same create operation replay changed the owned tree")
			}
			duplicate, _ := canonical.Clone(r)
			duplicate["operation_id"], duplicate["slug"] = h.next(), "another-path"
			receiptTransitionRefuse(t, h, "create", duplicate, "ALREADY_EXISTS")
			collision, _ := canonical.Clone(r)
			collision["operation_id"] = h.next()
			collision["artifact_id"] = map[string]string{"spec": "SPEC-OTHER", "plan": "PLAN-OTHER", "knowledge": "CTX-OTHER", "decomposition": "DECOMP-OTHER"}[kind]
			code := "ALREADY_EXISTS"
			if kind == "knowledge" || kind == "decomposition" {
				// These kinds bind ID to slug before a pathname can collide.
				code = "INVALID_ID"
			}
			receiptTransitionRefuse(t, h, "create", collision, code)
			for _, field := range []string{"kind", "schema_version"} {
				bad, _ := canonical.Clone(r)
				bad["operation_id"] = h.next()
				bad[field] = "unregistered-version"
				receiptTransitionRefuse(t, h, "create", bad, "INVALID_MODEL")
			}
		})
	}
}

func TestN04CreateCatalogBoundsRefuseBeforeWriting(t *testing.T) {
	t.Run("public-count", func(t *testing.T) {
		h := newHarness(t)
		h.createPair()
		// Literal valid rendered fixtures populate the real public catalog;
		// no catalog scanner, cap or public operation is replaced.
		for i := 0; i < repository.MaxArtifacts-2; i++ {
			v := testutil.Spec()
			v["artifact_id"], v["slug"] = fmt.Sprintf("SPEC-CAP-%04d", i), fmt.Sprintf("cap-%04d", i)
			body, err := render.Render(testutil.Seal(t, v))
			if err != nil {
				t.Fatal(err)
			}
			writeFixture(t, h.root, fmt.Sprintf(".codearbiter/specs/cap-%04d.html", i), body)
		}
		n := model.M(testutil.Spec()["normative"])
		r := object{"operation_id": h.next(), "kind": "spec", "artifact_id": "SPEC-CAP-OVERFLOW", "slug": "cap-overflow", "title": n["title"], "summary": n["summary"], "normative": n}
		receiptTransitionRefuse(t, h, "create", r, "MAX_ARTIFACTS")
		h.run("identity", object{"artifact_id": "SPEC-EXAMPLE"})
	})
	t.Run("save-byte-bound", func(t *testing.T) {
		h := newHarness(t)
		h.createPair()
		v := testutil.Spec()
		v["artifact_id"], v["slug"] = "SPEC-CAP-BYTES", "cap-bytes"
		d := testutil.Seal(t, v)
		body, err := render.Render(d)
		if err != nil {
			t.Fatal(err)
		}
		fs, err := store.Open(h.root)
		if err != nil {
			t.Fatal(err)
		}
		defer fs.Close()
		// Isolate the existing aggregate save guard without materializing
		// 64 MiB. This is a synthetic catalog total, not a public scan oracle.
		e := &Engine{FS: fs, RequestHash: canonical.BytesHash([]byte("synthetic byte-cap request")), Catalog: &repository.Catalog{BytesTotal: repository.MaxCatalogBytes - len(body) + 1}}
		before := readModeTree(t, h.root)
		_, err = e.save(object{"operation_id": h.next()}, repository.Entry{Path: ".codearbiter/specs/cap-bytes.html"}, d)
		if fault.Code(err) != "MAX_BYTES" || !maps.Equal(before, readModeTree(t, h.root)) {
			t.Fatalf("catalog byte-cap save did not refuse without any write: %v", err)
		}
	})
}

func nativeThreeReceiptedFixture(t *testing.T) (*harness, *assistiveFixture) {
	t.Helper()
	h := newHarness(t)
	h.createPair()
	f := &assistiveFixture{t: t, root: h.root}
	// Establish the current progress schema through real ordinary owners
	// BEFORE approval, so later stop/reconcile operations do not change the
	// normative schema identity while the desired receipt guard is exercised.
	f.mutate("task-block", object{"task": "T-001", "reason": "Owned fixture initialization."})
	f.mutate("task-reconcile", object{"task": "T-001", "state": "PENDING", "reason": "Owned fixture ready."})
	addScopedPrerequisite(f, "fact")
	h.approvePair()
	d := h.doc("PLAN-EXAMPLE")
	pr := receiptTransitionCapture(t, h, "GATE-LOCAL", "prerequisite", object{"prerequisite": d.Symbols.ByID["GATE-LOCAL"].Value})
	h.run("prerequisite", receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": pr}))
	return h, f
}

func TestN10ReceiptedReviewRetainsRefsAndScopeBaseline(t *testing.T) {
	for _, initial := range []string{"IN_PROGRESS", "REVIEW", "DONE", "ACCEPTED", "STALE"} {
		t.Run(initial, func(t *testing.T) {
			h, f := nativeThreeReceiptedFixture(t)
			h.start("T-001")
			if initial != "IN_PROGRESS" {
				h.review("T-001")
			}
			if initial == "DONE" || initial == "ACCEPTED" {
				h.start("T-002")
				h.review("T-002")
				if initial == "ACCEPTED" {
					h.accept("CP-01")
				} else {
					f.mutate("accept-scope", object{"scope": "CP-01", "reason": "Synthetic implementation report, not acceptance."})
				}
			}
			if initial == "STALE" {
				// Historical STALE is intentionally not manufactured by a new
				// runtime event. Retain all actual fixture receipts unchanged.
				d := h.doc("PLAN-EXAMPLE")
				state(d, "T-001")["state"], state(d, "T-001")["reason"] = "STALE", "Historical unresolved progress fixture."
				d.Data["revision"] = d.Revision() + 1
				d, err := render.Prepare(d.Data)
				if err != nil {
					t.Fatal(err)
				}
				body, err := render.Render(d)
				if err != nil {
					t.Fatal(err)
				}
				writeFixture(t, h.root, ".codearbiter/plans/example.html", body)
			}
			before := h.doc("PLAN-EXAMPLE")
			if state(before, "T-001")["state"] != initial {
				t.Fatal("named source state was not established")
			}
			input := h.input()
			vr, rr := h.taskReceipts("T-001")
			r := receiptTransitionRequest(h, object{"task": "T-001", "verification_receipt": vr, "review_receipt": rr})
			h.run("task-review", r)
			after := h.doc(before.ID())
			want, _ := canonical.Clone(state(before, "T-001"))
			want["state"], want["reason"] = "REVIEW", nil
			want["evidence_refs"] = model.List(append(model.Strings(state(before, "T-001")["evidence_refs"]), vr, rr)...)
			if !equalValue(want, state(after, "T-001")) || !equalValue(before.Norm(), after.Norm()) || after.Revision() != before.Revision()+1 {
				t.Fatal("receipted review lost old refs/state fields, exact pair append, or requirements")
			}
			oldBase := model.M(model.M(model.M(before.Data["execution"])["scopes"])["CP-01"])
			wantBase := oldBase
			if oldBase == nil {
				wantBase = object{"base_input_sha256": input, "plan_sha256": before.NormHash()}
			}
			if !equalValue(wantBase, model.M(model.M(after.Data["execution"])["scopes"])["CP-01"]) {
				t.Fatal("review failed to establish/retain exact scope baseline")
			}
			for _, id := range []string{"T-002", "T-003"} {
				if !equalValue(state(before, id), state(after, id)) {
					t.Fatal("review changed another task")
				}
			}
			settled := readModeTree(t, h.root)
			h.run("task-review", r)
			if !maps.Equal(settled, readModeTree(t, h.root)) {
				t.Fatal("review replay repeated an effect")
			}
		})
	}
}

func TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence(t *testing.T) {
	for _, mismatch := range []string{"baseline", "source-input", "ordinary-prerequisite", "failed-named-test", "missing-named-test"} {
		t.Run(mismatch, func(t *testing.T) {
			h, f := nativeThreeReceiptedFixture(t)
			h.start("T-001")
			if mismatch == "baseline" {
				h.review("T-001")
				f.mutate("apply", object{"changes": []any{object{"op": "record.update", "symbol": "T-003", "fields": object{"steps": model.List("Revised independent method.")}}}})
				p := h.doc("PLAN-EXAMPLE")
				h.mut("approve", p.ID(), object{"receipt": h.receipt(p, p.ID(), "approval", object{})})
				p = h.doc("PLAN-EXAMPLE")
				pr := receiptTransitionCapture(t, h, "GATE-LOCAL", "prerequisite", object{"prerequisite": p.Symbols.ByID["GATE-LOCAL"].Value})
				h.run("prerequisite", receiptTransitionRequest(h, object{"prerequisite": "GATE-LOCAL", "receipt": pr}))
			}
			vr, rr := h.taskReceipts("T-001")
			code := "STALE_EVIDENCE"
			if mismatch == "baseline" {
				code = "SCOPE_RECONCILIATION_REQUIRED"
			}
			if mismatch == "source-input" {
				writeFixture(t, h.root, "src/stage1.go", []byte("Changed after exact fixture receipts.\n"))
			}
			if mismatch == "ordinary-prerequisite" {
				f.mutate("prerequisite", prerequisiteReport("unknown", "tool_result"))
				code = "AUTHORITY_UNVERIFIED"
			}
			if mismatch == "failed-named-test" || mismatch == "missing-named-test" {
				fs, err := store.Open(h.root)
				if err != nil {
					t.Fatal(err)
				}
				original, err := authority.Load(fs, vr)
				fs.Close()
				if err != nil {
					t.Fatal(err)
				}
				payload, err := canonical.Clone(original.Payload())
				if err != nil {
					t.Fatal(err)
				}
				first := model.M(model.A(payload["commands"])[0])
				first["tests"] = empty()
				code = "OBSERVATION_UNVERIFIED"
				if mismatch == "failed-named-test" {
					first["tests"] = []any{object{"name": "TestEnvironmentOverrides", "status": "fail"}}
					code = "INVALID_MODEL"
				}
				// Actual success-observation capture rejects failed statuses at its
				// closed producer schema and missing declared names at verification.
				// Neither case may forge a success receipt to reach a later consumer.
				context := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "verification", "record_id": "T-001"})
				source := observedSourceForContextFixture(t, h.root, model.M(context["subject"]), "verification", "verification_runner", "passed", "Synthetic failed/missing-name observation; no command ran.", payload, context)
				receiptTransitionRefuse(t, h, "capture-observation", source, code)
				return
			}
			receiptTransitionRefuse(t, h, "task-review", receiptTransitionRequest(h, object{"task": "T-001", "verification_receipt": vr, "review_receipt": rr}), code)
		})
	}
}

func TestN10StrictScopeAcceptanceRetainsEveryMemberReceipt(t *testing.T) {
	for _, initial := range []string{"review", "mixed", "later-scope"} {
		t.Run(initial, func(t *testing.T) {
			h, _ := nativeThreeReceiptedFixture(t)
			for _, id := range []string{"T-001", "T-002"} {
				h.start(id)
				h.review(id)
			}
			scope := "CP-01"
			if initial == "mixed" || initial == "later-scope" {
				h.accept("CP-01")
			}
			if initial == "mixed" {
				h.review("T-001")
			}
			if initial == "later-scope" {
				h.start("T-003")
				h.review("T-003")
				scope = "CP-02"
			}
			q := h.quality(scope)
			before := h.doc("PLAN-EXAMPLE")
			r := receiptTransitionRequest(h, object{"scope": scope, "receipt": q})
			h.run("accept-scope", r)
			after := h.doc(before.ID())
			selected := map[string]bool{}
			for _, id := range model.Strings(before.Symbols.ByID[scope].Value["tasks"]) {
				selected[id] = true
				want, _ := canonical.Clone(state(before, id))
				want["state"], want["reason"] = "ACCEPTED", nil
				want["evidence_refs"] = model.List(append(model.Strings(state(before, id)["evidence_refs"]), q)...)
				if !equalValue(want, state(after, id)) {
					t.Fatalf("scope member %s lost old receipts, completion fields or exact quality append", id)
				}
			}
			for _, id := range []string{"T-001", "T-002", "T-003"} {
				if !selected[id] && !equalValue(state(before, id), state(after, id)) {
					t.Fatal("acceptance changed another scope")
				}
			}
			if !equalValue(before.Norm(), after.Norm()) || !equalValue(model.M(before.Data["execution"])["scopes"], model.M(after.Data["execution"])["scopes"]) || after.Revision() != before.Revision()+1 {
				t.Fatal("acceptance changed requirements/baseline or was not one mutation")
			}
			settled := readModeTree(t, h.root)
			h.run("accept-scope", r)
			if !maps.Equal(settled, readModeTree(t, h.root)) {
				t.Fatal("acceptance replay repeated scope effects")
			}
		})
	}
}

func TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope(t *testing.T) {
	for _, mismatch := range []string{"later-member-blocked", "later-member-stale", "prior-unaccepted", "prior-stale"} {
		t.Run(mismatch, func(t *testing.T) {
			h, f := nativeThreeReceiptedFixture(t)
			for _, id := range []string{"T-001", "T-002"} {
				h.start(id)
				h.review(id)
			}
			scope, code := "CP-01", "SCOPE_NOT_READY"
			var q string
			switch mismatch {
			case "later-member-blocked":
				q = h.quality(scope)
				f.mutate("task-block", object{"task": "T-002", "reason": "Owned late-member stop fixture."})
			case "later-member-stale":
				writeFixture(t, h.root, "src/stage2.go", []byte("Changed after the second member's actual fixture evidence.\n"))
				h.review("T-001")
				q = h.quality(scope)
				code = "STALE_EVIDENCE"
			case "prior-unaccepted", "prior-stale":
				scope = "CP-02"
				if mismatch == "prior-stale" {
					h.accept("CP-01")
					writeFixture(t, h.root, "src/stage1.go", []byte("Changed before fresh target evidence, after predecessor acceptance.\n"))
					code = "STALE_EVIDENCE"
				} else {
					code = "DEPENDENCY_NOT_ACCEPTED"
				}
				h.start("T-003")
				h.review("T-003")
				q = h.quality(scope)
			}
			// Prove target quality itself is current: refusal must not be an
			// accidental stale-quality setup failure masking the named guard.
			fs, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			p, s := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
			qr, err := authority.Load(fs, q)
			if err == nil {
				err = evidence.Quality(qr, p, s, scope, h.input())
			}
			if err == nil && mismatch == "later-member-stale" {
				err = evidence.TaskFresh(fs, p, s, p.Symbols.ByID["T-001"].Value, h.input())
			}
			if err == nil && (mismatch == "prior-unaccepted" || mismatch == "prior-stale") {
				err = evidence.TaskFresh(fs, p, s, p.Symbols.ByID["T-003"].Value, h.input())
			}
			fs.Close()
			if err != nil {
				t.Fatalf("named refusal fixture did not preserve current target evidence: %v", err)
			}
			receiptTransitionRefuse(t, h, "accept-scope", receiptTransitionRequest(h, object{"scope": scope, "receipt": q}), code)
		})
	}
}
