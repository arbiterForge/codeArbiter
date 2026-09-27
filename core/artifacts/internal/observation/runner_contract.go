package observation

import (
	"path/filepath"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

// QualifiedCommandProfile pins collector selection and every adapted launch input.
// The older profile remains separate so retained evidence is not reinterpreted.
const QualifiedCommandProfile = "declared-command/0.2.0"

func launchFileSchema() map[string]any {
	return closed(map[string]any{
		"path": text(), "sha256": hash(), "filesystem_id": text(),
		"role": map[string]any{"enum": model.List("declared-executable", "node-runtime", "npm-cli", "npm-manifest", "runner-entrypoint")},
	}, "path", "sha256", "filesystem_id", "role")
}

func validateQualifiedBinding(binding, definition map[string]any) bool {
	argv, declared := model.Strings(binding["argv"]), model.Strings(definition["argv"])
	if len(argv) == 0 || len(declared) == 0 || !filepath.IsAbs(argv[0]) {
		return false
	}
	collector := model.S(binding["collector_profile"])
	if collector == "" || (len(model.A(definition["required_tests"])) == 0) != (collector == "exit-only/0.1.0") {
		return false
	}
	files := map[string]map[string]any{}
	paths := map[string]bool{}
	for _, value := range model.A(binding["launch_files"]) {
		file := model.M(value)
		role, path := model.S(file["role"]), model.S(file["path"])
		if files[role] != nil || paths[path] || !filepath.IsAbs(path) {
			return false
		}
		files[role], paths[path] = file, true
	}
	wrapper := files["declared-executable"]
	if wrapper == nil {
		return false
	}
	npm := strings.ToLower(filepath.Base(declared[0]))
	isNPM := npm == "npm" || npm == "npm.cmd"
	if manifest := files["npm-manifest"]; manifest != nil {
		if !isNPM || !validNPMManifest(model.S(manifest["path"]), model.S(binding["cwd"]), declared) {
			return false
		}
	} else if isNPM && collector != "exit-only/0.1.0" {
		return false
	}
	if files["node-runtime"] == nil && files["npm-cli"] == nil {
		entrypoint := files["runner-entrypoint"]
		needsEntrypoint := false
		if (npm == "node" || npm == "node.exe") && len(declared) > 1 {
			switch strings.ToLower(filepath.Ext(declared[1])) {
			case ".js", ".mjs", ".cjs":
				needsEntrypoint = true
			}
		}
		if needsEntrypoint != (entrypoint != nil) {
			return false
		}
		if needsEntrypoint {
			path := declared[1]
			if !filepath.IsAbs(path) {
				path = filepath.Join(model.S(binding["cwd"]), path)
			}
			if filepath.Clean(path) != model.S(entrypoint["path"]) {
				return false
			}
		}
		// No adaptation: only argv[0] resolution may differ from the declaration.
		ext := strings.ToLower(filepath.Ext(argv[0]))
		return ext != ".cmd" && ext != ".bat" && len(argv) == len(declared) && same(argv[1:], declared[1:]) && model.S(wrapper["path"]) == argv[0] && model.S(wrapper["sha256"]) == model.S(binding["executable_sha256"])
	}
	if !isNPM || files["node-runtime"] == nil || files["npm-cli"] == nil || files["runner-entrypoint"] != nil || len(argv) != len(declared)+1 || !same(argv[2:], declared[1:]) {
		return false
	}
	wrapperPath := model.S(wrapper["path"])
	if !strings.EqualFold(filepath.Base(wrapperPath), "npm.cmd") {
		return false
	}
	install := filepath.Dir(wrapperPath)
	node := model.S(files["node-runtime"]["path"])
	cli := model.S(files["npm-cli"]["path"])
	return node == filepath.Join(install, "node.exe") && cli == filepath.Join(install, "node_modules", "npm", "bin", "npm-cli.js") && argv[0] == node && argv[1] == cli && model.S(files["node-runtime"]["sha256"]) == model.S(binding["executable_sha256"])
}

func validNPMManifest(path, cwd string, declared []string) bool {
	prefix := "."
	for i := 1; i < len(declared); i++ {
		if declared[i] == "--" {
			break
		}
		if declared[i] == "--prefix" && i+1 < len(declared) {
			i++
			prefix = declared[i]
		} else if strings.HasPrefix(declared[i], "--prefix=") {
			prefix = strings.TrimPrefix(declared[i], "--prefix=")
		}
	}
	if !filepath.IsAbs(prefix) {
		prefix = filepath.Join(cwd, prefix)
	}
	return path == filepath.Join(prefix, "package.json")
}
