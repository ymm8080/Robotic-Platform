#!/usr/bin/env python3
"""Fix all AI code review issues for PR #44."""
import json
import os
import re

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

# ── Fix 1: ewm_backend.py — remove duplicate import ──────────────────────
print("Fix 1: ewm_backend.py — removing duplicate 'from auth import' line...")
with open("sap-bridge/backends/ewm_backend.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "from .oauth2_token_manager import OAuth2TokenManager, read_client_secret\n"
    "from auth import OAuth2TokenManager, read_client_secret\n",
    "from .oauth2_token_manager import OAuth2TokenManager, read_client_secret\n",
)

with open("sap-bridge/backends/ewm_backend.py", "w", encoding="utf-8") as f:
    f.write(content)
print("  Done.")

# ── Fix 2: zewm_robco_exceptions.py — fix encoding ───────────────────────
print("Fix 2: zewm_robco_exceptions.py — fixing encoding...")
# Read with latin-1 to avoid errors, then re-save as UTF-8
with open("sap-bridge/clients/zewm_robco_exceptions.py", "r", encoding="latin-1") as f:
    content = f.read()

with open("sap-bridge/clients/zewm_robco_exceptions.py", "w", encoding="utf-8") as f:
    f.write(content)
print("  Done.")

# ── Fix 3: test_zewm_robco_client.py — already fixed by ruff --fix ────────
print("Fix 3: test_zewm_robco_client.py — already fixed by ruff --fix")

# ── Fix 4: auto-fix.sh — replace hardcoded Windows path ──────────────────
print("Fix 4: auto-fix.sh — replacing hardcoded Windows path with relative path...")
with open("auto-fix.sh", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    'PROJECT_ROOT="D:/EWM ROBOT/ROBOTIC PLATFORM CODES"',
    'PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
)

with open("auto-fix.sh", "w", encoding="utf-8") as f:
    f.write(content)
print("  Done.")

# ── Fix 5: Grafana dashboard — remove hardcoded panel IDs ────────────────
print("Fix 5: Grafana dashboard — removing hardcoded panel IDs...")
with open("monitoring/dashboards/v5-traffic-coordinator.json", "r", encoding="utf-8") as f:
    dashboard = json.load(f)

for panel in dashboard.get("panels", []):
    if "id" in panel:
        del panel["id"]

with open("monitoring/dashboards/v5-traffic-coordinator.json", "w", encoding="utf-8") as f:
    json.dump(dashboard, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("  Done.")

# ── Fix 6: zewm_robco_client.py — narrow exception catch ─────────────────
print("Fix 6: zewm_robco_client.py — narrowing broad exception catch...")
with open("sap-bridge/clients/zewm_robco_client.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the broad exception catch with more specific ones
old_catch = "except (ValueError, KeyError, AttributeError):"
new_catch = """except (json.JSONDecodeError, KeyError):
    # JSONDecodeError: response body is not valid JSON
    # KeyError: expected "error" or "message" key is missing"""

content = content.replace(old_catch, new_catch)

# Add json import if not present
if "import json" not in content.split("\n")[:30]:
    # Add after the first import line
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            lines.insert(i, "import json")
            break
    content = "\n".join(lines)

with open("sap-bridge/clients/zewm_robco_client.py", "w", encoding="utf-8") as f:
    f.write(content)
print("  Done.")

# ── Fix 7: fleet.py — add reset() method and relax load_scenario ─────────
print("Fix 7: fleet.py — adding reset() method and relaxing load_scenario...")
with open("traffic_coordinator_v5/simulator/fleet.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the strict check in load_scenario with a more helpful message + reset option
old_check = '''if self._robots or len(self.lane_graph.all_lanes()) > 0:
            raise RuntimeError("load_scenario() called on a non-empty fleet or non-empty map; create a new FleetSimulator instead")'''

new_check = '''if self._robots or len(self.lane_graph.all_lanes()) > 0:
            raise RuntimeError(
                "load_scenario() called on a non-empty fleet or non-empty map; "
                "call reset() first or create a new FleetSimulator instead"
            )'''

content = content.replace(old_check, new_check)

# Add reset() method before load_scenario
reset_method = '''
    def reset(self) -> None:
        """Clear all robots and lanes, returning the simulator to an empty state.

        Useful for re-loading a different scenario without creating a new
        ``FleetSimulator`` instance.
        """
        self._robots.clear()
        self.lane_graph.clear()

'''
# Find the load_scenario method and insert reset() before it
content = content.replace(
    "    def load_scenario(self, name: str) -> list[str]:",
    reset_method + "    def load_scenario(self, name: str) -> list[str]:",
)

with open("traffic_coordinator_v5/simulator/fleet.py", "w", encoding="utf-8") as f:
    f.write(content)
print("  Done.")

# ── Fix 8: Remove helper scripts and backup files ────────────────────────
print("Fix 8: Removing helper scripts and backup files from repo root...")
helper_files = [
    "_check_pr30.py",
    "_fix_lint6.py",
    "_fix_lint7.py",
    "_fix_lint8.py",
    "_fix_lint9.py",
    "_fix_pr30_v2.py",
    "_fix_pr30_v3.py",
    "_fix_pr30_v4.py",
    "auto-fix-v2.sh.bak",
    "auto-fix.yml.bak",
    "auto-implement-and-pr.sh",
    "auto-plan-implement-and-pr.sh",
]

for f in helper_files:
    if os.path.exists(f):
        os.remove(f)
        print(f"  Removed: {f}")

print("\nAll fixes applied successfully!")
