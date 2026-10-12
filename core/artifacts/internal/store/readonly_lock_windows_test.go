//go:build windows

package store

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"testing"
	"time"
	"unsafe"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

type observationLocker interface {
	ObservationLock(bool, time.Duration) (func(), error)
}

func TestWindowsLockNativeLayouts(t *testing.T) {
	if unsafe.Sizeof(uintptr(0)) != 8 {
		t.Fatal("native layout proof covers supported Windows amd64/arm64 only")
	}
	if unsafe.Sizeof(lockUnicodeString{}) != 16 || unsafe.Offsetof(lockUnicodeString{}.Buffer) != 8 ||
		unsafe.Sizeof(lockObjectAttributes{}) != 48 || unsafe.Offsetof(lockObjectAttributes{}.RootDirectory) != 8 ||
		unsafe.Offsetof(lockObjectAttributes{}.ObjectName) != 16 || unsafe.Offsetof(lockObjectAttributes{}.Attributes) != 24 ||
		unsafe.Offsetof(lockObjectAttributes{}.SecurityDescriptor) != 32 || unsafe.Offsetof(lockObjectAttributes{}.SecurityQualityOfService) != 40 ||
		unsafe.Sizeof(lockIOStatus{}) != 16 || unsafe.Offsetof(lockIOStatus{}.Information) != 8 {
		t.Fatal("Windows native ABI layout mismatch")
	}
}

func TestObservationLockRejectsGenericReparseAttributes(t *testing.T) {
	for _, target := range []string{".codearbiter", meta, meta + "/store.lock"} {
		t.Run(target, func(t *testing.T) {
			f := initializedLockFixture(t)
			name := filepath.Join(f.Root, filepath.FromSlash(target))
			// Native non-name-surrogate directory tags require an empty directory.
			// Missing descendants are irrelevant: the tagged ancestor must refuse
			// before either missing-state initialization or descent.
			if target != meta+"/store.lock" {
				if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(meta), "store.lock")); err != nil {
					t.Fatal(err)
				}
				if target == ".codearbiter" {
					if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(meta))); err != nil {
						t.Fatal(err)
					}
				}
			}
			pointer, err := syscall.UTF16PtrFromString(name)
			if err != nil {
				t.Fatal(err)
			}
			handle, err := syscall.CreateFile(pointer, syscall.GENERIC_WRITE, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
			if err != nil {
				t.Fatalf("SETUP: generic reparse handle unavailable: %v", err)
			}
			defer syscall.CloseHandle(handle)
			// Private non-Microsoft tag plus a fixed fixture GUID, no target path.
			// This exercises a real non-name-surrogate reparse object, not a mock.
			header := make([]byte, 24)
			header[0] = 0x42
			for i := 8; i < 24; i++ {
				header[i] = byte(i)
			}
			var count uint32
			if err := syscall.DeviceIoControl(handle, 0x900a4, &header[0], uint32(len(header)), nil, 0, &count, nil); err != nil {
				t.Fatalf("SETUP: generic reparse fixture unavailable: %v", err)
			}
			defer func() {
				if err := syscall.DeviceIoControl(handle, 0x900ac, &header[0], uint32(len(header)), nil, 0, &count, nil); err != nil {
					t.Errorf("fixture generic reparse cleanup: %v", err)
				}
			}()
			readTag := func() []byte {
				b := make([]byte, 16384)
				if err := syscall.DeviceIoControl(handle, 0x900a8, nil, 0, &b[0], uint32(len(b)), &count, nil); err != nil {
					t.Fatal(err)
				}
				return b[:count]
			}
			beforeTag := readTag()
			before := testutil.Tree(t, f.Root)
			release, err := observeLock(t, f, false)
			if release != nil {
				release()
			}
			if fault.Code(err) != "UNSAFE_PATH" {
				t.Fatalf("generic reparse object accepted: %v", err)
			}
			if !bytes.Equal(readTag(), beforeTag) {
				t.Fatal("refusal changed generic reparse bytes")
			}
			testutil.AssertTree(t, f.Root, before)
		})
	}
}

