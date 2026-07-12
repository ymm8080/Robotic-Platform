#!/usr/bin/env pwsh
$ErrorActionPreference = "Continue"
Set-Location "d:\EWM Robot\Robotic Platform Codes"

Write-Host "=== Step 1: Checkout PR branch ==="
git checkout -f feat/p1-8-scenario-cli
git reset --hard origin/feat/p1-8-scenario-cli
Write-Host "Current branch: $(git branch --show-current)"

Write-Host "=== Step 2: Fix sap-bridge lint ==="
Set-Location "d:\EWM Robot\Robotic Platform Codes\sap-bridge"
python -m ruff check . --config ruff.toml --fix
python -m ruff check . --config ruff.toml

Set-Location "d:\EWM Robot\Robotic Platform Codes"

Write-Host "=== Step 3: Fix cli.py ==="
$cliFile = "traffic_coordinator_v5\simulator\cli.py"
$content = Get-Content $cliFile -Raw

# Add threading import
$content = $content -replace "import signal`nimport sys`nimport time", "import signal`nimport sys`nimport threading`nimport time"

# Add SimulatedRobot to imports
$content = $content -replace "from traffic_coordinator_v5\.simulator\.robot import RobotConfig`n", "from traffic_coordinator_v5.simulator.robot import RobotConfig, SimulatedRobot`n"

# Add scenario dispatch in run()
$content = $content -replace "    lane_graph = LaneGraph\.from_yaml\(args\.map\)`n    if not lane_graph\.all_lanes\(\):", "    if args.scenario:`n        return _run_scenario(args)`n`n    lane_graph = LaneGraph.from_yaml(args.map)`n    if not lane_graph.all_lanes():"

Set-Content $cliFile -Value $content -NoNewline
Write-Host "cli.py fixed"

Write-Host "=== Step 4: Fix traffic_coordinator_main.py ==="
$mainFile = "traffic_coordinator_v5\traffic_coordinator_main.py"
$content = Get-Content $mainFile -Raw

# Add import logging
$content = $content -replace "import json`nimport os", "import json`nimport logging`nimport os"

# Add _logger definition after all imports (before MODE =)
$content = $content -replace "from traffic_coordinator_v5\.maps\.loader import load_facility_map`n`nMODE", "from traffic_coordinator_v5.maps.loader import load_facility_map`n`n_logger = logging.getLogger(__name__)`n`nMODE"

# Remove _snap_executor.shutdown(wait=True)
$content = $content -replace "        stop_event\.wait\(TICK_INTERVAL\)`n    _snap_executor\.shutdown\(wait=True\)", "        stop_event.wait(TICK_INTERVAL)"

# Replace print() calls with _logger calls
$content = $content -replace 'print\("\[snapshot\] restored coordinator state from snapshot"\)', '_logger.info("[snapshot] restored coordinator state from snapshot")'
$content = $content -replace 'print\(f"\[snapshot\] restore failed: \{exc\}"\)', '_logger.warning("[snapshot] restore failed: %s", exc)'
$content = $content -replace 'print\("\[snapshot\] no prior snapshot found — starting fresh"\)', '_logger.info("[snapshot] no prior snapshot found — starting fresh")'

Set-Content $mainFile -Value $content -NoNewline
Write-Host "traffic_coordinator_main.py fixed"

Write-Host "=== Step 5: Verify fixes ==="
Set-Location "d:\EWM Robot\Robotic Platform Codes\sap-bridge"
python -m ruff check . --config ruff.toml
Set-Location "d:\EWM Robot\Robotic Platform Codes"

Write-Host "=== Step 6: Check git diff ==="
git diff --stat

Write-Host "=== Step 7: Commit and push ==="
git add -A
git commit -m "fix: resolve CI lint errors and AI review issues (PR #30)

- Fix sap-bridge ruff lint: I001 import sorting, F401 unused imports, UP031 format
- Add missing 'import threading' and 'SimulatedRobot' import to cli.py
- Add scenario dispatch in run() to call _run_scenario() when --scenario is set
- Define _logger in traffic_coordinator_main.py (was undefined)
- Remove undefined _snap_executor.shutdown() call
- Replace print() calls with _logger calls for consistency

Fixes CI Lint failure and addresses AI code review issues."
git push origin feat/p1-8-scenario-cli

Write-Host "=== Done ==="
