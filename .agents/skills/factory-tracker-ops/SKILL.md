---
name: factory-tracker-ops
description: Shared reference for how factory agents track and communicate work through the issue tracker — reading a task, creating a ticket, posting comments/updates, setting lifecycle status for the loop, and resolving a requester's identity. All tracker operations go through the `scripts/tracker` CLI (default provider `jira`), falling back to commenting on the PR or replying to the caller only when the tracker is unreachable. Use whenever any factory skill needs to read or update the task's record.
---

# factory-tracker-ops

Shared tracker reference for the factory loop. The agents are **not** tied to
any chat bot — the unit of work is a generic **task** that may originate from
Slack, a Jira ticket, a GitHub issue, or a direct prompt. This skill governs how
to read that task, communicate progress, and track lifecycle. Every other
factory skill defers here for those mechanics. Say "the tracker" and "the
ticket" generically — Jira is the provider, configured under `tracker` in
`foreman/config.json`.

## The task context

Each run is given a task context by whatever invoked it (the host prompt, a
Slack message, a Jira-triggered followup, etc.). The fields you rely on are
these.
- `task_id` — a stable identifier for the work (e.g. a Jira issue key like
  `PROJ-123`, a GitHub issue number, or a generated id for a bare prompt). This
  is the key used to link a PR back to the task (see `factory-github-ops`).
- `task_source` — where it came from, e.g. `jira`, `github`, or `prompt`.
- `task_url` — a link to the task's record, when one exists (the Jira/GitHub
  issue URL for a tracked task, or the originating conversation/thread link for
  a `prompt`-originated task).
- The **originating conversation/thread link** — a link to where the request
  came from (e.g. the Slack thread the request was posted in), when known and
  distinct from `task_url`. For a `prompt`-originated task this is usually
  `task_url` itself. For a tracker-filed task that came from a chat thread, the
  foreman records this link on the ticket and passes it in the child brief, and
  the PR-opening skills surface it in the PR body (see `factory-github-ops` PR
  body contents).
- `requester` — who asked (a tracker user, GitHub user, or the prompting
  human), used for reviewer assignment.

Trust your run's conversation history for your **own** prior actions. Re-read
the task's record only to pick up **externally-mutable** facts that may have
changed since your last turn — new comments, the ticket's current status, or
the linked PR's state (PR facts come from `scripts/factory-state`).

## The record and the conversation (door-dependent)

Factory agents work across **two channels**, and they are not interchangeable.
- **The record — the tracker ticket.** The durable system of record. The
  enriched issue, the story-point estimate, the **spec PR link** (the spec
  itself lives as a committed file in that PR, never as a ticket comment),
  progress, artifacts (PR / review links), lifecycle status, and the pipeline
  gate labels all live here. Keep writing them here.
