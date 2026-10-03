package evidence

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func completionGit(t *testing.T, root string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", append([]string{"-C", root}, args...)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, out)
	}
	return strings.TrimSpace(string(out))
}

func completionWrite(t *testing.T, root, rel string, data []byte) {
	t.Helper()
	target := filepath.Join(root, filepath.FromSlash(rel))
	if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, data, 0600); err != nil {
		t.Fatal(err)
	}
}

func completionFixture(t *testing.T) *store.FS {
	t.Helper()
	git, gitErr := exec.LookPath("git")
	if gitErr != nil {
		t.Fatal(gitErr)
	}
	git, gitErr = filepath.Abs(git)
	if gitErr != nil {
		t.Fatal(gitErr)
	}
	t.Setenv("CODEARBITER_GIT_EXECUTABLE", git)

	root := testutil.Root(t)
	completionGit(t, root, "init", "-q")
	completionWrite(t, root, "source.txt", []byte("original\n"))
	completionWrite(t, root, ".gitignore", []byte("ignored/\n"))
	completionGit(t, root, "add", ".")
	completionGit(t, root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic fixture")
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { f.Close() })
	return f
}

// Build bindings and the reference through the real producer implementation,
// including Python's platform-specific raw filesystem identity representation.
func completionPython(t *testing.T, root string) ([]any, []any) {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	source := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "pysrc"))
	script := `import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import _artifactauthoritylib as a
root = pathlib.Path(sys.argv[2]).resolve()
common = pathlib.Path(a._git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
exe = pathlib.Path(sys.executable).resolve()
b = {"definition_sha256": "a"*64, "argv": [str(exe)], "collector_profile": "fixture", "launch_files": [a._launch_file(exe, "declared-executable")], "cwd": str(root), "cwd_filesystem_id": a._path_identity(root), "workspace_root": str(root), "workspace_filesystem_id": a._path_identity(root), "git_common_dir": str(common), "git_common_filesystem_id": a._path_identity(common), "executable_sha256": a._file_sha256(exe)}
print(json.dumps({"bindings": [b], "snapshots": a._workspace_snapshots([b])}))`
	python := os.Getenv("CODEARBITER_TEST_PYTHON")
	if python == "" {
		python = "python"
	}
	cmd := exec.Command(python, "-c", script, source, root)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("Python workspace fixture: %v: %s", err, out)
	}
	var result map[string]any
	if err := json.Unmarshal(bytes.TrimSpace(out), &result); err != nil {
		t.Fatal(err)
	}
	return model.A(result["bindings"]), model.A(result["snapshots"])
}

func TestCompletionWorkspaceRawMatchesPython(t *testing.T) {
	f := completionFixture(t)
	completionWrite(t, f.Root, "source.txt", []byte("changed\r\n"))
	completionWrite(t, f.Root, "new file.txt", []byte("untracked\x00bytes"))
	completionWrite(t, f.Root, "ignored/output", []byte("outside closure"))
	bindings, want := completionPython(t, f.Root)
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatalf("selected verification workspace cannot be independently frozen: %v", err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("native workspace does not match producer\ngot %v\nwant %v", got, want)
	}
}

func TestCompletionWorkspaceRequiresExplicitGit(t *testing.T) {
	f := completionFixture(t)
	t.Setenv("CODEARBITER_GIT_EXECUTABLE", "")
	if _, err := completionGitText(f.Root, completionGitHead); err == nil {
		t.Fatal("completion silently searched ambient PATH for Git instead of requiring the bridge-selected absolute executable")
	}
}

