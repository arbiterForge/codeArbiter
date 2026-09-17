package validate

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"path"
	"strings"
)

// InputIncludes checks declared path coverage, not complete build-dependency
// closure. The latter still requires project-specific review of roots/excludes.
func InputIncludes(norm map[string]any, target string) bool {
	policy := model.M(norm["verification_inputs"])
	if policy == nil {
		return true
	}
	within := func(root string) bool { return root == "." || target == root || strings.HasPrefix(target, root+"/") }
	covered := false
	for _, root := range model.Strings(policy["roots"]) {
		if within(root) {
			covered = true
		}
	}
	for _, exclude := range model.Strings(policy["exclude_directories"]) {
		if within(exclude) {
			return false
		}
	}
	return covered
}

// IsTestCommand recognizes common runner entry points regardless of executable
// path. This is deliberately not a shell parser or a universal runner detector:
// custom wrappers must still declare required_tests in the reviewed plan.
func IsTestCommand(argv []string) bool {
	if len(argv) == 0 {
		return false
	}
	exe := strings.ToLower(path.Base(strings.ReplaceAll(argv[0], `\`, "/")))
	exe = strings.TrimSuffix(exe, ".exe")
	args := argv[1:]
	has := func(s string) bool {
		for _, a := range args {
			if a == s {
				return true
			}
		}
		return false
	}
	switch {
	case exe == "go":
		for _, a := range args {
			if !strings.HasPrefix(a, "-") {
				return a == "test"
			}
		}
	case exe == "pytest" || exe == "py.test" || exe == "vitest" || exe == "jest" || exe == "mocha":
		return true
	case exe == "python" || exe == "python3" || exe == "py" || strings.HasPrefix(exe, "python3."):
		for i, a := range args {
			if a == "-m" && i+1 < len(args) {
				return args[i+1] == "pytest" || args[i+1] == "unittest"
			}
		}
	case exe == "node":
		return has("--test")
	case exe == "npm" || exe == "pnpm" || exe == "yarn" || exe == "bun":
		for _, a := range args {
			if a == "test" || a == "t" || strings.HasPrefix(a, "test:") {
				return true
			}
		}
	case exe == "cargo" || exe == "dotnet" || exe == "deno":
		return has("test")
	}
	return false
}
