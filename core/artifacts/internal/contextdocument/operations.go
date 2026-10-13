package contextdocument

import (
	"bytes"
	"fmt"
	"os"
	"reflect"
	"regexp"
	"strings"
	"unicode/utf8"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// Mutation is a finite context-document request. Nil expected bytes mean an
// explicitly absent file; present empty bytes are never treated as absent.
type Mutation struct {
	OperationID        string
	Mode               string
	Typed              []byte
	Selections         []PreviewSelection
	ExpectedDocument   []byte
	ExpectedProvenance []byte
	ProposedProvenance []byte
}

// VerifiedAuthority cannot be implemented by a caller outside this package.
// ApplyWithReceipt constructs it only after the owning workflow's verifier.
type VerifiedAuthority interface {
	contextMutationAuthority()
	mutationBinding() string
}
type verifiedAuthority struct{ binding string }

func (verifiedAuthority) contextMutationAuthority() {}
func (a verifiedAuthority) mutationBinding() string { return a.binding }

const contextRendererVersion = "codearbiter.repository-context-renderer/0.1.0"

func previewForMutation(r Mutation) (Preview, error) {
	if r.Mode != "create" && r.Mode != "adopt" && r.Mode != "update" {
		return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", "select create, adopt or update")
	}
	if r.Mode == "create" && r.ExpectedDocument != nil || r.Mode != "create" && r.ExpectedDocument == nil {
		return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", "creation requires absent document; adoption and update require exact existing bytes")
	}
	p, err := RenderPreview(r.Typed, r.ExpectedDocument, r.Mode != "create", r.Selections)
	if err != nil {
		return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", err.Error())
	}
	if r.Mode != "adopt" && bytes.Equal(p.Bytes, r.ExpectedDocument) {
		// A selected field may need fresh reviewed evidence even when its rendered
		// Markdown remains byte-identical. The update still needs a real change
		// to that field's provenance; metadata outside the selection and a pure
		// no-op cannot turn an unchanged document into an authorized mutation.
		if r.Mode != "update" || len(r.Selections) == 0 || bytes.Equal(r.ProposedProvenance, r.ExpectedProvenance) {
			return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", "context mutation must change a selected field or create a document")
		}
		_, oldFields, oldErr := parseProvenanceV2(r.ExpectedProvenance, p)
		_, proposedFields, proposedErr := parseProvenanceV2(r.ProposedProvenance, p)
		if oldErr != nil || proposedErr != nil {
			return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", "unchanged document requires valid existing and proposed v2 provenance")
		}
		changedSelected := false
		for _, selection := range r.Selections {
			oldID, oldField := provenanceFieldForEntry(oldFields, selection.EntryID)
			newID, newField := provenanceFieldForEntry(proposedFields, selection.EntryID)
			if oldID == "" || oldID != newID || oldField["owner_ref"] != selection.Anchor || newField["owner_ref"] != selection.Anchor {
				return Preview{}, fault.New("OWNERSHIP_REQUIRED", "selected field lacks exact provenance ownership")
			}
			if !reflect.DeepEqual(oldField, newField) {
				changedSelected = true
			}
		}
		if !changedSelected {
			return Preview{}, fault.New("INVALID_CONTEXT_MUTATION", "unchanged document requires changed selected-field provenance")
		}
	}
	return p, nil
}

func byteIdentity(b []byte) any {
	if b == nil {
		return nil
	}
	return canonical.BytesHash(b)
}

// mutationBinding is a preview identity, not approval. Its inclusion of the
// renderer version and all byte identities prevents approval of one proposed
// change from being replayed against another source or metadata pair.
func mutationBinding(r Mutation, p Preview) (string, error) {
	selections := make([]any, len(r.Selections))
	for i, selection := range r.Selections {
		selections[i] = map[string]any{"entry_id": selection.EntryID, "anchor": selection.Anchor}
	}
	return canonical.Hash(map[string]any{
		"renderer": contextRendererVersion, "operation_id": r.OperationID, "mode": r.Mode,
		"document_id": p.DocumentID, "target_path": p.TargetPath,
		"typed_sha256": canonical.BytesHash(r.Typed), "selections": selections,
		"before_document_sha256":   byteIdentity(r.ExpectedDocument),
		"before_provenance_sha256": byteIdentity(r.ExpectedProvenance),
		"after_document_sha256":    p.AfterSHA256,
		"after_provenance_sha256":  canonical.BytesHash(r.ProposedProvenance),
	})
}

// PreviewBinding is inert. The returned digest identifies a proposal; it is
// not an approval and never authorizes Apply on its own.
func PreviewBinding(r Mutation) (Preview, string, error) {
	p, err := previewForMutation(r)
	if err != nil {
		return Preview{}, "", err
	}
	binding, err := mutationBinding(r, p)
	if err != nil {
		return Preview{}, "", err
	}
	return p, binding, nil
}

func exactKeys(m map[string]any, keys ...string) bool {
	if len(m) != len(keys) {
		return false
	}
	for _, key := range keys {
		if _, ok := m[key]; !ok {
			return false
		}
	}
	return true
}
func safeText(value any) bool {
	s, ok := value.(string)
	if !ok || s == "" || utf8.RuneCountInString(s) > 256 || !utf8.ValidString(s) {
		return false
	}
	for _, r := range s {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}

var provenanceID = regexp.MustCompile(`^(?:FIELD|CLAIM)-[A-Z0-9]+(?:-[A-Z0-9]+)*$`)

func validProvenanceEvidence(value any) bool {
	m := model.M(value)
	switch model.S(m["kind"]) {
	case "content":
		return exactKeys(m, "kind", "path", "digest_method", "digest") && validate.Path(model.S(m["path"]), false) && m["digest_method"] == "sha256-raw" && digest.MatchString(model.S(m["digest"]))
	case "membership":
		if !exactKeys(m, "kind", "predicate", "scope_paths", "digest_method", "digest") || m["digest_method"] != "sha256-membership-v1" || !digest.MatchString(model.S(m["digest"])) {
			return false
		}
		predicate := model.S(m["predicate"])
		if predicate != "manifests" && predicate != "instructions" && predicate != "configuration" && predicate != "tests" && predicate != "infrastructure" && predicate != "security" && predicate != "data" {
			return false
		}
		scopes := model.A(m["scope_paths"])
		if len(scopes) == 0 || len(scopes) > 32 {
			return false
		}
		seen := map[string]bool{}
		for _, value := range scopes {
			s := model.S(value)
			if !validate.Path(s, true) || seen[s] {
				return false
			}
			seen[s] = true
		}
		return true
	}
	return false
}

// parseProvenanceV2 mirrors the closed existing _provenancelib schema-2 record.
// It validates storage shape and field IDs only; review labels are inert data.
func parseProvenanceV2(raw []byte, p Preview) (map[string]any, map[string]map[string]any, error) {
	record, err := canonical.Object(raw)
	if err != nil || !exactKeys(record, "schema", "doc", "created", "document", "fields") || model.I(record["schema"]) != 2 || record["doc"] != p.DocumentID || !safeText(record["created"]) {
		return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context provenance record")
	}
	document := model.M(record["document"])
	if !exactKeys(document, "path", "digest_method", "digest") || document["path"] != p.TargetPath || document["digest_method"] != "sha256-raw" || document["digest"] != p.AfterSHA256 {
		return nil, nil, fault.New("PROVENANCE_CONFLICT", "document and provenance identities disagree")
	}
	fields := model.A(record["fields"])
	if len(fields) == 0 || len(fields) > 128 {
		return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context provenance fields")
	}
	byID, seen := map[string]map[string]any{}, map[string]bool{}
	for _, value := range fields {
		field := model.M(value)
		id := model.S(field["id"])
		if !exactKeys(field, "id", "owner_ref", "claims") || !strings.HasPrefix(id, "FIELD-") || !provenanceID.MatchString(id) || seen[id] || !safeText(field["owner_ref"]) {
			return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context provenance field")
		}
		seen[id] = true
		byID[id] = field
		claims := model.A(field["claims"])
		if len(claims) == 0 || len(claims) > 128 {
			return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context provenance claims")
		}
		for _, value := range claims {
			claim := model.M(value)
			claimID := model.S(claim["id"])
			review := model.M(claim["semantic_review"])
			if !exactKeys(claim, "id", "semantic_review", "evidence", "effective_authority_refs") || !strings.HasPrefix(claimID, "CLAIM-") || !provenanceID.MatchString(claimID) || seen[claimID] || !exactKeys(review, "state", "reference") {
				return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context provenance claim")
			}
			seen[claimID] = true
			state := model.S(review["state"])
			if state != "unreviewed" && state != "reviewed" && state != "identity_acknowledged" || state == "reviewed" && !safeText(review["reference"]) || review["reference"] != nil && !safeText(review["reference"]) {
				return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported semantic review state")
			}
			evidence := model.A(claim["evidence"])
			if len(evidence) == 0 || len(evidence) > 128 {
				return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context evidence")
			}
			for _, item := range evidence {
				if !validProvenanceEvidence(item) {
					return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context evidence")
				}
			}
			refs, ok := claim["effective_authority_refs"].([]any)
			if !ok {
				return nil, nil, fault.New("OWNERSHIP_REQUIRED", "context authority references must be an array")
			}
			if len(refs) > 32 {
				return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context authority references")
			}
			seenRefs := map[string]bool{}
			for _, ref := range refs {
				s := model.S(ref)
				if !safeText(ref) || seenRefs[s] {
					return nil, nil, fault.New("OWNERSHIP_REQUIRED", "unsupported context authority references")
				}
				seenRefs[s] = true
			}
		}
	}
	return record, byID, nil
}

func currentBytes(f *store.FS, path string) ([]byte, error) {
	b, err := f.Read(path, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, nil
	}
	return b, err
}
func samePreimage(actual, expected []byte) bool {
	return (actual == nil) == (expected == nil) && bytes.Equal(actual, expected)
}

func provenanceFieldForEntry(fields map[string]map[string]any, entryID string) (string, map[string]any) {
	if strings.HasPrefix(entryID, "FIELD-") {
		return entryID, fields[entryID]
	}
	if !strings.HasPrefix(entryID, "CLAIM-") {
		return "", nil
	}
	for fieldID, field := range fields {
		for _, value := range model.A(field["claims"]) {
			if model.S(model.M(value)["id"]) == entryID {
				return fieldID, field
			}
		}
	}
	return "", nil
}

// Apply is closed until the owning workflow supplies an independently
// verified authority object bound to the exact proposed transaction.
func Apply(f *store.FS, r Mutation, authority VerifiedAuthority) (store.Outcome, error) {
	if f == nil {
		return store.Outcome{}, fault.New("INVALID_CONTEXT_MUTATION", "repository store is required")
	}
	p, err := previewForMutation(r)
	if err != nil {
		return store.Outcome{}, err
	}
	if r.Mode == "update" && r.ExpectedProvenance == nil || r.Mode != "update" && r.ExpectedProvenance != nil {
		return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "update requires existing v2 ownership; creation and adoption require absent provenance")
	}
	provenancePath := ".codearbiter/.provenance/" + p.DocumentID + ".json"
	binding, err := mutationBinding(r, p)
	if err != nil {
		return store.Outcome{}, err
	}
	if authority == nil || authority.mutationBinding() != binding {
		return store.Outcome{}, fault.New("AUTHORITY_REQUIRED", "exact context preview lacks owning-workflow authorization")
	}
	// A journaled retry identifies its original request before comparing a now
	// changed target. Different input under the same ID is always rejected.
	replay, err := f.Lookup(r.OperationID, binding)
	if err != nil {
		return store.Outcome{}, err
	}
	if replay != nil {
		return *replay, nil
	} // durable historical outcome, not current freshness
	_, proposedFields, err := parseProvenanceV2(r.ProposedProvenance, p)
	if err != nil {
		return store.Outcome{}, err
	}
	if err := ValidateCurrentEvidence(f, r.ProposedProvenance, p); err != nil {
		return store.Outcome{}, err
	}
	beforeDocument, err := currentBytes(f, p.TargetPath)
	if err != nil {
		return store.Outcome{}, err
	}
	beforeProvenance, err := currentBytes(f, provenancePath)
	if err != nil {
		return store.Outcome{}, err
	}
	if !samePreimage(beforeDocument, r.ExpectedDocument) || !samePreimage(beforeProvenance, r.ExpectedProvenance) {
		return store.Outcome{}, fault.New("REVISION_CONFLICT", "context document or provenance differs from exact expected bytes")
	}
	if pending, err := f.Pending(); err != nil {
		return store.Outcome{}, err
	} else if len(pending) > 0 {
		return store.Outcome{}, fault.New("RECOVERY_REQUIRED", "reconcile pending context transaction before another write")
	}
	selected := map[string]string{}
	if r.Mode == "create" {
		for _, entry := range p.ProposedEntries {
			anchor := "entry:" + entry.ID
			if p.DocumentID == "CONTEXT" && entry.Kind == "identity" && entry.Identity.Field == "project_name" {
				anchor = "project_name"
			}
			selected[entry.ID] = anchor
		}
	} else {
		for _, selection := range r.Selections {
			selected[selection.EntryID] = selection.Anchor
		}
	}
	selectedFields := map[string]bool{}
	for id, anchor := range selected {
		fieldID, field := provenanceFieldForEntry(proposedFields, id)
		if field == nil || field["owner_ref"] != anchor {
			return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "selected field lacks exact provenance ownership")
		}
		if selectedFields[fieldID] {
			return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "multiple entries claim one field selection")
		}
		selectedFields[fieldID] = true
	}
	if r.Mode != "update" && len(selectedFields) != len(proposedFields) {
		return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "provenance fields do not match selected typed fields")
	}
	if r.Mode == "update" {
		priorPreview := p
		priorPreview.AfterSHA256 = canonical.BytesHash(r.ExpectedDocument)
		_, oldFields, err := parseProvenanceV2(r.ExpectedProvenance, priorPreview)
		if err != nil {
			return store.Outcome{}, err
		}
		if len(oldFields) != len(proposedFields) {
			return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "update cannot add or remove ownership fields")
		}
		for id, oldField := range oldFields {
			newField := proposedFields[id]
			if newField == nil || oldField["owner_ref"] != newField["owner_ref"] {
				return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "update cannot transfer field ownership")
			}
			if !selectedFields[id] && !reflect.DeepEqual(oldField, newField) {
				return store.Outcome{}, fault.New("OWNERSHIP_REQUIRED", "unselected provenance field changed")
			}
		}
	}
	if len(p.Bytes) > canonical.MaxBytes || len(r.ProposedProvenance) > canonical.MaxBytes {
		return store.Outcome{}, fault.New("MAX_BYTES", "context transaction exceeds byte limit")
	}
	result := map[string]any{"document_id": p.DocumentID, "target_path": p.TargetPath, "document_sha256": p.AfterSHA256, "provenance_sha256": canonical.BytesHash(r.ProposedProvenance), "mode": r.Mode}
	out, err := f.Commit(r.OperationID, binding, []store.Edit{
		{Path: p.TargetPath, Before: r.ExpectedDocument, After: p.Bytes},
		{Path: provenancePath, Before: r.ExpectedProvenance, After: r.ProposedProvenance},
	}, result)
	if err != nil {
		return out, err
	}
	if len(out.Paths) != 2 || out.Paths[0] != p.TargetPath || out.Paths[1] != provenancePath {
		return store.Outcome{}, fmt.Errorf("unexpected context transaction paths")
	}
	return out, nil
}

// ApplyWithReceipt is the production admission seam. The receipt reference is
// only a locator: authority independently loads and verifies the observed
// owning-workflow source, exact context preview and current source evidence.
// The caller must hold the repository store's exclusive writer lock.
func ApplyWithReceipt(f *store.FS, r Mutation, receiptRef string) (store.Outcome, error) {
	if f == nil {
		return store.Outcome{}, fault.New("INVALID_CONTEXT_MUTATION", "repository store is required")
	}
	_, binding, err := PreviewBinding(r)
	if err != nil {
		return store.Outcome{}, err
	}
	if replay, err := f.Lookup(r.OperationID, binding); err != nil {
		return store.Outcome{}, err
	} else if replay != nil {
		return *replay, nil
	}
	if err := authority.ValidateContextPreview(f, receiptRef, binding); err != nil {
		return store.Outcome{}, err
	}
	return Apply(f, r, verifiedAuthority{binding: binding})
}
