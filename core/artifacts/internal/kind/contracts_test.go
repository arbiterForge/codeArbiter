package kind

import (
	"reflect"
	"testing"
)

func TestContractsAreClosedOrderedAndKindNeutral(t *testing.T) {
	wantNames := []string{"spec", "plan"}
	if got := Names(); !reflect.DeepEqual(got, wantNames) {
		t.Fatalf("Names() = %v, want %v", got, wantNames)
	}

	want := map[string]Contract{
		"spec": {Name: "spec", Directory: ".codearbiter/specs", Schema: "spec"},
		"plan": {Name: "plan", Directory: ".codearbiter/plans", Schema: "plan"},
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
	if _, ok := Lookup("ticket"); ok {
		t.Fatal("unregistered kinds must remain closed")
	}
}
