//go:build linux

package operations

import (
	"errors"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// Synthetic host observations only; these tests never certify a live user turn.
func pairFixture(h *harness, delegate bool) (object, object) {
	h.t.Helper()
	mode := "approve-only"
	if delegate {
		mode = "delegate-methods"
	}
	prompt := "approve-sprint SPEC-EXAMPLE PLAN-EXAMPLE " + mode + " fixture-token-1234"
	ctx := h.run("sprint-approval-context", object{"artifact_id": "PLAN-EXAMPLE", "spec_id": "SPEC-EXAMPLE", "delegate_methods": delegate, "prompt_sha256": canonical.BytesHash([]byte(prompt))})
	sources := []object{}
	for _, key := range []string{"spec_context", "plan_context"} {
		cr := model.M(ctx[key])
		b, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(model.S(cr["context_ref"]))))
		if err != nil {
			h.t.Fatal(err)
		}
		c, err := canonical.Object(b)
		if err != nil {
			h.t.Fatal(err)
		}
		payload := object{"sprint_pair": ctx["pair"]}
		producer := object{"host": "fixture", "session_id": "one-turn", "prompt_sha256": canonical.BytesHash([]byte(prompt))}
		obs := object{"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": c["subject"], "context_ref": cr["context_ref"], "context_sha256": cr["context_sha256"], "payload_sha256": mustHashFixture(h.t, payload), "producer_profile": "host-user-pair/0.1.0", "producer_run_id": "fixture:one-turn", "producer_result": producer, "producer_result_sha256": mustHashFixture(h.t, producer)}
		op, oh := h.immutableJSON("observations", obs)
		ev := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "approval", "authority_kind": "user_workflow", "subject": c["subject"], "actor": "synthetic user fixture", "origin": "fixture one turn", "verdict": "approved", "payload": payload, "source_text": prompt, "observation_ref": op, "observation_sha256": oh}
		sources = append(sources, h.authoritySource(ev))
	}
	p, s := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	req := object{"artifact_id": p.ID(), "spec_id": s.ID(), "operation_id": h.next(), "expected": object{"revision": p.Revision(), "model_sha256": p.Hash()}, "spec_expected": object{"revision": s.Revision(), "model_sha256": s.Hash()}, "spec_source": sources[0], "plan_source": sources[1]}
	return ctx, req
}
func decisionFixture() object {
	lenses := object{}
	for _, n := range []string{"Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable"} {
		lenses[n] = object{"verdict": "Adequate", "reason": "Existing bounded task contracts remain unchanged."}
	}
	return object{"task_id": "T-001", "options": []any{object{"label": "Explicit precedence", "steps": model.List("Write the retained negative test.", "Use an explicit precedence table and preserve the named oracle."), "lenses": lenses}}, "selected": int64(0), "strength": "moderate", "rationale": "The recorded spec determines precedence; this single evidenced method preserves its constraints and verification."}
}
func smartsReq(h *harness, grant string) object {
	p := h.doc("PLAN-EXAMPLE")
	return object{"artifact_id": p.ID(), "operation_id": h.next(), "expected": object{"revision": p.Revision(), "model_sha256": p.Hash()}, "grant_receipt": grant, "decision": decisionFixture()}
}
func TestSprintPairAtomicApprovalAndReplay(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	s, p := h.doc("SPEC-EXAMPLE"), h.doc("PLAN-EXAMPLE")
	_, req := pairFixture(h, true)
	out := h.run("sprint-approve", req)
	for _, id := range []string{s.ID(), p.ID()} {
		if h.run("validate", object{"artifact_id": id, "gate": "approved"})["valid"] != true {
			t.Fatal(id)
		}
	}
	if h.doc(s.ID()).NormHash() != s.NormHash() || h.doc(p.ID()).NormHash() == p.NormHash() {
		t.Fatal("only the plan binding should change norm")
	}
	if model.S(out["grant_receipt"]) == "" {
		t.Fatal("missing explicit grant")
	}
	before := h.doc(p.ID()).Hash()
	h.run("sprint-approve", req)
	if h.doc(p.ID()).Hash() != before {
		t.Fatal("replay mutated")
	}
}
func TestSprintPairStaleMemberCannotPartiallyApprove(t *testing.T) {
	for _, id := range []string{"SPEC-EXAMPLE", "PLAN-EXAMPLE"} {
		t.Run(id, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			_, r := pairFixture(h, false)
			h.mut("apply", id, object{"changes": []any{object{"op": "header.update", "fields": object{"summary": "Changed after the prompt was armed."}}}})
			if _, err := h.request("sprint-approve", r); err == nil {
				t.Fatal("stale accepted")
			}
			for _, id := range []string{"SPEC-EXAMPLE", "PLAN-EXAMPLE"} {
				if h.run("validate", object{"artifact_id": id, "gate": "approved"})["valid"] == true {
					t.Fatal("partial approval")
				}
			}
		})
	}
}
func TestSprintPairWrongSourceLeavesBothDraft(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	r["plan_source"] = r["spec_source"]
	if _, err := h.request("sprint-approve", r); err == nil {
		t.Fatal("wrong source accepted")
	}
	for _, id := range []string{"SPEC-EXAMPLE", "PLAN-EXAMPLE"} {
		if model.S(model.M(h.doc(id).Data["governance"])["state"]) != "draft" {
			t.Fatal("partial write")
		}
	}
}
func TestSprintPairCannotUseGenericCapture(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	if _, err := h.request("capture-observation", model.M(r["spec_source"])); fault.Code(err) != "PAIR_APPROVAL_REQUIRED" {
		t.Fatalf("got %v", err)
	}
}
func TestSprintPairReceiptCannotApproveSingleArtifact(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	out := h.run("sprint-approve", r)
	p := h.doc("PLAN-EXAMPLE")
	if _, err := h.request("approve", object{"artifact_id": p.ID(), "operation_id": h.next(), "expected": object{"revision": p.Revision(), "model_sha256": p.Hash()}, "receipt": out["grant_receipt"]}); fault.Code(err) != "PAIR_APPROVAL_REQUIRED" {
		t.Fatalf("got %v", err)
	}
}
func TestSMARTSExplicitGrantPreservesScopeAndOriginalProofObligations(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	out := h.run("sprint-approve", r)
	before := h.doc("PLAN-EXAMPLE")
	task := before.Symbols.ByID["T-001"].Value
	req := smartsReq(h, model.S(out["grant_receipt"]))
	got := h.run("smarts-apply", req)
	after := h.doc(before.ID())
	if after.NormHash() == before.NormHash() {
		t.Fatal("method unchanged")
	}
	for _, key := range []string{"paths", "criterion_refs", "verification", "done_when", "rollback", "checkpoint", "execution_scope", "depends_on"} {
		if mustHashFixture(t, task[key]) != mustHashFixture(t, after.Symbols.ByID["T-001"].Value[key]) {
			t.Fatal("weakened obligation", key)
		}
	}
	if h.run("validate", object{"artifact_id": after.ID(), "gate": "approved"})["valid"] != true || got["authority_kind"] != "smarts_workflow" || got["acceptance_granted"] != false {
		t.Fatal("wrong approval boundary")
	}
	h.run("smarts-apply", req)
	if h.doc(after.ID()).Hash() != after.Hash() {
		t.Fatal("replay changed state")
	}
}
func TestSMARTSWithoutExplicitDelegationRefused(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, false)
	out := h.run("sprint-approve", r)
	if out["grant_receipt"] != nil {
		t.Fatal("implicit delegation")
	}
	p := h.doc("PLAN-EXAMPLE")
	a := model.M(model.A(model.M(p.Data["governance"])["approvals"])[0])
	if _, err := h.request("smarts-apply", smartsReq(h, model.S(a["source_ref"]))); fault.Code(err) != "DELEGATION_REQUIRED" {
		t.Fatalf("got %v", err)
	}
}
func TestSMARTSCannotInventInitialApproval(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	if _, err := h.request("smarts-apply", smartsReq(h, ".codearbiter/.artifacts/receipts/"+canonical.BytesHash(nil)+".json")); err == nil {
		t.Fatal("self-delegated")
	}
}
func TestSMARTSRejectsMalformedOrScopeExpandingChoices(t *testing.T) {
	for _, variant := range []string{"missing-lens", "hedging", "paths", "verification", "dominated", "bad-selected", "empty-steps"} {
		t.Run(variant, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			_, r := pairFixture(h, true)
			out := h.run("sprint-approve", r)
			req := smartsReq(h, model.S(out["grant_receipt"]))
			d := model.M(req["decision"])
			o := model.M(model.A(d["options"])[0])
			before := h.doc("PLAN-EXAMPLE").Hash()
			switch variant {
			case "missing-lens":
				delete(model.M(o["lenses"]), "Securable")
			case "hedging":
				model.M(model.M(o["lenses"])["Reliable"])["reason"] = "Might work."
			case "paths":
				o["paths"] = model.List("**")
			case "verification":
				o["verification"] = []any{}
			case "dominated":
				other, _ := canonical.Clone(o)
				other["label"] = "Stronger option"
				for _, v := range model.M(other["lenses"]) {
					model.M(v)["verdict"] = "Strong"
				}
				d["options"] = append(model.A(d["options"]), other)
			case "bad-selected":
				d["selected"] = int64(99)
			case "empty-steps":
				o["steps"] = []any{}
			}
			if _, err := h.request("smarts-apply", req); err == nil {
				t.Fatal("invalid choice accepted")
			}
			if h.doc("PLAN-EXAMPLE").Hash() != before {
				t.Fatal("refusal mutated")
			}
		})
	}
}
func TestSMARTSTieDoesNotDemandAnotherHumanDecision(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	out := h.run("sprint-approve", r)
	req := smartsReq(h, model.S(out["grant_receipt"]))
	d := model.M(req["decision"])
	other, _ := canonical.Clone(model.M(model.A(d["options"])[0]))
	other["label"] = "Equivalent bounded lookup"
	other["steps"] = model.List("Retain the oracle and use a bounded lookup.")
	d["options"] = append(model.A(d["options"]), other)
	d["selected"] = int64(1)
	d["strength"] = "tied"
	h.run("smarts-apply", req)
}
func TestSMARTSChangedSpecRevokesGrant(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	out := h.run("sprint-approve", r)
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"summary": "Changed product requirement."}}}})
	if _, err := h.request("smarts-apply", smartsReq(h, model.S(out["grant_receipt"]))); err == nil {
		t.Fatal("stale scope accepted")
	}
}
func TestSprintPairCannotRecycleInitialDelegation(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, false)
	h.run("sprint-approve", r)
	if _, err := h.request("sprint-approval-context", object{"artifact_id": "PLAN-EXAMPLE", "spec_id": "SPEC-EXAMPLE", "delegate_methods": true, "prompt_sha256": canonical.BytesHash([]byte("fixture"))}); err == nil {
		t.Fatal("initial delegation recycled")
	}
}
func TestSprintPairCrashRecoveryBlocksPartialAuthority(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			_, r := pairFixture(h, true)
			r["protocol"] = Protocol
			rh := mustHashFixture(t, object{"operation": "sprint-approve", "request": r})
			f, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			unlock, err := f.Lock(true, time.Second)
			if err != nil {
				t.Fatal(err)
			}
			c, err := repository.Scan(f)
			if err != nil {
				t.Fatal(err)
			}
			entry, err := c.Resolve("PLAN-EXAMPLE")
			if err != nil {
				t.Fatal(err)
			}
			f.Inject = func(step string) error {
				if step == "after-replace-0" {
					return errors.New("synthetic interruption after first canonical replacement")
				}
				return nil
			}
			e := Engine{FS: f, Catalog: c, RequestHash: rh}
			_, err = e.sprintApprove(r, entry)
			if err == nil {
				t.Fatal("failure injection did not fire")
			}
			unlock()
			f.Close()
			if _, err = h.request("validate", object{"artifact_id": "SPEC-EXAMPLE", "gate": "approved"}); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("partial authority visible: %v", err)
			}
			if _, err := h.request("recover", object{"operation_id": r["operation_id"], "mode": mode}); err != nil {
				t.Fatal(err)
			}
			if mode == "complete" {
				h.run("sprint-approve", r)
				for _, id := range []string{"SPEC-EXAMPLE", "PLAN-EXAMPLE"} {
					if h.run("validate", object{"artifact_id": id, "gate": "approved"})["valid"] != true {
						t.Fatal(id)
					}
				}
			} else {
				for _, id := range []string{"SPEC-EXAMPLE", "PLAN-EXAMPLE"} {
					if h.run("validate", object{"artifact_id": id, "gate": "approved"})["valid"] == true {
						t.Fatal("rollback retained approval")
					}
				}
				if _, err = h.request("sprint-approve", r); fault.Code(err) != "OPERATION_ROLLED_BACK" {
					t.Fatalf("got %v", err)
				}
			}
		})
	}
}