- **The conversation — the channel that can wake the run.** A task's
  conversation channel is fixed at trigger time (the task's "door") and is
  recorded on the ticket by the foreman.

The door determines where every gating ask goes.
- **Slack-triggered task.** The conversation is the Slack thread the request
  came from. Every ask that must be answered before the run can continue — a
  clarifying question, spec approval, the merge ask, or any `continue` prompt —
  goes **in that Slack thread** (posted by the **foreman**; child agents relay
  through it — see **Who can post where** below), and only a thread reply
  wakes the run. The ticket stays **record-only** — a comment left on the
  ticket never wakes a Slack-originated run. When an agent posts a ticket
  comment on a Slack-door task, include a one-line pointer to the live Slack
  thread so a reader of the ticket knows where the conversation is happening.
- **Jira-triggered task.** The ticket **is** the conversation. Post gating asks
  as **Jira comments** and the requester replies there — the Jira integration
  routes ticket replies to the run, so a comment reply wakes it.

### Who can post where (capability rule)

The two doors have different reach for different agents.
- **Only the foreman can post to the chat thread.** The Slack integration is
  bound to the foreman run alone — child agents (triage, spec, implementation,
  code-review) have **no way** to post into the Slack thread and must never
  attempt to (no hunting for Slack tools, webhooks, or credentials). On a
  Slack-door task, a child delivers a gating ask by **relaying it through the
  foreman** — send the foreman (the run id in your brief's coordination footer)
  an agent-to-agent message with the subject prefixed `RELAY:` and a body
  containing the exact, ready-to-post Slack-mrkdwn text of the ask (written
  for a stranger), then end the child's turn. The foreman posts that text to the
  thread verbatim, **records the child's `agent_id`**, and **keeps waiting** so
  the human's thread reply can inject into the still-active foreman run. The
  foreman then forwards the reply verbatim to the paused child — that forwarded
  message is what resumes the child. Ending the foreman turn mid-pause can stop
  plain thread replies from landing at all, so keep the run active.
- **Any agent can post a Jira comment.** Children carry tracker credentials,
  so on a Jira-door task they post gating asks themselves via
  `scripts/tracker comment` — no relay needed.
- **Fallback.** If agent-to-agent messaging is unavailable on a Slack-door
  task, post the ask as a ticket comment noting the conversation channel was
  unreachable, and end — degraded but never stuck. Never spin trying to reach
  a channel you cannot post to.

A `RELAY:` message is **not** a completion report — the step is still
incomplete and the foreman keeps waiting for it (see the completion report
contract below).

**Write every gate ask for a stranger.** A reply may cold-start a **fresh** run
that re-derives all state from the ticket, so the ask itself must carry the
ticket key, the exact question, and what a valid reply looks like (e.g. "Reply
`approved` to start implementation on PROJ-123, or describe the changes you
want"). Never assume the reader has the current run's context. Record the
durable content the ask refers to (e.g. the spec PR link) on the ticket either
way.

## A ticket is mandatory (ensure-ticket)

Every actionable request runs against a tracker **ticket** — there is **no
ticketless mode**. The **foreman is the sole ticket creator** — downstream
agents (triage, spec, implementation, code-review) adopt the ticket the foreman
provides and never create one independently.

For the **foreman**, ensure a ticket exists before (or immediately after)
dispatching a child, in this order.
1. **Provided / already in the conversation.** If the request carries a ticket
   (an issue key/URL in the task context, the incoming message, or this run's
   history), use it. Read its **description, pipeline label, status, estimate,
   and artifacts** (see **Pipeline labels and completion signals** below) —
   together they are the durable task state.
2. **Follow-up on an in-flight issue or its open PR (canonical adopt
   procedure).** If the request is a follow-up on work already in flight —
   resolving merge conflicts, addressing PR review comments, or any ask to
   improve/continue/change the implementation of an existing issue or its open
   PR — do not create a new ticket for that follow-up. When the request
   references an in-flight issue or its PR (by issue key/URL, PR link/number,
   title, or the originating thread), find and adopt that issue and treat the
   work as continued implementation (rework) on the **same** ticket + PR. To
   find the issue, check any issue key/URL named in the request, then the PR's
   linked issue references, then the PR body for an issue reference, then
   search the tracker by the PR's title / intent. Adopt the clear match. Only
   create a new ticket when no existing issue can be found, and title that
   fallback ticket for the main task, never as a resolve-conflicts,
   address-comments, or follow-up chore. Guard against over-adoption — a
   genuinely new task that merely mentions an unrelated issue still gets its
   own ticket.
3. **Find an existing one (search before creating).** If none was provided,
   look for an existing open ticket
   (`scripts/tracker search-issues "<keywords>"`) **before** creating anything,
   and adopt a clear match rather than minting a duplicate. The search spans
   every routed project by default, so a duplicate someone filed in a different
   team's project still surfaces.
4. **Create a skeleton.** Only when the search above turns up no match, create
   one from the issue template below with no gate label (triage seeds the
   first one) and status **In Progress**. Use the new ticket's key as `task_id`
   from then on.

For **all other agents** (triage, spec, implementation, code-review) the rules
are these.
- **Fast path.** The foreman included `task_id` in the brief. Adopt it.
- **Parallel-dispatch path.** `task_id` was not in the brief — drain your inbox
  (`list_messages_from_agents` / `read_messages_from_agents`). The foreman
  sends `{"task_id":"<key>","task_url":"<url>"}` seconds after dispatch. If
  nothing yet, call `wait_for_events` once (up to 2 minutes) then drain again.
  If still none, post a brief error in the conversation and end.
- **Never create a ticket.** A downstream agent that reaches its step with no
  ticket should error out, not create one.

The **only** requests exempt from the ticket mandate are non-requests — a bare
greeting, banter, or a message with no actionable ask — answered briefly and
never ticketed. Every real ask gets a ticket before any work proceeds.

## Backend — the `scripts/tracker` CLI

All tracker actions go through the `scripts/tracker` CLI, which delegates to a
provider script. The default provider is `jira`. Auth is env-only —
`$JIRA_BASE_URL`, `$JIRA_EMAIL`, and `$JIRA_API_TOKEN` — never stored in
config. Do every read and mutation through these subcommands.
- **Read** the issue with `scripts/tracker get-issue <KEY>`. It returns the
  title, description, status, assignee/creator, **labels** (including the
  pipeline gate labels — see **Pipeline labels** below), and the **estimate**
  (story points) — the externally-mutable state `factory-spec` uses to size a
  spec.
- **Search** for an existing ticket with
  `scripts/tracker search-issues "<keywords>"` (open issues, for
  deduplication / ensure-ticket). With no `--team` it searches **every** routed
  project, so a duplicate filed in another team's project is still found; pass
  `--team <PROJECTKEY>` (repeatable) to scope the search when you already know
  where the work belongs.
- **Create** an issue with
  `scripts/tracker create-issue --title ... --description ... --team "<PROJECTKEY>" [--labels ...] [--status "<state>"] [--estimate <n>]`.
  `--team` is the **Jira project key** — pick it by routing area (see
  **Routing, in two stages** below); omit it only to fall back to the config's
  `tracker.default_project`. The issue type comes from that project's
  `issue_type` override when it has one, else config `tracker.issue_type`.
  Pass `--status` to set the initial lifecycle state on creation (e.g.
  `Triage` for triage intake, `In Progress` for a foreman skeleton); omit it to
  use the project default. Pass `--estimate` for the story-points value (XS=1,
  S=2, M=3, L=5, XL=8) — the provider writes it to that project's story-points
  field (its own `story_points_field` override when it has one, else config
  `tracker.story_points_field`).
- **Comment** with `scripts/tracker comment --issue <KEY> --body ...` to post
  clarifying questions (Jira-door tasks), progress, or PR notifications. This
  is how **every agent except triage** records updates on the issue (triage
  appends to the description instead — see **Where triage records updates**
  below). Write comment bodies in plain markdown — the tracker CLI converts
  markdown to Jira's ADF format.
- **Attach a PR** to the ticket with
  `scripts/tracker attach-pr --issue <KEY> --url <github-pr-url> --title "PR #<N>: <short description>"`.
  It creates a **Jira remote link** on the issue. Use this whenever a PR is
  opened for the task, in addition to posting a comment with the link.
- **Set or append the description** with
  `scripts/tracker update-issue <KEY> [--append-description ...] [--description ...]`
  to record information in the issue **body**. `--append-description` adds
  text after the existing body (separated by a blank line); `--description`
  replaces it wholesale (the two are mutually exclusive). **Triage** uses
  `--append-description` to record its updates (reproduction proof, progress,
  the enriched template) instead of commenting; other agents keep commenting.
- **Set the actual status, estimate, and/or labels** with
  `scripts/tracker update-issue <KEY> [--status "<state>"] [--estimate <n>] [--add-label <name> ...] [--remove-label <name> ...]`
  to track the lifecycle (see **Lifecycle status**) and record step completion
  (see **Pipeline labels and completion signals**). It mutates the ticket's
  **real properties** in one update — moving the workflow state, setting the
  story-points estimate, and adding/removing gate labels (label edits are a
  delta, so existing labels like the categorization label are preserved).
  Example triage completion update —
  `scripts/tracker update-issue PROJ-123 --status "Todo" --estimate 3 --add-label triage-done`.
  Example implementation completion update —
  `scripts/tracker update-issue PROJ-123 --status "In Progress" --add-label impl-done --remove-label "spec-done"`.
- **List labels** with `scripts/tracker list-labels` when you need to see what
  label names exist in the workspace.
- **Resolve a person's Jira accountId** with
  `scripts/tracker find-user "<email or display name>"` — it prints matches
  with `accountId`, `name`, `email`, and a ready-to-use `mention` token
  (`[~accountid:<id>]`). Use it when you need to @-mention someone whose
  accountId isn't already on the ticket or in
  `scripts/reviewer_overrides.json`.
- **Read the requester/assignee's email** (from `get-issue`) so
  `factory-resolve-reviewer` can map them to a GitHub handle (pass it as
  `--email`).

Whenever you "update the ticket's status", set an estimate, or complete work by
label, change the ticket's **actual properties** (workflow status, estimate,
and labels), not just a comment. A comment may *accompany* the change to
explain it, but the status/estimate/label change must land on the ticket so the
durable signals stay accurate. Do **not** settle for only a comment when a real
status/estimate/label change is what the step requires.

Only if the tracker is **entirely** unreachable (the Jira auth env vars
`$JIRA_BASE_URL` / `$JIRA_EMAIL` / `$JIRA_API_TOKEN` are missing) may you
proceed without a ticket as a last resort — say so explicitly, keep
communicating on the PR / by direct reply, and still stamp the PR↔task metadata
block (`factory-github-ops`) so the work is traceable. This is an exception,
not the normal path.

## Lifecycle status

The loop tracks a single lifecycle state for the task, mirrored to the ticket's
**status**. The factory uses six canonical state names — **Triage, Todo, In
Progress, In Review, Done, Canceled** — and the config map
`tracker.status_map` in `foreman/config.json` maps each one to the customer's
real Jira status name, with any per-project `status_map` override applied on top
for that project's own tickets. Pass the factory state name to
`scripts/tracker update-issue <KEY> --status "<state>"`; the provider resolves
the issue's project from its key and applies the mapped Jira status. This
status is one of the durable completion signals the foreman verifies alongside
the gate label and produced artifacts. The states are these.
- **Triage** — triage owns the ticket and is clarifying/reproducing/sizing it.
- **Todo** — triage finished. The issue is enriched and has a story-point
  estimate.
- **In Progress** — spec or implementation owns the ticket, or implementation
  has opened/linked a PR and recorded `impl-done`.
- **In Review** — code-review has reviewed the linked PR and recorded its
  accepted/rejected verdict; a human merge or implementation rework may follow.
- **Done** — the PR merged; loop closed (see `complete`).
- **Canceled** — the work was aborted (user request, infeasible, or no real
  work to do).

Set exactly one state at a time, advancing **Triage → Todo → In Progress → In
Review → Done**, with **Canceled** as the abort branch and review rework moving
back to **In Progress**. A follow-up that revives a Done/Canceled task goes
back to **Triage** or **In Progress** depending on whether it needs new triage.
Updating the status means changing this property on the ticket, **not** posting
a comment that names the intended state.

## Pipeline labels and completion signals

Factory steps record completion through **tracker labels**, not by calling
sibling steps directly. The labels are the gate contract, but they are **not
the only durable signal**. Foreman verifies the label plus the step-specific
ticket status and artifact signals before it treats a step as complete. Each
label is **descriptive of completed work** rather than an instruction to run a
particular next step, and exactly **one** pipeline label should be active at a
time.

The five labels are these.
- `triage-done` — triage completed and recorded that the issue is non-obvious
  or complex enough to require a written spec artifact.
- `spec-done` — the issue has enough implementation direction to be built. An
  approved spec exists, triage recorded an obvious/simple fix direction, or
  the issue is a self-skills change. (When config `spec_approval_required` is
  `false`, the spec step applies `spec-done` as soon as the spec is committed —
  no approval pause; see `factory-spec`.)
- `impl-done` — implementation completed and one or more PRs are open and
  linked.
- `review-done` — review accepted the PR; merge remains a human action.
- `blocked` — review requested changes; implementation work is not accepted
  yet.

Only the **foreman** interprets these labels to choose workflow ordering,
auto-advance behavior, rework caps, or any other cross-step decision. Step
agents should treat labels as local preconditions and local completion outputs.

Spec work still reads the **estimate** to size its spec (XS/S → a concise
implementation spec; M/L/XL → a full product + tech spec). All spec work stays
under **In Progress**. Implementation completion also stays **In Progress**
with the PR linked; code-review records **In Review** when it posts the
verdict. Do not introduce a separate spec-review status.

### Step completion signals
Each step owns only its local completion signals.
- **Triage complete** — the issue is enriched, the status is **Todo**, and the
  story-points estimate is set (XS=1, S=2, M=3, L=5, XL=8). Triage also applies
  either `triage-done` or `spec-done`.
- **Spec complete** — the spec PR link is recorded on the ticket, approval came
  from the conversation when config `spec_approval_required` is `true` (no
  approval is expected when it is `false`), and `spec-done` is applied with
  `triage-done` removed. The spec itself lives as a committed file in that
  draft PR (under `agents/specs/`), never as a ticket comment. Spec reports the
  spec PR link + the applied label to the foreman.
- **Implementation complete** — one or more PR links are recorded on the
  ticket, the status is **In Progress**, and implementation applies
  `impl-done` while removing `spec-done`/`blocked`.
- **Review complete** — the reviewed PR link and review link/verdict are
  recorded on the ticket, the status is **In Review**, and code-review applies
  `review-done` for an accepted PR or `blocked` for changes requested while
  removing `impl-done`.

Only the **foreman** combines these signals with labels to decide what is
complete and what happens next. Step agents record their own signals and report
them; they do not interpret sibling signals or workflow ordering.

### Label update mechanics
Each step removes labels that no longer describe the current completed state
and adds the label for the work it just completed — by editing the ticket's
**actual labels**
(`scripts/tracker update-issue <KEY> --add-label "<completed-state>" --remove-label "<stale-state>"`),
never by just commenting the intended transition. Preserve non-pipeline labels
such as categorization labels.

Step-local completion labels are these.
- triage applies `triage-done` or `spec-done`.
- spec applies `spec-done`.
- implementation applies `impl-done`.
- review applies `review-done` when accepted or `blocked` when changes are
  requested.

### Completion report contract
A step is not "done" until it has (1) edited the ticket's labels to record its
completed state, (2) set its required ticket status/estimate signal when it
owns one, and (3) **recorded the artifacts it produced on the ticket** (for
example, the enriched issue + story-point estimate from triage, the spec PR
link from spec, the PR link, or the review link). **Every PR-opening step (spec
and implementation) must both attach the PR to the ticket AND comment the PR
link, before applying the gate label.**
1. `scripts/tracker attach-pr --issue <KEY> --url <pr-url> --title "PR #<N>: <short description>"` — creates a Jira remote link on the issue.
2. `scripts/tracker comment --issue <KEY> --body "PR: <pr-url>"` — records the link in the comment feed.

The review step must similarly post the review link as a comment. After all
required signals are present, the step also sends the **foreman** a brief
completion message — the result, artifact links, status/estimate signal, and
applied label — per the coordination footer in its dispatch brief.

Do not send the foreman a **completion** message before the step is actually
complete. A within-step human pause, such as a clarifying question or spec
approval request, is not a completion — on a Slack-door task deliver that ask
to the foreman as a `RELAY:` message instead (see **Who can post where**
above), which the foreman posts to the thread without treating the step as
done. If agent-to-agent messaging is unavailable, finish the local label and
artifact updates and end; the durable ticket state remains the source of
truth.

### The gating rule
On entry, after gathering state, read the linked ticket's labels. Each step has
a required label documented in its own playbook.
- Ticket linked **and** it carries the agent's required label → **proceed**.
- Ticket linked but **lacks** it → post the wrong-label message (below), then
  **end the turn**; do no work.
- **No** ticket linked → drain your inbox for the task_id the foreman sends
  (per **A ticket is mandatory** above). If none arrives, post a brief error
  and end. Do **not** create a ticket.

Foreman is **exempt** (it is the sole ticket creator and the pipeline source);
triage is **exempt** from the label gate (it is the pipeline's source and
applies the first gate label itself).

If multiple gate labels are present, the issue is inconsistent. A step agent
should proceed only if its own required label is present; otherwise post the
wrong-label message and end. Note the anomaly on the issue. Jira labels are
created on first use, so a "missing" gate label in the workspace is not a
blocker — applying it creates it.

### Canonical wrong-label message
When an issue reaches a step agent without that agent's gate label, post
exactly this (filled in) and end the turn.

> Skipping — <ticket key> isn't gated for *<this stage>* yet. It carries
> `<current label, or "no pipeline label">`, not `<required label>`. Re-apply
> the correct label for this step.

## The foreman creates tickets; triage enriches them

The **foreman** is the only factory agent that creates a ticket. When it
receives a new request with no existing ticket, it creates a skeleton issue via
`scripts/tracker create-issue` — a concise title, a brief description from the
request, and status **In Progress** (no gate label; triage seeds the first
one). The foreman also records the task's **door** (the Slack thread link for a
Slack-triggered task, or a note that the ticket itself is the conversation for
a Jira-triggered one) in the ticket description. The ticket is then passed to
the appropriate child agent via `task_id` in the brief, or via
`send_message_to_agent` in the parallel-dispatch path.

**Triage enriches** the foreman's skeleton into a full,
**ready-for-the-next-step** record using the template below — it never creates
a second issue.

### Issue template (target-repo track)
- **Title** — a concise one-line summary of the defect; the topic is fully
  contained by the issue title, so there is no separate Topic section.
- **Description** — what's wrong and where (affected endpoint/component/flow),
  expected vs. actual behavior, and any attached evidence; link the original
  source (`task_url`) when there is one, and the originating conversation
  thread when the door is Slack. Also record the chosen target repo as a
  `Target repo: <org/repo>` line (per `factory-triage`) so downstream steps
  read it instead of re-deciding.
- **Replication Steps** — concrete steps to reproduce, refined to the
  *confirmed* repro once you have one (or the documented non-repro /
  env-mismatch note). For a trivial/obvious fix that skips reproduction, record
  a brief "trivial — no repro needed" note instead of steps.
- **Acceptance Criteria** — the observable conditions that define "fixed".
- **Testing** — how the fix is verified. The deterministic check per
  `factory-verification` — a regression test per the target repo's
  `test_guidance` that fails before / passes after, plus that repo's
  validation gate (its `validate_command`), both read from that repo's settings
  via `scripts/factory-config repo --repo <org/repo>`.
- **Solution** — the fix direction. For an obvious fix, the concrete change;
  for a non-obvious one, a proposed direction/hypothesis the spec will
  elaborate.

Beyond the body sections, triage stamps the issue with this metadata.
- **Estimate** — set the story-points estimate before completing triage (XS=1,
  S=2, M=3, L=5, XL=8). If the story-points field cannot be set, append the
  estimate to the issue body and note the field failure.
- **Priority** — set an explicit priority (default **Medium**; raise for P0 /
  hot-path / data-integrity defects, lower for cosmetic ones).
- **Categorization label** — a type label distinct from the pipeline gate label
  (e.g. `bug` for a defect). It classifies *what* the issue is; the gate label
  records the latest completed pipeline state.

If the priority or categorization label can't be set (missing in the workspace,
or the CLI can't set it), proceed anyway and note on the issue that the field
couldn't be set.

### Routing, in two stages (project, then repo)
Routing happens in **two stages**, and the first narrows the second. Read both
from the resolver `scripts/factory-config` instead of parsing
`foreman/config.json` by hand — at many projects and many repos, hand-reading
the whole config is how a ticket ends up pointed at another team's repo.
1. **The Jira project.** Every factory issue is created in the project whose
   area the change falls under. `scripts/factory-config projects` lists each
   routed project key with the area it owns (config `tracker.project_routing`)
   plus the `tracker.default_project` fallback. Pick the key whose area matches
   the change and pass it via `--team`. An **existing** ticket has already
   answered this stage, because its key prefix *is* the project — `PAY-123`
   lives in `PAY`.
2. **The target repo, within that project's repos.** A project normally owns
   only some of the repos, so a ticket's candidates are just that project's
   subset. `scripts/factory-config repos --issue <ticket key>` (or
   `--key <PROJECTKEY>`) prints exactly those candidates with their
   descriptions and that project's `default_repo` fallback. Which candidate
   fits is `factory-triage`'s judgment; the narrowing is not, so never widen it
   back out to every configured repo. A project that declares no subset leaves
   every target repo a candidate, which is the single-project shape.

**Per-project tracker settings.** Multi-project sites rarely share one
workflow. A project entry may override `status_map`, `story_points_field`,
`issue_type`, and `spec_approval_required`, and `scripts/tracker` applies the
right project's override automatically for every read and write (it derives the
project from `--team`, or from the issue key on `get-issue` / `update-issue`).
So pass factory state names as usual, and when you need to know the effective
values, read them with `scripts/factory-config project --issue <ticket key>`.
Never assume one project's status names hold for another.

