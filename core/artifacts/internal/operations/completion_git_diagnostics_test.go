package operations

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

const completionGitDiagnosticLimit = 16 << 10

func completionGitTraceEnvironment(inherited []string, trace string) []string {
	environment := make([]string, 0, len(inherited)+3)
	for _, entry := range inherited {
		key, _, _ := strings.Cut(entry, "=")
		// Windows environment keys are case insensitive. Clear selectors rather
		// than retaining ambient requests to disclose private env/config values.
		if strings.EqualFold(key, "GIT_TRACE2_ENV_VARS") || strings.EqualFold(key, "GIT_TRACE2_CONFIG_PARAMS") || strings.EqualFold(key, "GIT_TRACE2_EVENT") {
			continue
		}
		environment = append(environment, entry)
	}
	return append(environment, "GIT_TRACE2_ENV_VARS=", "GIT_TRACE2_CONFIG_PARAMS=", "GIT_TRACE2_EVENT="+trace)
}

type completionDiagnosticOutput struct {
	bytes.Buffer
	limit     int
	truncated bool
}

func (b *completionDiagnosticOutput) Write(p []byte) (int, error) {
	n := len(p)
	remaining := b.limit - b.Len()
	if len(p) > remaining {
		p, b.truncated = p[:remaining], true
	}
	_, _ = b.Buffer.Write(p)
	return n, nil // Always drain the child, even after the retained output cap.
}

type completionDiagnosticResult struct {
	Output    string `json:"output"`
	Error     string `json:"error,omitempty"`
	Truncated bool   `json:"truncated"`
}

func completionDiagnosticCommand(git, root string, args ...string) completionDiagnosticResult {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, git, append([]string{"-C", root}, args...)...)
	command.Env = append(completionGitTraceEnvironment(os.Environ(), "0"), "GIT_OPTIONAL_LOCKS=0")
	command.WaitDelay = 100 * time.Millisecond
	output := &completionDiagnosticOutput{limit: 2048}
	command.Stdout, command.Stderr = output, output
	err := command.Run()
	result := completionDiagnosticResult{Output: output.String(), Truncated: output.truncated}
	if err != nil {
		result.Error = err.Error()
	}
	return result
}

func completionDiagnosticDirectory(path string) map[string]any {
	result := map[string]any{"path": path}
	info, err := os.Lstat(path)
	if err != nil {
		result["stat_error"] = err.Error()
		return result
	}
	result["mode"], result["size"] = info.Mode().String(), info.Size()
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return result
	}
	dir, err := os.Open(path)
	if err != nil {
		result["read_error"] = err.Error()
		return result
	}
	defer dir.Close()
	entries, err := dir.ReadDir(17)
	if err != nil && err != io.EOF {
		result["read_error"] = err.Error()
	}
	result["entries_truncated"] = len(entries) > 16
	if len(entries) > 16 {
		entries = entries[:16]
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		name := entry.Name()
		if len(name) > 256 {
			name = name[:256] + "[truncated]"
		}
		names = append(names, name)
	}
	result["entries"] = names
	return result
}

// This is failure-only observation of synthetic, fixture-owned repositories.
// No result repairs registration, retries the command, or changes its verdict.
func completionGitFailureContext(root, executable, trace string) string {
	resolved, resolveErr := filepath.EvalSymlinks(executable)
	common := completionDiagnosticCommand(executable, root, "rev-parse", "--path-format=absolute", "--git-common-dir")
	commonPath := filepath.Join(root, ".git")
	if common.Error == "" && !common.Truncated && filepath.IsAbs(strings.TrimSpace(common.Output)) {
		commonPath = strings.TrimSpace(common.Output)
	}
	context := map[string]any{
		"executable": executable, "resolved_executable": resolved,
		"version":    completionDiagnosticCommand(executable, root, "--version"),
		"common_dir": common, "fixture": completionDiagnosticDirectory(root),
		"metadata_parent":    completionDiagnosticDirectory(filepath.Join(commonPath, "worktrees")),
		"metadata_candidate": completionDiagnosticDirectory(filepath.Join(commonPath, "worktrees", "candidate")),
		"worktree_list":      completionDiagnosticCommand(executable, root, "worktree", "list", "--porcelain"),
	}
	if resolveErr != nil {
		context["executable_resolution_error"] = resolveErr.Error()
	}
	encoded, _ := json.Marshal(context)
	var output completionDiagnosticOutput
	output.limit = completionGitDiagnosticLimit
	fmt.Fprintf(&output, "completion Git failure context\nfixture_cwd: %s\n%s\ntrace2:\n", root, encoded)
	file, err := os.Open(trace)
	if err != nil {
		fmt.Fprintf(&output, "trace unavailable: %v\n", err)
	} else {
		defer file.Close()
		retained, readErr := io.ReadAll(io.LimitReader(file, 8193))
		if len(retained) > 8192 {
			retained = retained[:8192]
			fmt.Fprintln(&output, "[trace truncated at 8192 bytes]")
		}
		_, _ = output.Write(retained)
		if readErr != nil {
			fmt.Fprintf(&output, "\ntrace read error: %v\n", readErr)
		}
	}
	return output.String()
}

