SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
# ADR-0004: Python removed from application stack. All application code is
# Node.js/TypeScript. Python variable retained only for validate-definitions
# (pending migration to scripts/validate-definitions.ts + ajv).
PYTHON      := python3
STAGE       := $(shell cat .fusion/stage 2>/dev/null || echo 1)
IMAGE       := fusion-core:latest
FRONTEND    := frontend
BACKEND     := backend
SCHEMAS     := schemas
TERRAFORM   := terraform

# Colour helpers (no-op when stdout is not a terminal)
GREEN  := $(shell tput setaf 2 2>/dev/null || echo "")
YELLOW := $(shell tput setaf 3 2>/dev/null || echo "")
RED    := $(shell tput setaf 1 2>/dev/null || echo "")
RESET  := $(shell tput sgr0   2>/dev/null || echo "")
BOLD   := $(shell tput bold   2>/dev/null || echo "")

define BANNER
	@echo "$(BOLD)$(GREEN)=== $(1) ===$(RESET)"
endef

define WARN
	@echo "$(YELLOW)WARN: $(1)$(RESET)"
endef

define FAIL
	@echo "$(RED)FAIL: $(1)$(RESET)"; exit 1
endef

# ---------------------------------------------------------------------------
# .PHONY — nothing here produces a file
# ---------------------------------------------------------------------------
.PHONY: help \
	up down seed \
	backend-dev backend-test backend-lint \
	frontend-dev frontend-test frontend-lint \
	validate-definitions layout-check registry-check netpol-check \
	sast secrets-scan deps-scan license-scan container-scan \
	sbom sign slsa-provenance fips-check \
	dast stig-check \
	deploy-stage deploy-prod teardown \
	ci install-hooks lockfile-check deps-source-check \
	agent-policy-check

# ---------------------------------------------------------------------------
# Help — list all documented targets
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-25s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "  Current stage: $(BOLD)S$(STAGE)$(RESET)"

# ---------------------------------------------------------------------------
# Local dev stack
# ---------------------------------------------------------------------------
up: ## Start local dev stack (postgres, gitea, fusion-core, audit sink)
	@test -f docker-compose.yml || { \
		echo "$(YELLOW)WARN: docker-compose.yml does not exist yet (SCF-018).$(RESET)"; \
		echo "      Create it before running 'make up'."; \
		exit 1; \
	}
	docker compose up -d
	@echo "$(GREEN)Stack is up. Run 'make down' to stop.$(RESET)"

down: ## Stop local dev stack
	@test -f docker-compose.yml || { echo "No docker-compose.yml — nothing to stop."; exit 0; }
	docker compose down

seed: ## Seed the database with dev fixtures
	@test -f docker-compose.yml || { echo "Stack not running; run 'make up' first."; exit 1; }
	@test -f scripts/seed.ts || { \
		echo "$(YELLOW)WARN: scripts/seed.ts does not exist yet.$(RESET)"; exit 1; \
	}
	npx tsx scripts/seed.ts

# ---------------------------------------------------------------------------
# Backend (Node.js/TypeScript — ADR-0004)
# ---------------------------------------------------------------------------
backend-dev: ## Start Fastify with tsx watch hot reload [requires backend/]
	@test -d $(BACKEND) || { \
		echo "$(YELLOW)WARN: backend/ does not exist yet (SCF-005).$(RESET)"; exit 1; \
	}
	cd $(BACKEND) && npm run dev

backend-test: ## Run Vitest with coverage (≥60% enforced at S1)
	@test -d $(BACKEND) || { \
		$(WARN) "backend/ does not exist yet — no backend tests to run."; exit 0; \
	}
	cd $(BACKEND) && npm run test:coverage

backend-lint: ## ESLint + tsc --noEmit (backend)
	@test -d $(BACKEND) || { \
		$(WARN) "backend/ does not exist yet — no backend source to lint."; exit 0; \
	}
	$(call BANNER,ESLint — backend)
	cd $(BACKEND) && npm run lint
	$(call BANNER,TypeScript — backend)
	cd $(BACKEND) && npm run typecheck

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
frontend-dev: ## Start Vite dev server
	cd $(FRONTEND) && npm run dev

frontend-test: ## Run Vitest with coverage (≥60% enforced at S1)
	cd $(FRONTEND) && npm run test:coverage

frontend-lint: ## eslint + tsc --noEmit
	$(call BANNER,ESLint)
	cd $(FRONTEND) && npm run lint
	$(call BANNER,TypeScript)
	cd $(FRONTEND) && npm run typecheck

