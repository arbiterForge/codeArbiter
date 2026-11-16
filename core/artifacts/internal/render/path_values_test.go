package render

import (
	"bytes"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPathValuesRemainVisible(t *testing.T) {
	cases := []struct {
		name  string
		paths []any
		want  []string
		table bool
	}{
		{"knowledge scope strings", []any{"core/pysrc", "dir/<scope>&name.py"}, []string{"core/pysrc", "dir/&lt;scope&gt;&amp;name.py"}, false},
		{"mixed structured paths", []any{"first/string.py", map[string]any{"action": "modify", "path": "second/object.go"}}, []string{"first/string.py", "modify", "second/object.go"}, false},
		{"plan action paths", []any{map[string]any{"action": "modify", "path": "src/object.go"}}, []string{"modify", "src/object.go"}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var w writer
			w.value(tc.paths, "paths")
			view := w.b.String()
			for _, value := range tc.want {
				if !strings.Contains(view, value) {
					t.Errorf("visible path value %q was lost: %s", value, view)
				}
			}
			if strings.Contains(view, "<table>") != tc.table {
				t.Errorf("path table classification differs: %s", view)
			}
			if strings.Contains(view, "<scope>") || strings.Contains(view, "<code></code>") {
				t.Errorf("unsafe or empty path rendering: %s", view)
			}
		})
	}
}

func knowledgePathsFixture(t *testing.T) *model.Document {
	t.Helper()
	empty := func() []any { return []any{} }
	value := map[string]any{
		"format": model.Format, "format_version": model.FormatVersion, "schema_version": model.SchemaVersion,
		"kind": "knowledge", "artifact_id": "CTX-PATH-FIXTURE", "slug": "path-fixture", "revision": int64(1),
		"governance":   map[string]any{"state": "draft", "approvals": empty(), "review_notes": empty()},
		"presentation": Presentation(""),
		"normative": map[string]any{"title": "Path rendering fixture", "summary": "Owned renderer compatibility fixture.",
			"baseline": map[string]any{"repository": nil, "commit": nil, "observed_date": "2026-11-15"},
			"sections": empty(), "sources": empty(), "notes": empty(), "retired_symbols": empty(),
			"records": []any{map[string]any{"id": "COMP-001", "type": "component", "title": "Source paths",
				"statement": "An inert fixture, not production qualification.", "basis": "proposed",
				"scope":        map[string]any{"paths": []any{"core/pysrc", "dir/<scope>&name.py"}},
				"related_refs": empty(), "source_refs": empty()}},
		},
	}
	d, err := Prepare(value)
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func TestKnowledgePathReadKeepsOriginalCanonicalBytes(t *testing.T) {
	path := filepath.Join("..", "..", "testdata", "compat", "knowledge-paths-0.3.2.html")
	original, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if canonical.BytesHash(original) != "d2a65e19f9e1adb0f12a10f9dda79ea8f04d2fa4cea3c8f7caa252b127c076ef" {
		t.Fatal("frozen pre-fix bytes changed")
	}
	d, err := Parse(original)
	if err != nil {
		t.Fatal(err)
	}
	if d.Hash() != knowledgePathsFixture(t).Hash() {
		t.Fatal("read changed model identity")
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(after, original) {
		t.Fatal("read rewrote original bytes", err)
	}
	corrected, err := Render(d)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Equal(corrected, original) {
		t.Fatal("explicit new write retained missing path values")
	}
	// The model container carries paths even under the broken renderer. Inspect
	// only the actual human-readable view when asserting this repair.
	view := bytes.SplitN(corrected, []byte(modelStart), 2)[0]
	if !bytes.Contains(view, []byte("core/pysrc")) || !bytes.Contains(view, []byte("dir/&lt;scope&gt;&amp;name.py")) {
		t.Fatal("new knowledge view still hides scope paths")
	}
	read, err := Parse(corrected)
	if err != nil || read.Hash() != d.Hash() {
		t.Fatal("corrected write changed model identity", err)
	}
}

func TestKnowledgePathProfilesRefuseNoncanonicalBytes(t *testing.T) {
	path := filepath.Join("..", "..", "testdata", "compat", "knowledge-paths-0.3.2.html")
	old, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	corrected, err := Render(knowledgePathsFixture(t))
	if err != nil {
		t.Fatal(err)
	}
	for name, original := range map[string][]byte{"legacy": old, "current": corrected} {
		t.Run(name, func(t *testing.T) {
			cases := map[string][]byte{
				"visible statement": bytes.Replace(original, []byte("An inert fixture, not production qualification."), []byte("Forged visible claim."), 1),
				"stylesheet":        bytes.Replace(original, []byte("</style>"), []byte(".forged{display:none}</style>"), 1),
				"script":            append(bytes.Clone(original), []byte("<script>alert(1)</script>")...),
				"container":         bytes.Replace(original, []byte(modelStart), []byte(modelStart+modelStart), 1),
				"marker":            bytes.Replace(original, []byte("CA:BEGIN:COMP-001"), []byte("CA:BEGIN:COMP-002"), 1),
				"whitespace":        append(bytes.Clone(original), '\n'),
				"model hash":        bytes.Replace(original, []byte(`"revision": 1`), []byte(`"revision": 2`), 1),
			}
			if name == "legacy" {
				cases["changed empty cell"] = bytes.Replace(original, []byte("<code></code>"), []byte("<code>forged</code>"), 1)
			} else {
				cases["partial path rendering"] = bytes.Replace(original, []byte("<li>core/pysrc</li>"), []byte("<li></li>"), 1)
			}
			for mutation, bad := range cases {
				t.Run(mutation, func(t *testing.T) {
					if bytes.Equal(bad, original) {
						t.Fatal("mutation did not reach its intended bytes")
					}
					if _, err := Parse(bad); err == nil {
						t.Fatal("noncanonical view accepted")
					}
				})
			}
		})
	}
}

func TestObjectPathTablesKeepHistoricalGrammar(t *testing.T) {
	original, err := os.ReadFile(filepath.Join("..", "..", "testdata", "compat", "plan-0.3.0.html"))
	if err != nil {
		t.Fatal(err)
	}
	for _, version := range []string{"0.3.0", "0.3.1"} {
		t.Run(version, func(t *testing.T) {
			value, err := DecodeModel(original)
			if err != nil {
				t.Fatal(err)
			}
			value["schema_version"] = version
			d, err := Prepare(value)
			if err != nil {
				t.Fatal(err)
			}
			current, err := renderProfile(d, 0, false)
			if err != nil {
				t.Fatal(err)
			}
			legacy, err := renderProfile(d, 0, true)
			if err != nil || !bytes.Equal(current, legacy) {
				t.Fatal("object path table grammar changed", err)
			}
			got, err := Parse(current)
			if err != nil || got.Hash() != d.Hash() {
				t.Fatal("historical object table no longer reads", err)
			}
		})
	}
}
