package evidence

// NT-04 / N-F09: the qualified binding schema, role validation and the
// completion consumer share one launch-file bound. Transition rows: N15:02,
// N17:01.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// producerNPMBindings writes a real npm workspace layout and binds it through
// the actual Python producer (_bind_commands). No command is executed by the
// binding beyond the producer's own bounded npm qualification probes.
func producerNPMBindings(t *testing.T, root string, workspaces int) ([]any, map[string]any) {
	t.Helper()
	if _, err := exec.LookPath("npm"); err != nil {
		t.Skipf("npm is not on PATH; the real producer cannot bind an npm layout here: %v", err)
	}
	paths := make([]string, workspaces)
	for i := range paths {
		paths[i] = fmt.Sprintf("packages/p%d", i)
		manifest, _ := json.Marshal(map[string]any{"name": fmt.Sprintf("p%d", i), "scripts": map[string]any{"test": "vitest run --reporter=verbose"}})
		completionWrite(t, root, filepath.Join(paths[i], "package.json"), manifest)
	}
	rootManifest, _ := json.Marshal(map[string]any{"name": "root", "workspaces": paths, "scripts": map[string]any{"test": "npm -w p0 run test"}})
	completionWrite(t, root, "package.json", rootManifest)
	_, file, _, _ := runtime.Caller(0)
	source := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "pysrc"))
	script := `import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import _artifactauthoritylib as a
root = pathlib.Path(sys.argv[2]).resolve()
definition = {"argv": ["npm", "test"], "cwd": ".", "required_tests": ["example test"]}
print(json.dumps(a._bind_commands(root, {"commands": [{"definition": definition, "definition_sha256": "a"*64}]}, {})))`
	python := os.Getenv("CODEARBITER_TEST_PYTHON")
	if python == "" {
		python = "python"
	}
	out, err := exec.Command(python, "-c", script, source, root).CombinedOutput()
	if err != nil {
		t.Fatalf("Python producer: %v: %s", err, out)
	}
	var bindings []any
	if err := json.Unmarshal(bytes.TrimSpace(out), &bindings); err != nil {
		t.Fatal(err)
	}
	definition := map[string]any{"argv": []any{"npm", "test"}, "cwd": ".", "required_tests": []any{"example test"}}
	return bindings, definition
}

func TestCompletionAdmitsActualProducerLaunchBindingCounts(t *testing.T) {
	for _, workspaces := range []int{30, 31, 32} {
		t.Run(fmt.Sprintf("workspaces-%d", workspaces), func(t *testing.T) {
			f := completionFixture(t)
			bindings, definition := producerNPMBindings(t, f.Root, workspaces)
			binding := model.M(bindings[0])
			files := model.A(binding["launch_files"])
			// POSIX npm binds wrapper + root manifest; native Windows npm also binds
			// node runtime, npm CLI and the npm prefix helper.
			extra := 2
			if strings.EqualFold(filepath.Base(model.S(model.A(binding["argv"])[0])), "node.exe") {
				extra = 5
			}
			if len(files) != workspaces+extra || len(files) > observation.MaxLaunchFiles {
				t.Fatalf("producer emitted %d launch files for %d workspaces", len(files), workspaces)
			}
			if es := schema.ValidateWith(observation.QualifiedCommandBindingsSchema(), bindings); len(es) > 0 {
				t.Fatalf("producer binding violates the qualified schema: %v", es[0])
			}
			if !observation.ValidQualifiedBinding(binding, definition) {
				t.Fatal("producer binding fails qualified role validation")
			}
			if _, err := CompletionWorkspaces(f, bindings, false); err != nil {
				t.Fatalf("completion consumer rejected a valid producer binding of %d files: %v", len(files), err)
			}
		})
	}
}

// Synthetic real-file bindings exercise the exact consumer bound independently
// of the producer's platform: 37 is admitted, 38 is not.
func TestCompletionLaunchFileBoundMatchesContract(t *testing.T) {
	f := completionFixture(t)
	bindings, _ := completionPython(t, f.Root)
	base := model.M(bindings[0])
	for _, total := range []int{33, 34, observation.MaxLaunchFiles, observation.MaxLaunchFiles + 1} {
		t.Run(fmt.Sprint(total), func(t *testing.T) {
			binding, _ := canonical.Clone(base)
			files := model.A(binding["launch_files"])[:1]
			for i := len(files); i < total; i++ {
				rel := fmt.Sprintf("launch/f%02d.txt", i)
				data := []byte(fmt.Sprintf("launch input %d\n", i))
				completionWrite(t, f.Root, rel, data)
				path := filepath.Join(f.Root, filepath.FromSlash(rel))
				identity, err := CompletionPathIdentity(path)
				if err != nil {
					t.Fatal(err)
				}
				files = append(files, map[string]any{"path": path, "sha256": canonical.BytesHash(data), "filesystem_id": identity, "role": "npm-workspace-manifest"})
			}
			binding["launch_files"] = files
			_, err := CompletionWorkspaces(f, []any{binding}, false)
			if total <= observation.MaxLaunchFiles && err != nil {
				t.Fatalf("consumer rejected %d launch files within the contract: %v", total, err)
			}
			if total > observation.MaxLaunchFiles && err == nil {
				t.Fatalf("consumer admitted %d launch files beyond the contract", total)
			}
		})
	}
}