func TestCompletionWorkspaceRawWhileNativeLockHeld(t *testing.T) {
	f := completionFixture(t)
	completionWrite(t, f.Root, ".codearbiter/.artifacts/store.lock", nil)
	bindings, want := completionPython(t, f.Root)
	unlock, err := f.Lock(true, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatalf("native lock prevents raw selected-workspace proof: %v", err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("locked workspace differs from producer\ngot %v\nwant %v", got, want)
	}
}

func TestCompletionWorkspaceMappedMutationInvalidates(t *testing.T) {
	f := completionFixture(t)
	mapped := filepath.Join(testutil.Root(t), "linked")
	completionGit(t, f.Root, "worktree", "add", "--detach", mapped, "HEAD")
	bindings, _ := completionPython(t, mapped)
	before, err := CompletionWorkspaces(f, bindings, true)
	if err != nil {
		t.Fatalf("selected mapped workspace cannot be frozen: %v", err)
	}
	completionWrite(t, mapped, "source.txt", []byte("changed after review"))
	after, err := CompletionWorkspaces(f, bindings, true)
	if err != nil {
		t.Fatal(err)
	}
	if reflect.DeepEqual(before, after) {
		t.Fatal("mapped source mutation did not invalidate completed evidence")
	}
}

func TestCompletionWorkspaceRawMultipleRootsMatchProducerOrder(t *testing.T) {
	f := completionFixture(t)
	parent := testutil.Root(t)
	roots := []string{filepath.Join(parent, "Upper"), filepath.Join(parent, "lower")}
	bindings, want := []any{}, []any{}
	for _, root := range roots {
		completionGit(t, f.Root, "worktree", "add", "--detach", root, "HEAD")
		b, s := completionPython(t, root)
		bindings = append(bindings, b...)
		want = append(want, s...)
	}
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("native multi-worktree order differs from producer\ngot %v\nwant %v", got, want)
	}
}

