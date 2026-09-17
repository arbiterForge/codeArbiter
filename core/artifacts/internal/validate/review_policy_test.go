package validate_test

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"testing"
)

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
