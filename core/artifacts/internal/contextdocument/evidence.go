package contextdocument

import (
	"os"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// T-008's seven finite membership selectors. This implementation supports
// ASCII path components only: Unicode casefold/NFC must use the Python owner,
// never a silently different Go approximation.
var memberNames = map[string]map[string]bool{
	"manifests":      {"package.json": true, "pyproject.toml": true, "cargo.toml": true, "go.mod": true, "pom.xml": true, "build.gradle": true, "build.gradle.kts": true, "requirements.txt": true, "pipfile": true, "gemfile": true, "composer.json": true},
	"instructions":   {"agents.md": true, "claude.md": true, "gemini.md": true, "copilot-instructions.md": true},
	"configuration":  {".editorconfig": true, ".gitattributes": true, "tsconfig.json": true, "pytest.ini": true, "tox.ini": true, "setup.cfg": true, "mypy.ini": true},
	"tests":          {},
	"infrastructure": {"dockerfile": true, "compose.yaml": true, "compose.yml": true},
	"security":       {"security.md": true, "codeowners": true, "dependabot.yml": true, "dependabot.yaml": true},
	"data":           {"schema.sql": true, "schema.prisma": true},
}
var memberDirectories = map[string]map[string]bool{
	"tests":          {"tests": true, "test": true, "__tests__": true},
	"infrastructure": {"infra": true, "infrastructure": true, "workflows": true},
	"security":       {"security": true},
	"data":           {"migrations": true, "schemas": true},
}
var memberVendor = map[string]bool{"vendor": true, "node_modules": true, "third_party": true}
var memberGenerated = map[string]bool{"generated": true, "dist": true, "build": true, "__pycache__": true, "target": true}
var sensitiveNames = map[string]bool{".env": true, ".ssh": true, ".aws": true, ".gnupg": true, ".npmrc": true, ".pypirc": true, "credentials": true, "credentials.json": true, "id_rsa": true, "id_ed25519": true, "known_hosts": true, "secrets.json": true}

func contentEvidencePath(path string) bool {
	if !memberPath(path, false) {
		return false
	}
	for _, part := range strings.Split(path, "/") {
		name := strings.ToLower(part)
		if sensitiveNames[name] || strings.HasPrefix(name, ".env.") || strings.HasSuffix(name, ".pem") || strings.HasSuffix(name, ".key") || strings.HasSuffix(name, ".p12") || strings.HasSuffix(name, ".pfx") {
			return false
		}
	}
	return true
}

func memberPath(path string, root bool) bool {
	if len(path) == 0 || len(path) > 1024 || !validate.Path(path, root) {
		return false
	}
	if path == "." {
		return root
	}
	for _, r := range path {
		if r > 127 || r < 32 || r == 127 {
			return false
		}
	}
	for _, component := range strings.Split(path, "/") {
		if strings.EqualFold(component, ".git") {
			return false
		}
	}
	return true
}
func memberWithin(path, parent string) bool {
	return parent == "." || path == parent || strings.HasPrefix(path, parent+"/")
}
func memberMatch(predicate, relative string, directory bool) bool {
	name := strings.ToLower(relative[strings.LastIndex(relative, "/")+1:])
	if directory {
		return memberDirectories[predicate][name]
	}
	if memberNames[predicate][name] {
		return true
	}
	switch predicate {
	case "manifests":
		return strings.HasSuffix(name, ".csproj") || strings.HasSuffix(name, ".fsproj") || strings.HasSuffix(name, ".vbproj")
	case "tests":
		return strings.HasPrefix(name, "test_") && strings.HasSuffix(name, ".py") || strings.HasSuffix(name, ".test.ts") || strings.HasSuffix(name, ".test.tsx") || strings.HasSuffix(name, ".test.js") || strings.HasSuffix(name, ".test.jsx") || strings.HasSuffix(name, ".spec.ts") || strings.HasSuffix(name, ".spec.js")
	case "infrastructure":
		return strings.HasSuffix(name, ".tf") || strings.HasSuffix(name, ".tfvars")
	case "data":
		return strings.HasSuffix(name, ".sql") || strings.HasSuffix(name, ".prisma")
	}
	return false
}
func memberSort(paths []string) {
	sort.Slice(paths, func(i, j int) bool {
		a, b := strings.ToLower(paths[i]), strings.ToLower(paths[j])
		if a == b {
			return paths[i] < paths[j]
		}
		return a < b
	})
}

func memberEntries(f *store.FS, relative string) ([]os.DirEntry, error) {
	entries, err := f.ListUnfollowed(relative)
	if err != nil {
		return nil, fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership scope is unavailable")
	}
	count := len(entries)
	if relative == "." {
		for _, entry := range entries {
			if entry.Name() == ".git" {
				count--
				break
			}
		}
	}
	if count > 1152 {
		return nil, fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership directory exceeds its bound")
	}
	seen := map[string]bool{}
	for _, entry := range entries {
		name := entry.Name()
		if name == ".git" {
			continue
		}
		if !memberPath(name, false) || strings.Contains(name, "/") {
			return nil, fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "membership path requires exact ASCII grammar")
		}
		folded := strings.ToLower(name)
		if seen[folded] {
			return nil, fault.New("SOURCE_EVIDENCE_UNKNOWN", "case-colliding membership entries")
		}
		seen[folded] = true
		if entry.Type()&os.ModeSymlink != 0 {
			return nil, fault.New("SOURCE_EVIDENCE_UNKNOWN", "linked membership entry is unreadable")
		}
	}
	return entries, nil
}

