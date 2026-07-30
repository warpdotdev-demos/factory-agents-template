---
name: manage-review-reassignment
description: Redirect a factory PR's review to a different person when the requester asks for it on the task. Use when a task already has a linked/open fix PR and someone asks to send the review to someone else or names a different reviewer. Reassigns the GitHub reviewer and notifies the task's record without changing workflow ordering.
---

# manage-review-reassignment

Handles the optional "actually, have <someone else> review it" case after a PR is
open. Only relevant once a PR exists for the task; this helper does not decide
or change the workflow lifecycle status. Works for **both tracks** — a
target-repo fix PR or a self-update PR against the template repo (config
`self_repo`) — since it just swaps the GitHub reviewer on whichever PR the task
maps to.

## Step 1 — Identify the requested reviewer

From the newest message, determine who review should go to. They may be named as
a tracker mention, a name, or a GitHub handle. If a GitHub handle was given
directly, use it; otherwise resolve their identity to a handle with
`scripts/factory-resolve-reviewer` (see `factory-github-ops`) — pass their
tracker user id as `--user` and/or their email (read via `factory-tracker-ops`)
as `--email`, plus `--repo <owner/repo>`.

If the script prints nothing (it never guesses) or you otherwise can't
confidently resolve them, ask one concise clarifying question in the task's
conversation channel (tag the requester; deliver it via a
`RELAY:` message to the foreman on either door — you cannot post to the
conversation yourself — per
the door-dependent doctrine and **Who can post where** in
`factory-tracker-ops`) and end your turn.

Sanity-check the request comes from the requester or the current reviewer; if a
random third party tries to reroute, confirm with the requester first.

## Step 2 — Reassign on the PR

Find the task's PR with `scripts/factory-pr-meta find --task-id <key> --repo
<owner/repo>` (see `factory-github-ops`), then swap reviewers:

```bash
gh pr edit <pr> --repo <owner/repo> --add-reviewer <new-handle> --remove-reviewer <old-handle>
```

Remove the previous reviewer so ownership is unambiguous (unless the request was
to *add* a reviewer rather than *replace* — honor what was asked).

## Step 3 — Notify

Notify the task, tagging the **new**
reviewer so they know it's on them — on a Slack-door task as a record comment
via `factory-tracker-ops`; on a Jira-door task in your report to the foreman
(no service-account comment — the foreman's response reaches the ticket via
the Warp app):

> Updated — review reassigned to <@new-reviewer>: <PR URL>.

Leave the lifecycle status unchanged; do not set **In Review** merely because the
reviewer changed. End your turn.
