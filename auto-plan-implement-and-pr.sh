#!/usr/bin/env bash
# ============================================================================
# auto-plan-implement-and-pr.sh — v5.3 (native task system + background dispatch)
# Claude Code instruction document: reads design docs, generates a plan,
# auto-detects constraints, dispatches via Claude Code's NATIVE Agent/Task system.
#
# USAGE:  cat auto-plan-implement-and-pr.sh | claude
# ============================================================================

# ======================= Configuration =======================
EXTERNAL_DESIGN_DIR="d:/ewm robot/reference/design all"
IMPL_PLAN_DIR="${EXTERNAL_DESIGN_DIR}/implementation plan"
PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"
TODAY_DATE=$(date +%Y%m%d 2>/dev/null || echo 'TODAY')
PLAN_FILE=$(ls -t "${IMPL_PLAN_DIR}"/*${TODAY_DATE}*.* 2>/dev/null | head -1)
if [ -z "${PLAN_FILE}" ]; then
  PLAN_FILE="${IMPL_PLAN_DIR}/IMPLEMENTATION_PLAN_${TODAY_DATE}.md"
fi
BRANCH_NAME="feat/auto-impl-$(date +%Y%m%d-%H%M%S 2>/dev/null || echo 'snapshot')"
# ============================================================

echo "=============================================="
echo " auto-plan-implement-and-pr.sh v5.3"
echo " Design dir : ${EXTERNAL_DESIGN_DIR}"
echo " Plan file  : ${PLAN_FILE}"
echo "=============================================="
echo ""

# ╔══════════════════════════════════════════════════════════════╗
# ║  ARCHITECTURE — What Claude Code provides vs what we build ║
# ╚══════════════════════════════════════════════════════════════╝
#
# NATIVE (Claude Code handles automatically):
#   Agent(run_in_background=true) — async subagent, returns task_id
#   <task-notification> — auto-delivered when agent completes. THE trigger.
#   TaskOutput(task_id, block=false) — non-blocking completion check
#   TaskCreate/TaskUpdate/TaskList — state tracker for phases
#   ScheduleWakeup(delaySeconds) — safety net for hung agents
#
# WE BUILD (orchestration on top):
#   1. Parse plan -> extract creates, consumes, files per phase
#   2. Match creates->consumes -> logical dependencies
#   3. Build file->phases map -> mechanical constraints
#   4. TaskCreate each phase with constraint metadata
#   5. Ready-check at each notification: logical deps done + no file overlap
#   6. Dispatch ready phases via Agent(run_in_background=true)

echo "=== STAGE 1/3: ANALYSIS & PLAN GENERATION ==="
echo ""

echo "STEP 1A — Read external design documents"
echo ""
echo "   Glob + Read all .md in:"
echo "     - ${IMPL_PLAN_DIR}/"
echo "     - ${EXTERNAL_DESIGN_DIR}/Design - Core/"
echo "   Find plan file with today's date (${TODAY_DATE})."
echo ""

echo "STEP 1B — Explore current codebase"
echo ""
echo "   Glob ${PROJECT_ROOT}. Read key files:"
echo "     core/config.py, core/coordinator.py, core/gateway.py,"
echo "     core/survival/worm_blackbox.py, core/survival/version_router.py,"
echo "     traffic_coordinator_v5/traffic_coordinator_main.py,"
echo "     traffic_coordinator_v5/simulator/cli.py,"
echo "     traffic_coordinator_v5/simulator/fleet.py,"
echo "     docker-compose-v5.yml,"
echo "     core/tests/test_platform_adapter_survival.py,"
echo "     core/tests/test_vda5050_adapters.py,"
echo "     dashboard/src/, monitoring/"
echo ""

echo "STEP 1C — Analyze program logic + file overlap"
echo ""
echo "   For each candidate phase, answer 4 questions:"
echo ""
echo "   Q1: CREATES — what new artifacts does this phase PRODUCE?"
echo "       Functions, classes, endpoints, config keys, files, CLI flags"
echo ""
echo "   Q2: CONSUMES — what artifacts does this phase USE?"
echo "       Imports, function calls, API calls, config reads"
echo "       Both existing AND to-be-created by other phases"
echo ""
echo "   Q3: FILES — which files does this phase EDIT?"
echo "       *** CRITICAL: same file = cannot run in parallel ***"
echo "       High contention -> consider splitting or merging phases"
echo ""
echo "   Q4: Does another phase CONSUME what THIS phase CREATES?"
echo "       If yes -> that phase has a logical dependency on this one"
echo ""

echo "STEP 1D — Write plan to ${PLAN_FILE}"
echo ""
echo "   DERIVE phases from design docs. Do NOT use a fixed list."
echo ""
echo "   Phase template (EXACT format):"
echo ""
echo "     ### <Phase ID>: <Title>"
echo ""
echo "     **Priority:** P0 | P1"
echo "       P0 = critical (blocks PR on failure, wins tie-break)"
echo "       P1 = normal   (noted in PR on failure, loses tie-break)"
echo ""
echo "     **Creates:**"
echo "       - \`func_name()\` in \`module.py\` — new method"
echo "       - \`GET /api/endpoint\` in \`main.py\` — new route"
echo "       - \`ClassName.field\` in \`config.py\` — new field"
echo ""
echo "     **Consumes:**"
echo "       - \`existing_func()\` from \`module.py\` — existing code"
echo "       - \`GET /api/existing\` — existing endpoint"
echo ""
echo "     **Files:**"
echo "       - \`path/to/file\` — what to change"
echo "       Be EXHAUSTIVE. Phases sharing files CANNOT run in parallel."
echo ""
echo "     **Changes:**"
echo "       - Specific implementation details"
echo ""
echo "     **Verify:** \`exact command to run\`"
echo ""
echo "     *** DO NOT add **Depends on:**. Dependencies are auto-detected. ***"
echo ""
echo "   Plan sections:"
echo "     1. CURRENT BASELINE"
echo "     2. IMPLEMENTATION PHASES (one per phase, template above)"
echo "     3. CREATES/CONSUMES CROSS-REFERENCE (for review)"
echo "     4. FILE CONTENTION MAP (identifies bottlenecks)"
echo "     5. VERIFICATION CRITERIA"
echo "     6. FILE CHANGE MATRIX"
echo "     7. OUT OF SCOPE"
echo ""

echo "CREATE BRANCH BEFORE STAGE 2"
echo "   cd ${PROJECT_ROOT} && git checkout -b ${BRANCH_NAME}"
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 2 — NATIVE TASK SYSTEM + BACKGROUND DISPATCH
# ═══════════════════════════════════════════════════════════════
echo "==========================================================="
echo "  STAGE 2/3: CONSTRAINT DETECTION + DISPATCH"
echo "==========================================================="
echo ""

echo "STEP 2A — Auto-detect constraints"
echo ""
echo "   LAYER 1 — LOGICAL (creates -> consumes):"
echo "     Build creates_map[artifact_key] and consumes_map[artifact_key]."
echo "     Match: consumer.logical_deps += producer for each match."
echo "     Key format: \"module.py::func()\", \"GET /api/path\", \"Class.field\""
echo ""
echo "   LAYER 2 — MECHANICAL (file overlap):"
echo "     Build file_map[path] = [phase_ids]."
echo "     >1 phase per file = mechanical conflict = must sequence."
echo "     Order: P0 before P1, then by ID."
echo ""

echo "STEP 2B — Create Task items (Claude Code native Task system)"
echo ""
echo "   TaskCreate for EACH phase:"
echo ""
echo "     TaskCreate("
echo "       subject: \"[P0|P1] <Phase ID>: <Title>\""
echo "       description: \"Files: <list> | Verify: <cmd>\""
echo "       metadata: {"
echo "         phase_id, priority, files: [...],"
echo "         logical_deps: [...], mechanical_deps: [...]"
echo "       }"
echo "     )"
echo ""
echo "   Why native Task system:"
echo "     - TaskList shows all phases + status at a glance"
echo "     - TaskGet fetches full metadata (deps, files) for ready-check"
echo "     - TaskUpdate marks completions/failures/skips"
echo "     - No separate mental table to maintain across turns"
echo ""

echo "STEP 2C — Dispatch loop (notification-driven)"
echo ""
echo "   HOW TURNS WORK:"
echo "     Claude Code's native background-task lifecycle:"
echo "       1. Agent(run_in_background=true) -> returns task_id -> agent runs"
echo "       2. Orchestrator ends turn (no block)"
echo "       3. Agent completes -> <task-notification> arrives"
echo "       4. Claude Code auto-resumes -> orchestrator re-evaluates"
echo "       5. Repeat until all phases done"
echo ""
echo "     No while-loop. No polling. No cron. The <task-notification> IS"
echo "     the trigger. Claude Code wakes itself up when work finishes."
echo ""

echo "   TURN 0 (initial dispatch):"
echo ""
echo "   ready = (logical_deps empty) AND (no mutual file conflict among ready)"
echo "   Dispatch ready phases: Agent(run_in_background=true). End turn."
echo ""

echo "   TURN 1+ (notification received):"
echo ""
echo "   1. TaskOutput(task_id, block=false) -> completed or failed?"
echo "      -> TaskUpdate status accordingly"
echo "      -> If failed: TaskUpdate status='skipped' for logical dependents"
echo ""
echo "   2. Re-evaluate: for each 'pending' phase:"
echo "      ready = ("
echo "        all(logical_deps are 'completed')"
echo "        AND"
echo "        no_overlap(this.files, files_of(all 'in_progress' phases))"
echo "      )"
echo ""
echo "   3. Among newly-ready: check mutual file overlap."
echo "      Only dispatch one per conflicting file group."
echo ""
echo "   4. Dispatch: Agent(run_in_background=true). TaskUpdate 'in_progress'."
echo "      End turn."
echo ""
echo "   5. Nothing ready + agents running -> end turn, wait for next notification."
echo "      Safety: ScheduleWakeup(delaySeconds=300) in case notification lost."
echo ""
echo "   6. STOP: TaskList shows no 'pending' + no 'in_progress'."
echo ""

echo "   EXAMPLE (8-phase plan):"
echo ""
echo "     Turn 0: P0-1 + P1-4 + P1-7 + P1-8 dispatch bg"
echo "     Turn 1: <notification P1-7> P0-1,P1-4 running. P0-2 blocked (P0-1 files). Nothing ready."
echo "     Turn 2: <notification P0-1> P1-4,P1-8 running. P0-3 ready (no overlap P1-4). Dispatch P0-3."
echo "     Turn 3: ...etc..."
echo "     -> 8 phases complete. Notification-driven, no idle waiting."
echo ""

echo "   FAILURE:"
echo "     Failed phase -> logical dependents cascade-skip."
echo "     Mechanical-only dependents proceed (file lock released)."
echo "     Priority only affects PR decision."
echo ""

echo "   STANDARD AGENT PROMPT:"
echo ""
echo "     subagent_type: \"general-purpose\""
echo "     description: \"<Phase ID> [<P0|P1>]: <Title>\""
echo "     run_in_background: true"
echo "     prompt: |"
echo "       Implement one phase from the plan at: ${PLAN_FILE}"
echo "       Project root: ${PROJECT_ROOT}"
echo "       Your phase: <Phase ID> [Priority: <P0|P1>] - <Title>"
echo "       1. Read YOUR phase from the plan."
echo "       2. Read EVERY file listed BEFORE editing."
echo "       3. Make ALL changes. Match existing code style."
echo "       4. Run verify. Fix until green."
echo "       5. Report: SUCCESS + files, or FAILURE + errors."
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 3 — GIT + PR
# ═══════════════════════════════════════════════════════════════
echo "==========================================================="
echo "  STAGE 3/3: GIT + PR"
echo "==========================================================="
echo ""
echo "After TaskList: no pending, no in_progress:"
echo ""
echo "  1. git status && git add . && git commit"
echo "  2. git push -u origin ${BRANCH_NAME}"
echo "  3. PR: any P0 failed? -> STOP. Otherwise -> gh pr create"
echo ""

echo "=============================================="
echo " auto-plan-implement-and-pr.sh v5.3 — END"
echo "=============================================="
