package operations

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"testing"
)

// Linux init-store locks the repository directory without creating the legacy
// board parent. Tests that fabricate a legacy board must create that fixture.
func ensureLegacyBoardFixtureDir(t *testing.T, root string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(root, ".codearbiter"), 0755); err != nil {
		t.Fatal(err)
	}
}

func TestWorkIdentityStableAcrossRenameAndArchive(t *testing.T) {
	root := testutil.Root(t)
	request := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		result, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return result.(map[string]any)
	}
	request("init-store", object{})
	n := 0
	next := func() string { n++; return fmt.Sprintf("work-op-%04d", n) }
	first := request("work-create", object{
		"operation_id": next(), "title": "Same title", "intent": "First outcome", "work_type": "fix",
	})
	second := request("work-create", object{
		"operation_id": next(), "title": "Same title", "intent": "Second outcome", "work_type": "fix",
	})
	id := first["work_id"].(string)
	if !regexp.MustCompile(`^WORK-[A-F0-9]{32}$`).MatchString(id) || id == second["work_id"] {
		t.Fatalf("new work identities must be opaque and distinct: %q, %q", id, second["work_id"])
	}
	if first["project_id"] != second["project_id"] {
		t.Fatalf("one repository must retain one project identity: %v, %v", first["project_id"], second["project_id"])
	}
	renamed := request("work-update", object{
		"operation_id": next(), "work_id": id, "action": "rename", "title": "Renamed",
		"expected": object{"revision": first["revision"], "model_sha256": first["model_sha256"]},
	})
	request("work-update", object{
		"operation_id": next(), "work_id": id, "action": "archive",
		"expected": object{"revision": renamed["revision"], "model_sha256": renamed["model_sha256"]},
	})
	got := request("work-get", object{"work_id": id})
	if got["work_id"] != id || got["title"] != "Renamed" || got["state"] != "archived" {
		t.Fatalf("rename/archive changed identity or lost selected work: %+v", got)
	}
	other := request("work-get", object{"work_id": second["work_id"]})
	if other["title"] != "Same title" || other["work_id"] != second["work_id"] {
		t.Fatalf("same-title work was conflated: %+v", other)
	}
}

func TestWorkAdoptJournalsBoardCutoverAndReplays(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	boardPath := filepath.Join(root, ".codearbiter", "open-tasks.md")
	ensureLegacyBoardFixtureDir(t, root)
	board := []byte("# Work\n- [ ] demo.feat.0001 - Build parser\n  - Desc: Parse safely\n")
	if err := os.WriteFile(boardPath, board, 0644); err != nil {
		t.Fatal(err)
	}
	block := []byte("- [ ] demo.feat.0001 - Build parser\n  - Desc: Parse safely")
	id := "WORK-0123456789ABCDEF0123456789ABCDEF"
	request := object{"protocol": Protocol, "operation_id": "adopt-one-board-001",
		"expected_board_sha256": fmt.Sprintf("%x", sha256.Sum256(board)), "expected_archive_sha256": nil,
		"rows": []any{object{"location": "open", "line": int64(2), "block_sha256": fmt.Sprintf("%x", sha256.Sum256(block)),
			"work_id": id, "origin": "DECOMP#PARSER", "alias": "demo.feat.0001", "title": "Build parser", "intent": "Parse safely", "work_type": "feature", "state": "queued",
			"started_at": nil, "completed_at": nil, "spec_id": nil, "plan_id": nil}},
	}
	first, err := Run(root, "work-adopt", request)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(boardPath); !os.IsNotExist(err) {
		t.Fatalf("legacy board remains writable: %v", err)
	}
	snapshot, err := os.ReadFile(filepath.Join(root, ".codearbiter", "legacy", "open-tasks.md"))
	if err != nil || string(snapshot) != string(board) {
		t.Fatalf("legacy snapshot changed: %v", err)
	}
	selected, err := Run(root, "work-get", object{"protocol": Protocol, "work_id": id})
	if err != nil || selected.(map[string]any)["title"] != "Build parser" {
		t.Fatalf("adopted work is unreadable: %v", err)
	}
	replayed, err := Run(root, "work-adopt", request)
	if err != nil || first.(map[string]any)["project_id"] != replayed.(map[string]any)["project_id"] {
		t.Fatalf("cutover replay changed project identity: %v", err)
	}
}

func TestAdoptionBlocksIgnoreScaffoldDocumentation(t *testing.T) {
	board := []byte("# Open tasks\n" +
		"Schema (one task = a lifecycle line + indented content sub-bullets):\n" +
		"```\n- [~] poc.auth.0001 - Example (started 2026-06-18)\n```\n" +
		"- Marker: `[ ]` queued | `[~]` in-progress | `[x]` done. In-progress and done\n" +
		"- ID `<group>.<type>.<seq>`: `group` = build phase (poc/mvp1/v1...), `type` =\n" +
		"- `Desc` / `Done when` / `Boundaries` are filled when known (`TBD` until then).\n" +
		"## In-flight\n- [ ] demo.feat.0001 - Actual work\n")
	blocks, err := adoptionBlocks(board)
	if err != nil || len(blocks) != 1 || blocks[10] != digestBytes([]byte("- [ ] demo.feat.0001 - Actual work")) {
		t.Fatalf("scaffold was inventoried as work: blocks=%v err=%v", blocks, err)
	}
}

func TestWorkAdoptRefusesStaleBoardAndUncoveredRows(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, ".codearbiter", "open-tasks.md")
	ensureLegacyBoardFixtureDir(t, root)
	before := []byte("- [ ] First row\n")
	if err := os.WriteFile(path, before, 0644); err != nil {
		t.Fatal(err)
	}
	request := object{"protocol": Protocol, "operation_id": "adopt-refusal-001",
		"expected_board_sha256": fmt.Sprintf("%x", sha256.Sum256(before)), "expected_archive_sha256": nil, "rows": []any{}}
	if _, err := Run(root, "work-adopt", request); fault.Code(err) != "INCOMPLETE_ADOPTION" {
		t.Fatalf("uncovered board was accepted: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, ".codearbiter", "work", "project.json")); !os.IsNotExist(err) {
		t.Fatalf("native owner was partially published: %v", err)
	}
	if err := os.WriteFile(path, []byte("- [ ] Later human edit\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "work-adopt", request); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale preimage was accepted: %v", err)
	}
	actual, err := os.ReadFile(path)
	if err != nil || string(actual) != "- [ ] Later human edit\n" {
		t.Fatalf("later edit was lost: %v", err)
	}
}

