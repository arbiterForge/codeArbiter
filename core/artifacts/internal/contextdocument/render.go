package contextdocument

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html"
	"regexp"
	"sort"
	"strings"
)

// PreviewSelection is an inert request for one parsed candidate. It conveys no ownership.
type PreviewSelection struct{ EntryID, Anchor string }

// PreviewChange names an exact span in the original bytes and its replacement.
type PreviewChange struct {
	EntryID, Kind, Field, Anchor string
	Span                         ByteSpan
	Old, New                     string
}

// Preview contains proposed bytes and diffs only; it performs no filesystem write.
type Preview struct {
	DocumentID, TargetPath, BeforeSHA256, AfterSHA256 string
	Bytes                                             []byte
	ProposedEntries                                   []Entry
	Changes                                           []PreviewChange
}

var simpleShellArg = regexp.MustCompile("^[A-Za-z0-9_./:=+@%-]+$")

func previewHash(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func shellWord(value string) string {
	if simpleShellArg.MatchString(value) {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}

func entryField(entry Entry) string {
	switch entry.Kind {
	case "identity":
		return entry.Identity.Field
	case "fact":
		return entry.Fact.Field
	default:
		return "_"
	}
}

func markdownText(value string) string {
	return strings.NewReplacer("\\", "\\\\", "`", "\\`", "*", "\\*", "_", "\\_", "[", "\\[", "]", "\\]", "#", "\\#", "!", "\\!", "|", "\\|").Replace(html.EscapeString(value))
}

func codeSpan(value string) string {
	longest, current := 0, 0
	for _, ch := range value {
		if ch == '`' {
			current++
			if current > longest {
				longest = current
			}
		} else {
			current = 0
		}
	}
	delimiter := strings.Repeat("`", longest+1)
	if strings.HasPrefix(value, "`") || strings.HasSuffix(value, "`") {
		value = " " + value + " "
	}
	return delimiter + value + delimiter
}

// Map entries keep their concern, paths and one-line role together inside the
// owned span. Changing a concern cannot leave a stale unowned section heading.
// Other typed entries retain inert, HTML-escaped JSON on one line.
func managedLine(entry Entry) (string, error) {
	if entry.Kind == "map_entry" {
		paths := make([]string, len(entry.MapEntry.Paths))
		for i, path := range entry.MapEntry.Paths {
			paths[i] = codeSpan(path)
		}
		return "- **" + markdownText(entry.MapEntry.Concern) + "**: " + strings.Join(paths, ", ") + " — " + markdownText(entry.MapEntry.Role) + " (consumer: " + codeSpan(entry.MapEntry.ConsumerRef) + "; evidence: " + markdownText(strings.Join(entry.MapEntry.EvidenceRefs, ", ")) + ")", nil
	}
	data, err := json.Marshal(entry)
	if err != nil {
		return "", err
	}
	return "- `" + entry.ID + "`: " + string(data), nil
}

func legacyLine(entry Entry, candidate MarkdownCandidate) (string, error) {
	switch candidate.Anchor {
	case "project_name":
		if entry.Kind == "identity" && entry.Identity.Field == "project_name" {
			return html.EscapeString(entry.Identity.Value), nil
		}
	case "coding_pattern:line_endings":
		if entry.Kind == "fact" && entry.Fact.Field == "coding_pattern" {
			return html.EscapeString(entry.Fact.Value), nil
		}
	case "security_observation:approved_crypto", "security_observation:forbidden_crypto":
		if entry.Kind == "fact" && entry.Fact.Field == "security_observation" {
			return html.EscapeString(entry.Fact.Value), nil
		}
	default:
		if strings.HasPrefix(candidate.Anchor, "map:") && entry.Kind == "map_entry" && len(entry.MapEntry.Paths) == 1 && candidate.Anchor == "map:"+entry.MapEntry.Concern+":"+entry.MapEntry.Paths[0] {
			return html.EscapeString(entry.MapEntry.Role), nil
		}
		if strings.HasPrefix(candidate.Anchor, "test_command:") && entry.Kind == "command" {
			command := entry.Command
			if command.Invocation.Kind != "literal_argv" {
				return "", fmt.Errorf("legacy command line requires literal argv")
			}
			words := make([]string, len(command.Invocation.Argv))
			for i, arg := range command.Invocation.Argv {
				words[i] = shellWord(arg)
			}
			state := command.Verification.State
			if state == "passed" || state == "failed" {
				state = "historical_" + state
			}
			return strings.Join(words, " ") + " # cwd=" + shellWord(command.CWD) + " state=" + state + " prerequisites=" + shellWord(strings.Join(command.Prerequisites, ",")) + " evidence=" + shellWord(strings.Join(command.EvidenceRefs, ",")), nil
		}
	}
	return "", fmt.Errorf("typed entry %s cannot replace legacy anchor %q", entry.ID, candidate.Anchor)
}

func renderCandidate(entry Entry, candidate MarkdownCandidate) (string, error) {
	if candidate.Kind != entry.Kind || candidate.Field != "" && candidate.Field != entryField(entry) {
		return "", fmt.Errorf("entry %s does not match candidate kind/field", entry.ID)
	}
	if candidate.Anchor == "entry:"+entry.ID {
		return managedLine(entry)
	}
	if strings.HasPrefix(candidate.Anchor, "entry:") {
		return "", fmt.Errorf("entry %s does not match field marker", entry.ID)
	}
	return legacyLine(entry, candidate)
}

func templateTitle(doc Document) (string, error) {
	switch doc.DocumentID {
	case "CONTEXT":
		for _, entry := range doc.Entries {
			if entry.Kind == "identity" && entry.Identity.Field == "project_name" {
				return "# Project: " + html.EscapeString(entry.Identity.Value), nil
			}
		}
		return "", fmt.Errorf("missing CONTEXT template requires project_name")
	case "tech-stack":
		return "# Tech stack", nil
	case "coding-standards":
		return "# Coding standards", nil
	case "security-controls":
		return "# Security controls", nil
	case "code-map":
		return "# Code map", nil
	}
	return "", fmt.Errorf("unknown document template")
}

func renderTemplate(doc Document) ([]byte, error) {
	if doc.DocumentID == "code-map" && countMapEntries(doc.Entries) > 50 {
		return nil, fmt.Errorf("code map exceeds 50 entries")
	}
	title, err := templateTitle(doc)
	if err != nil {
		return nil, err
	}
	var out strings.Builder
	if doc.DocumentID == "CONTEXT" {
		out.WriteString("---\n---\n")
	}
	out.WriteString(title + "\n\n")
	for _, entry := range doc.Entries {
		if doc.DocumentID == "CONTEXT" && entry.Kind == "identity" && entry.Identity.Field == "project_name" {
			continue
		}
		line, err := managedLine(entry)
		if err != nil {
			return nil, err
		}
		out.WriteString("<!-- ca:field " + entry.ID + " " + entry.Kind + " " + entryField(entry) + " -->\n")
		out.WriteString(line + "\n")
		out.WriteString("<!-- ca:end-field " + entry.ID + " -->\n\n")
	}
	result := []byte(out.String())
	if doc.DocumentID == "code-map" && len(result) > 20*1024 {
		return nil, fmt.Errorf("code map exceeds 20 KiB")
	}
	if _, err := ParseMarkdown(doc.DocumentID, result); err != nil {
		return nil, fmt.Errorf("rendered template is unsupported: %w", err)
	}
	return result, nil
}

func countMapEntries(entries []Entry) int {
	count := 0
	for _, entry := range entries {
		if entry.Kind == "map_entry" {
			count++
		}
	}
	return count
}

func countMapCandidates(candidates []MarkdownCandidate) int {
	count := 0
	for _, candidate := range candidates {
		if candidate.Kind == "map_entry" {
			count++
		}
	}
	return count
}

// RenderPreview validates raw typed input, reparses source, and proposes only
// selected candidate replacements or a deterministic missing-file template.
// The exists flag distinguishes absent files from present empty files.
func RenderPreview(input, source []byte, exists bool, selections []PreviewSelection) (Preview, error) {
	doc, err := Validate(input)
	if err != nil {
		return Preview{}, err
	}
	identities := map[string]bool{}
	for _, entry := range doc.Entries {
		if entry.Kind == "identity" {
			if identities[entry.Identity.Field] {
				return Preview{}, fmt.Errorf("duplicate singular identity field %q", entry.Identity.Field)
			}
			identities[entry.Identity.Field] = true
		}
	}
	if !exists {
		if len(source) != 0 || len(selections) != 0 {
			return Preview{}, fmt.Errorf("missing-file preview cannot select existing bytes")
		}
		result, err := renderTemplate(doc)
		if err != nil {
			return Preview{}, err
		}
		return Preview{DocumentID: doc.DocumentID, TargetPath: doc.TargetPath, AfterSHA256: previewHash(result), Bytes: result, ProposedEntries: doc.Entries,
			Changes: []PreviewChange{{Kind: "create", Span: ByteSpan{0, 0}, New: string(result)}}}, nil
	}
	original := bytes.Clone(source)
	if doc.DocumentID == "code-map" && len(original) > 20*1024 {
		return Preview{}, fmt.Errorf("existing code map exceeds 20 KiB; preserve and diagnose")
	}
	parsed, err := ParseMarkdown(doc.DocumentID, original)
	if err != nil {
		return Preview{}, err
	}
	if len(selections) != len(doc.Entries) {
		return Preview{}, fmt.Errorf("each typed entry needs one candidate selection")
	}
	byID := make(map[string]Entry, len(doc.Entries))
	for _, entry := range doc.Entries {
		byID[entry.ID] = entry
	}
	byAnchor := make(map[string]MarkdownCandidate, len(parsed.Candidates))
	for _, candidate := range parsed.Candidates {
		byAnchor[candidate.Anchor] = candidate
	}
	seenIDs, seenAnchors := map[string]bool{}, map[string]bool{}
	changes := make([]PreviewChange, 0, len(selections))
	for _, selection := range selections {
		entry, ok := byID[selection.EntryID]
		if !ok || seenIDs[selection.EntryID] || seenAnchors[selection.Anchor] {
			return Preview{}, fmt.Errorf("unknown or duplicate preview selection")
		}
		candidate, ok := byAnchor[selection.Anchor]
		if !ok {
			return Preview{}, fmt.Errorf("unrecognized Markdown anchor %q", selection.Anchor)
		}
		seenIDs[selection.EntryID], seenAnchors[selection.Anchor] = true, true
		newLine, err := renderCandidate(entry, candidate)
		if err != nil {
			return Preview{}, err
		}
		oldLine := string(original[candidate.Span.Start:candidate.Span.End])
		if newLine != oldLine {
			changes = append(changes, PreviewChange{EntryID: entry.ID, Kind: entry.Kind, Field: entryField(entry), Anchor: candidate.Anchor, Span: candidate.Span, Old: oldLine, New: newLine})
		}
	}
	sort.Slice(changes, func(i, j int) bool { return changes[i].Span.Start < changes[j].Span.Start })
	var result bytes.Buffer
	last := 0
	for _, change := range changes {
		result.Write(original[last:change.Span.Start])
		result.WriteString(change.New)
		last = change.Span.End
	}
	result.Write(original[last:])
	output := result.Bytes()
	if doc.DocumentID == "code-map" && (len(output) > 20*1024 || countMapCandidates(parsed.Candidates) > 50) {
		return Preview{}, fmt.Errorf("code map exceeds 20 KiB or 50 entries")
	}
	if _, err := ParseMarkdown(doc.DocumentID, output); err != nil {
		return Preview{}, fmt.Errorf("proposed Markdown is unsupported: %w", err)
	}
	return Preview{DocumentID: doc.DocumentID, TargetPath: doc.TargetPath, BeforeSHA256: previewHash(original), AfterSHA256: previewHash(output), Bytes: bytes.Clone(output), ProposedEntries: doc.Entries, Changes: changes}, nil
}
