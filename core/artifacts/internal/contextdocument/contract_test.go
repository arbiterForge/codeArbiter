package contextdocument

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

func TestContextDocumentContract(t *testing.T) {
	const evidence = `"evidence_refs":["CLAIM-SOURCE-1"]`
	entry := map[string]string{
		"identity":             `{"id":"FIELD-NAME","kind":"identity","field":"project_name","value":"Arbiter",` + evidence + `}`,
		"fact":                 `{"id":"CLAIM-RUNTIME","kind":"fact","field":"runtime","value":"Go 1.27.1","state":"observed","source_ref":"go.mod","consumer_ref":"core/artifacts",` + evidence + `}`,
		"command":              `{"id":"FIELD-TEST","kind":"command","invocation":{"kind":"literal_argv","argv":["go","test","./..."]},"cwd":"core/artifacts","prerequisites":["Go 1.27.1"],"verification":{"state":"declared","observation_ref":null,"binding":null},` + evidence + `}`,
		"source_relationship":  `{"id":"FIELD-SOURCE","kind":"source_relationship","subject":"CLAIM-RUNTIME","relation":"derived_from","object_ref":"go.mod",` + evidence + `}`,
		"map_entry":            `{"id":"FIELD-MAP","kind":"map_entry","concern":"artifact engine","paths":["core/artifacts"],"role":"structured artifact owner","consumer_ref":"core/artifacts",` + evidence + `}`,
		"constraint_reference": `{"id":"FIELD-CONSTRAINT","kind":"constraint_reference","source_ref":"ADR-0037","scope":"core/artifacts","status":"existing_applicable",` + evidence + `}`,
	}
	binding := `{"source_snapshot_id":"` + strings.Repeat("a", 64) + `","runtime_ref":"go1.27.1/windows-amd64","lock_digest":"` + strings.Repeat("b", 64) + `","prerequisites_digest":"` + strings.Repeat("c", 64) + `","oracle_ref":"TestContextDocumentContract","argv":["go","test","./..."],"cwd":"core/artifacts","declared_prerequisites":["Go 1.27.1"],"environment_digest":"` + strings.Repeat("d", 64) + `"}`
	bound := strings.Replace(entry["command"], `"state":"declared","observation_ref":null,"binding":null`, `"state":"passed","observation_ref":"OBS-001","binding":`+binding, 1)
	document := func(id, record string) []byte {
		return []byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"` + id + `","entries":[` + record + `]}`)
	}

	t.Run("valid_typed_five_documents", func(t *testing.T) {
		cases := map[string]struct{ target, record string }{
			"CONTEXT":           {".codearbiter/CONTEXT.md", entry["identity"]},
			"tech-stack":        {".codearbiter/tech-stack.md", entry["command"]},
			"coding-standards":  {".codearbiter/coding-standards.md", entry["fact"]},
			"security-controls": {".codearbiter/security-controls.md", entry["constraint_reference"]},
			"code-map":          {".codearbiter/code-map.md", entry["map_entry"]},
		}
		for id, tc := range cases {
			doc, err := Validate(document(id, tc.record))
			if err != nil || doc.DocumentID != id || doc.TargetPath != tc.target || len(doc.Entries) != 1 {
				t.Errorf("%s: document=%+v error=%v", id, doc, err)
			}
		}
		if _, err := Validate(document("tech-stack", entry["source_relationship"])); err != nil {
			t.Errorf("source relationship rejected: %v", err)
		}
		unicodeBoundary := strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"`+strings.Repeat("é", 512)+`"`, 1)
		if _, err := Validate(document("CONTEXT", unicodeBoundary)); err != nil {
			t.Errorf("512-codepoint factual value rejected: %v", err)
		}
	})

	t.Run("unknown_document_and_payload", func(t *testing.T) {
		for _, candidate := range [][]byte{
			document("open-tasks", entry["identity"]),
			[]byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"CONTEXT","body":"# rewrite","entries":[]}`),
			[]byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"CONTEXT","sections":[{"name":"anything","body":"replace"}],"entries":[]}`),
			[]byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"CONTEXT","document_id":"code-map","entries":[]}`),
		} {
			if _, err := Validate(candidate); err == nil {
				t.Errorf("unsafe document accepted: %s", candidate)
			}
		}
	})

	t.Run("unrecognized_fields_and_normative_claim", func(t *testing.T) {
		for _, candidate := range []string{
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"Arbiter","section":"Anything"`, 1),
			strings.Replace(entry["identity"], `"id":"FIELD-NAME"`, `"id":"CLAIM-NAME"`, 1),
			strings.Replace(entry["fact"], `"id":"CLAIM-RUNTIME"`, `"id":"FIELD-RUNTIME"`, 1),
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"# Whole document\nreplacement"`, 1),
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"Arbiter","approval":"approved"`, 1),
			strings.Replace(entry["fact"], `"state":"observed"`, `"state":"approved"`, 1),
			strings.Replace(entry["constraint_reference"], `"status":"existing_applicable"`, `"status":"existing_applicable","statement":"New rule"`, 1),
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"`+strings.Repeat("x", 513)+`"`, 1),
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"`+strings.Repeat("é", 513)+`"`, 1),
		} {
			id := "CONTEXT"
			if strings.Contains(candidate, `"kind":"constraint_reference"`) {
				id = "security-controls"
			}
			if _, err := Validate(document(id, candidate)); err == nil {
				t.Errorf("unsupported claim accepted: %s", candidate)
			}
		}
	})

	t.Run("command_state_and_invocation", func(t *testing.T) {
		doc, err := Validate(document("tech-stack", bound))
		if err != nil || doc.Entries[0].Command.Verification.State != "passed" || doc.Entries[0].Command.Verification.ObservationRef != "OBS-001" {
			t.Errorf("historical observation-bound pass rejected: %v", err)
		}
		failed := strings.Replace(bound, `"state":"passed"`, `"state":"failed"`, 1)
		if _, err := Validate(document("tech-stack", failed)); err != nil {
			t.Errorf("historical observation-bound failure rejected: %v", err)
		}
		for _, candidate := range []string{
			strings.Replace(entry["command"], `"state":"declared"`, `"state":"passed"`, 1),
			strings.Replace(bound, `"go","test","./..."],"cwd":"core/artifacts","declared_prerequisites"`, `"go","test","./other"],"cwd":"core/artifacts","declared_prerequisites"`, 1),
			strings.Replace(bound, `"declared_prerequisites":["Go 1.27.1"]`, `"declared_prerequisites":["other"]`, 1),
			strings.Replace(entry["command"], `"go","test"`, `"sh","-c"`, 1),
			strings.Replace(entry["command"], `"go","test"`, `"env.exe","go"`, 1),
			strings.Replace(entry["command"], `"go","test"`, `"go test","./..."`, 1),
			strings.Replace(entry["command"], `"go","test"`, `"go","&&"`, 1),
			strings.Replace(entry["command"], `"cwd":"core/artifacts"`, `"cwd":"../outside"`, 1),
			strings.Replace(entry["command"], `"cwd":"core/artifacts"`, `"cwd":"CON"`, 1),
			strings.Replace(entry["command"], `"kind":"literal_argv","argv":["go","test","./..."]`, `"kind":"declaration_ref","argv":["go","test"]`, 1),
		} {
			if _, err := Validate(document("tech-stack", candidate)); err == nil {
				t.Errorf("unsafe command accepted: %s", candidate)
			}
		}
		declaration := `{"id":"FIELD-CI","kind":"command","invocation":{"kind":"declaration_ref","path":"package.json","selector":"scripts.test","text":"npm run test | tee log"},"cwd":"site","prerequisites":[],"verification":{"state":"unknown","observation_ref":null,"binding":null},` + evidence + `}`
		if _, err := Validate(document("tech-stack", declaration)); err != nil {
			t.Errorf("inert declaration rejected: %v", err)
		}
	})

	t.Run("document_entry_scope", func(t *testing.T) {
		if _, err := Validate(document("code-map", entry["command"])); err == nil {
			t.Fatal("command accepted in code-map")
		}
		if _, err := Validate(document("tech-stack", entry["map_entry"])); err == nil {
			t.Fatal("map entry accepted in tech-stack")
		}
		if _, err := Validate(document("CONTEXT", entry["identity"]+","+entry["identity"])); err == nil {
			t.Fatal("duplicate field ID accepted")
		}
	})

	t.Run("canonical_schema_and_disabled_kind", func(t *testing.T) {
		contract, ok := kind.Lookup("context")
		codec := kind.Codecs()["context"]
		if !ok || contract.Schema != "context" || contract.Directory != ".codearbiter" ||
			!codec.Optional || codec.Representation != kind.Markdown || codec.Extension != ".md" {
			t.Fatal("context kind is not registered as optional Markdown")
		}
		if _, err := schema.Get("context", ""); err != nil {
			t.Fatalf("packaged context schema unavailable: %v", err)
		}
		canonicalSchema := filepath.Join("..", "..", "schemas", "context.schema.json")
		embeddedSchema := filepath.Join("..", "schema", "context.schema.json")
		original, err := os.ReadFile(canonicalSchema)
		if err != nil {
			t.Fatal(err)
		}
		copyBytes, err := os.ReadFile(embeddedSchema)
		if err != nil || string(original) != string(copyBytes) {
			t.Fatalf("generated schema parity: %v", err)
		}
		model, err := canonical.Decode(original)
		if err != nil {
			t.Fatal(err)
		}
		positives := map[string]string{
			"CONTEXT":           entry["identity"],
			"tech-stack":        entry["command"],
			"coding-standards":  entry["fact"],
			"security-controls": entry["constraint_reference"],
			"code-map":          entry["map_entry"],
		}
		for id, candidate := range positives {
			valid, err := canonical.Decode(document(id, candidate))
			if err != nil {
				t.Fatal(err)
			}
			if issues := schema.ValidateWith(model, valid); len(issues) != 0 {
				t.Errorf("schema rejected %s: %v", id, issues)
			}
		}
		unicodeBoundary := strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"`+strings.Repeat("é", 512)+`"`, 1)
		unicodeValid, err := canonical.Decode(document("CONTEXT", unicodeBoundary))
		if err != nil {
			t.Fatal(err)
		}
		if issues := schema.ValidateWith(model, unicodeValid); len(issues) != 0 {
			t.Fatalf("schema rejected 512-codepoint value: %v", issues)
		}
		for _, candidate := range []struct{ id, entry string }{
			{"tech-stack", entry["source_relationship"]},
			{"tech-stack", bound},
			{"tech-stack", `{"id":"FIELD-CI","kind":"command","invocation":{"kind":"declaration_ref","path":"package.json","selector":"scripts.test","text":"npm run test | tee log"},"cwd":"site","prerequisites":[],"verification":{"state":"unknown","observation_ref":null,"binding":null},` + evidence + `}`},
		} {
			valid, err := canonical.Decode(document(candidate.id, candidate.entry))
			if err != nil {
				t.Fatal(err)
			}
			if issues := schema.ValidateWith(model, valid); len(issues) != 0 {
				t.Errorf("schema rejected valid variant: %v", issues)
			}
		}
		negativeEntries := []string{
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"Arbiter","section":"Anything"`, 1),
			strings.Replace(entry["identity"], `"id":"FIELD-NAME"`, `"id":"CLAIM-NAME"`, 1),
			strings.Replace(entry["identity"], `"value":"Arbiter"`, `"value":"`+strings.Repeat("é", 513)+`"`, 1),
			strings.Replace(entry["fact"], `"state":"observed"`, `"state":"approved"`, 1),
			strings.Replace(entry["command"], `"state":"declared"`, `"state":"passed"`, 1),
			strings.Replace(bound, `"observation_ref":"OBS-001"`, `"observation_ref":null`, 1),
			strings.Replace(bound, `"lock_digest":"`+strings.Repeat("b", 64)+`"`, `"lock_digest":"bad"`, 1),
			strings.Replace(entry["command"], `"prerequisites":["Go 1.27.1"]`, `"prerequisites":"Go 1.27.1"`, 1),
			strings.Replace(entry["command"], `"kind":"literal_argv","argv":["go","test","./..."]`, `"kind":"declaration_ref","argv":["go","test"]`, 1),
			strings.Replace(entry["constraint_reference"], `"status":"existing_applicable"`, `"status":"existing_applicable","statement":"New rule"`, 1),
			strings.Replace(entry["map_entry"], `"paths":["core/artifacts"]`, `"paths":"core/artifacts"`, 1),
			strings.Replace(entry["source_relationship"], `"relation":"derived_from"`, `"relation":"approves"`, 1),
		}
		for _, candidate := range negativeEntries {
			id := "CONTEXT"
			switch {
			case strings.Contains(candidate, `"kind":"command"`):
				id = "tech-stack"
			case strings.Contains(candidate, `"kind":"constraint_reference"`):
				id = "security-controls"
			case strings.Contains(candidate, `"kind":"map_entry"`):
				id = "code-map"
			}
			invalid, err := canonical.Decode(document(id, candidate))
			if err != nil {
				t.Fatal(err)
			}
			if issues := schema.ValidateWith(model, invalid); len(issues) == 0 {
				t.Errorf("schema accepted unsupported variant: %s", candidate)
			}
		}
		// Document-specific kind scope, path safety, shell semantics and duplicate
		// entry IDs are cross-field checks in Validate, beyond this inactive schema.
		unsafePath := strings.Replace(entry["command"], `"cwd":"core/artifacts"`, `"cwd":"CON"`, 1)
		structurallyValid, err := canonical.Decode(document("tech-stack", unsafePath))
		if err != nil {
			t.Fatal(err)
		}
		if issues := schema.ValidateWith(model, structurallyValid); len(issues) != 0 {
			t.Fatalf("schema unexpectedly owns portable path semantics: %v", issues)
		}
		if _, err := Validate(document("tech-stack", unsafePath)); err == nil {
			t.Fatal("runtime accepted reserved cwd")
		}
	})
}
