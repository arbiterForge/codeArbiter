package evidence

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Regression tests for the snapshot hardening follow-ups in #962.

// countedScan runs one snapshotOnce pass and counts how often each repository
// path was read.
func countedScan(t *testing.T, root string, plan *model.Document) (map[string]any, map[string]int) {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	reads := map[string]int{}
	f.SetReadHook(func(rel string, _ bool) { reads[strings.TrimPrefix(rel, "./")]++ })
	s, err := snapshotOnce(f, plan)
	if err != nil {
		t.Fatal(err)
	}
	return s["manifest"].(map[string]any)["entries"].(map[string]any), reads
}

// staleFarmBinding records a binding whose base hash no projection matches.
func staleFarmBinding(t *testing.T, root, projection string) {
	t.Helper()
	b, err := canonical.Marshal(map[string]any{"format": "codearbiter.farm-binding/0.1.0", "projection_path": projection, "base_sha256": canonical.BytesHash([]byte("no projection has this base"))})
	if err != nil {
		t.Fatal(err)
	}
	completionWrite(t, root, authority.Root+"/farm-bindings/"+canonical.BytesHash(b)+".json", b)
}

// A bound projection is opened once per scan: as an output when its binding
// matches, and as an ordinary input, from the same read, when it does not.
func TestSnapshotFarmProjectionOpenedOnce(t *testing.T) {
	const projection = ".codearbiter/plans/p0.plan.json"
	matched := farmBindingFixture(t, 1, true)
	entries, reads := countedScan(t, matched, nil)
	if reads[projection] != 1 {
		t.Errorf("matched binding: projection read %d times, want 1 (reads %v)", reads[projection], reads)
	}
	if _, ok := entries[projection]; ok {
		t.Error("matched binding: the projection was hashed as an input")
	}

	stale := farmBindingFixture(t, 1, false)
	staleFarmBinding(t, stale, projection)
	entries, reads = countedScan(t, stale, nil)
	if reads[projection] != 1 {
		t.Errorf("stale binding: projection read %d times, want 1 (reads %v)", reads[projection], reads)
	}
	item, ok := entries[projection].(map[string]any)
	body, err := os.ReadFile(filepath.Join(stale, filepath.FromSlash(projection)))
	if err != nil {
		t.Fatal(err)
	}
	if !ok || item["kind"] != "bytes" || item["sha256"] != canonical.BytesHash(body) {
		t.Errorf("stale binding: projection entry %v, want its bytes hashed as an input", entries[projection])
	}
}

// Farm bindings never make a scan open or list anything ahead of its walk: a
// projection outside the plan's roots is not read at all.
func TestSnapshotScopedRootsNeverReadFarmProjections(t *testing.T) {
	root := farmBindingFixture(t, 3, true)
	_, reads := countedScan(t, root, snapshotPolicy(t, []string{"src"}, nil))
	for p, n := range reads {
		if strings.HasSuffix(p, ".plan.json") {
			t.Errorf("projection %s outside the roots was read %d times", p, n)
		}
	}
	if reads["src/a.txt"] != 1 {
		t.Fatalf("the scoped root was not walked: %v", reads)
	}
}

// The scan's anchor cache is bounded, so a very wide root policy fails closed
// instead of exhausting file descriptors.
func TestSnapshotAnchorCacheIsCapped(t *testing.T) {
	root := testutil.Root(t)
	roots := []string{}
	for i := 0; i <= maxAnchors; i++ {
		rel := fmt.Sprintf("d%03d/x", i)
		completionWrite(t, root, rel+"/f.txt", []byte("f\n"))
		roots = append(roots, rel)
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	_, err = snapshotOnce(f, snapshotPolicy(t, roots, nil))
	if fault.Code(err) != "MAX_INPUTS" {
		t.Fatalf("%d roots under distinct parents: got %v, want MAX_INPUTS", len(roots), err)
	}
	// Under the cap the same shape scans normally.
	if _, err := snapshotOnce(f, snapshotPolicy(t, roots[:maxAnchors/2], nil)); err != nil {
		t.Fatalf("%d roots: %v", maxAnchors/2, err)
	}
}

// A reused anchor is re-checked against its parent's current entry, so a cached
// handle never outlives a swap of the directory name it was opened under.
func TestAnchorsRecheckReusedDirectory(t *testing.T) {
	root := testutil.Root(t)
	completionWrite(t, root, "a/b/f.txt", []byte("f\n"))
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	anch := newAnchors(f)
	defer anch.Close()
	if _, err := anch.get("a/b"); err != nil {
		t.Fatal(err)
	}
	if _, err := anch.get("a/b"); err != nil {
		t.Fatalf("unchanged reuse: %v", err)
	}
	if err := os.Rename(filepath.Join(root, "a"), filepath.Join(root, "a-old")); err != nil {
		t.Skipf("this host cannot rename a directory that has an open handle: %v", err)
	}
	completionWrite(t, root, "a/b/f.txt", []byte("swapped\n"))
	if _, err := anch.get("a/b"); fault.Code(err) != "CONCURRENT_CHANGE" {
		t.Fatalf("reuse after the name was swapped: got %v, want CONCURRENT_CHANGE", err)
	}
}

// A tracked symlink fails the snapshot itself with UNSAFE_PATH, not only the
// store primitive beneath it.
func TestSnapshotTrackedSymlinkIsUnsafePath(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "target.txt", []byte("target\n"))
	if err := os.Symlink("target.txt", filepath.Join(root, "link.txt")); err != nil {
		t.Skipf("host does not permit native symlink fixtures: %v", err)
	}
	completionGit(t, root, "add", ".")
	snapshotCommit(t, root, "symlink")
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if _, err := Snapshot(f, nil); fault.Code(err) != "UNSAFE_PATH" {
		t.Fatalf("tracked symlink: got %v (code %q), want UNSAFE_PATH", err, fault.Code(err))
	}
}

