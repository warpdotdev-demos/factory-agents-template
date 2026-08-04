#!/usr/bin/env python3
"""Tests for factory-dispatch's per-repo environment / runner resolution.

With many repos configured, one cloud environment rarely carries every repo's
toolchain, so a child step must be dispatched into the environment that has the
target repo. These tests point the dispatcher at a synthetic foreman config and
assert the resolution order: flag, then the repo's `target_repos` entry, then the
owning Jira project's `project_routing` entry, then the shared environment
variable.
"""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISPATCH_SCRIPT = os.path.join(REPO_ROOT, "scripts", "factory-dispatch")

CONFIG = {
    "tracker": {
        "provider": "jira",
        "project_routing": {
            "PAY": {
                "description": "payments",
                "repos": ["acme/payments-api", "acme/webapp"],
                "environment_id": "env-pay-project",
                "runner_id": "runner-pay-project",
            },
            "SEARCH": {
                "description": "search",
                "repos": ["acme/search-service", "acme/webapp"],
            },
        },
        "default_project": "PAY",
    },
    "target_repos": {
        "acme/payments-api": {
            "description": "payments API",
            "base_branch": "main",
            "validate_command": "make check",
            "test_guidance": "pytest",
            "environment_id": "env-payments-api",
            "runner_id": "runner-payments-api",
        },
        "acme/search-service": {
            "description": "search service",
            "base_branch": "main",
            "validate_command": "cargo test",
            "test_guidance": "cargo test",
        },
        "acme/webapp": {
            "description": "web app",
            "base_branch": "main",
            "validate_command": "npm test",
            "test_guidance": "vitest",
        },
    },
    "default_target_repo": "acme/webapp",
    "spec_approval_required": True,
    "self_repo": "acme/factory-agents",
    "self_project": "PAY",
}


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dispatch = _load_script("factory_dispatch_env", DISPATCH_SCRIPT)


class EnvironmentResolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "config.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(CONFIG, fh)
        self._saved_config_path = dispatch.FOREMAN_CONFIG_PATH
        dispatch.FOREMAN_CONFIG_PATH = path
        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("FACTORY_FOREMAN_ENV", "FACTORY_FOREMAN_RUNNER")
        }

    def tearDown(self):
        dispatch.FOREMAN_CONFIG_PATH = self._saved_config_path
        self._tmp.cleanup()
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def resolve_env(self, flag=None, repo=None, project=None):
        with contextlib.redirect_stderr(io.StringIO()):
            return dispatch._resolve_environment(flag, repo, project)

    def resolve_runner(self, flag=None, repo=None, project=None):
        with contextlib.redirect_stderr(io.StringIO()):
            return dispatch._resolve_runner(flag, repo, project)

    def test_repo_environment_wins_over_project_and_env_var(self):
        os.environ["FACTORY_FOREMAN_ENV"] = "env-shared"
        value, source = self.resolve_env(repo="acme/payments-api")
        self.assertEqual(value, "env-payments-api")
        self.assertIn("target_repos[acme/payments-api]", source)

    def test_explicit_flag_wins_over_everything(self):
        value, source = self.resolve_env(flag="env-explicit",
                                         repo="acme/payments-api")
        self.assertEqual(value, "env-explicit")
        self.assertEqual(source, "flag")

    def test_project_environment_used_when_repo_declares_none(self):
        value, source = self.resolve_env(repo="acme/webapp", project="PAY")
        self.assertEqual(value, "env-pay-project")
        self.assertIn("project_routing[PAY]", source)

    def test_single_owning_project_is_derived_from_the_repo(self):
        # acme/search-service is only listed under SEARCH, which declares no
        # environment, so this falls through to the shared environment variable.
        os.environ["FACTORY_FOREMAN_ENV"] = "env-shared"
        value, source = self.resolve_env(repo="acme/search-service")
        self.assertEqual(value, "env-shared")
        self.assertEqual(source, "$FACTORY_FOREMAN_ENV")

    def test_shared_repo_without_project_context_skips_project_default(self):
        # acme/webapp is owned by two projects, so no single project applies.
        os.environ["FACTORY_FOREMAN_ENV"] = "env-shared"
        value, source = self.resolve_env(repo="acme/webapp")
        self.assertEqual(value, "env-shared")
        self.assertEqual(source, "$FACTORY_FOREMAN_ENV")

    def test_unresolved_environment_returns_none(self):
        self.assertEqual(self.resolve_env(repo="acme/webapp"), (None, None))

    def test_unknown_repo_warns_and_falls_back(self):
        os.environ["FACTORY_FOREMAN_ENV"] = "env-shared"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            value, source = dispatch._resolve_environment(None, "acme/ghost", None)
        self.assertEqual(value, "env-shared")
        self.assertEqual(source, "$FACTORY_FOREMAN_ENV")
        self.assertIn("acme/ghost", stderr.getvalue())

    def test_placeholder_values_are_treated_as_unset(self):
        os.environ["FACTORY_FOREMAN_ENV"] = "REPLACE_ME"
        self.assertEqual(self.resolve_env(repo="acme/webapp"), (None, None))

    def test_runner_resolution_mirrors_environment(self):
        value, source = self.resolve_runner(repo="acme/payments-api")
        self.assertEqual(value, "runner-payments-api")
        value, source = self.resolve_runner(repo="acme/webapp", project="PAY")
        self.assertEqual(value, "runner-pay-project")
        os.environ["FACTORY_FOREMAN_RUNNER"] = "runner-shared"
        value, source = self.resolve_runner(repo="acme/webapp")
        self.assertEqual(value, "runner-shared")
        self.assertEqual(source, "$FACTORY_FOREMAN_RUNNER")


class ProjectKeyFromIssueTest(unittest.TestCase):
    def test_issue_prefix_is_the_project(self):
        self.assertEqual(dispatch._project_key_from_issue("PAY-123"), "PAY")
        self.assertEqual(dispatch._project_key_from_issue("pay-1"), "PAY")
        self.assertIsNone(dispatch._project_key_from_issue(""))
        self.assertIsNone(dispatch._project_key_from_issue(None))


class PayloadTest(unittest.TestCase):
    def test_remote_carries_environment_and_runner_when_resolved(self):
        payload = dispatch._build_run_agents_payload(
            "base", "prompt", "auto", "env-1", "FA_triage_x", "triage", True,
            "runner-1",
        )
        self.assertEqual(payload["remote"]["environment_id"], "env-1")
        self.assertEqual(payload["remote"]["runner_id"], "runner-1")

    def test_remote_omits_unresolved_execution_settings(self):
        payload = dispatch._build_run_agents_payload(
            "base", "prompt", None, None, "FA_triage_x", "triage", True, None,
        )
        self.assertNotIn("environment_id", payload["remote"])
        self.assertNotIn("runner_id", payload["remote"])
        self.assertNotIn("model_id", payload)


if __name__ == "__main__":
    unittest.main()
