// Package contextdocument validates inert, bounded inputs for the five canonical
// repository context Markdown documents. It neither enrolls a kind nor writes.
package contextdocument

import (
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

const Format = "codearbiter.repository-context/0.1.0"

var fieldID = regexp.MustCompile(`^(?:FIELD|CLAIM)-[A-Z0-9]+(?:-[A-Z0-9]+)*$`)
var digest = regexp.MustCompile(`^[0-9a-f]{64}$`)

var documents = map[string]struct {
	path  string
	kinds map[string]bool
}{
	"CONTEXT":           {".codearbiter/CONTEXT.md", map[string]bool{"identity": true, "fact": true, "source_relationship": true}},
	"tech-stack":        {".codearbiter/tech-stack.md", map[string]bool{"fact": true, "command": true, "source_relationship": true}},
	"coding-standards":  {".codearbiter/coding-standards.md", map[string]bool{"fact": true, "source_relationship": true, "constraint_reference": true}},
	"security-controls": {".codearbiter/security-controls.md", map[string]bool{"fact": true, "source_relationship": true, "constraint_reference": true}},
	"code-map":          {".codearbiter/code-map.md", map[string]bool{"map_entry": true, "source_relationship": true}},
}

type Document struct {
	DocumentID string
	TargetPath string
	Entries    []Entry
}

type Entry struct {
	ID                  string
	Kind                string
	Identity            *Identity
	Fact                *Fact
	Command             *Command
	SourceRelationship  *SourceRelationship
	MapEntry            *MapEntry
	ConstraintReference *ConstraintReference
}

type Identity struct {
	Field, Value string
	EvidenceRefs []string
}
type Fact struct {
	Field, Value, State, SourceRef, ConsumerRef string
	EvidenceRefs                                []string
}
type Invocation struct {
	Kind                 string
	Argv                 []string
	Path, Selector, Text string
}
type Command struct {
	Invocation                  Invocation
	CWD                         string
	Prerequisites, EvidenceRefs []string
	Verification                Verification
}
type Verification struct {
	State          string
	ObservationRef string
	Binding        *Binding
}
type Binding struct {
	SourceSnapshotID      string
	RuntimeRef            string
	LockDigest            string
	PrerequisitesDigest   string
	OracleRef             string
	Argv                  []string
	CWD                   string
	DeclaredPrerequisites []string
	EnvironmentDigest     string
}
type SourceRelationship struct {
	Subject, Relation, ObjectRef string
	EvidenceRefs                 []string
}
type MapEntry struct {
	Concern           string
	Paths             []string
	Role, ConsumerRef string
	EvidenceRefs      []string
}
type ConstraintReference struct {
	SourceRef, Scope, Status string
	EvidenceRefs             []string
}

func closed(value any, required ...string) (map[string]any, error) {
	m, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("object required")
	}
	if len(m) != len(required) {
		return nil, fmt.Errorf("unknown or missing object field")
	}
	for _, key := range required {
		if _, ok := m[key]; !ok {
			return nil, fmt.Errorf("missing field %s", key)
		}
	}
	return m, nil
}

func bounded(value any, limit int) (string, error) {
	s, ok := value.(string)
	if !ok || s == "" || utf8.RuneCountInString(s) > limit || strings.TrimSpace(s) != s || strings.ContainsAny(s, "\r\n") {
		return "", fmt.Errorf("bounded single-line text required")
	}
	return s, nil
}

func text(m map[string]any, key string, limit int) (string, error) { return bounded(m[key], limit) }

func oneOf(s string, allowed ...string) bool {
	for _, item := range allowed {
		if s == item {
			return true
		}
	}
	return false
}

func relative(value any, root bool) (string, error) {
	s, err := bounded(value, 256)
	if err != nil {
		return "", err
	}
	if !validate.Path(s, root) {
		return "", fmt.Errorf("repository-relative path required")
	}
	return s, nil
}

