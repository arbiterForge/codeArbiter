//go:build linux || darwin || windows

package store

import (
	"bytes"
	"errors"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func fs(t *testing.T) *FS {
	t.Helper()
	f, e := Open(testutil.Root(t))
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { f.Close() })
	return f
}
func TestTransactionalCAS(t *testing.T) {
	f := fs(t)
	h := canonical.BytesHash([]byte("request"))
	p := ".codearbiter/specs/test.html"
	o, e := f.Commit("test-cas-0001", h, []Edit{{p, nil, []byte("old")}})
	if e != nil || o.State != "committed" {
		t.Fatal(o, e)
	}
	o, e = f.Commit("test-cas-0001", h, nil)
	if e != nil || !o.Replay {
		t.Fatal(o, e)
	}
	if _, e = f.Commit("test-cas-0001", canonical.BytesHash(nil), nil); fault.Code(e) != "OPERATION_ID_REUSE" {
		t.Fatal(e)
	}
	if _, e = f.Commit("test-cas-0002", h, []Edit{{p, []byte("wrong"), []byte("new")}}); fault.Code(e) != "REVISION_CONFLICT" {
		t.Fatal(e)
	}
	b, _ := f.Read(p, 100)
	if string(b) != "old" {
		t.Fatal("failed CAS changed bytes")
	}
}
func TestReplaceRecovery(t *testing.T) {
	for _, step := range []string{"after-stage-0", "after-journal", "after-replace-0", "after-replace-1", "after-complete"} {
		for _, mode := range []string{"complete", "rollback"} {
			t.Run(step+"/"+mode, func(t *testing.T) {
				f := fs(t)
				p, q := ".codearbiter/specs/a.html", ".codearbiter/plans/a.html"
				h := canonical.BytesHash([]byte("request"))
				if _, e := f.Commit("initial-0001", h, []Edit{{p, nil, []byte("a")}, {q, nil, []byte("b")}}); e != nil {
					t.Fatal(e)
				}
				f.Inject = func(s string) error {
					if s == step {
						return errors.New("injected")
					}
					return nil
				}
				_, e := f.Commit("update-0001", h, []Edit{{p, []byte("a"), []byte("A")}, {q, []byte("b"), []byte("B")}})
				if e == nil {
					t.Fatal("fault not injected")
				}
				f.Inject = nil
				if step == "after-stage-0" {
					a, _ := f.Read(p, 100)
					b, _ := f.Read(q, 100)
					if string(a) != "a" || string(b) != "b" {
						t.Fatal("precommit changed live bytes")
					}
					if _, e = f.Commit("update-0001", h, []Edit{{p, []byte("a"), []byte("A")}, {q, []byte("b"), []byte("B")}}); e != nil {
						t.Fatal(e)
					}
					return
				}
				o, e := f.Recover("update-0001", mode)
				if e != nil {
					t.Fatal(e)
				}
				a, _ := f.Read(p, 100)
				b, _ := f.Read(q, 100)
				if o.State == "committed" {
					if string(a) != "A" || string(b) != "B" {
						t.Fatal("complete failed")
					}
				} else if string(a) != "a" || string(b) != "b" {
					t.Fatal("rollback failed")
				}
			})
		}
	}
}
func TestRecoveryConflictPreservesExternalEdit(t *testing.T) {
	f := fs(t)
	h := canonical.BytesHash(nil)
	p := "a.html"
	f.Inject = func(s string) error {
		if s == "after-replace-0" {
			return errors.New("interrupt")
		}
		return nil
	}
	_, _ = f.Commit("conflict-0001", h, []Edit{{p, nil, []byte("new")}})
	f.Inject = nil
	os.WriteFile(filepath.Join(f.Root, p), []byte("external"), 0600)
	if _, e := f.Recover("conflict-0001", "rollback"); fault.Code(e) != "RECOVERY_CONFLICT" {
		t.Fatal(e)
	}
	b, _ := f.Read(p, 100)
	if string(b) != "external" {
		t.Fatal("external bytes lost")
	}
}
func TestPathEscapeAndSymlink(t *testing.T) {
	f := fs(t)
	outside := testutil.Root(t)
	os.WriteFile(filepath.Join(outside, "secret"), []byte("secret"), 0600)
	if e := os.Symlink(outside, filepath.Join(f.Root, "escape")); e != nil {
		t.Fatal(e)
	}
	for _, p := range []string{"../secret", "escape/secret"} {
		if _, e := f.Read(p, 100); e == nil {
			t.Fatal("escape accepted")
		}
	}
	if _, e := f.Commit("escape-0001", canonical.BytesHash(nil), []Edit{{"escape/new", nil, []byte("x")}}); e == nil {
		t.Fatal("symlink write accepted")
	}
	if _, e := os.Stat(filepath.Join(outside, "new")); !os.IsNotExist(e) {
		t.Fatal("escaped write")
	}
}
func TestWriterLock(t *testing.T) {
	f := fs(t)
	g, e := Open(f.Root)
	if e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	unlock, e := f.Lock(true, time.Second)
	if e != nil {
		t.Fatal(e)
	}
	defer unlock()
	if _, e = g.Lock(true, 20*time.Millisecond); fault.Code(e) != "LOCK_TIMEOUT" {
		t.Fatal(e)
	}
}
func TestCreateRaceDoesNotOverwrite(t *testing.T) {
	f := fs(t)
	f.Inject = func(s string) error {
		if s == "before-replace-0" {
			return os.WriteFile(filepath.Join(f.Root, "new.html"), []byte("external"), 0600)
		}
		return nil
	}
	_, e := f.Commit("race-create-01", canonical.BytesHash(nil), []Edit{{"new.html", nil, []byte("ours")}})
	if e == nil {
		t.Fatal("expected conflict")
	}
	b, _ := f.Read("new.html", 100)
	if !bytes.Equal(b, []byte("external")) {
		t.Fatal(fmt.Sprintf("overwrote race winner: %s", b))
	}
}
