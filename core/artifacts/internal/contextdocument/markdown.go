package contextdocument

import (
	"bytes"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

// ByteSpan is a half-open byte range in ParsedMarkdown.Bytes(). Offsets, not
// normalized strings, preserve every line ending and human-authored byte.
type ByteSpan struct {
	Start int
	End   int
}

// MarkdownCandidate describes syntax that a later, separately authorized
// operation may bind to a typed field. Parsing never claims ownership.
type MarkdownCandidate struct {
	Kind   string
	Field  string
	Anchor string
	Span   ByteSpan
}

type ParsedMarkdown struct {
	DocumentID string
	TargetPath string
	Candidates []MarkdownCandidate
	Unowned    []ByteSpan
	source     []byte
}

func (p ParsedMarkdown) Bytes() []byte { return bytes.Clone(p.source) }

type markdownLine struct {
	start, end int // end excludes CR/LF
	text       string
	visible    bool
	fence      string // nonempty only for content within a fenced block
}

var (
	managedStart = regexp.MustCompile(`^<!-- ca:field ((?:FIELD|CLAIM)-[A-Z0-9]+(?:-[A-Z0-9]+)*) (identity|fact|command|source_relationship|map_entry|constraint_reference) ([a-z_]+|_) -->$`)
	managedEnd   = regexp.MustCompile(`^<!-- ca:end-field ((?:FIELD|CLAIM)-[A-Z0-9]+(?:-[A-Z0-9]+)*) -->$`)
	mapBullet    = regexp.MustCompile("^- `([^`]+)` — (.+)$")
)

func markdownLines(source []byte) ([]markdownLine, error) {
	if len(source) == 0 || !utf8.Valid(source) || bytes.IndexByte(source, 0) >= 0 {
		return nil, fmt.Errorf("supported Markdown requires nonempty UTF-8 text without NUL")
	}
	lines := make([]markdownLine, 0, bytes.Count(source, []byte{'\n'})+1)
	for start := 0; start < len(source); {
		end := len(source)
		if offset := bytes.IndexByte(source[start:], '\n'); offset >= 0 {
			end = start + offset
		}
		contentEnd := end
		if contentEnd > start && source[contentEnd-1] == '\r' {
			contentEnd--
		}
		if bytes.IndexByte(source[start:contentEnd], '\r') >= 0 {
			return nil, fmt.Errorf("unsupported bare carriage return at byte %d", start)
		}
		lines = append(lines, markdownLine{start: start, end: contentEnd, text: string(source[start:contentEnd])})
		if end == len(source) {
			break
		}
		start = end + 1
	}
	return lines, nil
}

func classifyMarkdown(lines []markdownLine) error {
	comment, fenceChar, fenceRun, language := false, byte(0), 0, ""
	for i := range lines {
		text := lines[i].text
		trimmed := strings.TrimSpace(text)
		if comment {
			if strings.Contains(text, "-->") {
				comment = false
			}
			continue
		}
		if fenceChar != 0 {
			run := 0
			for run < len(trimmed) && trimmed[run] == fenceChar {
				run++
			}
			if run >= fenceRun && strings.TrimSpace(trimmed[run:]) == "" {
				fenceChar, fenceRun, language = 0, 0, ""
			} else {
				lines[i].fence = string(fenceChar) + ":" + language
			}
			continue
		}
		if strings.HasPrefix(trimmed, "<!--") && !strings.Contains(trimmed, "-->") {
			comment = true
			continue
		}
		if strings.HasPrefix(trimmed, "<!--") { // whole-line comments are never headings
			lines[i].visible = true // exact managed markers are read separately
			continue
		}
		if len(trimmed) >= 3 && (trimmed[0] == '`' || trimmed[0] == '~') {
			run := 0
			for run < len(trimmed) && trimmed[run] == trimmed[0] {
				run++
			}
			if run >= 3 {
				fenceChar, fenceRun = trimmed[0], run
				language = strings.TrimSpace(trimmed[run:])
				continue
			}
		}
		lines[i].visible = true
	}
	if comment {
		return fmt.Errorf("unterminated Markdown comment")
	}
	if fenceChar != 0 {
		return fmt.Errorf("unterminated Markdown fence")
	}
	return nil
}

func markdownFieldAllowed(kind, field string) bool {
	switch kind {
	case "identity":
		return oneOf(field, "project_name", "project_purpose", "project_scope")
	case "fact":
		return oneOf(field, "runtime", "test_boundary", "coding_pattern", "security_observation", "project_fact")
	default:
		return field == "_"
	}
}

func addMarkdownCandidate(candidates *[]MarkdownCandidate, seen map[string]bool, kind, field, anchor string, span ByteSpan) error {
	if seen[anchor] {
		return fmt.Errorf("duplicate Markdown anchor %q", anchor)
	}
	if span.Start >= span.End {
		return fmt.Errorf("empty Markdown candidate %q", anchor)
	}
	seen[anchor] = true
	*candidates = append(*candidates, MarkdownCandidate{Kind: kind, Field: field, Anchor: anchor, Span: span})
	return nil
}

func parseManagedMarkdown(documentID string, lines []markdownLine, skip []bool, candidates *[]MarkdownCandidate, seen map[string]bool) error {
	for i := range lines {
		if !lines[i].visible || skip[i] {
			continue
		}
		text := lines[i].text
		if strings.HasPrefix(strings.TrimSpace(text), "<!-- ca:") && text != strings.TrimSpace(text) {
			return fmt.Errorf("indented field marker at line %d", i+1)
		}
		open := managedStart.FindStringSubmatch(text)
		if open == nil {
			if managedEnd.MatchString(text) || strings.HasPrefix(text, "<!-- ca:") {
				return fmt.Errorf("malformed or orphan field marker at line %d", i+1)
			}
			continue
		}
		id, kind, field := open[1], open[2], open[3]
		if kind == "fact" && !strings.HasPrefix(id, "CLAIM-") || kind != "fact" && !strings.HasPrefix(id, "FIELD-") {
			return fmt.Errorf("field marker %q has wrong ID family", id)
		}
		if !documents[documentID].kinds[kind] || !markdownFieldAllowed(kind, field) {
			return fmt.Errorf("field marker %q has unsupported kind or field", id)
		}
		if i+2 >= len(lines) || !lines[i+1].visible || !lines[i+2].visible || strings.TrimSpace(lines[i+1].text) == "" {
			return fmt.Errorf("field marker %q lacks one content line and closing marker", id)
		}
		if lines[i+2].text != "<!-- ca:end-field "+id+" -->" {
			return fmt.Errorf("field marker %q has mismatched or missing close", id)
		}
		if strings.HasPrefix(lines[i+1].text, "<!-- ca:") {
			return fmt.Errorf("nested field marker %q", id)
		}
		if err := addMarkdownCandidate(candidates, seen, kind, field, "entry:"+id, ByteSpan{lines[i+1].start, lines[i+1].end}); err != nil {
			return err
		}
		skip[i], skip[i+1], skip[i+2] = true, true, true
		i += 2
	}
	return nil
}

func markdownHeading(line markdownLine, prefix string) string {
	if !line.visible || !strings.HasPrefix(line.text, prefix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(line.text, prefix))
}

func parseLegacyMarkdown(documentID string, lines []markdownLine, skip []bool, candidates *[]MarkdownCandidate, seen map[string]bool) error {
	var titlePrefix string
	switch documentID {
	case "CONTEXT":
		titlePrefix = "Project: "
	case "tech-stack":
		titlePrefix = "Tech stack"
	case "coding-standards":
		titlePrefix = "Coding standards"
	case "security-controls":
		titlePrefix = "Security controls"
	case "code-map":
		titlePrefix = "Code map"
	}
	titleCount, section := 0, ""
	sections := map[string]bool{}
	commandNumber := 0
	for i, line := range lines {
		if skip[i] {
			continue
		}
		if heading := markdownHeading(line, "# "); heading != "" && !strings.HasPrefix(line.text, "## ") {
			validTitle := heading == titlePrefix || strings.HasPrefix(heading, titlePrefix+" — ")
			if documentID == "CONTEXT" {
				validTitle = strings.HasPrefix(heading, titlePrefix)
			}
			if !validTitle {
				return fmt.Errorf("%s: unsupported document title at line %d", documentID, i+1)
			}
			titleCount++
			if titleCount != 1 {
				return fmt.Errorf("%s: duplicate document title", documentID)
			}
			if documentID == "CONTEXT" {
				value := strings.TrimPrefix(heading, titlePrefix)
				if value == "" || strings.TrimSpace(value) != value {
					return fmt.Errorf("CONTEXT: ambiguous project name")
				}
				start := line.start + len("# ") + len(titlePrefix)
				if err := addMarkdownCandidate(candidates, seen, "identity", "project_name", "project_name", ByteSpan{start, line.end}); err != nil {
					return err
				}
			}
			continue
		}
		if heading := markdownHeading(line, "## "); heading != "" {
			section = heading
			if documentID == "code-map" || section == "Test" || section == "Line endings and encoding" || section == "Cryptographic primitives" {
				if sections[section] {
					return fmt.Errorf("%s: duplicate known heading %q", documentID, section)
				}
				sections[section] = true
			}
			continue
		}
		if titleCount == 0 {
			continue
		}
		switch documentID {
		case "code-map":
			if section == "" || !line.visible || !strings.HasPrefix(line.text, "- `") {
				continue
			}
			parts := mapBullet.FindStringSubmatchIndex(line.text)
			if parts == nil {
				continue
			} // other human bullet shapes remain unowned
			path := line.text[parts[2]:parts[3]]
			if _, err := relative(path, false); err != nil {
				continue
			}
			anchor := "map:" + section + ":" + path
			span := ByteSpan{line.start + parts[4], line.start + parts[5]}
			if err := addMarkdownCandidate(candidates, seen, "map_entry", "", anchor, span); err != nil {
				return err
			}
		case "tech-stack":
			if section != "Test" || line.fence != "`:sh" && line.fence != "~:sh" {
				continue
			}
			if strings.TrimSpace(line.text) == "" || strings.HasPrefix(strings.TrimSpace(line.text), "#") {
				continue
			}
			commandNumber++
			anchor := fmt.Sprintf("test_command:%d", commandNumber)
			if err := addMarkdownCandidate(candidates, seen, "command", "", anchor, ByteSpan{line.start, line.end}); err != nil {
				return err
			}
		case "coding-standards":
			if section != "Line endings and encoding" || !line.visible || !strings.HasPrefix(line.text, "- UTF-8, no BOM. Canonical EOL is ") {
				continue
			}
			if err := addMarkdownCandidate(candidates, seen, "fact", "coding_pattern", "coding_pattern:line_endings", ByteSpan{line.start + 2, line.end}); err != nil {
				return err
			}
		case "security-controls":
			if section != "Cryptographic primitives" || !line.visible {
				continue
			}
			for _, label := range []struct{ prefix, anchor string }{{"**Approved:** ", "security_observation:approved_crypto"}, {"**Forbidden:** ", "security_observation:forbidden_crypto"}} {
				if strings.HasPrefix(line.text, label.prefix) {
					if err := addMarkdownCandidate(candidates, seen, "fact", "security_observation", label.anchor, ByteSpan{line.start + len(label.prefix), line.end}); err != nil {
						return err
					}
				}
			}
		}
	}
	if titleCount != 1 {
		return fmt.Errorf("%s: missing supported document title", documentID)
	}
	if documentID == "CONTEXT" {
		if len(lines) < 4 || lines[0].text != "---" {
			return fmt.Errorf("CONTEXT: missing leading frontmatter")
		}
		closed := false
		for i := 1; i < len(lines); i++ {
			if lines[i].text == "---" {
				closed = true
				break
			}
			if strings.HasPrefix(lines[i].text, "# ") {
				break
			}
		}
		if !closed {
			return fmt.Errorf("CONTEXT: unterminated leading frontmatter")
		}
	}
	return nil
}

// ParseMarkdown recognizes a finite set of legacy and explicit field-template
// shapes. Candidate spans are syntactic only: headings and comments never grant
// ownership, approval, freshness, or permission to mutate a document.
func ParseMarkdown(documentID string, source []byte) (ParsedMarkdown, error) {
	contract, ok := documents[documentID]
	if !ok {
		return ParsedMarkdown{}, fmt.Errorf("unknown repository context document %q", documentID)
	}
	lines, err := markdownLines(source)
	if err != nil {
		return ParsedMarkdown{}, fmt.Errorf("%s: %w", documentID, err)
	}
	if err := classifyMarkdown(lines); err != nil {
		return ParsedMarkdown{}, fmt.Errorf("%s: %w", documentID, err)
	}
	candidates, seen := []MarkdownCandidate{}, map[string]bool{}
	skip := make([]bool, len(lines))
	if err := parseManagedMarkdown(documentID, lines, skip, &candidates, seen); err != nil {
		return ParsedMarkdown{}, fmt.Errorf("%s: %w", documentID, err)
	}
	if err := parseLegacyMarkdown(documentID, lines, skip, &candidates, seen); err != nil {
		return ParsedMarkdown{}, err
	}
	identityFields := map[string]bool{}
	for _, candidate := range candidates {
		if candidate.Kind != "identity" {
			continue
		}
		if identityFields[candidate.Field] {
			return ParsedMarkdown{}, fmt.Errorf("%s: duplicate identity field %q", documentID, candidate.Field)
		}
		identityFields[candidate.Field] = true
	}
	if len(candidates) == 0 {
		return ParsedMarkdown{}, fmt.Errorf("%s: unsupported Markdown template has no bounded field candidates", documentID)
	}
	sort.Slice(candidates, func(i, j int) bool { return candidates[i].Span.Start < candidates[j].Span.Start })
	unowned := make([]ByteSpan, 0, len(candidates)+1)
	end := 0
	for _, candidate := range candidates {
		if candidate.Span.Start < end || candidate.Span.End > len(source) {
			return ParsedMarkdown{}, fmt.Errorf("%s: overlapping or invalid field spans", documentID)
		}
		if candidate.Span.Start > end {
			unowned = append(unowned, ByteSpan{end, candidate.Span.Start})
		}
		end = candidate.Span.End
	}
	if end < len(source) {
		unowned = append(unowned, ByteSpan{end, len(source)})
	}
	return ParsedMarkdown{DocumentID: documentID, TargetPath: contract.path, Candidates: candidates, Unowned: unowned, source: bytes.Clone(source)}, nil
}
