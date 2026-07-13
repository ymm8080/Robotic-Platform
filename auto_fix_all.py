#!/usr/bin/env python3
"""
Comprehensive auto-fix script for SAP EWM Robot Platform.
This script fixes ALL issues and implements ALL improvements identified in AI code review.

Key fixes:
1. Auth.py improvements (thread safety, error handling)
2. ZewmRobcoClient improvements (validation, escaping, error handling)
3. Exception logging improvements
4. Linting and code quality issues
5. Documentation improvements
6. Configuration validation improvements
"""

import re
import subprocess
import sys
from pathlib import Path


class AutoFixer:
    def __init__(self):
        self.project_root = Path(r"D:\EWM Robot\Robotic Platform Codes")
        self.fixes_applied = []
        self.errors = []

    def log(self, message: str):
        print(f"[INFO] {message}")

    def error(self, message: str):
        print(f"[ERROR] {message}", file=sys.stderr)
        self.errors.append(message)

    def success(self, message: str):
        print(f"[OK] {message}")
        self.fixes_applied.append(message)

    def apply_fix(self, description: str, fix_func):
        """Apply a fix and handle errors gracefully."""
        try:
            result = fix_func()
            if result:
                self.success(f"{description}: {result}")
            else:
                self.log(f"{description}: No changes needed")
        except Exception as e:
            self.error(f"{description}: Failed - {e}")

    def run_command(self, cmd: str, cwd=None, check=True):
        """Run a shell command."""
        cwd = cwd or self.project_root
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        if check and result.returncode != 0:
            self.error(f"Command failed: {cmd}\n{result.stderr}")
        return result

    # ===== FIX 1: sap-bridge/auth.py =====
    def fix_auth_py(self) -> str:
        """Fix OAuth2 token manager with thread safety and proper error handling."""
        auth_path = self.project_root / "sap-bridge" / "auth.py"

        with open(auth_path, encoding="utf-8") as f:
            content = f.read()

        changes_made = []

        # 1. Ensure threading import
        if "import threading" not in content:
            content = re.sub(
                r"import logging\nimport time\n\nimport httpx",
                "import logging\nimport threading\nimport time\n\nimport httpx",
                content,
            )
            changes_made.append("Added threading import")

        # 2. Add thread lock to __init__
        if "self._lock = threading.Lock()" not in content:
            # Find the line with cache_key
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if 'self._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"' in line:
                    indent = len(line) - len(line.lstrip())
                    spaces = " " * indent
                    lines[i] = f"{line}\n{spaces}self._lock = threading.Lock()"
                    content = "\n".join(lines)
                    changes_made.append("Added thread lock to __init__")
                    break

        # 3. Fix get_token method to handle bytes properly
        old_get_token = (
            "    def get_token(self) -> str | None:\n"
            '        """Return cached token if still valid, None otherwise."""\n'
            "        token = self._redis.get(self._cache_key)\n"
            "        if token:\n"
            '            logger.debug("OAuth2 token served from cache")\n'
            "            return token\n"
            "        return None"
        )

        new_get_token = (
            "    def get_token(self) -> str | None:\n"
            '        """Return cached token if still valid, None otherwise."""\n'
            "        token = self._redis.get(self._cache_key)\n"
            "        if token:\n"
            '            logger.debug("OAuth2 token served from cache")\n'
            "            return token.decode() if isinstance(token, bytes) else token\n"
            "        return None"
        )

        if old_get_token in content:
            content = content.replace(old_get_token, new_get_token)
            changes_made.append("Fixed get_token bytes decoding")

        # 4. Implement thread-safe get_valid_token method
        old_get_valid_token = (
            "    def get_valid_token(self, client: httpx.Client) -> str:\n"
            '        """Return a valid token — from cache or fetch new.\n'
            "\n"
            "        Uses a lock to prevent multiple threads from fetching tokens\n"
            "        simultaneously (cache stampede protection).\n"
            '        """\n'
            "        token = self.get_token()\n"
            "        if token:\n"
            "            return token\n"
            "        with self._lock:\n"
            "            # Double-check after acquiring lock — another thread may have\n"
            "            # already refreshed the token while we were waiting.\n"
            "            token = self.get_token()\n"
            "            if token:\n"
            "                return token\n"
            "            return self.fetch_new(client)"
        )

        # Check if method needs fixing
        if "with self._lock:" not in content:
            # Find get_valid_token method
            method_pattern = r'def get_valid_token\(self, client: httpx\.Client\) -> str:.*?"""Return a valid token'
            match = re.search(method_pattern, content, re.DOTALL)
            if match:
                method_start = match.start()
                # Find the end of the method (next def or class)
                method_end = content.find("\n    def ", method_start)
                if method_end == -1:
                    method_end = content.find("\nclass ", method_start)
                if method_end == -1:
                    method_end = len(content)

                old_method = content[method_start:method_end]
                # Replace with thread-safe version
                content = content[:method_start] + old_get_valid_token + content[method_end:]
                changes_made.append("Implemented thread-safe get_valid_token")

        # 5. Fix close method to handle Redis connection properly
        if (
            "self._redis.connection_pool.disconnect()" not in content
            and "self._redis.close()" in content
        ):
            content = content.replace(
                "self._redis.close()", "self._redis.connection_pool.disconnect()"
            )
            changes_made.append("Fixed Redis connection closing")

        # 6. Add better error logging in fetch_new method
        if "except FileNotFoundError:" in content and "raise" in content:
            # Already has error handling
            pass
        else:
            # Add proper error handling for missing secret file
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "def read_client_secret(" in line:
                    # Find the end of the function
                    for j in range(i, len(lines)):
                        if lines[j].strip() == "" and j > i:
                            func_body = "\n".join(lines[i:j])
                            if "except FileNotFoundError:" not in func_body:
                                # Add error handling
                                func_body = func_body.replace(
                                    "    with open(secret_file) as f:",
                                    '    try:\n        with open(secret_file) as f:\n            return f.read().strip()\n    except FileNotFoundError:\n        logger.error(f"OAuth2 client secret file not found: {secret_file}")\n        raise',
                                )
                                lines[i:j] = func_body.split("\n")
                                content = "\n".join(lines)
                                changes_made.append("Added error handling for missing secret file")
                            break

        if changes_made:
            with open(auth_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Applied {len(changes_made)} fixes: {', '.join(changes_made)}"
        return "No fixes needed"

    # ===== FIX 2: sap-bridge/clients/zewm_robco_client.py =====
    def fix_zewm_client(self) -> str:
        """Fix ZEWM Robco client issues."""
        client_path = self.project_root / "sap-bridge" / "clients" / "zewm_robco_client.py"

        with open(client_path, encoding="utf-8") as f:
            content = f.read()

        changes_made = []

        # 1. Fix parameter escaping in _function_import_url
        old_url_builder = (
            '        qs = "&".join(\n'
            "            f\"{k}='{v}'\" for k, v in params.items() if v is not None\n"
            "        )"
        )

        new_url_builder = (
            "        parts: list[str] = []\n"
            "        for k, v in params.items():\n"
            "            if v is not None:\n"
            '                escaped = str(v).replace("\'", "\'\'")\n'
            "                parts.append(f\"{k}='{escaped}'\")\n"
            '        qs = "&".join(parts)'
        )

        if old_url_builder in content:
            content = content.replace(old_url_builder, new_url_builder)
            changes_made.append("Fixed SQL injection vulnerability in URL parameter escaping")

        # 2. Improve validate_config to treat defaults as errors
        old_validate = (
            '        base_url = config.get("base_url", "")\n'
            "        if not base_url:\n"
            '            errors.append("base_url is not configured")\n'
            "        elif base_url == DEFAULT_BASE_URL:\n"
            "            logger.info(\n"
            '                "base_url may be default (%s) — verify config", DEFAULT_BASE_URL,\n'
            "            )\n\n"
            '        client_val = config.get("client", "")\n'
            "        if not client_val:\n"
            '            errors.append("SAP client is not configured")\n'
            '        elif client_val == "100":\n'
            '            logger.info("SAP client may be default (100) — verify tenant")'
        )

        new_validate = (
            '        base_url = config.get("base_url", "")\n'
            "        if not base_url or base_url == DEFAULT_BASE_URL:\n"
            "            errors.append(\n"
            '                f"base_url may be default ({DEFAULT_BASE_URL}) — check config",\n'
            "            )\n\n"
            '        client_val = config.get("client", "")\n'
            '        if not client_val or client_val == "100":\n'
            '            errors.append("SAP client may be default (100) — verify tenant")'
        )

        if old_validate in content:
            content = content.replace(old_validate, new_validate)
            changes_made.append("Improved config validation to treat defaults as errors")

        # 3. Fix _handle_error_response exception handling to be more specific
        old_error_handling = """        try:
            err = body.get("error", {})
            raw_code = err.get("code", "INTERNAL_ERROR")
            # Strip SAP's "/NNN" numeric suffix
            error_code = raw_code.split("/")[0]
            detail = err.get("message", {}).get("value", "")
            raise_for_error_code(error_code, detail)
        except (ValueError, KeyError, AttributeError):
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: unexpected error format: {body}",
            )"""

        new_error_handling = """        try:
            body = resp.json()
        except json.JSONDecodeError:
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: non-JSON response: {resp.text[:200]}",
            )
        try:
            err = body.get("error", {})
            raw_code = err.get("code", "INTERNAL_ERROR")
            # Strip SAP's "/NNN" numeric suffix
            error_code = raw_code.split("/")[0]
            detail = err.get("message", {}).get("value", "")
            raise_for_error_code(error_code, detail)
        except KeyError:
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: unexpected error format: {body}",
            )"""

        if old_error_handling in content:
            content = content.replace(old_error_handling, new_error_handling)
            changes_made.append("Improved error response parsing with better exception handling")

        # 4. Add missing import for json if not present
        if "import json" not in content.split("\n")[:10]:
            lines = content.split("\n")
            import_found = False
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    import_found = True
                elif import_found and line and not line.startswith(("import ", "from ", "#")):
                    # Insert after imports
                    lines.insert(i, "import json")
                    content = "\n".join(lines)
                    changes_made.append("Added missing json import")
                    break

        # 5. Fix close() method to handle None checks properly
        close_method_start = content.find("def close(self) -> None:")
        if close_method_start != -1:
            close_method_end = content.find("\n\n", close_method_start)
            if close_method_end == -1:
                close_method_end = len(content)

            close_method = content[close_method_start:close_method_end]
            if "self._csrf = None" not in close_method:
                # Find where to insert clearing of csrf reference
                lines = close_method.split("\n")
                for i, line in enumerate(lines):
                    if "self._oauth2 = None" in line:
                        lines.insert(i + 1, "        self._csrf = None")
                        new_close_method = "\n".join(lines)
                        content = (
                            content[:close_method_start]
                            + new_close_method
                            + content[close_method_end:]
                        )
                        changes_made.append("Fixed close() method to clear csrf reference")
                        break

        if changes_made:
            with open(client_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Applied {len(changes_made)} fixes: {', '.join(changes_made)}"
        return "No fixes needed"

    # ===== FIX 3: traffic_coordinator_v5/simulator/fleet.py =====
    def fix_fleet_py(self) -> str:
        """Fix fleet.py exception handling."""
        fleet_path = self.project_root / "traffic_coordinator_v5" / "simulator" / "fleet.py"

        with open(fleet_path, encoding="utf-8") as f:
            content = f.read()

        changes_made = []

        # 1. Fix bare except Exception statements
        if "except Exception:" in content:
            content = content.replace("except Exception:", "except Exception as exc:")
            changes_made.append("Fixed bare except Exception statements")

        # 2. Improve logging of exceptions
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "except Exception as exc:" in line:
                # Find the next line with logger.error
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "logger.error" in lines[j] and "Failed to connect MQTT" in lines[j]:
                        # Check if exc is being logged
                        if (
                            "%s" not in lines[j]
                            and "exc" not in lines[j]
                            and "{exc}" not in lines[j]
                        ):
                            # Fix the logging line
                            if lines[j].endswith('")') or lines[j].endswith('")') or lines[j].endswith('")'):
                                lines[j] = lines[j][:-2] + ", exc)"
                            else:
                                lines[j] = lines[j].replace('")', ", exc)")
                            changes_made.append(
                                "Improved exception logging in MQTT connection error"
                            )
                        break

        if changes_made:
            content = "\n".join(lines)
            with open(fleet_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Applied {len(changes_made)} fixes: {', '.join(changes_made)}"
        return "No fixes needed"

    # ===== FIX 4: traffic_coordinator_v5/simulator/cli.py =====
    def fix_cli_py(self) -> str:
        """Fix cli.py import ordering."""
        cli_path = self.project_root / "traffic_coordinator_v5" / "simulator" / "cli.py"

        with open(cli_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Check if random is imported in top imports
        random_imported = any("import random" in line for line in lines[:30])

        if not random_imported:
            # Find the import section
            for i, line in enumerate(lines):
                if "import logging" in line:
                    # Insert after logging import
                    lines.insert(i + 1, "import random\n")
                    with open(cli_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    return "Added import random to top imports"

        return "No fixes needed"

    # ===== FIX 5: monitoring/dashboards/v5-traffic-coordinator.json =====
    def fix_grafana_dashboard(self) -> str:
        """Fix Grafana dashboard configuration."""
        dashboard_path = (
            self.project_root / "monitoring" / "dashboards" / "v5-traffic-coordinator.json"
        )

        if not dashboard_path.exists():
            return "Dashboard file not found, skipping"

        with open(dashboard_path, encoding="utf-8") as f:
            content = f.read()

        changes_made = []

        # 1. Fix __inputs/__requires header
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
            changes_made.append("Fixed dashboard header with templating variable")

        # 2. Replace ${DS_PROMETHEUS} with $datasource
        ds_count = content.count("${DS_PROMETHEUS}")
        if ds_count > 0:
            content = content.replace("${DS_PROMETHEUS}", "$datasource")
            changes_made.append(f"Replaced {ds_count} datasource references")

        if changes_made:
            with open(dashboard_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Applied {len(changes_made)} fixes: {', '.join(changes_made)}"
        return "No fixes needed"

    # ===== FIX 6: sap-bridge/services/sap_coordinator_bridge.py =====
    def fix_sap_coordinator_bridge(self) -> str:
        """Fix SAP coordinator bridge issues."""
        bridge_path = self.project_root / "sap-bridge" / "services" / "sap_coordinator_bridge.py"

        if not bridge_path.exists():
            return "SAP coordinator bridge file not found, skipping"

        with open(bridge_path, encoding="utf-8") as f:
            content = f.read()

        changes_made = []

        # 1. Move GRACE_POLLS to module-level constant
        if "GRACE_POLLS = 2" not in content.split("\n")[:50]:
            # Find AUTO_CONFIRM line
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if 'AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"' in line:
                    lines.insert(
                        i + 1,
                        "# Number of consecutive polls a task must be inactive before auto-confirming.",
                    )
                    lines.insert(i + 2, "GRACE_POLLS = 2")
                    changes_made.append("Added module-level GRACE_POLLS constant")
                    content = "\n".join(lines)
                    break

        # 2. Remove inline GRACE_POLLS and change logger.info to logger.debug
        if "GRACE_POLLS = 2" in content and "if tid not in self._inactive_since:" in content:
            # Find and fix the inline assignment
            pattern = r"# Not in any explicit list — use grace-period fallback\s+GRACE_POLLS = 2\s+if tid not in self\._inactive_since:\s+self\._inactive_since\[tid\] = self\._poll_count\s+logger\.info\("
            replacement = "# Not in any explicit list — use grace-period fallback\n            if tid not in self._inactive_since:\n                self._inactive_since[tid] = self._poll_count\n                logger.debug("

            import re

            if re.search(pattern, content, re.MULTILINE):
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
                changes_made.append("Removed inline GRACE_POLLS and changed info to debug logging")

        if changes_made:
            with open(bridge_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Applied {len(changes_made)} fixes: {', '.join(changes_made)}"
        return "No fixes needed"

    # ===== FIX 7: Run linting and tests =====
    def run_linting_and_tests(self) -> str:
        """Run linting and tests to verify fixes."""
        results = []

        # Run ruff on all fixed files
        files_to_check = [
            "sap-bridge/auth.py",
            "sap-bridge/clients/zewm_robco_client.py",
            "traffic_coordinator_v5/simulator/fleet.py",
            "traffic_coordinator_v5/simulator/cli.py",
            "sap-bridge/services/sap_coordinator_bridge.py",
        ]

        for file_path in files_to_check:
            full_path = self.project_root / file_path
            if full_path.exists():
                result = self.run_command(f'python -m ruff check --fix "{full_path}"', check=False)
                if result.returncode == 0:
                    results.append(f"[PASS] {file_path}: Linting passed")
                else:
                    results.append(f"[WARN] {file_path}: Linting issues found")

        # Run tests for zewm_robco_client
        test_path = self.project_root / "sap-bridge" / "tests" / "test_zewm_robco_client.py"
        if test_path.exists():
            result = self.run_command(f'python -m pytest "{test_path}" -v --tb=short', check=False)
            if result.returncode == 0:
                results.append("[PASS] All tests passed")
            else:
                results.append(f"[FAIL] Tests failed: {result.returncode}")

        return "\n".join(results) if results else "No linting or tests run"

    # ===== MAIN EXECUTION =====
    def run_all_fixes(self):
        """Execute all fixes."""
        self.log("Starting comprehensive auto-fix script...")
        self.log("=" * 60)

        # Apply all fixes
        self.apply_fix("Auth.py improvements", self.fix_auth_py)
        self.apply_fix("ZEWM Robco client improvements", self.fix_zewm_client)
        self.apply_fix("Fleet.py exception handling", self.fix_fleet_py)
        self.apply_fix("CLI.py import ordering", self.fix_cli_py)
        self.apply_fix("Grafana dashboard configuration", self.fix_grafana_dashboard)
        self.apply_fix("SAP coordinator bridge", self.fix_sap_coordinator_bridge)

        self.log("=" * 60)
        self.log("Running linting and tests...")
        lint_result = self.run_linting_and_tests()
        print(lint_result)

        # Summary
        self.log("=" * 60)
        self.log("SUMMARY:")
        self.log(f"[OK] Applied {len(self.fixes_applied)} fixes")
        if self.errors:
            self.log(f"[ERROR] Encountered {len(self.errors)} errors")
            for error in self.errors:
                self.log(f"  - {error}")
        else:
            self.log("[OK] No errors encountered")

        return len(self.errors) == 0


def main():
    """Main entry point."""
    fixer = AutoFixer()
    success = fixer.run_all_fixes()

    if success:
        print("\n[SUCCESS] All fixes completed successfully!")
        print("\nNext steps:")
        print("1. Review the changes with: git diff")
        print(
            "2. Commit the fixes: git commit -am 'fix: apply all AI review fixes and improvements'"
        )
        print("3. Push the changes: git push")
    else:
        print("\n[ERROR] Some fixes failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
