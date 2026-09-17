//go:build linux

package store

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestReviewConflictingBeforeImageIsPreserved(t *testing.T) {
	f := fs(t)
	p := "sample.html"
	if err := os.WriteFile(filepath.Join(f.Root, p), []byte("live"), 0600); err != nil {
		t.Fatal(err)
	}
	backup := filepath.Join(f.Root, ".codearbiter/.artifacts/history/conflict-123-0.before")
	if err := os.MkdirAll(filepath.Dir(backup), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(backup, []byte("foreign backup"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := f.Commit("conflict-123", canonical.BytesHash(nil), []Edit{{p, []byte("live"), []byte("new")}})
	if err == nil {
		t.Fatal("conflicting before image was accepted")
	}
	b, err := os.ReadFile(backup)
	if err != nil || string(b) != "foreign backup" {
		t.Fatalf("failed commit removed unowned backup: %q %v", b, err)
	}
	b, err = os.ReadFile(filepath.Join(f.Root, p))
	if err != nil || string(b) != "live" {
		t.Fatal("live bytes changed")
	}
}

func TestReviewLegacyJournalRemainsReadable(t *testing.T) {
	f := fs(t)
	id, request := "legacy-read-001", canonical.BytesHash(nil)
	if _, err := f.Commit(id, request, []Edit{{"test.html", nil, []byte("x")}}); err != nil {
		t.Fatal(err)
	}
	j, err := f.journal(id)
	if err != nil {
		t.Fatal(err)
	}
	j["format"] = "codearbiter.transaction/0.1.0"
	delete(j, "result")
	b, err := canonical.Marshal(j)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(f.Root, journalPath(id)), b, 0600); err != nil {
		t.Fatal(err)
	}
	o, err := f.Lookup(id, request)
	if err != nil || !o.Replay || o.State != "committed" {
		t.Fatalf("legacy journal refused: %v %v", o, err)
	}
}

func TestReviewNewJournalIsClosed(t *testing.T) {
	f := fs(t)
	id := "closed-journal-001"
	if _, err := f.Commit(id, canonical.BytesHash(nil), []Edit{{"test.html", nil, []byte("x")}}); err != nil {
		t.Fatal(err)
	}
	j, err := f.journal(id)
	if err != nil {
		t.Fatal(err)
	}
	delete(j, "result")
	j["unexpected"] = true
	if err = validJournal(id, j); fault.Code(err) != "CORRUPT_JOURNAL" {
		t.Fatal("unknown journal field accepted", err)
	}
}
