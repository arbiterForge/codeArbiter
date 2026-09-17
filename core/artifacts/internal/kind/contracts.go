// Package kind owns the closed, compile-time registry for structured artifact
// kinds. The storage/catalog/schema kernel consumes these contracts without
// embedding document-specific directory or schema switches.
package kind

type Contract struct {
	Name      string
	Directory string
	Schema    string
}

var contracts = []Contract{
	{Name: "spec", Directory: ".codearbiter/specs", Schema: "spec"},
	{Name: "plan", Directory: ".codearbiter/plans", Schema: "plan"},
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
