package operations

import (
	"bytes"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"os"
	"strings"
)

// capture records a host-owned cooperative attestation. The request contains
// only the exact source locator and digest; it cannot manufacture authority by
// supplying kind, authority_kind or verdict labels. It NEVER asserts that the
// source text proves a human identity or executes the claimed tests. Immutable
// objects are independently verifiable; retry completes a missing receipt after
// an interrupted event write without modifying an artifact.
func (e *Engine) capture(r object) (any, error) {
	ev, eb, err := authority.LoadSource(e.FS, model.S(r["source_ref"]), model.S(r["source_sha256"]))
	if err != nil {
		return nil, err
	}
	subject := model.M(ev["subject"])
	entry, err := e.Catalog.Resolve(model.S(subject["artifact_id"]))
	if err != nil {
		return nil, err
	}
	d := entry.Doc
	if model.S(subject["normative_sha256"]) != d.NormHash() {
		return nil, fault.New("STALE_EVIDENCE", "event names an outdated definition")
	}
	sid := model.S(subject["record_id"])
	if sid != d.ID() {
		if r, ok := d.Symbols.ByID[sid]; !ok || r.Retired {
			return nil, fault.New("UNKNOWN_SUBJECT", "event subject is absent or retired")
		}
	}
	kind := model.S(ev["kind"])
	if kind == "verification" || kind == "spec_review" || kind == "quality_review" {
		if es := schema.ValidateWith(evidence.PayloadSchema(kind), ev["payload"]); len(es) > 0 {
			return nil, &es[0]
		}
	}
	eh := canonical.BytesHash(eb)
	receipt := object{"format": "codearbiter.receipt/0.2.0", "kind": ev["kind"], "authority_kind": ev["authority_kind"], "subject": subject, "event_sha256": eh, "authority_source_ref": r["source_ref"], "authority_source_sha256": r["source_sha256"]}
	rb, err := canonical.Marshal(receipt)
	if err != nil {
		return nil, err
	}
	rh := canonical.BytesHash(rb)
	ep, rp := authority.EventRef(eh), authority.Ref(rh)
	for _, item := range []struct {
		p     string
		b     []byte
		write func() error
	}{{ep, eb, func() error { return e.FS.PutEvent(eh, eb) }}, {rp, rb, func() error { return e.FS.PutReceipt(rh+".json", rb) }}} {
		old, readErr := e.FS.Read(item.p, 1<<20)
		if readErr == nil {
			if !bytes.Equal(old, item.b) {
				return nil, fault.New("INVALID_OUTPUT", "content-addressed bytes disagree")
			}
			continue
		}
		if !os.IsNotExist(readErr) {
			return nil, readErr
		}
		if err = item.write(); err != nil {
			return nil, err
		}
	}
	if _, err = authority.Load(e.FS, rp); err != nil {
		return nil, err
	}
	return object{"receipt": rp, "receipt_sha256": rh, "event": ep, "event_sha256": eh, "authority_source": r["source_ref"], "authority_source_sha256": r["source_sha256"], "artifact_approval_changed": false, "trust_model": "host-source-bound cooperative workflow attestation; not independent identity authentication"}, nil
}
func (e *Engine) export(r object, entry repository.Entry) (any, error) {
	target := model.S(r["target"])
	if !validate.Path(target, false) || !strings.HasPrefix(target, ".codearbiter/exports/") || !strings.HasSuffix(target, ".html") || strings.Count(target, "/") != 2 {
		return nil, fault.New("UNSAFE_PATH", "export target must be .codearbiter/exports/<name>.html")
	}
	if model.S(r["model_sha256"]) != entry.Doc.Hash() {
		return nil, fault.New("REVISION_CONFLICT", "export source changed")
	}
	// Export is a presentation copy, not a relocation of the canonical pair.
	// A single-file export cannot promise a companion that was not exported.
	copy, err := canonical.Clone(entry.Doc.Data)
	if err != nil {
		return nil, err
	}
	model.M(copy["presentation"])["companion_path"] = ""
	doc, err := render.Prepare(copy)
	if err != nil {
		return nil, err
	}
	data, err := render.Render(doc)
	if err != nil {
		return nil, err
	}
	out := object{"path": target, "sha256": canonical.BytesHash(data), "source_model_sha256": entry.Doc.Hash(), "normative_sha256": doc.NormHash(), "standalone": true, "canonical": false, "companion_links": "omitted; qualified references remain readable without unresolved links"}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, []store.Edit{{Path: target, After: data}}, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}
