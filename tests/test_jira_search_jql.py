#!/usr/bin/env python3
"""Unit tests for the Jira provider's JQL construction (search-issues).

Pure-logic tests for `build_search_jql`; no network, no Jira credentials.
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


jira = _load_script("jira_provider_jql", JIRA_SCRIPT)


class BuildSearchJqlTest(unittest.TestCase):
    def test_keywords_project_and_open_filter(self):
        jql = jira.build_search_jql("login endpoint 500", "PROJ")
        self.assertIn('project = "PROJ"', jql)
        self.assertIn("statusCategory != Done", jql)
        self.assertIn('text ~ "login"', jql)
        self.assertIn('text ~ "endpoint"', jql)
        self.assertIn('text ~ "500"', jql)
        self.assertTrue(jql.endswith("ORDER BY updated DESC"))

    def test_keyword_clauses_are_ored_and_grouped(self):
        jql = jira.build_search_jql("login endpoint", "PROJ")
        self.assertIn('(text ~ "login" OR text ~ "endpoint")', jql)

    def test_stop_words_and_short_tokens_dropped(self):
        jql = jira.build_search_jql("the login for me is ok", None)
        self.assertIn('text ~ "login"', jql)
        self.assertNotIn('"the"', jql)
        self.assertNotIn('"for"', jql)
        self.assertNotIn('"me"', jql)
        self.assertNotIn('"is"', jql)
        self.assertNotIn('"ok"', jql)  # too short

    def test_short_query_falls_back_to_whole_text(self):
        jql = jira.build_search_jql("ui", None)
        self.assertIn('text ~ "ui"', jql)

    def test_no_project_clause_when_project_is_none(self):
        jql = jira.build_search_jql("login", None)
        self.assertNotIn("project =", jql)
        self.assertIn("statusCategory != Done", jql)

    def test_quotes_in_keywords_are_escaped(self):
        jql = jira.build_search_jql('crash "boom" thing', None)
        self.assertIn('text ~ "\\"boom\\""', jql)

    def test_backslashes_are_escaped(self):
        jql = jira.build_search_jql("path c:\\temp today", None)
        self.assertIn('text ~ "c:\\\\temp"', jql)


if __name__ == "__main__":
    unittest.main()
