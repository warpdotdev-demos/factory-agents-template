#!/usr/bin/env python3
"""Unit tests for the Jira provider's status mechanics.

Covers the pure logic only -- factory-state -> Jira-status mapping
(`resolve_status_name`) and transition selection (`select_transition`) -- with
no network and no Jira credentials.
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


jira = _load_script("jira_provider_status", JIRA_SCRIPT)

STATUS_MAP = {
    "Triage": "To Do",
    "Todo": "To Do",
    "In Progress": "In Progress",
    "In Review": "In Review",
    "Done": "Done",
    "Canceled": "Won't Do",
}


class ResolveStatusNameTest(unittest.TestCase):
    def test_mapped_factory_state(self):
        self.assertEqual(jira.resolve_status_name("Triage", STATUS_MAP), "To Do")
        self.assertEqual(jira.resolve_status_name("Canceled", STATUS_MAP), "Won't Do")

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(jira.resolve_status_name("in progress", STATUS_MAP), "In Progress")
        self.assertEqual(jira.resolve_status_name("TODO", STATUS_MAP), "To Do")
        self.assertEqual(jira.resolve_status_name("  In Review  ", STATUS_MAP), "In Review")

    def test_unmapped_name_passes_through(self):
        self.assertEqual(
            jira.resolve_status_name("Blocked Upstream", STATUS_MAP),
            "Blocked Upstream",
        )

    def test_empty_map_passes_through(self):
        self.assertEqual(jira.resolve_status_name("Triage", {}), "Triage")

    def test_default_map_comes_from_foreman_config(self):
        # With no explicit map, the module falls back to STATUS_MAP loaded from
        # foreman/config.json (tracker.status_map). Verify the plumbing without
        # coupling to the config's specific values.
        self.assertIsInstance(jira.STATUS_MAP, dict)
        expected = jira.STATUS_MAP.get("Triage", "Triage")
        self.assertEqual(jira.resolve_status_name("Triage"), expected)


class SelectTransitionTest(unittest.TestCase):
    TRANSITIONS = [
        {"id": "11", "name": "Start Progress", "to": {"name": "In Progress"}},
        {"id": "21", "name": "Send to review", "to": {"name": "In Review"}},
        {"id": "31", "name": "Close", "to": {"name": "Done"}},
    ]

    def test_matches_on_target_status_name(self):
        chosen = jira.select_transition(self.TRANSITIONS, "In Review")
        self.assertEqual(chosen["id"], "21")

    def test_match_is_case_insensitive(self):
        chosen = jira.select_transition(self.TRANSITIONS, "in review")
        self.assertEqual(chosen["id"], "21")
        chosen = jira.select_transition(self.TRANSITIONS, "DONE")
        self.assertEqual(chosen["id"], "31")

    def test_matches_destination_not_transition_name(self):
        # "Start Progress" is the transition's *name*; selection must key off
        # the destination status ("In Progress"), not the transition label.
        self.assertIsNone(jira.select_transition(self.TRANSITIONS, "Start Progress"))
        chosen = jira.select_transition(self.TRANSITIONS, "In Progress")
        self.assertEqual(chosen["id"], "11")

    def test_no_match_returns_none(self):
        self.assertIsNone(jira.select_transition(self.TRANSITIONS, "Backlog"))

    def test_empty_or_missing_transitions(self):
        self.assertIsNone(jira.select_transition([], "Done"))
        self.assertIsNone(jira.select_transition(None, "Done"))

    def test_malformed_transition_entries_are_skipped(self):
        transitions = [{"id": "1"}, {"id": "2", "to": {}},
                       {"id": "3", "to": {"name": "Done"}}]
        chosen = jira.select_transition(transitions, "Done")
        self.assertEqual(chosen["id"], "3")


if __name__ == "__main__":
    unittest.main()
