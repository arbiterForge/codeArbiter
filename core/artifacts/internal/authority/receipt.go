// Package authority verifies content-addressed cooperative workflow attestations.
// It does not claim that same-user filesystem access is an identity boundary.
// A host adapter must capture an actual existing workflow event; a valid hash
// alone does not establish that the human/reviewer action really occurred.
package authority

import (
	"bytes"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"path"
	"regexp"
	"strings"
)

const Root = ".codearbiter/.artifacts"

var digest = regexp.MustCompile(`^[0-9a-f]{64}$`)

func str() map[string]any { return map[string]any{"type": "string", "minLength": int64(1)} }
func obj(props map[string]any, required ...string) map[string]any {
	return map[string]any{"type": "object", "properties": props, "required": model.List(required...), "additionalProperties": false}
}
func digestSchema() map[string]any {
	return map[string]any{"type": "string", "pattern": digest.String()}
}
func subjectSchema() map[string]any {
	return obj(map[string]any{"artifact_id": str(), "normative_sha256": digestSchema(), "record_id": str()}, "artifact_id", "normative_sha256", "record_id")
}
func ReceiptSchema() map[string]any {
	return obj(map[string]any{"format": map[string]any{"const": "codearbiter.receipt/0.2.0"}, "kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}, "authority_kind": map[string]any{"enum": model.List("user_workflow", "smarts_workflow", "review_workflow", "verification_runner")}, "subject": subjectSchema(), "event_sha256": digestSchema(), "authority_source_ref": str(), "authority_source_sha256": digestSchema()}, "format", "kind", "authority_kind", "subject", "event_sha256", "authority_source_ref", "authority_source_sha256")
}
func legacyReceiptSchema() map[string]any {
	return obj(map[string]any{"format": map[string]any{"const": "codearbiter.receipt/0.1.0"}, "kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}, "authority_kind": map[string]any{"enum": model.List("user_workflow", "smarts_workflow", "review_workflow", "verification_runner")}, "subject": subjectSchema(), "event_sha256": digestSchema()}, "format", "kind", "authority_kind", "subject", "event_sha256")
}
func EventSchema() map[string]any {
	base := map[string]any{"kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}, "authority_kind": map[string]any{"enum": model.List("user_workflow", "smarts_workflow", "review_workflow", "verification_runner")}, "subject": subjectSchema(), "actor": str(), "origin": str(), "verdict": map[string]any{"enum": model.List("approved", "passed", "satisfied", "reconciled")}, "payload": map[string]any{"type": "object"}, "source_text": str()}
	legacy := map[string]any{}
	for k, v := range base {
		legacy[k] = v
	}
	legacy["format"] = map[string]any{"const": "codearbiter.workflow-event/0.1.0"}
	observed := map[string]any{}
	for k, v := range base {
		observed[k] = v
	}
	observed["format"] = map[string]any{"const": "codearbiter.workflow-event/0.2.0"}
	observed["kind"] = map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}
	observed["observation_ref"] = str()
	observed["observation_sha256"] = digestSchema()
	return map[string]any{"oneOf": []any{
		obj(legacy, "format", "kind", "authority_kind", "subject", "actor", "origin", "verdict", "payload", "source_text"),
		obj(observed, "format", "kind", "authority_kind", "subject", "actor", "origin", "verdict", "payload", "source_text", "observation_ref", "observation_sha256"),
	}}
}
func first(es []fault.Error) error {
	if len(es) > 0 {
		return &es[0]
	}
	return nil
}
func Ref(sha string) string       { return Root + "/receipts/" + sha + ".json" }
func EventRef(sha string) string  { return Root + "/events/" + sha + ".json" }
func SourceRef(sha string) string { return Root + "/authority-sources/" + sha + ".json" }
func refHash(p, sub string) (string, error) {
	if path.Dir(p) != Root+"/"+sub || !strings.HasSuffix(p, ".json") {
		return "", fault.New("INVALID_RECEIPT", "receipt/event path is not in its content-addressed store")
	}
	h := strings.TrimSuffix(path.Base(p), ".json")
	if !digest.MatchString(h) {
		return "", fault.New("INVALID_RECEIPT", "invalid content-addressed name")
	}
	return h, nil
}

// LoadSource reads the host-owned, content-addressed workflow event that the
// adapter captured from its existing authority boundary. The request supplies
// only a locator and digest; authority labels are taken from these independently
// read bytes. This remains a cooperative same-user filesystem boundary, not
// cryptographic identity authentication.
func LoadSource(f *store.FS, p, expected string) (map[string]any, []byte, error) {
	h, err := refHash(p, "authority-sources")
	if err != nil || h != expected {
		return nil, nil, fault.New("AUTHORITY_UNVERIFIED", "authority source locator and digest do not agree")
	}
	b, err := f.Read(p, 1<<20)
	if err != nil || canonical.BytesHash(b) != expected {
		return nil, nil, fault.New("AUTHORITY_UNVERIFIED", "authority source is unavailable or changed")
	}
	ev, err := canonical.Object(b)
	if err != nil {
		return nil, nil, fault.New("AUTHORITY_UNVERIFIED", "authority source is not canonical workflow-event JSON")
	}
	if err = first(schema.ValidateWith(EventSchema(), ev)); err != nil {
		return nil, nil, err
	}
	if err = ValidateEvent(ev); err != nil {
		return nil, nil, err
	}
	return ev, b, nil
}

type Receipt struct {
	Data, Event           map[string]any
	Path, Hash, EventPath string
}

// Inspect validates and returns a content-addressed receipt for evidence
// inventory. Legacy receipts remain inspectable so repositories can preserve
// their history while acquiring fresh authority, but callers must use Load
// before allowing a receipt to confer authority.
func Inspect(f *store.FS, p string) (*Receipt, error) {
	h, e := refHash(p, "receipts")
	if e != nil {
		return nil, e
	}
	b, e := f.Read(p, 1<<20)
	if e != nil {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "receipt is unavailable")
	}
	if canonical.BytesHash(b) != h {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "receipt bytes changed")
	}
	r, e := canonical.Object(b)
	if e != nil {
		return nil, e
	}
	receiptFormat := model.S(r["format"])
	receiptSchema := ReceiptSchema()
	if receiptFormat == "codearbiter.receipt/0.1.0" {
		receiptSchema = legacyReceiptSchema()
	}
	if e = first(schema.ValidateWith(receiptSchema, r)); e != nil {
		return nil, e
	}
	ep := EventRef(model.S(r["event_sha256"]))
	eb, e := f.Read(ep, 1<<20)
	if e != nil || canonical.BytesHash(eb) != model.S(r["event_sha256"]) {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "captured workflow event is absent or changed")
	}
	ev, e := canonical.Object(eb)
	if e != nil {
		return nil, e
	}
	if e = first(schema.ValidateWith(EventSchema(), ev)); e != nil {
		return nil, e
	}
	for _, k := range []string{"kind", "authority_kind", "subject"} {
		a, _ := canonical.Hash(r[k])
		b, _ := canonical.Hash(ev[k])
		if a != b {
			return nil, fault.New("AUTHORITY_UNVERIFIED", "receipt disagrees with its captured workflow event")
		}
	}
	if e = ValidateEvent(ev); e != nil {
		return nil, e
	}
	if model.S(ev["format"]) == "codearbiter.workflow-event/0.2.0" {
		observed, _, observedErr := observation.Inspect(f, model.S(ev["observation_ref"]), model.S(ev["observation_sha256"]))
		if observedErr != nil {
			return nil, observedErr
		}
		contextRef, contextHash := model.S(observed["context_ref"]), model.S(observed["context_sha256"])
		context, _, contextErr := observation.LoadContext(f, contextRef, contextHash)
		if contextErr != nil {
			return nil, contextErr
		}
		if linkErr := observation.ValidateLink(ev, observed, context, contextRef, contextHash); linkErr != nil {
			return nil, linkErr
		}
	}
	if receiptFormat == "codearbiter.receipt/0.2.0" {
		_, sourceBytes, sourceErr := LoadSource(f, model.S(r["authority_source_ref"]), model.S(r["authority_source_sha256"]))
		if sourceErr != nil || !bytes.Equal(sourceBytes, eb) || model.S(r["authority_source_sha256"]) != model.S(r["event_sha256"]) {
			return nil, fault.New("AUTHORITY_UNVERIFIED", "captured event no longer matches its policy-owned authority source")
		}
	}
	return &Receipt{r, ev, p, h, ep}, nil
}

func Load(f *store.FS, p string) (*Receipt, error) {
	r, err := Inspect(f, p)
	if err != nil {
		return nil, err
	}
	if model.S(r.Data["format"]) == "codearbiter.receipt/0.1.0" {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "legacy receipt remains readable but requires a fresh policy-owned attestation")
	}
	if model.S(r.Event["format"]) != "codearbiter.workflow-event/0.2.0" {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "legacy workflow event remains readable but cannot confer current authority")
	}
	if model.S(r.Event["format"]) == "codearbiter.workflow-event/0.2.0" {
		observed, _, observationErr := observation.Load(f, model.S(r.Event["observation_ref"]), model.S(r.Event["observation_sha256"]))
		if observationErr != nil || model.S(observed["format"]) != "codearbiter.observation/0.2.0" {
			return nil, fault.New("AUTHORITY_UNVERIFIED", "legacy observation remains inspectable but requires fresh production evidence")
		}
	}
	return r, nil
}
func (r *Receipt) Subject(d *model.Document, id, kind string) error {
	s := model.M(r.Data["subject"])
	if model.S(r.Data["kind"]) != kind || model.S(s["artifact_id"]) != d.ID() || model.S(s["normative_sha256"]) != d.NormHash() || model.S(s["record_id"]) != id {
		return fault.New("STALE_EVIDENCE", "receipt does not apply to this artifact, definition and subject")
	}
	return nil
}
func (r *Receipt) Payload() map[string]any { return model.M(r.Event["payload"]) }
func Approved(f *store.FS, d *model.Document) (*Receipt, error) {
	gov := model.M(d.Data["governance"])
	if model.S(gov["state"]) != "approved" {
		return nil, fault.New("AUTHORITY_UNVERIFIED", "artifact has not been approved by its workflow")
	}
	for _, v := range model.A(gov["approvals"]) {
		a := model.M(v)
		if model.S(a["normative_sha256"]) != d.NormHash() || model.S(a["artifact_id"]) != d.ID() {
			continue
		}
		r, e := Load(f, model.S(a["source_ref"]))
		if e != nil {
			continue
		}
		if r.Hash != model.S(a["source_sha256"]) || model.S(r.Data["authority_kind"]) != model.S(a["authority_kind"]) {
			continue
		}
		if e = r.Subject(d, d.ID(), "approval"); e == nil {
			return r, nil
		}
	}
	return nil, fault.New("AUTHORITY_UNVERIFIED", "no current, source-verified workflow approval")
}
func ApprovalRecord(r *Receipt, d *model.Document) map[string]any {
	return map[string]any{"artifact_id": d.ID(), "authority_kind": r.Data["authority_kind"], "source_ref": r.Path, "source_sha256": r.Hash, "normative_sha256": d.NormHash(), "attestation_level": "workflow_attested"}
}
func Status(f *store.FS, d *model.Document) map[string]any {
	_, e := Approved(f, d)
	out := map[string]any{"state": model.M(d.Data["governance"])["state"], "authority_verified": e == nil, "trust_model": "cooperative workflow attestation"}
	if e != nil {
		out["diagnostic"] = fault.Code(e)
	}
	return out
}

