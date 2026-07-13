#!/usr/bin/env python3
"""Fix _load_mqtt_password method in core/gateway.py"""

import os

# Read the file
with open("core/gateway.py", "r", encoding="utf-8") as f:
    content = f.read()

# Define the old and new method
old_method = '''    def _load_mqtt_password(self) -> str:
        """Load MQTT password from env var or Docker secret file."""
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
        return ""'''

new_method = '''    def _load_mqtt_password(self) -> str:
        """Load MQTT password from env var or Docker secret file."""
        password = os.environ.get("MQTT_PASSWORD", "")
        if password:
            return password
        password_file = os.environ.get("MQTT_PASSWORD_FILE", "")
        if password_file:
            try:
                with open(password_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        logger.warning("MQTT password file is empty: %s", password_file)
                    return content
            except FileNotFoundError:
                logger.error("MQTT password file not found: %s", password_file)
            except PermissionError:
                logger.error("Permission denied reading MQTT password file: %s", password_file)
            except OSError as e:
                logger.error("Cannot read MQTT password file %s: %s", password_file, e)
        return ""'''

# Replace the method
if old_method in content:
    content = content.replace(old_method, new_method)
    with open("core/gateway.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated _load_mqtt_password method in core/gateway.py")
else:
    print("Old method not found, checking if new method already exists...")
    if new_method in content:
        print("New method already exists")
    else:
        print("Error: Could not find the method to replace")
        print("Looking for pattern 'def _load_mqtt_password'...")
        if "def _load_mqtt_password" in content:
            print("Found method but content differs")