func TestWorkAdoptRefusesHiddenMalformedTaskMarker(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	board := []byte("- [ ] Visible row\n* [ ] Hidden row\n")
	path := filepath.Join(root, ".codearbiter", "open-tasks.md")
	ensureLegacyBoardFixtureDir(t, root)
	if err := os.WriteFile(path, board, 0644); err != nil {
		t.Fatal(err)
	}
	r := object{"protocol": Protocol, "operation_id": "adopt-hidden-001", "expected_board_sha256": fmt.Sprintf("%x", sha256.Sum256(board)), "expected_archive_sha256": nil,
		"rows": []any{object{"location": "open", "line": int64(1), "block_sha256": fmt.Sprintf("%x", sha256.Sum256([]byte("- [ ] Visible row"))),
			"work_id": "WORK-22222222222222222222222222222222", "origin": "legacy:open#VISIBLE", "alias": nil,
			"title": "Visible row", "intent": "Visible row", "work_type": "unknown", "state": "queued", "started_at": nil, "completed_at": nil, "spec_id": nil, "plan_id": nil}}}
	if _, err := Run(root, "work-adopt", r); fault.Code(err) != "INVALID_LEGACY_BOARD" {
		t.Fatalf("malformed hidden task was dropped: %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("board was removed: %v", err)
	}
}

func TestLegacyBoardLockRefusesExternalHardLink(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	external := filepath.Join(t.TempDir(), "external")
	if err := os.WriteFile(external, nil, 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, ".codearbiter", "open-tasks.md.lock")
	ensureLegacyBoardFixtureDir(t, root)
	if err := os.Link(external, link); err != nil {
		t.Skipf("hard links unavailable: %v", err)
	}
	file, err := openLegacyBoardLock(root)
	if file != nil {
		_ = file.Close()
	}
	if fault.Code(err) != "LEGACY_LOCK_FAILED" {
		t.Fatalf("hardlinked lock was accepted: %v", err)
	}
	info, err := os.Stat(external)
	if err != nil || info.Size() != 0 {
		t.Fatalf("external file was changed: %v", err)
	}
}

func TestWorkAdoptRecoveryPreservesLaterBoardEdit(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	boardPath := filepath.Join(root, ".codearbiter", "open-tasks.md")
	ensureLegacyBoardFixtureDir(t, root)
	board := []byte("- [ ] Recover row\n")
	if err := os.WriteFile(boardPath, board, 0644); err != nil {
		t.Fatal(err)
	}
	r := object{"protocol": Protocol, "operation_id": "adopt-recover-001", "expected_board_sha256": fmt.Sprintf("%x", sha256.Sum256(board)), "expected_archive_sha256": nil,
		"rows": []any{object{"location": "open", "line": int64(1), "block_sha256": fmt.Sprintf("%x", sha256.Sum256([]byte("- [ ] Recover row"))),
			"work_id": "WORK-11111111111111111111111111111111", "origin": "legacy:open#RECOVER", "alias": nil,
			"title": "Recover row", "intent": "Recover row", "work_type": "unknown", "state": "queued", "started_at": nil, "completed_at": nil, "spec_id": nil, "plan_id": nil}}}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	hash, err := canonical.Hash(object{"operation": "work-adopt", "request": r})
	if err != nil {
		t.Fatal(err)
	}
	f.Inject = func(step string) error {
		if step == "after-replace-1" {
			return errors.New("injected")
		}
		return nil
	}
	_, err = (&Engine{FS: f, RequestHash: hash}).workAdopt(r)
	if err == nil {
		t.Fatal("fault was not injected")
	}
	f.Inject = nil
	later := []byte("- [ ] Later edit\n")
	if err := os.WriteFile(boardPath, later, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Recover("adopt-recover-001", "rollback"); err == nil {
		t.Fatal("rollback overwrote a later board edit")
	}
	actual, err := os.ReadFile(boardPath)
	if err != nil || string(actual) != string(later) {
		t.Fatalf("later edit was lost: %v", err)
	}
	if err := os.WriteFile(boardPath, board, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Recover("adopt-recover-001", "rollback"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, ".codearbiter", "work", "project.json")); !os.IsNotExist(err) {
		t.Fatalf("rolled back project survived: %v", err)
	}
	actual, err = os.ReadFile(boardPath)
	if err != nil || string(actual) != string(board) {
		t.Fatalf("rollback did not restore board: %v", err)
	}
}

func TestWorkCompleteWithUnknownCheck(t *testing.T) {
	root := testutil.Root(t)
	for _, name := range []string{"specs", "plans"} {
		if err := os.MkdirAll(filepath.Join(root, ".codearbiter", name), 0755); err != nil {
			t.Fatal(err)
		}
	}
	n := 0
	call := func(op string, fields object) object {
		t.Helper()
		n++
		fields["protocol"] = Protocol
		if op == "create" || op == "work-create" || op == "work-update" {
			fields["operation_id"] = fmt.Sprintf("journey-op-%04d", n)
		}
		value, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return value.(map[string]any)
	}
	call("init-store", object{})
	call("create", object{"kind": "spec", "artifact_id": "SPEC-JOURNEY", "slug": "journey", "title": "Journey", "summary": "An outcome"})
	call("create", object{"kind": "plan", "artifact_id": "PLAN-JOURNEY", "slug": "journey", "title": "Journey plan", "summary": "A path", "spec_id": "SPEC-JOURNEY"})
	created := call("work-create", object{"title": "Fix the journey", "intent": "Make selected work useful", "work_type": "fix", "spec_id": "SPEC-JOURNEY", "plan_id": "PLAN-JOURNEY"})
	id := created["work_id"].(string)
	if created["spec_id"] != "SPEC-JOURNEY" || created["plan_id"] != "PLAN-JOURNEY" || created["check_status"] != "unknown" {
		t.Fatalf("attachments or unknown check lost: %+v", created)
	}
	started := call("work-update", object{"work_id": id, "action": "start", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	completed := call("work-update", object{"work_id": id, "action": "complete", "expected": object{"revision": started["revision"], "model_sha256": started["model_sha256"]}})
	if completed["state"] != "complete" || completed["check_status"] != "unknown" {
		t.Fatalf("completion claimed verification or lost progress: %+v", completed)
	}
	got := call("work-get", object{"work_id": id})
	if got["state"] != "complete" || got["spec_id"] != "SPEC-JOURNEY" || got["plan_id"] != "PLAN-JOURNEY" {
		t.Fatalf("selected work lost attachment or progress: %+v", got)
	}
	// The selected context has exact attachment paths. It must not traverse an
	// unrelated damaged specification while reading those known documents.
	unrelated := filepath.Join(root, ".codearbiter", "specs", "unrelated.html")
	if err := os.WriteFile(unrelated, []byte("damaged unrelated artifact"), 0644); err != nil {
		t.Fatal(err)
	}
	context := call("work-context", object{"work_id": id, "budget": int64(4096)})
	if context["context_complete"] != false || context["assessment"] != "advisory" || model.S(model.M(context["spec"])["artifact_id"]) != "SPEC-JOURNEY" || model.S(model.M(context["plan"])["artifact_id"]) != "PLAN-JOURNEY" {
		t.Fatalf("bounded context omitted exact attachments or overstated completeness: %+v", context)
	}
	view, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(got["path"].(string))))
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"Local progress", "Check status is separate from completion", "../specs/journey.html", "../plans/journey.html"} {
		if !strings.Contains(string(view), expected) {
			t.Fatalf("work view omitted %q", expected)
		}
	}
	if strings.Contains(string(view), "Governance record") || strings.Contains(string(view), "DRAFT") {
		t.Fatal("work view introduced an approval or draft-status gate")
	}
	request := object{"protocol": Protocol, "operation_id": "journey-reopen-001", "work_id": id, "action": "reopen", "expected": object{"revision": completed["revision"], "model_sha256": completed["model_sha256"]}}
	first, err := Run(root, "work-update", request)
	if err != nil {
		t.Fatal(err)
	}
	replayed, err := Run(root, "work-update", request)
	if err != nil || replayed.(map[string]any)["model_sha256"] != first.(map[string]any)["model_sha256"] {
		t.Fatalf("same operation did not replay its original result: %v, %v", replayed, err)
	}
	if first.(map[string]any)["state"] != "active" || first.(map[string]any)["check_status"] != "unknown" {
		t.Fatalf("reopening lost unknown check state: %+v", first)
	}
	_, err = Run(root, "work-update", object{"protocol": Protocol, "operation_id": "journey-stale-001", "work_id": id, "action": "archive", "expected": object{"revision": completed["revision"], "model_sha256": completed["model_sha256"]}})
	if err == nil || !regexp.MustCompile("REVISION_CONFLICT").MatchString(err.Error()) {
		t.Fatalf("stale selected update must fail CAS: %v", err)
	}
}

func TestWorkRetryPreservesLaterEdit(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	create := object{"protocol": Protocol, "operation_id": "retry-create-001", "title": "Before", "intent": "Preserve later edits", "work_type": "fix"}
	value, err := Run(root, "work-create", create)
	if err != nil {
		t.Fatal(err)
	}
	created := value.(map[string]any)
	id := created["work_id"].(string)
	rename := object{"protocol": Protocol, "operation_id": "retry-rename-001", "work_id": id, "action": "rename", "title": "After", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}}
	value, err = Run(root, "work-update", rename)
	if err != nil {
		t.Fatal(err)
	}
	renamed := value.(map[string]any)
	value, err = Run(root, "work-update", object{"protocol": Protocol, "operation_id": "retry-archive-001", "work_id": id, "action": "archive", "expected": object{"revision": renamed["revision"], "model_sha256": renamed["model_sha256"]}})
	if err != nil {
		t.Fatal(err)
	}
	archived := value.(map[string]any)
	replayedCreate, err := Run(root, "work-create", create)
	if err != nil || replayedCreate.(map[string]any)["model_sha256"] != created["model_sha256"] {
		t.Fatalf("create replay lost original result: %v, %v", replayedCreate, err)
	}
	replayedRename, err := Run(root, "work-update", rename)
	if err != nil || replayedRename.(map[string]any)["model_sha256"] != renamed["model_sha256"] {
		t.Fatalf("rename replay lost original result: %v, %v", replayedRename, err)
	}
	current, err := Run(root, "work-get", object{"protocol": Protocol, "work_id": id})
	if err != nil {
		t.Fatal(err)
	}
	got := current.(map[string]any)
	if got["model_sha256"] != archived["model_sha256"] || got["title"] != "After" || got["state"] != "archived" {
		t.Fatalf("replay rewound later edit: %+v", got)
	}
}

