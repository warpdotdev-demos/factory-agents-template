#!/usr/bin/env python3
"""Regression test for the github provider's resolve-threads delegation.

`scripts/github` must forward `resolve-threads` to `factory-resolve-threads` *without*
injecting the subcommand name as a positional, because `factory-resolve-threads`
is a flat CLI. It must continue to forward the command name for subcommand-based
`factory-pr-meta` operations.

This test loads the provider as a module and monkey-patches `subprocess.run` so
it exercises the argument-forwarding logic without touching the GitHub API.
"""
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_SCRIPT = os.path.join(REPO_ROOT, "scripts", "github")
FACTORY_RESOLVE_THREADS = os.path.join(REPO_ROOT, "scripts", "factory-resolve-threads")
FACTORY_PR_META = os.path.join(REPO_ROOT, "scripts", "factory-pr-meta")


def _load_github_module():
    loader = SourceFileLoader("github_provider", GITHUB_SCRIPT)
    module = loader.load_module()
    return module


def test_resolve_threads_no_subcommand_token():
    """The resolve-threads path must not pass the command name as a positional."""
    github = _load_github_module()
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    old_run = subprocess.run
    subprocess.run = fake_run
    try:
        ret = github.main(
            [
                "resolve-threads",
                "--repo", "warpdotdev/factory-agents",
                "--pr", "94",
                "--thread-ids", "PRRT_kwDOTEGiAs6P-RgI",
                "--rework-cycle", "1",
                "--commit-sha", "deadbeef",
            ]
        )
    finally:
        subprocess.run = old_run

    assert ret == 0, f"unexpected return code: {ret}"
    assert len(calls) == 1, f"expected exactly one subprocess call, got {calls}"
    assert calls[0][0] == FACTORY_RESOLVE_THREADS, (
        f"expected call to factory-resolve-threads, got {calls[0][0]}"
    )
    assert "resolve-threads" not in calls[0], (
        f"command name was forwarded to the flat CLI: {calls[0]}"
    )
    assert calls[0] == [
        FACTORY_RESOLVE_THREADS,
        "--repo", "warpdotdev/factory-agents",
        "--pr", "94",
        "--thread-ids", "PRRT_kwDOTEGiAs6P-RgI",
        "--rework-cycle", "1",
        "--commit-sha", "deadbeef",
    ], f"unexpected forwarded argv: {calls[0]}"


def test_factory_pr_meta_still_receives_subcommand():
    """Subcommand-based factory-pr-meta operations still receive the command name."""
    github = _load_github_module()
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(
            argv, returncode=0, stdout="<!-- factory-agent: {} -->\n", stderr=""
        )

    old_run = subprocess.run
    subprocess.run = fake_run
    try:
        ret = github.main(["build", "--task-id", "TEST-QUALITY-1012"])
    finally:
        subprocess.run = old_run

    assert ret == 0, f"unexpected return code: {ret}"
    assert len(calls) == 1, f"expected exactly one subprocess call, got {calls}"
    assert calls[0][0] == FACTORY_PR_META, f"expected call to factory-pr-meta, got {calls[0][0]}"
    assert calls[0][1] == "build", f"subcommand not forwarded: {calls[0]}"
    assert calls[0] == [
        FACTORY_PR_META,
        "build",
        "--task-id",
        "TEST-QUALITY-1012",
    ], f"unexpected forwarded argv: {calls[0]}"


if __name__ == "__main__":
    test_resolve_threads_no_subcommand_token()
    test_factory_pr_meta_still_receives_subcommand()
    print("PASS: github provider delegation works for both flat and subcommand-based CLIs")
