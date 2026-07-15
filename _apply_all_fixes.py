#!/usr/bin/env python3
"""Apply all PR #49 AI review fixes directly."""

import os

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

# ============ 1. Fix core/gateway.py ============
print("Fixing core/gateway.py...")
with open("core/gateway.py", encoding="utf-8") as f:
    content = f.read()

# Add _load_mqtt_password method and improve _publish
old_publish = """    def _publish(self, topic: str, payload: dict) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=self._qos)
        except Exception:
            logger.exception("MqttGateway failed to publish to %s", topic)"""

new_publish = """    def _load_mqtt_password(self) -> str:
        \"\"\"Load MQTT password from env var or Docker secret file.\"\"\"
        password = os.environ.get("MQTT_PASSWORD", "")
        if password:
            return password
        password_file = os.environ.get("MQTT_PASSWORD_FILE", "")
        if password_file:
            try:
                with open(password_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                logger.error("Cannot read MQTT password file: %s", password_file)
        return ""

    def _publish(self, topic: str, payload: dict) -> None:
        \"\"\"Publish message to MQTT topic with null-guard and error logging.\"\"\"
        if self._client is None:
            logger.warning("Cannot publish to %s: MQTT client not initialized", topic)
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=self._qos)
        except Exception:
            logger.exception("MqttGateway failed to publish to %s", topic)"""

if old_publish in content:
    content = content.replace(old_publish, new_publish)
    with open("core/gateway.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("  OK: gateway.py fixed")
else:
    print("  SKIP: pattern not found (may already be fixed)")

# ============ 2. Fix core/coordinator.py ============
print("Fixing core/coordinator.py...")
with open("core/coordinator.py", encoding="utf-8") as f:
    content = f.read()

# Fix snapshot - save timestamps
old_snap = '"recently_completed": [tid for tid, _ in self._recently_completed],\n            "recently_failed": [tid for tid, _ in self._recently_failed],'
new_snap = '"recently_completed": [[tid, ts] for tid, ts in self._recently_completed],\n            "recently_failed": [[tid, ts] for tid, ts in self._recently_failed],'

if old_snap in content:
    content = content.replace(old_snap, new_snap)
    print("  OK: snapshot fixed")
else:
    print("  SKIP: snapshot pattern not found")

# Fix restore - handle both old and new format
old_restore = """        # Restore recently completed / failed task tracking
        self._recently_completed.clear()
        for tid in data.get("recently_completed", []):
            self._recently_completed.append((tid, 0.0))
        self._recently_failed.clear()
        for tid in data.get("recently_failed", []):
            self._recently_failed.append((tid, 0.0))"""

new_restore = """        # Restore recently completed / failed task tracking (with timestamps)
        self._recently_completed.clear()
        for item in data.get("recently_completed", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                self._recently_completed.append((item[0], float(item[1])))
            else:
                self._recently_completed.append((item, 0.0))
        self._recently_failed.clear()
        for item in data.get("recently_failed", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                self._recently_failed.append((item[0], float(item[1])))
            else:
                self._recently_failed.append((item, 0.0))"""

if old_restore in content:
    content = content.replace(old_restore, new_restore)
    print("  OK: restore fixed")
else:
    print("  SKIP: restore pattern not found")

with open("core/coordinator.py", "w", encoding="utf-8") as f:
    f.write(content)

# ============ 3. Fix e2e/pages/command.panel.js ============
print("Fixing e2e/pages/command.panel.js...")
with open("e2e/pages/command.panel.js", encoding="utf-8") as f:
    content = f.read()

old_cmd = """  commandButton(robotId, command) {
    // Try to scope to the robot's card/row first; fall back to global search.
    const robotSection = this.page.locator(`[data-testid="robot-${robotId}"]`);
    return robotSection
      .getByRole('button', { name: new RegExp(`^${command}$`, 'i') })
      .or(
        this.page.getByRole('button', { name: new RegExp(`^${command}$`, 'i') })
      )
      .first();
  }

  async sendCommand(robotId, command) {
    await this.commandButton(robotId, command).click();
  }"""

new_cmd = """  async commandButton(robotId, command) {
    const cmdRegex = new RegExp(`^${command}$`, 'i');
    // Try to scope to the robot's card/row first; fall back to global search.
    const robotSection = this.page.locator(`[data-testid="robot-${robotId}"]`);
    const button = robotSection
      .getByRole('button', { name: cmdRegex })
      .or(
        this.page.getByRole('button', { name: cmdRegex })
      )
      .first();

    if (await button.count() === 0) {
      throw new Error(`Command button "${command}" not found for robot "${robotId}"`);
    }
    return button;
  }

  async sendCommand(robotId, command) {
    const button = await this.commandButton(robotId, command);
    await button.click();
  }"""

if old_cmd in content:
    content = content.replace(old_cmd, new_cmd)
    with open("e2e/pages/command.panel.js", "w", encoding="utf-8") as f:
        f.write(content)
    print("  OK: command.panel.js fixed")
else:
    print("  SKIP: pattern not found")

# ============ 4. Fix e2e/pages/dashboard.page.js ============
print("Fixing e2e/pages/dashboard.page.js...")
with open("e2e/pages/dashboard.page.js", encoding="utf-8") as f:
    content = f.read()

content = content.replace("timeout: 5000", "timeout: 3000")
with open("e2e/pages/dashboard.page.js", "w", encoding="utf-8") as f:
    f.write(content)
print("  OK: dashboard.page.js fixed")

print("\nAll fixes applied!")
