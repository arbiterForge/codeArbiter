//go:build linux || darwin || windows

package store

import (
	"errors"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
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

func TestJournalPublicationCrash(t *testing.T) {
	if root := os.Getenv("CA_ARTIFACT_JOURNAL_CRASH_FIXTURE"); root != "" {
		f, e := Open(root)
		if e != nil {
			os.Exit(90)
		}
		defer f.Close()
		f.Inject = func(point string) error {
			if point == os.Getenv("CA_ARTIFACT_JOURNAL_CRASH_AT") {
				os.Exit(99)
			}
			return nil
		}
		_, e = f.Commit("journal-crash-001", canonical.BytesHash([]byte("fixture")),
			[]Edit{{Path: "a.txt", Before: []byte("old"), After: []byte("new")}})
		if e != nil {
			os.Exit(92)
		}
		os.Exit(0)
	}
	for _, point := range []string{"before-journal-publish", "during-journal-publish", "after-journal-publish"} {
		t.Run(point, func(t *testing.T) {
			root := testutil.Root(t)
			if e := os.WriteFile(filepath.Join(root, "a.txt"), []byte("old"), 0644); e != nil {
				t.Fatal(e)
			}
			command := exec.Command(os.Args[0], "-test.run=^TestJournalPublicationCrash$")
			command.Env = append(os.Environ(), "CA_ARTIFACT_JOURNAL_CRASH_FIXTURE="+root,
				"CA_ARTIFACT_JOURNAL_CRASH_AT="+point)
			if e := command.Run(); e == nil || command.ProcessState.ExitCode() != 99 {
				t.Fatalf("expected publication crash at %s: %v", point, e)
			}
			final := filepath.Join(root, ".codearbiter", ".artifacts", "transactions", "journal-crash-001.json")
			_, e := os.Stat(final)
			if point == "before-journal-publish" && !os.IsNotExist(e) {
				t.Fatalf("final journal published too early: %v", e)
			}
			if point != "before-journal-publish" && e != nil {
				t.Fatal(e)
			}
			f, e := Open(root)
			if e != nil {
				t.Fatal(e)
			}
			defer f.Close()
			if point == "before-journal-publish" {
				stage := final + ".next"
				witness := filepath.Join(root, "journal-stage-witness")
				if e := os.Link(stage, witness); e != nil {
					t.Fatal(e)
				}
				f.Inject = func(step string) error {
					if step == "after-journal-publish" {
						return errors.New("pause retry after publication")
					}
					return nil
				}
				_, e = f.Commit("journal-crash-001", canonical.BytesHash([]byte("fixture")),
					[]Edit{{Path: "a.txt", Before: []byte("old"), After: []byte("new")}})
				if fault.Code(e) != "COMMIT_OUTCOME_UNKNOWN" {
					t.Fatalf("expected paused retry, got %v", e)
				}
				f.Inject = nil
				oldInfo, e := os.Stat(witness)
				if e != nil {
					t.Fatal(e)
				}
				newInfo, e := os.Stat(final)
				if e != nil {
					t.Fatal(e)
				}
				if os.SameFile(oldInfo, newInfo) {
					t.Fatal("retry published the pre-crash journal inode without a fresh sync")
				}
				if _, e := f.Recover("journal-crash-001", "complete"); e != nil {
					t.Fatal(e)
				}
			} else if _, e := f.Recover("journal-crash-001", "complete"); e != nil {
				t.Fatal(e)
			}
			b, e := os.ReadFile(filepath.Join(root, "a.txt"))
			if e != nil || string(b) != "new" {
				t.Fatalf("retry/recovery failed: %q %v", b, e)
			}
		})
	}
}
