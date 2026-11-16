//go:build linux || darwin || windows

package store

import (
	"errors"
	"fmt"
	iofs "io/fs"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// These additive drafts characterize actual store owners. They do not run
// helpers, external commands or providers, and grant no host qualification.
func journalBoundarySnapshot(t *testing.T, root string) map[string]string {
	t.Helper()
	result := map[string]string{}
	err := filepath.WalkDir(root, func(path string, entry iofs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		if entry.IsDir() {
			result[filepath.ToSlash(rel)+"/"] = "directory"
			return nil
		}
		if !entry.Type().IsRegular() {
			return fmt.Errorf("nonregular owned fixture entry %s", rel)
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		result[filepath.ToSlash(rel)] = canonical.BytesHash(data)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func journalBoundaryTargets(t *testing.T, f *FS) []Edit {
	t.Helper()
	edits := []Edit{{Path: "one.txt", Before: []byte("old-one"), After: []byte("new-one")},
		{Path: "two.txt", Before: []byte("old-two"), After: []byte("new-two")}}
	for _, edit := range edits {
		if err := os.WriteFile(filepath.Join(f.Root, edit.Path), edit.Before, 0600); err != nil {
			t.Fatal(err)
		}
	}
	return edits
}

func journalBoundaryChanges(before, after map[string]string) map[string][2]string {
	changed := map[string][2]string{}
	for path, value := range before {
		next, exists := after[path]
		if !exists {
			changed[path] = [2]string{value, "<absent>"}
		} else if next != value {
			changed[path] = [2]string{value, next}
		}
	}
	for path, value := range after {
		if _, exists := before[path]; !exists {
			changed[path] = [2]string{"<absent>", value}
		}
	}
	return changed
}

func journalBoundaryPrepared(t *testing.T, f *FS, id, point string, edits []Edit) string {
	t.Helper()
	hash := canonical.BytesHash([]byte(id))
	f.Inject = func(step string) error {
		if step == point {
			return errors.New("owned unit interruption")
		}
		return nil
	}
	_, err := f.Commit(id, hash, edits, map[string]any{"marker": "durable-original"})
	f.Inject = nil
	if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
		t.Fatalf("prepared fixture failed: %v", err)
	}
	return hash
}

func TestN02CommitAdmissionAndPrepublicationCleanup(t *testing.T) {
	tooMany := make([]Edit, 513)
	for i := range tooMany {
		tooMany[i] = Edit{Path: fmt.Sprintf("item-%04d.txt", i), After: []byte("value")}
	}
	for _, tc := range []struct {
		name, id, code string
		edits          []Edit
	}{
		{"invalid-id", "bad:id-0001", "INVALID_OPERATION_ID", []Edit{{Path: "safe.txt", After: []byte("new")}}},
		{"zero-edits", "admit-zero-001", "INVALID_TRANSACTION", nil},
		{"too-many", "admit-many-001", "INVALID_TRANSACTION", tooMany},
		{"duplicate", "admit-duplicate-001", "INVALID_TRANSACTION", []Edit{{Path: "same.txt", After: []byte("a")}, {Path: "same.txt", After: []byte("b")}}},
		{"case-alias", "admit-case-001", "INVALID_TRANSACTION", []Edit{{Path: "Case.txt", After: []byte("a")}, {Path: "case.txt", After: []byte("b")}}},
		// Frozen N02:01 says disjoint edits. Current collidesWithTarget only
		// tests EqualFold; this explicit expectation needs Root review and may
		// expose a genuine product failure when execution is authorized.
		{"ancestor-overlap", "admit-ancestor-001", "INVALID_TRANSACTION", []Edit{{Path: "nested", After: []byte("a")}, {Path: "nested/child.txt", After: []byte("b")}}},
		{"ancestor-reversed", "admit-reversed-001", "INVALID_TRANSACTION", []Edit{{Path: "nested/child.txt", After: []byte("b")}, {Path: "nested", After: []byte("a")}}},
		{"ancestor-case-folded", "admit-folded-001", "INVALID_TRANSACTION", []Edit{{Path: "Nested", After: []byte("a")}, {Path: "nested/child.txt", After: []byte("b")}}},
		{"unsafe-path", "admit-path-001", "INVALID_TRANSACTION", []Edit{{Path: "../escape.txt", After: []byte("a")}}},
		{"nil-before-after", "admit-empty-001", "INVALID_TRANSACTION", []Edit{{Path: "empty.txt"}}},
		{"oversized-after", "admit-size-001", "INVALID_TRANSACTION", []Edit{{Path: "oversized.txt", After: make([]byte, canonical.MaxBytes+1)}}},
		{"before-mismatch", "admit-cas-001", "REVISION_CONFLICT", []Edit{{Path: "absent.txt", Before: []byte("not-present"), After: []byte("new")}}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			before := journalBoundarySnapshot(t, f.Root)
			_, err := f.Commit(tc.id, canonical.BytesHash([]byte("valid canonical request")), tc.edits)
			after := journalBoundarySnapshot(t, f.Root)
			changed := journalBoundaryChanges(before, after)
			if fault.Code(err) != tc.code {
				t.Fatalf("want %s: %v; changed owned paths/hashes=%v", tc.code, err, changed)
			}
			if !reflect.DeepEqual(before, after) {
				t.Fatalf("admission refusal changed owned store; changed owned paths/hashes=%v", changed)
			}
		})
	}
	t.Run("valid-prefix-lookalike", func(t *testing.T) {
		f := fs(t)
		before := journalBoundarySnapshot(t, f.Root)
		out, err := f.Commit("admit-lookalike-001", canonical.BytesHash([]byte("disjoint prefix lookalike")),
			[]Edit{{Path: "branch", After: []byte("left")}, {Path: "branching/child.txt", After: []byte("right")}})
		after := journalBoundarySnapshot(t, f.Root)
		if err != nil || out.State != "committed" || len(out.Paths) != 2 {
			t.Fatalf("disjoint lookalike rejected: %v %v; changed owned paths/hashes=%v", out, err, journalBoundaryChanges(before, after))
		}
		for path, want := range map[string]string{"branch": "left", "branching/child.txt": "right"} {
			data, err := f.Read(path, 100)
			if err != nil || string(data) != want {
				t.Fatalf("lookalike target %s missing: %v", path, err)
			}
		}
	})
	t.Run("exact-512", func(t *testing.T) {
		f := fs(t)
		out, err := f.Commit("admit-boundary-512", canonical.BytesHash([]byte("512 valid edits")), tooMany[:512])
		if err != nil || out.State != "committed" || len(out.Paths) != 512 {
			t.Fatalf("512 edit boundary: %v %v", out, err)
		}
		for _, edit := range tooMany[:512] {
			data, err := f.Read(edit.Path, 100)
			if err != nil || string(data) != "value" {
				t.Fatalf("boundary target missing: %s %v", edit.Path, err)
			}
		}
	})
	t.Run("prepublication-cleanup", func(t *testing.T) {
		f := fs(t)
		edits := journalBoundaryTargets(t, f)
		for _, dir := range []string{meta + "/transactions", meta + "/history"} {
			if err := f.Mkdir(dir); err != nil {
				t.Fatal(err)
			}
		}
		before := journalBoundarySnapshot(t, f.Root)
		f.Inject = func(step string) error {
			if step == "after-stage-1" {
				return errors.New("owned prepublication stop")
			}
			return nil
		}
		_, err := f.Commit("prepublication-cleanup-001", canonical.BytesHash([]byte("request")), edits)
		f.Inject = nil
		if err == nil {
			t.Fatal("prepublication stop did not happen")
		}
		if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
			t.Fatal("prepublication failure left stages/backups or changed targets")
		}
	})
}

func TestN02PreparedTargetCASRefusesConcurrentBytes(t *testing.T) {
	f := fs(t)
	edits := journalBoundaryTargets(t, f)
	f.Inject = func(step string) error {
		if step == "after-journal" {
			return os.WriteFile(filepath.Join(f.Root, "one.txt"), []byte("external-one"), 0600)
		}
		return nil
	}
	_, err := f.Commit("postjournal-cas-001", canonical.BytesHash([]byte("request")), edits)
	f.Inject = nil
	if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
		t.Fatalf("postpublication CAS was not uncertain: %v", err)
	}
	for name, want := range map[string]string{"one.txt": "external-one", "two.txt": "old-two"} {
		data, err := f.Read(name, 100)
		if err != nil || string(data) != want {
			t.Fatalf("CAS overwrote %s: %v", name, err)
		}
	}
	pending, err := f.Pending()
	if err != nil || len(pending) != 1 || pending[0] != "postjournal-cas-001" {
		t.Fatalf("pending barrier lost: %v %v", pending, err)
	}
	before := journalBoundarySnapshot(t, f.Root)
	if _, err := f.Recover("postjournal-cas-001", "complete"); fault.Code(err) != "RECOVERY_CONFLICT" {
		t.Fatalf("external edit was not a recovery conflict: %v", err)
	}
	if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
		t.Fatal("recovery conflict changed evidence")
	}
}

