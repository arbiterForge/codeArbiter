package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

const contextPreviewFormat = "codearbiter.context-preview/0.1.0"
const contextPreviewRoot = ".codearbiter/.artifacts/context-previews/"

func contextMutationFromPreview(preview object, beforeDoc, beforeProvenance []byte) (contextdocument.Mutation, error) {
	typed, err := canonical.Marshal(preview["typed"])
	if err != nil {
		return contextdocument.Mutation{}, err
	}
	proposed, err := canonical.Marshal(preview["proposed_provenance"])
	if err != nil {
		return contextdocument.Mutation{}, err
	}
	doc, err := contextdocument.Validate(typed)
	if err != nil || doc.DocumentID != model.S(preview["document_id"]) || doc.TargetPath != model.S(preview["target_path"]) {
		return contextdocument.Mutation{}, fault.New("INVALID_CONTEXT_MUTATION", "typed document and canonical target disagree")
	}
	if (beforeDoc == nil && preview["expected_document_sha256"] != nil) || (beforeDoc != nil && canonical.BytesHash(beforeDoc) != model.S(preview["expected_document_sha256"])) ||
		(beforeProvenance == nil && preview["expected_provenance_sha256"] != nil) || (beforeProvenance != nil && canonical.BytesHash(beforeProvenance) != model.S(preview["expected_provenance_sha256"])) {
		return contextdocument.Mutation{}, fault.New("REVISION_CONFLICT", "context preimages differ from expected identities")
	}
	selections := make([]contextdocument.PreviewSelection, 0, len(model.A(preview["selections"])))
	for _, value := range model.A(preview["selections"]) {
		s := model.M(value)
		selections = append(selections, contextdocument.PreviewSelection{EntryID: model.S(s["entry_id"]), Anchor: model.S(s["anchor"])})
	}
	return contextdocument.Mutation{OperationID: model.S(preview["operation_id"]), Mode: model.S(preview["mode"]), Typed: typed, Selections: selections, ExpectedDocument: beforeDoc, ExpectedProvenance: beforeProvenance, ProposedProvenance: proposed}, nil
}

// contextOrdinaryPreview retains an inert proposal and exact preimages for a
// retryable transaction. It creates no approval, observation or review claim.
func (e *Engine) contextOrdinaryPreview(r object, finalize bool) (any, error) {
	preview := object{}
	for key, value := range r {
		if key != "protocol" {
			preview[key] = value
		}
	}
	if !finalize {
		typed, err := canonical.Marshal(preview["typed"])
		if err != nil {
			return nil, err
		}
		doc, err := contextdocument.Validate(typed)
		if err != nil || doc.DocumentID != model.S(preview["document_id"]) || doc.TargetPath != model.S(preview["target_path"]) {
			return nil, fault.New("INVALID_CONTEXT_MUTATION", "typed document and canonical target disagree")
		}
	}
	beforeDoc, err := contextSourceBytes(e.FS, model.S(preview["target_path"]))
	if err != nil {
		return nil, err
	}
	beforeProvenance, err := contextSourceBytes(e.FS, ".codearbiter/.provenance/"+model.S(preview["document_id"])+".json")
	if err != nil {
		return nil, err
	}
	var body []byte
	var binding string
	var changes []contextdocument.PreviewChange
	if finalize {
		fr, err := finalizationFromPreview(preview)
		if err != nil {
			return nil, err
		}
		p, err := contextdocument.PreviewFinalization(e.FS, fr)
		if err != nil {
			return nil, err
		}
		body, binding = p.Document, p.Binding
		changes = []contextdocument.PreviewChange{{Kind: "finalize", Anchor: "initialization", Old: string(beforeDoc), New: string(body)}}
	} else {
		m, err := contextMutationFromPreview(preview, beforeDoc, beforeProvenance)
		if err != nil {
			return nil, err
		}
		p, hash, err := contextdocument.PreviewBinding(m)
		if err != nil {
			return nil, err
		}
		if err := contextdocument.ValidateCurrentEvidence(e.FS, m.ProposedProvenance, p); err != nil {
			return nil, err
		}
		body, binding, changes = p.Bytes, hash, p.Changes
	}
	record := object{"format": contextPreviewFormat, "request": preview, "preview_binding_sha256": binding, "before_document_base64": contextBase64(beforeDoc), "before_provenance_base64": contextBase64(beforeProvenance)}
	raw, err := canonical.Marshal(record)
	if err != nil {
		return nil, err
	}
	hash := canonical.BytesHash(raw)
	if err := e.FS.PutDerived("context-previews", hash, raw); err != nil {
		return nil, err
	}
	out := object{"preview_ref": contextPreviewRoot + hash + ".json", "preview_sha256": hash, "preview_binding_sha256": binding, "document_id": preview["document_id"], "target_path": preview["target_path"], "preview_document": string(body), "after_document_sha256": canonical.BytesHash(body), "evidence_assessed": false, "changes_omitted": int64(0), "preview_content_omitted": false}
	compact := make([]any, 0, len(changes))
	for i, c := range changes {
		if i == 32 {
			out["changes_omitted"] = int64(len(changes) - i)
			break
		}
		compact = append(compact, object{"entry_id": c.EntryID, "kind": c.Kind, "field": c.Field, "anchor": c.Anchor, "start": int64(c.Span.Start), "end": int64(c.Span.End), "old": c.Old, "new": c.New, "old_sha256": canonical.BytesHash([]byte(c.Old)), "new_sha256": canonical.BytesHash([]byte(c.New)), "old_bytes": int64(len(c.Old)), "new_bytes": int64(len(c.New)), "content_omitted": false})
	}
	out["changes"] = compact
	encoded, err := canonical.Marshal(out)
	if err != nil {
		return nil, err
	}
	if len(encoded) > 60*1024 {
		out["preview_document"], out["preview_content_omitted"] = nil, true
		for _, value := range compact {
			c := model.M(value)
			c["old"], c["new"], c["content_omitted"] = nil, nil, true
		}
	}
	return out, nil
}

