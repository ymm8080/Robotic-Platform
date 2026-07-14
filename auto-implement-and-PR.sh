#!/usr/bin/env bash
# ============================================================================
# auto-implement-and-PR.sh — Implement a plan phase → single PR (no merge)
#
# Durable, self-contained replacement for the memory-driven "auto-implement-and-PR"
# trigger. Hard-codes the plan-discovery step so the flow no longer depends on
# memory being loaded: it resolves the LATEST dated .md plan in the canonical
# IMPLEMENTATION PLAN folder (by mtime), reads it fully, then fans out the
# implement → verify → branch → PR flow.
#
# This is a PROMPT-SCRIPT (like auto-fix.sh): the body resolves paths and
# echoes instructions for the Claude/CatPaw agent. Run either way:
#   bash auto-implement-and-PR.sh [phase]
#   cat auto-implement-and-PR.sh | claude
#
# NOTE: This is the IMPLEMENTATION stage ONLY. auto-fix.sh runs AFTER the PR
# is created and CI/AI-review have run — do not invoke it during implementation.
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN_DIR="D:/EWM ROBOT/REFERENCE/DESIGN ALL/IMPLEMENTATION PLAN"
PHASE_HINT="${1:-}"

echo "================================================================"
echo "  auto-implement-and-PR.sh — implement plan phase → PR (no merge)"
echo "================================================================"
echo "  Project root: ${PROJECT_ROOT}"
echo "  Plan folder:  ${PLAN_DIR}"
[ -n "$PHASE_HINT" ] && echo "  Phase hint:   ${PHASE_HINT}"
echo ""

# ============================================================================
# STEP 0: RESOLVE THE LATEST PLAN (by modification time, .md only)
# ============================================================================
# Why mtime not filename-date: read-all-plans-latest-first rule says ls -lt and
# take newest by mtime. Why filter *.md: the folder also holds _build_*.py,
# _v7plan_diagrams/, and generated .docx that share the newest timestamps but
# are NOT plans. Case-insensitive glob catches .MD variants.

