// Package authority verifies content-addressed cooperative workflow attestations.
// It does not claim that same-user filesystem access is an identity boundary.
// A host adapter must capture an actual existing workflow event; a valid hash
// alone does not establish that the human/reviewer action really occurred.
package authority

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
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
	return obj(map[string]any{"format": map[string]any{"const": "codearbiter.receipt/0.1.0"}, "kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}, "authority_kind": map[string]any{"enum": model.List("user_workflow", "smarts_workflow", "review_workflow", "verification_runner")}, "subject": subjectSchema(), "event_sha256": digestSchema()}, "format", "kind", "authority_kind", "subject", "event_sha256")
}
func EventSchema() map[string]any {
	return obj(map[string]any{"format": map[string]any{"const": "codearbiter.workflow-event/0.1.0"}, "kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")}, "authority_kind": map[string]any{"enum": model.List("user_workflow", "smarts_workflow", "review_workflow", "verification_runner")}, "subject": subjectSchema(), "actor": str(), "origin": str(), "verdict": map[string]any{"enum": model.List("approved", "passed", "satisfied", "reconciled")}, "payload": map[string]any{"type": "object"}, "source_text": str()}, "format", "kind", "authority_kind", "subject", "actor", "origin", "verdict", "payload", "source_text")
}
func first(es []fault.Error) error {
	if len(es) > 0 {
		return &es[0]
	}
	return nil
}
func Ref(sha string) string      { return Root + "/receipts/" + sha + ".json" }
func EventRef(sha string) string { return Root + "/events/" + sha + ".json" }
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

type Receipt struct {
	Data, Event           map[string]any
	Path, Hash, EventPath string
}

func Load(f *store.FS, p string) (*Receipt, error) {
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
	if e = first(schema.ValidateWith(ReceiptSchema(), r)); e != nil {
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
	return &Receipt{r, ev, p, h, ep}, nil
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

// Vector includes receipt AND event bytes. It never authenticates a cursor.
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
		r, e := Load(f, p)
		if e != nil {
			return nil, e
		}
		out[p] = r.Hash
		out[r.EventPath] = model.S(r.Data["event_sha256"])
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
	}
	return out
}
