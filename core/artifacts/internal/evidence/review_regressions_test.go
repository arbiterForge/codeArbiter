package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func snapshotFixture(t *testing.T, roots, excludes []string) (*store.FS, *model.Document) {
	t.Helper()
	f, err := store.Open(testutil.Root(t))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { f.Close() })
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Plan(s)
	model.M(p["normative"])["verification_inputs"] = map[string]any{"roots": model.List(roots...), "exclude_directories": model.List(excludes...)}
	return f, testutil.Seal(t, p)
}

func TestSnapshotExplicitRootsCannotReincludeExcludedDirectories(t *testing.T) {
	f, p := snapshotFixture(t, []string{".", "cache", "cache/nested"}, []string{"cache"})
	if err := os.MkdirAll(filepath.Join(f.Root, "cache", "nested"), 0700); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(f.Root, "cache", "nested", "large.exe")
	out, err := os.Create(file)
	if err != nil {
		t.Fatal(err)
	}
	if err = out.Truncate(MaxInputFile + 1); err != nil {
		t.Fatal(err)
	}
	out.Close()
	snap, err := Snapshot(f, p)
	if err != nil {
		t.Fatalf("excluded explicit root was read: %v", err)
	}
	for name := range model.M(model.M(snap["manifest"])["entries"]) {
		if name == "cache" || strings.HasPrefix(name, "cache/") {
			t.Fatalf("excluded entry %s", name)
		}
	}
}

func TestSnapshotOversizeDiagnosticsNamePathAndLimit(t *testing.T) {
	for _, roots := range [][]string{{"site"}, {"site/pagefind.exe"}} {
		t.Run(strings.Join(roots, ","), func(t *testing.T) {
			f, p := snapshotFixture(t, roots, nil)
			if err := os.MkdirAll(filepath.Join(f.Root, "site"), 0700); err != nil {
				t.Fatal(err)
			}
			out, err := os.Create(filepath.Join(f.Root, "site", "pagefind.exe"))
			if err != nil {
				t.Fatal(err)
			}
			if err = out.Truncate(MaxInputFile + 1); err != nil {
				t.Fatal(err)
			}
			out.Close()
			_, err = Snapshot(f, p)
			if fault.Code(err) != "MAX_BYTES" || !strings.Contains(err.Error(), "site/pagefind.exe") || !strings.Contains(err.Error(), "33554432") {
				t.Fatalf("oversize input lost actionable diagnostic: %v", err)
			}
		})
	}
}

func TestSnapshotMissingExplicitRootExplainsPlannedFiles(t *testing.T) {
	f, p := snapshotFixture(t, []string{"src/future.go"}, nil)
	_, err := Snapshot(f, p)
	if fault.Code(err) != "MISSING_INPUT_ROOT" || !strings.Contains(err.Error(), "src/future.go") || !strings.Contains(err.Error(), "existing containing directory") {
		t.Fatalf("missing planned file root has no usable guidance: %v", err)
	}
}

