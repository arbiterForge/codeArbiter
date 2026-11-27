package contextdocument

import (
	"encoding/base64"
	"regexp"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// PreviewFormat is the stored record format of an ordinary context preview.
// PreviewDirectory is its reserved output directory under .codearbiter/.artifacts.
// Both the producer (context-preview) and every strict output consumer
// (snapshot, normalized completion) use this one contract.
const PreviewFormat = "codearbiter.context-preview/0.1.0"
const PreviewDirectory = "context-previews"

var previewOperationID = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$`)

func invalidPreview(message string) error {
	return fault.New("INVALID_CONTEXT_PREVIEW", message)
}

// PreviewImage decodes a retained before-image: null stays absent, otherwise
// strict standard base64 bounded by the canonical byte limit.
func PreviewImage(value any) ([]byte, error) {
	if value == nil {
		return nil, nil
	}
	encoded, ok := value.(string)
	if !ok {
		return nil, invalidPreview("context preview before-image has an invalid encoding")
	}
	if base64.StdEncoding.DecodedLen(len(encoded)) > canonical.MaxBytes+3 {
		return nil, invalidPreview("context preview before-image is oversized")
	}
	decoded, err := base64.StdEncoding.Strict().DecodeString(encoded)
	if err != nil || len(decoded) > canonical.MaxBytes {
		return nil, invalidPreview("context preview before-image is malformed or oversized")
	}
	return decoded, nil
}

func previewDigest(value any, nullable bool) bool {
	if value == nil {
		return nullable
	}
	s, ok := value.(string)
	return ok && digest.MatchString(s)
}

// ValidateStoredPreview checks the stored format of a retained ordinary
// context preview record. It is deliberately not an applicability check: a
// preview whose target bytes have since changed is still a valid historical
// output; context-apply alone compares it with current preimages. It reads no
// repository file and grants no authority.
func ValidateStoredPreview(raw []byte) error {
	record, err := canonical.Object(raw)
	if err != nil {
		return invalidPreview("context preview is not a canonical object")
	}
	if _, err = closed(record, "format", "request", "preview_binding_sha256", "before_document_base64", "before_provenance_base64"); err != nil {
		return invalidPreview("context preview has unknown or missing fields")
	}
	if record["format"] != PreviewFormat {
		return invalidPreview("unsupported context preview format")
	}
	if !previewDigest(record["preview_binding_sha256"], false) {
		return invalidPreview("context preview binding is not a digest")
	}
	beforeDocument, err := PreviewImage(record["before_document_base64"])
	if err != nil {
		return err
	}
	beforeProvenance, err := PreviewImage(record["before_provenance_base64"])
	if err != nil {
		return err
	}
	request, ok := record["request"].(map[string]any)
	if !ok {
		return invalidPreview("context preview request is not an object")
	}
	if id, _ := request["operation_id"].(string); !previewOperationID.MatchString(id) {
		return invalidPreview("context preview operation ID is malformed")
	}
	if request["mode"] == "finalize" {
		if _, err = closed(request, "operation_id", "mode", "document_id", "target_path", "expected"); err != nil ||
			request["document_id"] != "CONTEXT" || request["target_path"] != documents["CONTEXT"].path {
			return invalidPreview("finalization preview must name only CONTEXT and its exact outputs")
		}
		values, ok := request["expected"].(map[string]any)
		if !ok {
			return invalidPreview("finalization output identities are required")
		}
		expected := make(map[string]string, len(values))
		for path, value := range values {
			s, ok := value.(string)
			if !ok {
				return invalidPreview("finalization output identity is malformed")
			}
			expected[path] = s
		}
		binding, err := FinalizationBinding(Finalization{OperationID: request["operation_id"].(string), Expected: expected})
		if err != nil || binding != record["preview_binding_sha256"] {
			return invalidPreview("finalization preview binding does not match its outputs")
		}
		return nil
	}
	if _, err = closed(request, "operation_id", "mode", "document_id", "target_path", "typed", "selections",
		"expected_document_sha256", "expected_provenance_sha256", "proposed_provenance"); err != nil {
		return invalidPreview("context preview request has unknown or missing fields")
	}
	switch request["mode"] {
	case "create", "adopt", "update":
	default:
		return invalidPreview("unsupported context preview mode")
	}
	id, _ := request["document_id"].(string)
	contract, known := documents[id]
	if !known || request["target_path"] != contract.path {
		return invalidPreview("context preview target is not its document's canonical path")
	}
	typed, err := canonical.Marshal(request["typed"])
	if err != nil {
		return invalidPreview("context preview typed document is not canonical")
	}
	doc, err := Validate(typed)
	if err != nil || doc.DocumentID != id || doc.TargetPath != contract.path {
		return invalidPreview("context preview typed document disagrees with its target")
	}
	selections, ok := request["selections"].([]any)
	if !ok || len(selections) > 128 {
		return invalidPreview("context preview selections are malformed")
	}
	for _, value := range selections {
		selection, err := closed(value, "entry_id", "anchor")
		if err != nil {
			return invalidPreview("context preview selection is malformed")
		}
		for _, key := range []string{"entry_id", "anchor"} {
			if s, ok := selection[key].(string); !ok || s == "" {
				return invalidPreview("context preview selection is malformed")
			}
		}
	}
	if _, ok := request["proposed_provenance"].(map[string]any); !ok {
		return invalidPreview("context preview provenance is not an object")
	}
	// The producer admits a preview only when each recorded preimage matches its
	// expected identity, so a retained record must still agree with itself.
	for _, pair := range []struct {
		expected any
		image    []byte
	}{{request["expected_document_sha256"], beforeDocument}, {request["expected_provenance_sha256"], beforeProvenance}} {
		if !previewDigest(pair.expected, true) || (pair.expected == nil) != (pair.image == nil) ||
			(pair.image != nil && canonical.BytesHash(pair.image) != pair.expected) {
			return invalidPreview("context preview preimage disagrees with its expected identity")
		}
	}
	return nil
}
