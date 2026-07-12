#!/usr/bin/env bash
# ============================================================================
# auto-fix.sh — CatPaw Local Auto-Fix Loop (v1.0)
#
# Fixes AI Code Review issues + CI failures on a PR, looping until the PR
# is mergeable or the max loop count is reached.
#
# CatPaw is the SOLE FIXER. GitHub Actions only detects and reports.
# The model used for fixing is whatever CatPaw is configured with
# (today: GLM 5.2). No API keys needed on GitHub.
#
# USAGE:
#   bash auto-fix.sh <PR_NUMBER>
#   bash auto-fix.sh              # will list open PRs to pick from
#   cat auto-fix.sh | claude      # pipe to CatPaw as prompt
#
# MULTI-PR PARALLEL:
#   Terminal 1: bash auto-fix.sh 26
#   Terminal 2: bash auto-fix.sh 27   ← independent loop
#   Terminal 3: bash auto-fix.sh 28   ← independent loop
# ============================================================================

PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"
MAX_LOOP=18
WARNING_AT=10
SLEEP_BETWEEN_LOOPS=45   # seconds to wait for CI/review after push

PR_NUMBER="${1:-}"

echo "================================================================"
echo "  auto-fix.sh v1.0 — CatPaw Local Auto-Fix Loop"
echo "================================================================"
echo "  Project:  ${PROJECT_ROOT}"
echo "  Max loop: ${MAX_LOOP} (warning at ${WARNING_AT})"
echo "  PR:       ${PR_NUMBER:-<not specified>}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0 — SELECT PR IF NOT GIVEN
# ═══════════════════════════════════════════════════════════════════════════

if [ -z "$PR_NUMBER" ]; then
  echo "STEP 0 — No PR number specified. Listing open PRs:"
  echo ""
  echo "  Run: gh pr list --state open"
  echo ""
  echo "  Pick a PR number and re-run:"
  echo "    bash auto-fix.sh <PR_NUMBER>"
  echo ""
  echo "  Or if you already know the number, pass it as argument."
  exit 1
fi

echo "Target: PR #${PR_NUMBER}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# MAIN LOOP INSTRUCTIONS FOR CATPAW AI
# ═══════════════════════════════════════════════════════════════════════════
#
# CatPaw AI: Follow these instructions EXACTLY. This is a LOOP.
# Repeat until an exit condition is met.
#

echo "================================================================"
echo "  FIX LOOP INSTRUCTIONS"
echo "================================================================"
echo ""
echo "  You are an auto-fix agent for PR #${PR_NUMBER}."
echo "  Project root: ${PROJECT_ROOT}"
echo "  You fix code issues found by AI review AND CI failures."
echo "  You loop until the PR is mergeable or max ${MAX_LOOP} iterations."
echo ""
echo "  LOOP STEPS (repeat until exit condition):"
echo ""

# ── STEP 1: CHECK PR MERGEABLE ──────────────────────────────────────────────

echo "  ┌─ STEP 1: CHECK PR MERGEABLE STATUS ─────────────────────┐"
echo "  │                                                          │"
echo "  │  Run:                                                    │"
echo "  │    cd \"${PROJECT_ROOT}\""
echo "  │    gh pr view ${PR_NUMBER} --json mergeable,mergeStateStatus,headRefName,baseRefName"
echo "  │                                                          │"
echo "  │  Parse the JSON output:                                  │"
echo "  │    mergeable: true/false/null                            │"
echo "  │    mergeStateStatus: CLEAN/MERGEABLE/BLOCKED/CONFLICTING │"
echo "  │    headRefName: <branch-name>     ← SAVE THIS            │"
echo "  │    baseRefName: <base-branch>     ← SAVE THIS            │"
echo "  │                                                          │"
echo "  │  EXIT CONDITIONS:                                        │"
echo "  │    mergeable==true AND mergeStateStatus in [CLEAN, MERGEABLE]:"
echo "  │      → Post comment: \"🎉 PR #${PR_NUMBER} is mergeable! Auto-fix complete.\""
echo "  │      → EXIT (success)                                    │"
echo "  │                                                          │"
echo "  │    mergeStateStatus==CONFLICTING:                        │"
echo "  │      → Try: git merge origin/<baseRefName> --no-edit     │"
echo "  │      → If merge conflicts:                               │"
echo "  │        Post comment: \"⚠️ Merge conflict, needs human resolve.\""
echo "  │        → EXIT (needs human)                              │"
echo "  │      → If merge succeeds: continue to fix loop            │"
echo "  │                                                          │"
echo "  │    mergeable==null:                                      │"
echo "  │      → GitHub is still computing. Sleep 15s, retry STEP 1│"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 2: CHECK RETRY COUNT ──────────────────────────────────────────────

