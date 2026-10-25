package contextdocument

import (
	"bytes"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// HTMLFormat is the CONTEXT.md frontmatter value that selects HTML knowledge.
const HTMLFormat = "context-format: html"

// MarkerInsert adds the standalone initialization marker after validating the
// CONTEXT activation frontmatter. It grants no approval.
func MarkerInsert(raw []byte) ([]byte, error) { return markerInsert(raw) }

// ValidateBoard checks the task board shape used by initialization.
func ValidateBoard(raw []byte) error { return validateBoard(raw) }

func frontmatterEnd(raw []byte) (int, int, error) {
	lines, err := markdownLines(raw)
	if err != nil || len(lines) < 2 || lines[0].text != "---" {
		return 0, 0, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT frontmatter is malformed")
	}
	for i := 1; i < len(lines); i++ {
		if lines[i].text == "---" {
			return lines[i].start, lines[i].end, nil
		}
	}
	return 0, 0, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT frontmatter is not closed")
}

// IsHTMLFormat reports whether CONTEXT.md selects HTML knowledge.
func IsHTMLFormat(raw []byte) bool {
	start, _, err := frontmatterEnd(raw)
	if err != nil {
		return false
	}
	for _, line := range strings.Split(string(raw[:start]), "\n") {
		if strings.TrimSpace(line) == HTMLFormat {
			return true
		}
	}
	return false
}

// ConvertedContext keeps CONTEXT.md as the small operational owner: its
// frontmatter bytes (with the format line added), the initialization marker
// if present, and a pointer to the narrative. bodyStart is where the old
// narrative began, for the cutover's content check.
func ConvertedContext(raw []byte) (converted []byte, bodyStart int, err error) {
	start, end, err := frontmatterEnd(raw)
	if err != nil {
		return nil, 0, err
	}
	eol := "\n"
	if bytes.Contains(raw[:end], []byte("\r\n")) {
		eol = "\r\n"
	}
	bodyStart = end
	if bodyStart < len(raw) && raw[bodyStart] == '\r' {
		bodyStart++
	}
	if bodyStart < len(raw) && raw[bodyStart] == '\n' {
		bodyStart++
	}
	initialized := false
	for _, line := range strings.Split(string(raw[bodyStart:]), "\n") {
		if strings.TrimSpace(line) == "<!--INITIALIZED-->" {
			initialized = true
		}
	}
	var out bytes.Buffer
	out.Write(raw[:start])
	if !IsHTMLFormat(raw) {
		out.WriteString(HTMLFormat + eol)
	}
	out.WriteString("---" + eol)
	if initialized {
		out.WriteString("<!--INITIALIZED-->" + eol)
	}
	out.WriteString(eol + "Narrative project context is in `.codearbiter/context/project.html`; read it through the artifact engine." + eol)
	return out.Bytes(), bodyStart, nil
}

var controlTag = regexp.MustCompile(`(?i)<!--\s*(/?)\s*(migration-paths|ci-paths|deploy-paths)\s*-->`)

type controlRange struct{ start, end int }

func controlRanges(raw []byte) ([]controlRange, error) {
	type openTag struct {
		kind  string
		start int
	}
	stack := []openTag{}
	ranges := []controlRange{}
	for _, match := range controlTag.FindAllSubmatchIndex(raw, -1) {
		kind := strings.ToLower(string(raw[match[4]:match[5]]))
		if match[2] == match[3] {
			stack = append(stack, openTag{kind, match[0]})
			continue
		}
		if len(stack) == 0 || stack[len(stack)-1].kind != kind {
			return nil, fault.New("INVALID_SCOPE_BLOCK", "operative scope block delimiters are mismatched")
		}
		start := stack[len(stack)-1].start
		stack = stack[:len(stack)-1]
		if len(stack) == 0 {
			ranges = append(ranges, controlRange{start, match[1]})
		}
	}
	if len(stack) != 0 {
		return nil, fault.New("INVALID_SCOPE_BLOCK", "operative scope block is not closed")
	}
	return ranges, nil
}

// ConfigOnlyControls keeps only the operative scope blocks of
// security-controls.md, byte for byte and in order. The narrative moves to
// HTML; nothing in the narrative becomes a control.
func ConfigOnlyControls(raw []byte) ([]byte, error) {
	ranges, err := controlRanges(raw)
	if err != nil {
		return nil, err
	}
	eol := "\n"
	if bytes.Contains(raw, []byte("\r\n")) {
		eol = "\r\n"
	}
	var out bytes.Buffer
	out.WriteString("# Security controls (configuration)" + eol + eol)
	out.WriteString("Operative scope blocks only. The narrative is in `.codearbiter/context/security-controls.html`." + eol)
	for _, match := range ranges {
		out.WriteString(eol)
		out.Write(raw[match.start:match.end])
		out.WriteString(eol)
	}
	return out.Bytes(), nil
}

// HasContent reports whether Markdown from start onward says anything beyond
// blank lines, HTML comments, and operative scope blocks. A heading can carry
// a rule on its own; callers handle generic document titles separately.
func HasContent(raw []byte, start int) bool {
	body := raw[start:]
	if ranges, err := controlRanges(body); err == nil {
		var without bytes.Buffer
		last := 0
		for _, match := range ranges {
			without.Write(body[last:match.start])
			last = match.end
		}
		without.Write(body[last:])
		body = without.Bytes()
	}
	// Remove closed comments without discarding visible text on the same line.
	// An unclosed comment is uncertain content and must receive coverage.
	var visible bytes.Buffer
	for len(body) > 0 {
		open := bytes.Index(body, []byte("<!--"))
		if open < 0 {
			visible.Write(body)
			break
		}
		visible.Write(body[:open])
		body = body[open+4:]
		close := bytes.Index(body, []byte("-->"))
		if close < 0 {
			return true
		}
		body = body[close+3:]
	}
	for _, line := range strings.Split(visible.String(), "\n") {
		t := strings.TrimSpace(line)
		if t != "" && t != "---" {
			return true
		}
	}
	return false
}