func TestWorkCreateRefusesLegacyOwner(t *testing.T) {
	root := testutil.Root(t)
	board := filepath.Join(root, ".codearbiter", "open-tasks.md")
	if err := os.MkdirAll(filepath.Dir(board), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(board, []byte("# Existing owner\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	_, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "legacy-test-001", "title": "Unadopted", "intent": "Keep one owner", "work_type": "fix"})
	if err == nil || !regexp.MustCompile("LEGACY_CONFLICT").MatchString(err.Error()) {
		t.Fatalf("legacy owner must be preserved: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, ".codearbiter", "work", "project.json")); !os.IsNotExist(err) {
		t.Fatalf("native owner was created beside legacy board: %v", err)
	}
}

func TestWorkMutationsRefuseLegacyOwnerAppearingLater(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	value, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "owner-create-001", "title": "Native", "intent": "Keep one owner", "work_type": "fix"})
	if err != nil {
		t.Fatal(err)
	}
	created := value.(map[string]any)
	board := filepath.Join(root, ".codearbiter", "open-tasks.md")
	if err := os.WriteFile(board, []byte("# Legacy board appeared\n"), 0644); err != nil {
		t.Fatal(err)
	}
	for _, request := range []struct {
		op     string
		fields object
	}{
		{"work-create", object{"operation_id": "owner-create-002", "title": "Second", "intent": "No dual backlog", "work_type": "fix"}},
		{"work-update", object{"operation_id": "owner-update-001", "work_id": created["work_id"], "action": "start", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}}},
	} {
		request.fields["protocol"] = Protocol
		if _, err := Run(root, request.op, request.fields); err == nil || !strings.Contains(err.Error(), "LEGACY_CONFLICT") {
			t.Fatalf("%s must refuse a second work owner: %v", request.op, err)
		}
	}
	value, err = Run(root, "work-get", object{"protocol": Protocol, "work_id": created["work_id"]})
	if err != nil || value.(map[string]any)["state"] != "queued" {
		t.Fatalf("selected native read must remain available without a dual write: %v, %v", value, err)
	}
}

func TestWorkOriginRetryFindsArchivedIdentity(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) (object, error) {
		fields["protocol"] = Protocol
		value, err := Run(root, op, fields)
		if err != nil {
			return nil, err
		}
		return value.(map[string]any), nil
	}
	if _, err := call("init-store", object{}); err != nil {
		t.Fatal(err)
	}
	fields := object{"operation_id": "origin-create-001", "title": "Promoted item", "intent": "Keep origin stable", "work_type": "fix", "origin": "DECOMP-PROJECT#WORK-001"}
	created, err := call("work-create", fields)
	if err != nil {
		t.Fatal(err)
	}
	archived, err := call("work-update", object{"operation_id": "origin-archive-001", "work_id": created["work_id"], "action": "archive", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	if err != nil || archived["state"] != "archived" {
		t.Fatalf("archive: %v, %+v", err, archived)
	}
	fields["operation_id"] = "origin-create-002"
	reused, err := call("work-create", fields)
	if err != nil || reused["work_id"] != created["work_id"] || reused["state"] != "archived" || reused["reused"] != true {
		t.Fatalf("archived promotion duplicated: %v, %+v", err, reused)
	}
	fields["operation_id"] = "origin-create-003"
	fields["intent"] = "Different work"
	changedInput, err := call("work-create", fields)
	if err != nil || changedInput["work_id"] != created["work_id"] || changedInput["input_differs"] != true || changedInput["intent"] != "Keep origin stable" {
		t.Fatalf("changed retry must surface current work without overwrite: %v, %+v", err, changedInput)
	}
}

func TestWorkOriginRetryRepairsMissingAttachmentAfterArchive(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		value, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return value.(map[string]any)
	}
	call("init-store", object{})
	call("create", object{"operation_id": "repair-spec-001", "kind": "spec", "artifact_id": "SPEC-REPAIR", "slug": "repair", "title": "Repair", "summary": "Outcome"})
	call("create", object{"operation_id": "repair-plan-001", "kind": "plan", "artifact_id": "PLAN-REPAIR", "slug": "repair", "title": "Repair plan", "summary": "Steps", "spec_id": "SPEC-REPAIR"})
	created := call("work-create", object{"operation_id": "repair-work-001", "title": "Promoted work", "intent": "Finish promotion", "work_type": "fix", "origin": "DECOMP-PROJECT#WORK-002"})
	archived := call("work-update", object{"operation_id": "repair-archive-001", "work_id": created["work_id"], "action": "archive", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	request := object{"operation_id": "repair-work-002", "title": "Promoted work", "intent": "Finish promotion", "work_type": "fix", "origin": "DECOMP-PROJECT#WORK-002", "spec_id": "SPEC-REPAIR", "plan_id": "PLAN-REPAIR"}
	repaired := call("work-create", request)
	if repaired["work_id"] != created["work_id"] || repaired["state"] != "archived" || repaired["check_status"] != "unknown" || repaired["spec_id"] != "SPEC-REPAIR" || repaired["plan_id"] != "PLAN-REPAIR" || repaired["attachment_repaired"] != true || repaired["revision"] != archived["revision"].(int64)+1 {
		t.Fatalf("origin retry did not repair the existing archived work: %+v", repaired)
	}
	replayed := call("work-create", request)
	if replayed["work_id"] != repaired["work_id"] || replayed["model_sha256"] != repaired["model_sha256"] {
		t.Fatalf("repair replay changed identity: %+v", replayed)
	}
	call("create", object{"operation_id": "repair-plan-002", "kind": "plan", "artifact_id": "PLAN-OTHER", "slug": "other", "title": "Other plan", "summary": "Different steps", "spec_id": "SPEC-REPAIR"})
	conflicting := call("work-create", object{"operation_id": "repair-work-003", "title": "Promoted work", "intent": "Finish promotion", "work_type": "fix", "origin": "DECOMP-PROJECT#WORK-002", "spec_id": "SPEC-REPAIR", "plan_id": "PLAN-OTHER"})
	if conflicting["input_differs"] != true || conflicting["model_sha256"] != repaired["model_sha256"] || conflicting["plan_id"] != "PLAN-REPAIR" {
		t.Fatalf("conflicting retry overwrote the selected attachment: %+v", conflicting)
	}
}

func TestWorkSelectedReadIsolatedFromKnowledgeButNotSharedJournal(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	createdValue, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "isolation-create-001", "title": "Selected work", "intent": "Keep reads scoped", "work_type": "fix"})
	if err != nil {
		t.Fatal(err)
	}
	id := createdValue.(map[string]any)["work_id"].(string)
	knowledge := filepath.Join(root, ".codearbiter", "context", "project.html")
	if err := os.MkdirAll(filepath.Dir(knowledge), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(knowledge, []byte("not an artifact"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "work-get", object{"protocol": Protocol, "work_id": id}); err != nil {
		t.Fatalf("unrelated optional knowledge blocked selected work: %v", err)
	}
	journal := filepath.Join(root, ".codearbiter", ".artifacts", "transactions", "bad!!.json")
	if err := os.WriteFile(journal, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err = Run(root, "work-get", object{"protocol": Protocol, "work_id": id})
	if err == nil || !strings.Contains(err.Error(), "CORRUPT_JOURNAL") {
		t.Fatalf("shared journal corruption was ignored: %v", err)
	}
}

func TestWorkContextSelectsScopedKnowledgeAndNamesOmissions(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	f.createKnowledge("knowledge", "CTX-CODING-STANDARDS", "coding-standards")
	f.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Large relevant note", strings.Repeat("Relevant details. ", 190), "user-reported", []string{"src/stage1.go"}))
	f.addKnowledge("CTX-CODE-MAP", knowledgeRecord("component", "Unrelated inventory", strings.Repeat("Unrelated details. ", 190), "user-reported", []string{"elsewhere/**"}))
	created := f.call("work-create", object{"operation_id": f.next(), "title": "Improve stage one", "intent": "Keep selected context useful", "work_type": "fix"})
	broken := filepath.Join(f.root, ".codearbiter", "context", "coding-standards.html")
	if err := os.WriteFile(broken, []byte("<p>broken</p>"), 0o644); err != nil {
		t.Fatal(err)
	}
	out := f.call("work-context", object{
		"work_id": created["work_id"], "paths": model.List("src/stage1.go"),
		"knowledge_refs": model.List("CTX-TECH-STACK#FACT-001"), "budget": int64(4096),
	})
	refs := knowledgeRefs(out, "knowledge")
	if refs["CTX-SECURITY-CONTROLS#CON-001"] == nil || refs["CTX-TECH-STACK#FACT-001"] == nil {
		t.Fatalf("selected work omitted a path constraint or explicit capability reference: %v", refs)
	}
	if refs["CTX-CODE-MAP#COMP-002"] != nil {
		t.Fatal("oversized unrelated inventory displaced selected knowledge")
	}
	if model.I(out["knowledge_omitted_count"]) == 0 || len(model.A(out["knowledge_unreadable"])) != 1 {
		t.Fatalf("selected work hid a budget omission or unreadable optional document: %v", out)
	}
	if knowledgeRefs(out, "knowledge_omitted")["CTX-TECH-STACK#FACT-002"] == nil {
		t.Fatalf("the omitted relevant record was not named: %v", out["knowledge_omitted"])
	}
	if out["assessment"] != "advisory" {
		t.Fatalf("selected knowledge became a permission verdict: %v", out["assessment"])
	}
	assertNoPermissionFields(t, out)
}

func TestWorkContextRejectsOutOfRangeBudgetBeforeIntConversion(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	created, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "budget-range-create-001", "title": "Budget range", "intent": "Protect conversion", "work_type": "fix"})
	if err != nil {
		t.Fatal(err)
	}
	fs, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	e := &Engine{FS: fs}
	_, err = e.workContext(object{"work_id": created.(map[string]any)["work_id"], "budget": int64(math.MaxInt64), "paths": []any{}})
	if fault.Code(err) != "INVALID_BUDGET" {
		t.Fatalf("out-of-range direct budget was accepted: %v", err)
	}
}

func TestWorkEffectLostCreateResponseRemainsUnknown(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	call("init-store", object{})
	created := call("work-create", object{"operation_id": "effect-create-001", "title": "Publish local work", "intent": "Track one outcome", "work_type": "fix"})
	id := created["work_id"].(string)
	configured := call("work-provider-configure", object{"operation_id": "effect-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	staged := call("work-effect-stage", object{"operation_id": "effect-stage-001", "work_id": id,
		"binding_generation": configured["binding_generation"],
		"expected":           object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	claimed := call("work-effect-claim", object{"operation_id": "effect-claim-001", "work_id": id,
		"binding_generation": configured["binding_generation"], "attempt_id": "effect-attempt-001",
		"expected": object{"revision": staged["revision"], "model_sha256": staged["model_sha256"]}})
	replayedClaim := call("work-effect-claim", object{"operation_id": "effect-claim-001", "work_id": id,
		"binding_generation": configured["binding_generation"], "attempt_id": "effect-attempt-001",
		"expected": object{"revision": staged["revision"], "model_sha256": staged["model_sha256"]}})
	if replayedClaim["revision"] != claimed["revision"] {
		t.Fatalf("journaled issue claim did not replay: %v", replayedClaim)
	}
	if model.S(model.M(claimed["provider_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("pre-send claim did not preserve uncertainty: %v", claimed)
	}
	view := call("work-view", object{"work_id": id})
	if !strings.Contains(model.S(view["html"]), "Outcome unknown") || strings.Contains(model.S(view["html"]), "<p class=\"state\">Unconfigured</p>") {
		t.Fatal("human work view concealed the uncertain provider effect")
	}
	// A process died after the claim. A new local store has no old journal,
	// but the canonical work record must still prevent a second create.
	fresh := testutil.Root(t)
	for _, rel := range []string{projectPath, workPath(id), ".codearbiter/work/provider.json"} {
		b, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(rel)))
		if err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(fresh, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, b, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := Run(fresh, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	current, err := Run(fresh, "work-get", object{"protocol": Protocol, "work_id": id})
	if err != nil || model.S(model.M(model.M(current)["provider_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("fresh store lost portable uncertain effect: %v, %v", current, err)
	}
	_, err = Run(fresh, "work-effect-claim", object{"protocol": Protocol, "operation_id": "effect-claim-002", "work_id": id,
		"binding_generation": configured["binding_generation"], "attempt_id": "effect-attempt-002",
		"expected": object{"revision": model.M(current)["revision"], "model_sha256": model.M(current)["model_sha256"]}})
	if err == nil || !strings.Contains(err.Error(), "EFFECT_UNKNOWN") {
		t.Fatalf("uncertain create was sent again: %v", err)
	}
}

func TestWorkStatusEffectPreservesBindingAndRecordsRemoteConflict(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	created := call("work-create", object{"operation_id": "status-create-001", "title": "Bound work", "intent": "Track one issue", "work_type": "fix"})
	id := model.S(created["work_id"])
	config := call("work-provider-configure", object{"operation_id": "status-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	generation := config["binding_generation"]
	expected := func(value object) object {
		return object{"revision": value["revision"], "model_sha256": value["model_sha256"]}
	}
	staged := call("work-effect-stage", object{"operation_id": "status-stage-create-001", "work_id": id, "binding_generation": generation, "expected": expected(created)})
	claimed := call("work-effect-claim", object{"operation_id": "status-claim-create-001", "work_id": id, "binding_generation": generation, "attempt_id": "status-attempt-create-001", "expected": expected(staged)})
	bound := call("work-effect-record", object{"operation_id": "status-record-create-001", "work_id": id, "binding_generation": generation, "attempt_id": "status-attempt-create-001", "remote_issue_number": int64(7), "remote_issue_url": "https://github.com/arbiterForge/disposable/issues/7", "remote_state": "open", "expected": expected(claimed)})
	staged = call("work-effect-stage", object{"operation_id": "status-stage-close-001", "work_id": id, "binding_generation": generation, "kind": "status_update", "desired_state": "closed", "expected": expected(bound)})
	effect := model.M(staged["provider_effect"])
	if model.I(effect["remote_issue_number"]) != 7 || model.S(effect["remote_state"]) != "open" || model.S(effect["desired_state"]) != "closed" {
		t.Fatalf("status stage lost its issue binding or observed baseline: %v", effect)
	}
	conflict := call("work-effect-conflict", object{"operation_id": "status-conflict-001", "work_id": id, "binding_generation": generation, "remote_state": "closed", "expected": expected(staged)})
	if model.S(model.M(conflict["provider_effect"])["status"]) != "conflict" {
		t.Fatalf("remote change was not retained for explicit reconciliation: %v", conflict)
	}
	view := call("work-view", object{"work_id": id})
	if html := model.S(view["html"]); !strings.Contains(html, "Remote issue is closed") || !strings.Contains(html, "Local intent was closed") {
		t.Fatalf("selected work view omitted the remote conflict state: %s", html)
	}
	staged = call("work-effect-stage", object{"operation_id": "status-stage-open-001", "work_id": id, "binding_generation": generation, "kind": "status_update", "desired_state": "open", "expected": expected(conflict)})
	claimed = call("work-effect-claim", object{"operation_id": "status-claim-open-001", "work_id": id, "binding_generation": generation, "attempt_id": "status-attempt-open-001", "expected": expected(staged)})
	record := object{"protocol": Protocol, "operation_id": "status-record-open-001", "work_id": id, "binding_generation": generation, "attempt_id": "status-attempt-open-001", "remote_issue_number": int64(7), "remote_issue_url": "https://github.com/arbiterForge/disposable/issues/7", "remote_state": "closed", "expected": expected(claimed)}
	if _, err := Run(root, "work-effect-record", record); fault.Code(err) != "INVALID_REMOTE_BINDING" {
		t.Fatalf("stale status readback was accepted: %v", err)
	}
	record["remote_state"] = "open"
	record["operation_id"] = "status-record-open-002"
	recorded := call("work-effect-record", record)
	if model.S(model.M(recorded["provider_effect"])["remote_state"]) != "open" || model.S(model.M(recorded["provider_effect"])["status"]) != "synchronized" {
		t.Fatalf("verified status result was not retained: %v", recorded)
	}
	staged = call("work-effect-stage", object{"operation_id": "status-stage-uncertain-001", "work_id": id, "binding_generation": generation, "kind": "status_update", "desired_state": "closed", "expected": expected(recorded)})
	claimed = call("work-effect-claim", object{"operation_id": "status-claim-uncertain-001", "work_id": id, "binding_generation": generation, "attempt_id": "status-attempt-uncertain-001", "expected": expected(staged)})
	resolution := object{"protocol": Protocol, "operation_id": "status-resolve-uncertain-001", "work_id": id, "binding_generation": generation, "attempt_id": "wrong-attempt-001", "remote_state": "open", "expected": expected(claimed)}
	if _, err := Run(root, "work-effect-conflict", resolution); fault.Code(err) != "EFFECT_CLAIM_CHANGED" {
		t.Fatalf("wrong uncertain attempt was accepted: %v", err)
	}
	resolution["attempt_id"] = "status-attempt-uncertain-001"
	resolution["remote_state"] = "closed"
	if _, err := Run(root, "work-effect-conflict", resolution); fault.Code(err) != "INVALID_REMOTE_BINDING" {
		t.Fatalf("matching desired status was falsely recorded as conflict: %v", err)
	}
	resolution["operation_id"] = "status-resolve-uncertain-002"
	resolution["remote_state"] = "open"
	accepted := call("work-effect-conflict", resolution)
	if model.S(model.M(accepted["provider_effect"])["status"]) != "conflict" {
		t.Fatalf("explicit uncertain resolution lost conflict state: %v", accepted)
	}
}

func TestWorkIssueAdoptionRequiresUnboundIdentityAndExactRepository(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	created := call("work-create", object{"operation_id": "adopt-create-001", "title": "Adopt issue", "intent": "Keep existing issue", "work_type": "fix"})
	id := model.S(created["work_id"])
	config := call("work-provider-configure", object{"operation_id": "adopt-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	request := object{"protocol": Protocol, "operation_id": "adopt-issue-001", "work_id": id,
		"binding_generation": config["binding_generation"], "remote_issue_number": int64(7),
		"remote_issue_url": "https://github.com/arbiterForge/disposable/issues/7", "remote_state": "open",
		"expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}}
	request["remote_issue_url"] = "https://github.com/arbiterForge/other/issues/7"
	if _, err := Run(root, "work-effect-adopt", request); fault.Code(err) != "INVALID_REMOTE_BINDING" {
		t.Fatalf("cross-repository adoption was accepted: %v", err)
	}
	request["remote_issue_url"] = "https://github.com/arbiterForge/disposable/issues/7"
	adopted := call("work-effect-adopt", request)
	effect := model.M(adopted["provider_effect"])
	if model.S(effect["status"]) != "synchronized" || model.I(effect["remote_issue_number"]) != 7 || model.S(effect["remote_state"]) != "open" {
		t.Fatalf("verified remote binding was not retained: %v", effect)
	}
	request["operation_id"] = "adopt-issue-002"
	request["expected"] = object{"revision": adopted["revision"], "model_sha256": adopted["model_sha256"]}
	if _, err := Run(root, "work-effect-adopt", request); fault.Code(err) != "EFFECT_ALREADY_SENT" {
		t.Fatalf("duplicate adoption was accepted: %v", err)
	}
}

func TestWorkEffectBindingChangeDoesNotSend(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	call("init-store", object{})
	created := call("work-create", object{"operation_id": "binding-create-001", "title": "Bind", "intent": "Stay scoped", "work_type": "fix"})
	id := created["work_id"].(string)
	first := call("work-provider-configure", object{"operation_id": "binding-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	staged := call("work-effect-stage", object{"operation_id": "binding-stage-001", "work_id": id, "binding_generation": first["binding_generation"],
		"expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	call("work-provider-configure", object{"operation_id": "binding-configure-002", "repository": "arbiterForge/other", "credential_ref": "GH_TOKEN", "effect_timing": "immediate", "expected_config_sha256": first["binding_generation"]})
	_, err := Run(root, "work-effect-claim", object{"protocol": Protocol, "operation_id": "binding-claim-001", "work_id": id,
		"binding_generation": first["binding_generation"], "attempt_id": "binding-attempt-001",
		"expected": object{"revision": staged["revision"], "model_sha256": staged["model_sha256"]}})
	if err == nil || !strings.Contains(err.Error(), "PROVIDER_BINDING_CHANGED") {
		t.Fatalf("old binding was allowed to claim an external effect: %v", err)
	}
	current := call("work-get", object{"work_id": id})
	if model.S(model.M(current["provider_effect"])["status"]) != "pending" {
		t.Fatalf("a refused claim changed portable intent: %v", current)
	}
}

func TestWorkEffectDeferredClaimRequiresMergeObservation(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	call("init-store", object{})
	created := call("work-create", object{"operation_id": "deferred-create-001", "title": "Defer", "intent": "Wait for merge", "work_type": "fix"})
	configured := call("work-provider-configure", object{"operation_id": "deferred-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	id := model.S(created["work_id"])
	staged := call("work-effect-stage", object{"operation_id": "deferred-stage-001", "work_id": id,
		"binding_generation": configured["binding_generation"], "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	claim := object{"protocol": Protocol, "operation_id": "deferred-claim-001", "work_id": id,
		"binding_generation": configured["binding_generation"], "attempt_id": "deferred-attempt-001",
		"expected": object{"revision": staged["revision"], "model_sha256": staged["model_sha256"]}}
	if _, err := Run(root, "work-effect-claim", claim); err == nil || !strings.Contains(err.Error(), "EFFECT_WAITING_FOR_MERGE") {
		t.Fatalf("deferred claim crossed merge boundary without observation: %v", err)
	}
	if model.S(model.M(call("work-get", object{"work_id": id})["provider_effect"])["status"]) != "pending" {
		t.Fatal("refused deferred claim changed portable intent")
	}
	claim["merge_pull_number"], claim["merge_commit_sha"] = int64(3), strings.Repeat("a", 40)
	claimed := call("work-effect-claim", claim)
	effect := model.M(claimed["provider_effect"])
	if model.S(effect["status"]) != "outcome_unknown" || model.I(effect["merge_pull_number"]) != 3 || model.S(effect["merge_commit_sha"]) != strings.Repeat("a", 40) {
		t.Fatalf("verified observation was not retained with the pre-send claim: %v", effect)
	}
	baseRecord := object{"protocol": Protocol, "operation_id": "deferred-record-001", "work_id": id,
		"binding_generation": configured["binding_generation"], "attempt_id": "wrong-attempt-001",
		"remote_issue_number": int64(7), "remote_issue_url": "https://github.com/arbiterForge/disposable/issues/7",
		"expected": object{"revision": claimed["revision"], "model_sha256": claimed["model_sha256"]}}
	if _, err := Run(root, "work-effect-record", baseRecord); err == nil || !strings.Contains(err.Error(), "EFFECT_CLAIM_CHANGED") {
		t.Fatalf("mismatched attempt recorded an issue: %v", err)
	}
	baseRecord["operation_id"], baseRecord["attempt_id"] = "deferred-record-002", "deferred-attempt-001"
	baseRecord["remote_issue_url"] = "https://github.com/arbiterForge/other/issues/7"
	if _, err := Run(root, "work-effect-record", baseRecord); err == nil || !strings.Contains(err.Error(), "INVALID_REMOTE_BINDING") {
		t.Fatalf("wrong repository recorded an issue: %v", err)
	}
	if model.S(model.M(call("work-get", object{"work_id": id})["provider_effect"])["status"]) != "outcome_unknown" {
		t.Fatal("refused record changed the uncertain pre-send claim")
	}
}

func TestWorkEffectConcurrentSyncHasOneClaim(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, request object) object {
		t.Helper()
		request["protocol"] = Protocol
		value, err := Run(root, op, request)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	call("init-store", object{})
	created := call("work-create", object{"operation_id": "concurrent-effect-create-001", "title": "One issue", "intent": "One claim", "work_type": "fix"})
	id := created["work_id"].(string)
	config := call("work-provider-configure", object{"operation_id": "concurrent-effect-configure-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	staged := call("work-effect-stage", object{"operation_id": "concurrent-effect-stage-001", "work_id": id, "binding_generation": config["binding_generation"],
		"expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	var wg sync.WaitGroup
	wins := make(chan error, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, err := Run(root, "work-effect-claim", object{"protocol": Protocol,
				"operation_id": fmt.Sprintf("concurrent-effect-claim-%03d", i), "work_id": id,
				"binding_generation": config["binding_generation"], "attempt_id": fmt.Sprintf("concurrent-attempt-%03d", i),
				"expected": object{"revision": staged["revision"], "model_sha256": staged["model_sha256"]}})
			wins <- err
		}(i)
	}
	wg.Wait()
	close(wins)
	succeeded := 0
	for err := range wins {
		if err == nil {
			succeeded++
		}
	}
	if succeeded != 1 {
		t.Fatalf("%d concurrent claims succeeded; want exactly one", succeeded)
	}
}

func TestWorkPortableIdentitySurvivesFreshLocalStore(t *testing.T) {
	source := testutil.Root(t)
	if _, err := Run(source, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	value, err := Run(source, "work-create", object{"protocol": Protocol, "operation_id": "portable-create-001", "title": "Portable work", "intent": "Survive a new clone", "work_type": "feature"})
	if err != nil {
		t.Fatal(err)
	}
	created := value.(map[string]any)
	target := testutil.Root(t)
	for _, rel := range []string{projectPath, created["path"].(string)} {
		original, err := os.ReadFile(filepath.Join(source, filepath.FromSlash(rel)))
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(target, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, original, 0644); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := Run(target, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	read, err := Run(target, "work-get", object{"protocol": Protocol, "work_id": created["work_id"]})
	if err != nil {
		t.Fatal(err)
	}
	got := read.(map[string]any)
	if got["work_id"] != created["work_id"] || got["project_id"] != created["project_id"] || got["title"] != "Portable work" {
		t.Fatalf("new local store lost portable identity: %+v", got)
	}
}

func TestWorkListPagesArchiveAndRejectsChangedMembership(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		value, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return value.(map[string]any)
	}
	call("init-store", object{})
	created := []object{}
	for i := 1; i <= 3; i++ {
		request := object{"operation_id": fmt.Sprintf("list-create-%03d", i), "title": fmt.Sprintf("Item %d", i), "intent": "Page safely", "work_type": "chore"}
		if i == 1 {
			request["origin"] = "checkpoint-2026-10-30#triage-1"
		}
		created = append(created, call("work-create", request))
	}
	archived := call("work-update", object{"operation_id": "list-archive-001", "work_id": created[0]["work_id"], "action": "archive", "expected": object{"revision": created[0]["revision"], "model_sha256": created[0]["model_sha256"]}})
	if archived["state"] != "archived" {
		t.Fatalf("archive did not persist: %+v", archived)
	}
	completed := call("work-update", object{"operation_id": "list-complete-002", "work_id": created[1]["work_id"], "action": "complete", "expected": object{"revision": created[1]["revision"], "model_sha256": created[1]["model_sha256"]}})
	first := call("work-list", object{"limit": int64(2), "budget": int64(4096)})
	if first["total"] != int64(3) || len(model.A(first["entries"])) != 2 || first["next_offset"] != int64(2) || first["content_snapshot"] != false {
		t.Fatalf("first page is not bounded: %+v", first)
	}
	second := call("work-list", object{"offset": first["next_offset"], "limit": int64(2), "membership_sha256": first["membership_sha256"], "budget": int64(4096)})
	if len(model.A(second["entries"])) != 1 || second["next_offset"] != nil {
		t.Fatalf("second page did not terminate: %+v", second)
	}
	states := map[string]string{}
	origins := map[string]string{}
	completionDates := map[string]string{}
	for _, item := range append(model.A(first["entries"]), model.A(second["entries"])...) {
		row := model.M(item)
		states[model.S(row["work_id"])] = model.S(row["state"])
		origins[model.S(row["work_id"])] = model.S(row["origin"])
		completionDates[model.S(row["work_id"])] = model.S(row["completed_at"])
	}
	if len(states) != 3 || states[model.S(created[0]["work_id"])] != "archived" {
		t.Fatalf("archived work missing from bounded list: %+v", states)
	}
	if origins[model.S(created[0]["work_id"])] != "checkpoint-2026-10-30#triage-1" {
		t.Fatalf("archived work origin missing from bounded list: %+v", origins)
	}
	if completionDates[model.S(created[1]["work_id"])] != model.S(completed["completed_at"]) || completionDates[model.S(created[2]["work_id"])] != "" {
		t.Fatalf("bounded list lost completion age or invented one: %+v", completionDates)
	}
	call("work-create", object{"operation_id": "list-create-004", "title": "New member", "intent": "Change membership", "work_type": "chore"})
	_, err := Run(root, "work-list", object{"protocol": Protocol, "offset": first["next_offset"], "membership_sha256": first["membership_sha256"]})
	if err == nil || !strings.Contains(err.Error(), "STALE_CURSOR") {
		t.Fatalf("membership change did not invalidate continuation: %v", err)
	}
}

func TestWorkListBudgetBoundaryMatchesEncodedPage(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 24; i++ {
		_, err := Run(root, "work-create", object{
			"protocol": Protocol, "operation_id": fmt.Sprintf("budget-create-%03d", i),
			"title":  fmt.Sprintf("Item %02d %s", i, strings.Repeat("x", 90)),
			"intent": "Keep page boundaries stable", "work_type": "chore",
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	fullValue, err := Run(root, "work-list", object{"protocol": Protocol, "limit": int64(64), "budget": int64(65536)})
	if err != nil {
		t.Fatal(err)
	}
	full := model.M(fullValue)
	all := model.A(full["entries"])
	if len(all) != 24 {
		t.Fatalf("full page has %d entries", len(all))
	}
	terminalBytes, err := json.Marshal(full)
	if err != nil {
		t.Fatal(err)
	}
	for _, budget := range []int64{4096, 5000, 8000, int64(len(terminalBytes)) + 511, 65536} {
		want := 0
		for n := 1; n <= len(all); n++ {
			var nextOffset any = int64(n)
			if n == len(all) {
				nextOffset = nil
			}
			candidate := object{
				"project_id": full["project_id"], "membership_sha256": full["membership_sha256"],
				"entries": all[:n], "offset": int64(0), "total": int64(len(all)),
				"next_offset": nextOffset, "content_snapshot": false,
			}
			encoded, err := json.Marshal(candidate)
			if err != nil {
				t.Fatal(err)
			}
			if int64(len(encoded))+512 > budget {
				break
			}
			want = n
		}
		value, err := Run(root, "work-list", object{"protocol": Protocol, "limit": int64(64), "budget": budget})
		if err != nil {
			t.Fatalf("budget %d: %v", budget, err)
		}
		page := model.M(value)
		if got := len(model.A(page["entries"])); got != want {
			t.Fatalf("budget %d: %d entries, want %d", budget, got, want)
		}
		encoded, err := json.Marshal(page)
		if err != nil || int64(len(encoded))+512 > budget {
			t.Fatalf("budget %d: encoded page %d bytes, error %v", budget, len(encoded), err)
		}
		if want == len(all) && page["next_offset"] != nil {
			t.Fatalf("budget %d: terminal page has a continuation", budget)
		}
	}
}

func TestWorkListBeforeFirstCreateIsEmptyButOrphansRefuse(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	value, err := Run(root, "work-list", object{"protocol": Protocol, "limit": int64(1)})
	if err != nil {
		t.Fatalf("fresh native project must have an empty selected listing: %v", err)
	}
	listed := model.M(value)
	if listed["total"] != int64(0) || len(model.A(listed["entries"])) != 0 || listed["next_offset"] != nil {
		t.Fatalf("fresh listing is not empty: %+v", listed)
	}
	if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(projectPath))); !os.IsNotExist(err) {
		t.Fatalf("listing created project identity before a write: %v", err)
	}
	created, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "first-work-001", "title": "First", "intent": "Retain first identity", "work_type": "chore"})
	if err != nil {
		t.Fatal(err)
	}
	value, err = Run(root, "work-list", object{"protocol": Protocol, "limit": int64(1)})
	if err != nil || model.M(value)["total"] != int64(1) || model.M(model.A(model.M(value)["entries"])[0])["work_id"] != model.M(created)["work_id"] {
		t.Fatalf("first work did not appear after the empty listing: %v, %+v", err, value)
	}

	orphanRoot := testutil.Root(t)
	if _, err := Run(orphanRoot, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	orphanDir := filepath.Join(orphanRoot, ".codearbiter", "work")
	if err := os.MkdirAll(orphanDir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(orphanDir, "WORK-"+strings.Repeat("A", 32)+".html"), []byte("orphan"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(orphanRoot, "work-list", object{"protocol": Protocol}); err == nil || !strings.Contains(err.Error(), "INVALID_PROJECT") {
		t.Fatalf("orphan work without project identity was accepted: %v", err)
	}
}

func TestWorkOriginsFindsArchivedIdentityInOneBoundedRead(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		value, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(value)
	}
	call("init-store", object{})
	origin := "checkpoint-2026-10-30#triage-1"
	query := object{"origins": []any{origin, "checkpoint-2026-10-30#triage-2"}}
	if got := call("work-origins", query); len(model.A(got["matches"])) != 0 {
		t.Fatalf("fresh project reported an origin match: %+v", got)
	}
	created := call("work-create", object{"operation_id": "origin-batch-001", "title": "Archived", "intent": "Retain correlation", "work_type": "chore", "origin": origin})
	call("work-update", object{"operation_id": "origin-batch-002", "work_id": created["work_id"], "action": "archive", "expected": object{"revision": created["revision"], "model_sha256": created["model_sha256"]}})
	got := call("work-origins", query)
	rows := model.A(got["matches"])
	if len(rows) != 1 || model.M(rows[0])["origin"] != origin || model.M(rows[0])["work_id"] != created["work_id"] || model.M(rows[0])["state"] != "archived" {
		t.Fatalf("archived correlation was not returned exactly once: %+v", got)
	}
	if _, err := Run(root, "work-origins", object{"protocol": Protocol, "origins": []any{origin, origin}}); err == nil {
		t.Fatal("duplicate origin query was accepted")
	}
}

func TestWorkConcurrentCreatesShareProjectButNotIdentity(t *testing.T) {
	root := testutil.Root(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	type result struct {
		value object
		err   error
	}
	results := make(chan result, 2)
	var group sync.WaitGroup
	for i := 1; i <= 2; i++ {
		group.Add(1)
		go func(i int) {
			defer group.Done()
			value, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": fmt.Sprintf("parallel-create-%03d", i), "title": "Parallel title", "intent": "Distinct work", "work_type": "chore"})
			if err != nil {
				results <- result{err: err}
				return
			}
			results <- result{value: value.(map[string]any)}
		}(i)
	}
	group.Wait()
	close(results)
	items := []object{}
	for got := range results {
		if got.err != nil {
			t.Fatal(got.err)
		}
		items = append(items, got.value)
	}
	if len(items) != 2 || items[0]["work_id"] == items[1]["work_id"] || items[0]["project_id"] != items[1]["project_id"] {
		t.Fatalf("parallel creates lost one owner or conflated identities: %+v", items)
	}
}
