#!/usr/bin/env python3
"""Unit tests for the Jira provider's PER-PROJECT settings resolution.

A multi-project Jira site rarely shares one workflow, issue type, or
story-points field, so any `tracker.project_routing` entry may override those
for its own project. These are pure-logic tests over the resolver helpers and
the multi-project JQL clause; no network and no Jira credentials.
"""
import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JIRA_SCRIPT = os.path.join(REPO_ROOT, "scripts", "jira")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jira = _load_script("jira_provider_projects", JIRA_SCRIPT)

ROUTING = {
    "PAY": "payments and billing",  # description-only: no overrides
    "SEARCH": {
        "description": "search and discovery",
        "repos": ["acme/search-service"],
        "status_map": {"In Review": "Code Review", "Canceled": "Won't Do"},
        "story_points_field": "customfield_10032",
        "issue_type": "Bug",
    },
    "OPS": {
        "description": "infrastructure",
        "story_points_field": None,  # estimates disabled for this project
    },
}


class ProjectKeyFromIssueTest(unittest.TestCase):
    def test_prefix_is_the_project(self):
        self.assertEqual(jira.project_key_from_issue("PAY-123"), "PAY")
        self.assertEqual(jira.project_key_from_issue("search-9"), "SEARCH")
        self.assertEqual(jira.project_key_from_issue("MOBILE-APP-4"), "MOBILE-APP")

    def test_blank_returns_none(self):
        self.assertIsNone(jira.project_key_from_issue(""))
        self.assertIsNone(jira.project_key_from_issue(None))


class ProjectOverridesTest(unittest.TestCase):
    def test_object_entry_yields_overrides(self):
        self.assertEqual(
            jira.project_overrides("SEARCH", ROUTING)["issue_type"], "Bug")

    def test_string_entry_has_no_overrides(self):
        self.assertEqual(jira.project_overrides("PAY", ROUTING), {})

    def test_unknown_or_missing_project_has_no_overrides(self):
        self.assertEqual(jira.project_overrides("NOPE", ROUTING), {})
        self.assertEqual(jira.project_overrides(None, ROUTING), {})


class ResolveStatusMapTest(unittest.TestCase):
    SITE = {"Triage": "To Do", "In Review": "In Review", "Canceled": "Done"}

    def test_project_override_layers_over_site_map(self):
        resolved = jira.resolve_status_map("SEARCH", ROUTING, self.SITE)
        self.assertEqual(resolved["In Review"], "Code Review")
        self.assertEqual(resolved["Canceled"], "Won't Do")
        self.assertEqual(resolved["Triage"], "To Do")  # untouched site default

    def test_project_without_override_keeps_site_map(self):
        self.assertEqual(
            jira.resolve_status_map("PAY", ROUTING, self.SITE), self.SITE)

    def test_status_name_resolution_uses_the_project_map(self):
        resolved = jira.resolve_status_map("SEARCH", ROUTING, self.SITE)
        self.assertEqual(
            jira.resolve_status_name("In Review", resolved), "Code Review")
        self.assertEqual(
            jira.resolve_status_name("In Review", self.SITE), "In Review")


class ResolveStoryPointsFieldTest(unittest.TestCase):
    def test_project_override_wins(self):
        self.assertEqual(
            jira.resolve_story_points_field("SEARCH", ROUTING),
            "customfield_10032",
        )

    def test_explicit_null_disables_estimates_for_that_project(self):
        self.assertIsNone(jira.resolve_story_points_field("OPS", ROUTING))

    def test_project_without_override_uses_site_field(self):
        self.assertEqual(
            jira.resolve_story_points_field("PAY", ROUTING),
            jira.STORY_POINTS_FIELD,
        )


class ResolveIssueTypeTest(unittest.TestCase):
    def test_project_override_wins(self):
        self.assertEqual(jira.resolve_issue_type("SEARCH", ROUTING), "Bug")

    def test_falls_back_to_site_issue_type(self):
        self.assertEqual(jira.resolve_issue_type("PAY", ROUTING), jira.ISSUE_TYPE)
        self.assertEqual(jira.resolve_issue_type(None, ROUTING), jira.ISSUE_TYPE)


class SearchScopeTest(unittest.TestCase):
    def test_explicit_teams_win(self):
        self.assertEqual(jira.search_projects(["PAY", "SEARCH"]),
                         ["PAY", "SEARCH"])

    def test_blank_teams_are_ignored(self):
        self.assertEqual(jira.search_projects(["", "  "]),
                         jira.search_projects([]))

    def test_default_scope_is_every_routed_project(self):
        self.assertEqual(jira.search_projects(None), jira.routed_projects())

    def test_multi_project_jql_uses_an_in_clause(self):
        jql = jira.build_search_jql("login 500", ["PAY", "SEARCH"])
        self.assertIn('project in ("PAY", "SEARCH")', jql)
        self.assertIn("statusCategory != Done", jql)

    def test_single_project_list_uses_equality(self):
        jql = jira.build_search_jql("login", ["PAY"])
        self.assertIn('project = "PAY"', jql)
        self.assertNotIn("project in", jql)

    def test_string_project_still_supported(self):
        self.assertIn('project = "PAY"', jira.build_search_jql("login", "PAY"))

    def test_no_projects_means_no_project_clause(self):
        jql = jira.build_search_jql("login", [])
        self.assertNotIn("project", jql)


if __name__ == "__main__":
    unittest.main()