// Vector includes receipt AND event bytes. It is an inspection dependency
// vector, not an authority decision: retained legacy evidence must keep reads
// reproducible without making that evidence current. It never authenticates a
// cursor.
func Vector(f *store.FS, docs ...*model.Document) (map[string]any, error) {
	out := map[string]any{}
	refs := map[string]bool{}
	for _, d := range docs {
		for _, v := range model.A(model.M(d.Data["governance"])["approvals"]) {
			refs[model.S(model.M(v)["source_ref"])] = true
		}
		if d.Kind() == "plan" {
			ex := model.M(d.Data["execution"])
			for _, v := range model.M(ex["tasks"]) {
				for _, r := range model.Strings(model.M(v)["evidence_refs"]) {
					refs[r] = true
				}
			}
			for _, v := range model.M(ex["prerequisite_evidence"]) {
				for _, r := range model.Strings(v) {
					refs[r] = true
				}
			}
		}
	}
	for p := range refs {
		r, e := Inspect(f, p)
		if e != nil {
			return nil, e
		}
		out[p] = r.Hash
		out[r.EventPath] = model.S(r.Data["event_sha256"])
		if model.S(r.Event["format"]) == "codearbiter.workflow-event/0.2.0" {
			observationRef := model.S(r.Event["observation_ref"])
			out[observationRef] = model.S(r.Event["observation_sha256"])
			observed, _, loadErr := observation.Inspect(f, observationRef, model.S(r.Event["observation_sha256"]))
			if loadErr != nil {
				return nil, loadErr
			}
			out[model.S(observed["context_ref"])] = model.S(observed["context_sha256"])
		}
		if model.S(r.Data["format"]) == "codearbiter.receipt/0.2.0" {
			out[model.S(r.Data["authority_source_ref"])] = model.S(r.Data["authority_source_sha256"])
		}
	}
	return out, nil
}

