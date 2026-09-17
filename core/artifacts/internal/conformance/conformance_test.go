package conformance_test

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

type golden struct {
	doc  *model.Document
	json []byte
	html []byte
}

type sourceGolden struct {
	value map[string]any
	json  []byte
	html  []byte
}

func loadSourceGolden(t *testing.T, name, jsonHash, htmlHash string) sourceGolden {
	t.Helper()
	root := filepath.Join("..", "..", "testdata", "reference")
	jsonBytes, err := os.ReadFile(filepath.Join(root, name+".json"))
	if err != nil {
		t.Fatal(err)
	}
	value, err := canonical.Object(jsonBytes)
	if err != nil {
		t.Fatal(err)
	}
	htmlBytes, err := os.ReadFile(filepath.Join(root, name+".html"))
	if err != nil {
		t.Fatal(err)
	}
	if canonical.BytesHash(jsonBytes) != jsonHash || canonical.BytesHash(htmlBytes) != htmlHash {
		t.Fatalf("%s reviewed source golden changed without manifest review", name)
	}
	if model.S(value["schema_version"]) != "0.2.0" || model.S(value["governance"].(map[string]any)["state"]) != "draft" {
		t.Fatalf("%s source boundary was silently relabeled", name)
	}
	return sourceGolden{value: value, json: jsonBytes, html: htmlBytes}
}

func resolve(t *testing.T, root, id string) (*model.Document, string) {
	t.Helper()
	fs, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	catalog, err := repository.Scan(fs)
	if err != nil {
		t.Fatal(err)
	}
	entry, err := catalog.Resolve(id)
	if err != nil {
		t.Fatal(err)
	}
	return entry.Doc, entry.Path

}

func createCurrentPair(t *testing.T, specSource, planSource sourceGolden) (golden, golden) {
	t.Helper()
	root := t.TempDir()
	create := func(operationID string, source map[string]any, kind, specID string) {
		normative := model.M(source["normative"])
		request := map[string]any{
			"protocol": operations.Protocol, "operation_id": operationID,
			"artifact_id": source["artifact_id"], "kind": kind, "slug": source["slug"],
			"title": normative["title"], "summary": normative["summary"], "normative": normative,
		}
		if specID != "" {
			request["spec_id"] = specID
		}
		if _, err := operations.Run(root, "create", request); err != nil {
			t.Fatal(err)
		}
	}
	create("conformance-spec-create", specSource.value, "spec", "")
	spec, specPath := resolve(t, root, model.S(specSource.value["artifact_id"]))
	planValue, err := canonical.Clone(planSource.value)
	if err != nil {
		t.Fatal(err)
	}
	model.M(model.M(planValue["normative"])["spec_ref"])["normative_sha256"] = spec.NormHash()
	create("conformance-plan-create", planValue, "plan", spec.ID())
	plan, planPath := resolve(t, root, model.S(planValue["artifact_id"]))
	loadHTML := func(path string) []byte {
		bytes, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(path)))
		if err != nil {
			t.Fatal(err)
		}
		return bytes
	}
	for name, doc := range map[string]*model.Document{"spec": spec, "plan": plan} {
		if err := doc.VerifyIntegrity(); err != nil {
			t.Fatal(err)
		}
		if errs := validate.Structural(doc); len(errs) != 0 {
			t.Fatalf("%s structural errors: %v", name, errs)
		}
		if _, err := doc.TypedNormative(); err != nil {
			t.Fatalf("%s typed normative model: %v", name, err)
		}
	}
	return golden{doc: spec, json: specSource.json, html: loadHTML(specPath)},
		golden{doc: plan, json: planSource.json, html: loadHTML(planPath)}
}

