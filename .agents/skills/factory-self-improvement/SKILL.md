---
name: factory-self-improvement
description: Shared reference for when a user, mid-conversation, asks a factory agent to change its own behaviour. Classify the ask as conversation-only (apply just for this run, no skill edit) versus structural/durable (a going-forward change), and for a structural change dispatch a background sub-agent that runs factory-self-update to edit the skills and reports back discreetly in the same conversation, so the current task is never interrupted. Use whenever any factory agent is asked mid-run to change how it acts.
---

# factory-self-improvement

Shared reference for handling a **behaviour-change request that arrives mid-run**.
Any factory agent — foreman, triage, spec, implementation, or code-review — may,
while working a task, be asked by a user to change how it acts. This skill governs
that moment. It does **not** change the pipeline; it decides whether the ask is a
one-off for the current run or a durable change to the agents' own playbook, and
routes a durable change to `factory-self-update` through a **background**
sub-agent so the main task is never interrupted. Defer to `factory-tracker-ops`
for posting mechanics and to `factory-progress-updates` for how terse to be.

## Relationship to factory-self-update

`factory-self-improvement` and `factory-self-update` are distinct, complementary
layers and are **not** consolidated. This skill is the **mid-conversation
trigger** — it decides whether a behaviour-change ask is conversation-only (apply
for this run, no edit) or structural/durable, and for a structural change it
dispatches a **background** sub-agent so the current task is not interrupted. It
does **not** edit skills, open PRs, or run `scripts/check` itself.
`factory-self-update` is the **implementation-track execution flow** that a
self-skills task runs end to end — scope the change, post a pre-confirm summary
for approval, edit the skills, validate with `scripts/check`, and open the
ready-for-review PR against the template repo (config `self_repo`).
`factory-self-improvement` **delegates to** `factory-self-update` for the actual
edit (Step 2 → Step 3), and a top-level standalone "improve yourself" request
skips this skill entirely and enters `factory-self-update` through the normal
triage → implement loop.

## When this applies

Read this skill the moment a user, mid-conversation, asks you to **change a
behaviour** — how you triage, how you write a PR, how you report, a default you
apply, anything about how the agents act. It does **not** apply to an ordinary
task request (a bug to fix, a feature to build) — that stays on the normal loop.
It applies only when the *subject of the change is the agents' own behaviour*.

## Step 1 — Classify conversation-only vs structural

Decide which of two kinds of change the user wants.
- **Conversation-only** — the user wants different behaviour for **just this run
  or task**. Phrasings like "for this one", "just here", "in this case", or a
  correction scoped to the work in front of you. Apply it **immediately** for the
  current conversation and keep going. Do **not** edit any skill and do **not**
  dispatch a sub-agent — a durable edit would over-apply a one-off preference.
- **Structural / durable** — the user wants a change to how the agents behave
  **going forward**. Phrasings like "from now on", "always", "going forward",
  "update your process so", "in future runs", or any ask that only makes sense as
  a permanent change. This needs a durable edit to the factory playbook,
  which is `factory-self-update`'s job (Step 2).
- **When you cannot tell**, ask **one** brief question in the task's
  conversation channel — whether this is just for the current task or a
  permanent change going forward — tag the requester, and, per the
  door-dependent doctrine in `factory-tracker-ops`, wait for their reply there
  (the Slack thread for a Slack-door task; the foreman's conversation,
  mirrored to the ticket by the Warp app, for a Jira-door
  task). When you are a child agent, deliver the question
  via a `RELAY:` message to the foreman on either door (see **Who can post
  where** in
  `factory-tracker-ops`) — you cannot post to the conversation yourself. Do
  not
  guess when the two readings diverge materially.

## Step 2 — For a structural change, dispatch a background sub-agent

A durable self-edit must **not** derail the task the user is actually waiting on,
so you do **not** stop and edit the skills inline. Instead spin up a **separate
sub-agent** that runs `factory-self-update`, and continue your current work while
it runs in the background. How you spin it up depends on who you are.
- **If you are the foreman** (the sole ticket creator and dispatcher), treat the
  request as a new self-skills task and run it through your normal
  `factory-foreman` routing. Create the self-skills ticket in the project
  configured as `self_project` in `foreman/config.json` (see **Project
  routing** in `factory-tracker-ops`), dispatch it as a background child run via
  the `run_agents` tool (its payload resolved by `scripts/factory-dispatch`), and
  then return to driving the main task.
- **If you are a downstream agent** (triage, spec, implementation, or
  code-review), you are **not** the ticket creator or dispatcher, so hand the
  request up. Send your parent foreman a message (`send_message_to_agent` to the
  `parent_run_id` from your brief's coordination footer) that quotes the
  behaviour change and asks it to run the self-skills flow, then continue your
  current step uninterrupted. If you have no parent foreman, record the request on
  the task so a foreman can pick it up later, and carry on.

Dispatch **one** self-update sub-agent per distinct request — if the same durable
change was already handed off earlier in this run, do not dispatch it again.

## Step 3 — The sub-agent updates the skills and reports back discreetly

The dispatched sub-agent runs the full `factory-self-update` flow — its own
pre-confirm summary, `scripts/check`, and a **ready-for-review PR** against the
template repo (config `self_repo`). Because it is a separate run, the user's
current task keeps moving while the self-update waits on its own approval and
review.

When the self-update finishes (its PR is open), it reports back **in the same
originating conversation** in a **low-noise** way, per `factory-progress-updates`
— a single terse line plus the PR link as a compact named hyperlink, formatted
for the task's door, not a running narration. The goal is that the user learns
the durable change was captured without being pulled off the task at hand.