func TestN02AcknowledgementWriteFailureRetainsRecoverableOutcome(t *testing.T) {
	f := fs(t)
	id := "acknowledgement-write-001"
	request := canonical.BytesHash([]byte("request"))
	edits := journalBoundaryTargets(t, f)[:1]
	blocker := filepath.Join(f.Root, filepath.FromSlash(journalPath(id)+".next"))
	f.Inject = func(step string) error {
		if step == "after-replace-0" {
			return os.Mkdir(blocker, 0700)
		}
		return nil
	}
	_, err := f.Commit(id, request, edits, map[string]any{"marker": "durable-original"})
	f.Inject = nil
	if fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
		t.Fatalf("ack write failure lost uncertainty: %v", err)
	}
	data, err := f.Read("one.txt", 100)
	if err != nil || string(data) != "new-one" {
		t.Fatalf("effect did not precede ack failure: %v", err)
	}
	journal, err := f.journal(id)
	if err != nil || journal["state"] != "prepared" || model.M(journal["result"])["marker"] != "durable-original" {
		t.Fatalf("recoverable intent lost: %v %v", journal, err)
	}
	backup, err := f.Read(meta+"/history/"+id+"-0.before", 100)
	if err != nil || string(backup) != "old-one" {
		t.Fatalf("original before image lost: %v", err)
	}
	if err := os.Remove(blocker); err != nil {
		t.Fatal(err)
	}
	if out, err := f.Recover(id, "complete"); err != nil || out.State != "committed" {
		t.Fatalf("recover ack failure: %v %v", out, err)
	}
	before := journalBoundarySnapshot(t, f.Root)
	out, err := f.Commit(id, request, edits)
	if err != nil || !out.Replay || out.Result["marker"] != "durable-original" {
		t.Fatalf("exact original result not replayed: %v %v", out, err)
	}
	if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
		t.Fatal("same-ID replay rewrote bytes")
	}
}

