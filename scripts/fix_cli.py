"""Fix cli.py: use public API instead of _robots."""

import pathlib

p = pathlib.Path("traffic_coordinator_v5/simulator/cli.py")
text = p.read_text(encoding="utf-8")
old = (
    "                for rid, robot in fleet._robots.items():\n"
    '                    if random.random() < args.fault_prob and robot.mode.name != "ERROR":\n'
)
new = (
    "                for rid in fleet.robot_ids:\n"
    "                    robot = fleet.get_robot(rid)\n"
    "                    if robot is None:\n"
    "                        continue\n"
    '                    if random.random() < args.fault_prob and robot.mode.name != "ERROR":\n'
)
print("found:", old in text)
text2 = text.replace(old, new, 1)
p.write_text(text2, encoding="utf-8")
print("verify:", new in text2)