func TestCompletionGitEnvFiltersInjectedConfig(t *testing.T) {
	ignore := filepath.Join(testutil.Root(t), "ignore")
	bridge := []string{"GIT_CONFIG_COUNT=1", "GIT_CONFIG_KEY_0=core.excludesFile", "GIT_CONFIG_VALUE_0=" + ignore}
	has := func(env []string, entry string) bool {
		for _, e := range env {
			if e == entry {
				return true
			}
		}
		return false
	}
	injected := func(env []string) []string {
		var out []string
		for _, e := range env {
			if strings.HasPrefix(strings.ToUpper(e), "GIT_CONFIG") && !strings.HasPrefix(strings.ToUpper(e), "GIT_CONFIG_GLOBAL=") && !strings.HasPrefix(strings.ToUpper(e), "GIT_CONFIG_NOSYSTEM=") {
				out = append(out, e)
			}
		}
		return out
	}
	files := []string{"GIT_CONFIG_GLOBAL=/g", "GIT_CONFIG_NOSYSTEM=1", "PATH=/bin"}
	got := completionGitEnv(append(append([]string{}, files...), bridge...))
	for _, e := range append(files, bridge...) {
		if !has(got, e) {
			t.Errorf("bridge environment lost %q: %v", e, got)
		}
	}
	for name, env := range map[string][]string{
		"parameters":         append([]string{"GIT_CONFIG_PARAMETERS='core.fsmonitor'='true'"}, bridge...),
		"legacy file":        {"GIT_CONFIG=/elsewhere"},
		"extra pair":         {"GIT_CONFIG_COUNT=2", "GIT_CONFIG_KEY_0=core.excludesFile", "GIT_CONFIG_VALUE_0=" + ignore, "GIT_CONFIG_KEY_1=core.fsmonitor", "GIT_CONFIG_VALUE_1=true"},
		"other key":          {"GIT_CONFIG_COUNT=1", "GIT_CONFIG_KEY_0=core.fsmonitor", "GIT_CONFIG_VALUE_0=" + ignore},
		"relative value":     {"GIT_CONFIG_COUNT=1", "GIT_CONFIG_KEY_0=core.excludesFile", "GIT_CONFIG_VALUE_0=ignore"},
		"pair without count": {"GIT_CONFIG_KEY_0=core.excludesFile", "GIT_CONFIG_VALUE_0=" + ignore},
	} {
		got := injected(completionGitEnv(env))
		if name == "parameters" {
			if len(got) != 3 || has(got, env[0]) {
				t.Errorf("%s: forwarded %v, want only the bridge pair", name, got)
			}
			continue
		}
		if len(got) != 0 {
			t.Errorf("%s: forwarded injected configuration %v", name, got)
		}
	}
}

