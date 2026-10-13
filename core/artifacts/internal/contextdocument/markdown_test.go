package contextdocument

import (
	"bytes"
	"strings"
	"testing"
)

func candidateByAnchor(t *testing.T, parsed ParsedMarkdown, anchor string) MarkdownCandidate {
	t.Helper()
	for _, candidate := range parsed.Candidates {
		if candidate.Anchor == anchor {
			return candidate
		}
	}
	t.Fatalf("missing candidate %q in %+v", anchor, parsed.Candidates)
	return MarkdownCandidate{}
}

func assertLossless(t *testing.T, original []byte, parsed ParsedMarkdown) {
	t.Helper()
	if !bytes.Equal(parsed.Bytes(), original) {
		t.Fatal("parse/roundtrip changed original bytes")
	}
	covered := make([]bool, len(original))
	for _, span := range parsed.Unowned {
		if span.Start < 0 || span.End < span.Start || span.End > len(original) {
			t.Fatalf("invalid unowned span %+v", span)
		}
		for offset := span.Start; offset < span.End; offset++ {
			if covered[offset] {
				t.Fatalf("overlap at byte %d", offset)
			}
			covered[offset] = true
		}
	}
	for _, candidate := range parsed.Candidates {
		span := candidate.Span
		if span.Start < 0 || span.End <= span.Start || span.End > len(original) {
			t.Fatalf("invalid candidate span %+v", span)
		}
		for offset := span.Start; offset < span.End; offset++ {
			if covered[offset] {
				t.Fatalf("overlap at byte %d", offset)
			}
			covered[offset] = true
		}
	}
	for offset, present := range covered {
		if !present {
			t.Fatalf("byte %d has no span", offset)
		}
	}
}

