# Plan — Mechanical CI/deploy/auth scope-touch detection (advisory) — #73 residual

Spec: advisory detection only (no new commit-block, no recorder). CI + deploy →
edit-time reminders H-15/H-16 + `security-reviewer` dispatched even on bare
`/commit`. Auth → advisory H-17 on narrow patterns. Generalize the migration
glob engine so all three path categories share one matcher.

MVP slice = T-01…T-04 (detection + reminders, fully testable). T-05…T-08 are
wiring/docs/release.

| # | Task | File(s) | Verification (tdd obligation) | AC | Dep |
|---|------|---------|-------------------------------|----|-----|
| T-01 | Generalize glob engine: `path_in_globs(rel, root, defaults, decl_re)`; refactor migration to use it (behavior-preserving) | `plugins/ca/hooks/_hooklib.py` | new `test_scope_paths.py` — migration paths still detected; non-paths rejected | AC-03 | — |
| T-02 | CI detection: `CI_DEFAULT_GLOBS`, `_CI_DECL_RE`, `is_ci_path` | `_hooklib.py` | `test_scope_paths.py` — workflow/gitlab/jenkins/circle/azure/bitbucket match; src files don't; `ci-paths` `+`/`-` override honored | AC-01, AC-03 | T-01 |
| T-03 | Deploy detection: `DEPLOY_DEFAULT_GLOBS`, `_DEPLOY_DECL_RE`, `is_deploy_path` | `_hooklib.py` | `test_scope_paths.py` — Dockerfile/compose/tf/tfvars/k8s/helm/kustomize/Procfile match; src files don't; `deploy-paths` override honored | AC-02, AC-03 | T-01 |
| T-04 | Advisory reminders H-15/H-16/H-17 + `AUTH_RE` | `plugins/ca/hooks/post-write-edit.py` | new `test_post_write_edit_scope.py` — CI→H-15, deploy→H-16, auth pattern→H-17, clean file→none, all non-blocking (exit 0) | AC-04, AC-05 | T-02, T-03 |
| T-05 | Ensure `commit-gate` classifies CI/deploy touches → dispatch `security-reviewer` (verify first, add only the gap) | `plugins/ca/skills/commit-gate/SKILL.md` (+ review/pr/checkpoint/sprint if missing) | read-through: classification step names CI/deploy + dispatches security-reviewer on bare commit | AC-06 | — |
| T-06 | Doc the new H-numbers | `docs/hooks.md` | H-15/H-16/H-17 rows in post-write table; advisory-not-block stated | AC-07 | T-04 |
| T-07 | Doc the declaration blocks | `security-controls.md` template / docs | `ci-paths`/`deploy-paths` format documented next to `migration-paths` | AC-07 | T-02, T-03 |
| T-08 | Release | `plugins/ca/.claude-plugin/plugin.json`, `CHANGELOG.md` | version bump + changelog entry; full hook suite green | AC-08, AC-09 | all |

## Notes
- No `pre-bash.py` change, no `infra-pass.py`, no marker. Migration/crypto/secret
  hard-blocks untouched.
- Reversible-before-merge principle: CI runs only when merged, IaC applies only
  when deployed → advisory + PR-gate review is proportionate; commit-block is
  reserved for irreversible-once-committed harms (secret/migration/crypto).
