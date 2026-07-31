#!/usr/bin/env python3
"""Tests for the routing resolver (`scripts/factory-config`).

Exercises the project -> repo mapping against synthetic configs in a temp repo
root: the two accepted `project_routing` value shapes (description string and
project object), the repo candidates a project exposes, per-project tracker
overrides, the derived repo -> projects reverse index, and the resolved
per-repo execution settings.
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_SCRIPT = os.path.join(REPO_ROOT, "scripts", "factory-config")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


factory_config = _load_script("factory_config_cli", CONFIG_SCRIPT)

SITE_STATUS_MAP = {
    "Triage": "To Do",
    "Todo": "To Do",
    "In Progress": "In Progress",
    "In Review": "In Review",
    "Done": "Done",
    "Canceled": "Done",
}

MULTI_PROJECT = {
    "tracker": {
        "provider": "jira",
        "project_routing": {
            "PAY": {
                "description": "payments and billing",
                "repos": ["acme/payments-api", "acme/webapp"],
                "default_repo": "acme/payments-api",
                "environment_id": "env-pay",
            },
            "SEARCH": {
                "description": "search and discovery",
                "repos": ["acme/search-service", "acme/webapp"],
                "status_map": {"In Review": "Code Review"},
                "story_points_field": "customfield_10032",
                "issue_type": "Bug",
                "spec_approval_required": False,
            },
        },
        "default_project": "PAY",
        "status_map": dict(SITE_STATUS_MAP),
        "story_points_field": "customfield_10016",
        "issue_type": "Task",
    },
    "target_repos": {
        "acme/payments-api": {
            "description": "payments API",
            "base_branch": "main",
            "validate_command": "make check",
            "test_guidance": "pytest under tests/",
            "environment_id": "env-payments-api",
        },
        "acme/search-service": {
            "description": "search service",
            "base_branch": "main",
            "validate_command": "cargo test",
            "test_guidance": "cargo test",
        },
        "acme/webapp": {
            "description": "shared web app",
            "base_branch": "main",
            "validate_command": "npm test",
            "test_guidance": "vitest beside the component",
        },
    },
    "default_target_repo": "acme/webapp",
    "spec_approval_required": True,
    "self_repo": "acme/factory-agents",
    "self_project": "PAY",
}

SINGLE_PROJECT = {
    "tracker": {
        "provider": "jira",
        "project_routing": {"ENG": "all product engineering"},
        "default_project": "ENG",
        "status_map": dict(SITE_STATUS_MAP),
        "story_points_field": "customfield_10016",
        "issue_type": "Task",
    },
    "target_repos": {
        "acme/webapp": {
            "description": "the web app",
            "base_branch": "main",
            "validate_command": "make check",
            "test_guidance": "pytest",
        },
        "acme/api": {
            "description": "the API",
            "base_branch": "develop",
            "validate_command": "./scripts/ci",
            "test_guidance": "go test ./...",
        },
    },
    "default_target_repo": "acme/webapp",
    "spec_approval_required": True,
    "self_repo": "acme/factory-agents",
    "self_project": "ENG",
}


@contextlib.contextmanager
def config_root(config):
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "foreman"))
        with open(os.path.join(root, "foreman", "config.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(config, fh)
        yield root


def run_cli(root, argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = factory_config.main(["--repo-root", root, *argv])
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


def normalized(config):
    return factory_config.normalize(copy.deepcopy(config))


class ProjectKeyTest(unittest.TestCase):
    def test_key_from_issue(self):
        self.assertEqual(factory_config.project_key_from_issue("PAY-123"), "PAY")
        self.assertEqual(factory_config.project_key_from_issue("pay-9"), "PAY")
        self.assertEqual(factory_config.project_key_from_issue(" PAY-1 "), "PAY")
        self.assertEqual(factory_config.project_key_from_issue("PAY"), "PAY")
        self.assertEqual(factory_config.project_key_from_issue(""), "")

    def test_multi_hyphen_key_keeps_prefix(self):
        self.assertEqual(
            factory_config.project_key_from_issue("MOBILE-APP-42"), "MOBILE-APP")


class RepoCandidatesTest(unittest.TestCase):
    def test_project_object_scopes_candidates(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(root, ["repos", "--issue", "PAY-123"])
        self.assertEqual(code, 0)
        self.assertEqual(out["project"], "PAY")
        self.assertTrue(out["scoped"])
        self.assertEqual([r["repo"] for r in out["repos"]],
                         ["acme/payments-api", "acme/webapp"])
        self.assertEqual(out["default_repo"], "acme/payments-api")

    def test_candidates_exclude_other_projects_repos(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(root, ["repos", "--key", "SEARCH"])
        self.assertNotIn("acme/payments-api", [r["repo"] for r in out["repos"]])

    def test_project_without_repos_keeps_every_repo(self):
        with config_root(SINGLE_PROJECT) as root:
            code, out, _ = run_cli(root, ["repos", "--key", "ENG"])
        self.assertEqual(code, 0)
        self.assertFalse(out["scoped"])
        self.assertEqual(sorted(r["repo"] for r in out["repos"]),
                         ["acme/api", "acme/webapp"])

    def test_default_repo_falls_back_to_global_then_first(self):
        norm = normalized(MULTI_PROJECT)
        # SEARCH declares no default_repo, but the global default is in its list.
        self.assertEqual(factory_config.project_default_repo(norm, "SEARCH"),
                         "acme/webapp")
        config = copy.deepcopy(MULTI_PROJECT)
        config["default_target_repo"] = "acme/payments-api"
        norm = normalized(config)
        # Now the global default is outside SEARCH's list -> its first repo wins.
        self.assertEqual(factory_config.project_default_repo(norm, "SEARCH"),
                         "acme/search-service")

    def test_unknown_repo_reference_is_dropped_from_candidates(self):
        config = copy.deepcopy(MULTI_PROJECT)
        config["tracker"]["project_routing"]["PAY"]["repos"].append("acme/ghost")
        norm = normalized(config)
        self.assertEqual(factory_config.project_repo_keys(norm, "PAY"),
                         ["acme/payments-api", "acme/webapp"])


class ProjectSettingsTest(unittest.TestCase):
    def test_overrides_layer_over_site_defaults(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(root, ["project", "--key", "SEARCH"])
        self.assertEqual(code, 0)
        self.assertTrue(out["configured"])
        self.assertEqual(out["status_map"]["In Review"], "Code Review")
        self.assertEqual(out["status_map"]["Done"], "Done")  # site default kept
        self.assertEqual(out["story_points_field"], "customfield_10032")
        self.assertEqual(out["issue_type"], "Bug")
        self.assertFalse(out["spec_approval_required"])

    def test_project_without_overrides_uses_site_defaults(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(root, ["project", "--issue", "PAY-7"])
        self.assertEqual(out["status_map"], SITE_STATUS_MAP)
        self.assertEqual(out["story_points_field"], "customfield_10016")
        self.assertEqual(out["issue_type"], "Task")
        self.assertTrue(out["spec_approval_required"])

    def test_story_points_can_be_disabled_per_project(self):
        config = copy.deepcopy(MULTI_PROJECT)
        config["tracker"]["project_routing"]["PAY"]["story_points_field"] = None
        with config_root(config) as root:
            _, out, _ = run_cli(root, ["project", "--key", "PAY"])
        self.assertIsNone(out["story_points_field"])

    def test_unknown_project_warns_and_uses_site_defaults(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, stderr = run_cli(root, ["project", "--key", "NOPE"])
        self.assertEqual(code, 0)
        self.assertFalse(out["configured"])
        self.assertIn("NOPE", stderr)
        self.assertEqual(out["status_map"], SITE_STATUS_MAP)

    def test_project_defaults_to_default_project(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(root, ["project"])
        self.assertEqual(out["key"], "PAY")


class ReverseIndexTest(unittest.TestCase):
    def test_shared_repo_lists_every_owning_project(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(
                root, ["projects-for-repo", "--repo", "acme/webapp"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out["projects"]), ["PAY", "SEARCH"])

    def test_scoped_ownership_wins_over_unscoped_projects(self):
        config = copy.deepcopy(MULTI_PROJECT)
        config["tracker"]["project_routing"]["PLATFORM"] = "the platform"
        with config_root(config) as root:
            _, out, _ = run_cli(
                root, ["projects-for-repo", "--repo", "acme/payments-api"])
        self.assertEqual(out["projects"], ["PAY"])

    def test_every_project_owns_every_repo_when_none_is_scoped(self):
        with config_root(SINGLE_PROJECT) as root:
            _, out, _ = run_cli(
                root, ["projects-for-repo", "--repo", "acme/api"])
        self.assertEqual(out["projects"], ["ENG"])


class RepoSettingsTest(unittest.TestCase):
    def test_repo_settings_and_environment(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(root, ["repo", "--repo", "acme/payments-api"])
        self.assertEqual(code, 0)
        self.assertEqual(out["validate_command"], "make check")
        self.assertEqual(out["base_branch"], "main")
        self.assertEqual(out["environment_id"], "env-payments-api")
        self.assertEqual(out["projects"], ["PAY"])
        self.assertEqual(out["project"], "PAY")

    def test_repo_inherits_project_environment(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(
                root, ["repo", "--repo", "acme/webapp", "--key", "PAY"])
        self.assertEqual(out["environment_id"], "env-pay")

    def test_shared_repo_has_no_project_environment_without_context(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(root, ["repo", "--repo", "acme/webapp"])
        self.assertIsNone(out["environment_id"])
        self.assertIsNone(out["project"])

    def test_repo_spec_approval_follows_project_override(self):
        with config_root(MULTI_PROJECT) as root:
            _, out, _ = run_cli(
                root, ["repo", "--repo", "acme/webapp", "--key", "SEARCH"])
        self.assertFalse(out["spec_approval_required"])

    def test_unknown_repo_fails_loudly(self):
        with config_root(MULTI_PROJECT) as root:
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as ctx:
                    factory_config.main(
                        ["--repo-root", root, "repo", "--repo", "acme/ghost"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("acme/ghost", stderr.getvalue())


class ProjectsListingTest(unittest.TestCase):
    def test_projects_lists_every_routed_project(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(root, ["projects"])
        self.assertEqual(code, 0)
        self.assertEqual(out["default_project"], "PAY")
        self.assertEqual([p["key"] for p in out["projects"]], ["PAY", "SEARCH"])
        self.assertEqual(out["projects"][0]["repos"],
                         ["acme/payments-api", "acme/webapp"])

    def test_show_emits_the_normalized_config(self):
        with config_root(MULTI_PROJECT) as root:
            code, out, _ = run_cli(root, ["show"])
        self.assertEqual(code, 0)
        self.assertEqual(out["self_repo"], "acme/factory-agents")
        self.assertIn("PAY", out["projects"])

    def test_missing_config_fails_loudly(self):
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    factory_config.main(["--repo-root", root, "show"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
