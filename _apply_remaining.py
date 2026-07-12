#!/usr/bin/env python3
"""Apply remaining PR #49 fixes."""
import os
os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

# ============ 1. Fix monitoring/dashboards/v5-traffic-coordinator.json ============
print("Fixing monitoring/dashboards/v5-traffic-coordinator.json...")
with open("monitoring/dashboards/v5-traffic-coordinator.json", "r", encoding="utf-8") as f:
    content = f.read()

# Replace __inputs/__requires with templating variable
old_header = """{
  "__inputs": [
    {
      "name": "DS_PROMETHEUS",
      "label": "Prometheus",
      "description": "",
      "type": "datasource",
      "pluginId": "prometheus",
      "pluginName": "Prometheus"
    }
  ],
  "__requires": [
    {
      "type": "datasource",
      "id": "prometheus",
      "name": "Prometheus",
      "version": "1.0.0"
    },
    {
      "type": "grafana",
      "id": "grafana",
      "name": "Grafana",
      "version": "10.0.0"
    }
  ],
  "title": "V5 Traffic Coordinator",
  "uid": "v5-traffic-coordinator",
  "schemaVersion": 39,
  "version": 2,"""

new_header = """{
  "title": "V5 Traffic Coordinator",
  "uid": "v5-traffic-coordinator",
  "schemaVersion": 39,
  "version": 2,
  "timezone": "browser",
  "editable": true,
  "templating": {
    "list": [
      {
        "name": "datasource",
        "type": "datasource",
        "query": "prometheus",
        "current": { "text": "Prometheus", "value": "Prometheus" }
      }
    ]
  },"""

if old_header in content:
    content = content.replace(old_header, new_header)
    print("  OK: header replaced")

# Replace all ${DS_PROMETHEUS} with $datasource
count = content.count("${DS_PROMETHEUS}")
content = content.replace("${DS_PROMETHEUS}", "$datasource")
if count > 0:
    print(f"  OK: replaced {count} datasource references")

with open("monitoring/dashboards/v5-traffic-coordinator.json", "w", encoding="utf-8") as f:
    f.write(content)

# ============ 2. Fix sap-bridge/services/sap_coordinator_bridge.py ============
print("\nFixing sap-bridge/services/sap_coordinator_bridge.py...")
with open("sap-bridge/services/sap_coordinator_bridge.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add GRACE_POLLS as module-level constant after AUTO_CONFIRM
old_auto = 'AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"'
new_auto = 'AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"\n# Number of consecutive polls a task must be inactive before auto-confirming.\nGRACE_POLLS = 2'

if old_auto in content and "GRACE_POLLS = 2" not in content.split("\n")[36]:
    content = content.replace(old_auto, new_auto, 1)
    print("  OK: added module-level GRACE_POLLS")

# Remove inline GRACE_POLLS and change logger.info to logger.debug
old_inline = """            # Not in any explicit list — use grace-period fallback
            GRACE_POLLS = 2
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.info("""

new_inline = """            # Not in any explicit list — use grace-period fallback
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.debug("""

if old_inline in content:
    content = content.replace(old_inline, new_inline)
    print("  OK: removed inline GRACE_POLLS, lowered log level")

with open("sap-bridge/services/sap_coordinator_bridge.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\nAll remaining fixes applied!")