func TestObservationLockPinsExistingRoot(t *testing.T) {
	f := initializedLockFixture(t)
	called := false
	f.Inject = func(step string) error {
		if step != "lock-after-root-open" {
			return nil
		}
		called = true
		if err := os.Rename(f.Root, f.Root+".swapped"); !errors.Is(err, syscall.Errno(32)) {
			t.Fatalf("anchored root replacement was allowed or unexercised: %v", err)
		}
		return nil
	}
	release, err := observeLock(t, f, false)
	if err != nil || !called {
		t.Fatalf("root phase unavailable: %v %v", called, err)
	}
	if err := os.Rename(f.Root, f.Root+".swapped"); !errors.Is(err, syscall.Errno(32)) {
		release()
		t.Fatalf("acquired root pin did not refuse rename: %v", err)
	}
	release()
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(f.Root, f.Root+".released"); err != nil {
		t.Fatalf("released root pin leaked: %v", err)
	}
	if err := os.Rename(f.Root+".released", f.Root); err != nil {
		t.Fatal(err)
	}
}

func observeLock(t *testing.T, f *FS, exclusive bool) (func(), error) {
	t.Helper()
	locker, ok := any(f).(observationLocker)
	if !ok {
		t.Fatal("Windows observation capability is absent; this is not a target RED")
	}
	return locker.ObservationLock(exclusive, 30*time.Millisecond)
}

func initializedLockFixture(t *testing.T) *FS {
	t.Helper()
	f := fs(t)
	release, err := f.Lock(true, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	release()
	return f
}

func TestObservationLockPreservesExclusion(t *testing.T) {
	for _, tc := range []struct {
		name                                                                string
		firstWriter, firstExclusive, secondWriter, secondExclusive, allowed bool
	}{
		{"shared-readers", false, false, false, false, true},
		{"observation-writer", false, false, true, true, false},
		{"writer-observation", true, true, false, false, false},
		{"index-observation", false, true, false, false, false},
		{"observation-index", false, false, false, true, false},
		{"index-writer", false, true, true, true, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := initializedLockFixture(t)
			g, err := Open(f.Root)
			if err != nil {
				t.Fatal(err)
			}
			defer g.Close()
			var release func()
			if tc.firstWriter {
				release, err = f.Lock(tc.firstExclusive, time.Second)
			} else {
				release, err = observeLock(t, f, tc.firstExclusive)
			}
			if err != nil {
				t.Fatal(err)
			}
			defer func() {
				if release != nil {
					release()
				}
			}()
			var second func()
			if tc.secondWriter {
				second, err = g.Lock(tc.secondExclusive, 30*time.Millisecond)
			} else {
				second, err = observeLock(t, g, tc.secondExclusive)
			}
			if tc.allowed {
				if err != nil {
					t.Fatalf("shared readers did not coexist: %v", err)
				}
				second()
			} else if fault.Code(err) != "LOCK_TIMEOUT" || second != nil {
				if second != nil {
					second()
				}
				t.Fatalf("independently opened lock bypassed exclusion: %v", err)
			}
			release()
			release = nil
			writer, err := g.Lock(true, time.Second)
			if err != nil {
				t.Fatalf("writer blocked after release: %v", err)
			}
			defer writer()
			out, err := g.Commit("readonly-release-commit", canonical.BytesHash([]byte("fixture")), []Edit{{Path: "after-release.txt", After: []byte("committed")}})
			if err != nil || out.State != "committed" {
				t.Fatalf("ordinary writer failed after observation release: %v %v", out, err)
			}
		})
	}
	for _, target := range []string{".codearbiter", meta, meta + "/store.lock"} {
		t.Run("observation-pins-"+target, func(t *testing.T) {
			f := initializedLockFixture(t)
			release, err := observeLock(t, f, false)
			if err != nil {
				t.Fatal(err)
			}
			name := filepath.Join(f.Root, filepath.FromSlash(target))
			err = os.Rename(name, name+".moved")
			if err == nil {
				release()
				t.Fatal("acquired observation allowed ancestor or mutex replacement")
			}
			if !errors.Is(err, syscall.Errno(32)) {
				release()
				t.Fatalf("pin refusal has unexpected cause: %v", err)
			}
			release()
			if err := os.Rename(name, name+".released"); err != nil {
				t.Fatalf("released observation leaked a pin: %v", err)
			}
		})
	}
}

