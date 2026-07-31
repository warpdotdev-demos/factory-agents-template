#!/usr/bin/env python3
"""Tests for the config validator (`scripts/factory-validate-config`).

Exercises the validator against synthetic config sets in a temp repo root:
valid configs pass, structural gaps fail, cross-file repos.self/self_repo
consistency is enforced, a pristine placeholder template passes with a
warning, and a partially-configured repo fails.
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
VALIDATE_SCRIPT = os.path.join(REPO_ROOT, "scripts", "factory-validate-config")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = _load_script("factory_validate_config_cli", VALIDATE_SCRIPT)

VALID_FOREMAN = {
    "tracker": {
        "provider": "jira",
        "browse_url": "https://acme.atlassian.net",
        "project_routing": {"ENG": "backend services and APIs"},
        "default_project": "ENG",
        "status_map": {
            "Triage": "To Do",
            "Todo": "To Do",
            "In Progress": "In Progress",
            "In Review": "In Review",
            "Done": "Done",
            "Canceled": "Done",
        },
        "story_points_field": "customfield_10016",
        "issue_type": "Task",
    },
    "target_repos": {
        "acme/webapp": {
            "description": "the main web application",
            "base_branch": "main",
            "validate_command": "make check",
            "test_guidance": "pytest under tests/",
            "app_start_command": "make dev",
            "app_url": "http://localhost:3000",
        }
    },
    "default_target_repo": "acme/webapp",
    "spec_approval_required": True,
    "self_repo": "acme/factory-agents",
    "self_project": "ENG",
}

TRACK_SKILLS = {
    "triage": "factory-triage",
    "spec": "factory-spec",
    "implementation": "factory-implement",
    "code-review": "factory-review",
}


def write_configs(root, foreman=None, self_override=None):
    foreman = foreman if foreman is not None else copy.deepcopy(VALID_FOREMAN)
    os.makedirs(os.path.join(root, "foreman"), exist_ok=True)
    with open(os.path.join(root, "foreman", "config.json"), "w",
              encoding="utf-8") as fh:
        json.dump(foreman, fh)
    repo_self = self_override or foreman.get("self_repo", "acme/factory-agents")
    for track, skill in TRACK_SKILLS.items():
        os.makedirs(os.path.join(root, track), exist_ok=True)
        with open(os.path.join(root, track, "config.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({
                "agent": {"entrypoint_skill": skill},
                "model": "auto",
                "repos": {"self": repo_self},
            }, fh)


def run_validate(root):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = validate.main(["--repo-root", root])
    return code, json.loads(stdout.getvalue())


class ValidConfigTest(unittest.TestCase):
    def test_valid_configs_pass(self):
        with tempfile.TemporaryDirectory() as root:
            write_configs(root)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "configured")
            self.assertEqual(result["errors"], [])

    def test_unknown_target_repo_field_warns_but_passes(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            foreman["target_repos"]["acme/webapp"]["bogus_field"] = "x"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("bogus_field" in w for w in result["warnings"]))


class StructuralErrorTest(unittest.TestCase):
    def test_missing_status_map_state_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            del foreman["tracker"]["status_map"]["Canceled"]
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("Canceled" in e for e in result["errors"]))

    def test_default_target_repo_not_in_map_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            foreman["default_target_repo"] = "acme/other"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("default_target_repo" in e for e in result["errors"]))

    def test_default_project_not_in_routing_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            foreman["tracker"]["default_project"] = "OTHER"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)

    def test_target_repo_missing_required_field_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            del foreman["target_repos"]["acme/webapp"]["validate_command"]
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)

    def test_missing_track_config_fails(self):
        with tempfile.TemporaryDirectory() as root:
            write_configs(root)
            os.remove(os.path.join(root, "spec", "config.json"))
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("spec" in e and "missing" in e
                                for e in result["errors"]))


def multi_project_foreman():
    """A two-project config whose projects each own a repo subset."""
    foreman = copy.deepcopy(VALID_FOREMAN)
    foreman["tracker"]["project_routing"] = {
        "PAY": {
            "description": "payments and billing",
            "repos": ["acme/webapp", "acme/payments-api"],
            "default_repo": "acme/payments-api",
        },
        "SEARCH": {
            "description": "search and discovery",
            "repos": ["acme/webapp"],
            "status_map": {"In Review": "Code Review"},
            "story_points_field": "customfield_10032",
            "issue_type": "Bug",
            "spec_approval_required": False,
            "environment_id": "env-search",
        },
    }
    foreman["tracker"]["default_project"] = "PAY"
    foreman["self_project"] = "PAY"
    foreman["target_repos"]["acme/payments-api"] = {
        "description": "the payments API",
        "base_branch": "main",
        "validate_command": "make check",
        "test_guidance": "pytest under tests/",
        "environment_id": "env-payments",
        "runner_id": "runner-payments",
    }
    return foreman


class ProjectRoutingTest(unittest.TestCase):
    def test_multi_project_config_with_repo_subsets_passes(self):
        with tempfile.TemporaryDirectory() as root:
            write_configs(root, foreman=multi_project_foreman())
            code, result = run_validate(root)
            self.assertEqual(code, 0, result["errors"])
            self.assertEqual(result["errors"], [])

    def test_project_referencing_unknown_repo_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["PAY"]["repos"].append("acme/ghost")
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("acme/ghost" in e for e in result["errors"]))

    def test_default_repo_outside_project_subset_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["SEARCH"]["default_repo"] = \
                "acme/payments-api"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("default_repo" in e for e in result["errors"]))

    def test_unroutable_repo_warns(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["target_repos"]["acme/orphan"] = {
                "description": "nobody owns me",
                "base_branch": "main",
                "validate_command": "make check",
                "test_guidance": "pytest",
            }
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("acme/orphan" in w for w in result["warnings"]))

    def test_unscoped_project_alongside_scoped_ones_warns(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["PLATFORM"] = "the platform"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("PLATFORM" in w for w in result["warnings"]))

    def test_several_unscoped_projects_warn(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = copy.deepcopy(VALID_FOREMAN)
            foreman["tracker"]["project_routing"] = {
                "ENG": "backend services",
                "WEB": "the web app",
            }
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("none declares" in w for w in result["warnings"]))

    def test_project_status_map_with_unknown_state_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["SEARCH"]["status_map"] = \
                {"Bogus": "Whatever"}
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("Bogus" in e for e in result["errors"]))

    def test_project_missing_description_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            del foreman["tracker"]["project_routing"]["PAY"]["description"]
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("description" in e for e in result["errors"]))

    def test_unknown_project_field_warns(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["PAY"]["bogus"] = "x"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("bogus" in w for w in result["warnings"]))

    def test_non_boolean_project_spec_approval_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["tracker"]["project_routing"]["SEARCH"][
                "spec_approval_required"] = "yes"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 1)

    def test_self_project_outside_routing_warns(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            foreman["self_project"] = "PLATFORM"
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(any("self_project" in w for w in result["warnings"]))

    def test_repo_execution_fields_are_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = multi_project_foreman()
            write_configs(root, foreman=foreman)
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertFalse(any("environment_id" in w for w in result["warnings"]))


class ConsistencyTest(unittest.TestCase):
    def test_mismatched_repos_self_fails(self):
        with tempfile.TemporaryDirectory() as root:
            write_configs(root, self_override="other/repo")
            code, result = run_validate(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("repos.self" in e for e in result["errors"]))


class PlaceholderPolicyTest(unittest.TestCase):
    def _pristine_foreman(self):
        foreman = copy.deepcopy(VALID_FOREMAN)
        foreman["tracker"]["project_routing"] = {
            "REPLACE_ME": "REPLACE_ME - what this project owns"}
        foreman["tracker"]["default_project"] = "REPLACE_ME"
        foreman["target_repos"] = {
            "REPLACE_ME/REPLACE_ME": {
                "description": "REPLACE_ME - what this repo owns",
                "base_branch": "main",
                "validate_command": "REPLACE_ME",
                "test_guidance": "REPLACE_ME",
            }
        }
        foreman["default_target_repo"] = "REPLACE_ME/REPLACE_ME"
        foreman["self_repo"] = "REPLACE_ME/REPLACE_ME"
        foreman["self_project"] = "REPLACE_ME"
        del foreman["tracker"]["browse_url"]
        return foreman

    def test_pristine_template_warns_but_passes(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = self._pristine_foreman()
            write_configs(root, foreman=foreman,
                          self_override="REPLACE_ME/REPLACE_ME")
            code, result = run_validate(root)
            self.assertEqual(code, 0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "pristine-template")
            self.assertTrue(any("REPLACE_ME" in w for w in result["warnings"]))

    def test_partially_configured_fails(self):
        with tempfile.TemporaryDirectory() as root:
            foreman = self._pristine_foreman()
            foreman["self_repo"] = "acme/factory-agents"  # identity set...
            write_configs(root, foreman=foreman,
                          self_override="acme/factory-agents")
            code, result = run_validate(root)  # ...but placeholders remain
            self.assertEqual(code, 1)
            self.assertEqual(result["state"], "partially-configured")


if __name__ == "__main__":
    unittest.main()
