package contextdocument

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

func mutationFixture(t *testing.T, name string) (*store.FS, func()) {
	t.Helper()
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, ".codearbiter"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "go.mod"), []byte("source evidence\n"), 0644); err != nil {
		t.Fatal(err)
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	unlock, err := f.Lock(true, 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	return f, func() { unlock(); f.Close() }
}

func mutationTyped(name string) []byte {
	return []byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"CONTEXT","entries":[{"id":"FIELD-NAME","kind":"identity","field":"project_name","value":"` + name + `","evidence_refs":["CLAIM-NAME"]}]}`)
}

func mutationProvenance(t *testing.T, document []byte, owner string) []byte {
	return mutationProvenanceFor(t, "CONTEXT", document, owner, "FIELD-NAME", "CLAIM-NAME")
}

func mutationProvenanceFor(t *testing.T, documentID string, document []byte, owner, fieldID, claimID string) []byte {
	t.Helper()
	path := ".codearbiter/" + documentID + ".md"
	record := map[string]any{
		"schema": 2, "doc": documentID, "created": "2026-09-27",
		"document": map[string]any{"path": path, "digest_method": "sha256-raw", "digest": canonical.BytesHash(document)},
		"fields": []any{map[string]any{"id": fieldID, "owner_ref": owner, "claims": []any{map[string]any{
			"id": claimID, "semantic_review": map[string]any{"state": "reviewed", "reference": "review:fixture"},
			"evidence":                 []any{map[string]any{"kind": "content", "path": "go.mod", "digest_method": "sha256-raw", "digest": canonical.BytesHash([]byte("source evidence\n"))}},
			"effective_authority_refs": []any{},
		}}}},
	}
	b, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func alterMutationProvenance(t *testing.T, original []byte, alter func(map[string]any)) []byte {
	t.Helper()
	var record map[string]any
	if err := json.Unmarshal(original, &record); err != nil {
		t.Fatal(err)
	}
	alter(record)
	b, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func mutationWrite(t *testing.T, f *store.FS, rel string, b []byte) {
	t.Helper()
	p := filepath.Join(f.Root, filepath.FromSlash(rel))
	if err := os.MkdirAll(filepath.Dir(p), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, b, 0644); err != nil {
		t.Fatal(err)
	}
}

func mutationRead(t *testing.T, f *store.FS, rel string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(f.Root, filepath.FromSlash(rel)))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func mutationRequest(t *testing.T, mode string, before, prior []byte, operation string) Mutation {
	t.Helper()
	r := Mutation{OperationID: operation, Mode: mode, Typed: mutationTyped("New"), ExpectedDocument: before, ExpectedProvenance: prior}
	if mode != "create" {
		r.Selections = []PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}}
	}
	p, err := RenderPreview(r.Typed, before, mode != "create", r.Selections)
	if err != nil {
		t.Fatal(err)
	}
	r.ProposedProvenance = mutationProvenance(t, p.Bytes, "project_name")
	return r
}

func fixtureMutationAuthority(t *testing.T, r Mutation) VerifiedAuthority {
	t.Helper()
	p, err := previewForMutation(r)
	if err != nil {
		t.Fatal(err)
	}
	binding, err := mutationBinding(r, p)
	if err != nil {
		t.Fatal(err)
	}
	return verifiedAuthority{binding: binding}
}

func TestContextMutationAdmission(t *testing.T) {
	const doc = ".codearbiter/CONTEXT.md"
	const prov = ".codearbiter/.provenance/CONTEXT.json"
	old := []byte("---\r\narbiter: enabled\r\n---\r\n# Project: Old\r\n\r\n## Human\nKeep exact bytes.\n")
	want := []byte("---\r\narbiter: enabled\r\n---\r\n# Project: New\r\n\r\n## Human\nKeep exact bytes.\n")
	t.Run("membership_python_parity_all_seven", assertMembershipParity)

	t.Run("approved_field_update_preserves_human_neighbors", func(t *testing.T) {
		f, done := mutationFixture(t, "update")
		defer done()
		initialized := bytes.Replace(old, []byte("# Project: Old"), []byte("<!--INITIALIZED-->\r\n# Project: Old"), 1)
		initializedWant := bytes.Replace(want, []byte("# Project: New"), []byte("<!--INITIALIZED-->\r\n# Project: New"), 1)
		prior := mutationProvenance(t, initialized, "project_name")
		mutationWrite(t, f, doc, initialized)
		mutationWrite(t, f, prov, prior)
		tasks := []byte("# Human tasks\n- [ ] retain task\n")
		audit := []byte("# Audit\nHuman event\n")
		mutationWrite(t, f, ".codearbiter/open-tasks.md", tasks)
		mutationWrite(t, f, ".codearbiter/overrides.log", audit)
		r := mutationRequest(t, "update", initialized, prior, "context-update-0001")
		out, err := Apply(f, r, fixtureMutationAuthority(t, r))
		if err != nil || out.State != "committed" {
			t.Fatalf("approved update: %+v %v", out, err)
		}
		if got := mutationRead(t, f, doc); !bytes.Equal(got, initializedWant) {
			t.Fatalf("marker or human neighbor changed: %q", got)
		}
		if got := mutationRead(t, f, prov); !bytes.Equal(got, r.ProposedProvenance) {
			t.Fatal("provenance pair not committed")
		}
		if !bytes.Equal(mutationRead(t, f, ".codearbiter/open-tasks.md"), tasks) || !bytes.Equal(mutationRead(t, f, ".codearbiter/overrides.log"), audit) {
			t.Fatal("refresh changed task or audit history")
		}
		out, err = Apply(f, r, fixtureMutationAuthority(t, r))
		if err != nil || !out.Replay {
			t.Fatalf("same request did not replay: %+v %v", out, err)
		}
	})

	t.Run("stale_document_and_provenance_pair_do_not_mutate", func(t *testing.T) {
		for _, altered := range []string{"document", "provenance"} {
			func() {
				f, done := mutationFixture(t, altered)
				defer done()
				prior := mutationProvenance(t, old, "project_name")
				r := mutationRequest(t, "update", old, prior, "context-stale-0001")
				actualDoc, actualProv := old, prior
				if altered == "document" {
					actualDoc = append(bytes.Clone(old), []byte("human edit\n")...)
				} else {
					actualProv = append(bytes.Clone(prior), '\n')
				}
				mutationWrite(t, f, doc, actualDoc)
				mutationWrite(t, f, prov, actualProv)
				if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "REVISION_CONFLICT" {
					t.Fatalf("stale %s pair admitted: %v", altered, err)
				}
				if !bytes.Equal(mutationRead(t, f, doc), actualDoc) || !bytes.Equal(mutationRead(t, f, prov), actualProv) {
					t.Fatalf("stale %s conflict mutated a target", altered)
				}
			}()
		}
	})

	t.Run("provenance_only_update_refuses_without_mutation", func(t *testing.T) {
		f, done := mutationFixture(t, "no-op")
		defer done()
		initialized := bytes.Replace(old, []byte("# Project: Old"), []byte("<!--INITIALIZED-->\r\n# Project: Old"), 1)
		prior := mutationProvenance(t, initialized, "project_name")
		mutationWrite(t, f, doc, initialized)
		mutationWrite(t, f, prov, prior)
		r := mutationRequest(t, "update", initialized, prior, "context-no-op-0001")
		r.Selections = nil
		if _, _, err := PreviewBinding(r); fault.Code(err) != "INVALID_CONTEXT_MUTATION" {
			t.Fatalf("provenance-only no-op unexpectedly previewed: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), initialized) || !bytes.Equal(mutationRead(t, f, prov), prior) {
			t.Fatal("refused no-op mutated initialized pair")
		}
	})

	t.Run("conflicting_document_provenance_identity_rejected", func(t *testing.T) {
		for _, conflict := range []string{"proposed", "existing", "owner"} {
			func() {
				f, done := mutationFixture(t, conflict)
				defer done()
				prior := mutationProvenance(t, old, "project_name")
				if conflict == "existing" {
					prior = mutationProvenance(t, []byte("different document"), "project_name")
				}
				if conflict == "owner" {
					prior = mutationProvenance(t, old, "other-anchor")
				}
				mutationWrite(t, f, doc, old)
				mutationWrite(t, f, prov, prior)
				r := mutationRequest(t, "update", old, prior, "context-pair-0001")
				if conflict == "proposed" {
					r.ProposedProvenance = mutationProvenance(t, old, "project_name")
				}
				if conflict == "owner" {
					r.ProposedProvenance = mutationProvenance(t, want, "other-anchor")
				}
				code := "PROVENANCE_CONFLICT"
				if conflict == "owner" {
					code = "OWNERSHIP_REQUIRED"
				}
				if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != code {
					t.Fatalf("%s pair admitted: %v", conflict, err)
				}
				if !bytes.Equal(mutationRead(t, f, doc), old) || !bytes.Equal(mutationRead(t, f, prov), prior) {
					t.Fatalf("%s pair changed", conflict)
				}
			}()
		}
	})

	t.Run("v2_text_and_array_compatibility", func(t *testing.T) {
		for _, tc := range []struct {
			name    string
			alter   func(map[string]any)
			allowed bool
		}{
			{"unicode_256", func(record map[string]any) { record["created"] = strings.Repeat("é", 256) }, true},
			{"unicode_257", func(record map[string]any) { record["created"] = strings.Repeat("é", 257) }, false},
			{"control_character", func(record map[string]any) { record["created"] = "2026\t09\t27" }, false},
			{"null_authority_refs", func(record map[string]any) {
				fields := record["fields"].([]any)
				claims := fields[0].(map[string]any)["claims"].([]any)
				claims[0].(map[string]any)["effective_authority_refs"] = nil
			}, false},
			{"scalar_authority_refs", func(record map[string]any) {
				fields := record["fields"].([]any)
				claims := fields[0].(map[string]any)["claims"].([]any)
				claims[0].(map[string]any)["effective_authority_refs"] = "ADR-0037"
			}, false},
		} {
			func() {
				f, done := mutationFixture(t, tc.name)
				defer done()
				prior := mutationProvenance(t, old, "project_name")
				mutationWrite(t, f, doc, old)
				mutationWrite(t, f, prov, prior)
				r := mutationRequest(t, "update", old, prior, "context-schema-0001")
				r.ProposedProvenance = alterMutationProvenance(t, r.ProposedProvenance, tc.alter)
				_, err := Apply(f, r, fixtureMutationAuthority(t, r))
				if tc.allowed {
					if err != nil || !bytes.Equal(mutationRead(t, f, doc), want) {
						t.Fatalf("valid v2 %s rejected: %v", tc.name, err)
					}
				} else {
					if fault.Code(err) != "OWNERSHIP_REQUIRED" {
						t.Fatalf("invalid v2 %s admitted: %v", tc.name, err)
					}
					if !bytes.Equal(mutationRead(t, f, doc), old) || !bytes.Equal(mutationRead(t, f, prov), prior) {
						t.Fatalf("invalid v2 %s mutated pair", tc.name)
					}
				}
			}()
		}
	})

	t.Run("changed_source_evidence_and_membership_fail_closed", func(t *testing.T) {
		for _, sourceKind := range []string{"changed_content", "membership"} {
			func() {
				f, done := mutationFixture(t, sourceKind)
				defer done()
				prior := mutationProvenance(t, old, "project_name")
				mutationWrite(t, f, doc, old)
				mutationWrite(t, f, prov, prior)
				r := mutationRequest(t, "update", old, prior, "context-source-0001")
				if sourceKind == "changed_content" {
					mutationWrite(t, f, "go.mod", []byte("human source edit\n"))
				} else {
					r.ProposedProvenance = alterMutationProvenance(t, r.ProposedProvenance, func(record map[string]any) {
						fields := record["fields"].([]any)
						claims := fields[0].(map[string]any)["claims"].([]any)
						claims[0].(map[string]any)["evidence"] = []any{map[string]any{"kind": "membership", "predicate": "manifests", "scope_paths": []any{"."}, "digest_method": "sha256-membership-v1", "digest": strings.Repeat("a", 64)}}
					})
				}
				code := "SOURCE_EVIDENCE_CONFLICT"
				if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != code {
					t.Fatalf("%s evidence admitted: %v", sourceKind, err)
				}
				if !bytes.Equal(mutationRead(t, f, doc), old) || !bytes.Equal(mutationRead(t, f, prov), prior) {
					t.Fatalf("%s evidence changed pair", sourceKind)
				}
			}()
		}
	})

	t.Run("current_membership_evidence_allows_scoped_update", func(t *testing.T) {
		f, done := mutationFixture(t, "membership-current")
		defer done()
		prior := mutationProvenance(t, old, "project_name")
		mutationWrite(t, f, doc, old)
		mutationWrite(t, f, prov, prior)
		r := mutationRequest(t, "update", old, prior, "context-membership-0001")
		digest, err := MembershipDigest(f, "manifests", []string{"."})
		if err != nil {
			t.Fatal(err)
		}
		r.ProposedProvenance = alterMutationProvenance(t, r.ProposedProvenance, func(record map[string]any) {
			fields := record["fields"].([]any)
			claims := fields[0].(map[string]any)["claims"].([]any)
			claims[0].(map[string]any)["evidence"] = []any{map[string]any{"kind": "membership", "predicate": "manifests", "scope_paths": []any{"."}, "digest_method": "sha256-membership-v1", "digest": digest}}
		})
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); err != nil {
			t.Fatalf("current membership rejected: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), want) {
			t.Fatal("scoped field update did not commit")
		}
		committed := mutationRead(t, f, prov)
		mutationWrite(t, f, "package.json", []byte(`{"name":"new"}`))
		stale := r
		stale.OperationID = "context-membership-0002"
		if _, err := Apply(f, stale, fixtureMutationAuthority(t, stale)); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
			t.Fatalf("changed membership admitted: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), want) || !bytes.Equal(mutationRead(t, f, prov), committed) {
			t.Fatal("changed membership mutated committed pair")
		}
	})

	t.Run("sensitive_content_evidence_is_refused", func(t *testing.T) {
		for _, sensitive := range []string{".env", "credentials.json", "keys/private.pem", "source/.env.local"} {
			func() {
				f, done := mutationFixture(t, sensitive)
				defer done()
				prior := mutationProvenance(t, old, "project_name")
				mutationWrite(t, f, doc, old)
				mutationWrite(t, f, prov, prior)
				r := mutationRequest(t, "update", old, prior, "context-sensitive-0001")
				r.ProposedProvenance = alterMutationProvenance(t, r.ProposedProvenance, func(record map[string]any) {
					fields := record["fields"].([]any)
					claims := fields[0].(map[string]any)["claims"].([]any)
					evidence := claims[0].(map[string]any)["evidence"].([]any)[0].(map[string]any)
					evidence["path"] = sensitive
				})
				if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "SOURCE_EVIDENCE_UNSUPPORTED" {
					t.Fatalf("sensitive %s read/admitted: %v", sensitive, err)
				}
				if !bytes.Equal(mutationRead(t, f, doc), old) || !bytes.Equal(mutationRead(t, f, prov), prior) {
					t.Fatalf("sensitive %s changed pair", sensitive)
				}
			}()
		}
	})

	t.Run("new_human_file_blocks_missing_creation", func(t *testing.T) {
		f, done := mutationFixture(t, "create")
		defer done()
		r := mutationRequest(t, "create", nil, nil, "context-create-0001")
		mutationWrite(t, f, doc, old)
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "REVISION_CONFLICT" {
			t.Fatalf("new human file admitted: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), old) {
			t.Fatal("new human file overwritten")
		}
		if _, err := os.Stat(filepath.Join(f.Root, filepath.FromSlash(prov))); !os.IsNotExist(err) {
			t.Fatal("provenance appeared after conflict")
		}
	})

	t.Run("missing_authority_and_hash_only_do_not_admit", func(t *testing.T) {
		f, done := mutationFixture(t, "closed")
		defer done()
		r := mutationRequest(t, "create", nil, nil, "context-closed-0001")
		if _, err := Apply(f, r, nil); fault.Code(err) != "AUTHORITY_REQUIRED" {
			t.Fatalf("nil authority: %v", err)
		}
		if _, err := Apply(f, r, verifiedAuthority{binding: strings.Repeat("0", 64)}); fault.Code(err) != "AUTHORITY_REQUIRED" {
			t.Fatalf("stale preview authority: %v", err)
		}
		if _, err := ApplyWithReceipt(f, r, "unobserved-context-receipt"); err == nil {
			t.Fatal("caller-supplied receipt name admitted without a verified observation")
		}
		if _, err := os.Stat(filepath.Join(f.Root, filepath.FromSlash(doc))); !os.IsNotExist(err) {
			t.Fatal("missing authority wrote document")
		}
		mutationWrite(t, f, doc, old)
		adopt := mutationRequest(t, "adopt", old, nil, "context-closed-0002")
		if _, err := Apply(f, adopt, nil); fault.Code(err) != "AUTHORITY_REQUIRED" {
			t.Fatalf("missing adoption authority admitted: %v", err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), old) {
			t.Fatal("missing adoption authority changed human file")
		}
	})

	t.Run("explicit_creation_and_adoption_are_distinct", func(t *testing.T) {
		f, done := mutationFixture(t, "modes")
		defer done()
		create := mutationRequest(t, "create", nil, nil, "context-mode-0001")
		if _, err := Apply(f, create, fixtureMutationAuthority(t, create)); err != nil {
			t.Fatalf("explicit missing creation: %v", err)
		}
		created := mutationRead(t, f, doc)
		if !bytes.Contains(created, []byte("# Project: New")) {
			t.Fatal("created template lacks field")
		}
		if !bytes.Equal(mutationRead(t, f, prov), create.ProposedProvenance) {
			t.Fatal("create lacks provenance")
		}
		if _, err := Apply(f, create, fixtureMutationAuthority(t, create)); err != nil {
			t.Fatalf("creation replay: %v", err)
		}
		g, finish := mutationFixture(t, "adopt")
		defer finish()
		mutationWrite(t, g, doc, old)
		adopt := mutationRequest(t, "adopt", old, nil, "context-adopt-0001")
		if _, err := Apply(g, adopt, fixtureMutationAuthority(t, adopt)); err != nil {
			t.Fatalf("explicit adoption: %v", err)
		}
		if got := mutationRead(t, g, doc); !bytes.Equal(got, want) {
			t.Fatalf("adoption changed wrong bytes: %q", got)
		}
	})

	t.Run("factual_claim_uses_existing_v2_field_ownership", func(t *testing.T) {
		f, done := mutationFixture(t, "fact")
		defer done()
		const coding = ".codearbiter/coding-standards.md"
		const codingProv = ".codearbiter/.provenance/coding-standards.json"
		previous := []byte("# Coding standards — Sample\n\n## Line endings and encoding\n- UTF-8, no BOM. Canonical EOL is LF.\n\n## Human\nKeep this.\n")
		prior := mutationProvenanceFor(t, "coding-standards", previous, "coding_pattern:line_endings", "FIELD-CODING", "CLAIM-CODING")
		mutationWrite(t, f, coding, previous)
		mutationWrite(t, f, codingProv, prior)
		typed := []byte(`{"format":"codearbiter.repository-context/0.1.0","document_id":"coding-standards","entries":[{"id":"CLAIM-CODING","kind":"fact","field":"coding_pattern","value":"UTF-8, no BOM. Canonical EOL is CRLF.","state":"observed","source_ref":"go.mod","consumer_ref":"core/artifacts","evidence_refs":["CLAIM-CODING"]}]}`)
		r := Mutation{OperationID: "context-fact-0001", Mode: "update", Typed: typed, Selections: []PreviewSelection{{EntryID: "CLAIM-CODING", Anchor: "coding_pattern:line_endings"}}, ExpectedDocument: previous, ExpectedProvenance: prior}
		preview, err := previewForMutation(r)
		if err != nil {
			t.Fatal(err)
		}
		r.ProposedProvenance = mutationProvenanceFor(t, "coding-standards", preview.Bytes, "coding_pattern:line_endings", "FIELD-CODING", "CLAIM-CODING")
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); err != nil {
			t.Fatalf("factual claim update: %v", err)
		}
		if got := mutationRead(t, f, coding); !bytes.Contains(got, []byte("EOL is CRLF.")) || !bytes.Contains(got, []byte("## Human\nKeep this.\n")) {
			t.Fatalf("factual update changed unowned text: %q", got)
		}
	})

	t.Run("unowned_or_unsupported_provenance_is_preserved", func(t *testing.T) {
		for _, previous := range [][]byte{nil, []byte(`{"schema":1,"doc":"CONTEXT","created":"2026-09-27","interview_derived":false,"entries":[]}`), []byte(`{"schema":99}`)} {
			f, done := mutationFixture(t, "unsupported")
			mutationWrite(t, f, doc, old)
			if previous != nil {
				mutationWrite(t, f, prov, previous)
			}
			r := mutationRequest(t, "update", old, previous, "context-owner-0001")
			if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); fault.Code(err) != "OWNERSHIP_REQUIRED" {
				t.Fatalf("unowned record admitted: %v", err)
			}
			if !bytes.Equal(mutationRead(t, f, doc), old) {
				t.Fatal("unowned document mutated")
			}
			if previous != nil && !bytes.Equal(mutationRead(t, f, prov), previous) {
				t.Fatal("unsupported record changed")
			}
			if previous != nil {
				adopt := mutationRequest(t, "adopt", old, previous, "context-owner-0002")
				if _, err := Apply(f, adopt, fixtureMutationAuthority(t, adopt)); fault.Code(err) != "OWNERSHIP_REQUIRED" {
					t.Fatalf("present provenance adopted: %v", err)
				}
			}
			done()
		}
	})

	t.Run("operation_id_reuse_with_different_request_rejected", func(t *testing.T) {
		f, done := mutationFixture(t, "reuse")
		defer done()
		first := mutationRequest(t, "create", nil, nil, "context-reuse-0001")
		if _, err := Apply(f, first, fixtureMutationAuthority(t, first)); err != nil {
			t.Fatal(err)
		}
		other := first
		other.Typed = mutationTyped("Other")
		if _, err := Apply(f, other, fixtureMutationAuthority(t, other)); fault.Code(err) != "OPERATION_ID_REUSE" {
			t.Fatalf("ID reused: %v", err)
		}
	})

	t.Run("replay_returns_historical_outcome_after_source_change", func(t *testing.T) {
		f, done := mutationFixture(t, "replay-source")
		defer done()
		r := mutationRequest(t, "create", nil, nil, "context-replay-0001")
		if _, err := Apply(f, r, fixtureMutationAuthority(t, r)); err != nil {
			t.Fatal(err)
		}
		committedDocument := mutationRead(t, f, doc)
		committedProvenance := mutationRead(t, f, prov)
		mutationWrite(t, f, "go.mod", []byte("changed after commit\n"))
		if out, err := Apply(f, r, fixtureMutationAuthority(t, r)); err != nil || !out.Replay || out.State != "committed" {
			t.Fatalf("durable historical replay lost: %+v %v", out, err)
		}
		if out, err := ApplyWithReceipt(f, r, "receipt-no-longer-available"); err != nil || !out.Replay || out.State != "committed" {
			t.Fatalf("historical receipt replay lost: %+v %v", out, err)
		}
		if !bytes.Equal(mutationRead(t, f, doc), committedDocument) || !bytes.Equal(mutationRead(t, f, prov), committedProvenance) {
			t.Fatal("stale source replay mutated pair")
		}
	})
}
