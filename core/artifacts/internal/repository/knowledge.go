package repository

import (
	"os"
	"path"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// Unreadable names one knowledge document that could not be used. It is an
// honest read result for that document only, never a verdict on other work.
type Unreadable struct {
	Path string
	Code string
}

// MaxKnowledgeDocuments bounds a knowledge load; the canonical layout has six.
const MaxKnowledgeDocuments = 64

// LoadKnowledge parses every knowledge and decomposition document on its own.
// One malformed or oversized document is reported and skipped, so it cannot
// veto a read of the others or of the task that asked for them.
func LoadKnowledge(f *store.FS) ([]Entry, []Unreadable, error) {
	entries, unreadable := []Entry{}, []Unreadable{}
	codecs := kind.Codecs()
	seen := map[string]bool{}
	for _, contract := range kind.All() {
		if !kind.Knowledge(contract.Name) {
			continue
		}
		codec := codecs[contract.Name]
		files, e := f.List(contract.Directory)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil {
			return nil, nil, e
		}
		names := []string{}
		for _, file := range files {
			if !file.IsDir() && strings.HasSuffix(file.Name(), codec.Extension) {
				names = append(names, file.Name())
			}
		}
		sort.Strings(names)
		for _, name := range names {
			if len(entries)+len(unreadable) >= MaxKnowledgeDocuments {
				return nil, nil, fault.New("MAX_ARTIFACTS", "knowledge document count exceeds 64")
			}
			p := path.Join(contract.Directory, name)
			b, e := f.Read(p, canonical.MaxBytes)
			if e != nil {
				unreadable = append(unreadable, Unreadable{p, "READ_FAILED"})
				continue
			}
			d, e := parseWithCodec(codec, b)
			if e != nil {
				unreadable = append(unreadable, Unreadable{p, fault.Code(e)})
				continue
			}
			if d.Kind() != contract.Name || seen[d.ID()] {
				unreadable = append(unreadable, Unreadable{p, "INVALID_LOCATION"})
				continue
			}
			seen[d.ID()] = true
			entries = append(entries, Entry{p, b, d})
		}
	}
	return entries, unreadable, nil
}