func TestCompletionWorkspaceCanonicalStateUpdatesStayFresh(t *testing.T) {
	f := completionFixture(t)
	spec := testutil.Seal(t, testutil.Spec())
	plan := testutil.Plan(spec)
	writePlan := func() {
		doc := testutil.Seal(t, plan)
		data, err := render.Render(doc)
		if err != nil {
			t.Fatal(err)
		}
		completionWrite(t, f.Root, ".codearbiter/plans/example.html", data)
	}
	data, err := render.Render(spec)
	if err != nil {
		t.Fatal(err)
	}
	completionWrite(t, f.Root, ".codearbiter/specs/example.html", data)
	writePlan()
	completionGit(t, f.Root, "add", ".")
	completionGit(t, f.Root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic artifacts")
	bindings, _ := completionPython(t, f.Root)
	before, err := CompletionWorkspaces(f, bindings, true)
	if err != nil {
		t.Fatalf("canonical completion workspace cannot be frozen: %v", err)
	}
	model.M(model.M(model.M(plan["execution"])["tasks"])["T-001"])["state"] = "IN_PROGRESS"
	plan["revision"] = int64(2)
	writePlan()
	after, err := CompletionWorkspaces(f, bindings, true)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(before, after) {
		t.Fatal("canonical task progress update invalidated completion evidence")
	}
	completionWrite(t, f.Root, "unrelated.html", []byte("ordinary source"))
	changed, err := CompletionWorkspaces(f, bindings, true)
	if err != nil {
		t.Fatal(err)
	}
	if reflect.DeepEqual(after, changed) {
		t.Fatal("ordinary HTML was incorrectly excluded from completion closure")
	}
}

func TestCompletionWorkspaceRawTracksGitTypes(t *testing.T) {
	f := completionFixture(t)
	completionWrite(t, f.Root, "deleted.txt", []byte("removed after index"))
	completionWrite(t, f.Root, "old name.txt", []byte("renamed after index"))
	completionWrite(t, f.Root, "materialized-link", []byte("source.txt"))
	completionGit(t, f.Root, "add", ".")
	completionGit(t, f.Root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic members")
	if err := os.Remove(filepath.Join(f.Root, "deleted.txt")); err != nil {
		t.Fatal(err)
	}
	completionGit(t, f.Root, "mv", "old name.txt", "renamed ü file.txt")
	completionGit(t, f.Root, "update-index", "--chmod=+x", "source.txt")
	linkObject := completionGit(t, f.Root, "hash-object", "-w", "materialized-link")
	completionGit(t, f.Root, "update-index", "--cacheinfo", "120000,"+linkObject+",materialized-link")
	completionGit(t, f.Root, "update-index", "--add", "--cacheinfo", "160000,"+completionGit(t, f.Root, "rev-parse", "HEAD")+",empty-gitlink")
	if err := os.Mkdir(filepath.Join(f.Root, "empty-gitlink"), 0700); err != nil {
		t.Fatal(err)
	}
	completionWrite(t, f.Root, "non-ascii-λ.txt", []byte("UTF-8 path"))
	bindings, want := completionPython(t, f.Root)
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Git type closure differs from Python\ngot %v\nwant %v", got, want)
	}
}

func TestCompletionWorkspaceRejectsIdentityAndCommandSubstitution(t *testing.T) {
	for _, change := range []string{"root-id", "cwd-id", "common-id", "common-path", "foreign-worktree", "executable", "launch-id", "launch-bytes", "relative-root", "empty-bindings"} {
		t.Run(change, func(t *testing.T) {
			f := completionFixture(t)
			bindings, _ := completionPython(t, f.Root)
			b := model.M(bindings[0])
			switch change {
			case "root-id":
				b["workspace_filesystem_id"] = "0:0"
			case "cwd-id":
				b["cwd_filesystem_id"] = "0:0"
			case "common-id":
				b["git_common_filesystem_id"] = "0:0"
			case "common-path":
				b["git_common_dir"] = f.Root
				b["git_common_filesystem_id"] = b["workspace_filesystem_id"]
			case "foreign-worktree":
				other := completionFixture(t)
				bindings, _ = completionPython(t, other.Root)
			case "executable":
				b["executable_sha256"] = strings.Repeat("0", 64)
			case "launch-id":
				model.M(model.A(b["launch_files"])[0])["filesystem_id"] = "0:0"
			case "launch-bytes":
				model.M(model.A(b["launch_files"])[0])["sha256"] = strings.Repeat("0", 64)
			case "relative-root":
				b["workspace_root"] = "."
			case "empty-bindings":
				bindings = nil
			}
			if _, err := CompletionWorkspaces(f, bindings, false); err == nil {
				t.Fatalf("%s substitution was accepted", change)
			}
		})
	}
}

func TestCompletionWorkspaceCanonicalNormalizationIsExact(t *testing.T) {
	for _, mutation := range []string{"malformed-canonical", "wrong-kind", "nested-html", "unknown-output", "artifact-norm", "mapped-canonical-state", "derived-output"} {
		t.Run(mutation, func(t *testing.T) {
			f := completionFixture(t)
			spec := testutil.Spec()
			writeSpec := func(root, rel string) {
				data, err := render.Render(testutil.Seal(t, spec))
				if err != nil {
					t.Fatal(err)
				}
				completionWrite(t, root, rel, data)
			}
			writeSpec(f.Root, ".codearbiter/specs/example.html")
			if mutation == "mapped-canonical-state" {
				completionGit(t, f.Root, "add", ".")
				completionGit(t, f.Root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic artifact")
			}
			root := f.Root
			if mutation == "mapped-canonical-state" {
				root = filepath.Join(testutil.Root(t), "linked")
				completionGit(t, f.Root, "worktree", "add", "--detach", root, "HEAD")
			}
			bindings, _ := completionPython(t, root)
			before, err := CompletionWorkspaces(f, bindings, true)
			if err != nil {
				t.Fatal(err)
			}
			reject := false
			switch mutation {
			case "malformed-canonical":
				completionWrite(t, root, ".codearbiter/specs/example.html", []byte("<html>unvalidated</html>"))
				reject = true
			case "wrong-kind":
				writeSpec(root, ".codearbiter/plans/spec-in-plan-directory.html")
				reject = true
			case "nested-html":
				completionWrite(t, root, ".codearbiter/specs/nested/ordinary.html", []byte("ordinary bytes"))
			case "unknown-output":
				completionWrite(t, root, ".codearbiter/.artifacts/unrecognized.txt", []byte("not a derived contract"))
				reject = true
			case "artifact-norm":
				model.M(spec["normative"])["summary"] = "Normative obligation changed."
				writeSpec(root, ".codearbiter/specs/example.html")
			case "mapped-canonical-state":
				spec["revision"] = int64(2)
				writeSpec(root, ".codearbiter/specs/example.html")
			case "derived-output":
				if err := f.Mkdir(".codearbiter/.artifacts"); err != nil {
					t.Fatal(err)
				}
				completionWrite(t, root, ".codearbiter/.artifacts/store.lock", nil)
			}
			after, err := CompletionWorkspaces(f, bindings, true)
			if reject {
				if err == nil {
					t.Fatalf("%s was accepted as normalized canonical input", mutation)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if mutation == "derived-output" {
				if !reflect.DeepEqual(before, after) {
					t.Fatal("validated native lock output invalidates snapshot")
				}
				return
			}
			if reflect.DeepEqual(before, after) {
				t.Fatalf("%s was incorrectly normalized away", mutation)
			}
		})
	}
}

func TestCompletionWorkspaceSymlinkParityAndEscape(t *testing.T) {
	f := completionFixture(t)
	link := filepath.Join(f.Root, "safe-link")
	if err := os.Symlink("source.txt", link); err != nil {
		t.Skipf("host does not permit native symlink fixtures: %v", err)
	}
	if err := os.Symlink("missing.txt", filepath.Join(f.Root, "dangling-link")); err != nil {
		t.Fatal(err)
	}
	bindings, want := completionPython(t, f.Root)
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("symlink closure differs from Python\ngot %v\nwant %v", got, want)
	}
	if err := os.Remove(link); err != nil {
		t.Fatal(err)
	}
	outside := testutil.Root(t)
	completionWrite(t, outside, "outside.txt", []byte("must not be imported"))
	if err := os.Symlink(filepath.Join(outside, "outside.txt"), link); err != nil {
		t.Fatal(err)
	}
	if _, err := CompletionWorkspaces(f, bindings, false); err == nil {
		t.Fatal("escaping workspace symlink was accepted")
	}
}

func TestCompletionReadFileRejectsBoundsAndIndirection(t *testing.T) {
	root := testutil.Root(t)
	file := filepath.Join(root, "evidence.txt")
	completionWrite(t, root, "evidence.txt", []byte("explicit selected evidence"))
	if _, err := CompletionReadFile(file, 4); err == nil {
		t.Fatal("oversize selected evidence was imported")
	}
	if _, err := CompletionReadFile(root, 100); err == nil {
		t.Fatal("directory was imported as evidence")
	}
	if _, err := CompletionReadFile("evidence.txt", 100); err == nil {
		t.Fatal("relative evidence locator was accepted")
	}
	data, err := CompletionReadFile(file, 100)
	if err != nil || string(data) != "explicit selected evidence" {
		t.Fatalf("bounded selected file read failed: %q %v", data, err)
	}
	link := filepath.Join(root, "linked.txt")
	if err := os.Symlink(file, link); err != nil {
		t.Skipf("host does not permit native symlink fixtures: %v", err)
	}
	if _, err := CompletionReadFile(link, 100); err == nil {
		t.Fatal("linked supporting material was imported")
	}
	ancestor := filepath.Join(testutil.Root(t), "linked-directory")
	if err := os.Symlink(root, ancestor); err != nil {
		t.Fatal(err)
	}
	if _, err := CompletionReadFile(filepath.Join(ancestor, "evidence.txt"), 100); err == nil {
		t.Fatal("supporting material through a linked ancestor was imported")
	}
}
