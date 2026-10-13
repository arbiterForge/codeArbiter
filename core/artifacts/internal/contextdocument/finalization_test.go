package contextdocument

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func finalizationFixture(t *testing.T) (*store.FS, func(), Finalization) {
	t.Helper()
	f, done := mutationFixture(t, "finalize")
	content := map[string]struct{ body, owner string }{
		"CONTEXT":           {"---\narbiter: enabled\nstage: 1\n---\n\n# Project: Sample\n\n## Human\nKeep these bytes.\n", "project_name"},
		"tech-stack":        {"# Tech stack\n\n<!-- ca:field CLAIM-ONE fact runtime -->\nRuntime: Go\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		"coding-standards":  {"# Coding standards\n\n<!-- ca:field CLAIM-ONE fact coding_pattern -->\nPattern: Go\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		"security-controls": {"# Security controls\n\n<!-- ca:field CLAIM-ONE fact security_observation -->\nNo persistent data domain found in scope.\n<!-- ca:end-field CLAIM-ONE -->\n", "entry:CLAIM-ONE"},
		"code-map":          {"# Code map\n\n## Core\n- `go.mod` — module manifest\n", "map:Core:go.mod"},
	}
	expected := map[string]string{}
	for _, id := range []string{"CONTEXT", "tech-stack", "coding-standards", "security-controls", "code-map"} {
		item := content[id]
		body := []byte(item.body)
		path := ".codearbiter/" + id + ".md"
		if _, err := ParseMarkdown(id, body); err != nil {
			t.Fatalf("fixture %s: %v", id, err)
		}
		mutationWrite(t, f, path, body)
		fieldID, claimID := "FIELD-ONE", "CLAIM-ONE"
		if id == "CONTEXT" {
			fieldID, claimID = "FIELD-NAME", "CLAIM-NAME"
		}
		provenance := mutationProvenanceFor(t, id, body, item.owner, fieldID, claimID)
		provPath := ".codearbiter/.provenance/" + id + ".json"
		mutationWrite(t, f, provPath, provenance)
		expected[path] = canonical.BytesHash(body)
		expected[provPath] = canonical.BytesHash(provenance)
	}
	for path, body := range map[string]string{
		".codearbiter/open-tasks.md":     "# Open tasks\n",
		".codearbiter/open-questions.md": "# Open questions\n\n_None open._\n",
		".codearbiter/overrides.log":     "# codeArbiter override log - append-only audit artifact. Never edit or delete prior lines.\n# Format: [ISO-8601] | BY: <name> <<email>> | GATE: <gate bypassed> | REASON: <reason>\n",
	} {
		mutationWrite(t, f, path, []byte(body))
		expected[path] = canonical.BytesHash([]byte(body))
	}
	return f, done, Finalization{OperationID: "context-final-0001", Expected: expected}
}

func TestContextFinalizationPositiveControls(t *testing.T) {
	f, done, r := finalizationFixture(t)
	defer done()
	before := mutationRead(t, f, ".codearbiter/CONTEXT.md")
	preview, err := PreviewFinalization(f, r)
	if err != nil || len(preview.Binding) != 64 || !bytes.Contains(preview.Document, []byte("<!--INITIALIZED-->")) {
		t.Fatalf("valid empty boards and zero-event audit rejected: %+v %v", preview, err)
	}
	if bytes.Contains(before, []byte("<!--INITIALIZED-->")) || !bytes.Equal(before, mutationRead(t, f, ".codearbiter/CONTEXT.md")) {
		t.Fatal("preview wrote the marker before finalization")
	}
	out, err := Finalize(f, r, verifiedAuthority{binding: preview.Binding})
	if err != nil || out.State != "committed" || len(out.Paths) != 2 {
		t.Fatalf("approved finalization failed: %+v %v", out, err)
	}
	after := mutationRead(t, f, ".codearbiter/CONTEXT.md")
	if !bytes.Contains(after, []byte("<!--INITIALIZED-->")) || !bytes.Contains(after, []byte("Keep these bytes.")) {
		t.Fatalf("marker or human content lost: %q", after)
	}
	var provenance map[string]any
	if err := json.Unmarshal(mutationRead(t, f, ".codearbiter/.provenance/CONTEXT.json"), &provenance); err != nil {
		t.Fatal(err)
	}
	if provenance["document"].(map[string]any)["digest"] != canonical.BytesHash(after) {
		t.Fatal("final marker left document provenance stale")
	}
	for path, expected := range r.Expected {
		if path == ".codearbiter/CONTEXT.md" || path == ".codearbiter/.provenance/CONTEXT.json" {
			continue
		}
		if canonical.BytesHash(mutationRead(t, f, path)) != expected {
			t.Fatalf("finalization changed independently-owned output %s", path)
		}
	}
	if replay, err := Finalize(f, r, verifiedAuthority{binding: preview.Binding}); err != nil || !replay.Replay {
		t.Fatalf("durable replay failed: %+v %v", replay, err)
	}
	t.Run("valid independently owned legacy state", func(t *testing.T) {
		legacy, closeLegacy, request := finalizationFixture(t)
		defer closeLegacy()
		for path, body := range map[string][]byte{
			".codearbiter/open-tasks.md":     []byte("# Open tasks\n\n- [ ] Re-scout provenance before rebaselining.\n- [ ] poc.test.0001 - Check the smoke path\n"),
			".codearbiter/open-questions.md": []byte("# Open questions\n\nUnresolved `[CONFIRM-NN]` items.\n\n- [CONFIRM-01] - Deferred by owner 2026-09-27.\n"),
			".codearbiter/overrides.log":     []byte("# codeArbiter override log — append-only audit artifact. Never edit or delete prior lines.\n2026-06-27T12:48:36Z | BY: owner@example.com | DEV: enter | NOTE: historical\n"),
		} {
			mutationWrite(t, legacy, path, body)
			request.Expected[path] = canonical.BytesHash(body)
		}
		approved, err := PreviewFinalization(legacy, request)
		if err != nil {
			t.Fatalf("valid owner history rejected: %v", err)
		}
		if _, err := Finalize(legacy, request, verifiedAuthority{binding: approved.Binding}); err != nil {
			t.Fatalf("valid owner history could not finalize: %v", err)
		}
		for _, path := range finalizationIndependent {
			if canonical.BytesHash(mutationRead(t, legacy, path)) != request.Expected[path] {
				t.Fatalf("legacy owner state changed at %s", path)
			}
		}
	})
}

func TestContextFinalizationNegativeControls(t *testing.T) {
	for _, altered := range []string{"missing", "malformed", "audit", "content", "raced", "postcheck", "source", "unapproved"} {
		t.Run(altered, func(t *testing.T) {
			f, done, r := finalizationFixture(t)
			defer done()
			preview, err := PreviewFinalization(f, r)
			if err != nil {
				t.Fatal(err)
			}
			if altered == "missing" || altered == "malformed" || altered == "raced" {
				path := ".codearbiter/open-tasks.md"
				body := []byte("# Open tasks\n- [ ] poc.test.0001 - First\n  - Desc: work\n  - Done when: complete\n  - Boundaries: none\n")
				if altered == "missing" {
					path = ".codearbiter/open-questions.md"
					body = nil
				} else if altered == "malformed" {
					body = []byte("# Open tasks\n- [ ] \n")
				}
				if body == nil {
					if err := os.Remove(filepath.Join(f.Root, filepath.FromSlash(path))); err != nil {
						t.Fatal(err)
					}
				} else {
					mutationWrite(t, f, path, body)
					if altered == "malformed" {
						r.Expected[path] = canonical.BytesHash(body)
					}
				}
			}
			if altered == "audit" || altered == "content" {
				path, body := ".codearbiter/overrides.log", []byte("# codeArbiter override log\nnot an event\n")
				if altered == "content" {
					path, body = ".codearbiter/code-map.md", []byte("# Wrong title\n")
				}
				mutationWrite(t, f, path, body)
				r.Expected[path] = canonical.BytesHash(body)
			}
			if altered == "source" {
				mutationWrite(t, f, "go.mod", []byte("source changed\n"))
			}
			if altered == "postcheck" {
				f.Inject = func(step string) error {
					if step == "before-finalize-commit" {
						path := ".codearbiter/CONTEXT.md"
						mutationWrite(t, f, path, append(mutationRead(t, f, path), []byte("Late human edit.\n")...))
					}
					return nil
				}
			}
			var authority VerifiedAuthority = verifiedAuthority{binding: preview.Binding}
			if altered == "unapproved" {
				authority = nil
			}
			if altered == "malformed" || altered == "audit" || altered == "content" {
				if _, err := PreviewFinalization(f, r); fault.Code(err) != "INVALID_CONTEXT_OUTPUT" {
					t.Fatalf("malformed %s output was not validated: %v", altered, err)
				}
				binding, err := finalizationBinding(r)
				if err != nil {
					t.Fatal(err)
				}
				authority = verifiedAuthority{binding: binding}
			}
			if _, err := Finalize(f, r, authority); err == nil || fault.Code(err) == "" {
				t.Fatalf("%s finalization admitted: %v", altered, err)
			}
			if bytes.Contains(mutationRead(t, f, ".codearbiter/CONTEXT.md"), []byte("<!--INITIALIZED-->")) {
				t.Fatal("failure wrote initialized marker")
			}
			if altered == "postcheck" && !bytes.Contains(mutationRead(t, f, ".codearbiter/CONTEXT.md"), []byte("Late human edit.")) {
				t.Fatal("late human edit was not preserved")
			}
		})
	}
}
