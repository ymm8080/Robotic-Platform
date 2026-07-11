#!/usr/bin/env bash
# ============================================================================
# auto-implement-and-pr.sh — v6.0 (native dispatch)
#
# Leverages Claude Code's native Agent/Task/<task-notification> lifecycle.
# Orchestrator only does: (1) parse plan, (2) pre-compute DAG, (3) fire
# ready phases each turn. Everything else is native.
#
# USAGE: cat auto-implement-and-pr.sh | claude
# ============================================================================

IMPL_PLAN_DIR="d:/ewm robot/reference/design all/implementation plan"
PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"
TODAY_DATE=$(date +%Y%m%d 2>/dev/null || echo 'TODAY')
PLAN_FILE=$(ls -t "${IMPL_PLAN_DIR}"/*${TODAY_DATE}*.* 2>/dev/null | head -1)
[ -z "${PLAN_FILE}" ] && echo "ERROR: No plan found for ${TODAY_DATE}" && exit 1
BRANCH_NAME="feat/auto-impl-$(date +%Y%m%d-%H%M%S 2>/dev/null || echo 'snapshot')"

echo "=== auto-implement-and-pr v6.0 ==="
echo "Plan: ${PLAN_FILE}"
echo ""

# ═══════════════════════════════════════════════════════════════
# PHASE 0: SETUP (one-time, before any agent)
# ═══════════════════════════════════════════════════════════════

echo "PHASE 0 — SETUP"
echo ""
echo "0.1 Create branch:"
echo "    cd ${PROJECT_ROOT} && git checkout -b ${BRANCH_NAME}"
echo ""

echo "0.2 Read plan and pre-compute DAG:"
echo ""
echo "    For each phase in ${PLAN_FILE}, extract:"
echo "      id, priority(P0|P1), title, creates[], consumes[], files[], verify"
echo ""
echo "    Build constraint maps:"
echo ""
echo "      // Logical: match creates -> consumes"
echo "      creates_map[key] = [producer_phase_ids]"
echo "      consumes_map[key] = [consumer_phase_ids]"
echo "      logical_deps[consumer] += producer  (for each match)"
echo ""
echo "      // Mechanical: same file -> cannot run simultaneously"
echo "      file_map[path] = [phase_ids]"
echo "      file_conflicts[phase] = [other phases touching same files]"
echo ""

echo "0.3 Create native Task items for ALL phases:"
echo ""
echo "    for each phase:"
echo "      TaskCreate("
echo "        subject: \"[P0|P1] <id>: <title>\""
echo "        metadata: {"
echo "          id, priority, files, logical_deps, verify"
echo "        }"
echo "      )"
echo ""
echo "    All phases start as 'pending'. TaskList is our dashboard."
echo ""

# ═══════════════════════════════════════════════════════════════
# PHASE 1: INITIAL DISPATCH
# ═══════════════════════════════════════════════════════════════

echo "PHASE 1 — INITIAL DISPATCH (Turn 0)"
echo ""
echo "READY CHECK (reused every turn):"
echo "  def ready(phase):"
echo "    // Condition A: all logical deps completed"
echo "    if any(dep.status != 'completed' for dep in phase.logical_deps):"
echo "      return false"
echo "    // Condition B: no file overlap with any RUNNING phase"
echo "    running = [p for p in all_phases if p.status == 'in_progress']"
echo "    if any(overlap(phase.files, r.files) for r in running):"
echo "      return false"
echo "    return true"
echo ""

echo "    Find all phases where ready() == true."
echo "    Among those, resolve mutual file conflicts:"
echo "      while ready_set has phases sharing files:"
echo "        keep highest priority (P0 > P1), then lowest ID"
echo "        defer the rest to next turn"
echo ""

echo "    Dispatch kept phases with Agent(run_in_background=true):"
echo ""
echo "      for phase in to_dispatch:"
echo "        task_id = Agent("
echo "          subagent_type: \"general-purpose\""
echo "          description: \"<id> [<P0|P1>]: <title>\""
echo "          run_in_background: true"
echo "          prompt: STANDARD_PROMPT(phase)"
echo "        )"
echo "        TaskUpdate(phase.task_id, status='in_progress',"
echo "          metadata: {agent_task_id: task_id})"
echo ""
echo "    END TURN. Do nothing else."
echo ""
echo "    ┌─────────────────────────────────────────────────────┐"
echo "    │ NATIVE TRIGGER: when ANY dispatched agent finishes, │"
echo "    │ Claude Code delivers <task-notification> and        │"
echo "    │ automatically starts the next turn.                 │"
echo "    │ No polling. No cron. No while loop.                 │"
echo "    └─────────────────────────────────────────────────────┘"
echo ""

# ═══════════════════════════════════════════════════════════════
# PHASE 2: AUTO-CONTINUE LOOP (turns 1..N)
# ═══════════════════════════════════════════════════════════════

echo "PHASE 2 — AUTO-CONTINUE (Turn 1, 2, 3, ...)"
echo ""
echo "    This phase runs automatically each time Claude Code wakes up"
echo "    from a <task-notification>. You re-enter this logic every turn."
echo ""
echo "    2.1 CHECK COMPLETION:"
echo "        for each phase where status == 'in_progress':"
echo "          result = TaskOutput(phase.agent_task_id, block=false)"
echo "          if result.done:"
echo "            if result.success:"
echo "              TaskUpdate(phase.task_id, status='completed')"
echo "            else:"
echo "              TaskUpdate(phase.task_id, status='failed')"
echo "              // cascade skip logical dependents"
echo "              for dep in get_dependents(phase):"
echo "                TaskUpdate(dep.task_id, status='skipped')"
echo ""

echo "    2.2 CHECK DONE:"
echo "        count = TaskList filter (status=pending OR status=in_progress)"
echo "        if count == 0:"
echo "          -> GOTO PHASE 3 (PR)"
echo ""

echo "    2.3 DISPATCH NEWLY READY:"
echo "        Compute ready() for all 'pending' phases."
echo "        Resolve mutual file conflicts (same as Phase 1)."
echo "        if any are ready:"
echo "          dispatch them with Agent(run_in_background=true)"
echo "          TaskUpdate -> 'in_progress'"
echo ""

echo "    2.4 END TURN:"
echo "        if (any dispatched):"
echo "          -> END TURN (wait for next <task-notification>)"
echo "        elif (any in_progress):"
echo "          -> Report: '<N> running, waiting...' END TURN"
echo "          -> Optional safety net: ScheduleWakeup(delaySeconds=120)"
echo "        else:"
echo "          -> GOTO PHASE 3 (all done)"
echo ""

# ═══════════════════════════════════════════════════════════════
# PHASE 3: PR
# ═══════════════════════════════════════════════════════════════

echo "PHASE 3 — GIT + PR"
echo ""
echo "    cd ${PROJECT_ROOT}"
echo "    git status && git add ."
echo "    git commit -m \"feat: auto-implemented ($(date +%Y%m%d))"
echo ""
echo "    <per-phase: [PASS|FAIL|SKIP] <id> [<P0|P1>]: <title>>\""
echo ""
echo "    git push -u origin ${BRANCH_NAME}"
echo ""
echo "    if any(p.status == 'failed' AND p.priority == 'P0'):"
echo "      -> STOP. No PR. Critical path broken."
echo "    else:"
echo "      -> gh pr create --title \"...\" --body \"..."
echo ""

# ═══════════════════════════════════════════════════════════════
# APPENDIX: STANDARD AGENT PROMPT
# ═══════════════════════════════════════════════════════════════

echo "==========================================================="
echo "  STANDARD AGENT PROMPT (for every phase)"
echo "==========================================================="
echo ""
echo "  subagent_type: \"general-purpose\""
echo "  description: \"<id> [<P0|P1>]: <title>\""
echo "  run_in_background: true"
echo ""
echo "  prompt:"
echo "    Implement one phase from the plan at: ${PLAN_FILE}"
echo "    Project root: ${PROJECT_ROOT}"
echo "    Your phase: <id> [<P0|P1>]: <title>"
echo ""
echo "    Steps:"
echo "    1. Read your phase section from the plan"
echo "    2. Read EVERY file listed in **Files:** BEFORE editing"
echo "    3. Make ALL changes described in **Changes:**"
echo "       Match existing code style, comments, naming conventions"
echo "    4. Run: <verify command>"
echo "       If it fails, fix and re-run until green"
echo "    5. Report exactly: SUCCESS | FAILURE"
echo "       List every file you modified with absolute paths"
echo ""

echo "=== auto-implement-and-pr v6.0 END ==="
