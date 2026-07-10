#!/usr/bin/env python3
"""Syntax-check all Python files via :mod:`ast`.

Exits non-zero if any ``.py`` file under ``sap-bridge/`` or ``scripts/`` fails
to parse. Lives in a separate file so the workflow step does not rely on a
multi-line ``python -c`` string (whose YAML indentation leaks into the Python
source and triggers ``IndentationError: unexpected indent``).
"""
import ast
import glob
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

# Resolve relative to this script so the check is cwd-independent.
REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ("sap-bridge/**/*.py", "scripts/*.py")

errors = 0
files = []
for pattern in PATTERNS:
    files.extend(REPO_ROOT.glob(pattern))

if not files:
    print(f"⚠️ No Python files found under {REPO_ROOT} for patterns {PATTERNS}", file=sys.stderr)
    sys.exit(2)

for f in sorted(files):
    with open(f, encoding="utf-8") as fh:
        try:
            ast.parse(fh.read())
        except SyntaxError as exc:
            print(f"❌ {f}: {exc}")
            errors += 1

if errors:
    print(f"\n{errors} file(s) with syntax errors", file=sys.stderr)
    sys.exit(1)

print(f"✅ All {len(files)} Python files syntactically valid")
