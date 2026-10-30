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
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"os"
	"path"
	"strings"
)

// parseWithCodec is deliberately closed. A future representation needs its
// parser and renderer before its kind may be registered for active reads.
func parseWithCodec(codec kind.Codec, b []byte) (*model.Document, error) {
	switch codec.Representation {
	case kind.HTML:
		return render.Parse(b)
	case kind.Markdown, kind.JSON:
		return nil, fault.New("UNSUPPORTED_REPRESENTATION", "representation codec is not implemented")
	default:
		return nil, fault.New("UNSUPPORTED_REPRESENTATION", "unknown artifact representation")
	}
}

type Entry struct {
	Path  string
	Bytes []byte
	Doc   *model.Document
}
type Catalog struct {
	Entries    map[string]Entry
	Order      []string
	BytesTotal int
}

const MaxArtifacts = 1024
const MaxCatalogBytes = 64 << 20

func Scan(f *store.FS) (*Catalog, error) {
	return ScanFor(f, "")
}

// ScanFor scans the active kind strictly while leaving a future optional kind
// out of unrelated reads. Registered spec and plan remain strict on every scan.
func ScanFor(f *store.FS, activeKind string) (*Catalog, error) {
	return scanContracts(f, kind.All(), kind.Codecs(), activeKind)
}

func scanContracts(f *store.FS, contracts []kind.Contract, codecs map[string]kind.Codec, activeKind string) (*Catalog, error) {
	out := &Catalog{Entries: map[string]Entry{}, Order: []string{}}
	total := 0
	activeFound := activeKind == ""
	for _, contract := range contracts {
		codec, ok := codecs[contract.Name]
		if ok && codec.Optional && contract.Name != activeKind {
			continue
		}
		if !ok || codec.Representation != kind.HTML || codec.Extension != ".html" || codec.IDPrefix == "" {
			return nil, fault.New("UNSUPPORTED_REPRESENTATION", "artifact kind has no supported representation codec")
		}
		if contract.Name == activeKind {
			activeFound = true
		}
		dir := contract.Directory
		anchor, e := f.OpenDir(dir)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil {
			return nil, e
		}
		defer anchor.Close()
		files, e := anchor.Entries()
		if e != nil {
			return nil, e
		}
		// A strict catalog rejects indirection anywhere in its directory,
		// including entries outside the active representation.
		for _, file := range files {
			if file.Type()&(os.ModeSymlink|os.ModeIrregular) != 0 {
				return nil, fault.New("UNSAFE_PATH", "symlink or reparse point encountered in scanned directory")
			}
		}
		for _, file := range files {
			if file.IsDir() || !strings.HasSuffix(file.Name(), codec.Extension) {
				continue
			}
			p := path.Join(dir, file.Name())
			if !validate.Path(p, false) {
				return nil, fault.At("UNSAFE_PATH", "", p, "nonportable artifact path")
			}
			if len(out.Order) >= MaxArtifacts {
				return nil, fault.At("MAX_ARTIFACTS", "", p, "live artifact count exceeds 1024")
			}
			legacy := strings.TrimSuffix(p, codec.Extension) + ".md"
			legacyExists, err := anchor.Has(path.Base(legacy))
			if err != nil {
				return nil, err
			}
			if legacyExists {
				if _, err := f.Read(legacy, canonical.MaxBytes); err == nil {
					return nil, fault.New("AMBIGUOUS_ARTIFACT", "HTML and Markdown coexist for a canonical slug; use reviewed pair cutover")
				} else if !os.IsNotExist(err) {
					return nil, err
				}
			}
			b, _, e := anchor.ReadEntry(file, canonical.MaxBytes)
			if e != nil {
				return nil, e
			}
			total += len(b)
			if total > MaxCatalogBytes {
				return nil, fault.At("MAX_BYTES", "", p, "live artifact catalog exceeds 64 MiB")
			}
			out.BytesTotal = total
			d, e := parseWithCodec(codec, b)
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
		// Anchored reads avoid repeated ancestor opens. Verify that the path
		// still names the directory we scanned before using its catalog.
		parent, e := f.OpenDir(path.Dir(dir))
		if e != nil {
			return nil, e
		}
		e = parent.Current(path.Base(dir), anchor)
		parent.Close()
		if e != nil {
			return nil, e
		}
	}
	if !activeFound {
		return nil, fault.New("UNSUPPORTED_VERSION", "unsupported artifact kind")
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
	codec, ok := kind.Codecs()[name]
	if !ok || codec.Representation != kind.HTML || codec.Extension != ".html" {
		return "", fault.New("UNSUPPORTED_REPRESENTATION", "artifact kind has no supported representation codec")
	}
	return path.Join(contract.Directory, slug+codec.Extension), nil
}
func (c *Catalog) Vector() map[string]any {
	v := map[string]any{}
	for id, e := range c.Entries {
		v[id] = map[string]any{"path": e.Path, "model_sha256": e.Doc.Hash()}
	}
	return v
}