**Self-related issues (special case).** Self-skills changes — changes to the
agents' own playbook/skills — and any ticket created by the foreman or
`factory-self-update` for a self-skills task go to the project key configured
as `self_project` in `foreman/config.json`. Read that value from config and
pass it via `--team` when creating a self-related ticket.

This is the one place to change where factory issues land — update the routing
table or `self_project` there to repoint issues. Choosing the routing-area
project is the **agent's** judgment; the CLI is a thin mechanic and does no
routing. When creating an issue, pass `--team` for the matching project key
(omit it only to fall back to `tracker.default_project`).

Triage populates the template **progressively** (see `factory-triage`) — fill
the Title (refine if the skeleton title needs clarity), Description, and
Replication Steps when taking ownership (Step 2a), then enrich Acceptance
Criteria, Testing, and Solution after reproduction (Step 3) and the complexity
call (Step 4), so the issue is complete before triage records its completion
label.

Set the issue status to **Triage** once triage takes ownership, then move it to
**Todo** when triage completes with a story-point estimate and completion
label. This structured template applies to the target-repo track; self-related
tickets use the `self_project` placement above.

## Communicating well

Defer to `factory-progress-updates` for **what** to post and how terse to be.
This skill is the **how**. The default channel for recording an update on the
ticket is a **comment** (`scripts/tracker comment`); fall back to a PR comment
or a direct reply when the tracker is unreachable. Tag the requester on
substantive updates (clarifying questions, specs, PR-ready notifications).

