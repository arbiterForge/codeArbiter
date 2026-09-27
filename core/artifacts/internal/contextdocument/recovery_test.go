package contextdocument

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const recoveryDocument = ".codearbiter/CONTEXT.md"
const recoveryProvenance = ".codearbiter/.provenance/CONTEXT.json"

func recoveryBytes(t *testing.T, f *store.FS, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(f.Root, filepath.FromSlash(path)))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func recoveryPending(t *testing.T, f *store.FS, want ...string) {
	t.Helper()
	got, err := f.Pending()
	if err != nil || len(got) != len(want) {
		t.Fatalf("pending = %v, %v; want %v", got, err, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pending = %v; want %v", got, want)
		}
	}
}

func TestContextRecoveryAndPaths(t *testing.T) {
	t.Run("interruptions_before_and_after_each_replacement", func(t *testing.T) {
		points := []string{
			"after-stage-0", "after-stage-1", "after-journal",
			"before-replace-0", "after-replace-0", "before-replace-1",
			"after-replace-1", "after-complete",
		}
		for _, point := range points {
			for _, mode := range []string{"complete", "rollback"} {
				f, done := mutationFixture(t, point+mode)
				r := mutationRequest(t, "create", nil, nil, "context-recover-0001")
				preview, _, err := PreviewBinding(r)
				if err != nil {
					t.Fatal(err)
				}
				f.Inject = func(at string) error {
					if at == point {
						return errors.New("interrupted at " + at)
					}
					return nil
				}
				_, err = Apply(f, r, fixtureMutationAuthority(t, r))
				if err == nil {
					t.Fatalf("%s: fault did not interrupt Apply", point)
				}
				f.Inject = nil
				beforeJournal := strings.HasPrefix(point, "after-stage-")
				committed := point == "after-complete"
				if beforeJournal {
					if recoveryBytes(t, f, recoveryDocument) != nil || recoveryBytes(t, f, recoveryProvenance) != nil {
						t.Fatalf("%s: changed target before journal", point)
					}
					recoveryPending(t, f)
					out, retryErr := Apply(f, r, fixtureMutationAuthority(t, r))
					if retryErr != nil || out.State != "committed" || out.Replay {
						t.Fatalf("%s: identical pre-journal retry = %+v, %v", point, out, retryErr)
					}
				} else if committed {
					recoveryPending(t, f)
					out, retryErr := Apply(f, r, fixtureMutationAuthority(t, r))
					if retryErr != nil || out.State != "committed" || !out.Replay {
						t.Fatalf("%s: lost response replay = %+v, %v", point, out, retryErr)
					}
				} else {
					recoveryPending(t, f, r.OperationID)
					// Individual replacements are visible before the journal is final.
					wantDocument := point == "after-replace-0" || point == "before-replace-1" || point == "after-replace-1"
					wantProvenance := point == "after-replace-1"
					if (recoveryBytes(t, f, recoveryDocument) != nil) != wantDocument || (recoveryBytes(t, f, recoveryProvenance) != nil) != wantProvenance {
						t.Fatalf("%s: wrong intermediate replacement state", point)
					}
					if _, retryErr := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(retryErr) != "RECOVERY_REQUIRED" {
						t.Fatalf("%s: pending Apply = %v", point, retryErr)
					}
					out, recoverErr := f.Recover(r.OperationID, mode)
					if recoverErr != nil {
						t.Fatalf("%s/%s: recovery = %+v, %v", point, mode, out, recoverErr)
					}
					recoveryPending(t, f)
					if mode == "rollback" {
						if out.State != "rolled_back" || recoveryBytes(t, f, recoveryDocument) != nil || recoveryBytes(t, f, recoveryProvenance) != nil {
							t.Fatalf("%s: rollback left context bytes", point)
						}
						if _, retryErr := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(retryErr) != "OPERATION_ROLLED_BACK" {
							t.Fatalf("%s: rolled-back ID retried: %v", point, retryErr)
						}
						done()
						continue
					}
					if out.State != "committed" {
						t.Fatalf("%s: complete state = %s", point, out.State)
					}
				}
				if !bytes.Equal(recoveryBytes(t, f, recoveryDocument), preview.Bytes) || !bytes.Equal(recoveryBytes(t, f, recoveryProvenance), r.ProposedProvenance) {
					t.Fatalf("%s/%s: final document/provenance pair differs", point, mode)
				}
				if _, err := f.Infrastructure(); err != nil {
					t.Fatalf("%s/%s: final infrastructure = %v", point, mode, err)
				}
				done()
			}
		}
	})

	t.Run("lost_response_replay_and_duplicate_operation_ids", func(t *testing.T) {
		f, done := mutationFixture(t, "lost-response")
		defer done()
		r := mutationRequest(t, "create", nil, nil, "context-lost-0001")
		f.Inject = func(at string) error {
			if at == "after-complete" {
				return errors.New("response lost")
			}
			return nil
		}
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
			t.Fatalf("lost response = %v", err)
		}
		f.Inject = nil
		beforeDoc := recoveryBytes(t, f, recoveryDocument)
		beforeProv := recoveryBytes(t, f, recoveryProvenance)
		out, err := Apply(f, r, fixtureMutationAuthority(t, r))
		if err != nil || !out.Replay || out.State != "committed" || len(out.Paths) != 2 || out.Result["document_id"] != "CONTEXT" {
			t.Fatalf("replay lost durable result = %+v, %v", out, err)
		}
		other := r
		other.Typed = mutationTyped("Different")
		if _, err := Apply(f, other, fixtureMutationAuthority(t, other)); fault.Code(err) != "OPERATION_ID_REUSE" {
			t.Fatalf("different input reused ID: %v", err)
		}
		if !bytes.Equal(beforeDoc, recoveryBytes(t, f, recoveryDocument)) || !bytes.Equal(beforeProv, recoveryBytes(t, f, recoveryProvenance)) {
			t.Fatal("replay or ID collision changed bytes")
		}
		// Historical replay reports the durable outcome even after a later human
		// edit. It neither revalidates current freshness nor rewrites that edit.
		human := []byte("later human content\n")
		mutationWrite(t, f, recoveryDocument, human)
		later, err := Apply(f, r, fixtureMutationAuthority(t, r))
		if err != nil || !later.Replay || later.State != "committed" || later.Result["document_sha256"] != out.Result["document_sha256"] {
			t.Fatalf("historical replay after human edit = %+v, %v", later, err)
		}
		if !bytes.Equal(recoveryBytes(t, f, recoveryDocument), human) || !bytes.Equal(recoveryBytes(t, f, recoveryProvenance), beforeProv) {
			t.Fatal("historical replay rewrote later content")
		}
	})

	t.Run("divergent_human_edits_preserve_pending_transaction", func(t *testing.T) {
		for _, changed := range []string{recoveryDocument, recoveryProvenance} {
			f, done := mutationFixture(t, changed)
			r := mutationRequest(t, "create", nil, nil, "context-human-0001")
			f.Inject = func(at string) error {
				if at == "after-replace-1" {
					return errors.New("interrupted")
				}
				return nil
			}
			if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
				t.Fatalf("%s: fault = %v", changed, err)
			}
			f.Inject = nil
			human := []byte("human edit outside journal\n")
			mutationWrite(t, f, changed, human)
			other := recoveryDocument
			if changed == other {
				other = recoveryProvenance
			}
			untouched := recoveryBytes(t, f, other)
			for _, mode := range []string{"complete", "rollback"} {
				if _, err := f.Recover(r.OperationID, mode); fault.Code(err) != "RECOVERY_CONFLICT" {
					t.Fatalf("%s/%s: divergent edit accepted: %v", changed, mode, err)
				}
				if !bytes.Equal(recoveryBytes(t, f, changed), human) || !bytes.Equal(recoveryBytes(t, f, other), untouched) {
					t.Fatalf("%s/%s: recovery changed human or companion bytes", changed, mode)
				}
				recoveryPending(t, f, r.OperationID)
			}
			done()
		}
	})

	t.Run("symlink_target_fails_before_context_mutation", func(t *testing.T) {
		f, done := mutationFixture(t, "symlink")
		defer done()
		outside := t.TempDir()
		dir := filepath.Join(f.Root, ".codearbiter", ".provenance")
		if err := os.Symlink(outside, dir); err != nil {
			// Windows hosts without symlink privilege have an unqualified cell.
			t.Skipf("native symlink creation unavailable: %v", err)
		}
		r := mutationRequest(t, "create", nil, nil, "context-link-0001")
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); err == nil {
			t.Fatal("symlink provenance parent accepted")
		}
		if recoveryBytes(t, f, recoveryDocument) != nil {
			t.Fatal("symlink failure changed document")
		}
		if files, err := os.ReadDir(outside); err != nil || len(files) != 0 {
			t.Fatalf("symlink destination changed: %v %v", files, err)
		}
		recoveryPending(t, f)
	})

	t.Run("case_alias_preserves_human_file", func(t *testing.T) {
		g, finish := mutationFixture(t, "case-alias")
		defer finish()
		alias := ".codearbiter/context.md"
		human := []byte("human lower-case alias\n")
		mutationWrite(t, g, alias, human)
		aliasRequest := mutationRequest(t, "create", nil, nil, "context-case-0001")
		if runtime.GOOS == "windows" {
			if _, err := Apply(g, aliasRequest, fixtureMutationAuthority(t, aliasRequest)); err == nil {
				t.Fatal("case alias accepted as absent canonical document")
			}
			if !bytes.Equal(recoveryBytes(t, g, alias), human) || recoveryBytes(t, g, recoveryProvenance) != nil {
				t.Fatal("case alias conflict changed target")
			}
			return
		}
		if _, err := Apply(g, aliasRequest, fixtureMutationAuthority(t, aliasRequest)); err != nil {
			t.Fatalf("case-distinct target rejected on %s: %v", runtime.GOOS, err)
		}
		if !bytes.Equal(recoveryBytes(t, g, alias), human) || recoveryBytes(t, g, recoveryProvenance) == nil {
			t.Fatal("case-distinct creation changed human alias or lost provenance")
		}
	})

	t.Run("case_colliding_transaction_paths_rejected_before_journal", func(t *testing.T) {
		f, done := mutationFixture(t, "case-collision")
		defer done()
		_, err := f.Commit("context-casepair-0001", canonical.BytesHash([]byte("case-pair")), []store.Edit{
			{Path: ".codearbiter/CONTEXT.md", After: []byte("first")},
			{Path: ".codearbiter/context.md", After: []byte("second")},
		})
		if fault.Code(err) != "INVALID_TRANSACTION" {
			t.Fatalf("case-colliding transaction admitted: %v", err)
		}
		if recoveryBytes(t, f, recoveryDocument) != nil || recoveryBytes(t, f, ".codearbiter/context.md") != nil {
			t.Fatal("case-colliding preflight changed target")
		}
		recoveryPending(t, f)
		const id = "context-casepair-0002"
		entries := []any{}
		for i, path := range []string{".codearbiter/CONTEXT.md", ".codearbiter/context.md"} {
			index := strconv.Itoa(i)
			entries = append(entries, map[string]any{
				"path": path, "before_sha256": nil,
				"after_sha256": canonical.BytesHash([]byte("first")), "size": 5,
				"stage":  ".codearbiter/.ca-artifact-" + id + "-" + index + ".new",
				"backup": ".codearbiter/.artifacts/history/" + id + "-" + index + ".before",
			})
		}
		journal, marshalErr := canonical.Marshal(map[string]any{
			"format": "codearbiter.transaction/0.2.0", "operation_id": id,
			"request_sha256": canonical.BytesHash([]byte("case-pair")),
			"state":          "prepared", "entries": entries, "result": nil,
		})
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		mutationWrite(t, f, ".codearbiter/.artifacts/transactions/"+id+".json", journal)
		if _, err := f.Pending(); fault.Code(err) != "CORRUPT_JOURNAL" {
			t.Fatalf("case-colliding journal admitted: %v", err)
		}
		if !bytes.Equal(recoveryBytes(t, f, ".codearbiter/.artifacts/transactions/"+id+".json"), journal) {
			t.Fatal("rejected journal bytes changed")
		}
	})

	t.Run("unsupported_journal_blocks_context_write_without_replacement", func(t *testing.T) {
		f, done := mutationFixture(t, "unsupported-journal")
		defer done()
		journal := ".codearbiter/.artifacts/transactions/context-unknown-0001.json"
		original := []byte(`{"format":"codearbiter.transaction/9.9.9","operation_id":"context-unknown-0001"}`)
		mutationWrite(t, f, journal, original)
		r := mutationRequest(t, "create", nil, nil, "context-new-0001")
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "CORRUPT_JOURNAL" {
			t.Fatalf("unsupported journal did not block Apply: %v", err)
		}
		if _, err := f.Recover("context-unknown-0001", "complete"); fault.Code(err) != "CORRUPT_JOURNAL" {
			t.Fatalf("unsupported journal recovered: %v", err)
		}
		if !bytes.Equal(recoveryBytes(t, f, journal), original) || recoveryBytes(t, f, recoveryDocument) != nil || recoveryBytes(t, f, recoveryProvenance) != nil {
			t.Fatal("unsupported journal or context bytes changed")
		}
	})
}
