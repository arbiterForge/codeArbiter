"""Unit tests for the shared path-glob scope detectors in _hooklib (#73).

Covers migration (behavior-preserving after the generalization refactor), CI,
and deploy/IaC detection, plus the `*-paths` declaration override blocks in
security-controls.md (`+` extends, `-` excludes, excludes win).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _hooklib import (  # noqa: E402
    is_ci_path, is_deploy_path, is_migration_path,
)


class _ControlsRepo(unittest.TestCase):
    """A temp repo whose .codearbiter/security-controls.md can be set per test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".codearbiter"))

    def tearDown(self):
        self._tmp.cleanup()

    def _controls(self, body):
        with open(os.path.join(self.root, ".codearbiter", "security-controls.md"),
                  "w", encoding="utf-8") as f:
            f.write(body)


class TestMigrationStillDetected(_ControlsRepo):
    """The generalization must not regress migration detection."""

    def test_default_migration_globs(self):
        for p in ("db/migrations/001_init.sql", "app/migrate/2026_add.rb",
                  "alembic/versions/abc.py", "prisma/migrations/x/migration.sql"):
            self.assertTrue(is_migration_path(p, self.root), p)

    def test_non_migration_rejected(self):
        for p in ("src/app.ts", "README.md", "db/seed.sql"):
            self.assertFalse(is_migration_path(p, self.root), p)

    def test_migration_override_block(self):
        self._controls(
            "# controls\n<!-- migration-paths -->\n+ sql/changesets/**\n"
            "- **/migrations/legacy/**\n<!-- /migration-paths -->\n")
        self.assertTrue(is_migration_path("sql/changesets/5.sql", self.root))
        self.assertFalse(is_migration_path("db/migrations/legacy/old.sql", self.root))


class TestCiDetection(_ControlsRepo):
    def test_default_ci_globs(self):
        for p in (".github/workflows/ci.yml", ".github/workflows/release.yaml",
                  ".gitlab-ci.yml", "Jenkinsfile", "build/Jenkinsfile",
                  ".circleci/config.yml", "azure-pipelines.yml",
                  "bitbucket-pipelines.yml"):
            self.assertTrue(is_ci_path(p, self.root), p)

    def test_non_ci_rejected(self):
        for p in ("src/index.ts", "docs/ci.md", "package.json"):
            self.assertFalse(is_ci_path(p, self.root), p)

    def test_ci_override_block(self):
        self._controls(
            "<!-- ci-paths -->\n+ ops/pipelines/**\n- .github/workflows/docs.yml\n"
            "<!-- /ci-paths -->\n")
        self.assertTrue(is_ci_path("ops/pipelines/deploy.yml", self.root))
        self.assertFalse(is_ci_path(".github/workflows/docs.yml", self.root))


class TestDeployDetection(_ControlsRepo):
    def test_default_deploy_globs(self):
        for p in ("Dockerfile", "svc/Dockerfile", "Dockerfile.prod",
                  "docker-compose.yml", "docker-compose.prod.yaml",
                  "infra/main.tf", "infra/prod.tfvars", "k8s/deploy.yaml",
                  "helm/chart/values.yaml", "kustomization.yaml", "Procfile"):
            self.assertTrue(is_deploy_path(p, self.root), p)

    def test_non_deploy_rejected(self):
        for p in ("src/server.ts", "docs/deploy.md", "main.go"):
            self.assertFalse(is_deploy_path(p, self.root), p)

    def test_deploy_override_block(self):
        self._controls(
            "<!-- deploy-paths -->\n+ pulumi/**\n- infra/sandbox.tf\n"
            "<!-- /deploy-paths -->\n")
        self.assertTrue(is_deploy_path("pulumi/index.ts", self.root))
        self.assertFalse(is_deploy_path("infra/sandbox.tf", self.root))


if __name__ == "__main__":
    unittest.main()
