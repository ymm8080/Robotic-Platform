#!/usr/bin/env bash
# ============================================================================
# auto-implement-and-pr.sh — v5.1 (DAG-driven, program-logic deps)
# Claude Code instruction document: reads a pre-built plan, AUTO-DETECTS
# dependencies from PROGRAM DEVELOPMENT LOGIC (creates→consumes matching)
# AND enforces HARD file-overlap constraint (no same-file parallel edits),
# dispatches subagents wave-by-wave, then PR.
#
# USAGE:  cat auto-implement-and-pr.sh | claude
#    OR   open this file in Claude Code and say "run auto-implement-and-pr"
# ============================================================================

# ======================= Configuration =======================
IMPL_PLAN_DIR="d:/ewm robot/reference/design all/implementation plan"
PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"
TODAY_DATE=$(date +%Y%m%d 2>/dev/null || echo 'TODAY')
PLAN_FILE=$(ls -t "${IMPL_PLAN_DIR}"/*${TODAY_DATE}*.* 2>/dev/null | head -1)
if [ -z "${PLAN_FILE}" ]; then
  echo "ERROR: No plan file found in ${IMPL_PLAN_DIR} containing today's date (${TODAY_DATE})."
  echo "Please run auto-plan-implement-and-pr.sh first, or create a plan file manually."
  exit 1
fi
BRANCH_NAME="feat/auto-impl-$(date +%Y%m%d-%H%M%S 2>/dev/null || echo 'snapshot')"
# ============================================================

echo "=============================================="
echo " auto-implement-and-pr.sh v5.1 (DAG-driven)"
echo " Plan : ${PLAN_FILE}"
echo " Root : ${PROJECT_ROOT}"
echo "=============================================="
echo ""

# ╔══════════════════════════════════════════════════════════════╗
# ║  CRITICAL RULE — READ THIS FIRST                           ║
# ╚══════════════════════════════════════════════════════════════╝
#
# YOU (Claude Code) are the ORCHESTRATOR, not the implementer.
# You MUST use the Agent tool to spawn subagents for EVERY phase.
# You MUST NOT implement any code yourself.
# You MUST NOT edit files directly.
#
# v5.1 DESIGN — Three rules for dispatch sequencing:
#
#   RULE 1 — PRIORITY (P0/P1), declared by the plan author:
#     = How CRITICAL this phase is. Like a severity label.
#     P0 = critical. Failure → no PR. Dispatch FIRST when multiple ready.
#     P1 = normal.   Failure → PR with notes. Dispatch AFTER P0 if tied.
#     Has ZERO relationship with dependencies.
#
#   RULE 2 — LOGICAL dependency, auto-detected from creates→consumes:
#     = Does Phase B USE (call, import, reference) something Phase A CREATES?
#     Detected by matching each phase's CREATES against every other's CONSUMES.
#     Example: P1-4 creates GET /playback, P1-6 calls GET /playback → P1-6 depends on P1-4.
#
#   RULE 3 — MECHANICAL constraint (HARD): same file = cannot run in parallel.
#     = If two phases touch the SAME FILE, they MUST be sequenced.
#     Even if they edit different lines/functions, simultaneous edits cause git conflicts.
#     Order: P0 before P1, then by phase ID.
#     Example: P0-1 and P0-2 both touch core/config.py → cannot be in same wave.
#
#   RULE 2 and RULE 3 both result in sequencing. They are independent reasons.
#   A phase may be blocked by BOTH a logical dep AND a file conflict.

echo "=== CLAUDE CODE ORCHESTRATION INSTRUCTIONS ==="
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP -1 — CREATE BRANCH BEFORE ANY CODE CHANGES
# ═══════════════════════════════════════════════════════════════
echo "STEP -1 — Create feature branch BEFORE development starts"
echo ""
echo "   ACTION: Run these git commands BEFORE dispatching any agent:"
echo "     1. cd ${PROJECT_ROOT}"
echo "     2. git status                    # review starting state"
echo "     3. git checkout -b ${BRANCH_NAME}  # create and switch"
echo "     4. git branch --show-current      # confirm"
echo ""
echo "   WHY: All subagent changes land on this branch from the start."
echo "   If branch already exists, use 'git checkout ${BRANCH_NAME}' instead."
echo "   If there are uncommitted changes, stash them first: git stash"
echo ""
echo "   *** Do NOT proceed to Step 0 until branch is confirmed. ***"
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 0 — READ PLAN → EXTRACT PHASES + PRIORITIES + CREATES/CONSUMES + FILES
# ═══════════════════════════════════════════════════════════════
echo "STEP 0 — Read plan and extract phases"
echo ""
echo "   Plan file: ${PLAN_FILE}"
echo ""
echo "   For EVERY phase in the plan, extract:"
echo "     - Phase ID (e.g. 'P0-1', 'P1-4')"
echo "     - Title"
echo "     - Priority: P0 (critical) or P1 (normal)"
echo "       This is ONLY a criticality label. NOT a dependency."
echo "     - CREATES: what new code artifacts this phase produces"
echo "       (new functions, classes, endpoints, config keys, modules)"
echo "     - CONSUMES: what existing or new code artifacts this phase uses"
echo "       (imports, function calls, API calls, config reads)"
echo "     - Files: the list of file paths under **Files:**"
echo "     - Changes: what to implement"
echo "     - Verify: the verification command"
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 0.5 — AUTO-DETECT DEPENDENCIES (TWO LAYERS)
# ═══════════════════════════════════════════════════════════════
echo "STEP 0.5 — Auto-detect all sequencing constraints"
echo ""
echo "   Two independent checks. Both produce sequencing constraints."
echo ""

echo "   ============================================================"
echo "   LAYER 1 — LOGICAL dependencies (creates -> consumes)"
echo "   ============================================================"
echo ""
echo "   Build two lookup tables from the plan:"
echo "     creates_map[artifact_key] = [phase_ids that CREATE it]"
echo "     consumes_map[artifact_key] = [phase_ids that CONSUME it]"
echo ""
echo "   Artifact key format:"
echo "     function:  \"module.py::function_name()\""
echo "     class:     \"module.py::ClassName\""
echo "     endpoint:  \"GET /api/path\"  or  \"POST /api/path\""
echo "     config:    \"ClassName.field_name\""
echo "     file:      \"path/to/file.py\" (only for NEW files)"
echo "     cli:       \"cli.py::--flag-name\""
echo ""
echo "   Match: For each artifact in creates_map:"
echo "     producers = creates_map[key]"
echo "     consumers = consumes_map[key]"
echo "     For each (producer, consumer) where producer != consumer:"
echo "       consumer DEPENDS ON producer  (logical dependency)"
echo ""
echo "   Example:"
echo "     P1-4 creates \"GET /playback\", P1-6 consumes \"GET /playback\""
echo "     -> P1-6 logically depends on P1-4"
echo ""

echo "   ============================================================"
echo "   LAYER 2 — MECHANICAL constraints (same file = CANNOT parallel)"
echo "   ============================================================"
echo ""
echo "   *** IRON RULE: Two agents MUST NOT edit the SAME FILE simultaneously. ***"
echo "   Even if they touch different lines/functions, parallel edits on the"
echo "   same file WILL cause git conflicts or overwrite each other's changes."
echo ""
echo "   Build a file->phases map from the plan:"
echo "     file_map[path] = [phase_ids that list this file]"
echo ""
echo "   For each file touched by >1 phase:"
echo "     These phases CONFLICT mechanically."
echo "     They must be SEQUENCED (one after another)."
echo "     Order: P0 before P1, then by phase ID."
echo ""
echo "   Example:"
echo "     config.py:      [P0-1, P0-2, P1-5]  -> P0-1 before P0-2 before P1-5"
echo "     coordinator.py: [P0-1, P0-2]         -> P0-1 before P0-2"
echo "     gateway.py:     [P1-5]               -> no conflict (only 1 phase)"
echo "     App.tsx:        [P1-6]               -> no conflict"
echo ""
echo "   This is a MECHANICAL constraint (git safety), completely separate"
echo "   from LOGICAL dependencies (creates->consumes). Both cause sequencing."
echo ""

echo "   ============================================================"
echo "   COMBINED DAG — merge both layers"
echo "   ============================================================"
echo ""
echo "   For each phase, its FULL dependency list ="
echo "     (logical deps from Layer 1) UNION (mechanical deps from Layer 2)"
echo ""
echo "   Print the combined DAG:"
echo ""
echo "     Phase     | Prio | Logical Deps    | File Conflicts      | FULL Deps"
echo "     ----------|------|-----------------|---------------------|----------"
echo "     P0-1: ... | P0   | (none)          | (none)              | (none)"
echo "     P0-2: ... | P0   | (none)          | P0-1(config.py)     | P0-1"
echo "     P0-3: ... | P0   | (none)          | (none)              | (none)"
echo "     P1-4: ... | P1   | (none)          | (none)              | (none)"
echo "     P1-5: ... | P1   | (none)          | P0-2(config.py)     | P0-2"
echo "     P1-6: ... | P1   | P1-4(/playback) | (none)              | P1-4"
echo "     P1-7: ... | P1   | (none)          | (none)              | (none)"
echo "     P1-8: ... | P1   | (none)          | (none)              | (none)"
echo ""

# ═══════════════════════════════════════════════════════════════
# DAG DISPATCH — WAVE BY WAVE
# ═══════════════════════════════════════════════════════════════
echo "DAG DISPATCH — Wave-by-wave across conversational turns"
echo ""
echo "   MECHANISM: You do NOT have a while-loop. Dispatch in WAVES."
echo "   Each wave = one conversational response with parallel Agent calls."
echo "   Track DAG state in a mental table. Update after each wave."
echo ""

echo "   -----------------------------------------------------------"
echo "   WAVE 1 — Dispatch all phases with EMPTY full-deps list"
echo "   -----------------------------------------------------------"
echo ""
echo "   1. Find ALL phases where FULL Deps = (none)."
echo "      These are independent — they can all run immediately."
echo ""
echo "   2. *** ALSO check: do any of these phases share a file? ***"
echo "      If Wave 1 candidates share a file, only dispatch the"
echo "      highest-priority one. The rest must wait for next wave."
echo ""
echo "   3. If multiple ready (no shared files), dispatch in priority"
echo "      order (P0 first). All in ONE message (parallel Agent calls)."
echo ""
echo "   4. Wait for ALL to report back. Update DAG table."
echo ""

echo "   -----------------------------------------------------------"
echo "   WAVE 2, 3, ... — Resolve and dispatch newly unblocked"
echo "   -----------------------------------------------------------"
echo ""
echo "   5. Re-evaluate: which pending phases have ALL deps satisfied?"
echo "      AND do not share files with any other ready phase?"
echo "      -> Those are READY. Dispatch in parallel."
echo "      -> Phases with a FAILED dependency -> SKIPPED (cascade)."
echo ""
echo "   6. Repeat until no phases remain pending or in_progress."
echo ""

echo "   -----------------------------------------------------------"
echo "   FAILURE — uniform rule, priority only affects PR decision"
echo "   -----------------------------------------------------------"
echo ""
echo "   When ANY phase fails (regardless of P0 or P1):"
echo "     -> Mark it 'failed'. Its dependents cascade to 'skipped'."
echo "     -> Phases that do NOT depend on it CONTINUE normally."
echo ""
echo "   Priority (P0/P1) only differs at PR time:"
echo "     -> Any P0 failed -> NO PR (critical path broken)."
echo "     -> Only P1 failed -> CREATE PR with failures noted."
echo ""

echo "   -----------------------------------------------------------"
echo "   CONCRETE EXAMPLE (from today's 8-phase plan)"
echo "   -----------------------------------------------------------"
echo ""
echo "   File overlap analysis:"
echo "     config.py:      P0-1, P0-2, P1-5, P0-3  -> 4 phases share it!"
echo "     coordinator.py: P0-1, P0-2               -> 2 phases share it"
echo "     gateway.py:     P1-5                      -> 1 phase, no conflict"
echo "     main.py:        P0-2, P1-4, P1-5          -> 3 phases share it!"
echo "     worm_blackbox:  P0-2, P1-4                -> 2 phases share it"
echo "     test_survival:  P0-1, P0-2                -> 2 phases share it"
echo "     test_vda5050:   P1-4, P1-5                -> 2 phases share it"
echo "     docker-compose: P0-3                      -> 1 phase, no conflict"
echo "     Dockerfile:     P0-3                      -> 1 phase, no conflict"
echo "     dashboard/*:    P1-6                      -> 1 phase, no conflict"
echo "     monitoring/*:   P1-7                      -> 1 phase, no conflict"
echo "     simulator/*:    P1-8                      -> 1 phase, no conflict"
echo ""
echo "   Creates->Consumes analysis:"
echo "     P1-6 consumes GET /playback -> P1-4 creates GET /playback"
echo "     -> P1-6 logically depends on P1-4"
echo ""
echo "   Combined DAG (both layers):"
echo "     P0-1: file-conflict with P0-2,P1-5,P0-3 on config.py + P0-2 on coordinator.py + P0-2 on test_survival"
echo "           -> P0-2,P1-5,P0-3 must wait (but P0-1 is P0, goes first on config.py)"
echo "     P0-2: waits for P0-1 (config.py, coordinator.py, test_survival)"
echo "     P0-3: waits for P0-1 (config.py); waits for P0-2 (config.py)"
echo "           Also: P0-3 touches config.py, P0-1 and P0-2 do too"
echo "     P1-4: waits for P0-2 (main.py, worm_blackbox); waits for P1-5 (main.py share? no, P1-5 touches main.py too)"
echo "           Actually P1-4 and P1-5 both touch main.py and test_vda5050"
echo "     P1-5: waits for P0-2 (main.py); waits for P0-1,P0-2 (config.py)"
echo "     P1-6: waits for P1-4 (logical dep: /playback endpoint)"
echo "     P1-7: no conflicts, no logical deps -> Wave 1 candidate"
echo "     P1-8: no conflicts, no logical deps -> Wave 1 candidate"
echo ""
echo "   Wave dispatch:"
echo "     Wave 1: P0-1 + P1-7 + P1-8  (P0-1 goes first on config.py; P0-2, P0-3, P1-5 blocked by file conflict on config.py; P1-4 blocked by file conflict on main.py with P0-2)"
echo "     Wave 2: P0-2 + P1-4 + P1-6(?)  (P0-2 unblocked after P0-1; P1-4: does P1-4 share files with P0-2? Yes, main.py + worm_blackbox. P1-4 waits. P1-6: logical dep on P1-4, still blocked)"
echo "             Actually: P0-2 conflicts with P1-4 on main.py -> only P0-2 runs"
echo "     Wave 3: P0-3 + P1-4 + P1-5  (P0-3 waits for P0-2 on config.py; P1-4 waits for P0-2 on main.py; P1-5 waits for P0-2 on config.py+main.py. But P0-3, P1-4, P1-5 all share? Check: P0-3 vs P1-4: no shared files. P0-3 vs P1-5: config.py! So P0-3 and P1-5 can't both run. P1-4 vs P1-5: main.py + test_vda5050! Can't both run.)"
echo "             -> Only P0-3 runs (highest priority on config.py). P1-4 and P1-5 also blocked by each other."
echo "     Wave 4: P1-4 + P1-5? No, still share main.py + test_vda5050. P1-4 (lower ID) runs first."
echo "     Wave 5: P1-5"
echo "     Wave 6: P1-6 (logical dep on P1-4 satisfied)"
echo ""
echo "   -> 8 phases complete in 6 waves."
echo "   -> Key bottleneck: config.py (4 phases) and main.py (3 phases)."
echo ""

echo "   -----------------------------------------------------------"
echo "   AGENT PROMPT (identical for every phase, every wave)"
echo "   -----------------------------------------------------------"
echo ""
echo "     subagent_type: \"general-purpose\""
echo "     description: \"<Phase ID> [<P0|P1>]: <title>\""
echo "     prompt: |"
echo "       Implement one phase from the plan at: ${PLAN_FILE}"
echo "       Project root: ${PROJECT_ROOT}"
echo "       Your phase: <Phase ID> [Priority: <P0|P1>] - <Title>"
echo ""
echo "       1. Read YOUR phase section from the plan."
echo "       2. Read EVERY file listed BEFORE editing."
echo "       3. Make ALL changes described. Match existing code style."
echo "       4. Run the verification command. Fix until green."
echo "       5. Report: SUCCESS + output, or FAILURE + errors."
echo "          List every file you modified."
echo ""

# ═══════════════════════════════════════════════════════════════
# GIT + PR
# ═══════════════════════════════════════════════════════════════
echo ""
echo "==========================================================="
echo "  GIT + PR WORKFLOW"
echo "==========================================================="
echo ""
echo "After all waves complete (all phases resolved)."
echo ""
echo "  1. cd ${PROJECT_ROOT}"
echo "  2. git status"
echo "  3. git add .           # (branch created in STEP -1)"
echo "  4. git commit -m \"feat: auto-implemented ($(date +%Y%m%d))"
echo ""
echo "     <per-phase: [PASS|FAIL|SKIP] <id> [<P0|P1>]: <title>>\""
echo ""
echo "  5. git push -u origin ${BRANCH_NAME}"
echo ""
echo "  6. PR DECISION (based on priority, NOT dependency):"
echo "     -> Any P0 phase failed? -> STOP. Do NOT create PR."
echo "     -> Only P1 failed (or all pass)? -> Create PR:"
echo ""
echo "     gh pr create \\"
echo "       --title \"feat: auto-implemented ($(date +%Y%m%d))\" \\"
echo "       --body \"Generated with Claude Code auto-implement-and-pr.sh v5.1"
echo ""
echo "  Plan: ${PLAN_FILE}"
echo "  Branch: ${BRANCH_NAME}"
echo "  Waves: <N> waves"
echo "  Constraints: logical (creates->consumes) + mechanical (file overlap)"
echo ""
echo "  Results:"
echo "  <per-phase: [PASS|FAIL|SKIP] <id> [<P0|P1>]: <title>>"
echo ""
echo "  Summary: <N> succeeded, <M> failed, <K> skipped\""
echo "  7. Output the PR URL"
echo ""

echo "=============================================="
echo " auto-implement-and-pr.sh v5.1 — END"
echo "=============================================="
