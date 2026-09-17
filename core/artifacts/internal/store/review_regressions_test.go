//go:build linux

package store

import (
	"errors"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"testing"
	"time"
)

func TestReviewRetryOfRolledBackWriteIsNotSuccess(t *testing.T) {
	f, err := Open(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	unlock, err := f.Lock(true, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	id := "review-rollback-retry"
	h := canonical.BytesHash([]byte("request"))
	f.Inject = func(step string) error {
		if step == "after-journal" {
			return errors.New("interrupted")
		}
		return nil
	}
	if _, err := f.Commit(id, h, []Edit{{Path: "draft.txt", After: []byte("value")}}); fault.Code(err) != "COMMIT_OUTCOME_UNKNOWN" {
		t.Fatal(err)
	}
	f.Inject = nil
	if _, err := f.Recover(id, "rollback"); err != nil {
		t.Fatal(err)
	}
	if _, err := f.Lookup(id, h); fault.Code(err) != "OPERATION_ROLLED_BACK" {
		t.Fatalf("retry must not acknowledge a rolled-back write as successful: %v", err)
	}
}
