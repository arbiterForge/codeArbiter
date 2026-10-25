package contextdocument

import (
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// Section is an exact byte span in a Markdown source. Splitting headings is
// only coverage accounting; interpretation remains with the converting model.
type Section struct {
	Start, End int
	Heading    string
	Content    bool
}

func heading(text string) string {
	text = strings.TrimSpace(text)
	n := 0
	for n < len(text) && text[n] == '#' {
		n++
	}
	if n == 0 || n > 6 || n >= len(text) || text[n] != ' ' {
		return ""
	}
	return strings.TrimSpace(strings.TrimRight(strings.TrimSpace(text[n+1:]), "#"))
}

// Sections lists every Markdown section, including preamble text, without
// converting its meaning. Fenced headings remain within their parent section.
func Sections(raw []byte, start int, genericTitle string) ([]Section, error) {
	if start < 0 || start > len(raw) {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "invalid Markdown body offset")
	}
	if len(raw) == 0 {
		return []Section{}, nil
	}
	lines, err := markdownLines(raw)
	if err != nil {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "Markdown source is not supported UTF-8")
	}
	sections := []Section{}
	current, title := start, ""
	fenceChar, fenceRun := byte(0), 0
	appendSection := func(end int) {
		if end <= current {
			return
		}
		body := raw[current:end]
		contentStart := 0
		if title != "" && strings.EqualFold(title, genericTitle) {
			if i := strings.IndexByte(string(body), '\n'); i >= 0 {
				contentStart = i + 1
			} else {
				contentStart = len(body)
			}
		}
		sections = append(sections, Section{current, end, title, HasContent(body, contentStart)})
	}
	for _, line := range lines {
		if line.start < start {
			continue
		}
		trimmed := strings.TrimSpace(line.text)
		if len(trimmed) >= 3 && (trimmed[0] == '`' || trimmed[0] == '~') {
			run := 0
			for run < len(trimmed) && trimmed[run] == trimmed[0] {
				run++
			}
			if run >= 3 {
				if fenceChar == 0 {
					fenceChar, fenceRun = trimmed[0], run
				} else if trimmed[0] == fenceChar && run >= fenceRun {
					fenceChar, fenceRun = 0, 0
				}
				continue
			}
		}
		if fenceChar != 0 {
			continue
		}
		if nextTitle := heading(line.text); nextTitle != "" {
			appendSection(line.start)
			current, title = line.start, nextTitle
		}
	}
	appendSection(len(raw))
	return sections, nil
}
