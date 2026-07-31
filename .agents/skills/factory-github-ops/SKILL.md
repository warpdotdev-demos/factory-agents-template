---
name: factory-github-ops
description: Shared reference for the factory agents' GitHub mechanics across both tracks — PR conventions for the task's target repo (its entry in config target_repos in foreman/config.json) and the factory template repo itself (config self_repo), branch naming, draft vs ready, assigning and replacing reviewers, finding the PR associated with a task, detecting merged state, resolving a task requester to a GitHub handle, and resolving PR review threads after a rework. PR operations go through the provider-agnostic scripts/forge seam (default provider github, which delegates to scripts/github and the underlying scripts/factory-pr-meta and scripts/factory-resolve-threads). Use whenever you need to interact with GitHub or map a requester to a reviewer from any factory skill.
---

# factory-github-ops

Low-level GitHub reference for the factory loop. Other factory skills defer here
for PR conventions and identity mapping.

## PR operations seam (`scripts/forge`)

All PR mechanics go through the provider-agnostic `scripts/forge` CLI. It
accepts a `--provider` flag (default `github`) and a `FACTORY_FORGE_PROVIDER`
environment variable, then delegates all subcommands to the configured provider
script. The default `github` provider calls `scripts/github`, which wraps the
existing `scripts/factory-pr-meta` and `scripts/factory-resolve-threads` without
changing them. The `mock-code-forge` provider is an in-memory mock used only by
the eval harness (`scripts/factory-eval`). Use `forge` as the canonical entry
point for any PR operation; the underlying scripts remain valid direct calls for
existing code.

## Repo and conventions

Which repo you target depends on the **track** (`factory-triage` decides):

