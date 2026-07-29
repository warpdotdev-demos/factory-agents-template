#!/usr/bin/env python3
"""Unit tests for the tracker seam's provider resolution and delegation.

`scripts/tracker` must resolve the provider as: --provider flag, then the
FACTORY_TRACKER_PROVIDER environment variable, then tracker.provider from
foreman/config.json, then the built-in default ('jira') -- and forward the
subcommand + arguments unchanged to the provider script.

Loads the tracker as a module and monkey-patches `subprocess.run` so it
exercises the delegation logic without running any provider (no network).
"""
import importlib.util
import os
import subprocess
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER_SCRIPT = os.path.join(REPO_ROOT, "scripts", "tracker")
JIRA_SCRIPT = os.path.join(REPO_ROOT, "scripts", "jira")
MOCK_SCRIPT = os.path.join(REPO_ROOT, "scripts", "mock-issue-tracker")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tracker = _load_script("tracker_cli", TRACKER_SCRIPT)


class ResolveProviderTest(unittest.TestCase):
    def test_flag_wins_over_env_and_config(self):
        self.assertEqual(
            tracker.resolve_provider("mock-issue-tracker", "jira", "jira"),
            "mock-issue-tracker",
        )

    def test_env_wins_over_config(self):
        self.assertEqual(
            tracker.resolve_provider(None, "mock-issue-tracker", "jira"),
            "mock-issue-tracker",
        )

    def test_config_wins_over_default(self):
        self.assertEqual(
            tracker.resolve_provider(None, None, "mock-issue-tracker"),
            "mock-issue-tracker",
        )

    def test_default_is_jira(self):
        self.assertEqual(tracker.resolve_provider(None, None, None), "jira")
        self.assertEqual(tracker.resolve_provider("", "", ""), "jira")
        self.assertEqual(tracker.DEFAULT_PROVIDER, "jira")

    def test_config_provider_reads_foreman_config(self):
        # The template's committed foreman/config.json sets tracker.provider.
        self.assertEqual(tracker._config_provider(), "jira")


class DelegationTest(unittest.TestCase):
    def setUp(self):
        self._saved_env = os.environ.get("FACTORY_TRACKER_PROVIDER")
        os.environ.pop("FACTORY_TRACKER_PROVIDER", None)
        self._old_run = subprocess.run
        self.calls = []

        def fake_run(argv, **_kwargs):
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(argv, returncode=0)

        subprocess.run = fake_run

    def tearDown(self):
        subprocess.run = self._old_run
        if self._saved_env is None:
            os.environ.pop("FACTORY_TRACKER_PROVIDER", None)
        else:
            os.environ["FACTORY_TRACKER_PROVIDER"] = self._saved_env

    def test_defaults_to_jira_provider(self):
        ret = tracker.main(["get-issue", "PROJ-1"])
        self.assertEqual(ret, 0)
        self.assertEqual(self.calls, [[JIRA_SCRIPT, "get-issue", "PROJ-1"]])

    def test_provider_flag_delegates_to_mock(self):
        ret = tracker.main([
            "--provider", "mock-issue-tracker",
            "create-issue", "--title", "t", "--description", "d",
        ])
        self.assertEqual(ret, 0)
        self.assertEqual(self.calls, [[
            MOCK_SCRIPT, "create-issue", "--title", "t", "--description", "d",
        ]])

    def test_env_var_delegates_to_mock(self):
        os.environ["FACTORY_TRACKER_PROVIDER"] = "mock-issue-tracker"
        ret = tracker.main(["list-labels"])
        self.assertEqual(ret, 0)
        self.assertEqual(self.calls, [[MOCK_SCRIPT, "list-labels"]])

    def test_arguments_pass_through_unchanged(self):
        ret = tracker.main([
            "update-issue", "PROJ-2",
            "--status", "In Review",
            "--add-label", "impl-done",
        ])
        self.assertEqual(ret, 0)
        self.assertEqual(self.calls, [[
            JIRA_SCRIPT, "update-issue", "PROJ-2",
            "--status", "In Review",
            "--add-label", "impl-done",
        ]])

    def test_unknown_provider_fails_loudly(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                tracker.main(["--provider", "linear", "get-issue", "PROJ-1"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