// ValidateEvent checks kind/authority/verdict without filesystem side effects.
func ValidateEvent(ev map[string]any) error {
	if es := schema.ValidateWith(EventSchema(), ev); len(es) > 0 {
		return &es[0]
	}
	kind, authority, verdict := model.S(ev["kind"]), model.S(ev["authority_kind"]), model.S(ev["verdict"])
	switch kind {
	case "approval":
		if (authority != "user_workflow" && authority != "smarts_workflow") || verdict != "approved" {
			return fault.New("AUTHORITY_UNVERIFIED", "approval must come from the existing user or SMARTS approval path")
		}
	case "verification":
		if authority != "verification_runner" || verdict != "passed" {
			return fault.New("AUTHORITY_UNVERIFIED", "verification needs a passed runner event")
		}
	case "spec_review", "quality_review":
		if authority != "review_workflow" || verdict != "passed" {
			return fault.New("AUTHORITY_UNVERIFIED", "review needs a passed reviewer event")
		}
	case "prerequisite":
		if (authority != "user_workflow" && authority != "smarts_workflow") || verdict != "satisfied" {
			return fault.New("AUTHORITY_UNVERIFIED", "prerequisite must come from the existing user or SMARTS workflow")
		}
	case "reconciliation":
		if (authority != "user_workflow" && authority != "smarts_workflow") || verdict != "reconciled" {
			return fault.New("AUTHORITY_UNVERIFIED", "reconciliation must come from the existing user or SMARTS workflow")
		}
	case "farm_authorization":
		if (authority != "user_workflow" && authority != "smarts_workflow") || verdict != "approved" {
			return fault.New("AUTHORITY_UNVERIFIED", "farm authorization requires current workflow authority")
		}
	}
	return nil
}

