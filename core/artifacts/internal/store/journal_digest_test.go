//go:build linux || darwin || windows

package store

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func journalDigestFixture(format string) (string, map[string]any, map[string]any) {
	id := "digest-parity-001"
	entry := map[string]any{
		"path": "draft.html", "stage": ".ca-artifact-" + id + "-0.new",
		"backup": meta + "/history/" + id + "-0.before", "size": int64(3),
		"before_sha256": strings.Repeat("ab", 32), "after_sha256": strings.Repeat("01", 32),
	}
	journal := map[string]any{
		"format": format, "operation_id": id, "state": "committed",
		"request_sha256": strings.Repeat("ef", 32), "entries": []any{entry},
	}
	if format == "codearbiter.transaction/0.2.0" {
		journal["result"] = nil
	}
	return id, journal, entry
}

func TestJournalDigestGrammar(t *testing.T) {
	for _, format := range []string{"codearbiter.transaction/0.1.0", "codearbiter.transaction/0.2.0"} {
		t.Run(format, func(t *testing.T) {
			id, journal, _ := journalDigestFixture(format)
			if err := validJournal(id, journal); err != nil {
				t.Fatal("valid lowercase digests refused", err)
			}
			for _, field := range []string{"request_sha256", "before_sha256", "after_sha256"} {
				for name, value := range map[string]any{
					"uppercase": strings.Repeat("AB", 32), "nonhex": strings.Repeat("g", 64),
					"short": strings.Repeat("a", 63), "long": strings.Repeat("a", 65),
					"newline": strings.Repeat("a", 64) + "\n", "wrong type": int64(1),
				} {
					t.Run(field+"/"+name, func(t *testing.T) {
						id, journal, entry := journalDigestFixture(format)
						target := entry
						if field == "request_sha256" {
							target = journal
						}
						target[field] = value
						if err := validJournal(id, journal); fault.Code(err) != "CORRUPT_JOURNAL" {
							t.Fatalf("malformed %s accepted: %v", field, err)
						}
					})
				}
				id, journal, entry := journalDigestFixture(format)
				if field == "request_sha256" {
					journal[field] = nil
					if err := validJournal(id, journal); fault.Code(err) != "CORRUPT_JOURNAL" {
						t.Fatal("missing request digest accepted", err)
					}
				} else {
					entry[field] = nil
					if err := validJournal(id, journal); err != nil {
						t.Fatal("valid create/delete digest refused", field, err)
					}
				}
			}
		})
	}
}

func TestPendingRejectsCorruptCompletedDigest(t *testing.T) {
	for _, field := range []string{"request_sha256", "before_sha256", "after_sha256"} {
		t.Run(field, func(t *testing.T) {
			f := fs(t)
			request := canonical.BytesHash([]byte("digest fixture"))
			if _, err := f.Commit("digest-create-001", request, []Edit{{Path: "draft.html", After: []byte("old")}}); err != nil {
				t.Fatal(err)
			}
			id := "digest-update-001"
			if _, err := f.Commit(id, request, []Edit{{Path: "draft.html", Before: []byte("old"), After: []byte("new")}}); err != nil {
				t.Fatal(err)
			}
			journal, err := f.journal(id)
			if err != nil {
				t.Fatal(err)
			}
			target := journal
			if field != "request_sha256" {
				target = model.M(model.A(journal["entries"])[0])
			}
			target[field] = strings.Repeat("AB", 32)
			corrupt, err := canonical.Marshal(journal)
			if err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(f.Root, journalPath(id))
			if err := os.WriteFile(path, corrupt, 0600); err != nil {
				t.Fatal(err)
			}
			if _, err := f.Pending(); fault.Code(err) != "CORRUPT_JOURNAL" {
				t.Fatal("completed-history corruption was ignored", err)
			}
			preserved, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(preserved, corrupt) {
				t.Fatal("corrupt history was rewritten", err)
			}
			live, err := f.Read("draft.html", 100)
			if err != nil || string(live) != "new" {
				t.Fatal("live artifact changed", err)
			}
		})
	}
}