func TestContextMarkdownPreservation(t *testing.T) {
	t.Run("legacy_context_lf_unknown_section", func(t *testing.T) {
		original := []byte("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n\n# Project: codeArbiter\n\n## Owner notes\nHand edited.\n")
		parsed, err := ParseMarkdown("CONTEXT", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		candidate := candidateByAnchor(t, parsed, "project_name")
		if candidate.Kind != "identity" || candidate.Field != "project_name" || string(original[candidate.Span.Start:candidate.Span.End]) != "codeArbiter" {
			t.Fatalf("wrong project candidate: %+v", candidate)
		}
		original[0] = 'X'
		if parsed.Bytes()[0] != '-' {
			t.Fatal("parser retained mutable caller bytes")
		}
	})

	t.Run("legacy_context_crlf_roundtrip", func(t *testing.T) {
		original := []byte("---\r\narbiter: enabled\r\nstage: 2\r\n---\r\n<!--INITIALIZED-->\r\n\r\n# Project: Beacon\r\n\r\n## Human\r\nLeave this paragraph.\r\n")
		parsed, err := ParseMarkdown("CONTEXT", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		candidate := candidateByAnchor(t, parsed, "project_name")
		if string(original[candidate.Span.Start:candidate.Span.End]) != "Beacon" {
			t.Fatal("CRLF candidate includes line ending")
		}
	})

	t.Run("legacy_code_map_real_bullet", func(t *testing.T) {
		original := []byte("# Code map — codeArbiter\n\nHuman introduction.\n\n## Shared hook library (core/pysrc)\n\n- `core/pysrc/_hooklib.py` — hook dispatch kernel; host DI seam\n\n## Unknown human section\nPreserve me.\n")
		parsed, err := ParseMarkdown("code-map", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		candidate := candidateByAnchor(t, parsed, "map:Shared hook library (core/pysrc):core/pysrc/_hooklib.py")
		if candidate.Kind != "map_entry" || string(original[candidate.Span.Start:candidate.Span.End]) != "hook dispatch kernel; host DI seam" {
			t.Fatalf("wrong map role span: %+v", candidate)
		}
	})

	t.Run("inert_tech_stack_command", func(t *testing.T) {
		original := []byte("# Tech stack — Sample\n\n## Test\n\n```sh\n# human comment\npython -m unittest -v test_context_native | tee log\n```\n\n## Human\nDo not edit.\n")
		parsed, err := ParseMarkdown("tech-stack", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		candidate := candidateByAnchor(t, parsed, "test_command:1")
		if candidate.Kind != "command" || string(original[candidate.Span.Start:candidate.Span.End]) != "python -m unittest -v test_context_native | tee log" {
			t.Fatalf("command source was interpreted or split: %+v", candidate)
		}
	})

	t.Run("known_coding_and_security_lines", func(t *testing.T) {
		cases := []struct{ id, source, anchor, value string }{
			{"coding-standards", "# Coding standards — Sample\n\n## Line endings and encoding\n\n- UTF-8, no BOM. Canonical EOL is **LF** for all tracked text.\n\n## Owner note\nMine.\n", "coding_pattern:line_endings", "UTF-8, no BOM. Canonical EOL is **LF** for all tracked text."},
			{"security-controls", "# Security controls — Sample\n\n## Cryptographic primitives\n\n**Approved:** SHA-256.\n\n**Forbidden:** MD5.\n\n## Owner note\nMine.\n", "security_observation:approved_crypto", "SHA-256."},
		}
		for _, tc := range cases {
			parsed, err := ParseMarkdown(tc.id, []byte(tc.source))
			if err != nil {
				t.Fatalf("%s: %v", tc.id, err)
			}
			assertLossless(t, []byte(tc.source), parsed)
			candidate := candidateByAnchor(t, parsed, tc.anchor)
			if string(tc.source[candidate.Span.Start:candidate.Span.End]) != tc.value {
				t.Fatalf("wrong candidate for %s", tc.id)
			}
		}
	})

	t.Run("mixed_unowned_eol_preserved", func(t *testing.T) {
		original := []byte("# Code map — Sample\r\n\r\n## Components\r\n- `src/a.go` — role\r\n\r\n## Human\nMixed EOL stays as written.\n")
		parsed, err := ParseMarkdown("code-map", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
	})

	t.Run("duplicate_known_headings_rejected", func(t *testing.T) {
		original := []byte("# Code map — Sample\n\n## Components\n- `src/a.go` — first\n\n## Components\n- `src/b.go` — second\n")
		if _, err := ParseMarkdown("code-map", original); err == nil || !strings.Contains(err.Error(), "duplicate") {
			t.Fatalf("duplicate known heading accepted: %v", err)
		}
	})

	t.Run("ambiguous_map_anchor_rejected", func(t *testing.T) {
		original := []byte("# Code map — Sample\n\n## Components\n- `src/a.go` — first\n- `src/a.go` — second\n")
		if _, err := ParseMarkdown("code-map", original); err == nil || !strings.Contains(err.Error(), "duplicate") {
			t.Fatalf("duplicate candidate anchor accepted: %v", err)
		}
	})

	t.Run("unsupported_and_malformed_unchanged", func(t *testing.T) {
		cases := []struct {
			id     string
			source []byte
		}{
			{"open-tasks", []byte("# Code map — Sample\n## Components\n- `src/a.go` — role\n")},
			{"code-map", []byte("# Personal notes\n## Components\n- `src/a.go` — role\n")},
			{"CONTEXT", []byte("---\narbiter: enabled\n# Project: Foo\n")},
			{"tech-stack", []byte("# Tech stack — Sample\n## Test\n```sh\ngo test ./...\n")},
		}
		for _, tc := range cases {
			before := append([]byte(nil), tc.source...)
			if _, err := ParseMarkdown(tc.id, tc.source); err == nil {
				t.Fatalf("unsupported %s accepted", tc.id)
			}
			if !bytes.Equal(before, tc.source) {
				t.Fatalf("failed parse changed %s", tc.id)
			}
		}
	})

	t.Run("generated_comment_is_syntax_only", func(t *testing.T) {
		original := []byte("# Code map — Sample\n<!-- generated by codeArbiter -->\n## Components\n- `src/a.go` — role\n")
		parsed, err := ParseMarkdown("code-map", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		if len(parsed.Candidates) != 1 {
			t.Fatalf("unexpected candidate count: %d", len(parsed.Candidates))
		}
		if bytes.Contains(parsed.Bytes(), []byte("owner: accepted")) {
			t.Fatal("parser created ownership claim")
		}
	})

	t.Run("created_template_field_markers", func(t *testing.T) {
		original := []byte("---\n arbiter: enabled\n---\n# Project: Sample\n\n## Human\nKeep me.\n\n<!-- ca:field FIELD-SCOPE identity project_scope -->\nSynthetic project scope\n<!-- ca:end-field FIELD-SCOPE -->\n")
		parsed, err := ParseMarkdown("CONTEXT", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		candidate := candidateByAnchor(t, parsed, "entry:FIELD-SCOPE")
		if candidate.Kind != "identity" || candidate.Field != "project_scope" || string(original[candidate.Span.Start:candidate.Span.End]) != "Synthetic project scope" {
			t.Fatalf("wrong explicit candidate: %+v", candidate)
		}
	})

	t.Run("invalid_field_markers_rejected", func(t *testing.T) {
		for _, marker := range []string{
			"<!-- ca:field FIELD-SCOPE identity project_scope -->\nvalue\n<!-- ca:end-field FIELD-OTHER -->",
			"<!-- ca:field FIELD-SCOPE identity project_scope -->\n<!-- ca:field FIELD-OTHER identity project_scope -->\n<!-- ca:end-field FIELD-SCOPE -->",
			"<!-- ca:end-field FIELD-SCOPE -->",
			"<!-- ca:field CLAIM-SCOPE identity project_scope -->\nvalue\n<!-- ca:end-field CLAIM-SCOPE -->",
			"<!-- ca:field FIELD-SCOPE command _ -->\nvalue\n<!-- ca:end-field FIELD-SCOPE -->",
		} {
			source := []byte("---\narbiter: enabled\n---\n# Project: Sample\n" + marker + "\n")
			if _, err := ParseMarkdown("CONTEXT", source); err == nil {
				t.Fatalf("bad marker accepted: %s", marker)
			}
		}
	})

	t.Run("non_sh_fence_does_not_create_command", func(t *testing.T) {
		original := []byte("# Tech stack — Sample\n\n## Test\n\n```text\npython -m unittest\n```\n")
		if _, err := ParseMarkdown("tech-stack", original); err == nil || !strings.Contains(err.Error(), "unsupported") {
			t.Fatalf("text fence became executable command candidate: %v", err)
		}
	})

	t.Run("candidate_span_update_preserves_unowned_bytes", func(t *testing.T) {
		original := []byte("---\r\narbiter: enabled\r\n---\r\n# Project: Old\r\n\r\n## Human\nDo not normalize me.\n")
		parsed, err := ParseMarkdown("CONTEXT", original)
		if err != nil {
			t.Fatal(err)
		}
		candidate := candidateByAnchor(t, parsed, "project_name")
		updated := append([]byte(nil), original[:candidate.Span.Start]...)
		updated = append(updated, []byte("New")...)
		updated = append(updated, original[candidate.Span.End:]...)
		expected := bytes.Replace(original, []byte("# Project: Old\r\n"), []byte("# Project: New\r\n"), 1)
		if !bytes.Equal(updated, expected) {
			t.Fatal("candidate span consumed neighboring syntax or line ending")
		}
	})

	t.Run("partial_title_and_indented_marker_rejected", func(t *testing.T) {
		cases := []struct {
			id     string
			source string
		}{
			{"code-map", "# Code mapper\n## Components\n- `src/a.go` — role\n"},
			{"CONTEXT", "---\narbiter: enabled\n---\n# Project: Sample\n  <!-- ca:field FIELD-SCOPE identity project_scope -->\nvalue\n<!-- ca:end-field FIELD-SCOPE -->\n"},
		}
		for _, tc := range cases {
			if _, err := ParseMarkdown(tc.id, []byte(tc.source)); err == nil {
				t.Fatalf("ambiguous format accepted: %s", tc.source)
			}
		}
	})

	t.Run("four_tick_unknown_fence_preserved", func(t *testing.T) {
		original := []byte("# Code map — Sample\n\n## Components\n- `src/a.go` — role\n\n## Human\n````text\n```\n## Components\n- `src/a.go` — fake duplicate\n````\nAfter fence.\n")
		parsed, err := ParseMarkdown("code-map", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		if len(parsed.Candidates) != 1 {
			t.Fatalf("code fence created false candidates: %+v", parsed.Candidates)
		}
	})

	t.Run("mixed_legacy_and_managed_identity_rejected", func(t *testing.T) {
		original := []byte("---\narbiter: enabled\n---\n# Project: Old\n\n<!-- ca:field FIELD-NAME identity project_name -->\nNew\n<!-- ca:end-field FIELD-NAME -->\n")
		before := bytes.Clone(original)
		if _, err := ParseMarkdown("CONTEXT", original); err == nil || !strings.Contains(err.Error(), "duplicate identity field") {
			t.Fatalf("mixed project names accepted: %v", err)
		}
		if !bytes.Equal(before, original) {
			t.Fatal("rejected input changed")
		}
	})

	t.Run("two_managed_singular_identities_rejected", func(t *testing.T) {
		original := []byte("---\narbiter: enabled\n---\n# Project: Sample\n\n<!-- ca:field FIELD-SCOPE-A identity project_scope -->\nFirst scope\n<!-- ca:end-field FIELD-SCOPE-A -->\n<!-- ca:field FIELD-SCOPE-B identity project_scope -->\nSecond scope\n<!-- ca:end-field FIELD-SCOPE-B -->\n")
		if _, err := ParseMarkdown("CONTEXT", original); err == nil || !strings.Contains(err.Error(), "duplicate identity field") {
			t.Fatalf("two managed project scopes accepted: %v", err)
		}
	})

	t.Run("independent_fact_claims_same_field_allowed", func(t *testing.T) {
		original := []byte("# Coding standards — Sample\n\n<!-- ca:field CLAIM-PATTERN-A fact coding_pattern -->\nFirst pattern\n<!-- ca:end-field CLAIM-PATTERN-A -->\n<!-- ca:field CLAIM-PATTERN-B fact coding_pattern -->\nSecond pattern\n<!-- ca:end-field CLAIM-PATTERN-B -->\n")
		parsed, err := ParseMarkdown("coding-standards", original)
		if err != nil {
			t.Fatal(err)
		}
		assertLossless(t, original, parsed)
		if len(parsed.Candidates) != 2 {
			t.Fatalf("independent fact claims collapsed: %+v", parsed.Candidates)
		}
	})
}
