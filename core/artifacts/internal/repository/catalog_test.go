package repository

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestContextRepresentationBoundary(t *testing.T) {
	root := testutil.Root(t)
	spec := testutil.Seal(t, testutil.Spec())
	specBytes, err := render.Render(spec)
	if err != nil {
		t.Fatal(err)
	}
	plan := testutil.Seal(t, testutil.Plan(spec))
	planBytes, err := render.Render(plan)
	if err != nil {
		t.Fatal(err)
	}
	for name, data := range map[string][]byte{
		"specs/example.html": specBytes,
		"plans/example.html": planBytes,
	} {
		p := filepath.Join(root, ".codearbiter", name)
		if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	t.Run("html_spec_plan_identity", func(t *testing.T) {
		catalog, err := Scan(f)
		if err != nil {
			t.Fatal(err)
		}
		if want := len(specBytes) + len(planBytes); catalog.BytesTotal != want {
			t.Fatalf("catalog byte total = %d, want %d", catalog.BytesTotal, want)
		}
		for _, item := range []struct{ id, path, hash string }{
			{spec.ID(), ".codearbiter/specs/example.html", spec.Hash()},
			{plan.ID(), ".codearbiter/plans/example.html", plan.Hash()},
		} {
			entry, err := catalog.Resolve(item.id)
			if err != nil || entry.Path != item.path || entry.Doc.Hash() != item.hash {
				t.Fatalf("%s: %#v, %v", item.id, entry, err)
			}
		}
		if p, err := NewPath("spec", "new"); err != nil || p != ".codearbiter/specs/new.html" {
			t.Fatalf("spec path %q: %v", p, err)
		}
	})

	t.Run("unknown_representation_rejected", func(t *testing.T) {
		contracts := []kind.Contract{{Name: "future", Directory: ".codearbiter/future", Schema: "future"}}
		codecs := map[string]kind.Codec{"future": {Representation: kind.Representation("opaque"), Extension: ".opaque", Optional: true, IDPrefix: "FUTURE-"}}
		if _, err := scanContracts(f, contracts, codecs, "future"); fault.Code(err) != "UNSUPPORTED_REPRESENTATION" {
			t.Fatalf("unknown representation: %v", err)
		}
	})

	t.Run("inactive_optional_malformed_is_isolated", func(t *testing.T) {
		p := filepath.Join(root, ".codearbiter", "future", "bad.html")
		if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte("invalid optional content"), 0600); err != nil {
			t.Fatal(err)
		}
		contracts := append(kind.All(), kind.Contract{Name: "future", Directory: ".codearbiter/future", Schema: "future"})
		codecs := kind.Codecs()
		codecs["future"] = kind.Codec{Representation: kind.HTML, Extension: ".html", Optional: true, IDPrefix: "FUTURE-"}
		catalog, err := scanContracts(f, contracts, codecs, "spec")
		if err != nil {
			t.Fatalf("inactive optional malformed content blocked spec: %v", err)
		}
		if _, err := catalog.Resolve(spec.ID()); err != nil {
			t.Fatal(err)
		}
		if _, err := scanContracts(f, contracts, codecs, "future"); err == nil {
			t.Fatal("active malformed optional content was ignored")
		}
	})

	t.Run("legacy_duplicate_remains_error", func(t *testing.T) {
		p := filepath.Join(root, ".codearbiter", "specs", "example.md")
		if err := os.WriteFile(p, []byte("legacy duplicate"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := Scan(f); fault.Code(err) != "AMBIGUOUS_ARTIFACT" {
			t.Fatalf("legacy coexistence: %v", err)
		}
	})
}

func TestCatalogScanBoundsAncestorChecks(t *testing.T) {
	root := testutil.Root(t)
	dir := filepath.Join(root, ".codearbiter", "specs")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 20; i++ {
		v := testutil.Spec()
		v["artifact_id"] = fmt.Sprintf("SPEC-ABSENT-%02d", i)
		v["slug"] = fmt.Sprintf("absent-%02d", i)
		body, err := render.Render(testutil.Seal(t, v))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, fmt.Sprintf("absent-%02d.html", i)), body, 0600); err != nil {
			t.Fatal(err)
		}
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	stats := &store.OpenStats{}
	f.Stats = stats
	if _, err := Scan(f); err != nil {
		t.Fatal(err)
	}
	if stats.AncestorChecks > 8 || stats.FileOpens != 20 {
		t.Fatalf("catalog scan repeated path descent or skipped view verification: %+v", stats)
	}
}

func TestCatalogScanRejectsNonportableName(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows cannot create the nonportable filename")
	}
	root := testutil.Root(t)
	dir := filepath.Join(root, ".codearbiter", "specs")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	body, err := render.Render(testutil.Seal(t, testutil.Spec()))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "CON.html"), body, 0600); err != nil {
		t.Fatal(err)
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if _, err := Scan(f); fault.Code(err) != "UNSAFE_PATH" {
		t.Fatalf("nonportable catalog path: %v", err)
	}
}
