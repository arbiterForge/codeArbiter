package observation

import (
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// These fixtures exercise the retained producer contract, not host authentication.
func runnerObservation(nativeNPM bool) (map[string]any, map[string]any, map[string]any, string) {
	context := verificationContext()
	definition := model.M(model.M(model.A(context["commands"])[0])["definition"])
	result := verificationProducerResult()
	binding := model.M(model.A(result["command_bindings"])[0])
	root := model.S(binding["cwd"])
	file := func(role, path, hash string) map[string]any {
		return map[string]any{"role": role, "path": path, "sha256": hash, "filesystem_id": "1:" + role}
	}
	binding["collector_profile"] = "codearbiter-named-lines/0.1.0"
	binding["launch_files"] = []any{file("declared-executable", model.Strings(binding["argv"])[0], model.S(binding["executable_sha256"]))}
	if nativeNPM {
		definition["argv"] = []any{"npm", "--prefix", "site", "run", "test:browser", "--", "--reporter=json"}
		node := filepath.Join(root, "node.exe")
		cli := filepath.Join(root, "node_modules", "npm", "bin", "npm-cli.js")
		binding["argv"] = append([]any{node, cli}, model.A(definition["argv"])[1:]...)
		binding["collector_profile"] = "playwright-json/0.1.0"
		binding["launch_files"] = []any{
			file("declared-executable", filepath.Join(root, "npm.cmd"), testDigest("npm-wrapper")),
			file("node-runtime", node, model.S(binding["executable_sha256"])),
			file("npm-cli", cli, testDigest("npm-cli")),
			file("npm-manifest", filepath.Join(root, "site", "package.json"), testDigest("npm-manifest")),
		}
	}
	contextHash, _ := canonical.Hash(context)
	payload := verificationPayload(context)
	payloadHash, _ := canonical.Hash(payload)
	observed := currentVerificationObservation(contextHash, payloadHash)
	observed["producer_profile"] = "declared-command/0.2.0"
	observed["producer_result"] = result
	observed["producer_result_sha256"], _ = canonical.Hash(result)
	event := map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
	return observed, event, context, contextHash
}

func runnerAccepted(observed, event, context map[string]any, contextHash string) bool {
	observed["producer_result_sha256"], _ = canonical.Hash(observed["producer_result"])
	return len(schema.ValidateWith(Schema(), observed)) == 0 && ValidateLink(event, observed, context, ContextRef(contextHash), contextHash) == nil
}

func TestQualifiedRunnerContractAcceptsDirectAndNativeNPM(t *testing.T) {
	for _, native := range []bool{false, true} {
		observed, event, context, contextHash := runnerObservation(native)
		if !runnerAccepted(observed, event, context, contextHash) {
			t.Fatalf("qualified runner rejected (native npm=%v): %v", native, schema.ValidateWith(Schema(), observed))
		}
	}
}

func TestQualifiedRunnerContractRejectsBindingMutations(t *testing.T) {
	mutations := map[string]func(map[string]any){
		"missing collector":       func(b map[string]any) { delete(b, "collector_profile") },
		"invented collector":      func(b map[string]any) { b["collector_profile"] = "anything/0.1.0" },
		"exit-only named results": func(b map[string]any) { b["collector_profile"] = "exit-only/0.1.0" },
		"missing provenance":      func(b map[string]any) { delete(b, "launch_files") },
		"missing wrapper":         func(b map[string]any) { b["launch_files"] = model.A(b["launch_files"])[1:] },
		"duplicate role":          func(b map[string]any) { model.M(model.A(b["launch_files"])[1])["role"] = "declared-executable" },
		"unknown role":            func(b map[string]any) { model.M(model.A(b["launch_files"])[1])["role"] = "unknown" },
		"relative path":           func(b map[string]any) { model.M(model.A(b["launch_files"])[0])["path"] = "npm.cmd" },
		"runtime hash":            func(b map[string]any) { model.M(model.A(b["launch_files"])[1])["sha256"] = testDigest("other-node") },
		"runtime path": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[1])["path"] = filepath.Join(model.S(b["cwd"]), "different.exe")
		},
		"cli path": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[2])["path"] = filepath.Join(model.S(b["cwd"]), "other-cli.js")
		},
		"wrapper path": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[0])["path"] = filepath.Join(model.S(b["cwd"]), "other.cmd")
		},
		"missing manifest": func(b map[string]any) { b["launch_files"] = model.A(b["launch_files"])[:3] },
		"wrong manifest": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[3])["path"] = filepath.Join(model.S(b["cwd"]), "different.json")
		},
		"mutated argument":         func(b map[string]any) { model.A(b["argv"])[2] = "--different" },
		"extra argument":           func(b map[string]any) { b["argv"] = append(model.A(b["argv"]), "extra") },
		"unknown field":            func(b map[string]any) { b["permit"] = true },
		"unknown provenance field": func(b map[string]any) { model.M(model.A(b["launch_files"])[0])["permit"] = true },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			observed, event, context, contextHash := runnerObservation(true)
			mutate(model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0]))
			if runnerAccepted(observed, event, context, contextHash) {
				t.Fatal("self-consistent mutated runner provenance accepted")
			}
		})
	}
}

