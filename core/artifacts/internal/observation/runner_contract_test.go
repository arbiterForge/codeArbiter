package observation

import (
	"fmt"
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
		"unexpected npm prefix": func(b map[string]any) {
			b["launch_files"] = append(model.A(b["launch_files"]), map[string]any{
				"role": "npm-prefix", "path": filepath.Join(model.S(b["cwd"]), "node_modules", "npm", "bin", "npm-prefix.js"),
				"sha256": testDigest("npm-prefix"), "filesystem_id": "1:npm-prefix",
			})
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

// Workspace fixtures attest the inspected manifest closure, not host identity.
func workspaceRunnerObservation(nativeNPM bool, count int) (map[string]any, map[string]any, map[string]any, string) {
	observed, event, context, _ := runnerObservation(nativeNPM)
	binding := model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0])
	definition := model.M(model.M(model.A(context["commands"])[0])["definition"])
	root := model.S(binding["cwd"])
	definition["argv"] = []any{"npm", "run", "test:client", "--", "--", "--reporter=verbose"}
	files := model.A(binding["launch_files"])
	if nativeNPM {
		binding["argv"] = append(model.A(binding["argv"])[:2], model.A(definition["argv"])[1:]...)
		files = files[:3]
	} else {
		executable := filepath.Join(root, "npm")
		binding["argv"] = append([]any{executable}, model.A(definition["argv"])[1:]...)
		model.M(files[0])["path"] = executable
	}
	files = append(files, map[string]any{
		"role": "npm-manifest", "path": filepath.Join(root, "package.json"),
		"sha256": testDigest("root-package"), "filesystem_id": "1:root-package",
	})
	for i := range count {
		name := fmt.Sprintf("workspace-%d", i)
		files = append(files, map[string]any{
			"role": "npm-workspace-manifest", "path": filepath.Join(root, name, "package.json"),
			"sha256": testDigest(name), "filesystem_id": "1:" + name,
		})
	}
	if nativeNPM {
		files = append(files, map[string]any{
			"role": "npm-prefix", "path": filepath.Join(root, "node_modules", "npm", "bin", "npm-prefix.js"),
			"sha256": testDigest("npm-prefix"), "filesystem_id": "1:npm-prefix",
		})
	}
	binding["launch_files"] = files
	binding["collector_profile"] = "vitest-verbose/0.1.0"
	contextHash, _ := canonical.Hash(context)
	observed["context_ref"], observed["context_sha256"] = ContextRef(contextHash), contextHash
	return observed, event, context, contextHash
}

func TestQualifiedRunnerContractAcceptsWorkspaceManifestClosure(t *testing.T) {
	for _, native := range []bool{false, true} {
		for _, count := range []int{1, 2, 32} {
			t.Run(fmt.Sprintf("native-%v-manifests-%d", native, count), func(t *testing.T) {
				observed, event, context, contextHash := workspaceRunnerObservation(native, count)
				if !runnerAccepted(observed, event, context, contextHash) {
					t.Fatalf("named root npm workspace invocation with complete manifest closure rejected: %v", schema.ValidateWith(Schema(), observed))
				}
			})
		}
	}
}

func TestQualifiedRunnerContractRejectsInvalidWorkspaceManifestClosure(t *testing.T) {
	mutations := map[string]func(map[string]any){
		"duplicate workspace": func(b map[string]any) {
			files := model.A(b["launch_files"])
			b["launch_files"] = append(files, files[4])
		},
		"missing root": func(b map[string]any) {
			files := model.A(b["launch_files"])
			b["launch_files"] = append(files[:3], files[4:]...)
		},
		"root as workspace": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["path"] = filepath.Join(model.S(b["cwd"]), "package.json")
		},
		"outside root": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["path"] = filepath.Join(filepath.Dir(model.S(b["cwd"])), "outside", "package.json")
		},
		"unclean workspace": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["path"] = model.S(b["cwd"]) + string(filepath.Separator) + "child" + string(filepath.Separator) + ".." + string(filepath.Separator) + "workspace-0" + string(filepath.Separator) + "package.json"
		},
		"not a package manifest": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["path"] = filepath.Join(model.S(b["cwd"]), "workspace-0", "other.json")
		},
		"relative workspace": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["path"] = filepath.Join("workspace-0", "package.json")
		},
		"duplicate executable role": func(b map[string]any) {
			model.M(model.A(b["launch_files"])[4])["role"] = "node-runtime"
		},
		"missing npm prefix": func(b map[string]any) {
			files := model.A(b["launch_files"])
			b["launch_files"] = files[:len(files)-1]
		},
		"wrong npm prefix": func(b map[string]any) {
			files := model.A(b["launch_files"])
			model.M(files[len(files)-1])["path"] = filepath.Join(model.S(b["cwd"]), "other-prefix.js")
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			observed, event, context, contextHash := workspaceRunnerObservation(true, 2)
			if !runnerAccepted(observed, event, context, contextHash) {
				t.Fatal("valid workspace closure must be accepted before checking its mutation")
			}
			mutate(model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0]))
			if runnerAccepted(observed, event, context, contextHash) {
				t.Fatal("invalid workspace manifest closure accepted")
			}
		})
	}
	observed, event, context, contextHash := workspaceRunnerObservation(false, 33)
	if runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("more than 32 inspected workspace manifests accepted")
	}
}

func TestQualifiedRunnerContractRejectsExitOnlyWorkspaceManifestClosure(t *testing.T) {
	observed, event, context, _ := workspaceRunnerObservation(true, 2)
	definitionRow := model.M(model.A(context["commands"])[0])
	definition := model.M(definitionRow["definition"])
	definition["required_tests"] = []any{}
	definitionHash, _ := canonical.Hash(definition)
	definitionRow["definition_sha256"] = definitionHash
	result := model.M(observed["producer_result"])
	binding := model.M(model.A(result["command_bindings"])[0])
	binding["definition_sha256"] = definitionHash
	binding["collector_profile"] = "exit-only/0.1.0"
	command := model.M(model.A(result["commands"])[0])
	command["definition_sha256"] = definitionHash
	command["tests"] = []any{}
	payload := model.M(event["payload"])
	payload["commands"] = result["commands"]
	observed["payload_sha256"], _ = canonical.Hash(payload)
	contextHash, _ := canonical.Hash(context)
	observed["context_ref"], observed["context_sha256"] = ContextRef(contextHash), contextHash
	if runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("exit-only collector accepted workspace manifest closure")
	}
	// Prove the rejection is specific to workspace inspection for a named collector.
	binding["launch_files"] = model.A(binding["launch_files"])[:4]
	if !runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("otherwise valid exit-only npm binding rejected")
	}
}

func TestQualifiedRunnerContractRejectsPrefixHelperWithoutNativeNPM(t *testing.T) {
	observed, event, context, contextHash := workspaceRunnerObservation(false, 1)
	binding := model.M(model.A(model.M(observed["producer_result"])["command_bindings"])[0])
	binding["launch_files"] = append(model.A(binding["launch_files"]), map[string]any{
		"role": "npm-prefix", "path": filepath.Join(model.S(binding["cwd"]), "npm-prefix.js"),
		"sha256": testDigest("npm-prefix"), "filesystem_id": "1:npm-prefix",
	})
	if runnerAccepted(observed, event, context, contextHash) {
		t.Fatal("non-native npm binding accepted a prefix helper")
	}
}
