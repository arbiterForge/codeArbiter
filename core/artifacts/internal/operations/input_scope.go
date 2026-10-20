package operations

import (
	"errors"
	"os"
	"path"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

// Scope fingerprints are *advisory* and deliberately not a verification
// snapshot or a dependency closure. Limits keep normal task reports cheap.
const (
	maxScopedFiles      = 256
	maxScopedDepth      = 12
	maxScopedFileBytes  = 2 << 20
	maxScopedTotalBytes = 12 << 20
)

var commonBuildInputs = []string{
	"go.mod", "go.sum", "package.json", "package-lock.json",
	"pnpm-lock.yaml", "yarn.lock", "tsconfig.json", "pyproject.toml",
	"poetry.lock", "pytest.ini", "Cargo.toml", "Cargo.lock",
}

// scopedInputDigest hashes explicit task paths and declared shared paths,
// plus a small set of common build-control filenames at actual command roots.
// A directory path captures its children (including additions/deletions), not
// merely its mtime. A missing path is represented, not silently skipped.
//
// Neither this set nor an unchanged digest proves all dependency edges, a
// passing test, or authorization to act. If bounds or safe-read guarantees
// cannot be met, ordinary work remains reportable with an unassessed status.
func scopedInputDigest(f *store.FS, task map[string]any) (string, string) {
	primary := map[string]bool{}
	for _, raw := range model.A(task["paths"]) {
		p := model.S(model.M(raw)["path"])
		primary[p] = true
	}
	for _, p := range model.Strings(task["shared_inputs"]) {
		primary[p] = true
	}
	if len(primary) == 0 {
		return "", "no_declared_task_or_shared_paths"
	}
	selected := map[string]bool{}
	for p := range primary {
		if !scopedAllowed(p) {
			return "", "unsafe_or_unbounded_scope"
		}
		selected[p] = true
	}
	// Known build inputs are shared across tasks. Track their *absence* as
	// well: adding a manifest or lockfile after a run must change the digest.
	roots := map[string]bool{".": true}
	for _, raw := range model.A(task["verification"]) {
		cwd := model.S(model.M(raw)["cwd"])
		if cwd != "" && validate.Path(cwd, true) {
			roots[cwd] = true
		}
	}
	for cwd := range roots {
		for _, name := range commonBuildInputs {
			p := name
			if cwd != "." {
				p = path.Join(cwd, name)
			}
			selected[p] = true
		}
	}
	paths := make([]string, 0, len(selected))
	for p := range selected {
		paths = append(paths, p)
	}
	sort.Strings(paths)

	items := make([]any, 0, len(paths))
	visited := 0
	total := int64(0)
	existingPrimary := false
	var descend func(string, int) error
	descend = func(rel string, depth int) error {
		if depth > maxScopedDepth || visited >= maxScopedFiles {
			return errors.New("bounded_files")
		}
		visited++
		if !scopedAllowed(rel) {
			return errors.New("unsafe_path")
		}
		info, err := f.Stat(rel)
		if os.IsNotExist(err) {
			items = append(items, map[string]any{"path": rel, "kind": "missing"})
			return nil
		}
		if err != nil {
			return err
		}
		if info.IsDir() {
			if primary[rel] {
				existingPrimary = true
			}
			items = append(items, map[string]any{"path": rel, "kind": "directory"})
			entries, err := f.List(rel) // refuses symlink/reparse children
			if err != nil {
				return err
			}
			for _, entry := range entries {
				child := path.Join(rel, entry.Name())
				if err := descend(child, depth+1); err != nil {
					return err
				}
			}
			return nil
		}
		if !info.Mode().IsRegular() {
			return errors.New("nonregular_input")
		}
		for declared := range primary {
			if rel == declared || strings.HasPrefix(rel, declared+"/") {
				existingPrimary = true
				break
			}
		}
		if info.Size() > maxScopedFileBytes {
			return errors.New("bounded_bytes")
		}
		b, err := f.Read(rel, maxScopedFileBytes)
		if err != nil {
			return err
		}
		total += int64(len(b))
		if total > maxScopedTotalBytes {
			return errors.New("bounded_bytes")
		}
		items = append(items, map[string]any{
			"path": rel, "kind": "file", "sha256": canonical.BytesHash(b),
		})
		return nil
	}
	// Nested explicit paths can overlap. Deduplicate visits and hashes while
	// retaining each newly added/removed child in the tracked directory tree.
	seen := map[string]bool{}
	visit := descend
	descend = func(rel string, depth int) error {
		if seen[rel] {
			return nil
		}
		seen[rel] = true
		return visit(rel, depth)
	}
	for _, p := range paths {
		if err := descend(p, 0); err != nil {
			return "", "source_scope_unassessed"
		}
	}
	if !existingPrimary {
		return "", "missing_declared_inputs"
	}
	h, err := canonical.Hash(map[string]any{"format": "scoped-inputs/1", "items": items})
	if err != nil {
		return "", "source_scope_unassessed"
	}
	return h, ""
}

func scopedAllowed(rel string) bool {
	if rel == "." || !validate.Path(rel, false) || validate.IsRuntimeMarkerPath(rel) {
		return false
	}
	// Generated state and repository internals are not code-input subjects.
	if rel == ".git" || strings.HasPrefix(rel, ".git/") ||
		rel == ".codearbiter/.artifacts" || strings.HasPrefix(rel, ".codearbiter/.artifacts/") ||
		strings.HasPrefix(rel, ".codearbiter/specs/") ||
		strings.HasPrefix(rel, ".codearbiter/plans/") {
		return false
	}
	return true
}