func TestRunnerProfilesCannotBeRelabelled(t *testing.T) {
	observed, event, context, contextHash := runnerObservation(true)
	observed["producer_profile"] = "declared-command/0.1.0"
	if runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("qualified native npm relabelled as legacy producer")
	}
	context = verificationContext()
	contextHash, _ = canonical.Hash(context)
	payload := verificationPayload(context)
	payloadHash, _ := canonical.Hash(payload)
	observed = currentVerificationObservation(contextHash, payloadHash)
	event = map[string]any{"kind": "verification", "subject": subject(), "payload": payload}
	observed["producer_profile"] = "declared-command/0.2.0"
	if runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("unqualified legacy binding relabelled as qualified producer")
	}
}

func TestDirectNodeEntrypointIsRequiredAndExactlyBound(t *testing.T) {
	fixture := func() (map[string]any, map[string]any, map[string]any, string) {
		observed, event, context, _ := runnerObservation(false)
		binding := model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0])
		definition := model.M(model.M(model.A(context["commands"])[0])["definition"])
		script := filepath.Join("node_modules", "vitest", "vitest.mjs")
		definition["argv"] = []any{"node", script, "run", "--reporter=verbose"}
		binding["argv"] = []any{filepath.Join(model.S(binding["cwd"]), "node.exe"), script, "run", "--reporter=verbose"}
		binding["collector_profile"] = "vitest-verbose/0.1.0"
		model.M(model.A(binding["launch_files"])[0])["path"] = model.A(binding["argv"])[0]
		binding["launch_files"] = append(model.A(binding["launch_files"]), map[string]any{
			"role": "runner-entrypoint", "path": filepath.Join(model.S(binding["cwd"]), script),
			"sha256": testDigest("runner-cli"), "filesystem_id": "1:entrypoint",
		})
		contextHash, _ := canonical.Hash(context)
		observed["context_ref"], observed["context_sha256"] = ContextRef(contextHash), contextHash
		return observed, event, context, contextHash
	}
	observed, event, context, contextHash := fixture()
	if !runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("qualified direct node entrypoint rejected")
	}
	for name, mutate := range map[string]func(map[string]any){
		"missing": func(b map[string]any) { b["launch_files"] = model.A(b["launch_files"])[:1] },
		"wrong path": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[1])["path"] = filepath.Join(model.S(b["cwd"]), "other.mjs")
		},
		"relative": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[1])["path"] = "node_modules/vitest/vitest.mjs"
		},
	} {
		t.Run(name, func(t *testing.T) {
			observed, event, context, contextHash := fixture()
			mutate(model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0]))
			if runnerAccepted(observed, event, context, contextHash) {
				t.Fatal("unbound node entrypoint accepted")
			}
		})
	}
}
