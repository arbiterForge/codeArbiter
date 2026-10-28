//go:build linux || darwin || windows

package store

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func TestObstructedTransactionNamesOffendingEntry(t *testing.T) {
	for _, tc := range []struct {
		name string
		make func(string) error
	}{
		{"foreign-file", func(p string) error { return os.WriteFile(p, []byte("preserve me"), 0600) }},
		{"foreign-directory", func(p string) error { return os.Mkdir(p, 0700) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			if err := f.Mkdir(meta + "/transactions"); err != nil {
				t.Fatal(err)
			}
			rel := meta + "/transactions/unexpected-entry"
			if err := tc.make(filepath.Join(f.Root, filepath.FromSlash(rel))); err != nil {
				t.Fatal(err)
			}
			_, err := f.Pending()
			if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
				t.Fatalf("Pending diagnostic = %+v", got)
			}
			_, err = f.Infrastructure()
			if got := fault.Public(err); got.Code != "RECOVERY_REQUIRED" || got.Field != rel {
				t.Fatalf("Infrastructure diagnostic = %+v", got)
			}
			if _, err := f.Commit("obstructed-001", canonical.BytesHash([]byte("request")), []Edit{{Path: "draft.html", After: []byte("new")}}); err == nil {
				t.Fatal("foreign entry allowed a write")
			}
			if b, err := os.ReadFile(filepath.Join(f.Root, filepath.FromSlash(rel))); tc.name == "foreign-file" && (err != nil || string(b) != "preserve me") {
				t.Fatalf("foreign entry changed: %q %v", b, err)
			}
		})
	}
}

func TestMissingBeforeImageNamesExpectedPath(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit("history-seed-001", request, []Edit{{Path: "draft.html", After: []byte("old")}}); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Commit("history-next-001", request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	journal := filepath.Join(f.Root, filepath.FromSlash(journalPath("history-next-001")))
	journalBefore, err := os.ReadFile(journal)
	if err != nil {
		t.Fatal(err)
	}
	rel := meta + "/history/history-next-001-0.before"
	if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(rel))); err != nil {
		t.Fatal(err)
	}
	if pending, err := f.Pending(); err != nil || len(pending) != 0 {
		t.Fatalf("committed journals should remain readable: %v %v", pending, err)
	}
	if replay, err := f.Lookup("history-next-001", request); err != nil || replay == nil || !replay.Replay {
		t.Fatalf("exact committed replay should remain readable: %+v %v", replay, err)
	}
	_, err = f.Infrastructure()
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("missing before-image diagnostic = %+v", got)
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("missing history changed target: %q %v", got, err)
	}
	if _, err := os.Stat(filepath.Join(f.Root, filepath.FromSlash(rel))); !os.IsNotExist(err) {
		t.Fatalf("missing history was recreated: %v", err)
	}
	if got, err := os.ReadFile(journal); err != nil || string(got) != string(journalBefore) {
		t.Fatalf("missing history changed journal: %q %v", got, err)
	}
	if replay, err := f.Commit("history-next-001", request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil || !replay.Replay {
		t.Fatalf("exact-ID commit replay failed with missing history: %+v %v", replay, err)
	}
	if _, err := f.Commit("history-later-001", request, []Edit{{Path: "draft.html", Before: []byte("new"), After: []byte("later")}}); err != nil {
		t.Fatalf("new write blocked by missing history: %v", err)
	}
	if _, err := f.Infrastructure(); fault.Public(err).Field != rel {
		t.Fatalf("new write silently repaired missing history: %v", err)
	}
}

