package evidence

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestSnapshotShipSetMembership(t *testing.T) {
	git, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	if git, err = filepath.Abs(git); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CODEARBITER_GIT_EXECUTABLE", git)
	root := testutil.Root(t)
	completionGit(t, root, "init", "-q")
	completionWrite(t, root, "tracked.txt", []byte("one\n"))
	completionWrite(t, root, ".gitignore", []byte("ignored.txt\nbuild/\n"))
	completionGit(t, root, "add", ".")
	completionGit(t, root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
	completionWrite(t, root, "untracked.txt", []byte("u1\n"))
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { f.Close() })
	id := func() string {
		t.Helper()
		s, err := Snapshot(f, nil)
		if err != nil {
			t.Fatal(err)
		}
		return s["sha256"].(string)
	}
	base := id()
	if id() != base {
		t.Fatal("snapshot is not stable")
	}
	steps := []struct {
		name, rel, body string
		changes         bool
	}{
		{"tracked edit", "tracked.txt", "two\n", true},
		{"untracked edit", "untracked.txt", "u2\n", true},
		{"ignored file create", "ignored.txt", "x\n", false},
		{"ignored file edit", "ignored.txt", "y\n", false},
		{"ignored dir create", "build/out.bin", "z\n", false},
	}
	prev := base
	for _, st := range steps {
		completionWrite(t, root, st.rel, []byte(st.body))
		cur := id()
		if (cur != prev) != st.changes {
			t.Fatalf("%s: identity changed=%v, want %v", st.name, cur != prev, st.changes)
		}
		prev = cur
	}
	if _, err := os.Stat(filepath.Join(root, "build", "out.bin")); err != nil {
		t.Fatal(err)
	}
}

func snapshotGitFixture(t *testing.T) string {
	t.Helper()
	git, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	if git, err = filepath.Abs(git); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CODEARBITER_GIT_EXECUTABLE", git)
	root := testutil.Root(t)
	completionGit(t, root, "init", "-q")
	return root
}

