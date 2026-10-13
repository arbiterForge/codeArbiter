package validate_test

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"strings"
	"testing"
)

func TestReadyRejectsRepositoryRelativeExcludesOutsideRoots(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Plan(s)
	n := model.M(p["normative"])
	n["verification_inputs"] = map[string]any{"roots": model.List("src"), "exclude_directories": model.List("node_modules", "dist")}
	d := testutil.Seal(t, p)
	seen := map[string]bool{}
	for _, diagnostic := range validate.Ready(d, s) {
		if diagnostic.Code == "INVALID_INPUT_POLICY" && diagnostic.Field == "verification_inputs.exclude_directories" {
			for _, name := range []string{"node_modules", "dist"} {
				if strings.Contains(diagnostic.Message, name) && strings.Contains(diagnostic.Message, "repository-relative") {
					seen[name] = true
				}
			}
		}
	}
	if len(seen) != 2 {
		t.Fatalf("ready plan accepted provably inert exclusions: %v", seen)
	}
}

func TestReviewRunnerRecognition(t *testing.T) {
	for _, argv := range [][]string{
		{"/opt/go/bin/go", "test", "./..."}, {`C:\Go\bin\go.exe`, "test"},
		{"python3.13", "-I", "-m", "pytest"}, {"python", "-m", "unittest"},
		{"npm", "run", "test:unit"}, {"node", "--test", "spec.mjs"},
		{"yarn", "test"}, {"cargo", "test"}, {"dotnet", "test"},
	} {
		if !validate.IsTestCommand(argv) {
			t.Errorf("runner not recognized: %q", argv)
		}
	}
	for _, argv := range [][]string{{"go", "vet", "./..."}, {"go", "build"}, {"python3", "check_schema.py"}, {"npm", "run", "build"}, {"node", "app.js"}} {
		if validate.IsTestCommand(argv) {
			t.Errorf("non-test command misclassified: %q", argv)
		}
	}
}
func TestReviewNamedTestRequirementAtReadiness(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Plan(s)
	command := model.M(model.A(model.M(model.A(model.M(p["normative"])["tasks"])[0])["verification"])[0])
	command["argv"] = model.List("python3", "-m", "pytest", "tests")
	command["required_tests"] = model.List()
	d := testutil.Seal(t, p)
	found := false
	for _, e := range validate.Ready(d, s) {
		if e.Code == "NO_TESTS_DECLARED" {
			found = true
		}
	}
	if !found {
		t.Fatal("ready plan permits an unbound test runner")
	}
}

// The snapshot never hashes host runtime markers, so a plan must neither root its
// evidence there nor claim a task path there as covered.
func TestReadyRefusesRuntimeMarkerInputs(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	for _, root := range []string{".codearbiter/.markers", ".codearbiter/.markers/mode.d"} {
		p := testutil.Plan(s)
		model.M(p["normative"])["verification_inputs"] = map[string]any{"roots": model.List(".", root), "exclude_directories": model.List()}
		_, err := render.Prepare(p)
		if fault.Code(err) != "INVALID_INPUT_POLICY" || !strings.Contains(err.Error(), "unsafe input root") {
			t.Errorf("root %q under the runtime marker directory was accepted", root)
		}
	}
	for _, policy := range []map[string]any{nil, {"roots": model.List("."), "exclude_directories": model.List()}} {
		p := testutil.Plan(s)
		n := model.M(p["normative"])
		if policy == nil {
			delete(n, "verification_inputs")
		} else {
			n["verification_inputs"] = policy
		}
		task := model.M(model.A(n["tasks"])[0])
		task["paths"] = append(model.A(task["paths"]), map[string]any{"action": "modify", "path": ".codearbiter/.markers/mode.d/x.json"})
		found := false
		for _, e := range validate.Ready(testutil.Seal(t, p), s) {
			if e.Code == "UNCOVERED_INPUT" && strings.Contains(e.Message, ".codearbiter/.markers/") {
				found = true
			}
		}
		if !found {
			t.Errorf("task path under the runtime marker directory was certified as covered (policy %v)", policy)
		}
	}
	if !validate.InputIncludes(map[string]any{}, ".codearbiter/.markers-x/note.md") {
		t.Error("a look-alike sibling of the runtime marker directory lost coverage")
	}
}