func (e *Engine) contextOrdinaryApply(r object) (any, error) {
	hash := model.S(r["preview_sha256"])
	if model.S(r["preview_ref"]) != contextPreviewRoot+hash+".json" {
		return nil, fault.New("INVALID_CONTEXT_PREVIEW", "preview reference must name its exact digest")
	}
	raw, err := e.FS.Read(model.S(r["preview_ref"]), canonical.MaxBytes)
	if err != nil {
		return nil, err
	}
	if canonical.BytesHash(raw) != hash {
		return nil, fault.New("INVALID_CONTEXT_PREVIEW", "preview bytes changed")
	}
	record, err := canonical.Object(raw)
	if err != nil || len(record) != 5 || record["format"] != contextPreviewFormat {
		return nil, fault.New("INVALID_CONTEXT_PREVIEW", "unsupported context preview")
	}
	preview := model.M(record["request"])
	input := object{"protocol": Protocol}
	for k, v := range preview {
		input[k] = v
	}
	if model.S(preview["mode"]) == "finalize" {
		if err := CheckRequest("context-finalize-preview", input); err != nil {
			return nil, err
		}
		fr, err := finalizationFromPreview(preview)
		if err != nil {
			return nil, err
		}
		binding, err := contextdocument.FinalizationBinding(fr)
		if err != nil || binding != model.S(record["preview_binding_sha256"]) {
			return nil, fault.New("INVALID_CONTEXT_PREVIEW", "finalization binding changed")
		}
		out, err := contextdocument.FinalizeOrdinary(e.FS, fr)
		if err != nil {
			return nil, err
		}
		return mutationResult(out), nil
	}
	if err := CheckRequest("context-preview", input); err != nil {
		return nil, err
	}
	beforeDoc, err := contextDecodeBase64(record["before_document_base64"])
	if err != nil {
		return nil, err
	}
	beforeProvenance, err := contextDecodeBase64(record["before_provenance_base64"])
	if err != nil {
		return nil, err
	}
	m, err := contextMutationFromPreview(preview, beforeDoc, beforeProvenance)
	if err != nil {
		return nil, err
	}
	_, binding, err := contextdocument.PreviewBinding(m)
	if err != nil || binding != model.S(record["preview_binding_sha256"]) {
		return nil, fault.New("INVALID_CONTEXT_PREVIEW", "retained mutation binding changed")
	}
	out, err := contextdocument.ApplyOrdinary(e.FS, m)
	if err != nil {
		return nil, err
	}
	return mutationResult(out), nil
}
