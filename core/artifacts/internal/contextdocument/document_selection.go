package contextdocument

import (
	"bytes"
	"fmt"
	"strings"
)

func contextFrontmatter(body []byte) ([]byte, error) {
	lines, err := markdownLines(body)
	if err != nil || len(lines) < 2 || lines[0].text != "---" {
		return nil, fmt.Errorf("CONTEXT requires leading frontmatter")
	}
	for _, line := range lines[1:] {
		if line.text == "---" {
			return body[:line.end], nil
		}
	}
	return nil, fmt.Errorf("CONTEXT frontmatter is unterminated")
}

func visibleInitializationMarkers(body []byte) int {
	lines, err := markdownLines(body)
	if err != nil || classifyMarkdown(lines) != nil {
		return -1
	}
	count := 0
	for _, line := range lines {
		if line.visible && strings.TrimSpace(line.text) == "<!--INITIALIZED-->" {
			count++
		}
	}
	return count
}

// Full-document selection is deliberately explicit and byte-bound. Legacy
// human layouts need not match the narrow field parser, but Markdown must be
// well formed and CONTEXT enrollment/initialization controls cannot change.
func renderDocumentSelection(doc Document, source []byte, exists bool, selections []PreviewSelection) (Preview, error) {
	entry := doc.Entries[0]
	if len(selections) != 1 || selections[0].EntryID != entry.ID || selections[0].Anchor != "document" {
		return Preview{}, fmt.Errorf("whole document requires its explicit document selection")
	}
	if !exists && len(source) != 0 {
		return Preview{}, fmt.Errorf("missing document cannot select existing bytes")
	}
	output := []byte(entry.Document.Markdown)
	for _, body := range [][]byte{output, source} {
		if len(body) == 0 && !exists {
			continue
		}
		lines, err := markdownLines(body)
		if err != nil {
			return Preview{}, err
		}
		if err := classifyMarkdown(lines); err != nil {
			return Preview{}, err
		}
	}
	// New output retains the document identity, without requiring any specific
	// body template or treating arbitrary Markdown as executable instructions.
	lines, _ := markdownLines(output)
	_ = classifyMarkdown(lines)
	titles := 0
	prefix := map[string]string{"CONTEXT": "Project: ", "tech-stack": "Tech stack", "coding-standards": "Coding standards", "security-controls": "Security controls", "code-map": "Code map"}[doc.DocumentID]
	for _, line := range lines {
		if title := markdownHeading(line, "# "); title != "" {
			if !strings.HasPrefix(title, prefix) {
				return Preview{}, fmt.Errorf("replacement document title disagrees with its identity")
			}
			titles++
		}
	}
	if titles != 1 {
		return Preview{}, fmt.Errorf("replacement needs one document title")
	}
	if doc.DocumentID == "CONTEXT" {
		after, err := contextFrontmatter(output)
		if err != nil {
			return Preview{}, err
		}
		if exists {
			before, err := contextFrontmatter(source)
			if err != nil || !bytes.Equal(before, after) {
				return Preview{}, fmt.Errorf("document replacement must preserve CONTEXT frontmatter exactly")
			}
		}
		marker := []byte("<!--INITIALIZED-->")
		if bytes.Count(output, marker) != bytes.Count(source, marker) || exists && visibleInitializationMarkers(output) != visibleInitializationMarkers(source) {
			return Preview{}, fmt.Errorf("document replacement must preserve initialization state")
		}
	}
	if doc.DocumentID == "code-map" && len(output) > 20*1024 {
		return Preview{}, fmt.Errorf("code map exceeds 20 KiB")
	}
	p := Preview{DocumentID: doc.DocumentID, TargetPath: doc.TargetPath, Bytes: bytes.Clone(output), AfterSHA256: previewHash(output), ProposedEntries: doc.Entries}
	if exists {
		p.BeforeSHA256 = previewHash(source)
	}
	if !bytes.Equal(source, output) {
		p.Changes = []PreviewChange{{EntryID: entry.ID, Kind: "document", Anchor: "document", Span: ByteSpan{0, len(source)}, Old: string(source), New: string(output)}}
	}
	return p, nil
}
