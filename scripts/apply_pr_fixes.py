"""Apply all PR review fixes in one shot."""
import pathlib

changes = []

# 1. core/coordinator.py — swap assigned_robots.add after _active_assignments
p = pathlib.Path("core/coordinator.py")
text = p.read_text(encoding="utf-8")
old = (
    "            adapter.dispatch(robot.robot_id, assignment, now)\n"
    "            assigned_robots.add(robot.robot_id)\n"
    "            self._active_assignments[robot.robot_id] = assignment\n"
)
new = (
    "            try:\n"
    "                adapter.dispatch(robot.robot_id, assignment, now)\n"
    "            except Exception as exc:\n"
    "                logger.error(\n"
    '                    "dispatch failed for robot %s task %s: %s",\n'
    "                    robot.robot_id, task.task_id, exc,\n"
    "                )\n"
    '                if self._requeue_task(task, now, "dispatch_exception"):\n'
    "                    remaining.append(task)\n"
    "                continue\n"
    "            self._active_assignments[robot.robot_id] = assignment\n"
    "            assigned_robots.add(robot.robot_id)\n"
)
if old in text:
    # Add logging import if not present
    if "import logging" not in text:
        text = text.replace(
            "import math\n",
            "import logging\nimport math\n",
        )
    # Add logger if not present
    if "logger = logging.getLogger" not in text:
        text = text.replace(
            '"""  # noqa: E501\n',
            '"""  # noqa: E501\n\nlogger = logging.getLogger(__name__)\n',
            1,
        )
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    changes.append("coordinator.py: dispatch try/except + swap assigned_robots order")
else:
    changes.append("coordinator.py: SKIP (pattern not found)")

# 2. simulator/robot.py — guard _finish_path against ERROR mode
p = pathlib.Path("traffic_coordinator_v5/simulator/robot.py")
text = p.read_text(encoding="utf-8")
old = (
    "        self.distance_along_lane = self.lane_graph.length(self.current_lane_id)\n"
    "        self.mode = SimRobotMode.IDLE\n"
)
new = (
    "        self.distance_along_lane = self.lane_graph.length(self.current_lane_id)\n"
    "        if self.mode != SimRobotMode.ERROR:\n"
    "            self.mode = SimRobotMode.IDLE\n"
)
if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    changes.append("robot.py: guard _finish_path against ERROR mode")
else:
    changes.append("robot.py: SKIP (pattern not found)")

# 3. simulator/cli.py — use public API instead of _robots
p = pathlib.Path("traffic_coordinator_v5/simulator/cli.py")
text = p.read_text(encoding="utf-8")
old = (
    '                for rid, robot in fleet._robots.items():\n'
    '                    if random.random() < args.fault_prob and robot.mode.name != "ERROR":\n'
)
new = (
    '                for rid in fleet.robot_ids:\n'
    '                    robot = fleet.get_robot(rid)\n'
    '                    if robot is None:\n'
    '                        continue\n'
    '                    if random.random() < args.fault_prob and robot.mode.name != "ERROR":\n'
)
if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    changes.append("cli.py: use public API instead of _robots")
else:
    changes.append("cli.py: SKIP (pattern not found)")

# 4. sap_coordinator_bridge.py — change AUTO_CONFIRM default to "0"
p = pathlib.Path("sap-bridge/services/sap_coordinator_bridge.py")
text = p.read_text(encoding="utf-8")
old = 'AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "1") == "1"'
new = 'AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"'
if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    changes.append("sap_coordinator_bridge.py: AUTO_CONFIRM default to 0")
else:
    changes.append("sap_coordinator_bridge.py: SKIP (pattern not found)")

# 5. traffic_coordinator_main.py — background snapshot saving
p = pathlib.Path("traffic_coordinator_v5/traffic_coordinator_main.py")
text = p.read_text(encoding="utf-8")
old_snap = (
    "    last_snapshot = 0.0\n"
    "    while not stop_event.is_set():\n"
)
new_snap = (
    "    last_snapshot = 0.0\n"
    "    _snap_executor = concurrent.futures.ThreadPoolExecutor(\n"
    "        max_workers=1, thread_name_prefix=\"snapshot\",\n"
    "    )\n"
    "    while not stop_event.is_set():\n"
)
old_snap2 = (
    "            try:\n"
    "                STATE_STORE.set(SNAPSHOT_KEY, COORDINATOR.snapshot())\n"
    "                last_snapshot = now\n"
    "            except Exception as exc:\n"
    '                print(f"[snapshot] save failed: {exc}")\n'
    "        stop_event.wait(TICK_INTERVAL)\n"
)
new_snap2 = (
    "            try:\n"
    "                snap = COORDINATOR.snapshot()\n"
    "                _snap_executor.submit(_save_snapshot, snap)\n"
    "                last_snapshot = now\n"
    "            except Exception as exc:\n"
    '                print(f"[snapshot] submit failed: {exc}")\n'
    "        stop_event.wait(TICK_INTERVAL)\n"
    "    _snap_executor.shutdown(wait=False)\n"
    "\n"
    "\n"
    "def _save_snapshot(snapshot_data) -> None:\n"
    '    """Save snapshot in background thread to avoid blocking tick loop."""\n'
    "    try:\n"
    "        STATE_STORE.set(SNAPSHOT_KEY, snapshot_data)\n"
    "    except Exception as exc:\n"
    '        print(f"[snapshot] save failed: {exc}")\n'
)
if old_snap in text and old_snap2 in text:
    if "import concurrent.futures" not in text:
        text = text.replace(
            "import json\n",
            "import concurrent.futures\nimport json\n",
        )
    text = text.replace(old_snap, new_snap, 1)
    text = text.replace(old_snap2, new_snap2, 1)
    p.write_text(text, encoding="utf-8")
    changes.append("traffic_coordinator_main.py: background snapshot saving")
else:
    changes.append("traffic_coordinator_main.py: SKIP (pattern not found)")

# 6. Remove temp test files if they exist
for tmp_file in ["e2e/_tmp-test.spec.js", "e2e/_tmp-test2.spec.js"]:
    tmp = pathlib.Path(tmp_file)
    if tmp.exists():
        tmp.unlink()
        changes.append(f"deleted: {tmp_file}")

for c in changes:
    print(c)
