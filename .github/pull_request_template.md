<!--
  PR template — rendered on PR creation (covers the manual-creation path).
  The AI-coding path is covered server-side by pr-supersession-check.yml,
  which runs on every pull_request event regardless of how the PR was made.
  Fill the checklist; delete sections that don't apply.
-->

## Pre-flight checklist

- [ ] Rebased on `master` and resolved all merge conflicts (no `<<<<<<<` / `=======` / `>>>>>>>` markers remain)
- [ ] Verified the diff vs `master` is **non-empty** (changes aren't already delivered by another PR)
- [ ] Checked **no open PR** covers the same files or concerns (if one does, I've coordinated with its author)
- [ ] This PR addresses a **single concern** (mixed concerns split into separate PRs)
- [ ] `ruff check .` and `ruff format --check .` pass locally
- [ ] Relevant tests pass (`pytest`)

## For AI-generated PRs

- [ ] Confirmed no parallel AI-PR already delivered these changes to `master`
- [ ] Reviewed and verified the AI-generated diff (not just that it compiles)

## Changes

<!-- What this PR accomplishes and why. Link the design plan / issue if any. -->

## Verification

<!-- How you tested this end-to-end (command, scenario, screenshot). -->

## Related

<!-- Issues, PRs, plan docs this supersedes or depends on. -->