func TestChangedBeforeImageNamesPathWithoutChangingBytes(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit("changed-seed-001", request, []Edit{{Path: "draft.html", After: []byte("old")}}); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Commit("changed-next-001", request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := meta + "/history/changed-next-001-0.before"
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	if err := os.WriteFile(absolute, []byte("bad"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Infrastructure(); fault.Public(err).Code != "CORRUPT_JOURNAL" || fault.Public(err).Field != rel {
		t.Fatalf("changed before-image diagnostic = %+v", fault.Public(err))
	}
	if got, err := os.ReadFile(absolute); err != nil || string(got) != "bad" {
		t.Fatalf("changed before-image was modified: %q %v", got, err)
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("changed before-image modified target: %q %v", got, err)
	}
}

func TestOversizedBeforeImageNamesPathAndPreservesBytes(t *testing.T) {
	f := fs(t)
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit("large-seed-001", request, []Edit{{Path: "draft.html", After: []byte("old")}}); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Commit("large-next-001", request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := meta + "/history/large-next-001-0.before"
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	oversized := bytes.Repeat([]byte("x"), canonical.MaxBytes+1)
	if err := os.WriteFile(absolute, oversized, 0600); err != nil {
		t.Fatal(err)
	}
	_, err := f.Infrastructure()
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("oversized before-image diagnostic = %+v", got)
	}
	if got, err := os.ReadFile(absolute); err != nil || !bytes.Equal(got, oversized) {
		t.Fatalf("oversized before-image changed: %v", err)
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("oversized before-image modified target: %q %v", got, err)
	}
}

func TestOrphanHistoryNamesEntryWithoutChangingIt(t *testing.T) {
	f := fs(t)
	const rel = meta + "/history/foreign.before"
	if err := f.Mkdir(meta + "/history"); err != nil {
		t.Fatal(err)
	}
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	if err := os.WriteFile(absolute, []byte("preserve me"), 0600); err != nil {
		t.Fatal(err)
	}
	if pending, err := f.Pending(); err != nil || len(pending) != 0 {
		t.Fatalf("orphan history should not block pending inspection: %v %v", pending, err)
	}
	_, err := f.Infrastructure()
	if got := fault.Public(err); got.Code != "ORPHAN_HISTORY" || got.Field != rel {
		t.Fatalf("orphan history diagnostic = %+v", got)
	}
	if got, err := os.ReadFile(absolute); err != nil || string(got) != "preserve me" {
		t.Fatalf("orphan history changed: %q %v", got, err)
	}
}

func TestOversizedJournalAfterSizeBlocksReplayAndRecovery(t *testing.T) {
	f := fs(t)
	const id = "oversize-after-001"
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit(id, request, []Edit{{Path: "draft.html", After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := journalPath(id)
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	original, err := os.ReadFile(absolute)
	if err != nil {
		t.Fatal(err)
	}
	j, err := canonical.Object(original)
	if err != nil {
		t.Fatal(err)
	}
	entry := model.M(model.A(j["entries"])[0])
	entry["size"] = int64(canonical.MaxBytes + 1)
	corrupt, err := canonical.Marshal(j)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(absolute, corrupt, 0600); err != nil {
		t.Fatal(err)
	}
	for _, check := range []struct {
		name string
		run  func() error
	}{
		{"pending", func() error { _, err := f.Pending(); return err }},
		{"replay", func() error { _, err := f.Lookup(id, request); return err }},
		{"recover", func() error { _, err := f.Recover(id, "rollback"); return err }},
		{"snapshot", func() error { _, err := f.Infrastructure(); return err }},
	} {
		t.Run(check.name, func(t *testing.T) {
			if got := fault.Public(check.run()); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
				t.Fatalf("oversized after size diagnostic = %+v", got)
			}
		})
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("invalid journal changed target: %q %v", got, err)
	}
	if got, err := os.ReadFile(absolute); err != nil || string(got) != string(corrupt) {
		t.Fatalf("invalid journal changed: %q %v", got, err)
	}
	if entries, err := f.List(meta + "/history"); err != nil || len(entries) != 0 {
		t.Fatalf("invalid journal wrote history: %v %v", entries, err)
	}
}

func TestUnparseableFinalJournalNamesPathAndBlocksRecovery(t *testing.T) {
	f := fs(t)
	rel := journalPath("broken-journal-001")
	if err := f.Mkdir(meta + "/transactions"); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(f.Root, filepath.FromSlash(rel))
	bad := []byte(`{"format":`)
	if err := os.WriteFile(path, bad, 0600); err != nil {
		t.Fatal(err)
	}
	_, err := f.Pending()
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("Pending diagnostic = %+v", got)
	}
	if _, err := f.Commit("blocked-write-001", canonical.BytesHash([]byte("request")), []Edit{{Path: "draft.html", After: []byte("new")}}); fault.Code(err) != "CORRUPT_JOURNAL" {
		t.Fatalf("malformed final journal allowed write: %v", err)
	}
	_, err = f.Recover("broken-journal-001", "rollback")
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("Recover diagnostic = %+v", got)
	}
	if got, err := os.ReadFile(path); err != nil || string(got) != string(bad) {
		t.Fatalf("unparseable journal changed: %q %v", got, err)
	}
}

func TestOversizedFinalJournalReportsCorruptionAndBlocksWrites(t *testing.T) {
	f := fs(t)
	const id = "oversized-final-001"
	request := canonical.BytesHash([]byte("request"))
	if _, err := f.Commit(id, request, []Edit{{Path: "draft.html", After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := journalPath(id)
	absolute := filepath.Join(f.Root, filepath.FromSlash(rel))
	oversized := bytes.Repeat([]byte("x"), 4<<20+1)
	if err := os.WriteFile(absolute, oversized, 0600); err != nil {
		t.Fatal(err)
	}
	for _, check := range []struct {
		name string
		run  func() error
	}{
		{"pending", func() error { _, err := f.Pending(); return err }},
		{"recover", func() error { _, err := f.Recover(id, "rollback"); return err }},
		{"new-write", func() error {
			_, err := f.Commit("blocked-oversized-001", request, []Edit{{Path: "draft.html", Before: []byte("new"), After: []byte("later")}})
			return err
		}},
	} {
		t.Run(check.name, func(t *testing.T) {
			if got := fault.Public(check.run()); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
				t.Fatalf("oversized journal diagnostic = %+v", got)
			}
		})
	}
	if got, err := f.Read("draft.html", 100); err != nil || string(got) != "new" {
		t.Fatalf("oversized journal changed target: %q %v", got, err)
	}
	if got, err := os.ReadFile(absolute); err != nil || !bytes.Equal(got, oversized) {
		t.Fatalf("oversized journal changed: %v", err)
	}
}

func TestInvalidJournalFilenameNamesEntry(t *testing.T) {
	f := fs(t)
	if err := f.Mkdir(meta + "/transactions"); err != nil {
		t.Fatal(err)
	}
	rel := meta + "/transactions/invalid!.json"
	if err := os.WriteFile(filepath.Join(f.Root, filepath.FromSlash(rel)), []byte("preserve me"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := f.Pending()
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("Pending diagnostic = %+v", got)
	}
	_, err = f.Infrastructure()
	if got := fault.Public(err); got.Code != "CORRUPT_JOURNAL" || got.Field != rel {
		t.Fatalf("Infrastructure diagnostic = %+v", got)
	}
}

func TestPreparedJournalNamesEntryInSnapshotDiagnostic(t *testing.T) {
	f := fs(t)
	id := "prepared-diag-001"
	f.Inject = func(step string) error {
		if step == "after-journal" {
			return os.ErrClosed
		}
		return nil
	}
	if _, err := f.Commit(id, canonical.BytesHash([]byte("request")), []Edit{{Path: "draft.html", After: []byte("new")}}); err == nil {
		t.Fatal("fixture did not stop after journal publication")
	}
	f.Inject = nil
	_, err := f.Infrastructure()
	if got := fault.Public(err); got.Code != "RECOVERY_REQUIRED" || got.Field != journalPath(id) {
		t.Fatalf("prepared journal diagnostic = %+v", got)
	}
}

func TestJournalRemovedBetweenListAndReadBlocksWithPath(t *testing.T) {
	f := fs(t)
	id := "removed-race-001"
	if _, err := f.Commit(id, canonical.BytesHash([]byte("request")), []Edit{{Path: "draft.html", After: []byte("new")}}); err != nil {
		t.Fatal(err)
	}
	rel := journalPath(id)
	f.SetReadHook(func(path string, anchored bool) {
		if path == rel && !anchored {
			if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(rel))); err != nil {
				t.Fatal(err)
			}
			f.SetReadHook(nil)
		}
	})
	_, err := f.Pending()
	if got := fault.Public(err); got.Code != "RECOVERY_REQUIRED" || got.Field != rel {
		t.Fatalf("journal list/read race diagnostic = %+v", got)
	}
}
