---
name: factory-ui-verification
description: Capture and surface video or screenshot proof for user-facing UI changes after implementation. Use whenever a change produces observable UI so that the implementation agent exercises the running interface, records visual proof, and attaches it to the task record and PR body. Uses the computer_use tool to drive the running UI and never commits media to the branch.
---

# factory-ui-verification

Dedicated UI-verification skill for the factory loop. This skill is the companion
to `factory-verification`. The latter owns the overall verification mandate
(regression tests + the target repo's validation gate, its `validate_command`
from its `target_repos` entry, plus the rule that user-facing changes need
visual proof). This skill owns the **mechanics of capturing that visual proof**
and surfacing it to the user.

## Trigger

Invoke this skill after implementation is complete, **whenever the change is
user-facing**. A change is user-facing when a human could see its effect rendered
in a UI, whether it touches a web app, a desktop client, a modal, a launch page,
or any other visual surface.

- Backend or headless changes do **not** trigger this skill.
- Configuration-only or data-only changes that happen to live in a UI repo but
  do not alter rendered output do not trigger this skill.
- When in doubt, err on the side of capturing proof.

## What to capture

Record the changed UI in action on the real path.

- For a **fix**, capture the surface before and after the change to show the
  symptom is gone.
- For a **new feature**, capture the new surface rendered and any key
  interactions.
- Prefer **video** when the change involves motion, transitions, or a multi-step
  interaction. A short clip is stronger than a series of stills.
- Prefer **screenshots** when the change is a static visual delta.
- Annotate the proof with a brief caption so the viewer knows what path was
  exercised.

## Validate proof against the spec

The captured proof must demonstrate the spec's acceptance criteria, not merely
exist. Before attaching screenshots or video, check each visual against the
approved ticket spec and the linked issue's acceptance criteria. The proof should
show the exact surface, state, and behavior the spec requires. Proof that captures
the wrong path, an incomplete state, or a missing acceptance criterion is treated
as missing proof.

## How to capture

**Do not install or configure a browser manually.** The `computer_use` tool
provides a pre-configured GUI desktop environment with a browser (Chromium)
already available. Never run `playwright install`, `apt-get install chromium`,
or attempt to configure browser library paths yourself — these steps waste time
and are error-prone. Use the `computer_use` tool directly.

Follow these four steps.

**Step 1 — Start the application server before the session.**
Before opening a `computer_use` session, start the app server so it is
reachable at a local URL. The task's target repo entry in config `target_repos`
(in `foreman/config.json`) declares how — its optional `app_start_command` is
the command that boots the app for UI verification, and its optional `app_url`
is the local URL the running app serves. Run the start command **in the
background** from the repo root.
```bash
# The target repo's app_start_command from its target_repos entry:
<app_start_command> &
```
Wait a few seconds for the server to become ready at the repo's `app_url`.
When the repo's entry has no `app_start_command` / `app_url`, derive the
startup command from the repo's README (or its `test_guidance` entry) and note
the command you used in the task record.

**Step 2 — Use computer_use to navigate the UI and save screenshots.**
Open a `computer_use` session and instruct it to perform the following steps.
1. Open a browser (Chromium is available in the desktop environment).
2. Navigate to the running app at the target repo's `app_url` (e.g.
   `http://localhost:8000`).
3. Exercise the affected UI path(s) — one UI state per scenario.
4. After reaching each key state, save a screenshot to a named disk file
   using this command.
   ```bash
   # Install scrot if not present:
   apt-get install -y scrot
   # Save a screenshot of the current screen:
   scrot -o /tmp/screenshot_<label>.png
   ```
   Name each file to make the scenario clear (e.g.
   `screenshot_a_no_bundle.png`, `screenshot_b_bundle_selected.png`,
   `screenshot_c_global_search_active.png`).

The `computer_use` tool lets the subagent see and interact with the screen, but
it does **not** return screenshot files to the calling agent. If the session ends
but no files exist at the expected paths, **the proof was not saved** — do not
treat the session as complete. Re-run it with explicit `scrot` commands at each
key UI state. A textual description of what the subagent observed is **never** a
substitute for actual image files.

**Step 3 — Upload screenshot files to GitHub.**
After the `computer_use` session ends, upload the saved files to get persistent,
publicly accessible URLs using the following commands.
```bash
gh release create visual-proof-<ticket-id> \
  --repo <owner/repo> \
  --title "Visual proof for <ticket-id>" \
  --notes "Screenshots for PR #<N>." \
  /tmp/screenshot_a_<label>.png /tmp/screenshot_b_<label>.png

# Verify the asset URLs:
gh release view visual-proof-<ticket-id> \
  --repo <owner/repo> \
  --json assets --jq '.assets[] | {name: .name, url: .url}'
```

**Step 4 — Embed via markdown image syntax.**
In the PR body and in the task record update, reference each screenshot by its
GitHub release download URL using the markdown image syntax shown below.
```markdown
![Caption describing the UI state](https://github.com/<owner>/<repo>/releases/download/visual-proof-<ticket-id>/<filename>.png)
```

No tool is a substitute for a real repro on the changed path. Capture the actual
rendered surface, not a mockup or static image from design.

## Attach the proof in two places

Visual proof is only useful if the reviewer and the requester can see it.

1. **Task record.** Embed the screenshots or video link in a progress update via
   `factory-tracker-ops` so the record carries the visual evidence.
2. **PR body.** Embed the same proof in the final PR description so the reviewer
   sees the validated behavior without re-running anything.

**Never commit the media to the branch.** Screenshots, videos, and screen
recordings are verification artifacts, not source code. They attach to the task
record and PR body only.

## If the UI cannot be exercised

If the running UI genuinely cannot be reached (for example, the local
environment cannot render the surface, a required credential is missing, or the
app cannot launch in the cloud environment), **say so explicitly** in the task
record and the PR body. Do not silently omit the proof. Treat the visual
verification as outstanding, not as satisfied.

A UI change shipped with a documented reason why visual proof is unavailable is
still incomplete until a human can confirm the rendered behavior. Record the
blocker and, when possible, the next step to obtain proof.

## Rework path

When a review rejection bounces the work back with `blocked`, re-run the UI
verification and capture updated proof **against the spec** before the PR is
re-marked ready. Update the PR description and the task record with the new
visuals; do not commit the media to the branch.

## Integration with factory-verification

`factory-verification` mandates that user-facing changes require visual proof.
This skill provides the concrete steps. When a change is user-facing, the
implementation agent should do the following.

1. Complete the code-level verification from `factory-verification` (a
   regression test per the target repo's `test_guidance` plus its validation
   gate, its `validate_command`, both from the repo's `target_repos` entry).
2. Invoke this skill to capture and surface the visual proof.
3. Only report the implementation complete when both steps are done, or when the
   outstanding proof has been explicitly flagged.