echo "  ┌─ STEP 2: CHECK RETRY COUNT ──────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Run (on the PR head branch, after STEP 3 checkout):     │"
echo "  │    git log -1 --pretty=%B                                │"
echo "  │                                                          │"
echo "  │  Look for pattern: [auto-fix-review N/${MAX_LOOP}]       │"
echo "  │                                                          │"
echo "  │  If found, extract N (current iteration).                │"
echo "  │  If not found, N=0 (first run).                          │"
echo "  │                                                          │"
echo "  │  NEXT=N+1                                                │"
echo "  │                                                          │"
echo "  │  EXIT CONDITIONS:                                        │"
echo "  │    NEXT > ${MAX_LOOP}:                                    │"
echo "  │      → Post comment: \"⛔ Max ${MAX_LOOP} iterations reached. Needs human intervention.\""
echo "  │      → EXIT (max reached)                                │"
echo "  │                                                          │"
echo "  │  WARNING:                                                │"
echo "  │    NEXT == ${WARNING_AT}:                                  │"
echo "  │      → Post comment: \"⚠️ Warning: ${WARNING_AT} iterations reached, still fixing. Will continue up to ${MAX_LOOP}.\""
echo "  │      → CONTINUE (do not exit)                            │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 3: CHECKOUT PR BRANCH (CRITICAL — DO EVERY ITERATION) ─────────────

echo "  ┌─ STEP 3: CHECKOUT PR BRANCH (CRITICAL) ──────────────────┐"
echo "  │                                                          │"
echo "  │  This step prevents fixing on the wrong branch.          │"
echo "  │  Do this EVERY iteration, even if you think you're       │"
echo "  │  already on the right branch.                            │"
echo "  │                                                          │"
echo "  │  Commands:                                               │"
echo "  │    cd \"${PROJECT_ROOT}\""
echo "  │    git fetch origin --prune                              │"
echo "  │    git checkout -B \"<headRefName>\" \"origin/<headRefName>\" │"
echo "  │                                                          │"
echo "  │  VERIFY (abort if mismatch):                             │"
echo "  │    CURRENT=\$(git branch --show-current)                  │"
echo "  │    if [ \"\$CURRENT\" != \"<headRefName>\" ]; then             │"
echo "  │      echo \"FATAL: Expected <headRefName> but on \$CURRENT\"│"
echo "  │      exit 1                                              │"
echo "  │    fi                                                    │"
echo "  │    echo \"On correct branch: \$CURRENT\"                    │"
echo "  │                                                          │"
echo "  │  SYNC WITH BASE (avoid conflicts):                       │"
echo "  │    git merge \"origin/<baseRefName>\" --no-edit \\           │"
echo "  │      2>/dev/null || echo \"No new changes on base\"         │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 4: COLLECT ISSUES (TWO SOURCES) ───────────────────────────────────

echo "  ┌─ STEP 4: COLLECT ISSUES (TWO SOURCES) ───────────────────┐"
echo "  │                                                          │"
echo "  │  SOURCE A — AI REVIEW COMMENTS:                          │"
echo "  │    Run:                                                  │"
echo "  │      gh pr view ${PR_NUMBER} --json comments              │"
echo "  │                                                          │"
echo "  │    Find the LATEST comment containing:                   │"
echo "  │      <!--AUTOFIX:HAS_ISSUES-->                           │"
echo "  │                                                          │"
echo "  │    If found:                                             │"
echo "  │      → Extract the review text ABOVE the marker          │"
echo "  │      → This is your list of issues to fix                │"
echo "  │                                                          │"
echo "  │    If latest comment has <!--AUTOFIX:CLEAN-->:           │"
echo "  │      → No review issues. Skip to Source B.               │"
echo "  │                                                          │"
echo "  │    If no comment with marker found:                      │"
echo "  │      → Review may not have run yet. Skip to Source B.    │"
echo "  │                                                          │"
echo "  │  SOURCE B — CI CHECK FAILURES:                           │"
echo "  │    Run:                                                  │"
echo "  │      gh pr view ${PR_NUMBER} --json statusCheckRollup                            │"
echo "  │                                                          │"
echo "  │    Look for any check with \"fail\" or \"failure\".          │"
echo "  │                                                          │"
echo "  │    For each failed check:                                │"
echo "  │      → Get the run ID from the check output              │"
echo "  │      → Run: gh run view <run-id> --log 2>&1 | tail -200  │"
echo "  │      → Extract error lines (lines with \"error\",           │"
echo "  │        \"Error\", \"FAILED\", \"Traceback\", \"ruff\",            │"
echo "  │        \"E \", \"assert\", \"ImportError\", etc.)              │"
echo "  │                                                          │"
echo "  │  COMBINE: Merge issues from Source A + Source B.         │"
echo "  │    If both are empty:                                    │"
echo "  │      → No issues found. Sleep ${SLEEP_BETWEEN_LOOPS}s, loop to STEP 1"
echo "  │    If only Source A has issues: fix review findings      │"
echo "  │    If only Source B has issues: fix CI failures          │"
echo "  │    If both have issues: fix both in this iteration       │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 5: READ AFFECTED FILES ────────────────────────────────────────────

