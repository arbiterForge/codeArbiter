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

var controlBlock = regexp.MustCompile(`(?is)<!--\s*(migration-paths|ci-paths|deploy-paths)\s*-->.*?<!--\s*/(migration-paths|ci-paths|deploy-paths)\s*-->`)

// ConfigOnlyControls keeps only the operative scope blocks of
// security-controls.md, byte for byte and in order. The narrative moves to
// HTML; nothing in the narrative becomes a control.
func ConfigOnlyControls(raw []byte) []byte {
	eol := "\n"
	if bytes.Contains(raw, []byte("\r\n")) {
		eol = "\r\n"
	}
	var out bytes.Buffer
	out.WriteString("# Security controls (configuration)" + eol + eol)
	out.WriteString("Operative scope blocks only. The narrative is in `.codearbiter/context/security-controls.html`." + eol)
	for _, match := range controlBlock.FindAll(raw, -1) {
		out.WriteString(eol)
		out.Write(match)
		out.WriteString(eol)
	}
	return out.Bytes()
}

// HasContent reports whether Markdown from start onward says anything beyond
// headings, blank lines, HTML comments, the initialization marker and the
// operative scope blocks. A cutover requires such content to have been
// recorded before its file is removed.
func HasContent(raw []byte, start int) bool {
	body := controlBlock.ReplaceAll(raw[start:], nil)
	comment := false
	for _, line := range strings.Split(string(body), "\n") {
		t := strings.TrimSpace(line)
		if comment {
			comment = !strings.Contains(t, "-->")
			continue
		}
		switch {
		case t == "", strings.HasPrefix(t, "#"), t == "---":
		case strings.HasPrefix(t, "<!--"):
			comment = !strings.Contains(t, "-->")
		default:
			return true
		}
	}
	return false
}
