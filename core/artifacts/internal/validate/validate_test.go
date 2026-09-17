package validate_test

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"testing"
)

func TestSpecReadiness(t *testing.T) {
	d := testutil.Seal(t, testutil.Spec())
	if es := validate.Ready(d, nil); len(es) != 0 {
		t.Fatal(es)
	}
	delete(model.M(model.A(d.Norm()["criteria"])[0]), "statement")
	d = testutil.Seal(t, d.Data)
	if len(validate.Ready(d, nil)) == 0 {
		t.Fatal("incomplete draft was ready")
	}
}
func TestDraftIncompleteRecords(t *testing.T) {
	v := testutil.Spec()
	model.M(v["normative"])["criteria"] = testutil.Arr(testutil.M{"id": "AC-001", "title": "Work in progress"})
	d := testutil.Seal(t, v)
	if len(validate.Ready(d, nil)) == 0 {
		t.Fatal("partial record ready")
	}
}
func TestPlanGraphAndCoverage(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Seal(t, testutil.Plan(s))
	if es := validate.Ready(p, s); len(es) > 0 {
		t.Fatal(es)
	}
	model.M(model.A(p.Norm()["tasks"])[0])["depends_on"] = model.List("T-002")
	d, e := model.Seal(p.Data)
	if e != nil {
		t.Fatal(e)
	}
	if es := validate.Structural(d); len(es) == 0 {
		t.Fatal("cycle accepted")
	}
}
func TestRoleBoundReferences(t *testing.T) {
	v := testutil.Spec()
	model.M(model.A(model.M(v["normative"])["criteria"])[0])["intent_refs"] = model.List("APPROACH-01")
	d, e := model.Seal(v)
	if e != nil {
		t.Fatal(e)
	}
	if len(validate.Structural(d)) == 0 {
		t.Fatal("wrong-role reference accepted")
	}
}
func TestPortablePaths(t *testing.T) {
	for _, s := range []string{"../escape", "a/../b", "/abs", "C:/file", `a\b`, "a//b", "CON.txt", "x/COM1", "x. ", "a\x00b", ".git/../x"} {
		if validate.Path(s, false) {
			t.Errorf("accepted %q", s)
		}
	}
	for _, s := range []string{"src/x.go", ".codearbiter/specs/sample.html"} {
		if !validate.Path(s, false) {
			t.Errorf("rejected %q", s)
		}
	}
}
func TestSchemaSupportsRepeatedArgsAndCells(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	v := testutil.Plan(s)
	c := model.M(model.A(model.M(model.A(model.M(v["normative"])["tasks"])[0])["verification"])[0])
	c["argv"] = model.List("echo", "a", "a")
	d := testutil.Seal(t, v)
	if es := schema.Validate("plan", d.Data); len(es) > 0 {
		t.Fatal(es)
	}
}
func TestClosedSchema(t *testing.T) {
	d := testutil.Seal(t, testutil.Spec())
	d.Data["approval_override"] = true
	if _, e := model.Check(d.Data); e == nil {
		t.Fatal("unknown field accepted")
	}
}
func TestSpecBinding(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Seal(t, testutil.Plan(s))
	s.Norm()["summary"] = "changed"
	s = testutil.Seal(t, s.Data)
	if es := validate.Binding(p, s); len(es) == 0 || es[0].Code != "STALE_SPEC" {
		t.Fatal(es)
	}
}