// End to end: the bridge's ignore pair still shapes membership, and injected
// configuration does not.
func TestSnapshotHonorsOnlyTheBridgeIgnorePair(t *testing.T) {
	root := snapshotGitFixture(t)
	completionWrite(t, root, "kept.txt", []byte("kept\n"))
	completionWrite(t, root, "local.txt", []byte("local\n"))
	ignore := filepath.Join(testutil.Root(t), "ignore")
	if err := os.WriteFile(ignore, []byte("local.txt\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_KEY_1", "GIT_CONFIG_VALUE_1", "GIT_CONFIG_PARAMETERS"} {
		t.Setenv(name, "")
		os.Unsetenv(name)
	}
	member := func() bool {
		t.Helper()
		_, entries := snapshotID(t, root)
		_, ok := entries["local.txt"]
		return ok
	}
	t.Setenv("GIT_CONFIG_COUNT", "1")
	t.Setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
	t.Setenv("GIT_CONFIG_VALUE_0", ignore)
	if member() {
		t.Fatal("the bridge's core.excludesFile pair was not honored")
	}
	t.Setenv("GIT_CONFIG_COUNT", "2")
	t.Setenv("GIT_CONFIG_KEY_1", "core.fsmonitor")
	t.Setenv("GIT_CONFIG_VALUE_1", "false")
	if !member() {
		t.Fatal("an extra injected pair was forwarded with the ignore pair")
	}
	os.Unsetenv("GIT_CONFIG_COUNT")
	os.Unsetenv("GIT_CONFIG_KEY_0")
	os.Unsetenv("GIT_CONFIG_VALUE_0")
	os.Unsetenv("GIT_CONFIG_KEY_1")
	os.Unsetenv("GIT_CONFIG_VALUE_1")
	t.Setenv("GIT_CONFIG_PARAMETERS", "'core.excludesfile'='"+filepath.ToSlash(ignore)+"'")
	if !member() {
		t.Fatal("GIT_CONFIG_PARAMETERS reached the membership probe")
	}
}

// A root below the top level of an enclosing work tree takes that work tree's
// membership scoped to the root, so the enclosing .gitignore applies (#962).
func TestSnapshotNestedRootUsesScopedGitMembership(t *testing.T) {
	top := snapshotGitFixture(t)
	completionWrite(t, top, ".gitignore", []byte("pkg/build/\nignored/\n"))
	completionWrite(t, top, "outside.txt", []byte("outside\n"))
	completionWrite(t, top, "pkg/tracked.txt", []byte("tracked\n"))
	completionGit(t, top, "add", ".")
	snapshotCommit(t, top, "nested")
	completionWrite(t, top, "pkg/src/untracked.txt", []byte("untracked\n"))
	completionWrite(t, top, "pkg/build/out.bin", []byte("one\n"))
	root := filepath.Join(top, "pkg")
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	snap := func() (string, map[string]any) {
		t.Helper()
		s, err := Snapshot(f, nil)
		if err != nil {
			t.Fatal(err)
		}
		manifest := s["manifest"].(map[string]any)
		if manifest["membership"] != "git_ship_set" {
			t.Fatalf("nested root membership %v, want git_ship_set", manifest["membership"])
		}
		return s["sha256"].(string), manifest["entries"].(map[string]any)
	}
	before, entries := snap()
	for _, want := range []string{"tracked.txt", "src/untracked.txt"} {
		if _, ok := entries[want]; !ok {
			t.Errorf("ship-set member %s is missing: %v", want, entries)
		}
	}
	for p := range entries {
		if strings.HasPrefix(p, "build") || strings.Contains(p, "outside") {
			t.Errorf("entry %s is ignored or outside the root", p)
		}
	}
	completionWrite(t, top, "pkg/build/out.bin", []byte("two\n"))
	completionWrite(t, top, "outside.txt", []byte("changed\n"))
	if after, _ := snap(); after != before {
		t.Fatal("an ignored or out-of-root change staled the nested root's identity")
	}
	completionWrite(t, top, "pkg/tracked.txt", []byte("edited\n"))
	if after, _ := snap(); after == before {
		t.Fatal("a tracked edit inside the nested root did not change its identity")
	}
}

// A nested root the enclosing work tree ignores, or whose Git probe cannot run,
// fails closed instead of falling back to the filesystem.
func TestSnapshotNestedRootFailsClosed(t *testing.T) {
	top := snapshotGitFixture(t)
	completionWrite(t, top, ".gitignore", []byte("ignored/\n"))
	completionWrite(t, top, "ignored/pkg/a.txt", []byte("a\n"))
	completionWrite(t, top, "pkg/a.txt", []byte("a\n"))
	for name, root := range map[string]string{"ignored root": filepath.Join(top, "ignored", "pkg"), "no Git executable": filepath.Join(top, "pkg")} {
		if name == "no Git executable" {
			t.Setenv("CODEARBITER_GIT_EXECUTABLE", "")
		}
		f, err := store.Open(root)
		if err != nil {
			t.Fatal(err)
		}
		_, err = Snapshot(f, nil)
		f.Close()
		if fault.Code(err) != "INPUT_MEMBERSHIP_UNAVAILABLE" {
			t.Errorf("%s: got %v, want INPUT_MEMBERSHIP_UNAVAILABLE", name, err)
		}
	}
}