func TestSMARTSInvalidatesAcceptedScopesAndRetainsHistoricalEvidence(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	grant := model.S(h.run("sprint-approve", r)["grant_receipt"])
	for _, id := range []string{"T-001", "T-002"} {
		h.start(id)
		h.review(id)
	}
	h.accept("CP-01")
	h.start("T-003")
	h.review("T-003")
	h.accept("CP-02")
	before := h.doc("PLAN-EXAMPLE")
	if h.run("eligible", object{"artifact_id": before.ID()})["all_accepted_and_current"] != true {
		t.Fatal("fixture did not become accepted")
	}
	h.run("smarts-apply", smartsReq(h, grant))
	after := h.doc(before.ID())
	for _, id := range []string{"T-001", "T-002", "T-003"} {
		if model.S(state(after, id)["state"]) != "PENDING" {
			t.Fatal("stale work accepted", id)
		}
		if !equalValue(state(before, id)["evidence_refs"], state(after, id)["evidence_refs"]) {
			t.Fatal("historical evidence discarded", id)
		}
	}
	if len(model.M(model.M(after.Data["execution"])["scopes"])) != 0 {
		t.Fatal("stale scope proof retained")
	}
	if h.run("eligible", object{"artifact_id": after.ID()})["all_accepted_and_current"] == true {
		t.Fatal("method decision accepted work")
	}
	h.start("T-001")
	h.review("T-001")
	if h.run("eligible", object{"artifact_id": after.ID()})["next_task"] != "T-002" {
		t.Fatal("fresh verification could not resume dependency")
	}
}
func TestSMARTSUnchangedMethodIsNotAnotherAttempt(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	grant := model.S(h.run("sprint-approve", r)["grant_receipt"])
	h.run("smarts-apply", smartsReq(h, grant))
	before := h.doc("PLAN-EXAMPLE").Hash()
	if _, err := h.request("smarts-apply", smartsReq(h, grant)); fault.Code(err) != "UNCHANGED_DECISION" {
		t.Fatalf("got %v", err)
	}
	if h.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("unchanged attempt mutated state")
	}
}
func TestSMARTSCannotReapproveAnAmendedProtectedPlan(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	grant := model.S(h.run("sprint-approve", r)["grant_receipt"])
	h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "T-001", "fields": object{"paths": []any{object{"path": "outside/scope.go", "action": "create"}}}}}})
	d := h.doc("PLAN-EXAMPLE")
	receipt := h.receipt(d, d.ID(), "approval", object{})
	h.mut("approve", d.ID(), object{"receipt": receipt})
	before := h.doc(d.ID()).Hash()
	if _, err := h.request("smarts-apply", smartsReq(h, grant)); fault.Code(err) != "DELEGATION_SCOPE" {
		t.Fatalf("old method grant survived changed protected scope: %v", err)
	}
	if h.doc(d.ID()).Hash() != before {
		t.Fatal("refused grant mutated state")
	}
}

func TestSMARTSDoesNotClearBlockedMembersOrTheirReason(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, r := pairFixture(h, true)
	grant := model.S(h.run("sprint-approve", r)["grant_receipt"])
	h.mut("task-block", "PLAN-EXAMPLE", object{"task": "T-002", "reason": "An external permission has not been granted."})
	before := h.doc("PLAN-EXAMPLE")
	h.run("smarts-apply", smartsReq(h, grant))
	after := h.doc(before.ID())
	if model.S(state(after, "T-002")["state"]) != "BLOCKED" || !equalValue(state(before, "T-002"), state(after, "T-002")) {
		t.Fatal("method choice cleared a blocked obligation")
	}
	if h.run("eligible", object{"artifact_id": after.ID()})["all_accepted_and_current"] == true {
		t.Fatal("blocked work accepted")
	}
}
