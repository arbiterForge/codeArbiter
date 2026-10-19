//go:build windows

package store

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// A junction reports ModeIrregular, not ModeSymlink, on current Go. One that
// stays inside the root passes os.Root containment, so the explicit link checks
// must refuse it on their own (#909).
func TestJunctionComponentsAreRefusedExplicitly(t *testing.T) {
	root := testutil.Root(t)
	real := filepath.Join(root, "real")
	if err := os.MkdirAll(real, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(real, "note.md"), []byte("x"), 0600); err != nil {
		t.Fatal(err)
	}
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", filepath.Join(root, "link"), real).CombinedOutput(); err != nil {
		t.Skipf("mklink /J unavailable: %v %s", err, out)
	}
	f, err := Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := f.check("real/note.md", false); err != nil {
		t.Fatalf("SETUP: a real path was refused: %v", err)
	}
	for _, rel := range []string{"link", "link/note.md"} {
		if code := fault.Code(f.check(rel, false)); code != "UNSAFE_PATH" {
			t.Errorf("check(%q) accepted an in-root junction component (code %q)", rel, code)
		}
	}
	if _, err := f.List("."); fault.Code(err) != "UNSAFE_PATH" {
		t.Errorf("List accepted a directory containing a junction: %v", err)
	}
	if _, err := f.List("real"); err != nil {
		t.Errorf("List refused a directory with no links: %v", err)
	}
}
