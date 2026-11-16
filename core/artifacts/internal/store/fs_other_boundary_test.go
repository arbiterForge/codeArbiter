//go:build !linux && !darwin && !windows

package store

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// N-F08 / NT-08: exercise the compiled unsupported backend, not just the
// diagnostic formatter. This unit does not qualify a native OS or installation.
func TestUnsupportedBackendOpenRefusesWithoutEffects(t *testing.T) {
	if NativeWrites || Backend != "unsupported-"+runtime.GOOS {
		t.Fatalf("unsupported source advertises writes or a different backend: %v %q", NativeWrites, Backend)
	}
	if _, supported := SupportedBackends[runtime.GOOS]; supported {
		t.Fatal("unsupported build is declared supported")
	}
	wantBackends := map[string]string{
		"darwin":  "darwin-osroot-flock",
		"linux":   "linux-openat-flock",
		"windows": "windows-osroot-lockfileex",
	}
	if len(SupportedBackends) != len(wantBackends) {
		t.Fatal("supported source declarations changed")
	}
	for goos, want := range wantBackends {
		if SupportedBackends[goos] != want {
			t.Fatalf("source declaration differs for %s", goos)
		}
	}
	root := t.TempDir()
	sentinel := filepath.Join(root, "sentinel")
	wantBytes := []byte("owned unsupported-backend sentinel\n")
	if err := os.WriteFile(sentinel, wantBytes, 0600); err != nil {
		t.Fatal(err)
	}
	missing := filepath.Join(root, "must-not-create")
	for _, target := range []string{root, missing} {
		fs, err := Open(target)
		if fs != nil || err == nil {
			t.Fatalf("unsupported Open returned a handle or success: %v %v", fs, err)
		}
		var diagnostic *fault.Error
		if !errors.As(err, &diagnostic) || diagnostic.Code != "UNSUPPORTED_PLATFORM" || fault.Exit(err) != 6 {
			t.Fatalf("unsupported Open returned a different protocol fault: %v", err)
		}
		for _, want := range []string{"unavailable on " + runtime.GOOS, "no native storage backend", "darwin, linux, windows", "not a release qualification"} {
			if !strings.Contains(diagnostic.Message, want) {
				t.Fatalf("actual Open diagnostic omits %q: %s", want, diagnostic.Message)
			}
		}
		for _, stale := range []string{"pending", "promotion", "require the tested Linux"} {
			if strings.Contains(diagnostic.Message, stale) {
				t.Fatalf("actual Open diagnostic retains %q", stale)
			}
		}
		if len(diagnostic.Message) > 512 || strings.Contains(diagnostic.Message, target) {
			t.Fatal("actual Open diagnostic is unbounded or exposes the requested path")
		}
	}
	got, err := os.ReadFile(sentinel)
	if err != nil || !bytes.Equal(got, wantBytes) {
		t.Fatalf("unsupported Open changed original bytes: %v", err)
	}
	entries, err := os.ReadDir(root)
	if err != nil || len(entries) != 1 || entries[0].Name() != "sentinel" {
		t.Fatalf("unsupported Open added or removed repository entries: %v", err)
	}
}
