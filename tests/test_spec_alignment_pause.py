#!/usr/bin/env python3
"""Regression tests for the spec grill-me alignment-pause protocol.

Without this protocol a spec child could silently resolve product/scope forks
and write a spec with no interactive alignment. The protocol requires a hard
grill-me gate (Step 2a) before investigation, structured
`spec_alignment_required` payloads carrying full question objects, and a foreman
that holds the gate and resumes the *existing* child with answers.

This module asserts the real behavioral invariants -- tests that WOULD FAIL if
the bugs were re-introduced:

1.  COORDINATION_FOOTER no-silent-pause invariants:
    - The footer does not tell children to stay silent while paused.
    - The pause path explicitly ends WITHOUT applying any gate label.
    - The footer routes pauses through the foreman (RELAY + structured payload).
2.  Full question-object invariant: question objects (id, text, options,
    tradeoff) appear in the `spec_alignment_required` schema.
3.  Foreman gate-hold invariant: the foreman must not advance any gate label
    while waiting for alignment answers.
4.  Question-id verification invariant: the spec skill requires verifying every
    question id is answered before Step 3; only an explicit proceed waiver
    allows conservative resolution.
5.  Resume-existing-child invariant: the foreman resumes the existing spec child
    with answers paired to the original questions rather than dispatching a
    fresh run.

These are `unittest.TestCase` methods rather than bare module-level functions so
the repo's CI gate -- `python3 -m unittest discover -s tests` -- actually
collects and runs them.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relpath):
    path = os.path.join(REPO_ROOT, relpath)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class SpecAlignmentPauseTests(unittest.TestCase):
    def test_coordination_footer_no_silent_pause(self):
        """Coordination footer must not tell children to stay silent when paused."""
        source = _read("scripts/factory-dispatch")
        self.assertNotIn(
            "stay silent while paused",
            source,
            "scripts/factory-dispatch must NOT say 'stay silent while paused'",
        )
        self.assertIn(
            "human_input_required",
            source,
            "scripts/factory-dispatch must mention 'human_input_required' so "
            "children know to send a structured pause message to the foreman",
        )
        self.assertIn(
            "spec_alignment_required",
            source,
            "scripts/factory-dispatch must mention 'spec_alignment_required' "
            "for the grill-me alignment pause path",
        )
        self.assertNotIn(
            "do not message the foreman yet",
            source,
            "scripts/factory-dispatch must NOT say 'do not message the foreman yet'",
        )

    def test_coordination_footer_pause_does_not_apply_label(self):
        """Paused children must end WITHOUT applying any gate label."""
        source = _read("scripts/factory-dispatch")
        self.assertIn(
            "paused step, just end without applying any label",
            source,
            "scripts/factory-dispatch COORDINATION_FOOTER must say 'paused "
            "step, just end without applying any label' so that a "
            "messaging-unavailable pause does not advance the pipeline without "
            "alignment answers",
        )

    def test_spec_alignment_message_carries_full_question_objects(self):
        """spec_alignment_required message must carry full question objects."""
        spec_skill = _read("spec/.agents/skills/factory-spec/SKILL.md")
        self.assertIn("spec_alignment_required", spec_skill)
        self.assertIn("send_message_to_agent", spec_skill)
        self.assertIn("Step 2a", spec_skill)
        self.assertIn("grill-me", spec_skill)
        for field in ('"id"', '"text"', '"options"', '"tradeoff"'):
            self.assertIn(
                field,
                spec_skill,
                f"factory-spec SKILL.md spec_alignment_required schema must "
                f"include question field {field}",
            )

    def test_foreman_holds_gate_during_alignment(self):
        """Foreman must not advance any gate label while waiting for alignment."""
        foreman_skill = _read("foreman/.agents/skills/factory-foreman/SKILL.md")
        self.assertIn("spec_alignment_required", foreman_skill)
        self.assertIn(
            "Do not advance any gate label",
            foreman_skill,
            "factory-foreman SKILL.md must say 'Do not advance any gate label "
            "while waiting for alignment answers'",
        )

    def test_spec_validates_question_ids_before_step3(self):
        """Spec must verify every question id is answered before Step 3."""
        spec_skill = _read("spec/.agents/skills/factory-spec/SKILL.md")
        self.assertIn("alignment_questions", spec_skill)
        self.assertIn(
            "do NOT proceed to Step 3",
            spec_skill,
            "factory-spec SKILL.md must say 'do NOT proceed to Step 3' for the "
            "case where question ids are unanswered without an explicit "
            "proceed waiver",
        )
        self.assertTrue(
            "proceed waiver" in spec_skill
            or "explicit proceed" in spec_skill
            or 'proceed" or' in spec_skill,
            "factory-spec SKILL.md must describe the explicit "
            "proceed/just-do-your-best waiver",
        )

    def test_foreman_resumes_existing_child_for_alignment_answers(self):
        """Foreman must resume the existing spec child, not dispatch a fresh run."""
        foreman_skill = _read("foreman/.agents/skills/factory-foreman/SKILL.md")
        self.assertIn(
            "Record the child's",
            foreman_skill,
            "factory-foreman SKILL.md must say 'Record the child's agent_id' "
            "so the foreman can reply to the existing spec child run directly",
        )
        self.assertIn(
            "paired with the original",
            foreman_skill,
            "factory-foreman SKILL.md must say answers are 'paired with the "
            "original' alignment_questions list",
        )
        self.assertNotIn(
            "dispatch a fresh spec run",
            foreman_skill,
            "factory-foreman SKILL.md must NOT say 'dispatch a fresh spec run' "
            "for alignment answers",
        )
        self.assertIn("spec_alignment_required", foreman_skill)
        self.assertIn("Do not advance any gate label", foreman_skill)

    def test_foreman_keeps_waiting_on_human_pause(self):
        """Foreman must keep waiting after a pause so a reply can inject live."""
        foreman_skill = _read("foreman/.agents/skills/factory-foreman/SKILL.md")
        self.assertIn(
            "Keep waiting",
            foreman_skill,
            "factory-foreman SKILL.md must tell the foreman to keep waiting "
            "after a RELAY ask",
        )
        self.assertTrue(
            "Do **not** end the foreman turn" in foreman_skill
            or "do **not** end the foreman turn" in foreman_skill,
            "factory-foreman SKILL.md must forbid ending the foreman turn "
            "mid-pause",
        )
        self.assertTrue(
            "your wait simply continues across that pause" in foreman_skill
            or (
                "keep waiting" in foreman_skill.lower()
                and "active" in foreman_skill
            )
        )
        # Still must resume the existing child with paired answers.
        self.assertIn("alignment_answers", foreman_skill)
        self.assertIn("Record the child's", foreman_skill)
        self.assertIn("Do not advance any gate label", foreman_skill)

    def test_foreman_agents_md_keeps_waiting_on_human_pause(self):
        """Track playbook must keep waiting across mid-loop conversation pauses."""
        agents = _read("foreman/AGENTS.md")
        agents_flat = " ".join(agents.split())
        self.assertIn("keep waiting", agents_flat)
        self.assertTrue(
            "do not end the Slack-door turn" in agents
            or "do not end the foreman turn" in agents_flat
        )
        self.assertTrue(
            "still-waiting foreman" in agents or "active" in agents_flat
        )
        self.assertTrue(
            "record the child's `agent_id` and keep waiting" in agents_flat
            or (
                "record the child's" in agents_flat
                and "keep waiting" in agents_flat
            )
        )

    def test_tracker_ops_foreman_keeps_waiting_on_slack_pause(self):
        """Shared wait-for-human pattern must keep the foreman waiting."""
        tracker = " ".join(
            _read(".agents/skills/factory-tracker-ops/SKILL.md").split()
        )
        self.assertTrue("keeps waiting" in tracker or "keep waiting" in tracker)
        self.assertTrue(
            "still-active foreman" in tracker
            or "live foreman" in tracker
            or "still-waiting foreman" in tracker
        )
        progress = " ".join(
            _read(".agents/skills/factory-progress-updates/SKILL.md").split()
        )
        self.assertTrue(
            "keeps waiting" in progress or "keep waiting" in progress
        )
        # finish_task must not be required for mid-loop conversation asks.
        self.assertNotIn("Slack host path (mandatory)", progress)

    def test_spec_agents_md_requires_grill_me_gate(self):
        """Track playbook must require grill-me before investigation."""
        agents = _read("spec/AGENTS.md")
        self.assertIn("grill-me", agents)
        self.assertIn("Step 2a", agents)
        self.assertIn("hard gate", agents)


if __name__ == "__main__":
    unittest.main()
