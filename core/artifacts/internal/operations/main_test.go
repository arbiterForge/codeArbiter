package operations

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// storeHooks holds per-root instrumentation for the store handle an engine
// operation opens. Keying by repository root keeps one test's ledger out of
// every other test running in parallel.
var storeHooks sync.Map

// TestMain fixes the process environment the completion fixtures need once,
// so tests that spawn Git can run in parallel: t.Setenv forbids t.Parallel.
// The values are the same for every test: the absolute Git the bridge would
// select, and an empty global configuration with system configuration off.
func TestMain(m *testing.M) {
	os.Exit(run(m))
}

func run(m *testing.M) int {
	openStore = func(root string) (*store.FS, error) {
		f, err := store.Open(root)
		if err == nil {
			if hook, ok := storeHooks.Load(root); ok {
				hook.(func(*store.FS))(f)
			}
		}
		return f, err
	}
	git, err := exec.LookPath("git")
	if errors.Is(err, exec.ErrNotFound) {
		// The bounded named-test bridge intentionally supplies a PATH with
		// only Go. Its selected tests do not use Git fixtures.
		return m.Run()
	}
	if err == nil {
		git, err = filepath.Abs(git)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "git is required:", err)
		return 1
	}
	dir, err := os.MkdirTemp("", "ca-operations-git-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer os.RemoveAll(dir)
	config := filepath.Join(dir, "gitconfig")
	if err := os.WriteFile(config, nil, 0600); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	for key, value := range map[string]string{"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": config, "CODEARBITER_GIT_EXECUTABLE": git} {
		if err := os.Setenv(key, value); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	}
	return m.Run()
}