func stringsOf(value any, max, limit int, unique bool) ([]string, error) {
	a, ok := value.([]any)
	if !ok || len(a) > max {
		return nil, fmt.Errorf("bounded array required")
	}
	out, seen := make([]string, 0, len(a)), map[string]bool{}
	for _, item := range a {
		s, err := bounded(item, limit)
		if err != nil || unique && seen[s] {
			return nil, fmt.Errorf("invalid or duplicate array item")
		}
		seen[s] = true
		out = append(out, s)
	}
	return out, nil
}

func refs(m map[string]any) ([]string, error) {
	out, err := stringsOf(m["evidence_refs"], 16, 128, true)
	if err != nil || len(out) == 0 {
		return nil, fmt.Errorf("evidence reference required")
	}
	return out, nil
}

func validateEntry(value any) (Entry, error) {
	m, ok := value.(map[string]any)
	if !ok {
		return Entry{}, fmt.Errorf("typed entry object required")
	}
	kind, err := text(m, "kind", 32)
	if err != nil {
		return Entry{}, err
	}
	keys := map[string][]string{
		"identity":             {"id", "kind", "field", "value", "evidence_refs"},
		"fact":                 {"id", "kind", "field", "value", "state", "source_ref", "consumer_ref", "evidence_refs"},
		"command":              {"id", "kind", "invocation", "cwd", "prerequisites", "verification", "evidence_refs"},
		"source_relationship":  {"id", "kind", "subject", "relation", "object_ref", "evidence_refs"},
		"map_entry":            {"id", "kind", "concern", "paths", "role", "consumer_ref", "evidence_refs"},
		"constraint_reference": {"id", "kind", "source_ref", "scope", "status", "evidence_refs"},
	}
	fields, ok := keys[kind]
	if !ok {
		return Entry{}, fmt.Errorf("unknown entry kind")
	}
	m, err = closed(m, fields...)
	if err != nil {
		return Entry{}, err
	}
	id, err := text(m, "id", 80)
	if err != nil || !fieldID.MatchString(id) {
		return Entry{}, fmt.Errorf("stable field ID required")
	}
	if kind == "fact" && !strings.HasPrefix(id, "CLAIM-") || kind != "fact" && !strings.HasPrefix(id, "FIELD-") {
		return Entry{}, fmt.Errorf("entry ID does not match field ownership kind")
	}
	evidence, err := refs(m)
	if err != nil {
		return Entry{}, err
	}
	entry := Entry{ID: id, Kind: kind}
	switch kind {
	case "identity":
		field, e1 := text(m, "field", 64)
		value, e2 := text(m, "value", 512)
		if e1 != nil || e2 != nil || !oneOf(field, "project_name", "project_purpose", "project_scope") {
			return Entry{}, fmt.Errorf("unsupported identity field")
		}
		entry.Identity = &Identity{field, value, evidence}
	case "fact":
		field, e1 := text(m, "field", 64)
		value, e2 := text(m, "value", 512)
		state, e3 := text(m, "state", 16)
		source, e4 := text(m, "source_ref", 256)
		consumer, e5 := text(m, "consumer_ref", 256)
		if e1 != nil || e2 != nil || e3 != nil || e4 != nil || e5 != nil || !oneOf(field, "runtime", "test_boundary", "coding_pattern", "security_observation", "project_fact") || !oneOf(state, "observed", "inferred", "proposed") {
			return Entry{}, fmt.Errorf("unsupported factual claim")
		}
		entry.Fact = &Fact{field, value, state, source, consumer, evidence}
	case "command":
		invocation, e1 := validateInvocation(m["invocation"])
		cwd, e2 := relative(m["cwd"], true)
		prerequisites, e3 := stringsOf(m["prerequisites"], 16, 128, true)
		verification, e4 := validateVerification(m["verification"], invocation, cwd, prerequisites)
		if e1 != nil || e2 != nil || e3 != nil || e4 != nil {
			return Entry{}, fmt.Errorf("unsupported command declaration")
		}
		entry.Command = &Command{invocation, cwd, prerequisites, evidence, verification}
	case "source_relationship":
		subject, e1 := text(m, "subject", 128)
		relation, e2 := text(m, "relation", 32)
		object, e3 := text(m, "object_ref", 256)
		if e1 != nil || e2 != nil || e3 != nil || !oneOf(relation, "derived_from", "owned_by", "consumed_by") {
			return Entry{}, fmt.Errorf("unsupported source relationship")
		}
		entry.SourceRelationship = &SourceRelationship{subject, relation, object, evidence}
	case "map_entry":
		concern, e1 := text(m, "concern", 128)
		role, e2 := text(m, "role", 256)
		consumer, e3 := text(m, "consumer_ref", 256)
		paths, e4 := stringsOf(m["paths"], 16, 256, true)
		if e1 != nil || e2 != nil || e3 != nil || e4 != nil || len(paths) == 0 {
			return Entry{}, fmt.Errorf("invalid map entry")
		}
		for _, p := range paths {
			if _, err := relative(p, false); err != nil {
				return Entry{}, err
			}
		}
		entry.MapEntry = &MapEntry{concern, paths, role, consumer, evidence}
	case "constraint_reference":
		source, e1 := text(m, "source_ref", 256)
		scope, e2 := relative(m["scope"], true)
		status, e3 := text(m, "status", 32)
		if e1 != nil || e2 != nil || e3 != nil || !oneOf(status, "existing_applicable", "observed_upstream", "proposed_adoption") {
			return Entry{}, fmt.Errorf("unsupported constraint reference")
		}
		entry.ConstraintReference = &ConstraintReference{source, scope, status, evidence}
	}
	return entry, nil
}

