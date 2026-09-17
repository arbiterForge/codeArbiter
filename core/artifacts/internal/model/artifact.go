// Package model preserves the lossless schema-checked representation while
// exposing typed domain views. Unknown fields are rejected by the packaged
// schemas before a Document is returned to an ordinary caller.
package model

import (
	"encoding/json"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"math"
)

const Format = "codearbiter.artifact"
const FormatVersion = "0.1.0"
const SchemaVersion = "0.3.1"

type Document struct {
	Data    map[string]any
	Symbols *symbol.Index
}

func M(v any) map[string]any { m, _ := v.(map[string]any); return m }
func A(v any) []any          { a, _ := v.([]any); return a }
func S(v any) string         { s, _ := v.(string); return s }
func I(v any) int64          { i, _ := v.(int64); return i }

// NativeInt accepts the portable integer range shared by every supported Go
// architecture. Protocol budgets, offsets and line mappings are bounded well
// below this range by their schemas and backing data.
func NativeInt(v any) (int, bool) {
	i, ok := v.(int64)
	if !ok {
		return 0, false
	}
	if i < math.MinInt32 || i > math.MaxInt32 {
		return 0, false
	}
	return int(i), true
}
func Strings(v any) []string {
	out := []string{}
	for _, x := range A(v) {
		out = append(out, S(x))
	}
	return out
}
func List(ss ...string) []any {
	out := make([]any, len(ss))
	for i, s := range ss {
		out[i] = s
	}
	return out
}
func Check(v map[string]any) (*Document, error) {
	if S(v["format"]) != Format || S(v["format_version"]) != FormatVersion || (S(v["schema_version"]) != SchemaVersion && S(v["schema_version"]) != "0.3.0") {
		return nil, fault.New("UNSUPPORTED_VERSION", "expected codearbiter.artifact 0.1.0 / schema 0.3.0 or 0.3.1")
	}
	es := schema.Validate(S(v["kind"]), v)
	if len(es) > 0 {
		return nil, &es[0]
	}
	idx, e := symbol.Build(M(v["normative"]))
	if e != nil {
		return nil, e
	}
	return &Document{v, idx}, nil
}
func (d *Document) ID() string           { return S(d.Data["artifact_id"]) }
func (d *Document) Kind() string         { return S(d.Data["kind"]) }
func (d *Document) Norm() map[string]any { return M(d.Data["normative"]) }
func (d *Document) Revision() int64      { return I(d.Data["revision"]) }
func (d *Document) Hash() string         { return S(M(d.Data["integrity"])["model_sha256"]) }
func (d *Document) NormHash() string     { return S(M(d.Data["integrity"])["normative_sha256"]) }
func (d *Document) Clone() (*Document, error) {
	v, e := canonical.Clone(d.Data)
	if e != nil {
		return nil, e
	}
	return Check(v)
}
func NormativeProjection(v map[string]any) map[string]any {
	out := map[string]any{}
	for _, k := range []string{"format_version", "kind", "schema_version", "artifact_id", "normative"} {
		out[k] = v[k]
	}
	return out
}
func Digests(v map[string]any) (string, string, error) {
	n, e := canonical.Hash(NormativeProjection(v))
	if e != nil {
		return "", "", e
	}
	copy := map[string]any{}
	for k, x := range v {
		if k != "integrity" {
			copy[k] = x
		}
	}
	m, e := canonical.Hash(copy)
	return n, m, e
}
func Seal(v map[string]any) (*Document, error) {
	idx, e := symbol.Build(M(v["normative"]))
	if e != nil {
		return nil, e
	}
	n, m, e := Digests(v)
	if e != nil {
		return nil, e
	}
	v["integrity"] = map[string]any{"normative_sha256": n, "model_sha256": m, "symbol_count": int64(len(idx.ByID))}
	return Check(v)
}
func (d *Document) VerifyIntegrity() error {
	n, m, e := Digests(d.Data)
	if e != nil {
		return e
	}
	if n != d.NormHash() || m != d.Hash() || I(M(d.Data["integrity"])["symbol_count"]) != int64(len(d.Symbols.ByID)) {
		return fault.New("DIGEST_MISMATCH", "artifact identities do not match content")
	}
	return nil
}
func (d *Document) TypedNormative() (any, error) {
	b, e := canonical.Marshal(d.Norm())
	if e != nil {
		return nil, e
	}
	if d.Kind() == "spec" {
		var v Spec
		e = json.Unmarshal(b, &v)
		return v, e
	}
	var v Plan
	e = json.Unmarshal(b, &v)
	return v, e
}