echo "  ┌─ STEP 5: READ AFFECTED SOURCE FILES ─────────────────────┐"
echo "  │                                                          │"
echo "  │  From the issues collected in STEP 4, extract file paths.│"
echo "  │                                                          │"
echo "  │  Patterns to match:                                      │"
echo "  │    - ruff: path/to/file.py:line:col: CODE message        │"
echo "  │    - pytest: File \"path/to/file.py\", line N              │"
echo "  │    - pytest: path/to/file.py::TestClass::test_method     │"
echo "  │    - review: file paths mentioned in comment text        │"
echo "  │    - generic: any *.py, *.ts, *.tsx path in error output │"
echo "  │                                                          │"
echo "  │  For each file:                                          │"
echo "  │    → Use read_file tool to read the COMPLETE file        │"
echo "  │    → Understand the context before fixing                │"
echo "  │    → Do NOT fix blindly — read first, understand, fix    │"
echo "  │                                                          │"
echo "  │  Also read related files if the issue spans modules:     │"
echo "  │    - If coordinator.py has an issue, also check          │"
echo "  │      config.py, messages.py for related types            │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 6: FIX CODE ───────────────────────────────────────────────────────

echo "  ┌─ STEP 6: FIX CODE ───────────────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Use CatPaw edit tools (string_replace, MultiEdit) to    │"
echo "  │  apply fixes. Do NOT rewrite entire files unless needed. │"
echo "  │                                                          │"
echo "  │  Fix rules:                                              │"
echo "  │    1. Only fix actual errors. Do not refactor.           │"
echo "  │    2. Preserve existing code style, comments, naming.    │"
echo "  │    3. For ruff: fix the specific lint issue.             │"
echo "  │    4. For syntax errors: fix with minimal changes.       │"
echo "  │    5. For test failures: fix SOURCE code, not tests      │"
echo "  │       (unless the test itself is wrong).                 │"
echo "  │    6. For import errors: add missing imports.            │"
echo "  │    7. For review issues: address the specific concern.   │"
echo "  │    8. Match existing indentation (tabs vs spaces).       │"
echo "  │                                                          │"
echo "  │  After fixing, track what you changed:                   │"
echo "  │    changed_files = []                                    │"
echo "  │    fix_summary = []                                      │"
echo "  │    For each fix: record file + what was fixed.           │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 7: VERIFY ─────────────────────────────────────────────────────────

echo "  ┌─ STEP 7: VERIFY FIXES ───────────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Run verification commands (cd \"${PROJECT_ROOT}\" first):  │"
echo "  │                                                          │"
echo "  │  1. Ruff lint:                                           │"
echo "  │       ruff check core/ --extend-exclude '__pycache__'    │"
echo "  │       ruff check sap-bridge/ --config sap-bridge/ruff.toml 2>/dev/null || true"
echo "  │       ruff check scripts/ --ignore E501 2>/dev/null || true"
echo "  │                                                          │"
echo "  │  2. Syntax check:                                        │"
echo "  │       python .github/scripts/syntax_check.py             │"
echo "  │                                                          │"
echo "  │  3. Pytest (fast tests, no external deps):               │"
echo "  │       python -m pytest core/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "  │       python -m pytest traffic_coordinator_v5/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "  │                                                          │"
echo "  │  If verification FAILS:                                  │"
echo "  │    → Read the new error output                           │"
echo "  │    → Fix the new error (go back to STEP 6)              │"
echo "  │    → Re-run verification                                 │"
echo "  │    → Max 3 retry attempts per iteration for verification │"
echo "  │    → If still failing after 3 tries:                     │"
echo "  │      commit what you have, note remaining issues         │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 8: COMMIT + PUSH ──────────────────────────────────────────────────