func validateInvocation(value any) (Invocation, error) {
	m, ok := value.(map[string]any)
	if !ok {
		return Invocation{}, fmt.Errorf("invocation object required")
	}
	kind, err := text(m, "kind", 32)
	if err != nil {
		return Invocation{}, err
	}
	if kind == "literal_argv" {
		m, err = closed(m, "kind", "argv")
		if err != nil {
			return Invocation{}, err
		}
		argv, err := stringsOf(m["argv"], 32, 512, false)
		if err != nil || len(argv) == 0 {
			return Invocation{}, fmt.Errorf("nonempty argv required")
		}
		exe := strings.ToLower(strings.ReplaceAll(argv[0], "\\", "/"))
		exe = exe[strings.LastIndex(exe, "/")+1:]
		firstSpace := strings.IndexAny(argv[0], " \t")
		firstSeparator := strings.IndexAny(argv[0], "/\\")
		if firstSpace >= 0 && (firstSeparator < 0 || firstSpace < firstSeparator) || oneOf(exe, "sh", "sh.exe", "bash", "bash.exe", "zsh", "zsh.exe", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "env", "env.exe") || strings.HasSuffix(exe, ".bat") || strings.HasSuffix(exe, ".cmd") || strings.ContainsAny(argv[0], "|&;<>\"'") || strings.Contains(argv[0], "=") {
			return Invocation{}, fmt.Errorf("shell declaration needs reference")
		}
		for _, arg := range argv {
			if oneOf(arg, "|", "||", "&&", ";", "<", ">", ">>", "2>", "2>>") {
				return Invocation{}, fmt.Errorf("shell operator needs declaration reference")
			}
		}
		return Invocation{Kind: kind, Argv: argv}, nil
	}
	if kind == "declaration_ref" {
		m, err = closed(m, "kind", "path", "selector", "text")
		if err != nil {
			return Invocation{}, err
		}
		path, e1 := relative(m["path"], false)
		selector, e2 := text(m, "selector", 128)
		declaration, e3 := text(m, "text", 512)
		if e1 != nil || e2 != nil || e3 != nil {
			return Invocation{}, fmt.Errorf("invalid declaration reference")
		}
		return Invocation{Kind: kind, Path: path, Selector: selector, Text: declaration}, nil
	}
	return Invocation{}, fmt.Errorf("unknown invocation kind")
}

