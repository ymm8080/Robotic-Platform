#!/usr/bin/env bash
# ============================================================================
# auto-plan-implement-and-pr.sh — v6.2 (chain-collapse)
#
# Reads design docs, generates plan, pre-computes DAG, COLLAPSES logically-
# dependent phases into chains (one agent, one branch, one PR). Dispatches
# chains via Claude Code native Agent(run_in_background=true).
# <task-notification> triggers each turn. No incremental merge latency.
#
# USAGE: cat auto-plan-implement-and-pr.sh | claude
# ============================================================================

EXTERNAL_DESIGN_DIR="d:/ewm robot/reference/design all"
IMPL_PLAN_DIR="${EXTERNAL_DESIGN_DIR}/implementation plan"
PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"
TODAY_DATE=$(date +%Y%m%d 2>/dev/null || echo 'TODAY')
PLAN_FILE=$(ls -t "${IMPL_PLAN_DIR}"/*${TODAY_DATE}*.* 2>/dev/null | head -1)
[ -z "${PLAN_FILE}" ] && PLAN_FILE="${IMPL_PLAN_DIR}/IMPLEMENTATION_PLAN_${TODAY_DATE}.md"
BRANCH="feat/auto-impl-$(date +%Y%m%d-%H%M%S 2>/dev/null || echo 'snapshot')"
MAX_RUNTIME=1800  # 30 minutes per chain before timeout
SAFETY_WAKEUP=300 # 5 minutes — if no notification, wake up and check

echo "=== auto-plan-implement-and-pr v6.2 (chain-collapse) ==="
echo "Design: ${EXTERNAL_DESIGN_DIR}"
echo "Plan:   ${PLAN_FILE}"
echo "Branch: ${BRANCH}"
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 1 — GENERATE PLAN
# ═══════════════════════════════════════════════════════════════

echo "=== STAGE 1: GENERATE PLAN ==="
echo ""

echo "1.1 Read design docs:"
echo "    Glob + Read all .md in:"
echo "      ${IMPL_PLAN_DIR}/"
echo "      ${EXTERNAL_DESIGN_DIR}/Design - Core/"
echo "    Key: 异构机器人融合平台_v5.0_完整堡垒版.md, 01_架构白皮书, 02_Function_Spec, 03_Runbook"
echo ""

echo "1.2 Explore codebase:"
echo "    Glob ${PROJECT_ROOT}"
echo "    Read: core/config.py, core/coordinator.py, core/gateway.py,"
echo "    core/survival/worm_blackbox.py, core/survival/version_router.py,"
echo "    traffic_coordinator_v5/traffic_coordinator_main.py,"
echo "    traffic_coordinator_v5/simulator/cli.py, fleet.py,"
echo "    docker-compose-v5.yml, dashboard/src/, monitoring/"
echo ""

echo "1.3 Derive phases (dynamic count, not fixed):"
echo ""
echo "    For each candidate phase, determine:"
echo "      CREATES  — new functions, endpoints, config keys, classes, files"
echo "      CONSUMES — functions, endpoints, config, imports it uses"
echo "      FILES    — every file this phase will EDIT (be exhaustive)"
echo ""
echo "    *** Phases sharing files cannot run in parallel. ***"
echo "    *** Logically dependent phases will be COLLAPSED into one chain. ***"
echo "    If many phases chain together, keep each phase focused."
echo ""

echo "1.4 Write plan to ${PLAN_FILE}:"
echo ""
echo "    ## 1. CURRENT BASELINE"
echo ""
echo "    ## 2. IMPLEMENTATION PHASES"
echo "      For each phase:"
echo ""
echo "      ### <Phase ID>: <Title>"
echo "      **Priority:** P0 | P1"
echo "        P0 = critical (blocks PR on failure, wins tie-break)"
echo "        P1 = normal   (noted in PR on failure, loses tie-break)"
echo ""
echo "      **Creates:**"
echo "        - \`func()\` in \`module.py\` — new method"
echo "        - \`GET /api/x\` in \`main.py\` — new endpoint"
echo "        - \`Class.field\` in \`config.py\` — new config"
echo ""
echo "      **Consumes:**"
echo "        - \`existing_func()\` from \`module.py\`"
echo "        - \`GET /api/existing\`"
echo ""
echo "      **Files:**"
echo "        - \`path/to/file\` — what to change"
echo "        EVERY file touched. Determines file conflicts."
echo ""
echo "      **Changes:**"
echo "        - Specific implementation details"
echo ""
echo "      **Verify:** \`exact command\`"
echo ""
echo "      *** NO Depends on: field. Dependencies auto-detected. ***"
echo "      *** Dependent phases auto-collapsed into one chain. ***"
echo ""
echo "    ## 3. CREATES/CONSUMES CROSS-REFERENCE"
echo "    ## 4. FILE CONTENTION MAP"
echo "    ## 5. VERIFICATION CRITERIA"
echo "    ## 6. FILE CHANGE MATRIX"
echo "    ## 7. OUT OF SCOPE"
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 1.5 — PRE-COMPUTE + COLLAPSE CHAINS
# ═══════════════════════════════════════════════════════════════

echo "=== STAGE 1.5: PRE-COMPUTE + COLLAPSE CHAINS ==="
echo ""

echo "1.5a Create shared integration branch:"
echo "     cd ${PROJECT_ROOT}"
echo "     git checkout main && git pull"
echo "     git checkout -b ${BRANCH}"
echo "     git push -u origin ${BRANCH}"
echo ""

echo "1.5b Compute logical deps (creates -> consumes):"
echo ""
echo "     creates_map[key] = [producers]"
echo "     consumes_map[key] = [consumers]"
echo "     match where producer != consumer: consumer.logical_deps += producer"
echo ""

echo "1.5c COLLAPSE logical dependency chains:"
echo ""
echo "     If B depends on A, B needs A's code. Separate agents would"
echo "     require A's PR to merge before B starts — slow. Instead,"
echo "     collapse A->B into ONE chain, ONE agent, ONE branch, ONE PR."
echo ""
echo "     ALGORITHM:"
echo "       Walk phases in topological order. For each unvisited phase,"
echo "       follow its single-dependent chain as long as the dependent"
echo "       ONLY depends on the current phase. Build chain: [A, B, ...]."
echo ""
echo "     Example:"
echo "       P1-4 creates /playback, P1-6 consumes /playback -> collapse"
echo "       Chains: C1:[P0-1], C2:[P0-2], C3:[P0-3], C4:[P1-4,P1-6],"
echo "               C5:[P1-5], C6:[P1-7], C7:[P1-8]"
echo "       8 phases -> 7 chains -> 7 agents -> 7 PRs"
echo ""

echo "1.5d Compute chain-level file conflicts:"
echo ""
echo "     chain_files = union of all phase files in chain"
echo "     chain_conflicts: chains sharing files -> must sequence"
echo ""

echo "1.5e Create Task items (one per CHAIN):"
echo "     for each chain:"
echo "       TaskCreate("
echo "         subject: \"[<prio>] <chain-id>: <titles>\""
echo "         metadata: {"
echo "           chain_id, phases: [...], priority,"
echo "           files: union(all phase files),"
echo "           chain_conflicts: [...],"
echo "           verify_all: [per-phase verify]"
echo "         }"
echo "       )"
echo ""

echo "1.5f ready() — simplified (no logical deps):"
echo ""
echo "     def ready(chain):"
echo "       # Chains have no logical deps (already collapsed into agent)"
echo "       # Only file conflicts with RUNNING chains block dispatch"
echo "       for conflict in chain.chain_conflicts:"
echo "         if conflict in running: return False"
echo "       return True"
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 2 — DISPATCH LOOP
# ═══════════════════════════════════════════════════════════════

echo "=== STAGE 2: DISPATCH LOOP ==="
echo ""

echo "    TURN 0 — initial dispatch:"
echo ""
echo "      ready_chains = [c for c in chains if ready(c)]"
echo "      to_fire = resolve_mutual_file_conflicts(ready_chains)"
echo ""
echo "      for chain in to_fire:"
echo "        TaskUpdate(task_id, status='in_progress',"
echo "          metadata: { started_at: current_timestamp() })"
echo "        Agent("
echo "          subagent_type: \"general-purpose\""
echo "          description: \"<chain-id> [P0|P1]: <titles>\""
echo "          run_in_background: true"
echo "          prompt: CHAIN_AGENT_PROMPT(chain)"
echo "        )"
echo "      END TURN"
echo ""

echo "    TURN 1+ — triggered by <task-notification>:"
echo ""

echo "      # A. UPDATE STATUS (no auto-merge)"
echo "      for chain in in_progress:"
echo "        r = TaskOutput(chain.agent_task_id, block=false)"
echo "        if r.done and r.success:"
echo "          TaskUpdate(task_id, status='completed')"
echo "          # PR created by agent. Manual merge required — no auto-merge."
echo "        elif r.done and not r.success:"
echo "          TaskUpdate(task_id, status='failed')"
echo "          gh pr close feat/<chain-id> 2>/dev/null"
echo ""

echo "      # A2. TIMEOUT CHECK — hung agents"
echo "      now = current_timestamp()"
echo "      for chain in in_progress:"
echo "        elapsed = now - chain.started_at"
echo "        if elapsed > \${MAX_RUNTIME}:"
echo "          TaskStop(chain.agent_task_id)"
echo "          TaskUpdate(task_id, status='timeout',"
echo "            reason: \"exceeded \${MAX_RUNTIME}s (ran \${elapsed}s)\")"
echo "          gh pr close feat/<chain-id>-<slug> 2>/dev/null"
echo ""

echo "      # B. CHECK DONE"
echo "      if no pending and no in_progress: -> GOTO STAGE 3"
echo ""

echo "      # C. DISPATCH NEWLY READY"
echo "      ready_chains = [c for c in pending if ready(c)]"
echo "      to_fire = resolve_mutual_file_conflicts(ready_chains)"
echo "      if to_fire:"
echo "        for chain in to_fire:"
echo "          TaskUpdate(task_id, status='in_progress',"
echo "            metadata: { started_at: current_timestamp() })"
echo "          Agent(subagent_type: \"general-purpose\","
echo "            description: \"<chain-id> [P0|P1]: <titles>\","
echo "            run_in_background: true,"
echo "            prompt: CHAIN_AGENT_PROMPT(chain))"
echo "        END TURN"
echo "      elif in_progress:"
echo "        Report: '<N> running, <M> pending. Timeout: \${MAX_RUNTIME}s per chain.'"
echo "        ScheduleWakeup(delaySeconds=\${SAFETY_WAKEUP},"
echo "          reason=\"hung-agent check: \${in_progress_count} chains running\")"
echo "        END TURN"
echo "      else: -> GOTO STAGE 3"
echo ""

# ═══════════════════════════════════════════════════════════════
# STAGE 3 — FINAL PR TO MAIN
# ═══════════════════════════════════════════════════════════════

echo "=== STAGE 3: FINAL PR TO MAIN ==="
echo ""

echo "    cd ${PROJECT_ROOT}"
echo "    git checkout ${BRANCH} && git pull"
echo ""

echo "    if any(chain.priority == 'P0' and chain.status == 'failed'):"
echo "      -> STOP. P0 chain failed. Report and exit."
echo ""

echo "    gh pr create --base main --head ${BRANCH} \\"
echo "      --title \"feat: auto-implemented ($(date +%Y%m%d))\" \\"
echo "      --body \"Plan: ${PLAN_FILE} | ${N} chains, ${M} phases | v6.2\""
echo ""

# ═══════════════════════════════════════════════════════════════
# CHAIN AGENT PROMPT
# ═══════════════════════════════════════════════════════════════

echo "==========================================================="
echo "  CHAIN AGENT PROMPT"
echo "==========================================================="
echo ""

echo "    subagent_type: \"general-purpose\""
echo "    description: \"<chain-id> [<P0|P1>]: <titles>\""
echo "    run_in_background: true"
echo ""

echo "    prompt:"
echo "      Implement ${N} phases IN SEQUENCE from: ${PLAN_FILE}"
echo "      Project root: ${PROJECT_ROOT}"
echo "      Shared base: ${BRANCH}"
echo "      Your chain: <phase1> -> <phase2> -> ..."
echo ""

echo "      STEPS:"
echo "      1. git fetch origin"
echo "         git checkout -b feat/<chain-id>-<slug> origin/${BRANCH}"
echo ""

echo "      2. FOR EACH phase in chain (in dependency order):"
echo "         a. Read the phase section from the plan"
echo "         b. Read EVERY file listed in **Files:** BEFORE editing"
echo "         c. Make ALL changes in **Changes:**"
echo "            Match existing code style, comments, naming"
echo "         d. Run: <verify command>. Fix until green."
echo "         e. git add ."
echo "            git commit -m \"feat(<phase-id>): <title>"
echo ""
echo "            Co-Authored-By: Claude Code <noreply@anthropic.com>\""
echo "         f. If any phase FAILS: stop chain. Report FAILURE."
echo ""

echo "      3. git push -u origin feat/<chain-id>-<slug>"
echo ""

echo "      4. gh pr create \\"
echo "         --base ${BRANCH} --head feat/<chain-id>-<slug> \\"
echo "         --title \"feat(<chain-id>): <titles>\" \\"
echo "         --body \"Chain: <phase-list>"
echo "         Plan: ${PLAN_FILE}"
echo "         Phases implemented sequentially in one branch.\""
echo ""

echo "      5. Report EXACTLY:"
echo "         STATUS: SUCCESS | FAILURE"
echo "         BRANCH: feat/<chain-id>-<slug>"
echo "         PR: <pr-url>"
echo "         PHASES:"
echo "           - <phase-id>: PASS|FAIL"
echo "         FILES:"
echo "           - <absolute-path>"
echo ""

echo "=== auto-plan-implement-and-pr v6.2 END ==="