func TestReviewNoZeroTestProofForAlternateRunnerSpelling(t *testing.T) {
	for _, argv := range [][]string{
		{"/usr/local/go/bin/go", "test", "./..."},
		{"python3", "-m", "pytest", "tests"},
		{"npm", "test"},
		{"node", "--test", "test.js"},
	} {
		t.Run(argv[0], func(t *testing.T) {
			s := testutil.Seal(t, testutil.Spec())
			p := testutil.Plan(s)
			task := model.M(model.A(model.M(p["normative"])["tasks"])[0])
			command := model.M(model.A(task["verification"])[0])
			command["argv"] = model.List(argv...)
			command["required_tests"] = model.List()
			d := testutil.Seal(t, p)
			task = d.Symbols.ByID["T-001"].Value
			th, _ := canonical.Hash(task)
			ch, _ := canonical.Hash(command)
			input := canonical.BytesHash([]byte("input"))
			r := &authority.Receipt{
				Data:  map[string]any{"kind": "verification", "subject": map[string]any{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": "T-001"}},
				Event: map[string]any{"payload": map[string]any{"input_sha256": input, "spec_sha256": s.NormHash(), "task_sha256": th, "commands": []any{map[string]any{"definition_sha256": ch, "exit": int64(0), "tests": []any{}, "stdout_sha256": canonical.BytesHash(nil), "stderr_sha256": canonical.BytesHash(nil)}}}},
			}
			if err := TaskPayload(r, d, s, task, input); fault.Code(err) != "NO_TESTS_DECLARED" {
				t.Fatalf("zero-test evidence was accepted for %v: %v", argv, err)
			}
		})
	}
}

// Host hooks write gitignored runtime state under .codearbiter/.markers/ (read-
// injection dedup markers, mode entries, gate records) while a reviewer reads the
// frozen target. That state is not reviewable input: if it entered the manifest,
// every review would invalidate its own evidence before publication.
func TestSnapshotIgnoresHostRuntimeMarkers(t *testing.T) {
	f, p := snapshotFixture(t, []string{"."}, []string{})
	write := func(rel, body string) {
		t.Helper()
		full := filepath.Join(f.Root, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(full), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(body), 0600); err != nil {
			t.Fatal(err)
		}
	}
	write(".codearbiter/.markers/standup-2026-10-04", "x")
	before, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	write(".codearbiter/.markers/readinject-0123.marker", "")
	write(".codearbiter/.markers/mode.d/session.json", "{}")
	after, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	if before["sha256"] != after["sha256"] {
		t.Fatal("a host runtime marker written during review changed the input snapshot")
	}
	for name := range model.M(model.M(after["manifest"])["entries"]) {
		if name == ".codearbiter/.markers/" || strings.HasPrefix(name, ".codearbiter/.markers/") {
			t.Fatalf("runtime marker entry %s is in the input manifest", name)
		}
	}
	// Controls: the exclusion is exactly the marker directory, not governance or
	// a look-alike sibling.
	write(".codearbiter/.markers-x/note.md", "x")
	sibling, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	if sibling["sha256"] == after["sha256"] {
		t.Fatal("a look-alike sibling of the marker directory was excluded")
	}
	write(".codearbiter/CONTEXT.md", "changed")
	governed, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	if governed["sha256"] == sibling["sha256"] {
		t.Fatal("a governed .codearbiter file change did not change the input snapshot")
	}
}

// A link named like the marker directory is skipped unfollowed: its in-repo
// target is still hashed at its real path, so the exclusion hides nothing.
func TestSnapshotMarkerLinkHidesNothing(t *testing.T) {
	f, p := snapshotFixture(t, []string{"."}, []string{})
	target := filepath.Join(f.Root, "real")
	if err := os.MkdirAll(target, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(target, "input.go"), []byte("package real\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(f.Root, ".codearbiter"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, filepath.Join(f.Root, ".codearbiter", ".markers")); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	snap, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	entries := model.M(model.M(snap["manifest"])["entries"])
	if entries["real/input.go"] == nil {
		t.Fatal("the in-repo target of a marker-named link lost its own coverage")
	}
	for name := range entries {
		if strings.HasPrefix(name, ".codearbiter/.markers/") {
			t.Fatalf("snapshot followed a marker-named link: %s", name)
		}
	}
}

// The exclusion is exact-case: on a case-sensitive filesystem a differently
// cased directory is ordinary input and stays hashed.
func TestSnapshotMarkerExclusionIsExactCase(t *testing.T) {
	f, p := snapshotFixture(t, []string{"."}, []string{})
	if err := os.MkdirAll(filepath.Join(f.Root, ".codearbiter", ".Markers"), 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(f.Root, ".codearbiter", ".markers")); err == nil {
		t.Skip("case-insensitive filesystem")
	}
	if err := os.WriteFile(filepath.Join(f.Root, ".codearbiter", ".Markers", "x"), []byte("x"), 0600); err != nil {
		t.Fatal(err)
	}
	snap, err := Snapshot(f, p)
	if err != nil {
		t.Fatal(err)
	}
	if model.M(model.M(snap["manifest"])["entries"])[".codearbiter/.Markers/x"] == nil {
		t.Fatal("a case variant of the marker directory was excluded")
	}
}

// Junctions report neither a directory nor a symlink, so the marker exclusion
// must not apply to them; the rooted read refuses an escaping junction instead.
func TestSnapshotMarkerJunctionFailsClosed(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("junctions are Windows-only")
	}
	f, p := snapshotFixture(t, []string{"."}, []string{})
	if err := os.MkdirAll(filepath.Join(f.Root, ".codearbiter"), 0700); err != nil {
		t.Fatal(err)
	}
	outside := t.TempDir()
	link := filepath.Join(f.Root, ".codearbiter", ".markers")
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", link, outside).CombinedOutput(); err != nil {
		t.Skipf("mklink /J unavailable: %v %s", err, out)
	}
	if _, err := Snapshot(f, p); err == nil {
		t.Fatal("snapshot accepted an escaping junction at the marker directory")
	}
}
