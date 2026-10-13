package operations

import (
	"encoding/base64"
	"os"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// contextSourceBytes distinguishes an absent file from a present empty file.
func contextSourceBytes(f *store.FS, p string) ([]byte, error) {
	b, err := f.Read(p, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, nil
	}
	return b, err
}

func contextBase64(value []byte) any {
	if value == nil {
		return nil
	}
	return base64.StdEncoding.EncodeToString(value)
}

func contextDecodeBase64(value any) ([]byte, error) {
	if value == nil {
		return nil, nil
	}
	encoded, ok := value.(string)
	if !ok {
		return nil, fault.New("INVALID_CONTEXT_AUTHORITY", "context preimage has an invalid encoding")
	}
	decoded, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(decoded) > canonical.MaxBytes {
		return nil, fault.New("INVALID_CONTEXT_AUTHORITY", "context preimage is malformed or oversized")
	}
	return decoded, nil
}

func (e *Engine) buildContextPreviewContext(preview object, promptHash string) (object, error) {
	if model.S(preview["mode"]) == "finalize" {
		return e.buildContextFinalizationContext(preview, promptHash)
	}
	if len(promptHash) != 64 {
		return nil, fault.New("INVALID_REQUEST", "context reply requires a prompt digest")
	}
	typed, err := canonical.Marshal(preview["typed"])
	if err != nil {
		return nil, err
	}
	proposed, err := canonical.Marshal(preview["proposed_provenance"])
	if err != nil {
		return nil, err
	}
	doc, err := contextdocument.Validate(typed)
	if err != nil || doc.DocumentID != model.S(preview["document_id"]) || doc.TargetPath != model.S(preview["target_path"]) {
		return nil, fault.New("INVALID_CONTEXT_MUTATION", "typed context document and target disagree")
	}
	beforeDoc, err := contextSourceBytes(e.FS, doc.TargetPath)
	if err != nil {
		return nil, err
	}
	beforeProvenance, err := contextSourceBytes(e.FS, ".codearbiter/.provenance/"+doc.DocumentID+".json")
	if err != nil {
		return nil, err
	}
	if (beforeDoc == nil && preview["expected_document_sha256"] != nil) || (beforeDoc != nil && canonical.BytesHash(beforeDoc) != model.S(preview["expected_document_sha256"])) ||
		(beforeProvenance == nil && preview["expected_provenance_sha256"] != nil) || (beforeProvenance != nil && canonical.BytesHash(beforeProvenance) != model.S(preview["expected_provenance_sha256"])) {
		return nil, fault.New("STALE_EVIDENCE", "context preview preimage changed")
	}
	selections := make([]contextdocument.PreviewSelection, 0, len(model.A(preview["selections"])))
	for _, value := range model.A(preview["selections"]) {
		selection := model.M(value)
		selections = append(selections, contextdocument.PreviewSelection{EntryID: model.S(selection["entry_id"]), Anchor: model.S(selection["anchor"])})
	}
	mutation := contextdocument.Mutation{
		OperationID: model.S(preview["operation_id"]), Mode: model.S(preview["mode"]),
		Typed: typed, Selections: selections, ExpectedDocument: beforeDoc,
		ExpectedProvenance: beforeProvenance, ProposedProvenance: proposed,
	}
	proposal, binding, err := contextdocument.PreviewBinding(mutation)
	if err != nil {
		return nil, err
	}
	if err := contextdocument.ValidateCurrentEvidence(e.FS, proposed, proposal); err != nil {
		return nil, err
	}
	id := "CONTEXT-" + strings.ToUpper(doc.DocumentID)
	record := object{"preview_binding_sha256": binding}
	recordHash, err := canonical.Hash(record)
	if err != nil {
		return nil, err
	}
	context := object{
		"format": "codearbiter.evidence-context/0.1.0", "activity": "context_approval",
		"subject":      object{"artifact_id": id, "record_id": id, "normative_sha256": binding},
		"input_sha256": binding, "prompt_sha256": promptHash,
		"record_sha256": recordHash, "record": record, "preview": preview,
		"preview_document": string(proposal.Bytes), "after_document_sha256": proposal.AfterSHA256,
		"before_document_base64": contextBase64(beforeDoc), "before_provenance_base64": contextBase64(beforeProvenance),
	}
	if es := schema.ValidateWith(observation.ContextSchema(), context); len(es) != 0 {
		return nil, &es[0]
	}
	return context, nil
}

func finalizationFromPreview(preview object) (contextdocument.Finalization, error) {
	if len(preview) != 5 || model.S(preview["mode"]) != "finalize" || model.S(preview["document_id"]) != "CONTEXT" || model.S(preview["target_path"]) != ".codearbiter/CONTEXT.md" {
		return contextdocument.Finalization{}, fault.New("INVALID_CONTEXT_FINALIZATION", "finalization preview must name only CONTEXT and exact outputs")
	}
	values := model.M(preview["expected"])
	if values == nil {
		return contextdocument.Finalization{}, fault.New("INVALID_CONTEXT_FINALIZATION", "finalization output identities are required")
	}
	expected := make(map[string]string, len(values))
	for path, value := range values {
		if _, ok := value.(string); !ok {
			return contextdocument.Finalization{}, fault.New("INVALID_CONTEXT_FINALIZATION", "finalization output identity is malformed")
		}
		expected[path] = model.S(value)
	}
	return contextdocument.Finalization{OperationID: model.S(preview["operation_id"]), Expected: expected}, nil
}

func (e *Engine) buildContextFinalizationContext(preview object, promptHash string) (object, error) {
	if len(promptHash) != 64 {
		return nil, fault.New("INVALID_REQUEST", "context reply requires a prompt digest")
	}
	r, err := finalizationFromPreview(preview)
	if err != nil {
		return nil, err
	}
	proposal, err := contextdocument.PreviewFinalization(e.FS, r)
	if err != nil {
		return nil, err
	}
	beforeDoc, err := contextSourceBytes(e.FS, ".codearbiter/CONTEXT.md")
	if err != nil {
		return nil, err
	}
	beforeProvenance, err := contextSourceBytes(e.FS, ".codearbiter/.provenance/CONTEXT.json")
	if err != nil {
		return nil, err
	}
	record := object{"preview_binding_sha256": proposal.Binding}
	recordHash, err := canonical.Hash(record)
	if err != nil {
		return nil, err
	}
	id := "CONTEXT-CONTEXT"
	context := object{
		"format": "codearbiter.evidence-context/0.1.0", "activity": "context_approval",
		"subject":      object{"artifact_id": id, "record_id": id, "normative_sha256": proposal.Binding},
		"input_sha256": proposal.Binding, "prompt_sha256": promptHash,
		"record_sha256": recordHash, "record": record, "preview": preview,
		"preview_document": string(proposal.Document), "after_document_sha256": canonical.BytesHash(proposal.Document),
		"before_document_base64": contextBase64(beforeDoc), "before_provenance_base64": contextBase64(beforeProvenance),
	}
	if es := schema.ValidateWith(observation.ContextSchema(), context); len(es) != 0 {
		return nil, &es[0]
	}
	return context, nil
}

func (e *Engine) contextEvidenceContext(r object) (any, error) {
	promptHash := model.S(r["prompt_sha256"])
	preview := object{}
	for _, k := range []string{"operation_id", "mode", "document_id", "target_path", "typed", "selections", "expected_document_sha256", "expected_provenance_sha256", "proposed_provenance"} {
		preview[k] = r[k]
	}
	context, err := e.buildContextPreviewContext(preview, promptHash)
	if err != nil {
		return nil, err
	}
	b, err := canonical.Marshal(context)
	if err != nil {
		return nil, err
	}
	h := canonical.BytesHash(b)
	if err := e.FS.PutDerived("evidence-contexts", h, b); err != nil {
		return nil, err
	}
	return object{"context_ref": observation.ContextRef(h), "context_sha256": h,
		"preview_binding_sha256": context["input_sha256"], "subject": context["subject"],
		"preview_document": context["preview_document"], "after_document_sha256": context["after_document_sha256"]}, nil
}

func (e *Engine) contextFinalizationEvidenceContext(r object) (any, error) {
	preview := object{}
	for _, key := range []string{"operation_id", "mode", "document_id", "target_path", "expected"} {
		preview[key] = r[key]
	}
	context, err := e.buildContextFinalizationContext(preview, model.S(r["prompt_sha256"]))
	if err != nil {
		return nil, err
	}
	b, err := canonical.Marshal(context)
	if err != nil {
		return nil, err
	}
	h := canonical.BytesHash(b)
	if err := e.FS.PutDerived("evidence-contexts", h, b); err != nil {
		return nil, err
	}
	return object{"context_ref": observation.ContextRef(h), "context_sha256": h,
		"preview_binding_sha256": context["input_sha256"], "subject": context["subject"],
		"preview_document": context["preview_document"], "after_document_sha256": context["after_document_sha256"]}, nil
}

func (e *Engine) captureContextPreview(r object) (any, error) {
	ev, eb, err := authority.LoadSource(e.FS, model.S(r["source_ref"]), model.S(r["source_sha256"]))
	if err != nil {
		return nil, err
	}
	if model.S(ev["kind"]) != "context_approval" || model.S(ev["authority_kind"]) != "user_workflow" {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "context capture requires its own observed user reply")
	}
	obs, _, err := observation.Load(e.FS, model.S(ev["observation_ref"]), model.S(ev["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	contextRef, contextHash := model.S(obs["context_ref"]), model.S(obs["context_sha256"])
	context, _, err := observation.LoadContext(e.FS, contextRef, contextHash)
	if err != nil {
		return nil, err
	}
	if err := observation.ValidateLink(ev, obs, context, contextRef, contextHash); err != nil {
		return nil, err
	}
	fresh, err := e.buildContextPreviewContext(model.M(context["preview"]), model.S(context["prompt_sha256"]))
	if err != nil {
		return nil, err
	}
	freshHash, err := canonical.Hash(fresh)
	if err != nil || freshHash != contextHash {
		return nil, fault.New("STALE_EVIDENCE", "context preview or source evidence changed after observation")
	}
	receipt, err := e.storeReceipt(r, ev, eb)
	if err != nil {
		return nil, err
	}
	if err := authority.ValidateContextPreview(e.FS, receipt.Path, model.S(context["input_sha256"])); err != nil {
		return nil, err
	}
	return object{"receipt": receipt.Path, "receipt_sha256": receipt.Hash,
		"event": receipt.EventPath, "event_sha256": canonical.BytesHash(eb),
		"authority_source": r["source_ref"], "authority_source_sha256": r["source_sha256"],
		"artifact_approval_changed": false,
		"trust_model":               "host-source-bound cooperative workflow attestation; not independent identity authentication"}, nil
}

func (e *Engine) contextApply(r object) (any, error) {
	receiptRef := model.S(r["receipt"])
	receipt, err := authority.Load(e.FS, receiptRef)
	if err != nil {
		return nil, err
	}
	if model.S(receipt.Data["kind"]) != "context_approval" {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "context mutation requires its own preview approval")
	}
	observed, _, err := observation.Load(e.FS, model.S(receipt.Event["observation_ref"]), model.S(receipt.Event["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	context, _, err := observation.LoadContext(e.FS, model.S(observed["context_ref"]), model.S(observed["context_sha256"]))
	if err != nil {
		return nil, err
	}
	preview := model.M(context["preview"])
	if model.S(preview["mode"]) == "finalize" {
		r, err := finalizationFromPreview(preview)
		if err != nil {
			return nil, err
		}
		outcome, err := contextdocument.FinalizeWithReceipt(e.FS, r, receiptRef)
		if err != nil {
			return nil, err
		}
		return mutationResult(outcome), nil
	}
	typed, err := canonical.Marshal(preview["typed"])
	if err != nil {
		return nil, err
	}
	proposed, err := canonical.Marshal(preview["proposed_provenance"])
	if err != nil {
		return nil, err
	}
	beforeDoc, err := contextDecodeBase64(context["before_document_base64"])
	if err != nil {
		return nil, err
	}
	beforeProvenance, err := contextDecodeBase64(context["before_provenance_base64"])
	if err != nil {
		return nil, err
	}
	if (beforeDoc == nil && preview["expected_document_sha256"] != nil) || (beforeDoc != nil && canonical.BytesHash(beforeDoc) != model.S(preview["expected_document_sha256"])) ||
		(beforeProvenance == nil && preview["expected_provenance_sha256"] != nil) || (beforeProvenance != nil && canonical.BytesHash(beforeProvenance) != model.S(preview["expected_provenance_sha256"])) {
		return nil, fault.New("INVALID_CONTEXT_AUTHORITY", "retained preimages disagree with the approved preview")
	}
	selections := make([]contextdocument.PreviewSelection, 0, len(model.A(preview["selections"])))
	for _, value := range model.A(preview["selections"]) {
		selection := model.M(value)
		selections = append(selections, contextdocument.PreviewSelection{EntryID: model.S(selection["entry_id"]), Anchor: model.S(selection["anchor"])})
	}
	mutation := contextdocument.Mutation{OperationID: model.S(preview["operation_id"]), Mode: model.S(preview["mode"]),
		Typed: typed, Selections: selections, ExpectedDocument: beforeDoc,
		ExpectedProvenance: beforeProvenance, ProposedProvenance: proposed}
	_, binding, err := contextdocument.PreviewBinding(mutation)
	if err != nil || binding != model.S(context["input_sha256"]) {
		return nil, fault.New("INVALID_CONTEXT_AUTHORITY", "retained mutation differs from the approved preview")
	}
	outcome, err := contextdocument.ApplyWithReceipt(e.FS, mutation, receiptRef)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}
