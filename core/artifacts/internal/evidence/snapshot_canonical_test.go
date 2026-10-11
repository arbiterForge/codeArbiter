package evidence

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// hostResolves reports whether this host resolves rel under root to a real path.
// A non-canonical spelling that the host resolves is exactly the case a root
// canonicalization must refuse; one it does not resolve is simply missing.
func hostResolves(root, rel string) bool {
	_, err := os.Lstat(filepath.Join(root, filepath.FromSlash(rel)))
	return err == nil
}

// wantNonCanonical requires a fail-closed refusal. When the host resolves the
// spelling the refusal must be the membership error; when it does not, the root
// is genuinely missing and MISSING_INPUT_ROOT is the correct refusal.
func wantNonCanonical(t *testing.T, repo, spelling string, err error, what string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: root %q was accepted", what, spelling)
	}
	if hostResolves(repo, spelling) {
		if fault.Code(err) != "INPUT_MEMBERSHIP_UNAVAILABLE" {
			t.Fatalf("%s: host resolves %q, so it must be refused as a non-canonical spelling: %v", what, spelling, err)
		}
		return
	}
	if fault.Code(err) != "MISSING_INPUT_ROOT" && fault.Code(err) != "INPUT_MEMBERSHIP_UNAVAILABLE" {
		t.Fatalf("%s: unexpected refusal %v", what, err)
	}
}

func TestSnapshotNonCanonicalRootFailsClosed(t *testing.T) {
	// Case variant inside a gitlink: "SUB/lib.txt" for submodule "sub".
	root, _ := snapshotSubmoduleFixture(t)
	for _, spelling := range []string{"SUB/lib.txt", "SUB", "Sub/lib.txt"} {
		_, _, err := snapshotTry(t, root, snapshotPolicy(t, []string{spelling}, nil))
		wantNonCanonical(t, root, spelling, err, "gitlink case variant")
	}
	// Case-variant ancestor of an ordinary tracked file.
	repo := snapshotGitFixture(t)
	completionWrite(t, repo, "Dir/inner/a.txt", []byte("a\n"))
	completionWrite(t, repo, "other.txt", []byte("o\n"))
	completionGit(t, repo, "add", ".")
	snapshotCommit(t, repo, "fixture")
	for _, spelling := range []string{"dir/inner/a.txt", "Dir/INNER/a.txt", "dir", "Dir/Inner"} {
		_, _, err := snapshotTry(t, repo, snapshotPolicy(t, []string{spelling, "other.txt"}, nil))
		wantNonCanonical(t, repo, spelling, err, "ancestor case variant")
	}
	// The exact spellings still work (non-vacuous).
	for _, exact := range []string{"Dir/inner/a.txt", "Dir", "Dir/inner"} {
		if _, entries, err := snapshotTry(t, repo, snapshotPolicy(t, []string{exact}, nil)); err != nil || len(entries) == 0 {
			t.Fatalf("exact root %q rejected: %v", exact, err)
		}
	}
	// A genuinely missing root keeps its own diagnostic.
	_, _, err := snapshotTry(t, repo, snapshotPolicy(t, []string{"nothing/here.txt"}, nil))
	if fault.Code(err) != "MISSING_INPUT_ROOT" {
		t.Fatalf("missing root: %v", err)
	}

	// Unicode normalization: tracked NFC name, root spelled NFD.
	const nfc, nfd = "caf\u00e9.txt", "cafe\u0301.txt"
	uni := snapshotGitFixture(t)
	completionWrite(t, uni, nfc, []byte("u\n"))
	completionWrite(t, uni, "other.txt", []byte("o\n"))
	completionGit(t, uni, "add", ".")
	snapshotCommit(t, uni, "fixture")
	_, _, err = snapshotTry(t, uni, snapshotPolicy(t, []string{nfd, "other.txt"}, nil))
	wantNonCanonical(t, uni, nfd, err, "NFD file root")

	// ... and a directory root spelled NFD for a tracked NFC directory.
	const nfcDir, nfdDir = "caf\u00e9dir", "cafe\u0301dir"
	completionWrite(t, uni, nfcDir+"/inner.txt", []byte("i\n"))
	completionGit(t, uni, "add", ".")
	snapshotCommit(t, uni, "dir fixture")
	_, _, err = snapshotTry(t, uni, snapshotPolicy(t, []string{nfdDir, "other.txt"}, nil))
	wantNonCanonical(t, uni, nfdDir, err, "NFD directory root")
	if _, _, err = snapshotTry(t, uni, snapshotPolicy(t, []string{nfcDir, nfc}, nil)); err != nil {
		t.Fatalf("exact NFC roots rejected: %v", err)
	}

	// Windows 8.3 short names (only where the volume generates them).
	short := snapshotGitFixture(t)
	completionWrite(t, short, "longdirectoryname/inner.txt", []byte("i\n"))
	completionWrite(t, short, "longfilename.txt", []byte("f\n"))
	completionGit(t, short, "add", ".")
	snapshotCommit(t, short, "fixture")
	tried := 0
	for _, long := range []string{"longdirectoryname", "longfilename.txt"} {
		sn := shortNameOf(t, filepath.Join(short, long))
		if sn == "" || strings.EqualFold(sn, long) {
			t.Logf("no distinct 8.3 short name for %q on this host; subcase has nothing to refuse", long)
			continue
		}
		tried++
		_, _, err := snapshotTry(t, short, snapshotPolicy(t, []string{sn}, nil))
		if fault.Code(err) != "INPUT_MEMBERSHIP_UNAVAILABLE" {
			t.Fatalf("8.3 name %q resolves on this host and must be INPUT_MEMBERSHIP_UNAVAILABLE: %v", sn, err)
		}
	}
	t.Logf("8.3 subcases exercised: %d", tried)
}