func TestSpecPlanConformance(t *testing.T) {
	specSource := loadSourceGolden(t, "spec",
		"993ab984404fd92339bd42bd62d30a3db5f28a2311ad087740ee24d0c855cff3",
		"d206bff4525ce9498b0d20ee5621a1199eeef57fb986b25c0828ebb60fc2c6b4")
	planSource := loadSourceGolden(t, "plan",
		"7d1a2e86dde48210cdc7362ea3270746cd2b6caf4468c464eb3ae4f5becd5356",
		"fdc917767b25928a5b27b1ecc5da89e3d3172d41ebe921ef0282c73077961bd8")
	spec, plan := createCurrentPair(t, specSource, planSource)

	t.Run("current render and parse integrity", func(t *testing.T) {
		for name, fixture := range map[string]golden{"spec": spec, "plan": plan} {
			rendered, err := render.Render(fixture.doc)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(rendered, fixture.html) {
				t.Fatalf("%s renderer is not stable for the current sealed document", name)
			}
			parsed, err := render.Parse(fixture.html)
			if err != nil {
				t.Fatal(err)
			}
			if parsed.Hash() != fixture.doc.Hash() || parsed.NormHash() != fixture.doc.NormHash() {
				t.Fatalf("%s identities changed across HTML round trip", name)
			}
			for id := range fixture.doc.Symbols.ByID {
				if bytes.Count(fixture.html, []byte("<!-- CA:BEGIN:"+id+" -->")) != 1 ||
					bytes.Count(fixture.html, []byte("id=\""+id+"\"")) != 1 {
					t.Fatalf("%s symbol %s lacks a unique marker/anchor pair", name, id)
				}
			}
		}
	})

	t.Run("binding coverage and dependency graph", func(t *testing.T) {
		binding := model.M(plan.doc.Norm()["spec_ref"])
		if model.S(binding["artifact_id"]) != spec.doc.ID() ||
			model.S(binding["normative_sha256"]) != spec.doc.NormHash() {
			t.Fatal("plan does not bind the reviewed specification identity")
		}
		criteria := map[string]bool{}
		for _, value := range model.A(spec.doc.Norm()["criteria"]) {
			criteria[model.S(model.M(value)["id"])] = false
		}
		tasks := map[string]map[string]any{}
		checkpointMembers := map[string]int{}
		for _, value := range model.A(plan.doc.Norm()["tasks"]) {
			task := model.M(value)
			id := model.S(task["id"])
			tasks[id] = task
			checkpointMembers[id]++
			for _, ref := range model.Strings(task["criterion_refs"]) {
				artifact, criterion, err := symbol.Split(ref)
				if err != nil || artifact != spec.doc.ID() {
					t.Fatalf("%s has invalid criterion ref %q", id, ref)
				}
				if _, ok := criteria[criterion]; !ok {
					t.Fatalf("%s references unknown criterion %s", id, criterion)
				}
				criteria[criterion] = true
			}
			for _, verification := range model.A(task["verification"]) {
				definition := model.M(verification)
				argv := model.Strings(definition["argv"])
				for index, arg := range argv {
					if arg == "-run" && (index+1 >= len(argv) || len(model.Strings(definition["required_tests"])) == 0) {
						t.Fatalf("%s has a named-test command without required test outcomes", id)
					}
				}
			}
		}
		for _, value := range model.A(plan.doc.Norm()["checkpoints"]) {
			checkpoint := model.M(value)
			for _, id := range model.Strings(checkpoint["tasks"]) {
				if _, ok := tasks[id]; !ok {
					t.Fatalf("checkpoint references unknown task %s", id)
				}
				checkpointMembers[id]--
			}
		}
		for id, count := range checkpointMembers {
			if count != 0 {
				t.Fatalf("task %s does not have exactly one checkpoint membership", id)
			}
		}
		for id, covered := range criteria {
			if !covered {
				t.Fatalf("active criterion %s is not covered", id)
			}
		}
		state := map[string]int{}
		var visit func(string)
		visit = func(id string) {
			if state[id] == 1 {
				t.Fatalf("task dependency cycle reaches %s", id)
			}
			if state[id] == 2 {
				return
			}
			state[id] = 1
			for _, dependency := range model.Strings(tasks[id]["depends_on"]) {
				if _, ok := tasks[dependency]; !ok {
					t.Fatalf("%s depends on unknown task %s", id, dependency)
				}
				visit(dependency)
			}
			state[id] = 2
		}
		for id := range tasks {
			visit(id)
		}
	})

	t.Run("identity domains remain independent", func(t *testing.T) {
		presentationOnly, err := canonical.Clone(spec.doc.Data)
		if err != nil {
			t.Fatal(err)
		}
		model.M(presentationOnly["presentation"])["brand_name"] = "Reviewed alternate brand"
		presentationDoc, err := model.Seal(presentationOnly)
		if err != nil {
			t.Fatal(err)
		}
		if presentationDoc.NormHash() != spec.doc.NormHash() || presentationDoc.Hash() == spec.doc.Hash() {
			t.Fatal("presentation edit changed the wrong identity domain")
		}

		metadataOnly, err := canonical.Clone(plan.doc.Data)
		if err != nil {
			t.Fatal(err)
		}
		metadataOnly["revision"] = model.I(metadataOnly["revision"]) + 1
		metadataDoc, err := model.Seal(metadataOnly)
		if err != nil {
			t.Fatal(err)
		}
		if metadataDoc.NormHash() != plan.doc.NormHash() || metadataDoc.Hash() == plan.doc.Hash() {
			t.Fatal("revision metadata edit changed the wrong identity domain")
		}

		normative, err := canonical.Clone(spec.doc.Data)
		if err != nil {
			t.Fatal(err)
		}
		norm := model.M(normative["normative"])
		norm["summary"] = model.S(norm["summary"]) + " Reviewed conformance mutation."
		normativeDoc, err := model.Seal(normative)
		if err != nil {
			t.Fatal(err)
		}
		if normativeDoc.NormHash() == spec.doc.NormHash() || normativeDoc.Hash() == spec.doc.Hash() {
			t.Fatal("normative edit did not change both identities")
		}
	})

	t.Run("adversarial inputs fail closed", func(t *testing.T) {
		duplicate := bytes.Replace(spec.json, []byte("{\n"), []byte("{\n  \"format\": \"duplicate\",\n"), 1)
		if _, err := canonical.Object(duplicate); err == nil {
			t.Fatal("duplicate JSON key accepted")
		}
		if _, err := render.Parse(append(append([]byte{}, spec.html...), []byte("<script>alert(1)</script>")...)); err == nil {
			t.Fatal("appended executable HTML accepted")
		}
		if _, err := render.Logo("image/svg+xml", []byte(`<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/x"/></svg>`)); err == nil {
			t.Fatal("remote hostile logo accepted")
		}
		if !strings.Contains(string(spec.html), "Content-Security-Policy") {
			t.Fatal("golden HTML lacks its offline content policy")
		}
	})
}
