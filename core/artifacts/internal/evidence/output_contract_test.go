package evidence

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// Every directory the store may write through PutDerived must be a reserved
// output this recognizer validates; otherwise a successful producer poisons
// every later strict snapshot and normalized completion (N-F01).
func TestRecognizedOutputsCoverEveryDerivedKind(t *testing.T) {
	kinds := store.DerivedKinds()
	if len(kinds) == 0 {
		t.Fatal("store declared no derived output kinds")
	}
	for _, kind := range kinds {
		if !recognizedOutputDirectories[kind] {
			t.Errorf("derived output %q is written by the store but not recognized by snapshot", kind)
		}
	}
	for _, internal := range []string{"transactions", "history"} {
		if recognizedOutputDirectories[internal] {
			t.Errorf("journal directory %q must stay outside the output recognizer", internal)
		}
	}
}
