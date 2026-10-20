package operations

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func ordinaryContextPreview(t *testing.T, root string, request object) object {
	t.Helper()
	v, err := Run(root, "context-preview", request)
	if err != nil {
		t.Fatalf("ordinary context preview: %v", err)
	}
	p := model.M(v)
	if p["evidence_assessed"] != false {
		t.Fatalf("preview claims assessed evidence: %v", p)
	}
	return object{"protocol": Protocol, "preview_ref": p["preview_ref"], "preview_sha256": p["preview_sha256"]}
}

func wholeDocumentRequest(t *testing.T, root string, r object, id, mode string, before, prior, after []byte) object {
	t.Helper()
	r["mode"], r["document_id"], r["target_path"] = mode, id, ".codearbiter/"+id+".md"
	r["typed"] = object{"format": contextdocument.Format, "document_id": id, "entries": []any{object{"id": "FIELD-DOCUMENT", "kind": "document", "markdown": string(after), "evidence_refs": []any{"CLAIM-DOCUMENT"}}}}
	r["selections"] = []any{object{"entry_id": "FIELD-DOCUMENT", "anchor": "document"}}
	r["expected_document_sha256"], r["expected_provenance_sha256"] = nil, nil
	if before != nil {
		r["expected_document_sha256"] = canonical.BytesHash(before)
	}
	if prior != nil {
		r["expected_provenance_sha256"] = canonical.BytesHash(prior)
	}
	p := model.M(r["proposed_provenance"])
	p["doc"] = id
	model.M(p["document"])["path"], model.M(p["document"])["digest"] = r["target_path"], canonical.BytesHash(after)
	field := model.M(model.A(p["fields"])[0])
	field["id"], field["owner_ref"] = "FIELD-DOCUMENT", "document"
	claim := model.M(model.A(field["claims"])[0])
	claim["id"] = "CLAIM-DOCUMENT"
	claim["semantic_review"] = object{"state": "unreviewed", "reference": nil}
	p["fields"] = []any{field}
	return r
}

func TestContextWholeDocumentCreateAdoptUpdate(t *testing.T) {
	for id, title := range map[string]string{"CONTEXT": "Project: Fixture", "tech-stack": "Tech stack", "coding-standards": "Coding standards", "security-controls": "Security controls", "code-map": "Code map"} {
		for _, mode := range []string{"create", "adopt", "v1", "v2"} {
			t.Run(id+"/"+mode, func(t *testing.T) {
				root, r := contextFixture(t)
				after := []byte("# " + title + "\n\nCurrent documented facts.\n")
				var before, prior []byte
				if mode != "create" {
					before = []byte("# Legacy custom heading\n\n" + strings.Repeat("Human historical content.\n", 54))
				}
				if id == "CONTEXT" {
					prefix := "---\narbiter: enabled\nmode: arbiter\nstage: 2\n---\n"
					if mode != "create" {
						prefix += "<!--INITIALIZED-->\n"
						before = append([]byte(prefix), before...)
					}
					after = append([]byte(prefix), after...)
				}
				if mode == "v1" {
					prior, _ = canonical.Marshal(object{"schema": int64(1), "doc": id, "entries": []any{object{"claim": "Historical only"}}})
				}
				if mode == "v2" {
					p := model.M(r["proposed_provenance"])
					p["doc"] = id
					model.M(p["document"])["path"] = ".codearbiter/" + id + ".md"
					model.M(p["document"])["digest"] = canonical.BytesHash(before)
					prior, _ = canonical.Marshal(p)
				}
				for path, body := range map[string][]byte{".codearbiter/" + id + ".md": before, ".codearbiter/.provenance/" + id + ".json": prior} {
					if body != nil {
						full := filepath.Join(root, filepath.FromSlash(path))
						if err := os.MkdirAll(filepath.Dir(full), 0755); err != nil {
							t.Fatal(err)
						}
						if err := os.WriteFile(full, body, 0644); err != nil {
							t.Fatal(err)
						}
					}
				}
				writeMode := mode
				if mode == "v1" {
					writeMode = "adopt"
				}
				if mode == "v2" {
					writeMode = "update"
				}
				r = wholeDocumentRequest(t, root, r, id, writeMode, before, prior, after)
				apply := ordinaryContextPreview(t, root, r)
				if _, err := Run(root, "context-apply", apply); err != nil {
					t.Fatal(err)
				}
				if !bytes.Equal(mustReadRefresh(t, filepath.Join(root, ".codearbiter", id+".md")), after) {
					t.Fatal("selected document bytes differ")
				}
				prov := mustReadRefresh(t, filepath.Join(root, ".codearbiter", ".provenance", id+".json"))
				r["operation_id"] = "context-update-whole-0002"
				r = wholeDocumentRequest(t, root, r, id, "update", after, prov, append(bytes.Clone(after), []byte("More current facts.\n")...))
				if _, err := Run(root, "context-apply", ordinaryContextPreview(t, root, r)); err != nil {
					t.Fatalf("whole ownership update: %v", err)
				}
			})
		}
	}
}