**Tag people with real mentions, formatted by platform.** Slack mention syntax
(`<@USERID>`) is not valid in Jira — it renders as literal text and notifies
no one. In Jira body content (comments via `scripts/tracker comment` /
`update-comment`, descriptions via `update-issue`), tag a person by writing
the mention token `[~accountid:<their-accountId>]` in the markdown — the
tracker CLI converts it to a real ADF mention that renders as a clickable
@-mention and notifies them. Resolve the accountId in this order — (1) the
ticket's own people — `scripts/tracker get-issue` returns the
reporter/requester and assignee with their `accountId`; (2) the identity map
`scripts/reviewer_overrides.json` — `slack_users` entries associate a Slack
user ID with the same person's `email`, `jira_account_id`, and `github`
handle; (3) `scripts/tracker find-user "<email or display name>"` (a shared
email is the join key across Slack, Jira, and GitHub). Fall back to the plain
display name only when no accountId can be resolved. Issue **titles** cannot
render mentions — use the display name there. Never embed a raw Slack mention
token in Jira content; reserve Slack mention syntax exclusively for messages
posted to Slack threads (Slack mrkdwn).

Never post probe/test chatter to a customer-visible record — write the real
update once.

Format by door, per the formatting policy in `factory-progress-updates`.
- **Slack-door messages** (posted to the Slack thread) — author in Slack
  mrkdwn. Slack renders its own mrkdwn, not CommonMark, so CommonMark bold,
  headers, or `[text](url)` links render as literal punctuation.
