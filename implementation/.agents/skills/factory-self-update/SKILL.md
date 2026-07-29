---
name: factory-self-update
description: Ship a change to the factory playbook itself (the agents' own skills, AGENTS.md, configs, scripts, or README) as its own PR against the factory template repo (config self_repo). Use when a task asks the agents to change their own behavior/skills rather than requesting a change in the target repo. Posts a pre-confirm summary for approval, validates with scripts/check, opens a ready-for-review PR with the metadata block, and applies extra guardrails to protected scripts.
---

# factory-self-update

The **self-skills track**. You get here when the **foreman** routes a self-skills
task here — triage classified it as a request to change the agents' *own*
skills/behavior/playbook (not a target-repo change) and labelled it `spec-done`
(some self-skills tasks arrive `spec-done` straight from triage with no spec
written, since not every change needs a spec).
The output is a **ready-for-review** PR against the factory template repo
(config `self_repo` in `foreman/config.json`, base `main`) that changes this
repo, validated by `scripts/check` and stamped with the PR↔task metadata block,
with the issue relabeled `impl-done`. You never merge — a human does.

This skill is **re-entrant** and owns an approval gate. Read/post the task via
`factory-tracker-ops`; use `factory-github-ops` for PR mechanics.

## Step 0 — Establish task_id, gate check, and recover state

**Establish the task_id first.** The foreman is the sole ticket creator — you
never create or search for tickets independently. Before any tracker operations.
1. **Provided in the brief.** If the foreman included a `task_id`, adopt it.
2. **Drain inbox (parallel-dispatch path).** If `task_id` was not in the brief,
   call `list_messages_from_agents` and `read_messages_from_agents` on any
   pending messages. The foreman sends `{"task_id":"<key>","task_url":"<url>"}`
   shortly after dispatch. If nothing yet, call `wait_for_events` once (up to
   2 minutes) then drain again.
3. **Error if still none.** If the task_id still has not arrived, post a brief
   error in the conversation and **end your turn**. Do **not** create a ticket.

**Gate (per `factory-tracker-ops` Pipeline labels).** A self-skills task is
labelled `spec-done` like any other implementation work. Once `task_id` is in
hand, read the linked issue's labels.
- Issue carries `spec-done` → proceed.
- Ticket linked but missing `spec-done` → post the canonical wrong-label
  message and **end your turn**.
- No linked ticket → post a brief error asking the requester to provide the
  ticket link in the conversation, tag them, and end your turn.

Self-related tickets are placed by the foreman when it creates the skeleton
ticket, in the project configured as `self_project` in `foreman/config.json`
(see **Project routing** in `factory-tracker-ops`). If the passed ticket appears
misplaced, note it on the ticket; never create a replacement.

Trust conversation history for your own prior actions. Re-derive external state
with these checks.
- Any existing self-update PR for this task.
  `scripts/factory-state --task-id <task_id> --repo <self_repo>` (read
  `self_repo` from `foreman/config.json`).
- Newest task comments (including an approval/change-request reply) via
  `factory-tracker-ops`.
Proceed by local state. No PR and no posted summary → Step 1; summary posted and
awaiting approval → Step 3; approved → Step 2 (implement) then Step 4. The
pre-confirm summary below is this track's own approval gate — separate from the
pipeline label.

## Step 1 — Scope the change and post a pre-confirm summary

Self-edits change the agents' own behavior, so a human approves the **plan**
before you write it. Record the change summary on the ticket for durability, and
**request approval in the task's conversation channel**. On a Slack-triggered
task you cannot post to the Slack thread yourself — only the foreman can — so
send the foreman a `RELAY:` message (agent-to-agent, to your coordination
footer's run id) whose body is the exact Slack-mrkdwn approval ask to post,
and the foreman posts it verbatim and forwards the reply back to you (a ticket
comment never wakes such a run). On a Jira-triggered task post the approval
ask yourself as a Jira comment (per the door-dependent doctrine and **Who can
post where** in `factory-tracker-ops`). Tag the requester and ask them to
reply **there**, writing the ask for a stranger — carry the ticket key, the
ask, and what a valid reply looks like. The substantive full-detail summary
includes these points.
- What behavior/skill changes and why.
- Which files you'll touch (skills, `AGENTS.md`, `config.json`, `scripts/`,
  `README.md`).
- Any protected-script impact (see guardrails below).

Then **end your turn** to await approval. A change-request reply loops back to
revise and re-post; an approval (from the conversation) advances to Step 2.

## Step 2 — Implement on a branch

Work from a fresh clone of the template repo (config `self_repo`) at base
`main`. Create a branch `factory/skills/<short-slug>-<task_id_suffix>` (the
`skills/` segment marks it as a self-edit; the task-id suffix avoids collisions
— see `factory-github-ops`).

Make the **minimal** change that satisfies the approved plan. Follow this repo's
conventions. Keep SKILL.md frontmatter (`name` kebab-case + non-empty
`description`), prefer editing existing skills over adding new ones, and keep
cross-references resolvable (every `` `skill-name` `` you mention must exist).

### Markdown style guardrails

Self-update skills are read by both humans and agents, so keep their prose
colon-free.

- **No colons in prose.** Never use `:` in prose. Prefer periods, commas, or
  split the thought into separate sentences, since a stray colon can be read as
  yaml-breaking by an agent. Code fences and inline code are exempt because
  colons can be required syntax there (this matches the colon-in-prose scan in
  `factory-validate-skills`). This applies to every skill this track authors or
  edits.

### Skill-edit quality guardrails

Skill additions and edits should be, when possible, concise, non-redundant,
and general.

- **Concise.** Minimal words, matching the playbook's style. Omit
  what the reader already knows.
- **Non-redundant.** State a rule once in its canonical place and
  reference it from elsewhere; do not restate across files.
- **General.** Capture the principle that holds across situations, not a
  warning scoped to the incident that prompted the edit.

### Protected-script guardrails

`scripts/` are the deterministic, frozen CLI surface and
`scripts/reviewer_overrides.json` changes reviewer resolution. Treat changes to
any `scripts/` file (especially `factory-resolve-reviewer`,
`factory-pr-meta`, `factory-state`, `tracker`, and `reviewer_overrides.json`) as
higher-risk. Call them out explicitly in the Step 1 summary, keep them minimal
and backwards-compatible, and don't change a script's documented flags/output
shape without saying so. Skills reference these by name, so a rename ripples.

## Step 3 — Validate

Run the repo's validation gate from the root — the target repos'
`validate_command`s do not apply here.

```bash
scripts/check
```

It runs `py_compile` + `--help` smoke tests over every script, then
`factory-validate-skills` (frontmatter lint, `git diff --check`, the dangling
cross-reference scan, and the colon-in-prose scan). It must exit clean
before you open the PR.

## Step 4 — Open the PR and notify

Build the metadata block (`source` is always `factory-agent`) and open a
**ready-for-review** PR (no `--draft`) against the template repo (config
`self_repo`), base `main`.

```bash
scripts/factory-pr-meta build --task-id <key> --task-source <jira|github|prompt> \
  --task-url <url> --oz-run-id <run_id> --repo <self_repo> --pr-url <url>
```

Write a PR body describing the behavior change, including the metadata block
line and a visible **Originating thread** line linking back to where the request
came from (the originating conversation/thread, e.g. the Slack thread) when one
is available (see `factory-github-ops` PR body contents). Verify exactly one
block with `scripts/factory-pr-meta verify`. **Assign the requester as reviewer
at PR-open (non-optional)** via the resolve → assign → fallback flow in
`factory-github-ops` — run `scripts/factory-resolve-reviewer` (pass the
requester's email or user id) then `gh pr edit --add-reviewer <handle>`; if no
handle resolves, ask the requester for their GitHub username **in the task's
conversation channel** (via the foreman `RELAY:` message on a Slack-door task,
or a Jira comment you post yourself — see **Who can post where** in
`factory-tracker-ops`) and assign on resume, never guessing a handle. Complete
by label via `factory-tracker-ops` — record the PR link on the ticket, remove
`spec-done`, add `impl-done`, keep the task **In Progress**, and post the
PR-ready notification tagging the requester with the PR link and what changed.

Then **report completion to the foreman** (per the coordination footer in your
brief) — send it a brief message with the PR link, status **In Progress**, the
change summary, and the applied label (`impl-done`) so it immediately
auto-dispatches code-review without waiting for a poll timeout. If messaging is
unavailable, just end your turn — the `impl-done` label remains the durable
trigger for review on the foreman's next poll.

Merge closes the loop via `complete`. CI failures route to `fix-failing-ci`.