func TestContextWholeDocumentLargePreviewIsBounded(t *testing.T) {
	root, r := contextFixture(t)
	before := []byte("# Old security policy\n" + strings.Repeat("Historical text.\n", 5000))
	after := []byte("# Security controls\n" + strings.Repeat("Current text.\n", 6000))
	if err := os.WriteFile(filepath.Join(root, ".codearbiter", "security-controls.md"), before, 0644); err != nil {
		t.Fatal(err)
	}
	r = wholeDocumentRequest(t, root, r, "security-controls", "adopt", before, nil, after)
	v, err := Run(root, "context-preview", r)
	if err != nil {
		t.Fatal(err)
	}
	p := model.M(v)
	raw, _ := canonical.Marshal(p)
	if len(raw) > 65536 || p["preview_content_omitted"] != true || p["preview_document"] != nil {
		t.Fatalf("unbounded/implicit preview truncation: %d bytes", len(raw))
	}
	change := model.M(model.A(p["changes"])[0])
	if change["content_omitted"] != true || change["old_sha256"] != canonical.BytesHash(before) || change["new_sha256"] != canonical.BytesHash(after) {
		t.Fatal("large diff lost exact identity")
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "preview_ref": p["preview_ref"], "preview_sha256": p["preview_sha256"]}); err != nil {
		t.Fatal(err)
	}
}

func TestContextOrdinaryFinalization(t *testing.T) {
	root, r := finalizationOperationsFixture(t)
	v, err := Run(root, "context-finalize-preview", r)
	if err != nil {
		t.Fatal(err)
	}
	p := model.M(v)
	apply := object{"protocol": Protocol, "preview_ref": p["preview_ref"], "preview_sha256": p["preview_sha256"]}
	if _, err := Run(root, "context-apply", apply); err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(mustReadRefresh(t, filepath.Join(root, ".codearbiter", "CONTEXT.md")), []byte("<!--INITIALIZED-->")) {
		t.Fatal("initialization marker missing")
	}
	if _, err := Run(root, "context-apply", apply); err != nil {
		t.Fatalf("finalization replay: %v", err)
	}
}