func snapshotCommit(t *testing.T, root, msg string) {
	t.Helper()
	completionGit(t, root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", msg)
}

func snapshotID(t *testing.T, root string) (string, map[string]any) {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	s, err := Snapshot(f, nil)
	if err != nil {
		t.Fatal(err)
	}
	return s["sha256"].(string), s["manifest"].(map[string]any)["entries"].(map[string]any)
}

func TestSnapshotDeletedIndexEntryAbsent(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "keep.txt", []byte("keep\n"))
	completionWrite(t, root, "gone.txt", []byte("gone\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	_, before := snapshotID(t, root)
	if _, ok := before["gone.txt"]; !ok {
		t.Fatal("tracked file missing from manifest")
	}
	if err := os.Remove(filepath.Join(root, "gone.txt")); err != nil {
		t.Fatal(err)
	}
	_, after := snapshotID(t, root)
	if _, ok := after["gone.txt"]; ok {
		t.Fatal("index entry deleted on disk is still in the manifest")
	}
	if _, ok := after["keep.txt"]; !ok {
		t.Fatal("surviving file missing from manifest")
	}
	for _, m := range after["./"].(map[string]any)["members"].([]any) {
		if m == "gone.txt" {
			t.Fatal("deleted file listed as a directory member")
		}
	}
}

func TestSnapshotGitlinkPointerOnly(t *testing.T) {
	root := snapshotGitFixture(t)
	upstream := testutil.Root(t)
	completionGit(t, upstream, "init", "-q")
	completionWrite(t, upstream, "lib.txt", []byte("lib\n"))
	completionGit(t, upstream, "add", ".")
	snapshotCommit(t, upstream, "lib one")
	completionWrite(t, root, "top.txt", []byte("top\n"))
	completionGit(t, root, "add", ".")
	completionGit(t, root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", upstream, "sub")
	snapshotCommit(t, root, "fixture")
	sub := filepath.Join(root, "sub")
	base, entries := snapshotID(t, root)
	if _, ok := entries["sub/lib.txt"]; ok {
		t.Fatal("submodule contents were descended into")
	}
	assertGitlink(t, entries, "sub", completionGit(t, sub, "rev-parse", "HEAD"))
	// Edits inside the submodule worktree must not change identity.
	completionWrite(t, sub, "lib.txt", []byte("edited\n"))
	completionWrite(t, sub, "extra.txt", []byte("extra\n"))
	if got, _ := snapshotID(t, root); got != base {
		t.Fatal("edit inside the submodule changed identity")
	}
	// Moving the submodule HEAD must change identity.
	completionGit(t, sub, "checkout", "-q", "--", "lib.txt")
	completionWrite(t, sub, "lib.txt", []byte("lib two\n"))
	completionGit(t, sub, "add", "lib.txt")
	snapshotCommit(t, sub, "lib two")
	if got, _ := snapshotID(t, root); got == base {
		t.Fatal("moving the submodule HEAD did not change identity")
	}
}

// A tracked submodule that is not checked out has no .git of its own, so its
// identity is the index pointer.
func TestSnapshotGitlinkNotCheckedOutUsesIndexPointer(t *testing.T) {
	root := snapshotGitFixture(t)
	upstream := testutil.Root(t)
	completionGit(t, upstream, "init", "-q")
	completionWrite(t, upstream, "lib.txt", []byte("lib\n"))
	completionGit(t, upstream, "add", ".")
	snapshotCommit(t, upstream, "lib one")
	completionGit(t, root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", upstream, "sub")
	snapshotCommit(t, root, "fixture")
	pointer := strings.Fields(completionGit(t, root, "ls-files", "-s", "--", "sub"))[1]
	completionGit(t, root, "submodule", "deinit", "-q", "-f", "--", "sub")
	if _, err := os.Lstat(filepath.Join(root, "sub", ".git")); !os.IsNotExist(err) {
		t.Fatalf("fixture: deinit left sub/.git (%v)", err)
	}
	_, entries := snapshotID(t, root)
	assertGitlink(t, entries, "sub", pointer)
}

func assertGitlink(t *testing.T, entries map[string]any, path, commit string) {
	t.Helper()
	entry, ok := entries[path].(map[string]any)
	if !ok {
		t.Fatalf("%s: gitlink entry missing from manifest: %#v", path, entries[path])
	}
	if entry["kind"] != "gitlink" || entry["commit"] != commit || len(entry) != 2 {
		t.Fatalf("%s: entry %#v, want kind gitlink and commit %s", path, entry, commit)
	}
}

func TestSnapshotExecutableFromIndexMode(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "tool.sh", []byte("#!/bin/sh\n"))
	completionWrite(t, root, "plain.txt", []byte("plain\n"))
	completionGit(t, root, "add", ".")
	completionGit(t, root, "update-index", "--chmod=+x", "tool.sh")
	snapshotCommit(t, root, "fixture")
	// Diverge the on-disk mode from the index where the filesystem has modes.
	if err := os.Chmod(filepath.Join(root, "plain.txt"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(filepath.Join(root, "tool.sh"), 0644); err != nil {
		t.Fatal(err)
	}
	_, entries := snapshotID(t, root)
	if entries["tool.sh"].(map[string]any)["executable"] != true {
		t.Fatal("index mode 100755 must be executable")
	}
	if entries["plain.txt"].(map[string]any)["executable"] != false {
		t.Fatal("index mode 100644 must not be executable")
	}
}

func snapshotAppend(t *testing.T, root, rel, line string) {
	t.Helper()
	fh, err := os.OpenFile(filepath.Join(root, filepath.FromSlash(rel)), os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = fh.WriteString(line); err != nil {
		t.Fatal(err)
	}
	if err = fh.Close(); err != nil {
		t.Fatal(err)
	}
}

func snapshotLogFixture(t *testing.T, git bool, rels ...string) string {
	t.Helper()
	root := snapshotGitFixture(t)
	if !git {
		root = testutil.Root(t)
	}
	completionWrite(t, root, "tracked.txt", []byte("one\n"))
	for _, rel := range rels {
		completionWrite(t, root, rel, []byte("first\n"))
	}
	if git {
		completionGit(t, root, "add", ".")
		snapshotCommit(t, root, "fixture")
	}
	return root
}

func TestSnapshotGateEventsAppendExempt(t *testing.T) {
	root := snapshotLogFixture(t, true, ".codearbiter/gate-events.log")
	before, entries := snapshotID(t, root)
	if _, ok := entries[".codearbiter/gate-events.log"]; ok {
		t.Fatal("gate-events.log must not be an identity entry")
	}
	snapshotAppend(t, root, ".codearbiter/gate-events.log", "second\n")
	if after, _ := snapshotID(t, root); after != before {
		t.Fatal("appending to gate-events.log changed the input identity")
	}
	out, err := exec.Command("git", "-C", root, "ls-files", ".codearbiter/gate-events.log").Output()
	if err != nil || !strings.Contains(string(out), "gate-events.log") {
		t.Fatalf("gate-events.log must stay git-tracked: %v", err)
	}
}

func TestSnapshotOverridesAppendCounts(t *testing.T) {
	root := snapshotLogFixture(t, true, ".codearbiter/overrides.log", ".codearbiter/gate-events.log.bak", "x/.codearbiter/gate-events.log")
	for _, rel := range []string{".codearbiter/overrides.log", ".codearbiter/gate-events.log.bak", "x/.codearbiter/gate-events.log"} {
		before, _ := snapshotID(t, root)
		snapshotAppend(t, root, rel, "second\n")
		if after, _ := snapshotID(t, root); after == before {
			t.Fatalf("appending to %s must change the input identity", rel)
		}
	}
}

func TestSnapshotPlanCannotExcludeCodearbiter(t *testing.T) {
	for _, ex := range []string{".codearbiter", ".codearbiter/overrides.log", ".codearbiter/x"} {
		// Sealing a plan that names governance in exclude_directories is refused.
		sealed := testutil.Plan(testutil.Seal(t, testutil.Spec()))
		model.M(sealed["normative"])["verification_inputs"] = map[string]any{"roots": model.List("."), "exclude_directories": model.List(ex)}
		if _, err := render.Prepare(sealed); err == nil || !strings.Contains(err.Error(), "governance cannot be excluded") {
			t.Fatalf("seal accepted exclude %q or wrong error: %v", ex, err)
		}
		// A document that bypasses sealing is still refused by the engine itself.
		f, p := snapshotFixture(t, []string{"."}, nil)
		model.M(p.Norm()["verification_inputs"])["exclude_directories"] = model.List(ex)
		if _, err := Snapshot(f, p); err == nil || !strings.Contains(err.Error(), "INVALID_INPUT_POLICY") {
			t.Fatalf("Snapshot accepted exclude %q or wrong error: %v", ex, err)
		}
	}
}

func snapshotMembership(t *testing.T, root string) string {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	s, err := Snapshot(f, nil)
	if err != nil {
		t.Fatal(err)
	}
	m, _ := s["manifest"].(map[string]any)["membership"].(string)
	return m
}

func TestSnapshotNonGitRootFilesystemMembership(t *testing.T) {
	plain := snapshotLogFixture(t, false)
	if _, err := os.Lstat(filepath.Join(plain, ".git")); err == nil {
		t.Fatal("fixture must not be a git work tree")
	}
	if got := snapshotMembership(t, plain); got != "filesystem" {
		t.Fatalf("non-git membership = %q, want filesystem", got)
	}
	gitRoot := snapshotLogFixture(t, true)
	if got := snapshotMembership(t, gitRoot); got != "git_ship_set" {
		t.Fatalf("git membership = %q, want git_ship_set", got)
	}
	// The label is part of the hashed manifest: identical bytes never share an
	// identity across the two modes.
	a, _ := snapshotID(t, plain)
	b, _ := snapshotID(t, gitRoot)
	if a == b {
		t.Fatal("filesystem and git_ship_set modes share an identity")
	}
}

func TestSnapshotGitProbeFailureFailsClosed(t *testing.T) {
	for _, env := range []string{"", filepath.Join(os.TempDir(), "codearbiter-no-such-git-executable")} {
		root := snapshotLogFixture(t, true)
		t.Setenv("CODEARBITER_GIT_EXECUTABLE", env)
		f, err := store.Open(root)
		if err != nil {
			t.Fatal(err)
		}
		s, err := Snapshot(f, nil)
		f.Close()
		if err == nil || s != nil {
			t.Fatalf("git root with failing probe (%q) returned a manifest instead of an error", env)
		}
		if !strings.Contains(err.Error(), "INPUT_MEMBERSHIP_UNAVAILABLE") {
			t.Fatalf("wrong error: %v", err)
		}
	}
}

func TestSnapshotGateEventsExemptWithoutGit(t *testing.T) {
	root := snapshotLogFixture(t, false, ".codearbiter/gate-events.log", ".codearbiter/overrides.log")
	if _, err := os.Lstat(filepath.Join(root, ".git")); err == nil {
		t.Fatal("fixture must not be a git work tree")
	}
	before, _ := snapshotID(t, root)
	snapshotAppend(t, root, ".codearbiter/gate-events.log", "second\n")
	if after, _ := snapshotID(t, root); after != before {
		t.Fatal("non-git walk: gate-events.log append changed identity")
	}
	snapshotAppend(t, root, ".codearbiter/overrides.log", "second\n")
	if after, _ := snapshotID(t, root); after == before {
		t.Fatal("non-git walk: overrides.log append must change identity")
	}
}

func snapshotPolicy(t *testing.T, roots, excludes []string) *model.Document {
	t.Helper()
	p := testutil.Plan(testutil.Seal(t, testutil.Spec()))
	model.M(p["normative"])["verification_inputs"] = map[string]any{"roots": model.List(roots...), "exclude_directories": model.List(excludes...)}
	return testutil.Seal(t, p)
}

func snapshotPolicyID(t *testing.T, root string, plan *model.Document) string {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	s, err := Snapshot(f, plan)
	if err != nil {
		t.Fatalf("snapshot with policy: %v", err)
	}
	return s["sha256"].(string)
}

func TestSnapshotGateEventsExplicitRootExempt(t *testing.T) {
	for _, git := range []bool{true, false} {
		root := snapshotLogFixture(t, git, "src/a.txt", ".codearbiter/gate-events.log")
		plan := snapshotPolicy(t, []string{"src", ".codearbiter/gate-events.log"}, nil)
		base := snapshotPolicyID(t, root, plan)
		snapshotAppend(t, root, ".codearbiter/gate-events.log", "second\n")
		if got := snapshotPolicyID(t, root, plan); got != base {
			t.Fatalf("git=%v: explicit gate-events root: append changed identity", git)
		}
		f, err := store.Open(root)
		if err != nil {
			t.Fatal(err)
		}
		s, err := Snapshot(f, plan)
		f.Close()
		if err != nil {
			t.Fatal(err)
		}
		items, _ := s["manifest"].(map[string]any)["entries"].(map[string]any)
		if _, ok := items[".codearbiter/gate-events.log"]; ok {
			t.Fatalf("git=%v: gate-events log must not be a manifest entry", git)
		}
		// Non-vacuous: the other explicit root still contributes.
		completionWrite(t, root, "src/a.txt", []byte("changed\n"))
		if snapshotPolicyID(t, root, plan) == base {
			t.Fatalf("git=%v: normal root must still contribute", git)
		}
	}
}

func TestSnapshotRedundantIgnoredExcludeAccepted(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "a.txt", []byte("a\n"))
	completionWrite(t, root, ".gitignore", []byte("deps/\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	completionWrite(t, root, "deps/d.txt", []byte("d1\n"))    // ignored by git
	completionWrite(t, root, "scratch/s.txt", []byte("s1\n")) // not ignored
	plan := snapshotPolicy(t, []string{"."}, []string{"deps", "scratch"})
	base := snapshotPolicyID(t, root, plan)
	completionWrite(t, root, "deps/d.txt", []byte("d2\n"))
	completionWrite(t, root, "deps/new.txt", []byte("n\n"))
	completionWrite(t, root, "scratch/s.txt", []byte("s2\n"))
	completionWrite(t, root, "scratch/new.txt", []byte("n\n"))
	if got := snapshotPolicyID(t, root, plan); got != base {
		t.Fatal("files under excluded directories changed identity")
	}
	// Non-vacuous: without the scratch exclude the same edit is an input.
	only := snapshotPolicy(t, []string{"."}, []string{"deps"})
	before := snapshotPolicyID(t, root, only)
	completionWrite(t, root, "scratch/s.txt", []byte("s3\n"))
	if snapshotPolicyID(t, root, only) == before {
		t.Fatal("a non-excluded, non-ignored directory must contribute")
	}
}

func TestSnapshotExcludesNarrowShipSet(t *testing.T) {
	root := snapshotGitFixture(t)
	for _, rel := range []string{"src/a.go", "src/vendor/v.go", "out/o.txt"} {
		completionWrite(t, root, rel, []byte("one\n"))
	}
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	plan := snapshotPolicy(t, []string{"src"}, []string{"src/vendor"})
	base := snapshotPolicyID(t, root, plan)
	completionWrite(t, root, "src/vendor/v.go", []byte("two\n"))
	if snapshotPolicyID(t, root, plan) != base {
		t.Fatal("tracked file under an excluded directory changed identity")
	}
	completionWrite(t, root, "out/o.txt", []byte("two\n"))
	if snapshotPolicyID(t, root, plan) != base {
		t.Fatal("tracked file outside the roots changed identity")
	}
	completionWrite(t, root, "src/a.go", []byte("two\n"))
	if snapshotPolicyID(t, root, plan) == base {
		t.Fatal("tracked file inside the roots and outside excludes must change identity")
	}
	// Exclude under a "." root, tracked file outside it still counts.
	dot := snapshotPolicy(t, []string{"."}, []string{"out"})
	before := snapshotPolicyID(t, root, dot)
	completionWrite(t, root, "out/o.txt", []byte("three\n"))
	if snapshotPolicyID(t, root, dot) != before {
		t.Fatal("tracked file under excluded out/ changed identity")
	}
	completionWrite(t, root, "src/vendor/v.go", []byte("three\n"))
	if snapshotPolicyID(t, root, dot) == before {
		t.Fatal("tracked file outside the exclude must change identity")
	}
}

func TestSnapshotProgressOnlyUpdateKeepsIdentity(t *testing.T) {
	root := snapshotGitFixture(t)
	plan := testutil.Seal(t, testutil.Plan(testutil.Seal(t, testutil.Spec())))
	write := func(d *model.Document) {
		t.Helper()
		b, err := render.Render(d)
		if err != nil {
			t.Fatal(err)
		}
		completionWrite(t, root, ".codearbiter/plans/example.plan.html", b)
	}
	write(plan)
	completionWrite(t, root, "a.txt", []byte("a\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	base, _ := snapshotID(t, root)
	reseal := func(edit func(v map[string]any)) *model.Document {
		t.Helper()
		v, err := canonical.Clone(plan.Data)
		if err != nil {
			t.Fatal(err)
		}
		edit(v)
		d, err := render.Prepare(v)
		if err != nil {
			t.Fatal(err)
		}
		return d
	}
	progress := reseal(func(v map[string]any) {
		model.M(model.M(model.M(v["execution"])["tasks"])["T-001"])["state"] = "IN_PROGRESS"
	})
	if progress.NormHash() != plan.NormHash() {
		t.Fatal("fixture: progress edit must not be normative")
	}
	// Self-proving negative control: the progress-only reseal really changes the
	// rendered HTML bytes, so an unchanged identity is the normative hash at work
	// and not an unchanged file.
	sealedBytes, err := render.Render(plan)
	if err != nil {
		t.Fatal(err)
	}
	progressBytes, err := render.Render(progress)
	if err != nil {
		t.Fatal(err)
	}
	if string(sealedBytes) == string(progressBytes) {
		t.Fatal("fixture: the progress-only reseal left the rendered plan HTML bytes unchanged")
	}
	write(progress)
	if got, _ := snapshotID(t, root); got != base {
		t.Fatal("progress-only update of a tracked plan changed identity")
	}
	_, entries := snapshotID(t, root)
	if e := entries[".codearbiter/plans/example.plan.html"].(map[string]any); e["kind"] != "artifact_normative" || e["sha256"] != plan.NormHash() {
		t.Fatalf("plan must contribute its normative hash: %v", e)
	}
	edited := reseal(func(v map[string]any) {
		model.M(v["normative"])["title"] = "A different normative title"
	})
	if edited.NormHash() == plan.NormHash() {
		t.Fatal("fixture: title edit must be normative")
	}
	write(edited)
	if got, _ := snapshotID(t, root); got == base {
		t.Fatal("normative edit of a tracked plan did not change identity")
	}
}

func snapshotTry(t *testing.T, root string, plan *model.Document) (string, map[string]any, error) {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	s, err := Snapshot(f, plan)
	if err != nil {
		return "", nil, err
	}
	return s["sha256"].(string), s["manifest"].(map[string]any)["entries"].(map[string]any), nil
}

func snapshotWantUnavailable(t *testing.T, err error, what string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: snapshot succeeded instead of failing closed", what)
	}
	if !strings.Contains(err.Error(), "INPUT_MEMBERSHIP_UNAVAILABLE") {
		t.Fatalf("%s: wrong error: %v", what, err)
	}
}

// snapshotSubmoduleFixture returns a repo with a checked-out submodule "sub".
func snapshotSubmoduleFixture(t *testing.T) (root, sub string) {
	t.Helper()
	root = snapshotGitFixture(t)
	upstream := testutil.Root(t)
	completionGit(t, upstream, "init", "-q")
	completionWrite(t, upstream, "lib.txt", []byte("lib\n"))
	completionGit(t, upstream, "add", ".")
	snapshotCommit(t, upstream, "lib one")
	completionWrite(t, root, "top.txt", []byte("top\n"))
	completionGit(t, root, "add", ".")
	completionGit(t, root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", upstream, "sub")
	snapshotCommit(t, root, "fixture")
	return root, filepath.Join(root, "sub")
}

func snapshotMoveHead(t *testing.T, dir string) {
	t.Helper()
	completionWrite(t, dir, "lib.txt", []byte("lib two\n"))
	completionGit(t, dir, "add", "lib.txt")
	snapshotCommit(t, dir, "lib two")
}

func TestSnapshotCaseRenamedTrackedFileFailsClosed(t *testing.T) {
	for _, tc := range []struct{ name, tracked, onDisk string }{
		{"file", "Foo.txt", "foo.txt"},
		{"directory", "Dir/a.txt", "dir/a.txt"},
	} {
		root := snapshotGitFixture(t)
		completionWrite(t, root, tc.tracked, []byte("one\n"))
		completionWrite(t, root, "other.txt", []byte("other\n"))
		completionGit(t, root, "add", ".")
		snapshotCommit(t, root, "fixture")
		if _, _, err := snapshotTry(t, root, nil); err != nil {
			t.Fatalf("%s: baseline snapshot: %v", tc.name, err)
		}
		// Two-step rename so it also works on case-insensitive filesystems.
		from, to := strings.Split(tc.tracked, "/")[0], strings.Split(tc.onDisk, "/")[0]
		if err := os.Rename(filepath.Join(root, from), filepath.Join(root, "case-rename-tmp")); err != nil {
			t.Fatal(err)
		}
		if err := os.Rename(filepath.Join(root, "case-rename-tmp"), filepath.Join(root, to)); err != nil {
			t.Fatal(err)
		}
		before, _, err := snapshotTry(t, root, nil)
		if err != nil {
			// Case-insensitive filesystem: git still lists the old spelling, so
			// membership is not faithful and must be refused.
			snapshotWantUnavailable(t, err, tc.name)
			continue
		}
		// Case-sensitive filesystem: git reports delete + untracked, so edits
		// to the renamed file must still move the identity. Never silent.
		completionWrite(t, root, tc.onDisk, []byte("two\n"))
		after, _, err := snapshotTry(t, root, nil)
		if err == nil && after == before {
			t.Fatalf("%s: edit to the case-renamed file was silently ignored", tc.name)
		}
	}
}

func TestSnapshotCaseMismatchedExplicitRootFailsClosed(t *testing.T) {
	for _, tc := range []struct{ name, tracked, edit, rootSpelling string }{
		{"file", "Foo.txt", "Foo.txt", "foo.txt"},
		{"directory", "Dir/a.txt", "Dir/a.txt", "dir"},
	} {
		root := snapshotGitFixture(t)
		completionWrite(t, root, tc.tracked, []byte("one\n"))
		completionWrite(t, root, "other.txt", []byte("other\n"))
		completionGit(t, root, "add", ".")
		snapshotCommit(t, root, "fixture")
		plan := snapshotPolicy(t, []string{tc.rootSpelling, "other.txt"}, nil)
		base, _, err := snapshotTry(t, root, plan)
		if err != nil {
			// Hard error (membership unavailable, or missing root on a
			// case-sensitive filesystem) is fail-closed.
			continue
		}
		completionWrite(t, root, tc.edit, []byte("two\n"))
		after, _, err := snapshotTry(t, root, plan)
		if err == nil && after == base {
			t.Fatalf("%s: edit to a shipped file under a case-mismatched root was silently ignored", tc.name)
		}
	}
}

func TestSnapshotUntrackedNestedRepoCountsHead(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "top.txt", []byte("top\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	nested := filepath.Join(root, "n")
	if err := os.MkdirAll(nested, 0700); err != nil {
		t.Fatal(err)
	}
	completionGit(t, nested, "init", "-q")
	completionWrite(t, nested, "lib.txt", []byte("lib\n"))
	completionGit(t, nested, "add", ".")
	snapshotCommit(t, nested, "one")
	base, entries, err := snapshotTry(t, root, nil)
	if err != nil {
		t.Fatal(err)
	}
	e, _ := entries["n"].(map[string]any)
	if e["kind"] != "gitlink" || e["commit"] != completionGit(t, nested, "rev-parse", "HEAD") {
		t.Fatalf("untracked nested repo must be a gitlink at its HEAD: %v", entries["n"])
	}
	if _, ok := entries["n/"]; ok {
		t.Fatal("nested repo recorded as an empty directory")
	}
	snapshotMoveHead(t, nested)
	if got, _, err := snapshotTry(t, root, nil); err != nil || got == base {
		t.Fatalf("commit inside the nested repo did not change identity (err=%v)", err)
	}
}

func TestSnapshotGitlinkFakeDotGitFailsClosed(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "top.txt", []byte("top\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	head := completionGit(t, root, "rev-parse", "HEAD")
	completionGit(t, root, "update-index", "--add", "--cacheinfo", "160000,"+head+",sub")
	if err := os.MkdirAll(filepath.Join(root, "sub"), 0700); err != nil {
		t.Fatal(err)
	}
	// Not checked out (no .git): the index pointer is the identity.
	_, entries, err := snapshotTry(t, root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if e, _ := entries["sub"].(map[string]any); e["kind"] != "gitlink" || e["commit"] != head {
		t.Fatalf("unchecked-out gitlink must keep its index pointer: %v", entries["sub"])
	}
	// An empty .git directory must not make git answer for the PARENT repo.
	if err := os.Mkdir(filepath.Join(root, "sub", ".git"), 0700); err != nil {
		t.Fatal(err)
	}
	_, _, err = snapshotTry(t, root, nil)
	snapshotWantUnavailable(t, err, "empty sub/.git")
	// A gitlink path that is a link to a real repository must not be followed.
	elsewhere := testutil.Root(t)
	completionGit(t, elsewhere, "init", "-q")
	completionWrite(t, elsewhere, "lib.txt", []byte("lib\n"))
	completionGit(t, elsewhere, "add", ".")
	snapshotCommit(t, elsewhere, "lib")
	if err := os.RemoveAll(filepath.Join(root, "sub")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(elsewhere, filepath.Join(root, "sub")); err != nil {
		t.Logf("symlinks unavailable on this host: %v", err)
		return
	}
	_, _, err = snapshotTry(t, root, nil)
	if err == nil {
		t.Fatal("a symlinked gitlink path was followed")
	}
}

func TestSnapshotGitlinkExplicitRoot(t *testing.T) {
	root, sub := snapshotSubmoduleFixture(t)
	plan := snapshotPolicy(t, []string{"sub"}, nil)
	base, entries, err := snapshotTry(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if e, _ := entries["sub"].(map[string]any); e["kind"] != "gitlink" {
		t.Fatalf("explicit submodule root must be a gitlink entry: %v", entries["sub"])
	}
	if _, ok := entries["sub/"]; ok {
		t.Fatal("explicit submodule root was walked as a directory")
	}
	snapshotMoveHead(t, sub)
	if got, _, err := snapshotTry(t, root, plan); err != nil || got == base {
		t.Fatalf("moving the submodule HEAD did not change identity (err=%v)", err)
	}
}

func TestSnapshotRootInsideGitlinkRejected(t *testing.T) {
	root, _ := snapshotSubmoduleFixture(t)
	if _, _, err := snapshotTry(t, root, snapshotPolicy(t, []string{"."}, nil)); err != nil {
		t.Fatalf("a . root must keep working: %v", err)
	}
	for _, roots := range [][]string{{"sub/lib.txt"}, {".", "sub/lib.txt"}} {
		_, _, err := snapshotTry(t, root, snapshotPolicy(t, roots, nil))
		if err == nil || !strings.Contains(err.Error(), "INVALID_INPUT_POLICY") {
			t.Fatalf("roots %v inside a submodule must be rejected: %v", roots, err)
		}
	}
}

func TestSnapshotIgnoredExplicitFileRootExcluded(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, ".gitignore", []byte("ignored.txt\n"))
	completionWrite(t, root, "src/a.txt", []byte("a\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	completionWrite(t, root, "ignored.txt", []byte("i1\n"))
	plan := snapshotPolicy(t, []string{"src", "ignored.txt"}, nil)
	base, entries, err := snapshotTry(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := entries["ignored.txt"]; ok {
		t.Fatal("gitignored explicit file root entered the manifest")
	}
	completionWrite(t, root, "ignored.txt", []byte("i2\n"))
	if got, _, err := snapshotTry(t, root, plan); err != nil || got != base {
		t.Fatalf("editing a gitignored explicit root changed identity (err=%v)", err)
	}
	completionWrite(t, root, "src/a.txt", []byte("b\n"))
	if got, _, err := snapshotTry(t, root, plan); err != nil || got == base {
		t.Fatalf("non-vacuous: the shipped root must still contribute (err=%v)", err)
	}
}

func TestSnapshotFakeRootDotGitFailsClosed(t *testing.T) {
	outer := snapshotGitFixture(t)
	completionWrite(t, outer, "top.txt", []byte("top\n"))
	completionGit(t, outer, "add", ".")
	snapshotCommit(t, outer, "fixture")
	inner := filepath.Join(outer, "inner")
	completionWrite(t, inner, "x.txt", []byte("x\n"))
	if err := os.Mkdir(filepath.Join(inner, ".git"), 0700); err != nil {
		t.Fatal(err)
	}
	_, _, err := snapshotTry(t, inner, nil)
	snapshotWantUnavailable(t, err, "empty .git at the root")
	// A linked worktree (.git FILE) is a real top-level and keeps working.
	wt := filepath.Join(testutil.Root(t), "wt")
	completionGit(t, outer, "worktree", "add", "-q", "-b", "linked", wt)
	if m := snapshotMembership(t, wt); m != "git_ship_set" {
		t.Fatalf("linked worktree membership = %q", m)
	}
}

func TestSnapshotUnmergedIndexFailsClosed(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "c.txt", []byte("base\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	if _, _, err := snapshotTry(t, root, nil); err != nil {
		t.Fatalf("baseline: %v", err)
	}
	blob := completionGit(t, root, "rev-parse", "HEAD:c.txt")
	cmd := exec.Command("git", "-C", root, "update-index", "--index-info")
	// A lone stage-2 record (no duplicate path) isolates the stage check.
	cmd.Stdin = strings.NewReader("0 0000000000000000000000000000000000000000\tc.txt\n100644 " + blob + " 2\tc.txt\n")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("fixture unmerged index: %v: %s", err, out)
	}
	if !strings.Contains(completionGit(t, root, "ls-files", "--stage"), " 2\tc.txt") {
		t.Fatal("fixture did not produce an unmerged entry")
	}
	_, _, err := snapshotTry(t, root, nil)
	snapshotWantUnavailable(t, err, "unmerged index")
	// An index path that is not portable is refused before any filesystem use,
	// even though it is absent from the working tree.
	completionGit(t, root, "reset", "-q", "--hard")
	completionGit(t, root, "update-index", "--add", "--cacheinfo", "100644,"+blob+",a\x7fb")
	_, _, err = snapshotTry(t, root, nil)
	snapshotWantUnavailable(t, err, "non-portable index path")
}

// TestSnapshotRejectsDifferingScans: Snapshot collects twice and refuses a pair
// of scans whose identities differ. The git probe runs once per scan, so its
// existing seam rewrites a tracked file exactly between the two scans.
func TestSnapshotRejectsDifferingScans(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "tracked.txt", []byte("one\n"))
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "fixture")
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	real := lstatDotGit
	t.Cleanup(func() { lstatDotGit = real })
	probes := 0
	lstatDotGit = func(p string) (os.FileInfo, error) {
		if filepath.Base(p) == ".git" {
			probes++
			if probes == 2 {
				completionWrite(t, root, "tracked.txt", []byte("two\n"))
			}
		}
		return real(p)
	}
	_, err = Snapshot(f, nil)
	if probes != 2 {
		t.Fatalf("expected one git probe per scan (2), saw %d", probes)
	}
	if fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("differing scans = %v, want CONCURRENT_CHANGE", err)
	}
	lstatDotGit = real
	if _, err := Snapshot(f, nil); err != nil {
		t.Fatalf("stable tree after the change: %v", err)
	}
}
