package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"os"
	"path/filepath"
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
