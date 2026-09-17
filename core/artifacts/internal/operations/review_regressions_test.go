//go:build linux

package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

func TestReviewOutlineNeverReturnsNonAdvancingPage(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "AC-001", "fields": object{"title": strings.Repeat("Long title ", 2000)}}}})
	_, err := h.request("outline", object{"artifact_id": "SPEC-EXAMPLE", "budget": int64(4096)})
	if fault.Code(err) != "RECORD_TOO_LARGE" {
		t.Fatalf("oversized first outline row must fail, not return an empty page at the same offset: %v", err)
	}
}

func TestReviewSnapshotHonorsExcludedLinkWithoutFollowingIt(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	outside := testutil.Root(t)
	if err := os.WriteFile(filepath.Join(outside, "private"), []byte("outside must not be read"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(h.root, "cache")); err != nil {
		t.Fatal(err)
	}
	h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"verification_inputs": object{"roots": model.List("."), "exclude_directories": model.List("cache")}}}}})
	before := h.input()
	if err := os.WriteFile(filepath.Join(outside, "private"), []byte("changed outside"), 0600); err != nil {
		t.Fatal(err)
	}
	if h.input() != before {
		t.Fatal("excluded target entered the snapshot")
	}
	// The same symlink is unsafe when it is an included source input.
	h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"verification_inputs": object{"roots": model.List("."), "exclude_directories": model.List()}}}}})
	if _, err := h.request("snapshot", object{"artifact_id": "PLAN-EXAMPLE"}); err == nil {
		t.Fatal("included source symlink was followed")
	}
}

func TestReviewReadyPolicyCoversEveryDeclaredTaskPath(t *testing.T) {
	for _, policy := range []object{
		{"roots": model.List("README.md"), "exclude_directories": model.List()},
		{"roots": model.List("."), "exclude_directories": model.List("src")},
	} {
		h := newHarness(t)
		h.createPair()
		h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "header.update", "fields": object{"verification_inputs": policy}}}})
		found := false
		for _, d := range validate.Ready(h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")) {
			if d.Code == "UNCOVERED_INPUT" {
				found = true
			}
		}
		if !found {
			t.Fatal("ready plan omitted declared source paths from its freshness inputs")
		}
	}
}

func TestReviewReadyRejectsWhitespaceScope(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "SCOPE-01", "fields": object{"statement": "   "}}}})
	found := false
	for _, d := range validate.Ready(h.doc("SPEC-EXAMPLE"), nil) {
		if d.Code == "NOT_READY" && d.Symbol == "SCOPE-01" && d.Field == "statement" {
			found = true
		}
	}
	if !found {
		t.Fatal("whitespace scope text was approved as a complete contract")
	}
}

func TestReviewSingleExportHasNoBrokenCompanionLocator(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	d := h.doc("PLAN-EXAMPLE")
	before := d.Hash()
	h.run("export", object{"artifact_id": d.ID(), "model_sha256": d.Hash(), "operation_id": h.next(), "target": ".codearbiter/exports/review.html"})
	b, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/exports/review.html"))
	if err != nil {
		t.Fatal(err)
	}
	if h.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("export mutated canonical source")
	}
	// A one-file standalone export cannot promise a companion file that was not exported.
	if strings.Contains(string(b), `class="companion"`) || strings.Contains(string(b), `href="../specs/`) {
		t.Fatal("standalone export retains an unresolved canonical-directory companion link")
	}
}