shopt -s nocaseglob
LATEST_PLAN=$(ls -t "${PLAN_DIR}"/*.md 2>/dev/null | head -1)
shopt -u nocaseglob

if [ -z "$LATEST_PLAN" ]; then
  echo "[ERROR] No .md plan found in: ${PLAN_DIR}"
  echo "        Check the path and that at least one plan .md exists."
  exit 1
fi

# Sanity: confirm it really looks like a plan (name contains 'plan' or a date),
# and warn if the newest .md is a build/helper file that slipped through.
BASENAME=$(basename "$LATEST_PLAN")
if echo "$BASENAME" | grep -qiE "_build|_diagram|helper|template"; then
  echo "[WARN] Newest .md by mtime looks like a helper file: ${BASENAME}"
  echo "       Falling back to newest plan-named .md."
  shopt -s nocaseglob
  LATEST_PLAN=$(ls -t "${PLAN_DIR}"/*plan*.md "${PLAN_DIR}"/*实施*.md "${PLAN_DIR}"/*IMPLEMENTATION*.md 2>/dev/null | head -1)
  shopt -u nocaseglob
fi

echo "================================================================"
echo "  STEP 0: LATEST PLAN (authoritative — read COMPLETELY first)"
echo "================================================================"
echo "  ${LATEST_PLAN}"
echo ""
echo "  -> ls -lt \"${PLAN_DIR}\"  # to see all plans by date for context"
echo ""

# ============================================================================
# IMPLEMENT-AND-PR INSTRUCTIONS FOR THE AGENT
# ============================================================================

echo "================================================================"
echo "  IMPLEMENT-AND-PR INSTRUCTIONS"
echo "================================================================"
echo ""
echo "  You are running auto-implement-and-PR: implement ONE phase of the"
echo "  latest plan into a single PR. Do NOT merge."
echo "  Project root: ${PROJECT_ROOT}"
echo ""

# -- STEP 1: READ THE PLAN ----------------------------------------------------

echo "  STEP 1: READ THE LATEST PLAN COMPLETELY"
echo "    Read this file IN FULL before touching any source:"
echo "      \"${LATEST_PLAN}\""
[ -n "$PHASE_HINT" ] && echo "    Target phase hint: ${PHASE_HINT}" \
  || echo "    Pick the next un-built phase per the plan's stated build order."
echo "    Older plans in the folder are CONTEXT ONLY — the latest is authority."
echo ""

# -- STEP 2: AVOID SUPERSESSION ----------------------------------------------

echo "  STEP 2: CONFIRM MASTER STATE + OPEN PRs (avoid superseding)"
echo "    cd \"${PROJECT_ROOT}\""
echo "    git fetch origin --prune"
echo "    git checkout master && git pull --ff-only"
echo "    gh pr list --state open --json number,title,headRefName"
echo "    If an open PR already covers this phase -> STOP, surface it."
echo "    See pr-supersession-prevention / sap-zewm-pr-supersession rules."
echo ""

# -- STEP 3: DECOMPOSE + FAN OUT ---------------------------------------------

echo "  STEP 3: DECOMPOSE PHASE → PARALLEL AGENTS (multi-agent Workflow)"
echo "    Break the phase into independent units (one per brand/file/module)."
echo "    Use the Workflow tool with pipeline()/parallel():"
echo "      - implement agents (disjoint files, or worktree isolation on conflict)"
echo "      - an adversarial reviewer agent"
echo "      - a test/verify agent"
echo "    Each implement agent does its OWN ruff+pytest inline — do NOT defer"
echo "    all verification to the end."
echo ""

# -- STEP 4: SYNTHESIZE + VERIFY --------------------------------------------

echo "  STEP 4: SYNTHESIZE + VERIFY"
echo "    cd \"${PROJECT_ROOT}\""
echo "    ruff check core/ --extend-exclude '__pycache__'"
echo "    ruff check sap-bridge/ --config sap-bridge/ruff.toml 2>/dev/null || true"
echo "    python .github/scripts/syntax_check.py"
echo "    python -m pytest core/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "    python -m pytest sap-bridge/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "    python -m pytest traffic_coordinator_v5/tests/ -q --tb=short --no-header 2>&1 | tail -30"
echo "    Red -> fix in-agent -> retry (max 3)."
echo ""

# -- STEP 5: BRANCH + PR (NO MERGE) -----------------------------------------

echo "  STEP 5: BRANCH OFF MASTER + CREATE PR (NEVER MERGE)"
echo "    cd \"${PROJECT_ROOT}\""
echo "    BRANCH=\"auto-impl/<phase-slug>\""
echo "    git checkout -B \"\$BRANCH\" master"
echo "    git add -A"
echo "    git commit -m \"feat(<phase>): <summary>\""
echo "    git push -u origin \"\$BRANCH\""
echo "    gh pr create --base master --title \"<phase title>\" --body-file .pr-body.md"
echo "    DO NOT run gh pr merge. The AI code review gate handles merge."
echo ""

# -- STEP 6: POST-PR HANDOFF -------------------------------------------------

echo "  STEP 6: POST-PR HANDOFF"
echo "    After CI (ci.yml, v5-core-ci.yml) + AI review (deepseek-pr-review.yml)"
echo "    have run on the new PR, hand off to the fix loop:"
echo "      bash auto-fix.sh <NEW_PR_NUMBER>"
echo "    auto-fix.sh is a POST-PR stage only — never during implementation."
echo ""

# ============================================================================
# EXIT CONDITIONS
# ============================================================================

echo "================================================================"
echo "  EXIT CONDITIONS"
echo "================================================================"
echo ""
echo "  1. PR CREATED: gh pr create succeeded -> hand off to auto-fix.sh -> EXIT"
echo "  2. SUPERSEDED: open PR already covers this phase -> STOP (surface it)"
echo "  3. UNRESOLVABLE FAILURES: ruff/pytest red after 3 retries -> EXIT (human)"
echo "  4. PLAN AMBIGUOUS: phase cannot be determined -> EXIT (ask human)"
echo ""
echo "================================================================"
echo "  auto-implement-and-PR.sh END"
echo "================================================================"