// InspectionVector fingerprints every approval input, including missing or
// corrupt sources. Unlike Vector it permits an unverified catalog row, but a
// cursor can never silently cross a receipt/event change between pages.
func InspectionVector(f *store.FS, d *model.Document) map[string]any {
	out := map[string]any{}
	read := func(p string) []byte {
		b, err := f.Read(p, 1<<20)
		if err != nil {
			out[p] = map[string]any{"unavailable": true}
			return nil
		}
		out[p] = canonical.BytesHash(b)
		return b
	}
	for _, value := range model.A(model.M(d.Data["governance"])["approvals"]) {
		p := model.S(model.M(value)["source_ref"])
		if _, err := refHash(p, "receipts"); err != nil {
			out[p] = "invalid_reference"
			continue
		}
		b := read(p)
		if b == nil {
			continue
		}
		receipt, err := canonical.Object(b)
		if err != nil {
			continue
		}
		h := model.S(receipt["event_sha256"])
		if digest.MatchString(h) {
			read(EventRef(h))
		}
		if model.S(receipt["format"]) == "codearbiter.receipt/0.2.0" {
			source := model.S(receipt["authority_source_ref"])
			if _, err := refHash(source, "authority-sources"); err == nil {
				read(source)
			}
		}
	}
	return out
}