func hash(value any) (string, error) {
	s, err := bounded(value, 64)
	if err != nil || !digest.MatchString(s) {
		return "", fmt.Errorf("SHA-256 digest required")
	}
	return s, nil
}

func validateBinding(value any) (*Binding, error) {
	m, err := closed(value, "source_snapshot_id", "runtime_ref", "lock_digest", "prerequisites_digest", "oracle_ref", "argv", "cwd", "declared_prerequisites", "environment_digest")
	if err != nil {
		return nil, err
	}
	source, e1 := hash(m["source_snapshot_id"])
	runtime, e2 := text(m, "runtime_ref", 128)
	lock, e3 := hash(m["lock_digest"])
	prereqDigest, e4 := hash(m["prerequisites_digest"])
	oracle, e5 := text(m, "oracle_ref", 128)
	argv, e6 := stringsOf(m["argv"], 32, 512, false)
	cwd, e7 := relative(m["cwd"], true)
	prerequisites, e8 := stringsOf(m["declared_prerequisites"], 16, 128, true)
	environment, e9 := hash(m["environment_digest"])
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil || e5 != nil || e6 != nil || e7 != nil || e8 != nil || e9 != nil || len(argv) == 0 {
		return nil, fmt.Errorf("invalid observation binding")
	}
	return &Binding{source, runtime, lock, prereqDigest, oracle, argv, cwd, prerequisites, environment}, nil
}

func sameStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func validateVerification(value any, invocation Invocation, cwd string, prerequisites []string) (Verification, error) {
	m, err := closed(value, "state", "observation_ref", "binding")
	if err != nil {
		return Verification{}, err
	}
	state, err := text(m, "state", 16)
	if err != nil {
		return Verification{}, err
	}
	if oneOf(state, "declared", "unknown") {
		if m["observation_ref"] != nil || m["binding"] != nil {
			return Verification{}, fmt.Errorf("unobserved command carries observation claim")
		}
		return Verification{State: state}, nil
	}
	if !oneOf(state, "passed", "failed") || invocation.Kind != "literal_argv" {
		return Verification{}, fmt.Errorf("unsupported verified command claim")
	}
	observation, e1 := text(m, "observation_ref", 128)
	binding, e2 := validateBinding(m["binding"])
	if e1 != nil || e2 != nil || binding.CWD != cwd || !sameStrings(binding.Argv, invocation.Argv) || !sameStrings(binding.DeclaredPrerequisites, prerequisites) {
		return Verification{}, fmt.Errorf("observation binding does not match declared command")
	}
	return Verification{State: state, ObservationRef: observation, Binding: binding}, nil
}

// Validate parses one inert input. References are preserved as claims for later
// provenance checks; neither this function nor its result grants authority.
func Validate(data []byte) (Document, error) {
	root, err := canonical.Object(data)
	if err != nil {
		return Document{}, err
	}
	root, err = closed(root, "format", "document_id", "entries")
	if err != nil {
		return Document{}, err
	}
	if root["format"] != Format {
		return Document{}, fmt.Errorf("unsupported context format")
	}
	id, err := text(root, "document_id", 32)
	if err != nil {
		return Document{}, err
	}
	contract, ok := documents[id]
	if !ok {
		return Document{}, fmt.Errorf("unknown repository context document")
	}
	values, ok := root["entries"].([]any)
	if !ok || len(values) == 0 || len(values) > 256 {
		return Document{}, fmt.Errorf("bounded nonempty entries required")
	}
	doc := Document{DocumentID: id, TargetPath: contract.path, Entries: make([]Entry, 0, len(values))}
	seen := map[string]bool{}
	for _, value := range values {
		entry, err := validateEntry(value)
		if err != nil {
			return Document{}, err
		}
		if !contract.kinds[entry.Kind] || seen[entry.ID] {
			return Document{}, fmt.Errorf("entry kind or ID is invalid for document")
		}
		seen[entry.ID] = true
		doc.Entries = append(doc.Entries, entry)
	}
	return doc, nil
}