echo "  ┌─ STEP 8: COMMIT + PUSH ──────────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Commands:                                               │"
echo "  │    cd \"${PROJECT_ROOT}\""
echo "  │    git config user.name \"CatPaw Auto-Fix\""
echo "  │    git config user.email \"auto-fix@catpaw.local\"         │"
echo "  │                                                          │"
echo "  │    git add -A                                            │"
echo "  │                                                          │"
echo "  │    # Check if there are actual changes                   │"
echo "  │    if git diff --staged --quiet; then                    │"
echo "  │      echo \"No changes to commit\"                         │"
echo "  │      → Sleep ${SLEEP_BETWEEN_LOOPS}s, loop to STEP 1     │"
echo "  │    fi                                                    │"
echo "  │                                                          │"
echo "  │    # Commit with retry counter                           │"
echo "  │    git commit -m \"fix: auto-fix-review NEXT/${MAX_LOOP}   │"
echo "  │                                                          │"
echo "  │    <fix summary — what was fixed and why>                │"
echo "  │                                                          │"
echo "  │    [auto-fix-review NEXT/${MAX_LOOP}]\"                    │"
echo "  │                                                          │"
echo "  │    # Push to PR branch                                   │"
echo "  │    git push origin \"<headRefName>\"                       │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 9: POST PR COMMENT ────────────────────────────────────────────────

echo "  ┌─ STEP 9: POST PR COMMENT ────────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Post a comment on the PR summarizing what was fixed:    │"
echo "  │                                                          │"
echo "  │  Run:                                                    │"
echo "  │    gh pr comment ${PR_NUMBER} --body \"## 🔧 Auto-Fix NEXT/${MAX_LOOP}"
echo "  │                                                          │"
echo "  │    **Fixed files:**                                      │"
echo "  │    - \`file1.py\` — description of fix                    │"
echo "  │    - \`file2.py\` — description of fix                    │"
echo "  │                                                          │"
echo "  │    **Issues addressed:**                                 │"
echo "  │    - Review: <issue from AI review>                     │"
echo "  │    - CI: <error from CI check>                          │"
echo "  │                                                          │"
echo "  │    **Verification:** ruff ✅ / pytest ✅/⚠️              │"
echo "  │                                                          │"
echo "  │    ---                                                    │"
echo "  │    *CatPaw auto-fix loop: NEXT/${MAX_LOOP}*\"              │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ── STEP 10: WAIT + LOOP ───────────────────────────────────────────────────

echo "  ┌─ STEP 10: WAIT + LOOP ───────────────────────────────────┐"
echo "  │                                                          │"
echo "  │  Sleep ${SLEEP_BETWEEN_LOOPS} seconds to let GitHub Actions       │"
echo "  │  re-run CI checks and DeepSeek AI review.                │"
echo "  │                                                          │"
echo "  │  Then loop back to STEP 1.                               │"
echo "  │                                                          │"
echo "  │  The push in STEP 8 triggers:                            │"
echo "  │    - ci.yml → CI checks re-run                           │"
echo "  │    - v5-core-ci.yml → core tests re-run                  │"
echo "  │    - deepseek-pr-review.yml → new AI review comment      │"
echo "  │                                                          │"
echo "  │  After waiting, STEP 1 will check if PR is now           │"
echo "  │  mergeable. If yes → exit. If no → STEP 4 collects       │"
echo "  │  new issues from the fresh review + CI run.              │"
echo "  │                                                          │"
echo "  └──────────────────────────────────────────────────────────┘"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# EXIT CONDITIONS SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

echo "================================================================"
echo "  EXIT CONDITIONS"
echo "================================================================"
echo ""
echo "  1. ✅ PR MERGEABLE"
echo "     mergeable==true AND mergeStateStatus in [CLEAN, MERGEABLE]"
echo "     → Post success comment → EXIT"
echo ""
echo "  2. ⛔ MAX LOOP REACHED"
echo "     NEXT > ${MAX_LOOP}"
echo "     → Post 'needs human' comment → EXIT"
echo ""
echo "  3. ⚠️ MERGE CONFLICT"
echo "     mergeStateStatus==CONFLICTING AND cannot auto-resolve"
echo "     → Post 'conflict' comment → EXIT"
echo ""
echo "  4. ✅ NO ISSUES + NO CI FAILURES"
echo "     Source A: <!--AUTOFIX:CLEAN--> in latest review"
echo "     Source B: all CI checks pass"
echo "     → If also mergeable → EXIT (same as #1)"
echo "     → If not yet mergeable → sleep, loop, re-check"
echo ""
echo "  WARNING at NEXT==${WARNING_AT}:"
echo "     Post warning comment but CONTINUE fixing"
echo ""
echo "================================================================"
echo "  auto-fix.sh v1.0 END"
echo "================================================================"
