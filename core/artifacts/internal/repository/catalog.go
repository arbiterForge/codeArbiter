// Package repository resolves artifact identity independently of its filename.
package repository

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"os"
	"path"
	"strings"
)

type Entry struct {
	Path  string
	Bytes []byte
	Doc   *model.Document
}
type Catalog struct {
	Entries map[string]Entry
	Order   []string
}

func Scan(f *store.FS) (*Catalog, error) {
	out := &Catalog{Entries: map[string]Entry{}, Order: []string{}}
	total := 0
	for _, contract := range kind.All() {
		dir := contract.Directory
		files, e := f.List(dir)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil {
			return nil, e
		}
		for _, file := range files {
			if file.IsDir() || !strings.HasSuffix(file.Name(), ".html") {
				continue
			}
			if len(out.Order) >= 1024 {
				return nil, fault.New("MAX_ARTIFACTS", "live artifact count exceeds 1024")
			}
			p := path.Join(dir, file.Name())
			legacy := strings.TrimSuffix(p, ".html") + ".md"
			if _, err := f.Read(legacy, canonical.MaxBytes); err == nil {
				return nil, fault.New("AMBIGUOUS_ARTIFACT", "HTML and Markdown coexist for a canonical slug; use reviewed pair cutover")
			} else if !os.IsNotExist(err) {
				return nil, err
			}
			b, e := f.Read(p, canonical.MaxBytes)
			if e != nil {
				return nil, e
			}
			total += len(b)
			if total > 64<<20 {
				return nil, fault.New("MAX_BYTES", "live artifact catalog exceeds 64 MiB")
			}
			d, e := render.Parse(b)
			if e != nil {
				return nil, fault.At(fault.Code(e), "", p, e.Error())
			}
			if d.Kind() != contract.Name {
				return nil, fault.New("INVALID_LOCATION", "artifact kind disagrees with its canonical directory")
			}
			if _, ok := out.Entries[d.ID()]; ok {
				return nil, fault.At("AMBIGUOUS_ARTIFACT", d.ID(), "", "multiple live files carry the same artifact ID")
			}
			out.Entries[d.ID()] = Entry{p, b, d}
			out.Order = append(out.Order, d.ID())
		}
	}
	return out, nil
}
func (c *Catalog) Resolve(id string) (Entry, error) {
	if !symbol.Pattern.MatchString(id) {
		return Entry{}, fault.New("INVALID_ID", "invalid artifact ID")
	}
	v, ok := c.Entries[id]
	if !ok {
		return Entry{}, fault.New("ARTIFACT_NOT_FOUND", "artifact ID has no live file")
	}
	return v, nil
}
func (c *Catalog) Spec(d *model.Document) (Entry, error) {
	if d.Kind() == "spec" {
		return c.Resolve(d.ID())
	}
	return c.Resolve(model.S(model.M(d.Norm()["spec_ref"])["artifact_id"]))
}
func NewPath(name, slug string) (string, error) {
	contract, ok := kind.Lookup(name)
	if !ok {
		return "", fault.New("UNSUPPORTED_VERSION", "unsupported artifact kind")
	}
	return path.Join(contract.Directory, slug+".html"), nil
}
func (c *Catalog) Vector() map[string]any {
	v := map[string]any{}
	for id, e := range c.Entries {
		v[id] = map[string]any{"path": e.Path, "model_sha256": e.Doc.Hash()}
	}
	return v
}
