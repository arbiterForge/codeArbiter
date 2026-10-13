package contextdocument

import (
	"bytes"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// Finalization is an exact, closed snapshot of the five content/provenance
// pairs and the independently written task, question and audit files.
type Finalization struct {
	OperationID string
	Expected    map[string]string
}

type FinalizationPreview struct {
	Binding          string
	BeforeDocument   []byte
	BeforeProvenance []byte
	Document         []byte
	Provenance       []byte
}

var finalizationDocuments = []string{"CONTEXT", "tech-stack", "coding-standards", "security-controls", "code-map"}
var finalizationIndependent = []string{".codearbiter/open-tasks.md", ".codearbiter/open-questions.md", ".codearbiter/overrides.log"}
var taskLine = regexp.MustCompile(`^- \[[ ~xX]\] \S`)
var taskID = regexp.MustCompile(`^- \[[ ~xX]\] ([a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[0-9]{4,}) - \S`)
var questionLine = regexp.MustCompile(`^(?:- )?(?:\[)?(CONFIRM-[0-9]{2,})(?:\])?(?::|\s+-)?\s+\S`)
var questionRef = regexp.MustCompile(`\[CONFIRM-[0-9]{2,}\]`)
var auditLine = regexp.MustCompile(`^(?:\[[0-9]{4}-[0-9]{2}-[0-9]{2}T[^]]+\]|[0-9]{4}-[0-9]{2}-[0-9]{2}T\S+) \| BY: [^|]+ \| (?:[A-Z][A-Z-]*:|SECURITY-OVERRIDE)(?: .*)?$`)

func finalizationPaths() []string {
	paths := make([]string, 0, 13)
	for _, id := range finalizationDocuments {
		paths = append(paths, ".codearbiter/"+id+".md", ".codearbiter/.provenance/"+id+".json")
	}
	return append(paths, finalizationIndependent...)
}

func finalizationBinding(r Finalization) (string, error) {
	if len(r.Expected) != len(finalizationPaths()) {
		return "", fault.New("INVALID_CONTEXT_FINALIZATION", "all required output identities are required")
	}
	for _, path := range finalizationPaths() {
		if !digest.MatchString(r.Expected[path]) {
			return "", fault.New("INVALID_CONTEXT_FINALIZATION", "required output identity is missing or malformed")
		}
	}
	expected := map[string]any{}
	for path, hash := range r.Expected {
		expected[path] = hash
	}
	return canonical.Hash(map[string]any{"renderer": "codearbiter.context-finalization/0.1.0", "operation_id": r.OperationID, "expected": expected})
}

func finalizationLines(raw []byte) ([]string, error) {
	lines, err := markdownLines(raw)
	if err != nil {
		return nil, err
	}
	result := make([]string, len(lines))
	for i, line := range lines {
		result[i] = line.text
	}
	return result, nil
}

func validateBoard(raw []byte) error {
	lines, err := finalizationLines(raw)
	if err != nil || len(lines) == 0 || lines[0] != "# Open tasks" {
		return fault.New("INVALID_CONTEXT_OUTPUT", "task board is missing or malformed")
	}
	seen := map[string]bool{}
	fenced := false
	for _, line := range lines[1:] {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "```") || strings.HasPrefix(trimmed, "~~~") {
			fenced = !fenced
			continue
		}
		if fenced || !strings.HasPrefix(line, "- [") {
			continue
		}
		if !taskLine.MatchString(line) {
			return fault.New("INVALID_CONTEXT_OUTPUT", "task board entry is malformed or duplicated")
		}
		if match := taskID.FindStringSubmatch(line); match != nil {
			if seen[match[1]] {
				return fault.New("INVALID_CONTEXT_OUTPUT", "task board entry is malformed or duplicated")
			}
			seen[match[1]] = true
		}
	}
	if fenced {
		return fault.New("INVALID_CONTEXT_OUTPUT", "task board has an unterminated example fence")
	}
	return nil
}

func validateQuestions(raw []byte) (map[string]bool, error) {
	lines, err := finalizationLines(raw)
	if err != nil || len(lines) == 0 || lines[0] != "# Open questions" {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "question board is missing or malformed")
	}
	seen := map[string]bool{}
	for _, line := range lines[1:] {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") || trimmed == "_None open._" {
			continue
		}
		if !strings.HasPrefix(trimmed, "CONFIRM-") && !strings.HasPrefix(trimmed, "- [CONFIRM-") && !strings.HasPrefix(trimmed, "[CONFIRM-") {
			continue // existing explanatory scaffold prose is not a question entry
		}
		match := questionLine.FindStringSubmatch(trimmed)
		if match == nil || seen[match[1]] {
			return nil, fault.New("INVALID_CONTEXT_OUTPUT", "question board entry is malformed or duplicated")
		}
		seen[match[1]] = true
	}
	return seen, nil
}

