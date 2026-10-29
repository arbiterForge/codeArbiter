//go:build linux

package operations

import (
	"encoding/json"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
	"strings"
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
	journalBytes, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/.artifacts/transactions/cutover-fixture-001.json"))
	if err != nil {
		t.Fatal(err)
	}
	var journal object
	if err := json.Unmarshal(journalBytes, &journal); err != nil || len(model.A(journal["entries"])) != 4 {
		t.Fatalf("pair cutover did not journal four edits: %v", err)
	}
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

func TestMigrationRefusesUnpairedCutover(t *testing.T) {
	for _, missing := range []string{"spec", "plan"} {
		t.Run(missing, func(t *testing.T) {
			h := newHarness(t)
			r := migrationRequest(t, h)
			delete(r, missing)
			for _, op := range []string{"migration-preview", "migration-apply"} {
				if op == "migration-apply" {
					r["operation_id"] = "cutover-unpaired-001"
					r["preview_sha256"] = strings.Repeat("0", 64)
					r["review"] = object{"actor": "fixture", "origin": "test", "source_text": "Fixture only"}
				}
				if _, err := h.request(op, r); fault.Code(err) != "INVALID_MODEL" || fault.Public(err).Field != "/"+missing {
					t.Fatalf("%s accepted an unpaired %s: %v", op, missing, err)
				}
			}
			for _, kind := range []string{"spec", "plan"} {
				if _, err := os.Stat(filepath.Join(h.root, ".codearbiter", kind+"s", "example.html")); !os.IsNotExist(err) {
					t.Fatalf("unpaired migration wrote %s HTML: %v", kind, err)
				}
				if _, err := os.Stat(filepath.Join(h.root, ".codearbiter", kind+"s", "example.md")); err != nil {
					t.Fatalf("unpaired migration removed %s Markdown: %v", kind, err)
				}
			}
		})
	}
}

func TestMigrationOwnerRefusesUnpairedCutover(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	delete(r, "plan")
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	c, err := repository.Scan(f)
	if err != nil {
		t.Fatal(err)
	}
	engine := &Engine{FS: f, Catalog: c}
	if _, _, err := engine.migration(r); fault.Code(err) != "PAIR_REQUIRED" {
		t.Fatalf("migration owner accepted an unpaired spec: %v", err)
	}
}

func TestMigrationRefusesMixedSlugPair(t *testing.T) {
	h := newHarness(t)
	r := migrationRequest(t, h)
	other := filepath.Join(h.root, ".codearbiter/plans/other.md")
	if err := os.WriteFile(other, []byte("# Legacy\nStatus: approved\nHistoric behavior\n"), 0644); err != nil {
		t.Fatal(err)
	}
	model.M(r["plan"])["slug"] = "other"
	model.M(r["plan"])["source_path"] = ".codearbiter/plans/other.md"
	for _, op := range []string{"migration-preview", "migration-apply"} {
		if op == "migration-apply" {
			r["operation_id"] = "cutover-mixed-slug-001"
			r["preview_sha256"] = strings.Repeat("0", 64)
			r["review"] = object{"actor": "fixture", "origin": "test", "source_text": "Fixture only"}
		}
		if _, err := h.request(op, r); fault.Code(err) != "PAIR_MISMATCH" {
			t.Fatalf("%s accepted mixed slug pair: %v", op, err)
		}
	}
	for _, rel := range []string{".codearbiter/specs/example.md", ".codearbiter/plans/other.md"} {
		if _, err := os.Stat(filepath.Join(h.root, filepath.FromSlash(rel))); err != nil {
			t.Fatalf("mixed slug attempt removed %s: %v", rel, err)
		}
	}
	for _, rel := range []string{".codearbiter/specs/example.html", ".codearbiter/plans/other.html"} {
		if _, err := os.Stat(filepath.Join(h.root, filepath.FromSlash(rel))); !os.IsNotExist(err) {
			t.Fatalf("mixed slug attempt wrote %s: %v", rel, err)
		}
	}
}

func TestMigrationRollbackKeepsHistoricalTwoEditCutoverRecoverable(t *testing.T) {
	h := newHarness(t)
	migrationRequest(t, h)
	legacy := []byte("# Legacy\nStatus: approved\nHistoric behavior\n")
	view, err := render.Render(testutil.Seal(t, testutil.Spec()))
	if err != nil {
		t.Fatal(err)
	}
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	_, err = f.Commit("historical-cutover-001", canonical.BytesHash([]byte("historical fixture")), []store.Edit{
		{Path: ".codearbiter/specs/example.html", After: view},
		{Path: ".codearbiter/specs/example.md", Before: legacy},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := f.Infrastructure(); err != nil {
		t.Fatalf("historical two-edit journal is not inspectable: %v", err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := h.request("migration-rollback", object{"operation_id": "historical-rollback-001", "cutover_operation_id": "historical-cutover-001"}); err != nil {
		t.Fatalf("historical two-edit cutover cannot be rolled back: %v", err)
	}
	if got, err := os.ReadFile(filepath.Join(h.root, ".codearbiter/specs/example.md")); err != nil || string(got) != string(legacy) {
		t.Fatalf("historical Markdown not restored: %v", err)
	}
	if _, err := os.Stat(filepath.Join(h.root, ".codearbiter/specs/example.html")); !os.IsNotExist(err) {
		t.Fatalf("historical HTML still live after rollback: %v", err)
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
func TestLegacyCaptureCannotConferApproval(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	s := h.doc("SPEC-EXAMPLE")
	ev := object{"format": "codearbiter.workflow-event/0.1.0", "kind": "approval", "authority_kind": "user_workflow", "subject": object{"artifact_id": s.ID(), "record_id": s.ID(), "normative_sha256": s.NormHash()}, "actor": "synthetic test", "origin": "unit test", "verdict": "approved", "payload": object{}, "source_text": "Synthetic event; no production approval."}
	if _, e := h.request("capture", object{"event": ev}); fault.Code(e) != "INVALID_MODEL" {
		t.Fatalf("inline caller event was accepted: %v", e)
	}
	source := h.authoritySource(ev)
	if _, e := h.request("capture", source); fault.Code(e) != "OBSERVATION_REQUIRED" {
		t.Fatalf("legacy workflow event conferred authority: %v", e)
	}
	if h.doc(s.ID()).Hash() != s.Hash() {
		t.Fatal("capture mutated artifact")
	}
	// A kind/verdict mismatch must fail before saving any event bytes.
	ev["authority_kind"] = "verification_runner"
	raw, _ := canonical.Marshal(ev)
	_, e := h.request("capture", h.authoritySource(ev))
	if fault.Code(e) != "AUTHORITY_UNVERIFIED" {
		t.Fatal(e)
	}
	if _, e := os.Stat(filepath.Join(h.root, ".codearbiter/.artifacts/events/"+canonical.BytesHash(raw)+".json")); !os.IsNotExist(e) {
		t.Fatal("invalid event persisted")
	}
}

func TestCaptureRejectsUnboundOrChangedAuthoritySource(t *testing.T) {
	h := newHarness(t)
	h.createPair()
	s := h.doc("SPEC-EXAMPLE")
	ev := object{"format": "codearbiter.workflow-event/0.1.0", "kind": "approval", "authority_kind": "user_workflow", "subject": object{"artifact_id": s.ID(), "record_id": s.ID(), "normative_sha256": s.NormHash()}, "actor": "synthetic test", "origin": "unit test", "verdict": "approved", "payload": object{}, "source_text": "Synthetic event; no production approval."}
	source := h.authoritySource(ev)
	wrong := object{"source_ref": source["source_ref"], "source_sha256": strings.Repeat("0", 64)}
	if _, e := h.request("capture", wrong); fault.Code(e) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("wrong source digest was accepted: %v", e)
	}
	path := filepath.Join(h.root, filepath.FromSlash(model.S(source["source_ref"])))
	if e := os.WriteFile(path, []byte("{}\n"), 0600); e != nil {
		t.Fatal(e)
	}
	if _, e := h.request("capture", source); fault.Code(e) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("changed authority source was accepted: %v", e)
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