func TestN03TerminalRecoveryReplayPreservesBytes(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			f := fs(t)
			id := "terminal-recovery-001"
			edits := journalBoundaryTargets(t, f)
			journalBoundaryPrepared(t, f, id, "after-journal", edits)
			first, err := f.Recover(id, mode)
			if err != nil || first.Replay {
				t.Fatalf("first recovery was not applied: %v %v", first, err)
			}
			want, opposite := "committed", "rollback"
			if mode == "rollback" {
				want, opposite = "rolled_back", "complete"
			}
			if first.State != want {
				t.Fatalf("wrong terminal state: %v", first)
			}
			if err := os.WriteFile(filepath.Join(f.Root, "one.txt"), []byte("later external edit"), 0600); err != nil {
				t.Fatal(err)
			}
			before := journalBoundarySnapshot(t, f.Root)
			for _, repeat := range []string{mode, opposite} {
				out, err := f.Recover(id, repeat)
				if err != nil || !out.Replay || out.State != want || out.OperationID != id || out.Result["marker"] != "durable-original" {
					t.Fatalf("terminal recovery not replayed: %v %v", out, err)
				}
				if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
					t.Fatal("terminal Recover acted as undo/reapply")
				}
			}
		})
	}
}

func TestN03RecoveryPreflightPreservesAllTargetsAndEvidence(t *testing.T) {
	for _, kind := range []string{"third-digest", "missing-stage", "missing-backup"} {
		t.Run(kind, func(t *testing.T) {
			f := fs(t)
			id := "preflight-recovery-001"
			edits := journalBoundaryTargets(t, f)
			point, mode, code := "after-journal", "complete", "CORRUPT_JOURNAL"
			if kind == "missing-backup" {
				point, mode = "after-replace-1", "rollback"
			}
			journalBoundaryPrepared(t, f, id, point, edits)
			switch kind {
			case "third-digest":
				code = "RECOVERY_CONFLICT"
				if err := os.WriteFile(filepath.Join(f.Root, "two.txt"), []byte("external-two"), 0600); err != nil {
					t.Fatal(err)
				}
			case "missing-stage":
				if err := os.Remove(filepath.Join(f.Root, ".ca-artifact-"+id+"-1.new")); err != nil {
					t.Fatal(err)
				}
			case "missing-backup":
				if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(meta+"/history/"+id+"-1.before"))); err != nil {
					t.Fatal(err)
				}
			}
			before := journalBoundarySnapshot(t, f.Root)
			_, err := f.Recover(id, mode)
			// Missing material has been CORRUPT_JOURNAL since fd7; third digest
			// is RECOVERY_CONFLICT. Do not silently rewrite that distinction to
			// match the frozen row's overbroad single diagnostic label.
			if fault.Code(err) != code {
				t.Fatalf("preflight diagnostic: want %s: %v", code, err)
			}
			if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
				t.Fatal("preflight failure mutated an earlier target or evidence")
			}
		})
	}
}

func TestN03UnreadableFinalJournalNeverBecomesClean(t *testing.T) {
	f := fs(t)
	id := "unreadable-boundary-001"
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit(id, request, []Edit{{Path: "one.txt", After: []byte("original")}}); err != nil {
		t.Fatal(err)
	}
	before := journalBoundarySnapshot(t, f.Root)
	rel := journalPath(id)
	restore := journalBoundaryDenyRead(t, filepath.Join(f.Root, filepath.FromSlash(rel)))
	for _, tc := range []struct {
		name string
		call func() error
	}{
		{"pending", func() error { _, err := f.Pending(); return err }},
		{"recover", func() error { _, err := f.Recover(id, "rollback"); return err }},
		{"new-write", func() error {
			_, err := f.Commit("unreadable-new-001", request, []Edit{{Path: "two.txt", After: []byte("new")}})
			return err
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.call()
			detail := fault.Public(err)
			if detail.Code != "IO_ERROR" || detail.Field != rel || fault.Exit(err) != 5 {
				t.Fatalf("unreadable journal became clean or lost bounded target: %+v", detail)
			}
		})
	}
	restore()
	if !reflect.DeepEqual(before, journalBoundarySnapshot(t, f.Root)) {
		t.Fatal("unreadable journal refusal changed owned bytes")
	}
}
