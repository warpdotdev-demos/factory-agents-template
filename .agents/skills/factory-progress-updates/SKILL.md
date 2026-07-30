---
name: factory-progress-updates
description: Shared policy for how the factory agents report progress on a task — keep a single, continuously-updated status comment for multi-step work on Slack-door tasks (on Jira-door tasks progress flows through the foreman's conversation, mirrored by the Warp app, with no service-account comments) and keep plain status updates terse, while leaving spec and PR-notification messages at full detail. Use whenever you create or change a todo list, or are about to post a progress update, from any factory skill.
---

# factory-progress-updates

Shared reference for **how** the factory loop communicates progress on a task. It
does not route or decide what work to do — the foreman owns workflow decisions,
and each step owns its local work. This skill governs two things every other
factory skill defers to: a **live status comment** and **terse status updates**.
The posting mechanics live in `factory-tracker-ops` (door-scoped: a ticket
comment on a Slack-door task, the foreman's conversation on a Jira-door task,
else a PR comment or a direct reply).

These two policies work together: the live status comment carries the
moment-to-moment "what am I doing now" signal, so individual progress posts can
stay short instead of narrating each step.

## Live status comment (Slack-door tasks)

For multi-step work on a **Slack-door** task, mirror your own todo list into
**one** status update on the
task's record and keep refreshing that same place rather than posting a stream of
new "update" messages. On a **Jira-door** task there is **no** live status
comment at all — service-account comments are prohibited there (see the door
doctrine and **Service-account comments never solicit replies** in
`factory-tracker-ops`); the Warp app already mirrors the foreman's
conversation onto the ticket, so progress reaches the ticket through the
foreman's step results and children report to the foreman instead.

- **Keep it current.** Whenever you create or change your todo list, update the
  status with the full current list (done / in-progress / pending). When the task
  is a tracked Slack-door ticket, post the initial status comment once via
  `scripts/tracker comment --issue <KEY> --body ...` and **capture the `id` field
  from the returned JSON**. Then refresh that same comment in-place on every state
  change via
  `scripts/tracker update-comment --issue <KEY> --comment-id <id> --body <updated-body>`
  so it stays a live reflection of progress. Do **not** post a new comment for
  each state change — update the one you first posted. In the no-tracker fallback,
  a brief progress note on the PR is enough. **Triage is the exception:** it keeps
  this live status in the issue **description** (via `update-issue
  --append-description`), not a comment — see **Where triage records updates** in
  `factory-tracker-ops`. Every other agent uses a comment (Slack door only).
- **Refresh on every state change.** Update it each time an item starts or
  completes, so it stays a live reflection of progress.
- **Do not use GFM checkboxes in ticket comments or descriptions.** The syntax
  `- [x]`
  and `- [ ]` is **not** supported by the ADF converter — both become regular
  bullet items with literal `[x]` / `[ ]` text, not interactive task items.
  Use Unicode symbols instead — ✅ for completed steps and ⬜ for pending steps —
  or plain-text status labels (`done:` / `in progress:` / `pending:`). This
  applies to everything written through the tracker CLI (record comments,
  descriptions); Slack-door thread
  messages are unaffected since Slack renders its own checkbox syntax.
- **Proportionality.** Skip the live status for trivial one-shot work (a single
  clarifying question, an abort, a one-line answer) — it's for multi-step work
  where live progress is useful.
- **Keep titles human.** It's customer-facing: use short, outcome-oriented item
  titles (e.g. "Reproduce the bug", "Open PR"), not internal tool jargon. Do
  **not** put comment IDs or run internals in it.

The status comment reflects progress; it does **not** replace the lifecycle
status (Triage / Todo / In Progress / In Review / Done / Canceled — see
`factory-tracker-ops`) or the substantive notifications below.

## Terse status updates

Messages that **merely report progress** should be short — one or two lines.
Don't narrate every step or restate context the task already has; the live status
comment already conveys step-by-step state. Prefer updating it over posting a new
"still working on X" message at all.

Messages that **carry substance keep their full detail** — do not shorten:
- a spec approval ask with the **spec PR link** (`factory-spec`),
- a pre-confirm summary of a self-skills change (`factory-self-update`),
- a PR-ready / "fix is up" notification with the PR link and what changed,
- a clarifying question (include everything you need to proceed),
- an abort/cancellation explanation.

Any of these that **gates progress and needs a reply** (a spec/plan for approval,
a clarifying question, a `continue`) must be delivered **in the task's
conversation channel** — the Slack thread for a Slack-triggered task, or the
foreman's own conversation response for a Jira-triggered task (mirrored to the
ticket by the Warp app; never a service-account comment, whose replies are not
routed to the factory) — per the door-dependent doctrine in
`factory-tracker-ops`. **Child agents cannot post to the conversation on
either door** — they deliver the ask to the foreman as a `RELAY:` message and
the foreman posts it verbatim (see **Who can post where** in
`factory-tracker-ops`). Never leave a gating ask only on the
ticket as a service-account comment: it does not wake the run on either door.
Write every such ask **for a
stranger** — include the ticket key, the exact question, and what a valid reply
looks like, since the reply may cold-start a fresh run.

