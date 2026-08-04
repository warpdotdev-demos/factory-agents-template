#!/usr/bin/env python3
"""Regression tests for factory-dispatch run_agents payload shape.

Cloud runs were failing the first child dispatch when the payload attached a
repo-qualified skills[] entry (org/repo:path/to/SKILL.md), then succeeding after
the foreman retried with an absolute filesystem path. The pattern that dispatches
first-try is:

1. omit skills[] from the run_agents payload entirely
2. put absolute checkout paths for AGENTS.md + entry SKILL.md in base_prompt

These tests lock that contract so first-try dispatch keeps working.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISPATCH = os.path.join(REPO_ROOT, "scripts", "factory-dispatch")

TRACKS = {
    "triage": "factory-triage",
    "spec": "factory-spec",
    "implementation": "factory-implement",
    "code-review": "factory-review",
}

# Short pointer only — not the full AGENTS.md body.
BASE_PROMPT_MAX_LEN = 600
# runner_id is emitted only when a repo/project/env var resolves one.
ALLOWED_REMOTE_KEYS = {"computer_use_enabled", "environment_id", "runner_id"}
PARENT_RUN_ID = "019fc823-8544-7b06-95d6-14ee251ecb15"


def _dispatch(track: str, *, cwd: str | None = None, env: dict | None = None) -> dict:
    cmd = [
        sys.executable,
        DISPATCH,
        "--track",
        track,
        "--prompt",
        "test brief",
        "--parent-run-id",
        PARENT_RUN_ID,
    ]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    # Isolate from ambient factory env that could change the payload shape.
    for key in list(merged):
        if key.startswith("FACTORY_FOREMAN_") and key not in (env or {}):
            merged.pop(key, None)
    proc = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"factory-dispatch failed for {track!r} (cwd={cwd!r}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


class FactoryDispatchPayloadTests(unittest.TestCase):
    def test_payload_omits_skills_and_uses_absolute_paths(self):
        for track, skill_name in TRACKS.items():
            with self.subTest(track=track):
                payload = _dispatch(track)
                run_agents = payload["run_agents"]
                skills = run_agents.get("skills")
                self.assertFalse(
                    skills,
                    f"run_agents.skills should be absent/empty for {track!r}, got {skills!r}",
                )

                base_prompt = run_agents["base_prompt"]
                self.assertIn(
                    skill_name,
                    base_prompt,
                    f"base_prompt for {track!r} should name {skill_name!r}",
                )
                self.assertLessEqual(
                    len(base_prompt),
                    BASE_PROMPT_MAX_LEN,
                    f"base_prompt for {track!r} is too long ({len(base_prompt)}); "
                    "it must be a short absolute-path pointer, not the full AGENTS.md",
                )

                agents_md = os.path.join(REPO_ROOT, track, "AGENTS.md")
                if os.path.isfile(agents_md):
                    with open(agents_md, encoding="utf-8") as fh:
                        body = fh.read()
                    if len(body) > 120:
                        mid = body[len(body) // 2 : len(body) // 2 + 60]
                        self.assertNotIn(
                            mid,
                            base_prompt,
                            f"base_prompt for {track!r} appears to inline AGENTS.md body",
                        )

                paths = re.findall(r"`([^`]+)`", base_prompt)
                self.assertTrue(paths, f"base_prompt for {track!r} has no backticked paths")
                for emitted in paths:
                    self.assertTrue(
                        os.path.isabs(emitted),
                        f"base_prompt for {track!r} emits non-absolute path {emitted!r}",
                    )
                    self.assertTrue(
                        os.path.isfile(emitted),
                        f"base_prompt for {track!r} path does not exist: {emitted!r}",
                    )

                # Still expose the derived skill for debugging, but children must
                # not need a skills[] attachment to start.
                self.assertIn(skill_name, payload["skill"])
                self.assertNotIn("skills", json.dumps(run_agents.get("skills")))

    def test_paths_resolve_from_non_repo_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            for track, skill_name in TRACKS.items():
                with self.subTest(track=track):
                    payload = _dispatch(track, cwd=tmp)
                    base_prompt = payload["run_agents"]["base_prompt"]
                    self.assertIn(skill_name, base_prompt)
                    for emitted in re.findall(r"`([^`]+)`", base_prompt):
                        self.assertTrue(os.path.isabs(emitted))
                        self.assertTrue(os.path.isfile(emitted))

    def test_remote_only_contains_expected_keys(self):
        payload = _dispatch("triage")
        remote = payload["run_agents"]["remote"]
        self.assertTrue(set(remote) <= ALLOWED_REMOTE_KEYS)
        self.assertNotIn("runner_id", remote)
        self.assertTrue(remote.get("computer_use_enabled"))

        payload = _dispatch(
            "triage",
            env={"FACTORY_FOREMAN_ENV": "env-from-env"},
        )
        remote = payload["run_agents"]["remote"]
        self.assertEqual(remote.get("environment_id"), "env-from-env")
        self.assertTrue(set(remote) <= ALLOWED_REMOTE_KEYS)

    def test_remote_carries_resolved_runner(self):
        payload = _dispatch(
            "triage",
            env={"FACTORY_FOREMAN_RUNNER": "runner-from-env"},
        )
        remote = payload["run_agents"]["remote"]
        self.assertEqual(remote.get("runner_id"), "runner-from-env")
        self.assertTrue(set(remote) <= ALLOWED_REMOTE_KEYS)


if __name__ == "__main__":
    unittest.main()
