#!/usr/bin/env bash
# ============================================================================
# auto-fix.sh — CatPaw Local Auto-Fix Loop (v2.0 — session-rotate)
#
# Each session runs MAX_LOOP (6) iterations. If issues remain after 6,
# CLOSE current session and START a new one (fresh context).
# New session checks AI Code Review: no issues + mergeable -> MERGE,
# else continue loop fix+push. Max MAX_SESSIONS (3) sessions.
#
# No PR comments — commit messages have fix descriptions,
# AI Code Review <!--AUTOFIX:HAS_ISSUES--> is the TODO list.
#
# USAGE:
#   bash auto-fix.sh <PR_NUMBER>
#   cat auto-fix.sh | claude
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_LOOP=6
MAX_SESSIONS=3
WARNING_AT=4
SLEEP_BETWEEN_LOOPS=45
SLEEP_BETWEEN_SESSIONS=10

PR_NUMBER="${1:-}"

echo "================================================================"
echo "  auto-fix.sh v2.0 — session-rotate"
echo "================================================================"
echo "  Loop/session: ${MAX_LOOP} | Max sessions: ${MAX_SESSIONS}"
echo "  PR: ${PR_NUMBER:-<not specified>}"
echo ""

if [ -z "$PR_NUMBER" ]; then
  echo "Run: gh pr list --state open"
  echo "Then: bash auto-fix.sh <PR_NUMBER>"
  exit 1
fi

echo "Target: PR #${PR_NUMBER}"
echo ""

# ============================================================================
# FIX LOOP INSTRUCTIONS FOR CATPAW AI — repeat until exit
# ============================================================================

echo "================================================================"
echo "  FIX LOOP INSTRUCTIONS"
echo "================================================================"
echo ""
echo "  You are an auto-fix agent for PR #${PR_NUMBER}."
echo "  Project root: ${PROJECT_ROOT}"
echo "  Each session: max ${MAX_LOOP} iterations."
echo "  If ${MAX_LOOP} exhausted and issues remain -> CLOSE session,"
echo "  OPEN new session (fresh context, N=0, S=S+1)."
echo "  New session reads AI Code Review comments to decide:"
echo "    - No issues + mergeable -> MERGE"
echo "    - Issues remain -> continue loop fix+push"
echo "  Max ${MAX_SESSIONS} sessions total."
echo ""

# -- STEP 1: CHECK PR MERGEABLE -----------------------------------------------

echo "  STEP 1: CHECK PR MERGEABLE"
echo "    cd \"${PROJECT_ROOT}\""
echo "    gh pr view ${PR_NUMBER} --json mergeable,mergeStateStatus,headRefName,baseRefName"
echo ""
echo "    Save: headRefName, baseRefName"
echo ""
echo "    mergeable==true AND status in [CLEAN, MERGEABLE] -> MERGE -> EXIT"
echo "    mergeStateStatus==CONFLICTING:"
echo "      git merge origin/<baseRefName> --no-edit"
echo "      conflicts -> EXIT (needs human)"
echo "      success -> continue"
echo "    mergeable==null -> Sleep 15s, retry STEP 1"
echo ""

# -- STEP 2: CHECK RETRY COUNT + SESSION ROTATION -----------------------------

echo "  STEP 2: CHECK RETRY COUNT + SESSION"
echo "    git log -1 --pretty=%B"
echo ""
echo "    Extract from latest commit message:"
echo "      [auto-fix-loop N/${MAX_LOOP}]     -> N = iteration in session"
echo "      [auto-fix-session S/${MAX_SESSIONS}]  -> S = session number"
echo "    If not found: N=0, S=1"
echo "    NEXT=N+1"
echo ""
echo "    When NEXT > ${MAX_LOOP} (session exhausted):"
echo "      NEXT_SESSION = S + 1"
echo "      If NEXT_SESSION > ${MAX_SESSIONS} -> EXIT (needs human)"
echo "      Else:"
echo "        -> Sleep ${SLEEP_BETWEEN_SESSIONS}s"
echo "        -> CLOSE current session"
echo "        -> OPEN new session (fresh context, N=0, S=S+1)"
echo "        -> New session starts at STEP 1: check AI Code Review"
echo "           comments + PR mergeable status"
echo "        -> Commit history is your fix log"
echo ""
echo "    NEXT == ${WARNING_AT} -> CONTINUE (keep fixing)"
echo ""

# -- STEP 3: CHECKOUT PR BRANCH -----------------------------------------------