## Action-first — lead with the ask

Any message that **gates progress on a human reply** must put the ask itself —
the blocking question or approval request, plus the requester tag — **first**,
above any status, detail, or links.

## Record artifacts at step completion
When a step completes, record the **artifacts it produced** on the ticket — the
enriched issue + estimate + Todo status (triage), the spec PR link
(spec), the PR link + In Progress status (implementation), the PR/review link +
In Review status (review) — so the ticket
is a complete record of what each step created. These same artifact/status links
go in the step's completion message to the foreman (see `factory-tracker-ops`),
which is how the foreman reports the step and decides what to do next.

**The PR must be attached to the ticket — and on a Slack-door task also linked
in a comment.** When
implementation (or spec) opens a PR, before applying the gate label:
1. `scripts/tracker attach-pr --issue <KEY> --url <pr-url> --title "PR #<N>: <short description>"` — a Jira remote link on the issue (both doors).
2. **Slack door only:** `scripts/tracker comment --issue <KEY> --body "PR: <pr-url>"` — the link in the comment feed. On a Jira-door task skip the comment — the foreman's step result (mirrored by the Warp app) carries the PR link.

The remote link gives the issue a first-class PR
connection in the tracker; the Slack-door comment makes it discoverable in the
activity thread.

**Post every link as a compact named hyperlink** per the formatting policy
below — never a bare URL.

When in doubt about whether a message is "just an update" or "substance," it's
substance — err toward keeping the detail. The goal is less noise, not less
information where it matters.

## Format outgoing messages for the door

The task's door (see `factory-tracker-ops`) determines the syntax of every
outgoing message — progress updates, clarifying questions, spec-approval asks,
PR-ready notifications, step results, and wrong-label messages.

**Slack-door messages are Slack mrkdwn.** Slack renders its own mrkdwn — not
CommonMark — so author every message posted to a Slack thread in mrkdwn, and
avoid the CommonMark forms Slack renders literally:

- *Bold* with single asterisks — `*bold*`, never `**bold**` (Slack shows
  `**bold**` as the literal text `**bold**`).
- _Italic_ with underscores — `_italic_`. Single asterisks are bold in Slack,
  not italic.
- Links as `<url|label>` — never `[label](url)`. Use short, descriptive labels
  (for example `<https://yourcompany.atlassian.net/browse/PROJ-123|PROJ-123>`,
  `<https://github.com/.../pull/42|PR #42>`,
  `<https://oz.warp.dev/runs/...|Oz run>`), never a bare URL.
- No `#` or `##` markdown headers — Slack renders them as literal `#`. Use a
  `*bold*` line as a pseudo-heading when a section break is needed.
- Bullets with `•` or `-`, never `*` (single asterisks bold the text).
- Inline code with backticks and fenced code blocks for multi-line code — both
  render the same in Slack mrkdwn.
- No markdown tables — Slack renders the pipe syntax literally. Use a list or
  stacked `*bold*` lines instead.

**Jira-door messages are plain markdown.** The foreman's Jira-door
conversation responses (mirrored to the ticket by the Warp app), the `RELAY:`
bodies children send it on a Jira-door task, and any Slack-door record
comment/description written via the tracker CLI are all authored in ordinary
markdown — standard bold, `[label](url)` links, lists — and the tracker CLI
converts markdown to Jira's ADF format when it posts (single newlines render
as real line breaks). Do not use Slack mrkdwn syntax
(`<url|label>` links or `*bold*`-as-bold) in any Jira-bound content, and never
end such a message by asking the reader to reply to a service-account comment
(see **Service-account comments never solicit replies** in
`factory-tracker-ops`).

This is a runtime-composition rule for the **text agents send**, not for skill
documentation prose. The SKILL.md files themselves stay standard markdown —
they are `.md` files read as markdown, not posted to a chat surface. Only the
quoted outgoing-message templates agents copy verbatim need converting to the
door's syntax (see `factory-tracker-ops` and `factory-spec`).

## Foreman dispatch notifications (one-liners only)

The foreman has three mandatory notification moments — each is exactly one line,
then stop:

1. **On dispatch:** post the step name and the child's Oz run link immediately
   after the `run_agents` dispatch returns `launched` (the run link is built from
   `factory-dispatch`'s `run_link_template` + the returned `agent_id`). Before
   entering the wait. Every dispatch, including auto-advance hops. Post it in
   the Slack thread on a Slack-door task, or as your own conversation response
   on a Jira-door task (the Warp app mirrors it — never a service-account
   comment).
2. **On user follow-up during a wait (status check only):** if the user is
   asking for a progress update and the answer requires tool calls, post one
   line with the current step + child Oz run link before those tool calls.
   Skip this for direct requests (scope change, providing info) — just act on
   them. Always link to the child's run, not the foreman's own run.
3. **On first poll timeout (~3 min):** notify that the step is taking longer
   than expected, include the Oz run link.

Keep all three to one line. Do not add context, backstory, or next-step
explanations — those come in the full step-result post (Step 4) once the child
completes. The point is that the requester always knows something is in flight
and has a link, even if they don't ask.
