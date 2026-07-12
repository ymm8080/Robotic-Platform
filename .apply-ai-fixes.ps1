#!/usr/bin/env pwsh
# Fixes for PR39 AI Review

# 1. sap-bridge/auth.py
$auth_py = Get-Content -Raw sap-bridge/auth.py
$auth_py = $auth_py -replace 'import contextlib\r\nimport logging\r\nimport time\r\n\r\nimport httpx\r\nimport redis as rd', 'import contextlib\r\nimport logging\r\nimport threading\r\nimport time\r\n\r\nimport httpx\r\nimport redis as rd'
$auth_py = $auth_py -replace '        self\._scope = scope\r\n        self\._cache_key = f"\{_TOKEN_KEY_PREFIX\}:\{token_url\}"', '        self._scope = scope\r\n        self._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"\r\n        self._lock = threading.Lock()'
$auth_py = $auth_py -replace '    def get_token\(self\) -> str \| None:\r\n        """Return cached token if still valid, None otherwise\."""\r\n        token = self\._redis\.get\(self\._cache_key\)\r\n        if token:\r\n            logger\.debug\("OAuth2 token served from cache"\)\r\n            return token\r\n        return None', '    def get_token(self) -> str | None:\r\n        """Return cached token if still valid, None otherwise."""\r\n        token = self._redis.get(self._cache_key)\r\n        if token:\r\n            logger.debug("OAuth2 token served from cache")\r\n            return token.decode() if isinstance(token, bytes) else token\r\n        return None'
$auth_py = $auth_py -replace '    def get_valid_token\(self, client: httpx\.Client\) -> str:\r\n        """Return a valid token — from cache or fetch new\.\r\n\r\n        This is the main entry point for callers\.\r\n        """\r\n        token = self\.get_token\(\)\r\n        if token:\r\n            return token\r\n        return self\.fetch_new\(client\)', '    def get_valid_token(self, client: httpx.Client) -> str:\r\n        """Return a valid token — from cache or fetch new.\r\n\r\n        Uses a lock to prevent multiple threads from fetching tokens\r\n        simultaneously (cache stampede protection).\r\n        """\r\n        token = self.get_token()\r\n        if token:\r\n            return token\r\n        with self._lock:\r\n            # Double-check after acquiring lock — another thread may have\r\n            # already refreshed the token while we were waiting.\r\n            token = self.get_token()\r\n            if token:\r\n                return token\r\n            return self.fetch_new(client)'
$auth_py = $auth_py -replace '    def close\(self\) -> None:\r\n        """Close Redis connection\."""\r\n        with contextlib\.suppress\(Exception\):\r\n            self\._redis\.close\(\)', '    def close(self) -> None:\r\n        """Close Redis connection."""\r\n        with contextlib.suppress(Exception):\r\n            self._redis.connection_pool.disconnect()'
$auth_py | Set-Content -NoNewline sap-bridge/auth.py
Write-Host "Updated: sap-bridge/auth.py"

# 2. traffic_coordinator_v5/simulator/cli.py — move import random to top
$cli_py = Get-Content -Raw traffic_coordinator_v5/simulator/cli.py
$cli_py = $cli_py -replace 'import argparse\r\nimport logging\r\nimport signal\r\nimport sys\r\nimport time\r\n', 'import argparse\r\nimport logging\r\nimport random\r\nimport signal\r\nimport sys\r\nimport time\r\n'
$cli_py = $cli_py -replace '            if args\.fault_prob > 0:\r\n                import random\r\n\r\n                for rid in fleet\.robot_ids:', '            if args.fault_prob > 0:\r\n                for rid in fleet.robot_ids:'
$cli_py | Set-Content -NoNewline traffic_coordinator_v5/simulator/cli.py
Write-Host "Updated: traffic_coordinator_v5/simulator/cli.py"

# 3. traffic_coordinator_v5/simulator/fleet.py — add try/except back to start()
$fleet_py = Get-Content -Raw traffic_coordinator_v5/simulator/fleet.py
$fleet_py = $fleet_py -replace '    def start\(self\) -> None:\r\n        """Start the MQTT client and optional real-time tick thread\."""\r\n        if self\._mqtt is not None:\r\n            self\._mqtt\.connect\(\)', '    def start(self) -> None:\r\n        """Start the MQTT client and optional real-time tick thread.\r\n\r\n        If the MQTT connection fails, the tick thread is not started to\r\n        avoid running in a half-connected state.\"""\r\n        if self._mqtt is not None:\r\n            try:\r\n                self._mqtt.connect()\r\n            except Exception as exc:\r\n                logger.error("Failed to connect MQTT: %s", exc)\r\n                return'
$fleet_py | Set-Content -NoNewline traffic_coordinator_v5/simulator/fleet.py
Write-Host "Updated: traffic_coordinator_v5/simulator/fleet.py"

Write-Host "All fixes applied."