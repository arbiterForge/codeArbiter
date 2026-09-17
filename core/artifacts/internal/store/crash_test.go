//go:build linux || darwin || windows

package store

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestProcessDeathRecovery(t *testing.T) {
	if root := os.Getenv("CA_ARTIFACT_CRASH_FIXTURE"); root != "" {
		f, e := Open(root)
		if e != nil {
			os.Exit(90)
		}
		unlock, e := f.Lock(true, time.Second)
		if e != nil {
			os.Exit(91)
		}
		defer unlock()
		f.Inject = func(point string) error {
			if point == os.Getenv("CA_ARTIFACT_CRASH_AT") {
				os.Exit(99)
			}
			return nil
		}
		_, e = f.Commit("process-crash-001", canonical.BytesHash([]byte("fixture")), []Edit{{Path: "a.txt", Before: []byte("old-a"), After: []byte("new-a")}, {Path: "b.txt", Before: []byte("old-b"), After: []byte("new-b")}})
		if e != nil {
			os.Exit(92)
		}
		os.Exit(0)
	}
	for _, point := range []string{"after-stage-1", "after-journal", "after-replace-0", "after-replace-1"} {
		for _, mode := range []string{"complete", "rollback"} {
			t.Run(point+"/"+mode, func(t *testing.T) {
				root := testutil.Root(t)
				os.WriteFile(filepath.Join(root, "a.txt"), []byte("old-a"), 0644)
				os.WriteFile(filepath.Join(root, "b.txt"), []byte("old-b"), 0644)
				command := exec.Command(os.Args[0], "-test.run=^TestProcessDeathRecovery$")
				command.Env = append(os.Environ(), "CA_ARTIFACT_CRASH_FIXTURE="+root, "CA_ARTIFACT_CRASH_AT="+point)
				err := command.Run()
				if err == nil {
					t.Fatal("child did not crash")
				}
				if code := command.ProcessState.ExitCode(); code != 99 {
					t.Fatalf("unexpected child exit %d", code)
				}
				f, e := Open(root)
				if e != nil {
					t.Fatal(e)
				}
				defer f.Close()
				unlock, e := f.Lock(true, time.Second)
				if e != nil {
					t.Fatal("process lock was not released", e)
				}
				defer unlock()
				if point == "after-stage-1" {
					for _, p := range []string{"a", "b"} {
						b, _ := os.ReadFile(filepath.Join(root, p+".txt"))
						if string(b) != "old-"+p {
							t.Fatal("pre-journal target changed")
						}
					}
					_, e = f.Commit("process-crash-001", canonical.BytesHash([]byte("fixture")), []Edit{{Path: "a.txt", Before: []byte("old-a"), After: []byte("new-a")}, {Path: "b.txt", Before: []byte("old-b"), After: []byte("new-b")}})
					if e != nil {
						t.Fatal(e)
					}
					return
				}
				_, e = f.Recover("process-crash-001", mode)
				if e != nil {
					t.Fatal(e)
				}
				prefix := "new-"
				if mode == "rollback" {
					prefix = "old-"
				}
				for _, p := range []string{"a", "b"} {
					b, e := f.Read(p+".txt", 10)
					if e != nil || string(b) != prefix+p {
						t.Fatal("mixed recovery", p, string(b), e)
					}
				}
				if _, e = f.Infrastructure(); e != nil {
					t.Fatal(e)
				}
			})
		}
	}
}
