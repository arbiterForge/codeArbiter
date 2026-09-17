// Package symbol provides immutable, artifact-local record addressing.
package symbol

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"regexp"
	"strings"
)

const MaxSymbols = 8192

var Pattern = regexp.MustCompile(`^[A-Z][A-Z0-9-]{1,79}$`)

type Record struct {
	ID      string
	Kind    string
	Path    string
	Value   map[string]any
	Retired bool
}
type Index struct {
	ByID  map[string]Record
	Order []string
}

func Build(norm map[string]any) (*Index, error) {
	idx := &Index{ByID: map[string]Record{}}
	var visit func(any, string, string, bool) error
	visit = func(v any, path, kind string, retired bool) error {
		switch x := v.(type) {
		case map[string]any:
			if id, ok := x["id"]; ok {
				s, ok := id.(string)
				if !ok || !Pattern.MatchString(s) {
					return fault.New("INVALID_ID", "record ID is invalid")
				}
				if _, exists := idx.ByID[s]; exists {
					return fault.At("DUPLICATE_ID", s, path, "duplicate record ID")
				}
				if len(idx.ByID) >= MaxSymbols {
					return fault.New("MAX_SYMBOLS", "symbol count exceeds 8192")
				}
				idx.ByID[s] = Record{s, kind, path, x, retired}
				idx.Order = append(idx.Order, s)
			}
			for _, k := range canonical.Keys(x) {
				if e := visit(x[k], path+"/"+k, k, retired || k == "retired_symbols"); e != nil {
					return e
				}
			}
		case []any:
			for _, item := range x {
				if e := visit(item, path, kind, retired); e != nil {
					return e
				}
			}
		}
		return nil
	}
	if e := visit(norm, "/normative", "document", false); e != nil {
		return nil, e
	}
	return idx, nil
}
func Split(ref string) (string, string, error) {
	a, b, ok := strings.Cut(ref, "#")
	if !ok || !Pattern.MatchString(a) || !Pattern.MatchString(b) {
		return "", "", fault.New("INVALID_REFERENCE", "expected ARTIFACT-ID#RECORD-ID")
	}
	return a, b, nil
}
