#!/usr/bin/env python3
"""Tests for the bootstrap CLI (`scripts/factory-init`).

Exercises the non-interactive (flag-driven) path against a temp repo root: the
five config files it writes, preservation of existing track configs, the
overwrite-safety rules, status-map merging, and target-repos JSON handling.
No network (every invocation passes --no-discover) and no TTY.
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
INIT_SCRIPT = os.path.join(REPO_ROOT, "scripts", "factory-init")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


factory_init = _load_script("factory_init_cli", INIT_SCRIPT)

BASE_FLAGS = [
    "--no-discover",
    "--self-repo", "acme/factory-agents",
    "--project", "ENG=backend services and APIs",
    "--self-project", "ENG",
    "--target-repo", "acme/webapp",
    "--target-description", "the main web application",
    "--target-base-branch", "main",
    "--target-validate-command", "make check",
    "--target-test-guidance", "pytest under tests/; add a failing-then-passing test",
    "--story-points-field", "customfield_10016",
]


def run_init(root, extra=None, flags=None):
    argv = list(flags if flags is not None else BASE_FLAGS)
    argv += ["--repo-root", root]
    argv += extra or []
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = factory_init.main(argv)
    return code, stdout.getvalue()


def read_json(root, *parts):
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return json.load(fh)


class WritesConfigsTest(unittest.TestCase):
    def test_writes_all_five_configs_and_overrides_skeleton(self):
        with tempfile.TemporaryDirectory() as root:
            code, out = run_init(root)
            self.assertEqual(code, 0)
            summary = json.loads(out)
            self.assertEqual(len(summary["written"]), 6)  # foreman + 4 tracks + overrides

            foreman = read_json(root, "foreman", "config.json")
            self.assertEqual(foreman["self_repo"], "acme/factory-agents")
            self.assertEqual(foreman["self_project"], "ENG")
            self.assertEqual(foreman["tracker"]["provider"], "jira")
            self.assertEqual(foreman["tracker"]["default_project"], "ENG")
            self.assertEqual(foreman["tracker"]["issue_type"], "Task")
            self.assertEqual(foreman["tracker"]["story_points_field"],
                             "customfield_10016")
            self.assertEqual(foreman["default_target_repo"], "acme/webapp")
            self.assertTrue(foreman["spec_approval_required"])
            entry = foreman["target_repos"]["acme/webapp"]
            self.assertEqual(entry["validate_command"], "make check")
            self.assertNotIn("app_start_command", entry)

            for track, skill in factory_init.DEFAULT_ENTRYPOINT_SKILLS.items():
                config = read_json(root, track, "config.json")
                self.assertEqual(config["agent"]["entrypoint_skill"], skill)
                self.assertEqual(config["model"], "auto")
                self.assertEqual(config["repos"]["self"], "acme/factory-agents")

            overrides = read_json(root, "scripts", "reviewer_overrides.json")
            self.assertEqual(overrides["overrides"], {})
            self.assertEqual(overrides["slack_users"], {})

    def test_status_map_defaults_merged_with_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root, extra=["--status-map", "Done=Shipped,Canceled=Shipped"])
            self.assertEqual(code, 0)
            status_map = read_json(root, "foreman", "config.json")["tracker"]["status_map"]
            self.assertEqual(status_map["Done"], "Shipped")
            self.assertEqual(status_map["Canceled"], "Shipped")
            self.assertEqual(status_map["In Progress"], "In Progress")
            self.assertEqual(sorted(status_map), sorted(factory_init.FACTORY_STATES))

    def test_story_points_none_disables_estimates(self):
        with tempfile.TemporaryDirectory() as root:
            flags = [f if f != "customfield_10016" else "none" for f in BASE_FLAGS]
            code, _ = run_init(root, flags=flags)
            self.assertEqual(code, 0)
            foreman = read_json(root, "foreman", "config.json")
            self.assertIsNone(foreman["tracker"]["story_points_field"])

    def test_target_repos_json_with_app_fields(self):
        repos = {
            "acme/webapp": {
                "description": "the web app",
                "base_branch": "main",
                "validate_command": "make check",
                "test_guidance": "pytest under tests/",
                "app_start_command": "make dev",
                "app_url": "http://localhost:3000",
            },
            "acme/api": {
                "description": "the backend API",
                "base_branch": "develop",
                "validate_command": "./scripts/ci",
                "test_guidance": "go test ./...",
            },
        }
        flags = [
            "--no-discover",
            "--self-repo", "acme/factory-agents",
            "--project", "ENG=everything",
            "--story-points-field", "none",
            "--target-repos-json", json.dumps(repos),
            "--default-target-repo", "acme/api",
        ]
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root, flags=flags)
            self.assertEqual(code, 0)
            foreman = read_json(root, "foreman", "config.json")
            self.assertEqual(foreman["default_target_repo"], "acme/api")
            self.assertEqual(
                foreman["target_repos"]["acme/webapp"]["app_url"],
                "http://localhost:3000")

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            code, out = run_init(root, extra=["--dry-run"])
            self.assertEqual(code, 0)
            self.assertFalse(
                os.path.exists(os.path.join(root, "foreman", "config.json")))
            summary = json.loads(out)
            self.assertTrue(all(w["dry_run"] for w in summary["written"]))


class MultiProjectTest(unittest.TestCase):
    """A Jira project owns a subset of the repos; init records that mapping."""

    REPOS = {
        "acme/payments-api": {
            "description": "payments API",
            "base_branch": "main",
            "validate_command": "make check",
            "test_guidance": "pytest under tests/",
            "environment_id": "env-payments",
        },
        "acme/search-service": {
            "description": "search service",
            "base_branch": "main",
            "validate_command": "cargo test",
            "test_guidance": "cargo test",
        },
    }

    def _flags(self, extra=None):
        return [
            "--no-discover",
            "--self-repo", "acme/factory-agents",
            "--story-points-field", "customfield_10016",
            "--target-repos-json", json.dumps(self.REPOS),
            "--default-target-repo", "acme/payments-api",
        ] + (extra or [])

    def test_project_repos_scopes_each_project(self):
        flags = self._flags([
            "--project", "PAY=payments and billing",
            "--project", "SEARCH=search and discovery",
            "--default-project", "PAY",
            "--self-project", "PAY",
            "--project-repos", "PAY=acme/payments-api",
            "--project-repos", "SEARCH=acme/search-service",
        ])
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root, flags=flags)
            self.assertEqual(code, 0)
            routing = read_json(root, "foreman", "config.json")["tracker"][
                "project_routing"]
            self.assertEqual(routing["PAY"]["repos"], ["acme/payments-api"])
            self.assertEqual(routing["PAY"]["description"],
                             "payments and billing")
            self.assertEqual(routing["SEARCH"]["repos"], ["acme/search-service"])

    def test_single_project_stays_a_plain_description_string(self):
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root)
            self.assertEqual(code, 0)
            routing = read_json(root, "foreman", "config.json")["tracker"][
                "project_routing"]
            self.assertEqual(routing["ENG"], "backend services and APIs")

    def test_projects_json_carries_per_project_overrides(self):
        projects = {
            "PAY": {
                "description": "payments",
                "repos": ["acme/payments-api"],
                "default_repo": "acme/payments-api",
            },
            "SEARCH": {
                "description": "search",
                "repos": ["acme/search-service"],
                "status_map": {"In Review": "Code Review"},
                "story_points_field": "customfield_10032",
                "issue_type": "Bug",
                "spec_approval_required": False,
            },
        }
        flags = self._flags([
            "--projects-json", json.dumps(projects),
            "--default-project", "PAY",
            "--self-project", "PAY",
        ])
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root, flags=flags)
            self.assertEqual(code, 0)
            routing = read_json(root, "foreman", "config.json")["tracker"][
                "project_routing"]
            self.assertEqual(routing["SEARCH"]["story_points_field"],
                             "customfield_10032")
            self.assertFalse(routing["SEARCH"]["spec_approval_required"])

    def test_project_repos_referencing_unknown_repo_fails(self):
        flags = self._flags([
            "--project", "PAY=payments",
            "--project-repos", "PAY=acme/ghost",
            "--self-project", "PAY",
        ])
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as ctx:
                    run_init(root, flags=flags)
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("acme/ghost", stderr.getvalue())

    def test_project_repos_for_unknown_project_fails(self):
        flags = self._flags([
            "--project", "PAY=payments",
            "--project-repos", "NOPE=acme/payments-api",
            "--self-project", "PAY",
        ])
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_init(root, flags=flags)
            self.assertEqual(ctx.exception.code, 1)

    def test_project_default_repo_outside_its_subset_fails(self):
        projects = {
            "PAY": {
                "description": "payments",
                "repos": ["acme/payments-api"],
                "default_repo": "acme/search-service",
            }
        }
        flags = self._flags([
            "--projects-json", json.dumps(projects),
            "--self-project", "PAY",
        ])
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_init(root, flags=flags)
            self.assertEqual(ctx.exception.code, 1)


class MergeTest(unittest.TestCase):
    """--merge onboards one more project/repo without rewriting the rest."""

    def _configure(self, root):
        code, _ = run_init(root, extra=["--status-map", "Done=Shipped"])
        self.assertEqual(code, 0)

    def test_merge_adds_project_and_repo_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as root:
            self._configure(root)
            code, _ = run_init(root, flags=[
                "--no-discover", "--merge",
                "--self-repo", "acme/factory-agents",
                "--project", "OPS=infrastructure and deploys",
                "--project-repos", "OPS=acme/terraform",
                "--target-repo", "acme/terraform",
                "--target-description", "infra as code",
                "--target-base-branch", "main",
                "--target-validate-command", "terraform validate",
                "--target-test-guidance", "terraform test under tests/",
                "--target-environment-id", "env-ops",
            ])
            self.assertEqual(code, 0)
            foreman = read_json(root, "foreman", "config.json")
            routing = foreman["tracker"]["project_routing"]
            self.assertEqual(sorted(routing), ["ENG", "OPS"])
            self.assertEqual(routing["OPS"]["repos"], ["acme/terraform"])
            self.assertEqual(sorted(foreman["target_repos"]),
                             ["acme/terraform", "acme/webapp"])
            self.assertEqual(
                foreman["target_repos"]["acme/terraform"]["environment_id"],
                "env-ops")
            # Untouched values survive the merge.
            self.assertEqual(foreman["tracker"]["status_map"]["Done"], "Shipped")
            self.assertEqual(foreman["tracker"]["default_project"], "ENG")
            self.assertEqual(foreman["default_target_repo"], "acme/webapp")

    def test_merge_can_repoint_defaults_when_asked(self):
        with tempfile.TemporaryDirectory() as root:
            self._configure(root)
            code, _ = run_init(root, flags=[
                "--no-discover", "--merge",
                "--self-repo", "acme/factory-agents",
                "--project", "OPS=infrastructure",
                "--default-project", "OPS",
                "--target-repo", "acme/terraform",
                "--target-description", "infra as code",
                "--target-base-branch", "main",
                "--target-validate-command", "terraform validate",
                "--target-test-guidance", "terraform test",
                "--default-target-repo", "acme/terraform",
            ])
            self.assertEqual(code, 0)
            foreman = read_json(root, "foreman", "config.json")
            self.assertEqual(foreman["tracker"]["default_project"], "OPS")
            self.assertEqual(foreman["default_target_repo"], "acme/terraform")

    def test_refusal_points_at_merge_and_force(self):
        with tempfile.TemporaryDirectory() as root:
            self._configure(root)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as ctx:
                    run_init(root, extra=["--self-project", "OTHER"])
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("--merge", stderr.getvalue())
            self.assertIn("--force", stderr.getvalue())


class PreservationAndSafetyTest(unittest.TestCase):
    def test_preserves_existing_track_skill_and_model(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "triage"))
            with open(os.path.join(root, "triage", "config.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({
                    "agent": {"entrypoint_skill": "custom-triage"},
                    "model": "claude-4-opus",
                    "repos": {"self": "old/repo"},
                }, fh)
            code, _ = run_init(root)
            self.assertEqual(code, 0)
            config = read_json(root, "triage", "config.json")
            self.assertEqual(config["agent"]["entrypoint_skill"], "custom-triage")
            self.assertEqual(config["model"], "claude-4-opus")
            self.assertEqual(config["repos"]["self"], "acme/factory-agents")

    def test_refuses_to_overwrite_customized_foreman_without_force(self):
        with tempfile.TemporaryDirectory() as root:
            code, _ = run_init(root)
            self.assertEqual(code, 0)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    run_init(root, extra=["--self-project", "OTHER"])
            self.assertEqual(ctx.exception.code, 1)
            code, _ = run_init(root, extra=["--force"])
            self.assertEqual(code, 0)

    def test_overwrites_pristine_placeholder_config_without_force(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "foreman"))
            with open(os.path.join(root, "foreman", "config.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"self_repo": "REPLACE_ME/REPLACE_ME"}, fh)
            code, _ = run_init(root)
            self.assertEqual(code, 0)
            foreman = read_json(root, "foreman", "config.json")
            self.assertEqual(foreman["self_repo"], "acme/factory-agents")

    def test_never_overwrites_reviewer_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "scripts"))
            existing = {"overrides": {"me": {"github": "me"}}, "slack_users": {}}
            path = os.path.join(root, "scripts", "reviewer_overrides.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(existing, fh)
            code, out = run_init(root)
            self.assertEqual(code, 0)
            self.assertEqual(read_json(root, "scripts", "reviewer_overrides.json"),
                             existing)
            summary = json.loads(out)
            self.assertTrue(any(s["path"] == path for s in summary["skipped"]))


class FlagValidationTest(unittest.TestCase):
    def test_missing_required_flags_fail_loud(self):
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    factory_init.main([
                        "--no-discover", "--self-repo", "acme/x",
                        "--repo-root", root,
                    ])
            self.assertEqual(ctx.exception.code, 1)

    def test_incomplete_single_target_repo_fails(self):
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    factory_init.main([
                        "--no-discover", "--self-repo", "acme/x",
                        "--project", "ENG=all",
                        "--target-repo", "acme/webapp",
                        "--repo-root", root,
                    ])

    def test_target_repos_json_missing_field_fails(self):
        with tempfile.TemporaryDirectory() as root:
            repos = {"acme/webapp": {"description": "d", "base_branch": "main"}}
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    factory_init.main([
                        "--no-discover", "--self-repo", "acme/x",
                        "--project", "ENG=all",
                        "--story-points-field", "none",
                        "--target-repos-json", json.dumps(repos),
                        "--repo-root", root,
                    ])

    def test_unknown_status_map_state_fails(self):
        with tempfile.TemporaryDirectory() as root:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_init(root, extra=["--status-map", "Bogus=Whatever"])


if __name__ == "__main__":
    unittest.main()