echo "  STEP 3: CHECKOUT PR BRANCH (every iteration)"
echo "    cd \"${PROJECT_ROOT}\""
echo "    git fetch origin --prune"
echo "    git checkout -B \"<headRefName>\" \"origin/<headRefName>\""
echo "    git merge \"origin/<baseRefName>\" --no-edit 2>/dev/null || true"
echo ""

# -- STEP 4: COLLECT ISSUES ---------------------------------------------------

echo "  STEP 4: COLLECT ISSUES"
echo ""
echo "    SOURCE A — AI REVIEW (TODO list):"
echo "      gh pr view ${PR_NUMBER} --json comments"
echo "      Find latest comment with: <!--AUTOFIX:HAS_ISSUES-->"
echo "      Extract text above marker = your TODO list"
echo "      If <!--AUTOFIX:CLEAN--> -> no review issues, skip to Source B"
echo ""
echo "    SOURCE B — CI FAILURES:"
echo "      gh pr view ${PR_NUMBER} --json statusCheckRollup"
echo "      For each failed check:"
echo "        gh run view <run-id> --log 2>&1 | tail -200"
echo "        Extract error lines"
echo ""
echo "    Both empty -> Sleep ${SLEEP_BETWEEN_LOOPS}s, loop to STEP 1"
echo ""

# -- STEP 5: READ AFFECTED FILES ----------------------------------------------

echo "  STEP 5: READ AFFECTED FILES"
echo "    Extract file paths from issues (ruff, pytest, review text)"
echo "    Read each file completely before fixing"
echo "    Read related files if issue spans modules"
echo ""

# -- STEP 6: FIX CODE ---------------------------------------------------------

echo "  STEP 6: FIX CODE"
echo "    Use string_replace / MultiEdit"
echo "    Only fix actual errors, preserve style"
echo "    Fix source not tests (unless test is wrong)"
echo "    Track: changed_files, fix_summary"
echo ""

# -- STEP 7: VERIFY -----------------------------------------------------------

echo "  STEP 7: VERIFY"
echo "    cd \"${PROJECT_ROOT}\""
echo "    ruff check core/ --extend-exclude '__pycache__'"
echo "    ruff check sap-bridge/ --config sap-bridge/ruff.toml 2>/dev/null || true"
echo "    python .github/scripts/syntax_check.py"
echo "    python -m pytest core/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "    python -m pytest traffic_coordinator_v5/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "    If fails -> fix -> retry (max 3) -> commit what you have"
echo ""

# -- STEP 8: COMMIT + PUSH ----------------------------------------------------

echo "  STEP 8: COMMIT + PUSH"
echo "    cd \"${PROJECT_ROOT}\""
echo "    git config user.name \"CatPaw Auto-Fix\""
echo "    git config user.email \"auto-fix@catpaw.local\""
echo "    git add -A"
echo "    if git diff --staged --quiet: no changes -> sleep, loop"
echo "    git commit -m \"fix: auto-fix-loop NEXT/${MAX_LOOP} session S/${MAX_SESSIONS}"
echo ""
echo "    <fix summary>"
echo ""
echo "    [auto-fix-loop NEXT/${MAX_LOOP}] [auto-fix-session S/${MAX_SESSIONS}]\""
echo "    git push origin \"<headRefName>\""
echo ""

# -- STEP 9: WAIT + LOOP ------------------------------------------------------

echo "  STEP 9: WAIT + LOOP"
echo "    Sleep ${SLEEP_BETWEEN_LOOPS}s for CI + AI review to re-run"
echo "    Push triggers: ci.yml, v5-core-ci.yml, deepseek-pr-review.yml"
echo "    Loop back to STEP 1"
echo ""

# ============================================================================
# EXIT CONDITIONS
# ============================================================================

echo "================================================================"
echo "  EXIT CONDITIONS"
echo "================================================================"
echo ""
echo "  1. MERGEABLE: mergeable==true + status in [CLEAN, MERGEABLE] -> MERGE -> EXIT"
echo "  2. SESSIONS EXHAUSTED: S > ${MAX_SESSIONS} -> EXIT (needs human)"
echo "  3. MERGE CONFLICT: cannot auto-resolve -> EXIT (needs human)"
echo ""
echo "  SESSION ROTATION (not exit):"
echo "    NEXT > ${MAX_LOOP} AND S <= ${MAX_SESSIONS}"
echo "    -> CLOSE session -> OPEN new (S+1, N=0) -> STEP 1"
echo "    -> New session reads AI review, decides MERGE or continue fix"
echo ""
echo "================================================================"
echo "  auto-fix.sh v2.0 END"
echo "================================================================"
