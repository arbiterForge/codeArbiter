package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func approvalIdentity(d *model.Document) object {
	return object{"artifact_id": d.ID(), "kind": d.Kind(), "revision": d.Revision(), "model_sha256": d.Hash(), "normative_sha256": d.NormHash()}
}
func equalValue(a, b any) bool {
	x, e := canonical.Hash(a)
	y, f := canonical.Hash(b)
	return e == nil && f == nil && x == y
}

// initialPair projects only the binding change. Neither document acquires
// authority before the one host-observed reply commits both approvals.
func (e *Engine) initialPair(plan repository.Entry, specID string, delegate bool) (repository.Entry, *model.Document, object, error) {
	bad := func(code, msg string) (repository.Entry, *model.Document, object, error) {
		return repository.Entry{}, nil, nil, fault.New(code, msg)
	}
	if plan.Doc.Kind() != "plan" {
		return bad("WRONG_KIND", "combined approval requires a plan and its specification")
	}
	spec, err := e.Catalog.Spec(plan.Doc)
	if err != nil {
		return repository.Entry{}, nil, nil, err
	}
	if spec.Doc.ID() != specID || model.S(spec.Doc.Data["slug"]) != model.S(plan.Doc.Data["slug"]) {
		return bad("PAIR_MISMATCH", "initial sprint must name the exact canonical same-slug pair")
	}
	for _, d := range []*model.Document{spec.Doc, plan.Doc} {
		g := model.M(d.Data["governance"])
		if model.S(g["state"]) != "draft" || len(model.A(g["approvals"])) != 0 {
			return bad("INITIAL_APPROVAL_ONLY", "combined initial approval cannot replace an existing delegation or approval")
		}
	}
	if model.S(model.M(plan.Doc.Norm()["spec_ref"])["binding_mode"]) != "draft_preview" {
		return bad("DRAFT_BINDING", "initial preview must retain its draft source binding")
	}
	for _, v := range model.M(model.M(plan.Doc.Data["execution"])["tasks"]) {
		st := model.M(v)
		if model.S(st["state"]) != "PENDING" || len(model.A(st["evidence_refs"])) != 0 {
			return bad("INITIAL_APPROVAL_ONLY", "initial pair cannot contain started or reviewed work")
		}
	}
	if err = validate.Error(validate.Ready(spec.Doc, nil)); err != nil {
		return repository.Entry{}, nil, nil, err
	}
	if err = validate.Error(validate.Ready(plan.Doc, spec.Doc)); err != nil {
		return repository.Entry{}, nil, nil, err
	}
	projected, err := plan.Doc.Clone()
	if err != nil {
		return repository.Entry{}, nil, nil, err
	}
	model.M(projected.Norm()["spec_ref"])["binding_mode"] = "approved_source"
	projected, err = render.Prepare(projected.Data)
	if err != nil {
		return repository.Entry{}, nil, nil, err
	}
	if err = validate.Error(validate.Binding(projected, spec.Doc)); err != nil {
		return repository.Entry{}, nil, nil, err
	}
	scope, err := observation.ProtectedPlanHash(projected.Norm())
	if err != nil {
		return repository.Entry{}, nil, nil, err
	}
	pair := object{"format": "codearbiter.sprint-pair/0.1.0", "spec": approvalIdentity(spec.Doc), "plan": approvalIdentity(plan.Doc), "approved_plan_normative_sha256": projected.NormHash(), "scope_sha256": scope, "delegate_methods": delegate}
	return spec, projected, pair, nil
}
func pairContext(d *model.Document, pair object, promptHash string) object {
	record := object{"sprint_pair": pair}
	rh, _ := canonical.Hash(record)
	return object{"format": "codearbiter.evidence-context/0.1.0", "activity": "approval", "subject": object{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": d.ID()}, "input_sha256": d.NormHash(), "prompt_sha256": promptHash, "record_sha256": rh, "record": record}
}
func (e *Engine) storeContext(context object) (object, error) {
	b, err := canonical.Marshal(context)
	if err != nil {
		return nil, err
	}
	h := canonical.BytesHash(b)
	if err = e.FS.PutDerived("evidence-contexts", h, b); err != nil {
		return nil, err
	}
	return object{"context_ref": observation.ContextRef(h), "context_sha256": h, "subject": context["subject"]}, nil
}
func (e *Engine) sprintContext(r object, plan repository.Entry) (any, error) {
	spec, projected, pair, err := e.initialPair(plan, model.S(r["spec_id"]), r["delegate_methods"] == true)
	if err != nil {
		return nil, err
	}
	sc, err := e.storeContext(pairContext(spec.Doc, pair, model.S(r["prompt_sha256"])))
	if err != nil {
		return nil, err
	}
	pc, err := e.storeContext(pairContext(projected, pair, model.S(r["prompt_sha256"])))
	if err != nil {
		return nil, err
	}
	return object{"pair": pair, "spec_context": sc, "plan_context": pc, "canonical_changed": false, "scope": "An explicit delegate-methods reply permits only existing task method-step revisions; all execution, verification, security and publication gates remain."}, nil
}
func (e *Engine) loadPairEvent(source object, d *model.Document, pair object) (object, []byte, error) {
	ev, b, err := authority.LoadSource(e.FS, model.S(source["source_ref"]), model.S(source["source_sha256"]))
	if err != nil {
		return nil, nil, err
	}
	obs, _, err := observation.Load(e.FS, model.S(ev["observation_ref"]), model.S(ev["observation_sha256"]))
	if err != nil {
		return nil, nil, err
	}
	if model.S(obs["producer_profile"]) != observation.PairProfile || !equalValue(model.M(ev["payload"])["sprint_pair"], pair) {
		return nil, nil, fault.New("PAIR_MISMATCH", "pair approval requires both observations from the one armed host reply")
	}
	ref, h := model.S(obs["context_ref"]), model.S(obs["context_sha256"])
	context, _, err := observation.LoadContext(e.FS, ref, h)
	if err != nil {
		return nil, nil, err
	}
	if err = observation.ValidateLink(ev, obs, context, ref, h); err != nil {
		return nil, nil, err
	}
	if !equalValue(pairContext(d, pair, canonical.BytesHash([]byte(model.S(ev["source_text"])))), context) {
		return nil, nil, fault.New("STALE_EVIDENCE", "paired host observation no longer matches both armed definitions")
	}
	return ev, b, nil
}
func withApproval(d *model.Document, r *authority.Receipt, revision int64) (*model.Document, error) {
	next, err := d.Clone()
	if err != nil {
		return nil, err
	}
	g := model.M(next.Data["governance"])
	g["state"] = "approved"
	g["approvals"] = append(model.A(g["approvals"]), authority.ApprovalRecord(r, d))
	next.Data["revision"] = revision
	return render.Prepare(next.Data)
}
func (e *Engine) sprintApprove(r object, plan repository.Entry) (any, error) {
	ps := model.M(r["plan_source"])
	raw, _, err := authority.LoadSource(e.FS, model.S(ps["source_ref"]), model.S(ps["source_sha256"]))
	if err != nil {
		return nil, err
	}
	actualSpec, err := e.Catalog.Resolve(model.S(r["spec_id"]))
	if err != nil {
		return nil, err
	}
	expectedSpec := model.M(r["spec_expected"])
	if actualSpec.Doc.Kind() != "spec" || model.I(expectedSpec["revision"]) != actualSpec.Doc.Revision() || model.S(expectedSpec["model_sha256"]) != actualSpec.Doc.Hash() {
		return nil, fault.New("REVISION_CONFLICT", "spec changed after this exact paired request was observed")
	}
	delegate := model.M(model.M(raw["payload"])["sprint_pair"])["delegate_methods"] == true
	spec, projected, pair, err := e.initialPair(plan, model.S(r["spec_id"]), delegate)
	if err != nil {
		return nil, err
	}
	expected := model.M(r["spec_expected"])
	if model.I(expected["revision"]) != spec.Doc.Revision() || model.S(expected["model_sha256"]) != spec.Doc.Hash() {
		return nil, fault.New("REVISION_CONFLICT", "the spec and plan must both match their armed revisions")
	}
	se, sb, err := e.loadPairEvent(model.M(r["spec_source"]), spec.Doc, pair)
	if err != nil {
		return nil, err
	}
	pe, pb, err := e.loadPairEvent(ps, projected, pair)
	if err != nil {
		return nil, err
	}
	so, _, err := observation.Load(e.FS, model.S(se["observation_ref"]), model.S(se["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	po, _, err := observation.Load(e.FS, model.S(pe["observation_ref"]), model.S(pe["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	if model.S(se["source_text"]) != model.S(pe["source_text"]) || !equalValue(so["producer_result"], po["producer_result"]) {
		return nil, fault.New("PAIR_MISMATCH", "two independent approvals cannot impersonate one host-observed reply")
	}
	sr, err := e.storeReceipt(model.M(r["spec_source"]), se, sb)
	if err != nil {
		return nil, err
	}
	pr, err := e.storeReceipt(ps, pe, pb)
	if err != nil {
		return nil, err
	}
	sn, err := withApproval(spec.Doc, sr, spec.Doc.Revision()+1)
	if err != nil {
		return nil, err
	}
	pn, err := withApproval(projected, pr, plan.Doc.Revision()+1)
	if err != nil {
		return nil, err
	}
	sbytes, err := render.Render(sn)
	if err != nil {
		return nil, err
	}
	pbytes, err := render.Render(pn)
	if err != nil {
		return nil, err
	}
	out := object{"spec": Identity(sn, spec.Path), "plan": Identity(pn, plan.Path), "receipt": pr.Path, "spec_receipt": sr.Path, "grant_receipt": nil, "authority_kind": "user_workflow"}
	if delegate {
		out["grant_receipt"] = pr.Path
	}
	committed, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: spec.Path, Before: spec.Bytes, After: sbytes}, {Path: plan.Path, Before: plan.Bytes, After: pbytes}}, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(committed), nil
}
func hasApproval(d *model.Document, receipt string) bool {
	for _, v := range model.A(model.M(d.Data["governance"])["approvals"]) {
		if model.S(model.M(v)["source_ref"]) == receipt {
			return true
		}
	}
	return false
}

// Reset only invalidates work. It retains receipt refs as history and never
// marks a task or scope accepted. A currently running writer must quiesce.
func resetMethodDependents(next *model.Document, task string) error {
	affected := map[string]bool{task: true}
	scopes := map[string]bool{}
	for changed := true; changed; {
		changed = false
		for _, v := range model.A(next.Norm()["tasks"]) {
			t := model.M(v)
			id := model.S(t["id"])
			scope := model.S(t["checkpoint"])
			hit := affected[id] || scopes[scope]
			for _, dep := range model.Strings(t["depends_on"]) {
				hit = hit || affected[dep]
			}
			if hit {
				if !affected[id] {
					affected[id] = true
					changed = true
				}
				if !scopes[scope] {
					scopes[scope] = true
					changed = true
				}
			}
		}
	}
	for id := range affected {
		if model.S(state(next, id)["state"]) == "IN_PROGRESS" {
			return fault.New("ACTIVE_WORK", "quiesce affected writers before changing their method")
		}
	}
	for id := range affected {
		st := state(next, id)
		// Method approval is not reconciliation authority. Invalidate stale
		// proof without clearing a recorded permission/security/task block.
		if model.S(st["state"]) == "BLOCKED" {
			continue
		}
		st["state"] = "PENDING"
		st["reason"] = "Delegated method revision invalidated this checkpoint; rerun its original verification and reviews."
	}
	for scope := range scopes {
		delete(model.M(model.M(next.Data["execution"])["scopes"]), scope)
	}
	return nil
}
func (e *Engine) smartsApply(r object, entry repository.Entry) (any, error) {
	d := entry.Doc
	if d.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "SMARTS method authority applies only to an already-approved plan")
	}
	spec, err := e.guards(d)
	if err != nil {
		return nil, err
	}
	grant, err := authority.Load(e.FS, model.S(r["grant_receipt"]))
	if err != nil {
		return nil, err
	}
	pair := model.M(grant.Payload()["sprint_pair"])
	if model.S(grant.Data["authority_kind"]) != "user_workflow" || pair["delegate_methods"] != true || !hasApproval(d, grant.Path) {
		return nil, fault.New("DELEGATION_REQUIRED", "use the explicit initial user pair approval already recorded on this plan")
	}
	if model.S(model.M(pair["plan"])["artifact_id"]) != d.ID() || model.S(model.M(pair["spec"])["artifact_id"]) != spec.ID() || model.S(model.M(pair["spec"])["normative_sha256"]) != spec.NormHash() {
		return nil, fault.New("DELEGATION_SCOPE", "grant names another plan or specification definition")
	}
	sr, err := authority.Approved(e.FS, spec)
	if err != nil {
		return nil, err
	}
	if !equalValue(sr.Payload()["sprint_pair"], pair) {
		return nil, fault.New("DELEGATION_REQUIRED", "the original combined spec approval is no longer current")
	}
	decision := model.M(r["decision"])
	if err = observation.ValidateDecision(decision); err != nil {
		return nil, err
	}
	id := model.S(decision["task_id"])
	symbol, ok := d.Symbols.ByID[id]
	if !ok || symbol.Kind != "tasks" || symbol.Retired {
		return nil, fault.New("UNKNOWN_TASK", "delegated method must name an existing task")
	}
	option := model.M(model.A(decision["options"])[model.I(decision["selected"])])
	next, _, err := Changes(d, []any{object{"op": "record.update", "symbol": id, "fields": object{"steps": option["steps"]}}})
	if err != nil {
		return nil, err
	}
	record := object{"pair": pair, "grant_receipt": grant.Path, "decision": decision, "before_normative": d.Norm(), "after_normative": next.Norm()}
	if err = observation.ValidateSMARTSRecord(record); err != nil {
		return nil, err
	}
	if d.NormHash() == next.NormHash() {
		return nil, fault.New("UNCHANGED_DECISION", "identical method needs no reapproval or retry; keep current authority")
	}
	if err = validate.Error(validate.Ready(next, spec)); err != nil {
		return nil, err
	}
	if err = resetMethodDependents(next, id); err != nil {
		return nil, err
	}
	payload := object{"smarts": record}
	rh, _ := canonical.Hash(payload)
	db, _ := canonical.Marshal(decision)
	subject := object{"artifact_id": d.ID(), "normative_sha256": next.NormHash(), "record_id": d.ID()}
	ctx := object{"format": "codearbiter.evidence-context/0.1.0", "activity": "approval", "subject": subject, "input_sha256": next.NormHash(), "prompt_sha256": canonical.BytesHash(db), "record_sha256": rh, "record": payload}
	cr, err := e.storeContext(ctx)
	if err != nil {
		return nil, err
	}
	dh, _ := canonical.Hash(decision)
	result := object{"grant_receipt": grant.Path, "decision_sha256": dh, "scope_sha256": pair["scope_sha256"]}
	rhash, _ := canonical.Hash(result)
	phash, _ := canonical.Hash(payload)
	obs := object{"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": subject, "context_ref": cr["context_ref"], "context_sha256": cr["context_sha256"], "payload_sha256": phash, "producer_profile": observation.SMARTSProfile, "producer_run_id": r["operation_id"], "producer_result": result, "producer_result_sha256": rhash}
	ob, err := canonical.Marshal(obs)
	if err != nil {
		return nil, err
	}
	oh := canonical.BytesHash(ob)
	if err = e.FS.PutObservation(oh, ob); err != nil {
		return nil, err
	}
	ev := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "approval", "authority_kind": "smarts_workflow", "subject": subject, "actor": "delegated SMARTS plan-method producer", "origin": r["operation_id"], "verdict": "approved", "payload": payload, "source_text": string(db), "observation_ref": observation.Ref(oh), "observation_sha256": oh}
	if err = observation.ValidateLink(ev, obs, ctx, model.S(cr["context_ref"]), model.S(cr["context_sha256"])); err != nil {
		return nil, err
	}
	eb, err := canonical.Marshal(ev)
	if err != nil {
		return nil, err
	}
	eh := canonical.BytesHash(eb)
	if err = e.FS.PutAuthoritySource(eh, eb); err != nil {
		return nil, err
	}
	receipt, err := e.storeReceipt(object{"source_ref": authority.SourceRef(eh), "source_sha256": eh}, ev, eb)
	if err != nil {
		return nil, err
	}
	next, err = withApproval(next, receipt, d.Revision()+1)
	if err != nil {
		return nil, err
	}
	bytes, err := render.Render(next)
	if err != nil {
		return nil, err
	}
	out := Identity(next, entry.Path)
	out["authority_kind"] = "smarts_workflow"
	out["receipt"] = receipt.Path
	out["grant_receipt"] = grant.Path
	out["acceptance_granted"] = false
	committed, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: entry.Path, Before: entry.Bytes, After: bytes}}, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(committed), nil
}
