package kind

import (
	"reflect"
	"testing"
)

func TestContractsAreClosedOrderedAndKindNeutral(t *testing.T) {
	wantNames := []string{"spec", "plan", "context", "knowledge", "decomposition", "work"}
	if got := Names(); !reflect.DeepEqual(got, wantNames) {
		t.Fatalf("Names() = %v, want %v", got, wantNames)
	}

	want := map[string]Contract{
		"spec":          {Name: "spec", Directory: ".codearbiter/specs", Schema: "spec"},
		"plan":          {Name: "plan", Directory: ".codearbiter/plans", Schema: "plan"},
		"context":       {Name: "context", Directory: ".codearbiter", Schema: "context"},
		"knowledge":     {Name: "knowledge", Directory: ".codearbiter/context", Schema: "knowledge"},
		"decomposition": {Name: "decomposition", Directory: ".codearbiter/decomposition", Schema: "decomposition"},
		"work":          {Name: "work", Directory: ".codearbiter/work", Schema: "work"},
	}
	for _, name := range wantNames {
		got, ok := Lookup(name)
		if !ok {
			t.Fatalf("Lookup(%q) did not find a registered contract", name)
		}
		if got != want[name] {
			t.Fatalf("Lookup(%q) = %#v, want %#v", name, got, want[name])
		}
	}
	for id, want := range map[string]string{"CTX-TECH-STACK": "knowledge", "DECOMP-PROJECT": "decomposition", "CONTEXT-X": "context", "WORK-ABC": "work"} {
		if got := ForID(id); got != want {
			t.Fatalf("ForID(%q) = %q, want %q", id, got, want)
		}
	}
	if !Knowledge("knowledge") || !Knowledge("decomposition") || Knowledge("spec") || Knowledge("context") {
		t.Fatal("Knowledge() misclassifies a kind")
	}
	if _, ok := Lookup("ticket"); ok {
		t.Fatal("unregistered kinds must remain closed")
	}
}
