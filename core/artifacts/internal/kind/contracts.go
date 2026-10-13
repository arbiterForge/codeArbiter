// Package kind owns the closed, compile-time registry for structured artifact
// kinds. The storage/catalog/schema kernel consumes these contracts without
// embedding document-specific directory or schema switches.
package kind

// Representation is a closed storage/codec selector. Adding a representation
// here does not enroll a kind or make a parser available.
type Representation string

const (
	HTML     Representation = "html"
	Markdown Representation = "markdown"
	JSON     Representation = "json"
)

type Codec struct {
	Representation Representation
	Extension      string
	Optional       bool
	IDPrefix       string
}

type Contract struct {
	Name      string
	Directory string
	Schema    string
}

var contracts = []Contract{
	{Name: "spec", Directory: ".codearbiter/specs", Schema: "spec"},
	{Name: "plan", Directory: ".codearbiter/plans", Schema: "plan"},
	{Name: "context", Directory: ".codearbiter", Schema: "context"},
}

var codecs = map[string]Codec{
	"spec":    {Representation: HTML, Extension: ".html", IDPrefix: "SPEC-"},
	"plan":    {Representation: HTML, Extension: ".html", IDPrefix: "PLAN-"},
	"context": {Representation: Markdown, Extension: ".md", Optional: true, IDPrefix: "CONTEXT-"},
}

// Codecs returns a copy so callers cannot mutate the registered dispatch.
func Codecs() map[string]Codec {
	out := make(map[string]Codec, len(codecs))
	for name, codec := range codecs {
		out[name] = codec
	}
	return out
}

func ForID(id string) string {
	for _, contract := range contracts {
		codec, ok := codecs[contract.Name]
		if ok && len(codec.IDPrefix) > 0 && len(id) >= len(codec.IDPrefix) && id[:len(codec.IDPrefix)] == codec.IDPrefix {
			return contract.Name
		}
	}
	return ""
}

func All() []Contract {
	out := make([]Contract, len(contracts))
	copy(out, contracts)
	return out
}

func Names() []string {
	out := make([]string, len(contracts))
	for i, contract := range contracts {
		out[i] = contract.Name
	}
	return out
}

func Lookup(name string) (Contract, bool) {
	for _, contract := range contracts {
		if contract.Name == name {
			return contract, true
		}
	}
	return Contract{}, false
}
