#!/usr/bin/env python3
"""Fix all remaining AI code review issues for PR #34."""

import sys

sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════════
# Fix zewm_robco_client.py (issues #2, #3, #9, #10)
# ═══════════════════════════════════════════════════════════════════
filepath = "sap-bridge/clients/zewm_robco_client.py"
with open(filepath, encoding="utf-8") as f:
    content = f.read()

# Fix #2: Change `raise` to `break` in _execute_with_retry exception handler
old_except = """                except Exception as exc:
                    logger.error(
                        "Retry header preparation failed (status=%d): %s",
                        resp.status_code,
                        exc,
                    )
                    raise"""
new_except = """                except Exception as exc:
                    logger.error(
                        "Retry header preparation failed (status=%d): %s",
                        resp.status_code,
                        exc,
                    )
                    # Break instead of raise to let _handle_error_response
                    # produce a meaningful typed exception for the caller.
                    break"""
content = content.replace(old_except, new_except)

# Fix #3: Use `with` statement for client management in _execute_with_retry
old_exec = """        client = self._get_client()
        try:
            headers = initial_headers or self._get_csrf_headers(client)
            resp = client.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
                auth=self._get_auth_for_request(),
            )

            retries = 0
            while resp.status_code in (401, 403, 429) and retries < _MAX_HTTP_RETRIES:"""
new_exec = """        with self._get_client() as client:
            headers = initial_headers or self._get_csrf_headers(client)
            resp = client.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
                auth=self._get_auth_for_request(),
            )

            retries = 0
            while resp.status_code in (401, 403, 429) and retries < _MAX_HTTP_RETRIES:"""
content = content.replace(old_exec, new_exec)

# Remove inner client.close() and reassignment since `with` handles it
old_inner = """                # Create a new client for retry to ensure clean connection state
                with contextlib.suppress(Exception):
                    client.close()
                client = self._get_client()"""
new_inner = """                # Create a new client for retry to ensure clean connection state
                client = self._get_client()"""
content = content.replace(old_inner, new_inner)

# Replace finally block with simple return
old_finally = """            return resp
        finally:
            with contextlib.suppress(Exception):
                client.close()"""
new_finally = """            return resp"""
content = content.replace(old_finally, new_finally)

# Fix #9: Upgrade validate_config log levels from info to warning
content = content.replace(
    '        base_url = config.get("base_url", "")\n        if not base_url or base_url == DEFAULT_BASE_URL:\n            logger.info(',
    '        base_url = config.get("base_url", "")\n        if not base_url or base_url == DEFAULT_BASE_URL:\n            logger.warning(',
)
content = content.replace(
    '        client_val = config.get("client", "")\n        if not client_val or client_val == "100":\n            logger.info(',
    '        client_val = config.get("client", "")\n        if not client_val or client_val == "100":\n            logger.warning(',
)

# Fix #10: Add _unwrap_collection_result helper method before get_in_process_who
old_section = """    # ── P1: get_in_process_who ────────────────────────────────────────

    def get_in_process_who("""
new_section = """    # ── P1: Collection result helper ────────────────────────────────────

    @staticmethod
    def _unwrap_collection_result(
        result: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        \"\"\"Unwrap a parse_response result into a list of dicts.

        Handles three cases:
        - ``None`` -> empty list
        - ``list`` -> returned as-is
        - ``dict`` with ``results`` key -> extracts the list
        - ``dict`` (single entity) -> wrapped in a single-element list

        Args:
            result: The return value of :meth:`parse_response`.

        Returns:
            A list of result dicts.
        \"\"\"
        if result is None:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
            return result["results"]
        return [result]

    # ── P1: get_in_process_who ────────────────────────────────────────

    def get_in_process_who("""
content = content.replace(old_section, new_section)

# Replace get_in_process_who inline logic with helper call
old_ipw = """        result = self._request("GET", url)
        # parse_response already handles unwrapping "results" if present
        if result is None:
            return []
        if isinstance(result, list):
            return result
        # result is a dict, check if it's a single item collection
        if "results" in result and isinstance(result["results"], list):
            return result["results"]
        # single dict result
        return [result]

    # ── P1: get_assigned_robot_who ────────────────────────────────────"""
new_ipw = """        result = self._request("GET", url)
        return self._unwrap_collection_result(result)

    # ── P1: get_assigned_robot_who ────────────────────────────────────"""
content = content.replace(old_ipw, new_ipw)