func TestSnapshotUnreadableDotGitFailsClosed(t *testing.T) {
	repo := snapshotGitFixture(t)
	completionWrite(t, repo, "a.txt", []byte("a\n"))
	completionGit(t, repo, "add", ".")
	snapshotCommit(t, repo, "fixture")
	if _, _, err := snapshotTry(t, repo, nil); err != nil {
		t.Fatalf("baseline: %v", err)
	}
	// A plain directory (no .git at all) is still the filesystem walk.
	plain := t.TempDir()
	completionWrite(t, plain, "a.txt", []byte("a\n"))
	if _, _, err := snapshotTry(t, plain, nil); err != nil {
		t.Fatalf("non-git root: %v", err)
	}
	real := lstatDotGit
	t.Cleanup(func() { lstatDotGit = real })
	for name, boom := range map[string]error{"permission": os.ErrPermission, "io": errors.New("device not ready")} {
		lstatDotGit = func(p string) (os.FileInfo, error) {
			if filepath.Base(p) == ".git" {
				return nil, boom
			}
			return real(p)
		}
		_, _, err := snapshotTry(t, repo, nil)
		snapshotWantUnavailable(t, err, "unreadable .git ("+name+")")
		// The same error on a root that has no repository must not hide behind it.
		_, _, err = snapshotTry(t, plain, nil)
		snapshotWantUnavailable(t, err, "unreadable .git on a plain root ("+name+")")
	}
}

func TestSnapshotGitlinkSharingParentGitDirFailsClosed(t *testing.T) {
	repo := snapshotGitFixture(t)
	completionWrite(t, repo, "top.txt", []byte("top\n"))
	completionGit(t, repo, "add", ".")
	snapshotCommit(t, repo, "fixture")
	head := completionGit(t, repo, "rev-parse", "HEAD")
	completionGit(t, repo, "update-index", "--add", "--cacheinfo", "160000,"+head+",sub")
	// sub/.git is a gitfile pointing at the PARENT's own git directory, so git
	// answers for the parent and the parent's HEAD would pose as sub's identity.
	completionWrite(t, repo, "sub/.git", []byte("gitdir: "+filepath.ToSlash(filepath.Join(repo, ".git"))+"\n"))
	_, _, err := snapshotTry(t, repo, nil)
	snapshotWantUnavailable(t, err, "gitlink sharing the parent git dir")
	if !strings.Contains(err.Error(), "shares the root repository's git directory") {
		t.Fatalf("refused for the wrong reason: %v", err)
	}
	// A real checked-out submodule keeps working (its git dir is its own).
	good, _ := snapshotSubmoduleFixture(t)
	if _, entries, err := snapshotTry(t, good, nil); err != nil || entries["sub"] == nil {
		t.Fatalf("genuine submodule rejected: %v", err)
	}
}