func TestObservationLockDetectsPhaseReplacement(t *testing.T) {
	for _, tc := range []struct{ name, step, target string }{
		{"arbiter", "lock-after-directory-open:.codearbiter", ".codearbiter"},
		{"metadata", "lock-after-directory-open:" + meta, meta},
		{"lock", "lock-after-file-open", meta + "/store.lock"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := initializedLockFixture(t)
			called := false
			var injectedTree map[string]string
			name := filepath.Join(f.Root, filepath.FromSlash(tc.target))
			f.Inject = func(step string) error {
				if step != tc.step {
					return nil
				}
				called = true
				if err := os.Rename(name, name+".original"); err != nil {
					t.Fatalf("SETUP: precise replacement failed: %v", err)
				}
				if tc.name != "lock" {
					if err := os.Mkdir(name, 0700); err != nil {
						t.Fatal(err)
					}
					lockDir := name
					if tc.name == "arbiter" {
						lockDir = filepath.Join(name, ".artifacts")
						if err := os.Mkdir(lockDir, 0700); err != nil {
							t.Fatal(err)
						}
					}
					if err := os.WriteFile(filepath.Join(lockDir, "store.lock"), nil, 0600); err != nil {
						t.Fatal(err)
					}
				} else if err := os.WriteFile(name, nil, 0600); err != nil {
					t.Fatal(err)
				}
				injectedTree = testutil.Tree(t, f.Root)
				return nil
			}
			release, err := observeLock(t, f, false)
			if release != nil {
				release()
			}
			if !called || fault.Code(err) != "CONCURRENT_CHANGE" {
				t.Fatalf("phase replacement accepted or unexercised: called=%v err=%v", called, err)
			}
			testutil.AssertTree(t, f.Root, injectedTree)
			// Rename the old object after refusal: every retained partial pin must
			// have closed, including the now-detached directory or lock.
			if err := os.Rename(name+".original", name+".cleanup"); err != nil {
				t.Fatalf("partial-open pin leaked: %v", err)
			}
			f.Inject = nil
			release, err = observeLock(t, f, false)
			if err != nil {
				t.Fatalf("current replacement could not acquire a fresh lock: %v", err)
			}
			release()
		})
	}
}