# Replace get_assigned_robot_who inline logic with helper call
old_arw = """        result = self._request("GET", url)
        # parse_response already handles unwrapping "results" if present
        if result is None:
            return []
        if isinstance(result, list):
            return result
        # result is a dict, check if it's a single item collection
        if "results" in result and isinstance(result["results"], list):
            return result["results"]
        # single dict result
        return [result]

    # ═══════════════════════════════════════════════════════════════════
    # P2 Stubs"""
new_arw = """        result = self._request("GET", url)
        return self._unwrap_collection_result(result)

    # ═══════════════════════════════════════════════════════════════════
    # P2 Stubs"""
content = content.replace(old_arw, new_arw)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ zewm_robco_client.py: Fixed #2 (break), #3 (with), #9 (warning), #10 (helper)")

# ═══════════════════════════════════════════════════════════════════
# Fix core/gateway.py (issue #4: MQTT async connection confirmation)
# ═══════════════════════════════════════════════════════════════════
filepath = "core/gateway.py"
with open(filepath, encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "        self._lock = threading.Lock()\n        self._running = False",
    "        self._lock = threading.Lock()\n        self._running = False\n        self._connect_event = threading.Event()",
)

content = content.replace(
    """        try:
            self._client.connect(self._broker_host, self._broker_port, keepalive=10)
            self._client.loop_start()
            logger.info(
                "MqttGateway connected to %s:%s", self._broker_host, self._broker_port
            )
            return True
        except Exception:
            logger.exception("MqttGateway failed to connect to MQTT broker")
            self._client = None
            return False""",
    """        try:
            self._connect_event.clear()
            self._client.connect(self._broker_host, self._broker_port, keepalive=10)
            self._client.loop_start()
            # Wait for on_connect callback to confirm connection (max 5s)
            if not self._connect_event.wait(timeout=5):
                logger.warning(
                    "MqttGateway connect to %s:%s — callback not received in 5s, "
                    "connection may still be in progress",
                    self._broker_host, self._broker_port,
                )
            else:
                logger.info(
                    "MqttGateway connected to %s:%s",
                    self._broker_host, self._broker_port,
                )
            return True
        except Exception:
            logger.exception("MqttGateway failed to connect to MQTT broker")
            self._client = None
            return False""",
)

content = content.replace(
    """        else:
            logger.error("MqttGateway connection failed, rc=%s", reason_code)""",
    """        else:
            logger.error("MqttGateway connection failed, rc=%s", reason_code)
        # Signal connection attempt completed (success or failure)
        self._connect_event.set()""",
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ core/gateway.py: Fixed #4 (async connection confirmation)")

# ═══════════════════════════════════════════════════════════════════
# Fix traffic_coordinator_v5/simulator/robot.py (issue #5: configurable _guard)
# ═══════════════════════════════════════════════════════════════════
filepath = "traffic_coordinator_v5/simulator/robot.py"
with open(filepath, encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "    charge_complete_threshold: float = 80.0  # % — exit CHARGING when reached (if not full)",
    "    charge_complete_threshold: float = 80.0  # % — exit CHARGING when reached (if not full)\n    tick_guard_multiplier: int = 2      # multiplier for path-length-based guard limit\n    tick_guard_floor: int = 1000        # minimum guard limit for tick loop",
)

content = content.replace(
    "        _guard = max(len(self._path) * 2 + 10, 1000)",
    "        _guard = max(\n            len(self._path) * self.config.tick_guard_multiplier + 10,\n            self.config.tick_guard_floor,\n        )",
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ traffic_coordinator_v5/simulator/robot.py: Fixed #5 (configurable _guard)")

# ═══════════════════════════════════════════════════════════════════
# Fix e2e/pages/dashboard.page.js (issue #8: env var for timeout)
# ═══════════════════════════════════════════════════════════════════
filepath = "e2e/pages/dashboard.page.js"
with open(filepath, encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    """  async isAuthenticated() {
    try {
      // Reduced from 5000ms to 2000ms for faster test feedback
      // If CI network latency causes false positives, consider increasing back to 3000-5000ms
      await this.title.waitFor({ state: 'visible', timeout: 2000 });
      return true;
    } catch {
      return false;
    }
  }""",
    """  async isAuthenticated() {
    try {
      // Timeout is configurable via E2E_AUTH_TIMEOUT_MS env var.
      // Default: 2000ms (fast feedback). In CI, set to 5000+ if network
      // latency causes false negatives.
      const timeout = parseInt(process.env.E2E_AUTH_TIMEOUT_MS || '2000', 10);
      await this.title.waitFor({ state: 'visible', timeout });
      return true;
    } catch {
      return false;
    }
  }""",
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ e2e/pages/dashboard.page.js: Fixed #8 (env var timeout)")

print("\n🎉 All AI code review fixes applied successfully!")
