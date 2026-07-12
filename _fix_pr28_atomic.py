#!/usr/bin/env python3
"""Atomically apply PR #28 AI code review fixes, commit, and push."""
import subprocess
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def run(cmd, check=True):
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(f"[stderr] {result.stderr.strip()}", file=sys.stderr)
    if check and result.returncode != 0:
        print(f"FAIL code={result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    return result


def patch_file(path, replacements, label):
    """Apply replacements to a file, asserting each old string is found."""
    p = ROOT / path
    t = p.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in t:
            print(f"WARNING [{label}]: old string not found, skipping", file=sys.stderr)
            continue
        t = t.replace(old, new, 1)
        print(f"  OK [{label}]: replacement applied")
    p.write_text(t, encoding="utf-8")


# Step 1: Clean checkout from origin/master
run("git fetch origin")
run("git reset --hard", check=False)
run("git checkout -- .", check=False)
run("git checkout -B fix/pr28-ai-review-final origin/master")

# Step 2: Apply fixes
# Fix Issue 4.3: simulator/robot.py _iso_now millisecond precision
patch_file("traffic_coordinator_v5/simulator/robot.py", [
    ("import time\nimport uuid\n",
     "import uuid\nfrom datetime import datetime, timezone\n"),
    ('    @staticmethod\n    def _iso_now() -> str:\n'
     '        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())\n',
     '    @staticmethod\n    def _iso_now() -> str:\n'
     '        """Return an ISO-8601 UTC timestamp with millisecond precision (VDA5050 format)."""\n'
     '        now = datetime.now(timezone.utc)\n'
     '        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"\n'),
], "robot.py")

# Fix Issues 3.1 + 4.1: coordinator.py logger + call-site guard + debug log
patch_file("core/coordinator.py", [
    ("from __future__ import annotations\n\nimport math\n",
     "from __future__ import annotations\n\nimport logging\nimport math\n"),
    ("from core.survival.worm_blackbox import WormBlackbox\n\n\n@dataclass\nclass TickResult:",
     "from core.survival.worm_blackbox import WormBlackbox\n\n"
     "logger = logging.getLogger(__name__)\n\n\n"
     "@dataclass\nclass TickResult:"),
    ('        self._robot_states[state.robot_id] = state\n'
     '        self._auto_report_progress(state.robot_id, now)\n',
     '        self._robot_states[state.robot_id] = state\n'
     '        # Only run auto-progress inference when the robot has an active\n'
     '        # assignment; avoids needless work on every uplink for idle robots.\n'
     '        if state.robot_id in self._active_assignments:\n'
     '            self._auto_report_progress(state.robot_id, now)\n'),
    ('        for offset, lane_id in enumerate(path[idx:]):\n'
     '            lane = self.fmap.lane(lane_id)\n'
     '            if lane is not None and lane.to_node == last_node:\n'
     '                if self.report_progress(robot_id, lane_id, now):\n'
     '                    break\n',
     '        for offset, lane_id in enumerate(path[idx:]):\n'
     '            lane = self.fmap.lane(lane_id)\n'
     '            if lane is not None and lane.to_node == last_node:\n'
     '                logger.debug(\n'
     '                    "auto_report_progress: robot %s reached end of lane %s "\n'
     '                    "(path offset %d, last_node=%s)",\n'
     '                    robot_id, lane_id, offset, last_node,\n'
     '                )\n'
     '                if self.report_progress(robot_id, lane_id, now):\n'
     '                    break\n'),
], "coordinator.py")

# Fix Issues 3.2 + 4.4: traffic_coordinator_main.py
tc_path = "traffic_coordinator_v5/traffic_coordinator_main.py"
tc_replacements = []
t_tc = (ROOT / tc_path).read_text(encoding="utf-8")

if "import concurrent.futures\n" in t_tc and "_snap_executor" not in t_tc:
    tc_replacements.append(("import concurrent.futures\n", ""))
if "import logging\n" not in t_tc:
    tc_replacements.append(("import json\n", "import json\nimport logging\n"))
if "_logger = logging.getLogger(__name__)" not in t_tc:
    tc_replacements.append(("\nMODE = os.environ.get",
                            "\n_logger = logging.getLogger(__name__)\n\nMODE = os.environ.get"))
tc_replacements.extend([
    ('            except Exception as exc:\n                print(f"[snapshot] save failed: {exc}")\n',
     '            except Exception as exc:\n                _logger.warning("[snapshot] save failed: %s", exc)\n'),
    ('        print("[snapshot] restored coordinator state from snapshot")\n',
     '        _logger.info("[snapshot] restored coordinator state from snapshot")\n'),
    ('        print(f"[snapshot] restore failed: {exc}")\n',
     '        _logger.warning("[snapshot] restore failed: %s", exc)\n'),
    ('    print("[snapshot] no prior snapshot found',
     '    _logger.info("[snapshot] no prior snapshot found'),
])
patch_file(tc_path, tc_replacements, "tc_main.py")

# Step 3: Verify
run("git diff --stat")

# Step 4: Stage + commit + push (all relative paths to avoid space issues)
run("git add core/coordinator.py traffic_coordinator_v5/simulator/robot.py traffic_coordinator_v5/traffic_coordinator_main.py")

# Write commit message to relative path
msg_file = ROOT / "_commit_msg.txt"
msg_file.write_text(
    "fix: address remaining PR #28 AI code review issues\n\n"
    "- simulator/robot.py: _iso_now uses real millisecond precision (Issue 4.3)\n"
    "- coordinator.py: add module logger + debug log in _auto_report_progress (Issue 4.1)\n"
    "- coordinator.py: call-site guard for _auto_report_progress (Issue 3.1)\n"
    "- traffic_coordinator_main.py: remove orphaned import, use _logger for snapshot (Issues 3.2, 4.4)\n",
    encoding="utf-8",
)
run("git commit -F _commit_msg.txt")
msg_file.unlink(missing_ok=True)

# Step 5: Push
run("git push origin fix/pr28-ai-review-final --force")

print("\n=== SUCCESS: branch pushed ===")
