#!/usr/bin/env python3
"""
验证所有修复是否已正确应用
"""

import json
import os
import sys
from pathlib import Path


def check_import(module_name, file_path):
    """检查模块是否能导入"""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            return False, f"Failed to load module spec: {file_path}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True, f"[OK] {module_name} import successful"
    except Exception as e:
        return False, f"[ERROR] {module_name} import failed: {e}"


def check_file_exists(file_path):
    """检查文件是否存在"""
    path = Path(file_path)
    if path.exists():
        return True, f"[OK] {file_path} exists"
    else:
        return False, f"[WARN] {file_path} does not exist"


def check_config_validity(config_path):
    """检查配置文件是否有效"""
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        required_keys = ["processes", "monitoring"]
        for key in required_keys:
            if key not in config:
                return False, f"配置缺少必要键: {key}"

        processes = config.get("processes", [])
        if not isinstance(processes, list):
            return False, "processes 必须是列表"

        for i, proc in enumerate(processes):
            if not isinstance(proc, dict):
                return False, f"进程 {i} 必须是字典"

            required_proc_keys = ["name", "command"]
            for key in required_proc_keys:
                if key not in proc:
                    return False, f"进程 {i} 缺少键: {key}"

        return True, f"[OK] Monitor config loaded ({len(processes)} processes)"

    except json.JSONDecodeError as e:
        return False, f"JSON解析失败: {e}"
    except Exception as e:
        return False, f"配置加载失败: {e}"


def check_fix_applied(file_path, check_strings):
    """检查特定修复是否已应用"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        results = []
        for check_str, description in check_strings:
            if check_str in content:
                results.append(f"[OK] {description}")
            else:
                results.append(f"[MISSING] {description} not found")

        return results
    except Exception as e:
        return [f"[ERROR] File read failed: {e}"]


def main():
    print("=== Verify Auto-fix and Monitoring System ===")
    print()

    print("1. Checking core scripts...")
    success, msg = check_import("auto_fix_all", "auto_fix_all.py")
    print(f"   {msg}")

    success, msg = check_import("monitor_catpaw", "monitor_catpaw.py")
    print(f"   {msg}")

    print()
    print("2. Checking configuration files...")
    success, msg = check_config_validity("catpaw_monitor_config.json")
    print(f"   {msg}")

    print()
    print("3. Checking key files...")
    files_to_check = [
        ("auto_fix_all.py", "Auto-fix script"),
        ("monitor_catpaw.py", "Monitor script"),
        ("catpaw_monitor_config.json", "Monitor config"),
        ("setup_catpaw_monitor.bat", "Setup script"),
        ("cleanup_temp_files.bat", "Cleanup script"),
        ("README_CatPaw_Monitor.md", "Monitor docs"),
    ]

    for file_path, description in files_to_check:
        exists, msg = check_file_exists(file_path)
        print(f"   {msg} ({description})")

    print()
    print("4. Checking if key fixes are applied...")

    auth_checks = [
        ("import threading", "Threading import"),
        ("self._lock = threading.Lock()", "Thread lock"),
        ("return token.decode() if isinstance(token, bytes) else token", "Bytes decode fix"),
    ]

    auth_results = check_fix_applied("sap-bridge/auth.py", auth_checks)
    for result in auth_results:
        print(f"   {result}")

    client_checks = [
        ('str(v).replace("\'", "\'\'")', "SQL injection protection"),
        ("if not base_url or base_url == DEFAULT_BASE_URL:", "Config validation improved"),
        ("import json", "JSON import"),
    ]

    client_results = check_fix_applied("sap-bridge/clients/zewm_robco_client.py", client_checks)
    for result in client_results:
        print(f"   {result}")

    print()
    print("5. Checking batch scripts...")
    for script in ["setup_catpaw_monitor.bat", "cleanup_temp_files.bat"]:
        if os.path.exists(script):
            try:
                with open(script, encoding="utf-8") as f:
                    content = f.read()
                if "@echo off" in content:
                    print(f"   [OK] {script} format correct")
                else:
                    print(f"   [WARN] {script} format may be incorrect")
            except:
                print(f"   [WARN] {script} cannot be read")
        else:
            print(f"   [ERROR] {script} does not exist")

    print()
    print("=== Verification Complete ===")
    print()
    print("Next steps:")
    print("1. Run auto-fix: python auto_fix_all.py")
    print("2. Setup monitoring: setup_catpaw_monitor.bat")
    print("3. Start monitoring: python monitor_catpaw.py")
    print("4. Cleanup temp files: cleanup_temp_files.bat")

    return 0


if __name__ == "__main__":
    sys.exit(main())