func TestObservationLockClosesEveryPartialOpen(t *testing.T) {
	for _, step := range []string{"lock-after-root-open", "lock-after-directory-open:.codearbiter", "lock-after-directory-open:" + meta, "lock-after-file-open", "lock-before-acquire"} {
		t.Run(step, func(t *testing.T) {
			f := initializedLockFixture(t)
			before := testutil.Tree(t, f.Root)
			called := false
			interruption := errors.New("fixture-only lock interruption")
			f.Inject = func(actual string) error {
				if actual == step {
					called = true
					return interruption
				}
				return nil
			}
			release, err := observeLock(t, f, false)
			if release != nil {
				release()
			}
			if !called || !errors.Is(err, interruption) {
				t.Fatalf("partial-open phase unexercised: %v %v", called, err)
			}
			testutil.AssertTree(t, f.Root, before)
			for _, target := range []string{meta + "/store.lock", meta, ".codearbiter"} {
				name := filepath.Join(f.Root, filepath.FromSlash(target))
				if err := os.Rename(name, name+".cleanup"); err != nil {
					t.Fatalf("partial pin leaked at %s: %v", target, err)
				}
				if err := os.Rename(name+".cleanup", name); err != nil {
					t.Fatal(err)
				}
			}
			if err := f.Close(); err != nil {
				t.Fatal(err)
			}
			if err := os.Rename(f.Root, f.Root+".cleanup"); err != nil {
				t.Fatalf("partial root pin leaked: %v", err)
			}
			if err := os.Rename(f.Root+".cleanup", f.Root); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestObservationLockRefusesMissingUnsafeAndSwappedState(t *testing.T) {
	// This baseline oracle uses the existing writer API, so the missing new
	// capability cannot manufacture RED. The current writer permits mutex rename.
	t.Run("writer-pins-existing-mutex", func(t *testing.T) {
		f := initializedLockFixture(t)
		lock := filepath.Join(f.Root, filepath.FromSlash(meta), "store.lock")
		before := testutil.Tree(t, f.Root)
		release, err := f.Lock(true, time.Second)
		if err != nil {
			t.Fatal(err)
		}
		err = os.Rename(lock, lock+".moved")
		if err == nil {
			release()
			if restoreErr := os.Rename(lock+".moved", lock); restoreErr != nil {
				t.Fatal(restoreErr)
			}
			t.Fatal("TARGET: a held writer mutex was replaceable; another opener can lock a different object")
		}
		if !errors.Is(err, syscall.Errno(32)) {
			release()
			t.Fatalf("rename refusal has unexpected cause: %v", err)
		}
		release()
		testutil.AssertTree(t, f.Root, before)
		if err := os.Rename(lock, lock+".released"); err != nil {
			t.Fatalf("released lock is still pinned: %v", err)
		}
	})
	for _, tc := range []struct {
		name, want string
		setup      func(*testing.T, *FS)
	}{
		{"missing-metadata", "LOCK_FAILED", func(t *testing.T, f *FS) {}},
		{"missing-lock", "LOCK_FAILED", func(t *testing.T, f *FS) {
			if err := os.MkdirAll(filepath.Join(f.Root, filepath.FromSlash(meta)), 0700); err != nil {
				t.Fatal(err)
			}
		}},
		{"metadata-file", "UNSAFE_PATH", func(t *testing.T, f *FS) {
			if err := os.WriteFile(filepath.Join(f.Root, ".codearbiter"), []byte("file"), 0600); err != nil {
				t.Fatal(err)
			}
		}},
		{"lock-directory", "UNSAFE_PATH", func(t *testing.T, f *FS) {
			if err := os.MkdirAll(filepath.Join(f.Root, filepath.FromSlash(meta), "store.lock"), 0700); err != nil {
				t.Fatal(err)
			}
		}},
		{"metadata-junction", "UNSAFE_PATH", func(t *testing.T, f *FS) {
			inner := filepath.Join(f.Root, "inner")
			if err := os.Mkdir(inner, 0700); err != nil {
				t.Fatal(err)
			}
			output, err := exec.Command("cmd", "/c", "mklink", "/J", filepath.Join(f.Root, ".codearbiter"), inner).CombinedOutput()
			if err != nil {
				t.Fatalf("SETUP: native junction support unavailable: %v %s", err, output)
			}
		}},
		{"lock-symlink", "UNSAFE_PATH", func(t *testing.T, f *FS) {
			if err := os.MkdirAll(filepath.Join(f.Root, filepath.FromSlash(meta)), 0700); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(f.Root, "target"), []byte("target"), 0600); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(filepath.Join(f.Root, "target"), filepath.Join(f.Root, filepath.FromSlash(meta), "store.lock")); err != nil {
				t.Fatalf("SETUP: native symlink support unavailable: %v", err)
			}
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := fs(t)
			tc.setup(t, f)
			before := testutil.Tree(t, f.Root)
			release, err := observeLock(t, f, false)
			if release != nil {
				release()
			}
			if fault.Code(err) != tc.want {
				t.Fatalf("unsafe observation want %s got %v", tc.want, err)
			}
			testutil.AssertTree(t, f.Root, before)
		})
	}
}
