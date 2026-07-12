#!/usr/bin/env python3
"""AI Auto-Fix Script for GitHub Actions Self-Healing CI.

This script:
1. Re-runs the failing CI commands (ruff, pytest, syntax check)
2. Collects all error output
3. Reads the affected source files
4. Sends errors + file contents to DeepSeek API for analysis
5. Parses the AI response and applies fixes
6. Re-runs the commands to verify the fixes work
7. Writes a summary of what was fixed

Used by .github/workflows/auto-fix.yml
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Force UTF-8 output
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_SIZE = 50_000  # 50KB per file — skip huge files
MAX_TOTAL_SIZE = 200_000  # 200KB total context for API call
MAX_ERROR_LINES = 500  # Truncate error output to prevent token explosion


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Run CI commands and collect errors
# ═══════════════════════════════════════════════════════════════════════════

def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command and return (returncode, combined stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or REPO_ROOT,
            timeout=120,
        )
        output = result.stdout + "\n" + result.stderr
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT: Command exceeded 120s: {' '.join(cmd)}"
    except FileNotFoundError:
        return 1, f"NOT FOUND: {' '.join(cmd)}"
    except Exception as e:
        return 1, f"ERROR running {' '.join(cmd)}: {e}"


def collect_errors() -> dict[str, str]:
    """Run all CI checks and collect error output for each."""
    errors: dict[str, str] = {}

    # 1. Ruff lint — sap-bridge
    rc, out = run_command(
        ["ruff", "check", ".", "--config", "ruff.toml"],
        cwd=REPO_ROOT / "sap-bridge",
    )
    if rc != 0 and out.strip():
        errors["ruff_sap_bridge"] = out[:MAX_ERROR_LINES]

    # 2. Ruff lint — core/
    rc, out = run_command(["ruff", "check", "core/"])
    if rc != 0 and out.strip():
        errors["ruff_core"] = out[:MAX_ERROR_LINES]

    # 3. Ruff lint — scripts/
    rc, out = run_command(["ruff", "check", "scripts/", "--ignore", "E501"])
    if rc != 0 and out.strip():
        errors["ruff_scripts"] = out[:MAX_ERROR_LINES]

    # 4. Syntax check
    rc, out = run_command(["python", ".github/scripts/syntax_check.py"])
    if rc != 0 and out.strip():
        errors["syntax_check"] = out[:MAX_ERROR_LINES]

    # 5. pytest — core/tests/ (fast, no external deps)
    rc, out = run_command(
        ["python", "-m", "pytest", "core/tests/", "-q", "--tb=short", "--no-header"],
    )
    if rc != 0 and out.strip():
        errors["pytest_core"] = out[:MAX_ERROR_LINES]

    # 6. pytest — traffic_coordinator_v5/tests/
    rc, out = run_command(
        ["python", "-m", "pytest", "traffic_coordinator_v5/tests/", "-q", "--tb=short", "--no-header"],
    )
    if rc != 0 and out.strip():
        errors["pytest_v5"] = out[:MAX_ERROR_LINES]

    return errors


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: Extract affected file paths from error output
# ═══════════════════════════════════════════════════════════════════════════

def extract_file_paths(errors: dict[str, str]) -> set[str]:
    """Extract file paths from error output using regex."""
    paths: set[str] = set()

    # Ruff format: path:line:col: CODE message
    ruff_pattern = re.compile(r"^([a-zA-Z0-9_./\-]+\.py):\d+", re.MULTILINE)

    # Pytest format: path::function or File "path", line N
    pytest_file_pattern = re.compile(r'File "([^"]+\.py)"', re.MULTILINE)
    pytest_path_pattern = re.compile(r"^([a-zA-Z0-9_./\-]+\.py)::", re.MULTILINE)

    # Generic: any .py file mentioned
    generic_pattern = re.compile(r"([a-zA-Z0-9_./\-]+/[a-zA-Z0-9_./\-]+\.py)")

    for error_text in errors.values():
        for match in ruff_pattern.finditer(error_text):
            paths.add(match.group(1))
        for match in pytest_file_pattern.finditer(error_text):
            paths.add(match.group(1))
        for match in pytest_path_pattern.finditer(error_text):
            paths.add(match.group(1))
        for match in generic_pattern.finditer(error_text):
            candidate = match.group(1)
            # Filter out site-packages and common false positives
            if "site-packages" not in candidate and "lib/python" not in candidate:
                paths.add(candidate)

    # Filter to only files that actually exist
    valid_paths: set[str] = set()
    for p in paths:
        full = REPO_ROOT / p
        if full.exists() and full.is_file():
            valid_paths.add(p)

    return valid_paths


def read_files(file_paths: set[str]) -> dict[str, str]:
    """Read file contents for the given paths."""
    contents: dict[str, str] = {}
    total_size = 0

    for path in sorted(file_paths):
        full = REPO_ROOT / path
        try:
            size = full.stat().st_size
            if size > MAX_FILE_SIZE:
                print(f"  ⏭️  Skipping {path} ({size} bytes — too large)")
                continue
            if total_size + size > MAX_TOTAL_SIZE:
                print(f"  ⏭️  Skipping {path} (context limit reached)")
                continue
            content = full.read_text(encoding="utf-8", errors="replace")
            contents[path] = content
            total_size += size
        except Exception as e:
            print(f"  ⚠️  Could not read {path}: {e}")

    return contents


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: Call DeepSeek API for fixes
# ═══════════════════════════════════════════════════════════════════════════

def build_prompt(errors: dict[str, str], files: dict[str, str]) -> list[dict]:
    """Build the message list for the DeepSeek API."""
    error_section = []
    for check_name, output in errors.items():
        error_section.append(f"### {check_name}\n```\n{output}\n```")
    error_text = "\n\n".join(error_section)

    file_section = []
    for path, content in files.items():
        file_section.append(f"### File: {path}\n```python\n{content}\n```")
    file_text = "\n\n".join(file_section)

    system_prompt = (
        "You are an automated code fixer for a Python project (SAP EWM Robot Dispatch Platform).\n"
        "You receive CI error logs and source files. Your job is to fix the errors.\n\n"
        "CRITICAL RULES:\n"
        "1. Only fix the actual errors reported. Do not refactor or change unrelated code.\n"
        "2. Preserve existing code style, comments, and naming conventions.\n"
        "3. For ruff errors: fix the specific lint issue (unused imports, undefined names, etc.)\n"
        "4. For syntax errors: fix the syntax issue with minimal changes.\n"
        "5. For test failures: fix the source code (not the tests), unless the test itself is wrong.\n"
        "6. For import errors: add missing imports or fix import paths.\n"
        "7. Do NOT add or remove files. Only modify existing files.\n"
        "8. Return the COMPLETE fixed file content for each file that needs changes.\n\n"
        "OUTPUT FORMAT:\n"
        "Return a JSON array. Each element has:\n"
        '  {"file": "relative/path/to/file.py", "content": "complete fixed file content"}\n\n'
        "Only include files that need changes.\n"
        "The content must be the COMPLETE file content (not a diff).\n"
        "Do NOT wrap the JSON in markdown code blocks.\n"
        "Do NOT add explanatory text before or after the JSON."
    )

    user_prompt = (
        f"## CI Error Logs\n\n{error_text}\n\n"
        f"## Source Files\n\n{file_text}\n\n"
        "## Task\n\n"
        "Fix the errors above. Return a JSON array of {\"file\": ..., \"content\": ...} objects.\n"
        "Only include files that need changes. Return ONLY the JSON, no markdown."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def call_deepseek_api(messages: list[dict]) -> dict | None:
    """Call DeepSeek API and return the response."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        return None

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": 8192,
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        print("Calling DeepSeek API...")
        resp = urllib.request.urlopen(req, timeout=180)
        result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        return {"content": content, "usage": result.get("usage", {})}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP Error: {e.code} {e.reason}")
        print(f"Response: {body[:500]}")
        return None
    except Exception as e:
        print(f"Error calling DeepSeek API: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: Parse API response and apply fixes
# ═══════════════════════════════════════════════════════════════════════════

def parse_fixes(response_content: str) -> list[dict]:
    """Parse the AI response into a list of {file, content} dicts.

    Handles multiple response formats:
    - Clean JSON array
    - JSON embedded in markdown code blocks
    - JSON with surrounding text
    """
    content = response_content.strip()

    # Try 1: Direct JSON parse
    try:
        fixes = json.loads(content)
        if isinstance(fixes, list):
            return fixes
    except json.JSONDecodeError:
        pass

    # Try 2: Extract JSON from markdown code block
    code_block = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
    if code_block:
        try:
            fixes = json.loads(code_block.group(1))
            if isinstance(fixes, list):
                return fixes
        except json.JSONDecodeError:
            pass

    # Try 3: Find the first [ to the last ]
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            fixes = json.loads(content[start:end + 1])
            if isinstance(fixes, list):
                return fixes
        except json.JSONDecodeError:
            pass

    # Try 4: Single file fix as JSON object
    try:
        obj = json.loads(content)
        if isinstance(obj, dict) and "file" in obj:
            return [obj]
    except json.JSONDecodeError:
        pass

    print("WARNING: Could not parse AI response as JSON")
    print(f"Response preview: {content[:500]}")
    return []


def apply_fixes(fixes: list[dict]) -> list[str]:
    """Apply the fixes to files. Returns list of fixed file paths."""
    fixed_files: list[str] = []

    for fix in fixes:
        if not isinstance(fix, dict):
            continue

        file_path = fix.get("file", "")
        content = fix.get("content", "")

        if not file_path or not content:
            continue

        full_path = REPO_ROOT / file_path

        # Safety: only write to existing files within the repo
        if not full_path.exists():
            print(f"  ⏭️  Skipping {file_path} — does not exist")
            continue

        try:
            # Resolve and check it's within the repo
            resolved = full_path.resolve()
            if not str(resolved).startswith(str(REPO_ROOT.resolve())):
                print(f"  ⏭️  Skipping {file_path} — outside repo root")
                continue

            # Only accept .py, .ts, .tsx, .js, .yml, .yaml, .toml files
            allowed_extensions = {".py", ".ts", ".tsx", ".js", ".yml", ".yaml", ".toml"}
            if full_path.suffix not in allowed_extensions:
                print(f"  ⏭️  Skipping {file_path} — extension not allowed")
                continue

            # Read original to check if there's actually a change
            original = full_path.read_text(encoding="utf-8", errors="replace")
            if original == content:
                print(f"  ⏭️  Skipping {file_path} — no changes")
                continue

            # Write the fixed content
            full_path.write_text(content, encoding="utf-8")
            fixed_files.append(file_path)
            print(f"  ✅ Fixed: {file_path}")

        except Exception as e:
            print(f"  ❌ Error writing {file_path}: {e}")

    return fixed_files


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: Verify fixes
# ═══════════════════════════════════════════════════════════════════════════

def verify_fixes(original_errors: dict[str, str]) -> dict[str, bool]:
    """Re-run the failing checks and see which ones are now fixed."""
    results: dict[str, bool] = {}

    if "ruff_sap_bridge" in original_errors:
        rc, _ = run_command(
            ["ruff", "check", ".", "--config", "ruff.toml"],
            cwd=REPO_ROOT / "sap-bridge",
        )
        results["ruff_sap_bridge"] = rc == 0

    if "ruff_core" in original_errors:
        rc, _ = run_command(["ruff", "check", "core/"])
        results["ruff_core"] = rc == 0

    if "ruff_scripts" in original_errors:
        rc, _ = run_command(["ruff", "check", "scripts/", "--ignore", "E501"])
        results["ruff_scripts"] = rc == 0

    if "syntax_check" in original_errors:
        rc, _ = run_command(["python", ".github/scripts/syntax_check.py"])
        results["syntax_check"] = rc == 0

    if "pytest_core" in original_errors:
        rc, _ = run_command(
            ["python", "-m", "pytest", "core/tests/", "-q", "--tb=short", "--no-header"],
        )
        results["pytest_core"] = rc == 0

    if "pytest_v5" in original_errors:
        rc, _ = run_command(
            ["python", "-m", "pytest", "traffic_coordinator_v5/tests/", "-q", "--tb=short", "--no-header"],
        )
        results["pytest_v5"] = rc == 0

    return results


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    os.chdir(REPO_ROOT)

    print("=" * 60)
    print("  AI Auto-Fix — Self-Healing CI")
    print("=" * 60)

    # Step 1: Collect errors
    print("\n📋 Step 1: Collecting CI errors...")
    errors = collect_errors()

    if not errors:
        print("✅ No errors found — CI may have failed for a different reason.")
        print("   (e.g., build failure, Docker issue, external service)")
        return 0

    print(f"\nFound {len(errors)} error category(ies):")
    for name, output in errors.items():
        lines = output.strip().split("\n")
        print(f"  • {name}: {len(lines)} lines of output")

    # Step 2: Extract affected files
    print("\n📂 Step 2: Identifying affected files...")
    file_paths = extract_file_paths(errors)
    print(f"  Found {len(file_paths)} affected file(s):")
    for p in sorted(file_paths):
        print(f"    - {p}")

    if not file_paths:
        print("  No specific files identified — trying to fix from error text alone.")

    # Step 3: Read file contents
    print("\n📖 Step 3: Reading source files...")
    files = read_files(file_paths)
    print(f"  Read {len(files)} file(s) ({sum(len(c) for c in files.values())} bytes)")

    if not files and not errors:
        print("  Nothing to fix — no errors and no files.")
        return 0

    # Step 4: Call DeepSeek API
    print("\n🤖 Step 4: Calling DeepSeek API for fixes...")
    messages = build_prompt(errors, files)
    response = call_deepseek_api(messages)

    if not response:
        print("❌ Failed to get response from DeepSeek API")
        return 1

    print(f"  Token usage: {response.get('usage', {})}")

    # Step 5: Parse and apply fixes
    print("\n🔧 Step 5: Applying fixes...")
    fixes = parse_fixes(response["content"])
    print(f"  Parsed {len(fixes)} fix(es) from AI response")

    if not fixes:
        print("❌ No fixes could be parsed from AI response")
        # Save raw response for debugging
        Path(REPO_ROOT / ".auto-fix-raw-response.txt").write_text(
            response["content"], encoding="utf-8"
        )
        return 1

    fixed_files = apply_fixes(fixes)

    if not fixed_files:
        print("❌ No files were actually changed")
        return 1

    # Step 6: Verify fixes
    print("\n✅ Step 6: Verifying fixes...")
    verification = verify_fixes(errors)

    passed = sum(1 for v in verification.values() if v)
    total = len(verification)

    print(f"\n  Verification: {passed}/{total} checks now passing")
    for check, ok in verification.items():
        status = "✅ PASS" if ok else "❌ STILL FAILING"
        print(f"    {check}: {status}")

    # Step 7: Write summary
    print("\n📝 Step 7: Writing summary...")
    summary_lines = [
        "## Auto-Fix Summary",
        "",
        f"**Fixed {len(fixed_files)} file(s):**",
        "",
    ]
    for f in fixed_files:
        summary_lines.append(f"- `{f}`")

    summary_lines.extend([
        "",
        f"**Verification: {passed}/{total} checks passing**",
        "",
    ])
    for check, ok in verification.items():
        status = "✅" if ok else "⚠️"
        summary_lines.append(f"- {status} {check}")

    summary_lines.extend([
        "",
        f"**Files fixed by DeepSeek AI**",
    ])

    summary = "\n".join(summary_lines)
    Path(REPO_ROOT / ".auto-fix-summary.txt").write_text(summary, encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"  ✅ Auto-fix complete: {len(fixed_files)} file(s) fixed")
    print(f"  Verification: {passed}/{total} checks passing")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
