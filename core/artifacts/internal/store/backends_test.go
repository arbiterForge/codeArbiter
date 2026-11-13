package store

import (
	"runtime"
	"strings"
	"testing"
)

// NT-08 / N-F08: the unsupported-platform diagnostic names the actual GOOS and
// the backends this source declares; it makes no release or pending claim.
func TestUnsupportedPlatformDiagnosticIsTruthful(t *testing.T) {
	message := unsupportedPlatformMessage("plan9")
	for _, want := range []string{"plan9", "darwin", "linux", "windows"} {
		if !strings.Contains(message, want) {
			t.Errorf("diagnostic omits %q: %s", want, message)
		}
	}
	for _, stale := range []string{"pending", "promotion", "require the tested Linux"} {
		if strings.Contains(message, stale) {
			t.Errorf("diagnostic keeps stale claim %q: %s", stale, message)
		}
	}
	if !strings.Contains(message, "not a release qualification") {
		t.Errorf("diagnostic does not separate source capability from qualification: %s", message)
	}
}

func TestSupportedBackendDeclarationMatchesBuiltBackend(t *testing.T) {
	want, supported := SupportedBackends[runtime.GOOS]
	if supported != NativeWrites {
		t.Fatalf("%s: declared support %v disagrees with NativeWrites %v", runtime.GOOS, supported, NativeWrites)
	}
	if supported && Backend != want {
		t.Fatalf("%s: built backend %q disagrees with declaration %q", runtime.GOOS, Backend, want)
	}
	if !supported && Backend != "unsupported-"+runtime.GOOS {
		t.Fatalf("unsupported backend label is wrong: %q", Backend)
	}
}