func validateAudit(raw []byte) error {
	lines, err := finalizationLines(raw)
	if err != nil || len(lines) == 0 || !strings.HasPrefix(lines[0], "# codeArbiter override log") {
		return fault.New("INVALID_CONTEXT_OUTPUT", "override audit header is missing or malformed")
	}
	for _, line := range lines[1:] {
		if strings.TrimSpace(line) == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if !auditLine.MatchString(line) || !strings.Contains(line, " | ") {
			return fault.New("INVALID_CONTEXT_OUTPUT", "override audit event is malformed")
		}
	}
	return nil
}

func markerInsert(raw []byte) ([]byte, error) {
	lines, err := markdownLines(raw)
	if err != nil || len(lines) < 4 || lines[0].text != "---" {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT frontmatter is malformed")
	}
	end, enabled, stage := -1, 0, 0
	for i := 1; i < len(lines); i++ {
		if lines[i].text == "---" {
			end = i
			break
		}
		if lines[i].text == "arbiter: enabled" {
			enabled++
		}
		if strings.HasPrefix(lines[i].text, "stage: ") {
			if oneOf(strings.TrimPrefix(lines[i].text, "stage: "), "1", "2", "3", "4") {
				stage++
			} else {
				return nil, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT stage is invalid")
			}
		}
	}
	if end < 0 || enabled != 1 || stage != 1 {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT activation and maturity are required")
	}
	if err := classifyMarkdown(lines); err != nil {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", err.Error())
	}
	for i := end + 1; i < len(lines); i++ {
		if lines[i].visible && lines[i].fence == "" && lines[i].text == "<!--INITIALIZED-->" {
			return nil, fault.New("ALREADY_INITIALIZED", "CONTEXT is already initialized")
		}
	}
	insert := lines[end].end
	eol := []byte("\n")
	if insert < len(raw) && raw[insert] == '\r' {
		eol = []byte("\r\n")
	}
	if insert+len(eol) > len(raw) || !bytes.Equal(raw[insert:insert+len(eol)], eol) {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT frontmatter must end before body")
	}
	insert += len(eol)
	out := make([]byte, 0, len(raw)+len("<!--INITIALIZED-->")+len(eol))
	out = append(out, raw[:insert]...)
	out = append(out, []byte("<!--INITIALIZED-->")...)
	out = append(out, eol...)
	out = append(out, raw[insert:]...)
	return out, nil
}

func visibleQuestionRefs(raw []byte) ([]string, error) {
	lines, err := markdownLines(raw)
	if err != nil {
		return nil, err
	}
	if err := classifyMarkdown(lines); err != nil {
		return nil, err
	}
	refs := []string{}
	for _, line := range lines {
		if !line.visible || line.fence != "" || strings.HasPrefix(strings.TrimSpace(line.text), "<!--") {
			continue
		}
		for _, ref := range questionRef.FindAllString(line.text, -1) {
			refs = append(refs, strings.Trim(ref, "[]"))
		}
	}
	return refs, nil
}

