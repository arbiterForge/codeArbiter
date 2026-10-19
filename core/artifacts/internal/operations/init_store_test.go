//go:build linux || darwin || windows

package operations

import (
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// fileDigests maps every regular file under root, except the local store
// metadata directory, to the SHA-256 of its bytes.
func fileDigests(t *testing.T, root string) map[string]string {
	t.Helper()
	out := map[string]string{}
	err := filepath.WalkDir(root, func(p string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if rel == ".codearbiter/.artifacts" || strings.HasPrefix(rel, ".codearbiter/.artifacts/") {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.IsDir() {
			return nil
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		sum := sha256.Sum256(b)
		out[rel] = hex.EncodeToString(sum[:])
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

// freshCheckout returns a repository holding a committed spec but, like a new
// clone or worktree, no local store metadata.
func freshCheckout(t *testing.T) string {
	t.Helper()
	root := testutil.Root(t)
	n := model.M(testutil.Spec()["normative"])
	if _, err := Run(root, "create", object{"protocol": Protocol, "operation_id": "init-store-fixture", "artifact_id": "SPEC-EXAMPLE", "kind": "spec", "slug": "example", "title": n["title"], "summary": n["summary"], "normative": n}); err != nil {
		t.Fatal(err)
	}
	if err := os.RemoveAll(filepath.Join(root, ".codearbiter", ".artifacts")); err != nil {
		t.Fatal(err)
	}
	return root
}

func TestInitStoreCreatesOnlyLockMetadata(t *testing.T) {
	root := freshCheckout(t)
	lock := filepath.Join(root, ".codearbiter", ".artifacts", "store.lock")
	before := fileDigests(t, root)
	out, err := Run(root, "init-store", object{"protocol": Protocol})
	if err != nil {
		t.Fatalf("TARGET: init-store refused on a fresh checkout: %v", err)
	}
	if runtime.GOOS == "linux" {
		// Linux locks the repository directory itself; nothing to create.
		if got := model.S(model.M(out)["store"]); got != "present" {
			t.Fatalf("linux store reported %q, want present", got)
		}
	} else {
		if got := model.S(model.M(out)["store"]); got != "created" {
			t.Fatalf("fresh store reported %q, want created", got)
		}
		if _, err := os.Lstat(lock); err != nil {
			t.Fatalf("init-store left store.lock absent: %v", err)
		}
	}
	if after := fileDigests(t, root); !reflect.DeepEqual(after, before) {
		t.Fatalf("init-store changed files outside the store metadata: before %v after %v", before, after)
	}
}

func TestInitStoreIsIdempotent(t *testing.T) {
	root := freshCheckout(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	lock := filepath.Join(root, ".codearbiter", ".artifacts", "store.lock")
	lockBefore, err := os.ReadFile(lock)
	if runtime.GOOS == "linux" && os.IsNotExist(err) {
		lockBefore, err = nil, nil
	}
	if err != nil {
		t.Fatal(err)
	}
	before := fileDigests(t, root)
	out, err := Run(root, "init-store", object{"protocol": Protocol})
	if err != nil {
		t.Fatalf("TARGET: init-store refused on an initialized store: %v", err)
	}
	if got := model.S(model.M(out)["store"]); got != "present" {
		t.Fatalf("initialized store reported %q, want present", got)
	}
	lockAfter, err := os.ReadFile(lock)
	if runtime.GOOS == "linux" && os.IsNotExist(err) && lockBefore == nil {
		lockAfter, err = nil, nil
	}
	if err != nil || string(lockAfter) != string(lockBefore) {
		t.Fatalf("init-store rewrote store.lock: %v", err)
	}
	if after := fileDigests(t, root); !reflect.DeepEqual(after, before) {
		t.Fatalf("init-store changed an initialized checkout: before %v after %v", before, after)
	}
	if _, err := Run(root, "identity", object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE"}); err != nil {
		t.Fatalf("read after initialization: %v", err)
	}
}