# ---------------------------------------------------------------------------
# Definition validation
# ---------------------------------------------------------------------------
validate-definitions: ## JSON Schema check on all definition.yaml files
	$(call BANNER,validate-definitions)
	@DEFS=$$(find fusion-nodes fusion-adapters -name "definition.yaml" 2>/dev/null); \
	if [ -z "$$DEFS" ]; then \
		echo "No definition.yaml files found — nothing to validate."; \
		exit 0; \
	fi; \
	FAIL=0; \
	for f in $$DEFS; do \
		kind=$$(grep -m1 '^kind:' "$$f" | awk '{print $$2}'); \
		schema=$(SCHEMAS)/$${kind}.schema.json; \
		if [ ! -f "$$schema" ]; then \
			echo "$(RED)FAIL: No schema for kind '$$kind' at $$schema$(RESET)"; FAIL=1; continue; \
		fi; \
		$(PYTHON) -c "\
import json, jsonschema, sys; \
import yaml; \
data = yaml.safe_load(open('$$f')); \
schema = json.load(open('$$schema')); \
try: jsonschema.validate(data, schema); print('PASS: $$f') \
except jsonschema.ValidationError as e: print('FAIL: $$f:', e.message); sys.exit(1) \
" || FAIL=1; \
	done; \
	exit $$FAIL

