package operations

import (
	"fmt"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
)

type sourceSection struct {
	id, source, artifactID string
	content                bool
	view                   object
}

// sourceSections inventories exact byte spans for the converting agent. It
// identifies sections but does not infer or import their meaning.
func (e *Engine) sourceSections() (map[string]any, []sourceSection, error) {
	ctx, present, err := readOptional(e.FS, contextPath)
	if err != nil || !present {
		return nil, nil, fault.New("NOT_INITIALIZED", "CONTEXT.md is absent or unreadable")
	}
	if contextdocument.IsHTMLFormat(ctx) {
		return nil, nil, fault.New("ALREADY_CONVERTED", "CONTEXT.md already selects HTML knowledge")
	}
	_, bodyStart, err := contextdocument.ConvertedContext(ctx)
	if err != nil {
		return nil, nil, err
	}
	initialized := strings.Contains(string(ctx[bodyStart:]), "<!--INITIALIZED-->")
	expected := map[string]any{}
	sections := []sourceSection{}
	add := func(p, id, title string, raw []byte, start int, active bool) error {
		expected[p] = canonical.BytesHash(raw)
		parts, err := contextdocument.Sections(raw, start, title)
		if err != nil {
			return err
		}
		for _, part := range parts {
			sectionID := fmt.Sprintf("%s@%d:%d", p, part.Start, part.End)
			content := active && part.Content
			sections = append(sections, sourceSection{sectionID, p, id, content,
				object{"id": sectionID, "source": p, "artifact_id": id,
					"start": int64(part.Start), "end": int64(part.End), "heading": part.Heading,
					"sha256": canonical.BytesHash(raw[part.Start:part.End]), "content": content}})
			if len(sections) > 1024 {
				return fault.New("TOO_MANY_SECTIONS", "conversion has more than 1024 Markdown sections")
			}
		}
		return nil
	}
	for _, doc := range knowledgeDocuments {
		p := doc.legacy
		raw, start, active := []byte(nil), 0, true
		if p == contextPath {
			raw, start, active = ctx, bodyStart, initialized
		} else {
			var found bool
			raw, found, err = readOptional(e.FS, p)
			if err != nil {
				return nil, nil, err
			}
			if !found {
				continue
			}
		}
		if err := add(p, knowledgeID(doc.slug), doc.title, raw, start, active); err != nil {
			return nil, nil, err
		}
	}
	decomp, err := decompositionSources(e.FS)
	if err != nil {
		return nil, nil, err
	}
	for _, p := range decomp {
		raw, _, err := readOptional(e.FS, p)
		if err != nil {
			return nil, nil, err
		}
		if err := add(p, "DECOMP-PROJECT", "", raw, 0, true); err != nil {
			return nil, nil, err
		}
	}
	return expected, sections, nil
}

func (e *Engine) validateSectionCoverage(sections []sourceSection, supplied any) error {
	rows, ok := supplied.([]any)
	if !ok || len(rows) != len(sections) {
		return fault.New("UNCOVERED_SECTION", "provide one coverage mapping for every Markdown section")
	}
	entries, unreadable, err := repository.LoadKnowledge(e.FS)
	if err != nil {
		return err
	}
	if len(unreadable) > 0 {
		return fault.At(unreadable[0].Code, "", unreadable[0].Path, "knowledge document is unreadable")
	}
	docs := map[string]repository.Entry{}
	for _, entry := range entries {
		docs[entry.Doc.ID()] = entry
	}
	wanted := map[string]sourceSection{}
	for _, section := range sections {
		wanted[section.id] = section
	}
	seen := map[string]bool{}
	for _, value := range rows {
		row := model.M(value)
		id := model.S(row["section"])
		section, exists := wanted[id]
		if !exists || seen[id] {
			return fault.New("UNCOVERED_SECTION", "coverage names an unknown or duplicate section")
		}
		seen[id] = true
		refs, ok := row["records"].([]any)
		if !ok || len(refs) > 32 || section.content && len(refs) == 0 {
			return fault.At("UNCOVERED_SECTION", "", section.source, "meaningful section has no record or note mapping")
		}
		for _, value := range refs {
			ref := model.S(value)
			docID, recordID, err := symbol.Split(ref)
			if err != nil || docID != section.artifactID {
				return fault.At("INVALID_COVERAGE", "", section.source, "section record belongs to another document")
			}
			doc, ok := docs[docID]
			if !ok {
				return fault.At("INVALID_COVERAGE", "", section.source, "section knowledge document is absent")
			}
			record, found := doc.Doc.Symbols.ByID[recordID]
			if !found || record.Retired || record.Kind != "records" && record.Kind != "notes" {
				return fault.At("INVALID_COVERAGE", recordID, section.source, "section mapping must name an active record or note")
			}
		}
	}
	return nil
}