func memberBoundary(f *store.FS, relative string) (string, error) {
	if relative == "." {
		return "", nil
	}
	current := ""
	for _, part := range strings.Split(relative, "/") {
		if current == "" {
			current = part
		} else {
			current += "/" + part
		}
		entries, err := memberEntries(f, current)
		if err != nil {
			return "", err
		}
		folded := strings.ToLower(part)
		if memberVendor[folded] {
			return "vendor", nil
		}
		if memberGenerated[folded] {
			return "generated", nil
		}
		for _, entry := range entries {
			if entry.Name() != ".git" {
				continue
			}
			info, err := f.Stat(current + "/.git")
			if err != nil || info.Mode()&os.ModeSymlink != 0 {
				return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "nested repository marker is unreadable")
			}
			if info.IsDir() {
				return "nested_repository", nil
			}
			if info.Mode().IsRegular() {
				return "submodule", nil
			}
			return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "nested repository marker is unreadable")
		}
	}
	return "", nil
}

// MembershipDigest reproduces T-008's sha256-membership-v1 for the exact
// ASCII subset. It has the same 1024 file/128 directory default bounds,
// vendor/generated/nested-repository dispositions and sorted JSON identity.
// Unreadable or unsupported names return no digest.
func MembershipDigest(f *store.FS, predicate string, scopes []string) (string, error) {
	if f == nil {
		return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "repository store is required")
	}
	if _, ok := memberNames[predicate]; !ok {
		return "", fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "unknown membership predicate")
	}
	if len(scopes) == 0 || len(scopes) > 16 {
		return "", fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "membership scope count is unsupported")
	}
	orderedScopes := append([]string{}, scopes...)
	sort.Strings(orderedScopes) // Python sorts declared scope paths before traversal.
	for i, scope := range orderedScopes {
		if !memberPath(scope, true) {
			return "", fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "membership scope requires exact ASCII grammar")
		}
		for _, other := range orderedScopes[:i] {
			a, b := strings.ToLower(scope), strings.ToLower(other)
			if memberWithin(a, b) || memberWithin(b, a) {
				return "", fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "overlapping membership scopes")
			}
		}
	}
	matches, gaps := map[string]bool{}, map[string]string{}
	files, dirs := 0, 0
	stack := make([]string, len(orderedScopes))
	for i := range orderedScopes {
		stack[i] = orderedScopes[len(orderedScopes)-1-i]
	}
	for len(stack) > 0 {
		relative := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		boundary, err := memberBoundary(f, relative)
		if err != nil {
			return "", err
		}
		if boundary != "" {
			gaps[relative] = boundary
			continue
		}
		entries, err := memberEntries(f, relative)
		if err != nil {
			return "", err
		}
		dirs++
		if dirs > 128 {
			return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership directory bound exceeded")
		}
		children := []string{}
		orderedEntries := append([]os.DirEntry(nil), entries...)
		sort.Slice(orderedEntries, func(i, j int) bool {
			a, b := strings.ToLower(orderedEntries[i].Name()), strings.ToLower(orderedEntries[j].Name())
			if a == b {
				return orderedEntries[i].Name() < orderedEntries[j].Name()
			}
			return a < b
		})
		for _, entry := range orderedEntries {
			name := entry.Name()
			if relative == "." && name == ".git" {
				continue
			}
			child := name
			if relative != "." {
				child = relative + "/" + name
			}
			if !memberPath(child, false) {
				return "", fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "membership path requires exact ASCII grammar")
			}
			info, err := f.Stat(child)
			if err != nil || info.Mode()&os.ModeSymlink != 0 {
				return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership entry is unreadable")
			}
			if info.IsDir() {
				folded := strings.ToLower(name)
				if memberVendor[folded] {
					gaps[child] = "vendor"
				} else if memberGenerated[folded] {
					gaps[child] = "generated"
				} else {
					if memberMatch(predicate, child, true) {
						matches[child] = true
					}
					children = append(children, child)
				}
			} else if info.Mode().IsRegular() {
				files++
				if files > 1024 {
					return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership file bound exceeded")
				}
				if memberMatch(predicate, child, false) {
					matches[child] = true
				}
			} else {
				return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership entry is unreadable")
			}
		}
		for i := len(children) - 1; i >= 0; i-- {
			stack = append(stack, children[i])
		}
		after, err := memberEntries(f, relative)
		if err != nil || len(after) != len(entries) {
			return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership directory changed during scan")
		}
		for i, entry := range entries {
			if entry.Name() != after[i].Name() || entry.Type() != after[i].Type() {
				return "", fault.New("SOURCE_EVIDENCE_UNKNOWN", "membership directory changed during scan")
			}
		}
	}
	orderedMatches := make([]string, 0, len(matches))
	for path := range matches {
		orderedMatches = append(orderedMatches, path)
	}
	memberSort(orderedMatches)
	gapPaths := make([]string, 0, len(gaps))
	for path := range gaps {
		gapPaths = append(gapPaths, path)
	}
	memberSort(gapPaths)
	excluded := make([]any, 0, len(gapPaths))
	for _, path := range gapPaths {
		excluded = append(excluded, map[string]any{"path": path, "reason": gaps[path]})
	}
	payload, err := canonical.Marshal(map[string]any{"method": "sha256-membership-v1", "predicate": predicate, "scope_paths": orderedScopes, "matches": orderedMatches, "excluded": excluded})
	if err != nil {
		return "", err
	}
	return canonical.BytesHash(payload), nil
}

