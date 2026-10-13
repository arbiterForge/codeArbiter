package contextdocument

import (
	"bytes"
	"fmt"
	"strings"
	"testing"
)

func TestContextBoundedRender(t *testing.T) {
	const evidence = `"evidence_refs":["SRC-1"]`
	document := func(id, entries string) []byte {
		return []byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"` + id + `","entries":[` + entries + `]}`)
	}
	identity := `{"id":"FIELD-NAME","kind":"identity","field":"project_name","value":"New Name",` + evidence + `}`
	mapEntry := `{"id":"FIELD-MAP","kind":"map_entry","concern":"Modules","paths":["core/artifacts"],"role":"new owner","consumer_ref":"core/artifacts",` + evidence + `}`
	command := `{"id":"FIELD-TEST","kind":"command","invocation":{"kind":"literal_argv","argv":["go","test","./..."]},"cwd":".","prerequisites":[],"verification":{"state":"declared","observation_ref":null,"binding":null},` + evidence + `}`
	declaration := `{"id":"FIELD-CI","kind":"command","invocation":{"kind":"declaration_ref","path":"package.json","selector":"scripts.test","text":"npm test | tee log"},"cwd":"site","prerequisites":[],"verification":{"state":"unknown","observation_ref":null,"binding":null},` + evidence + `}`
	fact := `{"id":"CLAIM-FACT","kind":"fact","field":"coding_pattern","value":"UTF-8 everywhere","state":"observed","source_ref":"README.md","consumer_ref":"core/artifacts",` + evidence + `}`
	securityFact := `{"id":"CLAIM-SEC","kind":"fact","field":"security_observation","value":"SHA-256 observed","state":"observed","source_ref":"README.md","consumer_ref":"core/artifacts",` + evidence + `}`

	t.Run("legacy_exact_bytes_and_determinism", func(t *testing.T) {
		source := []byte("---\r\nstage: 2\r\n---\r\n# Project: Old Name\r\n\r\nHuman note.\r\n")
		original := bytes.Clone(source)
		selection := []PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}}
		first, err := RenderPreview(document("CONTEXT", identity), source, true, selection)
		if err != nil {
			t.Fatal(err)
		}
		second, err := RenderPreview(document("CONTEXT", identity), source, true, selection)
		if err != nil {
			t.Fatal(err)
		}
		want := []byte("---\r\nstage: 2\r\n---\r\n# Project: New Name\r\n\r\nHuman note.\r\n")
		if !bytes.Equal(first.Bytes, want) || !bytes.Equal(second.Bytes, want) || !bytes.Equal(source, original) {
			t.Fatalf("preview changed neighboring/source bytes: %q / %q", first.Bytes, source)
		}
		if len(first.Changes) != 1 || len(second.Changes) != 1 || first.Changes[0] != second.Changes[0] || first.Changes[0].Old != "Old Name" || first.Changes[0].New != "New Name" {
			t.Fatalf("semantic/byte change missing or unstable: %+v / %+v", first.Changes, second.Changes)
		}
		if first.TargetPath != ".codearbiter/CONTEXT.md" || first.BeforeSHA256 == first.AfterSHA256 {
			t.Fatalf("target or digest incorrect: %+v", first)
		}
	})

	t.Run("bounded_map_role_and_limits", func(t *testing.T) {
		created, err := RenderPreview(document("code-map", mapEntry), nil, false, nil)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Contains(created.Bytes, []byte("- **Modules**: `core/artifacts` — new owner")) || bytes.Contains(created.Bytes, []byte(`"MapEntry":`)) {
			t.Fatalf("created map is not a concern/path/role index: %s", created.Bytes)
		}
		secondEntry := strings.ReplaceAll(strings.ReplaceAll(mapEntry, "FIELD-MAP", "FIELD-OTHER"), "core/artifacts", "core/pysrc")
		grouped, err := RenderPreview(document("code-map", mapEntry+","+secondEntry), nil, false, nil)
		if err != nil || !bytes.Contains(grouped.Bytes, []byte("- **Modules**: `core/artifacts` — new owner")) || !bytes.Contains(grouped.Bytes, []byte("- **Modules**: `core/pysrc` — new owner")) {
			t.Fatalf("same-concern entries were not retained: %s / %v", grouped.Bytes, err)
		}
		source := []byte("# Code map\n## Modules\n- `core/artifacts` — old owner\n\nHuman tail.\n")
		selection := []PreviewSelection{{EntryID: "FIELD-MAP", Anchor: "map:Modules:core/artifacts"}}
		preview, err := RenderPreview(document("code-map", mapEntry), source, true, selection)
		if err != nil {
			t.Fatal(err)
		}
		if string(preview.Bytes) != "# Code map\n## Modules\n- `core/artifacts` — new owner\n\nHuman tail.\n" {
			t.Fatalf("unexpected map edit: %q", preview.Bytes)
		}
		oversize := append(bytes.Clone(source), bytes.Repeat([]byte("x"), 20*1024)...)
		if _, err := RenderPreview(document("code-map", mapEntry), oversize, true, selection); err == nil {
			t.Fatal("oversized existing map accepted")
		}
		many := make([]string, 51)
		for i := range many {
			many[i] = fmt.Sprintf(`{"id":"FIELD-MAP-%d","kind":"map_entry","concern":"Module %d","paths":["core/artifacts"],"role":"owner","consumer_ref":"core/artifacts",%s}`, i, i, evidence)
		}
		tooMany := document("code-map", strings.Join(many, ","))
		if _, err := RenderPreview(tooMany, nil, false, nil); err == nil {
			t.Fatal("more than 50 map entries accepted")
		}
	})

	t.Run("duplicate_singular_identity_rejected", func(t *testing.T) {
		duplicate := strings.ReplaceAll(strings.ReplaceAll(identity, "FIELD-NAME", "FIELD-OTHER"), "New Name", "Conflicting Name")
		if _, err := RenderPreview(document("CONTEXT", identity+","+duplicate), nil, false, nil); err == nil {
			t.Fatal("duplicate project_name silently dropped during creation")
		}
	})

	t.Run("command_state_and_root_cwd", func(t *testing.T) {
		source := []byte("# Tech stack\n## Test\n```sh\nold command\n```\nHuman tail.\n")
		preview, err := RenderPreview(document("tech-stack", command), source, true, []PreviewSelection{{EntryID: "FIELD-TEST", Anchor: "test_command:1"}})
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Contains(preview.Bytes, []byte("go test ./...")) || !bytes.Contains(preview.Bytes, []byte("state=declared")) || !bytes.Contains(preview.Bytes, []byte("cwd=.")) || !bytes.HasSuffix(preview.Bytes, []byte("```\nHuman tail.\n")) {
			t.Fatalf("command rendering lost state/cwd/human tail: %q", preview.Bytes)
		}
	})

	t.Run("managed_declaration_stays_inert_and_preserves_human_bytes", func(t *testing.T) {
		created, err := RenderPreview(document("tech-stack", declaration), nil, false, nil)
		if err != nil {
			t.Fatal(err)
		}
		source := append(bytes.Clone(created.Bytes), []byte("Human tail.\r\n")...)
		updated := strings.Replace(declaration, "npm test | tee log", "npm run test | tee log", 1)
		preview, err := RenderPreview(document("tech-stack", updated), source, true, []PreviewSelection{{EntryID: "FIELD-CI", Anchor: "entry:FIELD-CI"}})
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Contains(preview.Bytes, []byte("npm run test | tee log")) || !bytes.Contains(preview.Bytes, []byte("\"State\":\"unknown\"")) || !bytes.HasSuffix(preview.Bytes, []byte("Human tail.\r\n")) {
			t.Fatalf("declaration or human bytes lost: %q", preview.Bytes)
		}
		legacy := []byte("# Tech stack\n## Test\n```sh\nold command\n```\n")
		if _, err := RenderPreview(document("tech-stack", declaration), legacy, true, []PreviewSelection{{EntryID: "FIELD-CI", Anchor: "test_command:1"}}); err == nil {
			t.Fatal("inert declaration converted to a legacy executable command")
		}
	})

	t.Run("missing_template_is_parseable_and_present_empty_rejects", func(t *testing.T) {
		for _, tc := range []struct{ id, entry string }{{"CONTEXT", identity}, {"tech-stack", command}, {"coding-standards", fact}, {"security-controls", securityFact}, {"code-map", mapEntry}} {
			preview, err := RenderPreview(document(tc.id, tc.entry), nil, false, nil)
			if err != nil {
				t.Fatalf("%s: %v", tc.id, err)
			}
			if _, err := ParseMarkdown(tc.id, preview.Bytes); err != nil {
				t.Fatalf("%s template unparsable: %v", tc.id, err)
			}
			if len(preview.Changes) != 1 || preview.Changes[0].Old != "" || len(preview.Bytes) == 0 {
				t.Fatalf("%s: missing creation diff", tc.id)
			}
		}
		if _, err := RenderPreview(document("CONTEXT", identity), nil, true, []PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}}); err == nil {
			t.Fatal("present empty file treated as absent")
		}
	})

	t.Run("selection_cannot_forge_span_or_ownership", func(t *testing.T) {
		source := []byte("---\n---\n# Project: Old Name\nHuman text.\n")
		for _, selection := range [][]PreviewSelection{
			{{EntryID: "FIELD-NAME", Anchor: "Human text."}},
			{{EntryID: "FIELD-NAME", Anchor: "project_name"}, {EntryID: "FIELD-NAME", Anchor: "project_name"}},
			nil,
		} {
			if _, err := RenderPreview(document("CONTEXT", identity), source, true, selection); err == nil {
				t.Fatalf("invalid selection accepted: %+v", selection)
			}
		}
		if _, err := RenderPreview([]byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"CONTEXT","entries":[{"id":"FIELD-NAME","kind":"identity","field":"project_name","value":"bad","evidence_refs":["SRC-1"],"target_path":"open-tasks.md"}]}`), source, true, []PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}}); err == nil {
			t.Fatal("raw typed payload bypassed validation")
		}
	})
}