func TestContextWholeDocumentOnboardingFinalization(t *testing.T) {
	root, request := contextFixture(t)
	before := map[string][]byte{}
	expected := object{}
	remember := func(path string) {
		t.Helper()
		body := mustReadRefresh(t, filepath.Join(root, filepath.FromSlash(path)))
		before[path], expected[path] = body, canonical.BytesHash(body)
	}
	for _, item := range []struct{ id, title string }{
		{"CONTEXT", "Project: Whole document fixture"},
		{"tech-stack", "Tech stack"},
		{"coding-standards", "Coding standards"},
		{"security-controls", "Security controls"},
		{"code-map", "Code map"},
	} {
		body := []byte("# " + item.title + "\n\n## Existing human layout\n\nObserved source facts.\n")
		if item.id == "CONTEXT" {
			body = append([]byte("---\narbiter: enabled\nstage: 2\n---\n"), body...)
		}
		request["operation_id"] = "onboarding-create-" + item.id
		request = wholeDocumentRequest(t, root, request, item.id, "create", nil, nil, body)
		if _, err := Run(root, "context-apply", ordinaryContextPreview(t, root, request)); err != nil {
			t.Fatal(err)
		}
		remember(".codearbiter/" + item.id + ".md")
		remember(".codearbiter/.provenance/" + item.id + ".json")
	}
	for path, body := range map[string]string{
		".codearbiter/open-tasks.md":     "# Open tasks\n",
		".codearbiter/open-questions.md": "# Open questions\n\n_None open._\n",
		".codearbiter/overrides.log":     "# codeArbiter override log - append-only audit artifact. Never edit or delete prior lines.\n",
	} {
		if err := os.WriteFile(filepath.Join(root, filepath.FromSlash(path)), []byte(body), 0644); err != nil {
			t.Fatal(err)
		}
		remember(path)
	}
	if len(expected) != 13 {
		t.Fatal("onboarding fixture must bind exactly thirteen outputs")
	}
	request = object{"protocol": Protocol, "operation_id": "onboarding-finalize-0001", "mode": "finalize",
		"document_id": "CONTEXT", "target_path": ".codearbiter/CONTEXT.md", "expected": expected}
	v, err := Run(root, "context-finalize-preview", request)
	if err != nil {
		t.Fatal(err)
	}
	p := model.M(v)
	if p["evidence_assessed"] != false {
		t.Fatal("finalization preview claimed assessed evidence")
	}
	apply := object{"protocol": Protocol, "preview_ref": p["preview_ref"], "preview_sha256": p["preview_sha256"]}
	for _, path := range []string{".codearbiter/open-tasks.md", ".codearbiter/.provenance/code-map.json"} {
		full := filepath.Join(root, filepath.FromSlash(path))
		if err := os.Remove(full); err != nil {
			t.Fatal(err)
		}
		if _, err := Run(root, "context-apply", apply); fault.Code(err) != "INVALID_CONTEXT_OUTPUT" {
			t.Fatalf("missing output %s accepted: %v", path, err)
		}
		if err := os.WriteFile(full, before[path], 0644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("source drift\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "context-apply", apply); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("stale source evidence accepted: %v", err)
	}
	for path, body := range before {
		if !bytes.Equal(mustReadRefresh(t, filepath.Join(root, filepath.FromSlash(path))), body) {
			t.Fatalf("preview or failed finalization changed %s", path)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("observed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	v, err = Run(root, "context-apply", apply)
	if err != nil || model.M(v)["transaction"].(store.Outcome).Replay {
		t.Fatalf("whole-document finalization: %v / %v", v, err)
	}
	after := map[string][]byte{}
	for path, body := range before {
		actual := mustReadRefresh(t, filepath.Join(root, filepath.FromSlash(path)))
		after[path] = actual
		switch path {
		case ".codearbiter/CONTEXT.md":
			if bytes.Count(actual, []byte("<!--INITIALIZED-->\n")) != 1 || !bytes.Equal(bytes.Replace(actual, []byte("<!--INITIALIZED-->\n"), nil, 1), body) {
				t.Fatal("finalization changed more than the initialization marker")
			}
		case ".codearbiter/.provenance/CONTEXT.json":
			prior, err := canonical.Object(body)
			if err != nil {
				t.Fatal(err)
			}
			model.M(prior["document"])["digest"] = p["after_document_sha256"]
			want, err := canonical.Marshal(prior)
			if err != nil || !bytes.Equal(actual, want) {
				t.Fatal("finalization changed provenance beyond the paired document digest")
			}
		default:
			if !bytes.Equal(actual, body) {
				t.Fatalf("finalization changed independent output %s", path)
			}
		}
	}
	for _, dir := range []string{"receipts", "authority-sources", "observations"} {
		if _, err := os.Stat(filepath.Join(root, ".codearbiter", ".artifacts", dir)); !os.IsNotExist(err) {
			t.Fatalf("onboarding fabricated %s", dir)
		}
	}
	v, err = Run(root, "context-apply", apply)
	if err != nil || !model.M(v)["transaction"].(store.Outcome).Replay {
		t.Fatalf("finalization replay: %v / %v", v, err)
	}
	for path, body := range after {
		if !bytes.Equal(mustReadRefresh(t, filepath.Join(root, filepath.FromSlash(path))), body) {
			t.Fatalf("replay changed %s", path)
		}
		expected[path] = canonical.BytesHash(body)
	}
	request["operation_id"] = "onboarding-finalize-0002"
	if _, err := Run(root, "context-finalize-preview", request); fault.Code(err) != "ALREADY_INITIALIZED" {
		t.Fatalf("second initialization accepted: %v", err)
	}
}

func TestContextOrdinaryCreateReplayAndIntegrity(t *testing.T) {
	root, request := contextFixture(t)
	claim := model.M(model.A(model.M(model.A(model.M(request["proposed_provenance"])["fields"])[0])["claims"])[0])
	claim["semantic_review"] = object{"state": "unreviewed", "reference": nil}
	apply := ordinaryContextPreview(t, root, request)
	if _, err := os.Stat(filepath.Join(root, ".codearbiter", "CONTEXT.md")); !os.IsNotExist(err) {
		t.Fatal("preview wrote canonical context")
	}
	bad := object{"protocol": Protocol, "preview_ref": apply["preview_ref"], "preview_sha256": canonical.BytesHash([]byte("wrong"))}
	if _, err := Run(root, "context-apply", bad); err == nil {
		t.Fatal("mismatched preview identity accepted")
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("source drift\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "context-apply", apply); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("stale evidence accepted: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("observed source\n"), 0644); err != nil {
		t.Fatal(err)
	}
	v, err := Run(root, "context-apply", apply)
	if err != nil || v.(map[string]any)["transaction"].(store.Outcome).Replay {
		t.Fatalf("ordinary apply: %v / %v", v, err)
	}
	for _, dir := range []string{"receipts", "authority-sources", "observations"} {
		if _, err := os.Stat(filepath.Join(root, ".codearbiter", ".artifacts", dir)); !os.IsNotExist(err) {
			t.Fatalf("ordinary work fabricated %s", dir)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("later drift\n"), 0644); err != nil {
		t.Fatal(err)
	}
	v, err = Run(root, "context-apply", apply)
	if err != nil || !v.(map[string]any)["transaction"].(store.Outcome).Replay {
		t.Fatalf("historical replay lost: %v / %v", v, err)
	}
}

func TestContextOrdinaryAdoptsMissingAndLegacyProvenance(t *testing.T) {
	for _, legacy := range []bool{false, true} {
		t.Run(map[bool]string{false: "missing", true: "v1"}[legacy], func(t *testing.T) {
			root, r := contextFixture(t)
			old := []byte("---\narbiter: enabled\nmode: arbiter\nstage: 2\n---\n<!--INITIALIZED-->\n# Project: Fixture Project\n\n## Human\nKeep these bytes.\n")
			path := filepath.Join(root, ".codearbiter", "CONTEXT.md")
			if err := os.WriteFile(path, old, 0644); err != nil {
				t.Fatal(err)
			}
			r["mode"], r["expected_document_sha256"] = "adopt", canonical.BytesHash(old)
			r["selections"] = []any{object{"entry_id": "FIELD-NAME", "anchor": "project_name"}}
			p := model.M(r["proposed_provenance"])
			model.M(p["document"])["digest"] = canonical.BytesHash(old)
			claim := model.M(model.A(model.M(model.A(p["fields"])[0])["claims"])[0])
			claim["semantic_review"] = object{"state": "unreviewed", "reference": nil}
			var prior []byte
			if legacy {
				prior = []byte(`{"schema":1,"doc":"CONTEXT","created":"2020-01-01","entries":[],"interview_derived":true}`)
				prov := filepath.Join(root, ".codearbiter", ".provenance", "CONTEXT.json")
				if err := os.MkdirAll(filepath.Dir(prov), 0755); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(prov, prior, 0644); err != nil {
					t.Fatal(err)
				}
				r["expected_provenance_sha256"] = canonical.BytesHash(prior)
			}
			apply := ordinaryContextPreview(t, root, r)
			if err := os.WriteFile(path, append(bytes.Clone(old), '\n'), 0644); err != nil {
				t.Fatal(err)
			}
			if _, err := Run(root, "context-apply", apply); fault.Code(err) != "REVISION_CONFLICT" {
				t.Fatalf("changed preimage accepted: %v", err)
			}
			if err := os.WriteFile(path, old, 0644); err != nil {
				t.Fatal(err)
			}
			if _, err := Run(root, "context-apply", apply); err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(mustReadRefresh(t, path), old) {
				t.Fatal("adoption changed initialized/human bytes")
			}
			if legacy {
				backup := filepath.Join(root, ".codearbiter", ".artifacts", "history", "context-fixture-0001-1.before")
				if !bytes.Equal(mustReadRefresh(t, backup), prior) {
					t.Fatal("legacy provenance history lost")
				}
			}
		})
	}
}

func TestContextWholeDocumentSelectionPreservesControls(t *testing.T) {
	old := []byte("---\narbiter: enabled\nmode: arbiter\nstage: 2\n---\n<!--INITIALIZED-->\n# Project: Fixture\n\n## Human\nOld description.\n")
	newDoc := bytes.Replace(old, []byte("Old description."), []byte("Updated description."), 1)
	makeTyped := func(body []byte) []byte {
		b, _ := canonical.Marshal(object{"format": contextdocument.Format, "document_id": "CONTEXT", "entries": []any{object{"id": "FIELD-DOCUMENT", "kind": "document", "markdown": string(body), "evidence_refs": []any{"CLAIM-DOCUMENT"}}}})
		return b
	}
	selection := []contextdocument.PreviewSelection{{EntryID: "FIELD-DOCUMENT", Anchor: "document"}}
	p, err := contextdocument.RenderPreview(makeTyped(newDoc), old, true, selection)
	if err != nil || !bytes.Equal(p.Bytes, newDoc) || len(p.Changes) != 1 {
		t.Fatalf("explicit whole-document replacement: %v / %v", p, err)
	}
	for _, body := range [][]byte{bytes.Replace(newDoc, []byte("arbiter: enabled"), []byte("arbiter: disabled"), 1), bytes.Replace(newDoc, []byte("<!--INITIALIZED-->\n"), nil, 1)} {
		if _, err := contextdocument.RenderPreview(makeTyped(body), old, true, selection); err == nil {
			t.Fatal("document replacement changed enrollment/initialization")
		}
	}
	if _, err := contextdocument.RenderPreview(makeTyped(bytes.Replace(newDoc, []byte("<!--INITIALIZED-->"), []byte("```\n<!--INITIALIZED-->\n```"), 1)), old, true, selection); err == nil {
		t.Fatal("initialization marker hidden in a code fence")
	}
	if _, err := contextdocument.RenderPreview(makeTyped(newDoc), old, true, nil); err == nil {
		t.Fatal("implicit whole-document replacement accepted")
	}
}

func TestContextOrdinaryRejectsAmbiguousUnsafeOrForgedRequests(t *testing.T) {
	for _, bad := range []string{"target", "selection", "provenance", "v2-adopt", "mixed-apply", "changed-preview"} {
		t.Run(bad, func(t *testing.T) {
			root, r := contextFixture(t)
			if bad == "target" {
				r["target_path"] = "../outside.md"
			}
			if bad == "selection" {
				r["selections"] = []any{object{"entry_id": "FIELD-NAME", "anchor": "document"}}
			}
			if bad == "provenance" {
				model.M(model.M(r["proposed_provenance"])["document"])["digest"] = canonical.BytesHash([]byte("unrelated document"))
			}
			if bad == "v2-adopt" {
				body := []byte("---\n---\n# Project: Fixture Project\n")
				if err := os.WriteFile(filepath.Join(root, ".codearbiter", "CONTEXT.md"), body, 0644); err != nil {
					t.Fatal(err)
				}
				r["mode"], r["expected_document_sha256"] = "adopt", canonical.BytesHash(body)
				r["selections"] = []any{object{"entry_id": "FIELD-NAME", "anchor": "project_name"}}
				prior, _ := canonical.Marshal(r["proposed_provenance"])
				if err := os.MkdirAll(filepath.Join(root, ".codearbiter", ".provenance"), 0755); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(root, ".codearbiter", ".provenance", "CONTEXT.json"), prior, 0644); err != nil {
					t.Fatal(err)
				}
				r["expected_provenance_sha256"] = canonical.BytesHash(prior)
			}
			if bad == "mixed-apply" || bad == "changed-preview" {
				apply := ordinaryContextPreview(t, root, r)
				if bad == "mixed-apply" {
					apply["receipt"] = "invented"
				} else {
					path := filepath.Join(root, filepath.FromSlash(model.S(apply["preview_ref"])))
					raw := mustReadRefresh(t, path)
					if err := os.WriteFile(path, append(raw, ' '), 0600); err != nil {
						t.Fatal(err)
					}
				}
				if _, err := Run(root, "context-apply", apply); err == nil {
					t.Fatal("ambiguous/tampered apply accepted")
				}
			} else if _, err := Run(root, "context-preview", r); err == nil {
				t.Fatal("invalid context preview accepted")
			}
			if bad != "v2-adopt" {
				if _, err := os.Stat(filepath.Join(root, ".codearbiter", "CONTEXT.md")); !os.IsNotExist(err) {
					t.Fatal("refused request mutated canonical context")
				}
			}
		})
	}
}
