package operations

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func completionGit(t *testing.T, root string, args ...string) string {
	t.Helper()
	command := exec.Command("git", append([]string{"-C", root}, args...)...)
	b, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v %s", args, err, b)
	}
	return strings.TrimSpace(string(b))
}

func completionHarness(t *testing.T) (*farmHarness, string) {
	t.Helper()
	config := filepath.Join(testutil.Root(t), "gitconfig")
	if err := os.WriteFile(config, nil, 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("GIT_CONFIG_NOSYSTEM", "1")
	t.Setenv("GIT_CONFIG_GLOBAL", config)
	git, gitErr := exec.LookPath("git")
	if gitErr != nil {
		t.Fatal(gitErr)
	}
	git, gitErr = filepath.Abs(git)
	if gitErr != nil {
		t.Fatal(gitErr)
	}
	t.Setenv("CODEARBITER_GIT_EXECUTABLE", git)

	h := newFarmHarness(t)
	completionGit(t, h.root, "init")
	writeFixture(t, h.root, ".gitignore", []byte(".codearbiter/.artifacts/\n"))
	writeFixture(t, h.root, "src/stage1.go", []byte("package stage\n"))
	completionGit(t, h.root, "add", ".")
	completionGit(t, h.root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture base")
	linked := filepath.Join(testutil.Root(t), "candidate")
	completionGit(t, h.root, "worktree", "add", "--detach", linked, "HEAD")
	h.createPair()
	return h, linked
}

func completionVerification(t *testing.T, h *farmHarness, id, workspace string, publication ...string) string {
	t.Helper()
	cr := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "verification", "record_id": id})
	c := h.derived(model.S(cr["context_ref"]))
	identity := func(path string) string {
		v, err := evidence.CompletionPathIdentity(path)
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	// These producers are synthetic and execute no command. Bind an isolated
	// regular file rather than the running test binary, whose temporary path
	// or read-sharing behavior depends on the hosted platform.
	executable := filepath.Join(testutil.Root(t), "synthetic-verifier")
	executableBytes := []byte("Synthetic verifier fixture; never executed.\n")
	if err := os.WriteFile(executable, executableBytes, 0700); err != nil {
		t.Fatal(err)
	}
	executableHash := canonical.BytesHash(executableBytes)
	common := completionGit(t, workspace, "rev-parse", "--path-format=absolute", "--git-common-dir")
	common, err := filepath.EvalSymlinks(common)
	if err != nil {
		t.Fatal(err)
	}
	bindings, commands := []any{}, []any{}
	for _, v := range model.A(c["commands"]) {
		row := model.M(v)
		def := model.M(row["definition"])
		argv := append([]any{executable}, model.A(def["argv"])[1:]...)
		bindings = append(bindings, object{"definition_sha256": row["definition_sha256"], "argv": argv, "cwd": workspace, "cwd_filesystem_id": identity(workspace), "workspace_root": workspace, "workspace_filesystem_id": identity(workspace), "git_common_dir": common, "git_common_filesystem_id": identity(common), "executable_sha256": executableHash, "collector_profile": "codearbiter-named-lines/0.1.0", "launch_files": []any{object{"path": executable, "sha256": executableHash, "filesystem_id": identity(executable), "role": "declared-executable"}}})
		tests := []any{}
		for _, name := range model.Strings(def["required_tests"]) {
			tests = append(tests, object{"name": name, "status": "pass"})
		}
		commands = append(commands, object{"definition_sha256": row["definition_sha256"], "exit": def["expected_exit"], "tests": tests, "stdout_sha256": canonical.BytesHash([]byte("synthetic test output")), "stderr_sha256": canonical.BytesHash(nil)})
	}
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	workspaces, err := evidence.CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatal(err)
	}
	payload := object{"input_sha256": c["input_sha256"], "spec_sha256": c["spec_sha256"], "task_sha256": c["task_sha256"], "commands": commands}
	producer := object{"environment_sha256": canonical.BytesHash([]byte("synthetic environment")), "command_bindings": bindings, "workspace_before": workspaces, "workspace_after": workspaces, "commands": commands}
	profile := observation.QualifiedCommandProfile
	if len(publication) > 0 {
		profile = observation.CompletionCommandProfile
		normalized := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "verification", "record_id": id, "verification_command_bindings": bindings})
		if normalized["context_ref"] != cr["context_ref"] || normalized["context_sha256"] != cr["context_sha256"] {
			t.Fatal("completion closure changed the immutable verification context")
		}
		producer["completion_workspace_after"] = normalized["completion_workspace_after"]
		if publication[0] == "tamper" {
			model.M(model.A(producer["completion_workspace_after"])[0])["content_sha256"] = strings.Repeat("0", 64)
		}
	}
	observed := object{"format": "codearbiter.observation/0.2.0", "kind": "verification", "subject": c["subject"], "context_ref": cr["context_ref"], "context_sha256": cr["context_sha256"], "payload_sha256": mustHashFixture(t, payload), "producer_profile": profile, "producer_run_id": "synthetic-completion-verifier", "producer_result": producer, "producer_result_sha256": mustHashFixture(t, producer)}
	event := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "verification", "authority_kind": "verification_runner", "subject": c["subject"], "actor": "synthetic test fixture", "origin": "isolated completion fixture", "verdict": "passed", "payload": payload, "source_text": "Synthetic qualified verification fixture; no real tests executed.", "observation_ref": h.forge("observations", observed), "observation_sha256": mustHashFixture(t, observed)}
	return model.S(h.run("capture-observation", object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)})["receipt"])
}

func completionContext(t *testing.T, h *farmHarness, id, kind string, receipts []string, files []string) object {
	t.Helper()
	return h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": kind, "record_id": id, "completion_selection": object{"verification_receipts": model.List(receipts...), "supporting_files": model.List(files...)}})
}
