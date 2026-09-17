//go:build linux

package operations

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
	"testing"
)

func migrationRequest(t *testing.T, h *harness) object {
	t.Helper()
	s := testutil.Seal(t, testutil.Spec())
	pn := model.M(testutil.Plan(s)["normative"])
	for _, kind := range []string{"spec", "plan"} {
		dir := filepath.Join(h.root, ".codearbiter", kind+"s")
		if e := os.MkdirAll(dir, 0755); e != nil {
			t.Fatal(e)
		}
		if e := os.WriteFile(filepath.Join(dir, "example.md"), []byte("# Legacy\nStatus: approved\nHistoric behavior\n"), 0644); e != nil {
			t.Fatal(e)
		}
	}
	mapping := func(target string) []any {
		return []any{object{"start_line": int64(1), "end_line": int64(3), "target": target, "disposition": "mapped", "reason": "Synthetic reviewed fixture mapping, not actual production migration."}}
	}
	return object{"spec": object{"source_path": ".codearbiter/specs/example.md", "artifact_id": s.ID(), "slug": "example", "normative": s.Norm(), "mappings": mapping("INTENT-01")}, "plan": object{"source_path": ".codearbiter/plans/example.md", "artifact_id": "PLAN-EXAMPLE", "slug": "example", "normative": pn, "mappings": mapping("T-001")}}
}
func TestMigrationPairAndRollback(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	preview := h.run("migration-preview", r)
	if _, e := os.Stat(filepath.Join(h.root, ".codearbiter/specs/example.html")); !os.IsNotExist(e) {
		t.Fatal("preview wrote a canonical artifact")
	}
	r["preview_sha256"] = preview["preview_sha256"]
	r["operation_id"] = "cutover-fixture-001"
	r["review"] = object{"actor": "test fixture", "origin": "unit test", "source_text": "Synthetic explicit mapping approval; not implementation approval."}
	h.run("migration-apply", r)
	for _, kind := range []string{"spec", "plan"} {
		if _, e := os.Stat(filepath.Join(h.root, ".codearbiter", kind+"s/example.md")); !os.IsNotExist(e) {
			t.Fatal("two live authorities")
		}
	}
	if model.S(model.M(h.doc("SPEC-EXAMPLE").Data["governance"])["state"]) != "draft" {
		t.Fatal("legacy approval transferred")
	}
	if h.doc("PLAN-EXAMPLE").Norm()["spec_ref"] == nil {
		t.Fatal("lost binding")
	}
	if _, e := h.request("migration-rollback", object{"operation_id": "rollback-fixture-001", "cutover_operation_id": "cutover-fixture-001"}); e != nil {
		t.Fatal(e)
	}
	for _, kind := range []string{"spec", "plan"} {
		b, e := os.ReadFile(filepath.Join(h.root, ".codearbiter", kind+"s/example.md"))
		if e != nil || string(b) != "# Legacy\nStatus: approved\nHistoric behavior\n" {
			t.Fatal("legacy bytes not restored")
		}
	}
}
func TestMigrationRequiresCompleteMapping(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	model.M(model.A(model.M(r["spec"])["mappings"])[0])["end_line"] = int64(2)
	_, e := h.request("migration-preview", r)
	if fault.Code(e) != "UNMAPPED_LEGACY" {
		t.Fatal(e)
	}
}
func TestMigrationStalePreview(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	p := h.run("migration-preview", r)
	r["preview_sha256"] = p["preview_sha256"]
	r["operation_id"] = "cutover-stale-001"
	r["review"] = object{"actor": "fixture", "origin": "test", "source_text": "Fixture only"}
	path := filepath.Join(h.root, ".codearbiter/specs/example.md")
	os.WriteFile(path, []byte("# Changed\nStatus: approved\nHistoric behavior\n"), 0644)
	_, e := h.request("migration-apply", r)
	if fault.Code(e) != "STALE_PREVIEW" {
		t.Fatal(e)
	}
	if _, e := os.Stat(filepath.Join(h.root, ".codearbiter/specs/example.html")); !os.IsNotExist(e) {
		t.Fatal("stale preview mutated files")
	}
}
func TestCaptureIsIdempotentNotApproval(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	s := h.doc("SPEC-EXAMPLE")
	ev := object{"format": "codearbiter.workflow-event/0.1.0", "kind": "approval", "authority_kind": "user_workflow", "subject": object{"artifact_id": s.ID(), "record_id": s.ID(), "normative_sha256": s.NormHash()}, "actor": "synthetic test", "origin": "unit test", "verdict": "approved", "payload": object{}, "source_text": "Synthetic event; no production approval."}
	a := h.run("capture", object{"event": ev})
	b := h.run("capture", object{"event": ev})
	if a["receipt"] != b["receipt"] {
		t.Fatal("capture not idempotent")
	}
	if h.doc(s.ID()).Hash() != s.Hash() {
		t.Fatal("capture mutated artifact")
	}
	h.mut("approve", s.ID(), object{"receipt": a["receipt"]})
	// A kind/verdict mismatch must fail before saving any event bytes.
	ev["authority_kind"] = "verification_runner"
	raw, _ := canonical.Marshal(ev)
	_, e := h.request("capture", object{"event": ev})
	if fault.Code(e) != "AUTHORITY_UNVERIFIED" {
		t.Fatal(e)
	}
	if _, e := os.Stat(filepath.Join(h.root, ".codearbiter/.artifacts/events/"+canonical.BytesHash(raw)+".json")); !os.IsNotExist(e) {
		t.Fatal("invalid event persisted")
	}
}
func TestNoIDReuseWithinBatch(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	_, _, e := Changes(h.doc("SPEC-EXAMPLE"), []any{object{"op": "record.retire", "symbol": "AC-001", "reason": "test"}, object{"op": "record.add", "collection": "criteria", "record": testutil.Criterion("AC-001")}})
	if fault.Code(e) != "DUPLICATE_ID" {
		t.Fatal(e)
	}
}

func TestCreateDoesNotShadowLegacy(t *testing.T) {
	h := newHarness(t)
	migrationRequest(t, h)
	_, e := h.request("create", object{"operation_id": "legacy-shadow-001", "artifact_id": "SPEC-OTHER", "kind": "spec", "slug": "example", "title": "Other", "summary": "Must not shadow legacy source"})
	if fault.Code(e) != "LEGACY_CONFLICT" {
		t.Fatal(e)
	}
}
func TestDuplicateCanonicalAuthoritiesFailClosed(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	os.WriteFile(filepath.Join(h.root, ".codearbiter/specs/example.md"), []byte("legacy duplicate"), 0644)
	_, e := h.request("index", nil)
	if fault.Code(e) != "AMBIGUOUS_ARTIFACT" {
		t.Fatal(e)
	}
}