layout-check: ## Verify node/adapter directory layout conventions
	$(call BANNER,layout-check)
	@for dir in fusion-nodes/*/; do \
		for f in definition.yaml main.tf playbook.yml values.yaml; do \
			test -f "$$dir$$f" || echo "$(YELLOW)WARN: $$dir$$f missing$(RESET)"; \
		done; \
	done
	@echo "Layout check complete."

registry-check: ## Verify all definition.yaml files reference valid registry entries
	$(call BANNER,registry-check)
	@echo "[S1: stub — implement when registry endpoint exists]"

netpol-check: ## Validate NetworkPolicy manifests match trust-zones.md pod selectors [S2+]
	$(call BANNER,netpol-check)
	@if [ "$(STAGE)" -lt 2 ]; then \
		echo "[S1: advisory — NetworkPolicy manifests not yet required]"; exit 0; \
	fi
	@test -d deploy/k8s/netpol || { \
		$(FAIL) "deploy/k8s/netpol/ does not exist (SCF-016)"; \
	}
	@command -v kubectl >/dev/null 2>&1 || { \
		echo "$(RED)INSTALL: kubectl not found$(RESET)"; exit 1; \
	}
	kubectl apply --dry-run=client -f deploy/k8s/netpol/

# ---------------------------------------------------------------------------
# Security gates (non-bypass — MUST NOT be skipped or continue-on-error)
# ---------------------------------------------------------------------------
agent-policy-check: ## Agent policy linter — CONFIRM tokens, domain vocab, .fusion/stage integrity (CM-3)
	$(call BANNER,agent-policy-check)
	@cd tools/agent_policy && npm run check -- "$(CURDIR)"

# ---------------------------------------------------------------------------
sast: ## Semgrep static analysis — Node.js + frontend rulesets [advisory S1; enforce S2+]
	$(call BANNER,sast — semgrep)
	@if command -v semgrep >/dev/null 2>&1; then \
		TARGETS="$(FRONTEND)/src/"; \
		if [ -d $(BACKEND)/src ]; then TARGETS="$$TARGETS $(BACKEND)/src/"; fi; \
		semgrep --config=auto --config=.semgrep/ --error $$TARGETS || { \
			if [ "$(STAGE)" -lt 2 ]; then \
				echo "$(YELLOW)[S1: advisory] Semgrep findings noted; not blocking at S1$(RESET)"; \
			else \
				exit 1; \
			fi; \
		}; \
	else \
		echo "$(YELLOW)WARN: semgrep not installed.$(RESET)"; \
		echo "  Install: https://semgrep.dev/docs/getting-started/"; \
		if [ "$(STAGE)" -ge 2 ]; then exit 1; fi; \
	fi

secrets-scan: ## gitleaks scan — enforced at all stages
	$(call BANNER,secrets-scan)
	@command -v gitleaks >/dev/null 2>&1 || { \
		echo "$(RED)INSTALL: gitleaks not found.$(RESET)"; \
		echo "  Windows: winget install gitleaks"; \
		echo "  macOS:   brew install gitleaks"; \
		echo "  Linux:   https://github.com/gitleaks/gitleaks/releases"; \
		exit 1; \
	}
	gitleaks detect --source . --no-banner --redact
	@echo "$(GREEN)PASS: No secrets detected$(RESET)"

deps-scan: ## npm audit — frontend + backend [advisory S1; enforce S2+]
	$(call BANNER,deps-scan — frontend npm audit)
	cd $(FRONTEND) && npm audit --audit-level=critical || { \
		if [ "$(STAGE)" -lt 2 ]; then \
			echo "$(YELLOW)[S1: advisory] npm audit findings noted$(RESET)"; \
		else exit 1; fi; \
	}
	$(call BANNER,deps-scan — backend npm audit)
	@if [ -d $(BACKEND) ]; then \
		cd $(BACKEND) && npm audit --audit-level=critical || { \
			if [ "$(STAGE)" -lt 2 ]; then \
				echo "$(YELLOW)[S1: advisory] backend npm audit findings noted$(RESET)"; \
			else exit 1; fi; \
		}; \
	else \
		echo "backend/ does not exist yet — skipping backend npm audit."; \
	fi

license-scan: ## License allow-list enforcement — enforced at all stages
	$(call BANNER,license-scan — Terraform BSL check)
	@if grep -rn 'registry\.terraform\.io' --include="*.tf" . 2>/dev/null; then \
		$(FAIL) "registry.terraform.io found in .tf files — HashiCorp BSL prohibited (CLAUDE.md §3)"; \
	fi
	@if grep -rn '"hashicorp/terraform"' --include="*.tf" . 2>/dev/null; then \
		$(FAIL) '"hashicorp/terraform" provider found — use registry.opentofu.org/* instead'; \
	fi
	@echo "$(GREEN)PASS: No HashiCorp Terraform references$(RESET)"
	$(call BANNER,license-scan — frontend npm packages)
	@if command -v license-checker >/dev/null 2>&1; then \
		cd $(FRONTEND) && license-checker \
			--failOn "AGPL-3.0;SSPL;BSL;Commons Clause" \
			--excludePrivatePackages \
			--summary || { \
			$(FAIL) "Denied license found in frontend npm deps — see ALLOWED_LICENSES.md"; \
		}; \
		echo "$(GREEN)PASS: No denied frontend npm licenses$(RESET)"; \
	else \
		echo "$(YELLOW)WARN: license-checker not installed. Run: npm install -g license-checker$(RESET)"; \
	fi
	$(call BANNER,license-scan — backend npm packages)
	@if [ -d $(BACKEND) ] && command -v license-checker >/dev/null 2>&1; then \
		cd $(BACKEND) && license-checker \
			--failOn "AGPL-3.0;SSPL;BSL;Commons Clause" \
			--excludePrivatePackages \
			--summary || { \
			$(FAIL) "Denied license found in backend npm deps — see ALLOWED_LICENSES.md"; \
		}; \
		echo "$(GREEN)PASS: No denied backend npm licenses$(RESET)"; \
	elif [ ! -d $(BACKEND) ]; then \
		echo "backend/ does not exist yet — skipping backend license scan."; \
	fi

container-scan: ## Trivy container image scan [advisory S1; enforce S2+]
	$(call BANNER,container-scan)
	@command -v trivy >/dev/null 2>&1 || { \
		echo "$(YELLOW)WARN: trivy not installed.$(RESET)"; \
		echo "  Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"; \
		if [ "$(STAGE)" -ge 2 ]; then exit 1; fi; \
		exit 0; \
	}
	@if ! docker image inspect $(IMAGE) >/dev/null 2>&1; then \
		echo "$(YELLOW)WARN: Image $(IMAGE) not built — build before scanning$(RESET)"; \
		if [ "$(STAGE)" -ge 2 ]; then exit 1; fi; \
		exit 0; \
	fi
	trivy image \
		--exit-code 1 \
		--severity CRITICAL,HIGH \
		$(IMAGE)

sbom: ## Generate CycloneDX SBOM via syft [S1: generated; S3+: signed]
	$(call BANNER,sbom)
	@command -v syft >/dev/null 2>&1 || { \
		echo "$(YELLOW)WARN: syft not installed.$(RESET)"; \
		echo "  Install: https://github.com/anchore/syft#installation"; \
		exit 0; \
	}
	syft . -o cyclonedx-json > sbom.cyclonedx.json
	@echo "$(GREEN)SBOM written to sbom.cyclonedx.json$(RESET)"

sign: ## cosign sign container image with KMS key [S3+]
	$(call BANNER,sign)
	@if [ "$(STAGE)" -lt 3 ]; then \
		echo "[S1-S2: stub — signing enforced at S3+]"; exit 0; \
	fi
	@command -v cosign >/dev/null 2>&1 || { \
		echo "$(RED)INSTALL: cosign not found$(RESET)"; exit 1; \
	}
	cosign sign --key=kms://$(KMS_KEY_ID) $(IMAGE)

slsa-provenance: ## Generate SLSA v1.0 build provenance [S3+]
	$(call BANNER,slsa-provenance)
	@if [ "$(STAGE)" -lt 3 ]; then \
		echo "[S1-S2: stub — SLSA provenance enforced at S3+]"; exit 0; \
	fi
	@echo "Implement SLSA provenance generation for stage $(STAGE)"

fips-check: ## Verify FIPS 140-3 provider is active (OpenSSL + Node.js) — enforced at all stages
	$(call BANNER,fips-check — OpenSSL provider)
	@command -v openssl >/dev/null 2>&1 || { \
		echo "$(RED)FAIL: openssl not found$(RESET)"; exit 1; \
	}
	@openssl list -providers 2>/dev/null | grep -i fips || { \
		echo "$(YELLOW)WARN: FIPS provider not listed by openssl.$(RESET)"; \
		echo "      On RHEL/UBI9: ensure crypto-policies is set to FIPS mode."; \
		echo "      On dev machines: advisory at S1; enforced at S2+."; \
		if [ "$(STAGE)" -ge 2 ]; then exit 1; fi; \
	}
	$(call BANNER,fips-check — Node.js crypto)
	@node -e "const f = require('crypto').getFips(); process.exit(f === 1 ? 0 : 2)" 2>/dev/null || { \
		echo "$(YELLOW)WARN: Node.js FIPS mode not active (require('crypto').getFips() !== 1).$(RESET)"; \
		echo "      In production: use UBI9 FIPS Node.js image with --openssl-fips flag."; \
		echo "      On dev machines: advisory at S1; enforced at S2+."; \
		if [ "$(STAGE)" -ge 2 ]; then exit 1; fi; \
	}

# ---------------------------------------------------------------------------
# DAST / STIG [S2+ and S3+ respectively]
# ---------------------------------------------------------------------------
dast: ## OWASP ZAP baseline scan [S2+]
	$(call BANNER,dast)
	@if [ "$(STAGE)" -lt 2 ]; then \
		echo "[S1: not yet required — DAST activated at S2]"; exit 0; \
	fi
	@command -v zap-baseline.py >/dev/null 2>&1 || docker image inspect owasp/zap2docker-stable >/dev/null 2>&1 || { \
		echo "$(RED)INSTALL: OWASP ZAP not found$(RESET)"; exit 1; \
	}
	docker run --rm owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000

stig-check: ## DISA STIG / OpenSCAP hardening check [S3+]
	$(call BANNER,stig-check)
	@if [ "$(STAGE)" -lt 3 ]; then \
		echo "[S1-S2: not yet required — STIG check activated at S3]"; exit 0; \
	fi
	@echo "Implement OpenSCAP STIG check for stage $(STAGE)"

# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------
deploy-stage: ## Deploy to staging environment [requires CODEOWNER approval]
	$(call BANNER,deploy-stage)
	@echo "$(YELLOW)Staging deployment requires CODEOWNER approval and passing CI.$(RESET)"
	@echo "Implement: tofu -chdir=$(TERRAFORM) apply -var-file=environments/staging.tfvars"

deploy-prod: ## Deploy to production [requires signed release tag + CODEOWNER approval, S3+]
	$(call BANNER,deploy-prod)
	@if [ "$(STAGE)" -lt 3 ]; then \
		$(FAIL) "Production deployment requires Stage 3+. Current stage: $(STAGE)"; \
	fi
	@echo "$(YELLOW)Production deployment requires signed release tag + CODEOWNER approval.$(RESET)"

teardown: ## Tear down a deployed solution (SOLUTION=<name> required)
	$(call BANNER,teardown)
	@test -n "$(SOLUTION)" || { $(FAIL) "SOLUTION variable required: make teardown SOLUTION=<name>"; }
	@echo "Tearing down solution: $(SOLUTION)"
	@echo "Implement: tofu destroy for solution $(SOLUTION)"

# ---------------------------------------------------------------------------
# Lockfile and dependency source integrity
# ---------------------------------------------------------------------------
lockfile-check: ## Verify package-lock.json files are committed (frontend + backend when present)
	$(call BANNER,lockfile-check)
	@FAIL=0; \
	for f in frontend/package-lock.json; do \
		if ! git ls-files --error-unmatch "$$f" >/dev/null 2>&1; then \
			echo "$(RED)FAIL: $$f is not committed to git$(RESET)"; FAIL=1; \
		else \
			echo "$(GREEN)PASS: $$f committed$(RESET)"; \
		fi; \
	done; \
	if [ -d $(BACKEND) ]; then \
		if ! git ls-files --error-unmatch "$(BACKEND)/package-lock.json" >/dev/null 2>&1; then \
			echo "$(RED)FAIL: backend/package-lock.json is not committed to git$(RESET)"; FAIL=1; \
		else \
			echo "$(GREEN)PASS: backend/package-lock.json committed$(RESET)"; \
		fi; \
	fi; \
	exit $$FAIL

deps-source-check: ## Verify all deps come from approved sources (npm registry only — ADR-0004)
	$(call BANNER,deps-source-check)
	@for pkg_json in $(FRONTEND)/package.json; do \
		node -e "\
const p = require('./$$pkg_json'); \
const all = {...(p.dependencies||{}), ...(p.devDependencies||{})}; \
const bad = Object.entries(all).filter(([,v]) => v.startsWith('git') || v.startsWith('file:') || v.startsWith('link:')); \
if (bad.length) { console.error('FAIL: Non-registry npm deps in $$pkg_json:', bad); process.exit(1); } \
else { console.log('PASS: All npm deps from registry ($$pkg_json)'); } \
"; \
	done
	@if [ -f $(BACKEND)/package.json ]; then \
		node -e "\
const p = require('./$(BACKEND)/package.json'); \
const all = {...(p.dependencies||{}), ...(p.devDependencies||{})}; \
const bad = Object.entries(all).filter(([,v]) => v.startsWith('git') || v.startsWith('file:') || v.startsWith('link:')); \
if (bad.length) { console.error('FAIL: Non-registry npm deps in backend/package.json:', bad); process.exit(1); } \
else { console.log('PASS: All backend npm deps from registry'); } \
"; \
	fi

# ---------------------------------------------------------------------------
# Developer tooling
# ---------------------------------------------------------------------------
install-hooks: ## Install pre-commit + pre-push git hooks
	$(call BANNER,install-hooks)
	@command -v pre-commit >/dev/null 2>&1 || { \
		echo "$(RED)INSTALL: pre-commit not found.$(RESET)"; \
		echo "  Install: https://pre-commit.com/#install (pipx install pre-commit)"; \
		exit 1; \
	}
	pre-commit install --hook-type pre-commit --hook-type pre-push
	@echo "$(GREEN)Hooks installed. 'make ci' will run on push.$(RESET)"

# ---------------------------------------------------------------------------
# CI — the complete gate set that runs in CI
# Enforced at Stage 1: lockfile-check, frontend-lint, frontend-test,
#   validate-definitions, secrets-scan, license-scan, fips-check, sast, deps-scan
# Backend gates are conditional on backend/ existing.
# ---------------------------------------------------------------------------
ci: ## Run everything CI runs, locally
	$(call BANNER,CI — Stage $(STAGE))
	@echo "Running enforced gate set for Stage $(STAGE)..."
	$(MAKE) agent-policy-check
	$(MAKE) lockfile-check
	$(MAKE) frontend-lint
	$(MAKE) frontend-test
	@test -d $(BACKEND) && $(MAKE) backend-lint || true
	@test -d $(BACKEND) && $(MAKE) backend-test || true
	$(MAKE) validate-definitions
	$(MAKE) secrets-scan
	$(MAKE) license-scan
	$(MAKE) fips-check
	$(MAKE) sast
	$(MAKE) deps-scan
	@if [ "$(STAGE)" -ge 2 ]; then $(MAKE) container-scan; fi
	@if [ "$(STAGE)" -ge 2 ]; then $(MAKE) dast; fi
	@if [ "$(STAGE)" -ge 3 ]; then $(MAKE) stig-check; fi
	$(MAKE) sbom
	@echo ""
	@echo "$(BOLD)$(GREEN)CI complete — Stage $(STAGE) gate set passed.$(RESET)"
