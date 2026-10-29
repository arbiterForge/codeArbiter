//go:build linux

package operations

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestCreateRefusesCatalogCountOverflowBeforeWriting(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	populateCatalogSpecs(t, h.root, 1022)
	dir := filepath.Join(h.root, ".codearbiter", "specs")
	fixture := testutil.Spec()
	normative := model.M(fixture["normative"])
	_, err := h.request("create", object{
		"operation_id": h.next(), "artifact_id": "SPEC-CAP-OVERFLOW", "kind": "spec", "slug": "cap-overflow",
		"title": normative["title"], "summary": normative["summary"], "normative": normative,
	})
	if fault.Code(err) != "MAX_ARTIFACTS" || fault.Public(err).Field != ".codearbiter/specs/cap-overflow.html" {
		t.Fatalf("create at catalog cap should refuse before writing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "cap-overflow.html")); !os.IsNotExist(err) {
		t.Fatalf("overflow create wrote an artifact: %v", err)
	}
	if _, err := h.request("identity", object{"artifact_id": "SPEC-EXAMPLE"}); err != nil {
		t.Fatalf("existing artifact became unreadable: %v", err)
	}
	plan := testutil.Plan(h.doc("SPEC-EXAMPLE"))
	plan["artifact_id"] = "PLAN-ZZ-OVERFLOW"
	plan["slug"] = "zz-overflow"
	planBytes, err := render.Render(testutil.Seal(t, plan))
	if err != nil {
		t.Fatal(err)
	}
	planPath := ".codearbiter/plans/zz-overflow.html"
	if err := os.WriteFile(filepath.Join(h.root, filepath.FromSlash(planPath)), planBytes, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := h.request("identity", object{"artifact_id": "SPEC-EXAMPLE"}); fault.Code(err) != "MAX_ARTIFACTS" || fault.Public(err).Field != planPath {
		t.Fatalf("out-of-band overflow should identify its artifact: %v", fault.Public(err))
	}
}

func populateCatalogSpecs(t *testing.T, root string, count int) {
	t.Helper()
	dir := filepath.Join(root, ".codearbiter", "specs")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < count; i++ {
		slug := fmt.Sprintf("cap-%04d", i)
		fixture := testutil.Spec()
		fixture["artifact_id"] = fmt.Sprintf("SPEC-CAP-%04d", i)
		fixture["slug"] = slug
		sealed := testutil.Seal(t, fixture)
		body, err := render.Render(sealed)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, slug+".html"), body, 0600); err != nil {
			t.Fatal(err)
		}
	}
}

func TestMigrationPreviewRefusesCatalogCountOverflow(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	populateCatalogSpecs(t, h.root, 1024)
	if _, err := h.request("migration-preview", r); fault.Code(err) != "MAX_ARTIFACTS" {
		t.Fatalf("migration preview accepted a pair beyond the catalog cap: %v", err)
	}
}

func TestSaveRefusesCatalogByteOverflowBeforeWriting(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	fixture := testutil.Spec()
	fixture["artifact_id"] = "SPEC-CAP-BYTES"
	fixture["slug"] = "cap-bytes"
	next := testutil.Seal(t, fixture)
	newBytes, err := render.Render(next)
	if err != nil {
		t.Fatal(err)
	}
	// The existing catalog is one byte short of accommodating this candidate.
	// Only the aggregate bound is under test, so the catalog total is synthetic.
	fs, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	engine := &Engine{
		FS: fs, RequestHash: strings.Repeat("0", 64),
		Catalog: &repository.Catalog{
			BytesTotal: 64<<20 - len(newBytes) + 1,
		},
	}
	path := ".codearbiter/specs/cap-bytes.html"
	_, err = engine.save(object{"operation_id": h.next()}, repository.Entry{Path: path}, next)
	if err == nil {
		t.Fatal("save accepted a candidate that exceeds the 64 MiB catalog limit")
	}
	if fault.Code(err) != "MAX_BYTES" || fault.Public(err).Field != path {
		t.Fatalf("save should refuse catalog byte overflow: %v", fault.Public(err))
	}
	if _, err := os.Stat(filepath.Join(h.root, filepath.FromSlash(path))); !os.IsNotExist(err) {
		t.Fatalf("overflow save wrote an artifact: %v", err)
	}
}