- **Target-repo track** (bug reports / features → `factory-spec` +
  `factory-implement`):
  - **Repo:** the task's target repo — the repo triage chose and recorded on
    the ticket (its `Target repo` line). Triage picked it from the repos the
    ticket's Jira project owns, so treat it as decided; resolve that repo's
    settings with `scripts/factory-config repo --repo <org/repo>` instead of
    re-reading `foreman/config.json`.
  - **Base branch:** the chosen repo's `base_branch` (from the same resolver
    call — repos differ, e.g. `main` in one and `master` in another).
  - **Branch naming:** `factory/<short-slug>`. **This branch/PR is shared across
    the spec and implementation phases:** `factory-spec` creates the branch,
    commits the spec as one markdown file under `agents/specs/` named
    `<ticket-key>: <very brief title>.md`, and opens the **draft PR** with a
    spec-marked title (e.g. `Spec: <title>`); `factory-implement` then **checks
    out that same branch**, adds the code to the same PR, and **updates the PR
    title and description** to describe the shipped change (it opens its own PR
    only when the spec was skipped). GitHub is the source of truth for the
    committed spec.
  - **Validation:** full — the target repo's validation gate (its
    `validate_command`) plus a regression test per its `test_guidance` (both
    from the repo's `target_repos` entry), per `factory-verification`. Exact
    tooling (linter, test runner, build) depends on the target repo's stack —
    consult the validate command's script or the repo's README. A headless or
    purely-backend change needs **no** UI /
    `computer_use` step; a **user-facing** change (regardless of which repo it
    targets) additionally requires computer-use screenshot proof attached to
    the task and the PR (see `factory-verification`).
- **Self-skills track** (skill changes → `factory-self-update`):
  - **Repo:** the factory template repo itself (config `self_repo` in
    `foreman/config.json` — the agents' own playbook).
  - **Base branch:** `main`.
  - **Branch naming:** `factory/skills/<short-slug>-<task_id_suffix>` (the
    `skills/` segment distinguishes self-edits from target-repo PRs; the task-id
    suffix keeps repeated requests like "update triage" from colliding).
  - **Validation:** `scripts/check` (script `py_compile` + `--help` smoke test +
    `factory-validate-skills` markdown/cross-reference lint) — the target
    repos' `validate_command`s, regression tests, and verification steps do not
    apply to this repo.

Shared for both tracks:

- Work from a fresh checkout/clone in the Oz environment.
- **Tooling:** `gh`. (A human operator may use other tools personally, but the
  autonomous agent should use `gh` for predictable, non-interactive PRs.)
- **Draft vs ready:** open PRs **ready for review** by default — `gh pr create`
  without `--draft`, or `gh pr ready <pr>` to promote an existing draft. The
  **one exception** is the spec phase's PR (`factory-spec`), which stays a
  **draft** while it awaits spec approval (marking it ready would break the
  approval gate); the implementation phase marks it ready (`gh pr ready`) when
  it adds the code on the spec→implement handoff. (When config
  `spec_approval_required` is `false` there is no approval gate, but the spec
  PR still stays a draft until implementation adds the code.) One logical
  change per PR.
- **Co-author trailer** on commits/PR body: `Co-Authored-By: Oz <oz-agent@warp.dev>`.

## Find the PR for a task

The canonical PR↔task link is a hidden metadata block stamped in the PR body at
open time by whichever skill opens the PR (`factory-spec` when it opens the spec
draft PR, `factory-implement` for target-repo changes with no prior spec PR,
`factory-self-update` for skill changes). It is identical for all tracks —
`source` is always `"factory-agent"` — so everything below is repo-agnostic. On
the spec path the spec phase stamps the block once and implementation reuses the
same PR, so `factory-pr-meta find` resolves the same PR for both phases. The
block is a single HTML comment on its own line containing compact JSON:
```text
<!-- factory-agent: {"source":"factory-agent","task_id":"<key>","task_source":"<jira|github|prompt>","task_url":"<url>","oz_run_id":"<run_id>","repo":"<owner/repo>","pr_url":"<url>"} -->
```

`source` is always `"factory-agent"` and `task_id` is the only **required**
field — it is the stable identifier for the work (a tracker issue key, a GitHub
issue number, or a generated id for a bare prompt). `task_source` and
`task_url` describe where the task lives; `oz_run_id`, `repo`, and `pr_url` are
optional hints. `ci_fix_attempts` is an optional integer recording how many
automated CI fixes have been pushed; it defaults to absent/0 and is managed via
`bump-ci-attempt` (below), not hand-edited. Treat this block as the source of
truth for the PR↔task mapping.

Don't hand-assemble or grep the block — `scripts/factory-pr-meta` owns its exact
shape:

- **Build** the block when opening/updating a PR (prints exactly one block line;
  optional keys are emitted only when passed):
  ```bash
  scripts/factory-pr-meta build --task-id <key> [--task-source <s>] \
    [--task-url <url>] [--oz-run-id <run_id>] \
    [--repo <owner/repo>] [--pr-url <url>]
  ```
- **Find** the task's PR when you don't already know it. It reads PR bodies in
  the named repo and matches `task_id`, so always disambiguate by
  **(task_id, repo)**. A task has at most one PR per repo. Pass the task's
  chosen/recorded target repo (or `self_repo` for the self-skills track):
  ```bash
  scripts/factory-pr-meta find --task-id <key> --repo <owner/repo>
  ```
  When the target repo is genuinely unknown, do **not** sweep every configured
  repo — that is one API round trip per repo and gets slow and rate-limited at
  scale. Narrow first to the repos the ticket's project owns
  (`scripts/factory-config repos --issue <key>`) and iterate only those, or let
  `scripts/factory-state --task-id <key> --issue <key>` do the scoped probe for
  you.
  Prints `{number,url,state,headRefName,merged,reviewers,ci_fix_attempts}` for
  the match, or nothing when the task has no PR in that repo.
- **Verify** exactly one valid block is present before trusting a PR — a missing
  or duplicated block breaks the task↔PR mapping:
  ```bash
  scripts/factory-pr-meta verify --pr <pr> --repo <owner/repo>
  ```
  Exits 0 only when exactly one valid block exists; nonzero (with the count on
  stderr) otherwise.

## PR body contents

Every factory PR body has two parts — a **visible description** for human
reviewers, and the hidden `factory-agent` metadata block above (the task↔PR
mapping). The visible description is a clean, current-state summary of the PR's
net effect (see the PR-opening skills), and it **must include an Originating
thread line** linking back to where the request came from.

**Originating thread line.** Include a visible line near the top of the body
that links back to the originating conversation/thread — the channel the task
originated from (the Slack thread the request was posted in is the common case;
for a Jira-triggered task it is the ticket itself). This is platform-agnostic
and is included **when an origin link is available**. Choose, in order of
preference, one of the following.
1. The **originating conversation/thread link** when one is known (e.g. the
   Slack thread URL the request came from). For a `prompt`-originated task this
   is typically the `task_url`. For a tracker-filed task it is the originating
   conversation link captured on the ticket/brief (distinct from the issue URL)
   when the request came from a chat thread.
2. Otherwise the **task record URL** (`task_url` — the Jira/GitHub issue),
   which still links a reviewer back to where the work is tracked.
3. Omit the line only when no origin link exists at all (e.g. a bare prompt with
   no associated thread or issue).

Place it as a standalone line so a reviewer can jump back to the request
context, e.g. `Originating thread: <link>`. It complements (does not replace)
the hidden metadata block, which already carries `task_url` for the task↔PR
mapping.

A minimal PR body template (the visible part, with the metadata block appended)
looks like this.

```text
## Summary
<what this PR changes and why>

## Verification
<test name + the validate command, or skip category + rationale for testing-exempt changes>

Originating thread: <originating conversation/thread link, e.g. the Slack thread>
<!-- factory-agent: {"source":"factory-agent","task_id":"...","task_url":"..."} -->
```

## Detect merged state

```bash
scripts/factory-pr-meta merged --pr <pr> --repo <owner/repo>
```

Prints `{state,mergedAt,merged}`: `merged` is true only when `state == MERGED`
with `mergedAt` set. `CLOSED` without `mergedAt` means closed-unmerged — do not
treat that as merged (see `complete`).

## Track CI auto-fix attempts

The automated CI-fix loop is capped per PR (3 attempts). The count is stored
durably in the metadata block's `ci_fix_attempts` field. After you push a CI fix
(`fix-failing-ci`), increment it exactly once:

```bash
scripts/factory-pr-meta bump-ci-attempt --pr <pr> --repo <owner/repo>
```

This read-modify-writes the PR body's single metadata block, preserving every
other key, and prints `{ci_fix_attempts}` with the new value. Don't hand-edit
the field; `find` surfaces the current value when you need to read it.

## Read ALL PR feedback surfaces

GitHub exposes **three distinct, non-overlapping comment surfaces** on a PR.
Reading only the first two and reporting "no inline threads" is the common
failure — file-level comments live on the third. **Query all three** before
concluding what feedback exists.

1. **Conversation comments** — the PR timeline, general comments not tied to a
   line of code.
   ```bash
   gh pr view <n> --repo <owner>/<repo> --comments
   gh api repos/<owner>/<repo>/issues/<n>/comments
   ```
2. **Top-level PR reviews** — the approve / request-changes review summaries
   (one per review event), each with a body but no inline comments.
   ```bash
   gh api repos/<owner>/<repo>/pulls/<n>/reviews
   ```
3. **Inline / file-level review comments** — comments tied to a specific
   `path` + line of the diff. This is the surface agents most often miss.
   ```bash
   gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate
   ```
   Each object carries `path`, `line` / `original_line`, `body`, `user.login`,
   `id`, and `in_reply_to_id` (non-null marks a reply within a thread, not a
   new top-level comment). For thread / resolution state, use the GraphQL
   `pullRequest.reviewThreads` query (see "Resolve PR review threads").

`gh pr view --comments` surfaces conversation comments (surface 1) and
top-level review summaries (surface 2) but **omits inline review comments**
(surface 3) — so do **not** treat an empty `gh pr view --comments` as "no
review feedback". Always also query `pulls/<n>/comments`.

**Reply per inline thread** with the review comment id (not the thread id)
```bash
gh api repos/<owner>/<repo>/pulls/<n>/comments/<review-comment-id>/replies \
  -f body="<reply text>"
```

**Confirm the count before concluding "no comments"** — `--paginate` emits one
JSON array per page, so count items, not pages.
```bash
gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate --jq '.[].id' | wc -l
```

## Resolve PR review threads

After a rework pushes commits that address review comments, resolve the specific
review threads whose feedback was actually addressed before re-applying
`impl-done` so the PR shows a clean review state (per `factory-implement` Step
0 and Step 7). Unrelated or unaddressed threads are left alone — do **not**
resolve threads the rework did not touch.

```bash
REWORK_SHA=$(git rev-parse HEAD)
scripts/factory-resolve-threads --repo <owner/repo> --pr <number> \\
  --thread-ids <id1,id2,...> --rework-cycle <N> --commit-sha "$REWORK_SHA"
```

- `--thread-ids` — comma-separated list of **GraphQL review thread node IDs**
  (each node's `id` field from the GraphQL `reviewThreads` query, e.g.
  `PRRT_kwDOTEGiAs6NuFxg`). Pass only the IDs of threads whose review feedback
  the rework concretely addressed. To list all thread node IDs on the PR before
  starting rework, run:
  ```bash
  gh api graphql -f query='query($o:String!,$r:String!,$p:Int!){repository(owner:$o,name:$r){pullRequest(number:$p){reviewThreads(first:100){nodes{id isResolved}}}}}' \\
    -f o=<owner> -f r=<repo> -F p=<number>
  ```
- `--rework-cycle` — the current `review_rework_attempts` count as returned by
  `scripts/factory-pr-meta bump-review-attempt`.
- `--commit-sha` — the SHA of the rework commit (HEAD after pushing). The script
  builds a GitHub commit URL and posts a reply
  `[addressed on rework # N](https://github.com/<owner>/<repo>/commit/<sha>)` on
  each thread before resolving it, so reviewers can jump directly to the
  addressing commit. Use `--commit-url` instead if you already have the full URL
  (both flags are accepted; `--commit-url` takes precedence). One of the two
  is required.

Prints `{"resolved": N}` where N is the count of threads resolved. Exits nonzero
on any API failure or if a given thread ID is not found on the PR.

## Post a review to GitHub (markdown body + inline comments)

Post the review as a **single GitHub API call** — body as plain markdown read from a file, inline comments from a `jq`-constructed JSON file. **Never post the body as a JSON object.** Write paragraph text as single continuous lines — do not manually wrap at 80 characters. GitHub PR review renders every newline within a paragraph as a visible line break.

```bash
# 1. Write the review body as plain markdown (never as JSON)
cat > /tmp/review_body.md << 'EOF'
## Overview
...
## Verdict
Found: X critical, Y important, Z suggestions

**Approve** / **Request changes**
EOF

# 2. Build the inline-comments JSON file using jq
#    jq encodes all strings safely — no shell escaping needed
#    Each object: {"path":"rel/path","line":42,"side":"RIGHT","body":"..."}
#    Multi-line ranges: also include start_line and start_side (both required together)
jq -n '[
  {"path": "path/to/file", "line": 42, "side": "RIGHT", "body": "⚠️ [IMPORTANT] ..."}
]' > /tmp/review_comments.json
# No inline comments: jq -n '[]' > /tmp/review_comments.json

# 3. Fetch head SHA and set the review event
HEAD_SHA=$(gh pr view <pr> --repo <owner/repo> --json headRefOid -q .headRefOid)
if [ "$VERDICT" = "APPROVE" ]; then EVENT="APPROVE"; else EVENT="REQUEST_CHANGES"; fi

# 4. POST body + inline comments in one request
#    --rawfile reads the markdown file as a literal string (no JSON escaping)
#    --slurpfile reads the JSON array file (wraps it; $comments[0] is the array)
jq -n \
  --rawfile body /tmp/review_body.md \
  --slurpfile comments /tmp/review_comments.json \
  --arg event "$EVENT" \
  --arg sha "$HEAD_SHA" \
  '{"commit_id":$sha,"body":$body,"event":$event,"comments":$comments[0]}' | \
  gh api repos/<owner/repo>/pulls/<pr>/reviews --method POST --input -
```

**If the review workflow produced a `review.json`**, extract its fields into
the same two files, then run steps 3–4 above:

```bash
jq -r '.body' review.json > /tmp/review_body.md
jq '.comments // []' review.json > /tmp/review_comments.json
VERDICT=$(jq -r '.verdict' review.json)
if [ "$VERDICT" = "APPROVE" ]; then EVENT="APPROVE"; else EVENT="REQUEST_CHANGES"; fi
```

## Assign / replace reviewers

```bash
gh pr edit <pr> --repo <owner/repo> --add-reviewer <handle>
gh pr edit <pr> --repo <owner/repo> --add-reviewer <new> --remove-reviewer <old>   # reassign
```

## Resolve a task requester → GitHub handle

The requester's GitHub handle is needed to assign them as reviewer. Resolve it
with `scripts/factory-resolve-reviewer`, which checks a hand-curated override
map first, then maps a public **email** → GitHub handle (user search), with an
optional org-membership cross-check when a repo is given:

```bash
scripts/factory-resolve-reviewer [--user <id>] [--email <email>] [--repo <owner/repo>]
```

It is task-system agnostic — it does not talk to any chat platform. For a
tracker-filed task, read the requester/assignee's email via the
`scripts/tracker` CLI (`get-issue`, see `factory-tracker-ops`) and pass it as
`--email`; pass their tracker user id as `--user` to hit the override map. It
prints a GitHub handle on stdout, or **nothing** (exit 0) when it can't resolve
one confidently — it **never guesses**, since assigning the wrong reviewer is
worse than asking.

**Manual overrides.** Email-based resolution fails for anyone without a public
email. When you hit such a user (and learn their handle, e.g. by asking on the
task), record it in `scripts/reviewer_overrides.json` so future requests resolve
automatically. The map is keyed by a stable user id and consulted **before** the
email chain; each value is a bare handle string or an object with a `github` key
(plus an optional `label` comment). Editing this file changes
`factory-resolve-reviewer`'s behavior, so it carries the same protected-script
review bar as the resolver itself (see `factory-self-update`).

**Fallback — ask the requester.** When the script prints an empty result, ask
**in the task's conversation channel** (the Slack thread for a Slack-door task,
or a Jira comment for a Jira-door task, per the door-dependent doctrine in
`factory-tracker-ops`; a child agent cannot post to the Slack thread itself —
it delivers the ask to the foreman as a `RELAY:` message per **Who can post
where** in `factory-tracker-ops`): tag the person, request their GitHub
username, include the ticket key and what a valid reply looks like, then end
your turn and resume when they reply. Never substitute a guessed handle.

## Assign the requester as reviewer at PR-open

Every PR the factory opens carries the task requester as a reviewer, assigned at
PR-open — this is non-optional, not a best-effort step the opener can skip, so the
requester never has to assign the PR to themselves. Each PR-opening skill runs the
resolve → assign → fallback flow above as part of opening the PR — `factory-spec`
when it opens the shared spec draft PR, `factory-implement` when it opens its own
PR (the spec was skipped), and `factory-self-update` for skill changes.

For the **shared spec PR** (`factory-spec` opens it, `factory-implement` reuses
it), the spec phase's assignment is the primary one. Implementation does **not**
blindly re-add the requester — check the PR's reviewers via
`scripts/factory-pr-meta find` and call `gh pr edit --add-reviewer` only when the
requester is absent, so the final PR carries the requester exactly once.
