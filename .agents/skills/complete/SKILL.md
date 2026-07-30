---
name: complete
description: Complete a factory task once its PR has merged. Use when a merge signal arrives for the task's PR (a merge webhook, or a message indicating it merged). Sets the task's lifecycle status to Done and posts a final wrap-up message; on close-without-merge it sets Canceled instead.
---

# complete

The final step for **both tracks** — a PR in the task's target repo (its entry
in config `target_repos`) or a self-update PR against the template repo (config
`self_repo`). End state: the task's lifecycle status is **Done** and a closing
message is posted. It works the same regardless of repo or task source.

## Trigger

This skill runs when the run is resumed with a merge signal — a host merge
webhook/followup, a human noting the merge on the task, or the **foreman**
dispatching this step after a human merges (the factory never merges — a human
does; the foreman only marks the issue Done afterward). Either way, don't trust
the signal blindly — **always re-verify** before acting. If you don't already
know the PR, find it first with
`scripts/factory-pr-meta find --task-id <key> --repo <owner/repo>` (see
`factory-github-ops`), then check its merge state:

```bash
scripts/factory-pr-meta merged --pr <pr> --repo <owner/repo>
```

Proceed only if it's actually merged (the script's `merged` field is `true`, i.e.
`state == MERGED` with `mergedAt` set). If the PR is closed-without-merge
(`state == CLOSED`, `merged` false), do **not** mark Done — that's a
cancellation: set the lifecycle status to **Canceled** via `factory-tracker-ops`,
post a brief note that the PR was closed without merging, and stop.

## Steps

1. Confirm whether the closing message was already posted (idempotent — don't
   double-post; re-read the task's record via `factory-tracker-ops`).
2. Set the task's lifecycle status to **Done** via `factory-tracker-ops` (move
   the ticket to its mapped Done status per config `tracker.status_map`) and
   **clear the pipeline gate label** (e.g. `review-done`) so the closed ticket
   carries no open-step signal. This is idempotent — re-asserting Done is a
   no-op.
3. Post one final message in the task's conversation channel (per the
   door-dependent doctrine in `factory-tracker-ops`; when running as a child,
   deliver it to the foreman as a `RELAY:` message on either door — only
   the foreman can post to the conversation, and a service-account ticket
   comment is never the conversation, per **Who can post where** in
   `factory-tracker-ops`), tagging the requester:

   > 🎉 Merged — <PR URL> is in. Thanks <@requester>! Closing this out.

4. End your turn. This task is done; future messages are unlikely but the
   **foreman** will still route them sanely (a revival is an unlabelled task, so
   it goes back to triage and re-enters the label pipeline at Triage/Todo before
   later work returns to In Progress).
