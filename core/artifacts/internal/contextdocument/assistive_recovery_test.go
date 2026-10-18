package contextdocument

import (
	"bytes"
	"errors"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestOrdinaryContextAdoptionRecoveryPreservesHistory(t *testing.T) {
	for _, mode := range []string{"complete", "rollback"} {
		t.Run(mode, func(t *testing.T) {
			f, done := mutationFixture(t, "ordinary-recovery")
			defer done()
			old := []byte("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n# Project: Old\n\nHuman bytes.\n")
			prior := []byte(`{"schema":1,"doc":"CONTEXT","entries":[]}`)
			mutationWrite(t, f, recoveryDocument, old)
			mutationWrite(t, f, recoveryProvenance, prior)
			r := mutationRequest(t, "adopt", old, prior, "ordinary-adoption-0001")
			f.Inject = func(point string) error {
				if point == "after-replace-0" {
					return errors.New("fixture interruption")
				}
				return nil
			}
			if _, err := ApplyOrdinary(f, r); fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
				t.Fatalf("interruption: %v", err)
			}
			f.Inject = nil
			if _, err := ApplyOrdinary(f, r); fault.Code(err) != "RECOVERY_REQUIRED" {
				t.Fatalf("pending retry accepted: %v", err)
			}
			if _, err := f.Recover(r.OperationID, mode); err != nil {
				t.Fatal(err)
			}
			if mode == "rollback" {
				if !bytes.Equal(mutationRead(t, f, recoveryDocument), old) || !bytes.Equal(mutationRead(t, f, recoveryProvenance), prior) {
					t.Fatal("rollback lost human bytes or v1 provenance")
				}
				if _, err := ApplyOrdinary(f, r); fault.Code(err) != "OPERATION_ROLLED_BACK" {
					t.Fatalf("rolled back operation retried: %v", err)
				}
			} else {
				out, err := ApplyOrdinary(f, r)
				if err != nil || !out.Replay {
					t.Fatalf("completed recovery retry: %v / %v", out, err)
				}
				if !bytes.Equal(mutationRead(t, f, recoveryProvenance), r.ProposedProvenance) {
					t.Fatal("completed recovery lost provenance")
				}
			}
		})
	}
}