func TestCompletionGitFailureDiagnostics(t *testing.T) {
	t.Parallel()
	// Explicitly exercise Windows-style case aliases on every host, while
	// preserving unrelated Git configuration/environment bytes unchanged.
	inherited := []string{"Path=retained-path", "git_trace2_env_vars=private-selector", "Git_Trace2_Config_Params=private-config-selector", "git_trace2_event=unowned-sink", "GIT_CONFIG_VALUE_0=PrivateFixtureValue-config"}
	got := completionGitTraceEnvironment(inherited, "owned-trace")
	want := []string{"Path=retained-path", "GIT_CONFIG_VALUE_0=PrivateFixtureValue-config", "GIT_TRACE2_ENV_VARS=", "GIT_TRACE2_CONFIG_PARAMS=", "GIT_TRACE2_EVENT=owned-trace"}
	if strings.Join(got, "\n") != strings.Join(want, "\n") {
		t.Fatal("owned trace environment did not clear selector aliases while preserving unrelated input")
	}
	root := testutil.Root(t)
	if b, err := exec.Command("git", "-C", root, "init").CombinedOutput(); err != nil {
		t.Fatalf("initialize owned diagnostic fixture: %v %s", err, b)
	}
	// These are fixture-owned, incomplete registrations. Reading diagnostics
	// must leave them intact and report only a bounded directory population.
	for i := 0; i < 40; i++ {
		if err := os.MkdirAll(filepath.Join(root, ".git", "worktrees", fmt.Sprintf("owned-%02d", i)), 0700); err != nil {
			t.Fatal(err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	child := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestCompletionGitDiagnosticFailureChild$", "-test.v")
	child.Env = append(os.Environ(), "CODEARBITER_COMPLETION_GIT_DIAGNOSTIC_CHILD="+root,
		"CA_PRIVATE_FIXTURE_TRACE_CANARY=PrivateFixtureValue-environment",
		"GIT_TRACE2_ENV_VARS=CA_PRIVATE_FIXTURE_TRACE_CANARY",
		"GIT_TRACE2_CONFIG_PARAMS=ca.fixturePrivateTraceValue",
		"GIT_CONFIG_COUNT=1", "GIT_CONFIG_KEY_0=ca.fixturePrivateTraceValue", "GIT_CONFIG_VALUE_0=PrivateFixtureValue-config")
	output, err := child.CombinedOutput()
	if err == nil || ctx.Err() != nil {
		t.Fatalf("expected the real invalid-ref Git failure, not success/timeout: %v %s", err, output)
	}
	text := string(output)
	if strings.Contains(text, "PrivateFixtureValue") {
		t.Error("owned failure trace disclosed the inert private fixture marker selected by ambient diagnostic variables")
	}
	for _, want := range []string{"nonexistent-fixture-ref", "completion Git failure context", "executable", "git version", root, "common_dir", "metadata_parent", "owned-", "\"entries_truncated\":true", "worktree_list", "trace2", "\"event\":\"start\""} {
		if !strings.Contains(text, want) {
			t.Errorf("failure diagnostics omitted %q: %s", want, text)
		}
	}
	if len(output) > 24<<10 {
		t.Errorf("fixture failure output exceeded its bounded diagnostic allowance: %d", len(output))
	}
	entries, err := os.ReadDir(filepath.Join(root, ".git", "worktrees"))
	if err != nil || len(entries) != 40 {
		t.Fatalf("read-only diagnostics changed registrations: count=%d err=%v", len(entries), err)
	}
	trace := filepath.Join(testutil.Root(t), "oversized-trace.jsonl")
	if err := os.WriteFile(trace, []byte("TRACE-START\n"+strings.Repeat("x", 128<<10)+"TRACE-UNRETAINED-END"), 0600); err != nil {
		t.Fatal(err)
	}
	git, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	bounded := completionGitFailureContext(root, git, trace)
	if len(bounded) > completionGitDiagnosticLimit || !strings.Contains(bounded, "TRACE-START") || !strings.Contains(bounded, "trace truncated") || strings.Contains(bounded, "TRACE-UNRETAINED-END") {
		t.Fatalf("failure-only trace admission did not retain a bounded prefix: bytes=%d", len(bounded))
	}
}

func TestCompletionGitDiagnosticFailureChild(t *testing.T) {
	root := os.Getenv("CODEARBITER_COMPLETION_GIT_DIAGNOSTIC_CHILD")
	if root == "" {
		return
	}
	completionGit(t, root, "worktree", "add", "--detach", filepath.Join(root, "candidate"), "nonexistent-fixture-ref")
}