- **Jira-door comments** (posted via `scripts/tracker comment`) — write plain
  markdown; the tracker CLI converts it to ADF.

### Where triage records updates
**Triage is the exception.** Instead of adding comments, the triage agent
records its updates by **appending to the issue's description**
(`scripts/tracker update-issue <KEY> --append-description ...`) — its findings,
reproduction proof, progress notes, and the enriched 6-section template all
live in the issue **body**. Every **other** agent (spec, implementation,
code-review, foreman) continues to record updates as **comments**. This keeps
the triage deliverable consolidated in one place (the description) while later
discussion stays in the comment thread. Lifecycle status, estimate, and
pipeline gate labels are still set on the ticket's real properties via
`update-issue` regardless of agent.

## The "wait for a human" pattern

You cannot block. When a step needs human input that gates its own progress (a
clarifying question, spec approval, merge ask, or any `continue`), do this.
1. **Deliver the ask to the task's conversation channel, by role and door**
   (see **Who can post where** above).
   - **Foreman** — post it directly in the Slack thread on a Slack-door task,
     or as a Jira comment on a Jira-door task. If the ask came from a child's
     `RELAY:` / structured pause, also **record that child's `agent_id`** so
     the later reply can resume the same child.
   - **Child agent, Slack door** — you cannot post to the thread; send the
     foreman a `RELAY:` message carrying the exact Slack-mrkdwn text to post,
     and the foreman posts it verbatim, records your `agent_id`, and **keeps
     waiting** (the child ends its own turn after the relay).
   - **Child agent, Jira door** — post the Jira comment yourself via
     `scripts/tracker comment`.
   Whoever authors it, tag the relevant person, tell them to reply there, and
   write the ask **for a stranger** — include the ticket key, the exact
   question, and what a valid reply looks like. On a Slack-door task, never
   depend on a ticket comment to resume the workflow; record the durable content
   the ask refers to (e.g. the spec PR link) on the ticket, but put the
   request-for-a-reply itself in the thread (via the relay when you are a child).
2. **Child ends; foreman keeps waiting on Slack mid-loop pauses.** After a child
   relays or posts a gating ask, the **child** ends its turn. The **foreman** on
   a Slack-door mid-loop pause (alignment / clarifying / approval) should **keep
   its wait loop running** so the thread reply injects into the live run and can
   be forwarded to the paused child. Do not end the foreman turn just to deliver
   that ask — doing so can stop plain thread replies from landing at all. A ticket
   comment wakes the run on the Jira door; on the Slack door the thread reply
   should land on the still-waiting foreman, which forwards it to the paused
   child when the ask was a child's relayed ask. Either way, re-derive external
   state from the task record + `scripts/factory-state` as needed.
Don't busy-poll in a spin loop — use the normal drain-then-wait pattern.
