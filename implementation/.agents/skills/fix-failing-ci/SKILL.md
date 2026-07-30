---
name: fix-failing-ci
description: Fix a failing CI suite on an existing factory PR branch in the task's target repo, re-validate with that repo's validation gate (its validate_command from its target_repos entry), push the fix, and bump the per-PR CI-fix attempt counter (host cap 3). Use when the implementation agent receives a CI-failure follow-up for a factory PR. This is a maintenance re-entry on an open PR, not gated by the pipeline label, and it leaves the issue's gate label unchanged. Stops and reports a human handoff when the attempt cap is reached or the failure is out of scope.
---

# fix-failing-ci

Use this helper for a CI-failure signal on a factory PR (for example, the host's
automated "automated fix attempt <n> of 3" follow-up). Output: a pushed fix on
the **existing** PR branch that turns CI green, or a clean hand-off to a human
when you can't. You never merge. This sub-flow does **not** change the issue's
gate label — the PR stays `impl-done` throughout.

Keep status posts terse per `factory-progress-updates`; read/post the task via
`factory-tracker-ops` and use `factory-github-ops` for PR mechanics. The task's
target repo is the repo recorded on the ticket; read its `validate_command`
from its entry in `target_repos` in `foreman/config.json`.

## Step 0 — Find the PR and check the attempt budget

A CI-fix followup always has an existing ticket: implementation already linked
the PR, kept the ticket **In Progress**, and applied `impl-done`. Confirm it
via `factory-tracker-ops` and keep working that same ticket — its gate label and
status are unchanged here. In the
unlikely event none is found, ensure one per `factory-tracker-ops`
("ensure-ticket") before proceeding.

Locate the PR for this task and read its current CI-fix attempt count:

```bash
scripts/factory-pr-meta find --task-id <key> --repo <task's target repo>
```

It returns `{number,url,state,headRefName,merged,reviewers,ci_fix_attempts}`.
Honor the attempt number the host gives you (it mirrors `ci_fix_attempts`):
- If attempts are **already exhausted** (3 used), do **not** attempt another fix.
  Post one brief note tagging the requester that automated fixes are exhausted
  and a human should take over, leave the PR open / **In Progress**, and end.
- If the PR is closed or merged, there's nothing to fix — end.

## Step 1 — Diagnose the failure

Pull the failing checks and logs for the PR head:

```bash
gh pr checks <pr> --repo <task's target repo>
gh run view <run-id> --repo <task's target repo> --log-failed
```

Identify the **specific** failing step (a failing test, a lint error, a
formatting diff, a build break). Reproduce it locally on the checked-out branch
with the targeted command appropriate to the repo's stack.

Only fix failures that belong to **this PR's change**. If CI is red for an
unrelated, pre-existing, or flaky-infra reason (not caused by this diff), do not
paper over it: post a brief note explaining what failed and why it's out of
scope, tag the requester, and end without consuming the fix as if it were yours.

## Step 2 — Fix and re-validate

Make the **minimal** change that addresses the root cause of the failure — don't
expand scope or refactor. Then re-run the full gate before pushing — the target
repo's validation gate:

```bash
<the target repo's validate_command from its target_repos entry in foreman/config.json>
```

It must pass locally (exact checks depend on the repo's stack — consult the
command's script or the repo's README). If your fix touches behavior, keep
`factory-verification` in force — the regression test must still pass.

## Step 3 — Push and bump the counter

Push to the **same** PR branch (never open a new PR). Then increment the durable
attempt counter exactly once:

```bash
scripts/factory-pr-meta bump-ci-attempt --pr <pr> --repo <task's target repo>
```

Post a terse update on the task (CI fix pushed, attempt n/3) per
`factory-tracker-ops` — a record comment on a Slack-door task; on a Jira-door
task the update travels in your report to the foreman instead (no
service-account comment) — report the outcome to the foreman, then **end your
turn**.
Do not change the issue's pipeline label from this helper.
