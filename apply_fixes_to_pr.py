#!/usr/bin/env python3
"""Apply AI review fixes to feat/c1-auth-extract-review branch files."""

import codecs
import re

# 1. Fix sap-bridge/auth.py
with open("sap-bridge/auth.py", encoding="utf-8") as f:
    auth_content = f.read()

# Add threading import after time
if "import threading" not in auth_content:
    auth_content = re.sub(
        r"import logging\nimport time\n",
        "import logging\nimport threading\nimport time\n",
        auth_content,
    )

# Add lock to __init__
if "self._lock" not in auth_content:
    auth_content = re.sub(
        r'self\._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"\n',
        r'self._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"\n        self._lock = threading.Lock()\n',
        auth_content,
    )

# Fix get_token bytes decode
if "return token.decode()" not in auth_content:
    auth_content = re.sub(
        r'if token:\s*logger\.debug\("OAuth2 token served from cache"\)\s*return token',
        'if token:\n            logger.debug("OAuth2 token served from cache")\n            return token.decode() if isinstance(token, bytes) else token',
        auth_content,
    )

# Fix get_valid_token to include lock and double-check
if "with self._lock:" not in auth_content:
    get_valid_token_pattern = r'def get_valid_token\(self, client: httpx\.Client\) -> str:\s*"""Return a valid token — from cache or fetch new\.\s*\n\s*This is the main entry point for callers\.\s*"""\s*token = self\.get_token\(\)\s*if token:\s*return token\s*return self\.fetch_new\(client\)'
    new_get_valid_token = '''def get_valid_token(self, client: httpx.Client) -> str:
        """Return a valid token — from cache or fetch new.

        Uses a lock to prevent multiple threads from fetching tokens
        simultaneously (cache stampede protection).
        """
        token = self.get_token()
        if token:
            return token
        with self._lock:
            # Double-check after acquiring lock — another thread may have
            # already refreshed the token while we were waiting.
            token = self.get_token()
            if token:
                return token
            return self.fetch_new(client)'''
    auth_content = re.sub(
        get_valid_token_pattern, new_get_valid_token, auth_content, flags=re.DOTALL
    )

# Fix close() method
if "self._redis.connection_pool.disconnect()" not in auth_content:
    auth_content = re.sub(
        r'def close\(self\) -> None:\s*"""Close Redis connection."""\s*with contextlib\.suppress\(Exception\):\s*self\._redis\.close\(\)',
        '''def close(self) -> None:
        """Close Redis connection.

        No-op: Redis connection is owned by the caller.
        """
        logger.debug("OAuth2TokenManager.close() is a no-op")''',
        auth_content,
        flags=re.DOTALL,
    )

# Add try-except around resp.json() if missing
if "try:" not in auth_content and "resp.json()" in auth_content:
    json_section_pattern = r'body = resp\.json\(\)\s+access_token = body\.get\("access_token"\)'
    new_json_section = """        try:
            body = resp.json()
        except ValueError:
            logger.error(
                "OAuth2 token response is not valid JSON: {resp.text[:200]}"
            )
            raise RuntimeError("OAuth2 token endpoint returned non-JSON response")

        access_token = body.get("access_token")"""
    auth_content = re.sub(json_section_pattern, new_json_section, auth_content)

with open("sap-bridge/auth.py", "w", encoding="utf-8") as f:
    f.write(auth_content)
print("✅ Fixed sap-bridge/auth.py")

# 2. Fix cli.py - ensure import random at top
with open("traffic_coordinator_v5/simulator/cli.py", encoding="utf-8") as f:
    cli_lines = f.readlines()

# Check if import random is at top
import_random_top = False
for line in cli_lines[:15]:
    if "import random" in line:
        import_random_top = True
        break

if not import_random_top:
    # Add import random after import logging
    fixed_lines = []
    for i, line in enumerate(cli_lines):
        if "import logging" in line:
            fixed_lines.append(line)
            fixed_lines.append("import random\n")
            import_random_top = True
        elif "import random" in line and i > 15:
            # Skip if it's inside a function
            continue
        else:
            fixed_lines.append(line)
    if import_random_top:
        with open("traffic_coordinator_v5/simulator/cli.py", "w", encoding="utf-8") as f:
            f.writelines(fixed_lines)
        print("✅ Fixed traffic_coordinator_v5/simulator/cli.py")
    else:
        print("⚠️ Could not find appropriate place to add import random in cli.py")

# 3. Fix fleet.py - add MQTT exception handling
with open("traffic_coordinator_v5/simulator/fleet.py", "rb") as f:
    fleet_content_bytes = f.read()
    # Remove BOM if present
    if fleet_content_bytes.startswith(codecs.BOM_UTF8):
        fleet_content_bytes = fleet_content_bytes[len(codecs.BOM_UTF8) :]
    fleet_content = fleet_content_bytes.decode("utf-8")

# Fix MQTT connection exception handling
if "except Exception as exc:" not in fleet_content and "self._mqtt.connect()" in fleet_content:
    fleet_content = re.sub(
        r"if self\._mqtt is not None:\s*self\._mqtt\.connect\(\)",
        """        if self._mqtt is not None:
            try:
                self._mqtt.connect()
            except Exception as exc:
                logger.exception("FleetSimulator: MQTT connection failed — running without MQTT")""",
        fleet_content,
    )

with open("traffic_coordinator_v5/simulator/fleet.py", "w", encoding="utf-8", newline="\n") as f:
    f.write(fleet_content)
print("✅ Fixed traffic_coordinator_v5/simulator/fleet.py")

print("\nAll AI code review fixes applied to current branch.")