// PreviewFinalization is read-only. It reacquires every declared output and
// every cited source through the same repository store used by Apply.
func PreviewFinalization(f *store.FS, r Finalization) (FinalizationPreview, error) {
	if f == nil {
		return FinalizationPreview{}, fault.New("INVALID_CONTEXT_FINALIZATION", "repository store is required")
	}
	binding, err := finalizationBinding(r)
	if err != nil {
		return FinalizationPreview{}, err
	}
	actual := map[string][]byte{}
	for _, path := range finalizationPaths() {
		body, err := f.Read(path, canonical.MaxBytes)
		if err != nil {
			if os.IsNotExist(err) {
				return FinalizationPreview{}, fault.New("INVALID_CONTEXT_OUTPUT", "required context output is absent")
			}
			return FinalizationPreview{}, err
		}
		if canonical.BytesHash(body) != r.Expected[path] {
			return FinalizationPreview{}, fault.New("REVISION_CONFLICT", "context output changed after preview")
		}
		actual[path] = body
	}
	if err := validateBoard(actual[".codearbiter/open-tasks.md"]); err != nil {
		return FinalizationPreview{}, err
	}
	questions, err := validateQuestions(actual[".codearbiter/open-questions.md"])
	if err != nil {
		return FinalizationPreview{}, err
	}
	if err := validateAudit(actual[".codearbiter/overrides.log"]); err != nil {
		return FinalizationPreview{}, err
	}
	for _, id := range finalizationDocuments {
		path, provPath := ".codearbiter/"+id+".md", ".codearbiter/.provenance/"+id+".json"
		body := actual[path]
		parsed, err := ParseMarkdown(id, body)
		if err != nil {
			return FinalizationPreview{}, fault.New("INVALID_CONTEXT_OUTPUT", fmt.Sprintf("%s: %v", id, err))
		}
		preview := Preview{DocumentID: id, TargetPath: path, AfterSHA256: canonical.BytesHash(body)}
		_, fields, err := parseProvenanceV2(actual[provPath], preview)
		if err != nil {
			return FinalizationPreview{}, err
		}
		owners := map[string]bool{}
		for _, candidate := range parsed.Candidates {
			owners[candidate.Anchor] = true
		}
		for _, field := range fields {
			if !owners[model.S(field["owner_ref"])] {
				return FinalizationPreview{}, fault.New("OWNERSHIP_REQUIRED", "context provenance names no current field")
			}
		}
		if err := ValidateCurrentEvidence(f, actual[provPath], preview); err != nil {
			return FinalizationPreview{}, err
		}
		refs, err := visibleQuestionRefs(body)
		if err != nil {
			return FinalizationPreview{}, fault.New("INVALID_CONTEXT_OUTPUT", "context question syntax is malformed")
		}
		for _, ref := range refs {
			if !questions[ref] {
				return FinalizationPreview{}, fault.New("UNADDRESSED_CONTEXT_GAP", "context gap lacks a question-board record")
			}
		}
	}
	marker, err := markerInsert(actual[".codearbiter/CONTEXT.md"])
	if err != nil {
		return FinalizationPreview{}, err
	}
	provenance, err := canonical.Object(actual[".codearbiter/.provenance/CONTEXT.json"])
	if err != nil {
		return FinalizationPreview{}, fault.New("PROVENANCE_CONFLICT", "CONTEXT provenance is malformed")
	}
	model.M(provenance["document"])["digest"] = canonical.BytesHash(marker)
	updated, err := canonical.Marshal(provenance)
	if err != nil {
		return FinalizationPreview{}, err
	}
	return FinalizationPreview{Binding: binding,
		BeforeDocument:   bytes.Clone(actual[".codearbiter/CONTEXT.md"]),
		BeforeProvenance: bytes.Clone(actual[".codearbiter/.provenance/CONTEXT.json"]),
		Document:         marker, Provenance: updated}, nil
}

// Finalize commits only the marker and its provenance pair after exact review.
// The caller must hold the store's writer lock; independent outputs are read
// again immediately before the two-file CAS transaction.
func Finalize(f *store.FS, r Finalization, approved VerifiedAuthority) (store.Outcome, error) {
	binding, err := finalizationBinding(r)
	if err != nil {
		return store.Outcome{}, err
	}
	if replay, err := f.Lookup(r.OperationID, binding); err != nil {
		return store.Outcome{}, err
	} else if replay != nil {
		return *replay, nil
	}
	if approved == nil || approved.mutationBinding() != binding {
		return store.Outcome{}, fault.New("AUTHORITY_REQUIRED", "exact finalization preview lacks owning-workflow approval")
	}
	preview, err := PreviewFinalization(f, r)
	if err != nil {
		return store.Outcome{}, err
	}
	// Recheck all source/output identities after validation and before Commit.
	if _, err := PreviewFinalization(f, r); err != nil {
		return store.Outcome{}, err
	}
	doc, prov := ".codearbiter/CONTEXT.md", ".codearbiter/.provenance/CONTEXT.json"
	if f.Inject != nil {
		if err := f.Inject("before-finalize-commit"); err != nil {
			return store.Outcome{}, err
		}
	}
	result := map[string]any{"document_id": "CONTEXT", "target_path": doc, "document_sha256": canonical.BytesHash(preview.Document), "provenance_sha256": canonical.BytesHash(preview.Provenance), "mode": "finalize"}
	return f.Commit(r.OperationID, binding, []store.Edit{{Path: doc, Before: preview.BeforeDocument, After: preview.Document}, {Path: prov, Before: preview.BeforeProvenance, After: preview.Provenance}}, result)
}

func FinalizeWithReceipt(f *store.FS, r Finalization, receipt string) (store.Outcome, error) {
	binding, err := finalizationBinding(r)
	if err != nil {
		return store.Outcome{}, err
	}
	if replay, err := f.Lookup(r.OperationID, binding); err != nil {
		return store.Outcome{}, err
	} else if replay != nil {
		return *replay, nil
	}
	if err := authority.ValidateContextPreview(f, receipt, binding); err != nil {
		return store.Outcome{}, err
	}
	return Finalize(f, r, verifiedAuthority{binding: binding})
}
