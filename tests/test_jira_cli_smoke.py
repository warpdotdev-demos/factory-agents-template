#!/usr/bin/env python3
"""Arg-parsing smoke tests for the Jira provider CLI (`scripts/jira`).

Verifies the command surface parses (subcommands, flags, positionals), --help
works for every subcommand, and update-issue's pre-network validation fails
loudly. No network, no Jira credentials.
"""
import contextlib
import importlib.util
import io
import os
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JIRA_SCRIPT = os.path.join(REPO_ROOT, "scripts", "jira")

SUBCOMMANDS = [
    "create-issue", "comment", "attach-pr", "list-labels",
    "search-issues", "get-issue", "update-issue", "find-user",
]


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jira = _load_script("jira_provider_cli", JIRA_SCRIPT)


class HelpSmokeTest(unittest.TestCase):
    def _assert_help_exits_zero(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                jira.build_parser().parse_args(argv)
        self.assertEqual(ctx.exception.code, 0)

    def test_top_level_help(self):
        self._assert_help_exits_zero(["--help"])

    def test_every_subcommand_help(self):
        for sub in SUBCOMMANDS:
            with self.subTest(subcommand=sub):
                self._assert_help_exits_zero([sub, "--help"])


class ArgParsingTest(unittest.TestCase):
    def test_create_issue_full_flag_surface(self):
        args = jira.build_parser().parse_args([
            "create-issue",
            "--title", "Fix login",
            "--description", "It breaks",
            "--team", "WEB",
            "--labels", "bug,triage-done",
            "--status", "Triage",
            "--estimate", "3",
            "--parent", "WEB-10",
            "--priority", "High",
        ])
        self.assertIs(args.func, jira.cmd_create_issue)
        self.assertEqual(args.team, "WEB")
        self.assertEqual(args.estimate, 3)
        self.assertEqual(args.labels, "bug,triage-done")
        self.assertEqual(args.parent, "WEB-10")
        self.assertEqual(args.priority, "High")

    def test_create_issue_requires_title_and_description(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                jira.build_parser().parse_args(["create-issue", "--title", "t"])
        self.assertEqual(ctx.exception.code, 2)

    def test_comment_requires_issue_and_body(self):
        args = jira.build_parser().parse_args(
            ["comment", "--issue", "PROJ-1", "--body", "hello"]
        )
        self.assertIs(args.func, jira.cmd_comment)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                jira.build_parser().parse_args(["comment", "--body", "hello"])

    def test_attach_pr_parses(self):
        args = jira.build_parser().parse_args([
            "attach-pr", "--issue", "PROJ-1",
            "--url", "https://github.com/org/repo/pull/42",
            "--title", "repo #42",
        ])
        self.assertIs(args.func, jira.cmd_attach_pr)
        self.assertEqual(args.url, "https://github.com/org/repo/pull/42")

    def test_search_issues_parses(self):
        args = jira.build_parser().parse_args(["search-issues", "login endpoint 500"])
        self.assertIs(args.func, jira.cmd_search_issues)
        self.assertEqual(args.query_text, "login endpoint 500")
        self.assertIsNone(args.team)

    def test_get_issue_positional_key(self):
        args = jira.build_parser().parse_args(["get-issue", "PROJ-9"])
        self.assertIs(args.func, jira.cmd_get_issue)
        self.assertEqual(args.key, "PROJ-9")

    def test_update_issue_repeatable_labels(self):
        args = jira.build_parser().parse_args([
            "update-issue", "PROJ-9",
            "--add-label", "spec-done",
            "--add-label", "blocked",
            "--remove-label", "triage-done",
            "--status", "In Progress",
            "--estimate", "5",
        ])
        self.assertIs(args.func, jira.cmd_update_issue)
        self.assertEqual(args.add_label, ["spec-done", "blocked"])
        self.assertEqual(args.remove_label, ["triage-done"])
        self.assertEqual(args.status, "In Progress")
        self.assertEqual(args.estimate, 5)

    def test_list_labels_parses(self):
        args = jira.build_parser().parse_args(["list-labels"])
        self.assertIs(args.func, jira.cmd_list_labels)

    def test_find_user_positional_query(self):
        args = jira.build_parser().parse_args(["find-user", "dev@example.com"])
        self.assertIs(args.func, jira.cmd_find_user)
        self.assertEqual(args.query, "dev@example.com")


class UpdateIssueValidationTest(unittest.TestCase):
    """update-issue validates its flag combinations before any HTTP call."""

    def test_description_flags_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                jira.main([
                    "update-issue", "PROJ-1",
                    "--description", "a",
                    "--append-description", "b",
                ])
        self.assertEqual(ctx.exception.code, 1)

    def test_requires_at_least_one_mutation(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                jira.main(["update-issue", "PROJ-1"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