// ValidateCurrentEvidence is an inert, read-only source check for an already
// rendered proposal. A schema-valid record's digest is never taken as proof of
// current source content or membership without reacquiring it from the store.
func ValidateCurrentEvidence(f *store.FS, provenance []byte, preview Preview) error {
	_, fields, err := parseProvenanceV2(provenance, preview)
	if err != nil {
		return err
	}
	if err := validateCodeMapTargets(f, preview); err != nil {
		return err
	}
	for _, field := range fields {
		for _, claimValue := range model.A(field["claims"]) {
			claim := model.M(claimValue)
			for _, evidenceValue := range model.A(claim["evidence"]) {
				evidence := model.M(evidenceValue)
				switch evidence["kind"] {
				case "content":
					path := model.S(evidence["path"])
					if !contentEvidencePath(path) {
						return fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "sensitive or unsupported content evidence path")
					}
					current, err := f.Read(path, 1<<20)
					if err != nil || canonical.BytesHash(current) != evidence["digest"] {
						return fault.New("SOURCE_EVIDENCE_CONFLICT", "context source evidence is missing or changed")
					}
					confirmed, err := f.Read(path, 1<<20)
					if err != nil || canonical.BytesHash(confirmed) != evidence["digest"] {
						return fault.New("SOURCE_EVIDENCE_CONFLICT", "context source evidence changed during read")
					}
				case "membership":
					values := model.A(evidence["scope_paths"])
					scopes := make([]string, len(values))
					for i, value := range values {
						scopes[i] = model.S(value)
					}
					current, err := MembershipDigest(f, model.S(evidence["predicate"]), scopes)
					if err != nil {
						return err
					}
					if current != evidence["digest"] {
						return fault.New("SOURCE_EVIDENCE_CONFLICT", "context membership evidence is changed")
					}
				default:
					return fault.New("SOURCE_EVIDENCE_UNSUPPORTED", "unknown context source evidence")
				}
			}
		}
	}
	return nil
}
