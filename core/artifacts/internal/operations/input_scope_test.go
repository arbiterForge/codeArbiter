package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func scopedWrite(t *testing.T, root, name, contents string) {
	t.Helper()
	target := filepath.Join(root, filepath.FromSlash(name))
	if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte(contents), 0600); err != nil {
		t.Fatal(err)
	}
}

func scopedLatest(f *assistiveFixture) object {
	f.t.Helper()
	checks := reportedChecks(f)
	if len(checks) == 0 {
		f.t.Fatal("no reported check")
	}
	return model.M(checks[len(checks)-1])
}

func TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	scopedWrite(t, f.root, "src/stage2.go", "package stage2\n")
	scopedWrite(t, f.root, "shared/api.go", "package shared\n")
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001",
		"fields": object{"shared_inputs": model.List("shared/api.go")},
	}}})
	reportFor(f, "pass", true)
	first := scopedLatest(f)
	if first["worktree_freshness"] != "scoped_unchanged" ||
		first["scope_complete"] != false || first["evidence_assessed"] != false ||
		first["named_tests_verified"] != false {
		t.Fatalf("matching task scope was promoted to full verification: %v", first)
	}
	scopedWrite(t, f.root, "src/stage2.go", "package changed_unrelated\n")
	if got := scopedLatest(f); got["worktree_freshness"] != "scoped_unchanged" {
		t.Fatalf("unrelated task caused false scope invalidation: %v", got)
	}
	scopedWrite(t, f.root, "shared/api.go", "package shared_updated\n")
	if got := scopedLatest(f); got["worktree_freshness"] != "scoped_changed" ||
		got["reported_outcome"] != "pass" || got["definition_current"] != true {
		t.Fatalf("shared interface change did not mark prior result affected: %v", got)
	}
	packet := packetFor(f, "T-001")
	if !strings.Contains(model.S(packet["next_action"]), "shared source input") {
		t.Fatalf("source change not surfaced in next useful action: %v", packet)
	}
	reportFor(f, "fail", true)
	if got := scopedLatest(f); got["reported_outcome"] != "fail" || got["worktree_freshness"] != "scoped_unchanged" {
		t.Fatalf("latest failure or new scoped run was lost: %v", got)
	}
	if model.S(state(f.doc("PLAN-EXAMPLE"), "T-001")["state"]) != "PENDING" {
		t.Fatal("file fingerprint changed implementation state")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult(t *testing.T) {
	f := newAssistiveFixture(t)
	f.mutate("apply", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001",
		"fields": object{"paths": []any{object{"path": "src", "action": "modify"}}},
	}}})
	scopedWrite(t, f.root, "src/first.go", "package src\n")
	scopedWrite(t, f.root, "go.mod", "module example.test/scoped\n")
	reportFor(f, "pass", true)
	if scopedLatest(f)["worktree_freshness"] != "scoped_unchanged" {
		t.Fatal("initial scoped source was not assessed")
	}
	scopedWrite(t, f.root, "unrelated/note.md", "irrelevant")
	if scopedLatest(f)["worktree_freshness"] != "scoped_unchanged" {
		t.Fatal("unrelated file changed scoped assessment")
	}
	scopedWrite(t, f.root, "src/new.go", "package src\n")
	if scopedLatest(f)["worktree_freshness"] != "scoped_changed" {
		t.Fatal("new file in declared source directory not detected")
	}
	if err := os.Remove(filepath.Join(f.root, "src", "new.go")); err != nil {
		t.Fatal(err)
	}
	if scopedLatest(f)["worktree_freshness"] != "scoped_unchanged" {
		t.Fatal("restoring the exact file set did not restore matching digest")
	}
	scopedWrite(t, f.root, "go.sum", "new-locked-dependency\n")
	if scopedLatest(f)["worktree_freshness"] != "scoped_changed" {
		t.Fatal("added shared build lockfile was not detected")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package stage1\n")
	reportFor(f, "pass", true)
	original := scopedLatest(f)
	if original["definition_current"] != true || original["worktree_freshness"] != "scoped_unchanged" {
		t.Fatalf("fixture is not initially current: %v", original)
	}
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{
		"op": "header.update", "fields": object{"summary": "Unrelated spec narrative changed."},
	}}}))
	packet := packetFor(f, "T-001")
	if packet["binding_current"] != false {
		t.Fatal("plan binding silently followed new source")
	}
	if scopedLatest(f)["definition_current"] != true {
		t.Fatal("unrelated narrative invalidated exactly referenced criteria")
	}
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{
		"op": "record.update", "symbol": "AC-001",
		"fields": object{"statement": "Use explicitly ordered config inputs under a changed contract."},
	}}}))
	got := scopedLatest(f)
	if got["definition_current"] != false || got["reported_outcome"] != "pass" {
		t.Fatalf("relevant criterion change failed to stale earlier reported check: %v", got)
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", strings.Repeat("x", maxScopedFileBytes+1))
	reportFor(f, "pass", true)
	note := scopedLatest(f)
	if note["worktree_freshness"] != "unassessed" ||
		note["scope_reason"] != "source_scope_unassessed" ||
		note["evidence_assessed"] != false {
		t.Fatalf("oversized source was treated as fresh or refused progress: %v", note)
	}
	before := f.doc("PLAN-EXAMPLE").Hash()
	if _, err := f.request("apply", f.mutation("PLAN-EXAMPLE", object{"changes": []any{object{
		"op": "record.update", "symbol": "T-001", "fields": object{
			"shared_inputs": model.List("../outside"),
		},
	}}})); fault.Code(err) != "INVALID_PATH" {
		t.Fatalf("unsafe shared source was not rejected: %v", err)
	}
	if f.doc("PLAN-EXAMPLE").Hash() != before {
		t.Fatal("rejected shared path modified plan")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package initial\n")
	reportFor(f, "pass", true)
	doc := f.doc("PLAN-EXAMPLE")
	recorded := model.M(model.A(model.M(model.M(doc.Data["execution"])["task_check_observations"])["T-001"])[0])
	delete(recorded, "criterion_subject_sha256")
	delete(recorded, "scoped_inputs_sha256")
	checks, _ := model.TaskCheckAssessments(doc, f.doc("SPEC-EXAMPLE"), "T-001")
	if note := model.M(checks[0]); note["worktree_freshness"] != "unassessed" ||
		note["definition_current"] != true {
		t.Fatalf("historical record was retroactively given a scoped identity: %v", note)
	}
	f.call("apply", f.mutation("SPEC-EXAMPLE", object{"changes": []any{object{
		"op": "header.update", "fields": object{"summary": "Different current spec"},
	}}}))
	checks, _ = model.TaskCheckAssessments(doc, f.doc("SPEC-EXAMPLE"), "T-001")
	if model.M(checks[0])["definition_current"] != false {
		t.Fatal("legacy whole-spec identity silently acquired newer per-criterion semantics")
	}
	f.assertNoAuthorityFiles()
}

func TestTaskCheckSymlinkInputsAreNotVerified(t *testing.T) {
	f := newAssistiveFixture(t)
	scopedWrite(t, f.root, "src/stage1.go", "package src\n")
	if err := os.Remove(filepath.Join(f.root, "src", "stage1.go")); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(f.root, "linked-target.go")
	if err := os.WriteFile(target, []byte("package link\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, filepath.Join(f.root, "src", "stage1.go")); err != nil {
		t.Skipf("file symlinks unavailable on this host: %v", err)
	}
	reportFor(f, "pass", true)
	if got := scopedLatest(f); got["worktree_freshness"] != "unassessed" {
		t.Fatalf("symlink source was followed or treated current: %v", got)
	}
	f.assertNoAuthorityFiles()
}
