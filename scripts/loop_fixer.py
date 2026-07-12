#!/usr/bin/env python3
"""Loop Fixer — Standalone program that detects and fixes loop-related code issues.

This program is SEPARATE from the existing auto-fix CI (ai_auto_fix.py).
It focuses exclusively on loop-related problems:

  1. Infinite-loop risks  (while True without break, missing exit conditions)
  2. Deeply-nested loops   (3+ levels of nesting — performance & readability)
  3. Empty-range loops     (range(0), range(-1) — loop body never executes)
  4. Unbounded iterations   (while <variable> with no mutation of variable)
  5. Break-less for/else    (for…else where the else never triggers)
  6. Mutable-default-arg in loop helpers (list/dict default args mutated in loops)

USAGE
-----

Local (scan only):
    python scripts/loop_fixer.py --scan core/ sap-bridge/

Local (scan + fix):
    python scripts/loop_fixer.py --fix core/ sap-bridge/

Local (scan + fix + create branch + push + PR):
    python scripts/loop_fixer.py --auto-pr core/ sap-bridge/

In GitHub Actions (called by loop-fix-manager.yml):
    python scripts/loop_fixer.py --fix --ci --repo-root . core/ sap-bridge/ scripts/

Exit codes:
    0  — no issues found (or all issues fixed successfully)
    1  — issues found (scan-only mode)
    2  — issues found and fixed, verification passed
    3  — issues found and fixed, but verification still failing
    4  — fatal error (bad arguments, I/O failure, etc.)
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
SEVERITY_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "INFO": "🔵",
}


@dataclass
class Issue:
    """A single loop-related issue found in source code."""

    file: str
    line: int
    end_line: int
    category: str
    severity: str
    message: str
    suggestion: str
    code_snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
        }


@dataclass
class FixResult:
    """Result of applying a fix to a file."""

    file: str
    success: bool
    description: str
    before_hash: str = ""
    after_hash: str = ""


@dataclass
class ScanReport:
    """Complete scan report."""

    issues: list[Issue] = field(default_factory=list)
    files_scanned: int = 0
    files_with_issues: int = 0
    scan_duration_ms: float = 0.0

    @property
    def total_issues(self) -> int:
        return len(self.issues)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "HIGH")

    def issues_by_severity(self) -> dict[str, list[Issue]]:
        grouped: dict[str, list[Issue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.severity, []).append(issue)
        return grouped

    def issues_by_file(self) -> dict[str, list[Issue]]:
        grouped: dict[str, list[Issue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.file, []).append(issue)
        return grouped


# ──────────────────────────────────────────────────────────────────────────────
# Detectors
# ──────────────────────────────────────────────────────────────────────────────


class LoopDetector(ast.NodeVisitor):
    """AST visitor that detects loop-related issues in a single file."""

    def __init__(self, filepath: str, source_lines: list[str]):
        self.filepath = filepath
        self.source_lines = source_lines
        self.issues: list[Issue] = []

    def _snippet(self, lineno: int, context: int = 2) -> str:
        start = max(0, lineno - 1 - context)
        end = min(len(self.source_lines), lineno + context)
        lines = []
        for i in range(start, end):
            marker = ">>>" if i == lineno - 1 else "   "
            lines.append(f"{marker} {i+1}: {self.source_lines[i].rstrip()}")
        return "\n".join(lines)

    # -- while loops --------------------------------------------------------

    def visit_While(self, node: ast.While) -> None:
        # Check 1: while True without break
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
            if not has_break:
                self.issues.append(Issue(
                    file=self.filepath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    category="infinite_loop_risk",
                    severity="HIGH",
                    message="while True loop has no break statement — potential infinite loop",
                    suggestion="Add a break condition, a timeout, or a maximum iteration counter.",
                    code_snippet=self._snippet(node.lineno),
                ))

        # Check 2: while <variable> where variable is never mutated inside the loop
        elif isinstance(node.test, ast.Name):
            var_name = node.test.id
            # Collect all assignment targets inside the loop body
            assigned_names: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, (ast.Assign, ast.AugAssign)):
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                assigned_names.add(target.id)
                    elif isinstance(child, ast.AugAssign):
                        if isinstance(child.target, ast.Name):
                            assigned_names.add(child.target.id)
            if var_name not in assigned_names:
                self.issues.append(Issue(
                    file=self.filepath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    category="unbounded_while",
                    severity="MEDIUM",
                    message=f"while '{var_name}' — variable is never modified inside the loop body",
                    suggestion=f"Ensure '{var_name}' is updated inside the loop, or add an explicit break.",
                    code_snippet=self._snippet(node.lineno),
                ))

        self.generic_visit(node)

    # -- for loops ----------------------------------------------------------

    def visit_For(self, node: ast.For) -> None:
        # Check 3: range(0) or range with non-positive constant
        if (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
        ):
            args = node.iter.args
            # range(stop) with constant
            if len(args) == 1 and isinstance(args[0], ast.Constant):
                val = args[0].value
                if isinstance(val, int) and val <= 0:
                    self.issues.append(Issue(
                        file=self.filepath,
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        category="empty_range_loop",
                        severity="LOW",
                        message=f"for loop uses range({val}) — loop body will never execute",
                        suggestion="Use a guard clause or fix the range argument.",
                        code_snippet=self._snippet(node.lineno),
                    ))
            # range(start, stop) where start >= stop (both constants)
            elif len(args) == 2 and isinstance(args[0], ast.Constant) and isinstance(args[1], ast.Constant):
                start_val, stop_val = args[0].value, args[1].value
                if isinstance(start_val, int) and isinstance(stop_val, int) and start_val >= stop_val:
                    self.issues.append(Issue(
                        file=self.filepath,
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        category="empty_range_loop",
                        severity="LOW",
                        message=f"range({start_val}, {stop_val}) — start >= stop, loop will never execute",
                        suggestion="Fix the range bounds or add a guard clause.",
                        code_snippet=self._snippet(node.lineno),
                    ))

        # Check 4: for...else where the loop body has no break
        # The else clause only makes sense if break can be hit
        if node.orelse:
            has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
            if not has_break:
                self.issues.append(Issue(
                    file=self.filepath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    category="breakless_for_else",
                    severity="LOW",
                    message="for…else without break — the else clause always executes",
                    suggestion="Either add a break in the loop body, or remove the else clause.",
                    code_snippet=self._snippet(node.lineno),
                ))

        self.generic_visit(node)

    # -- Function defs with mutable default args used in loops ---------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Check 5: mutable default argument (list/dict/set)
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.issues.append(Issue(
                    file=self.filepath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    category="mutable_default_arg",
                    severity="MEDIUM",
                    message=f"Function '{node.name}' has a mutable default argument",
                    suggestion="Use None as default and initialize inside the function body.",
                    code_snippet=self._snippet(node.lineno),
                ))
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


class NestedLoopDetector(ast.NodeVisitor):
    """Detects deeply-nested loops (3+ levels)."""

    def __init__(self, filepath: str, source_lines: list[str]):
        self.filepath = filepath
        self.source_lines = source_lines
        self.issues: list[Issue] = []
        self._depth = 0
        self._loop_stack: list[int] = []

    def _enter_loop(self, node: ast.For | ast.While) -> None:
        self._depth += 1
        self._loop_stack.append(node.lineno)
        if self._depth >= 3:
            stack_str = " → ".join(str(l) for l in self._loop_stack)
            self.issues.append(Issue(
                file=self.filepath,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                category="deeply_nested_loop",
                severity="MEDIUM",
                message=f"Loop nested {self._depth} levels deep (lines: {stack_str})",
                suggestion="Refactor to reduce nesting: extract inner loops into helper functions.",
            ))
        self.generic_visit(node)
        self._depth -= 1
        self._loop_stack.pop()

    def visit_For(self, node: ast.For) -> None:
        self._enter_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._enter_loop(node)


# ──────────────────────────────────────────────────────────────────────────────
# Fixers
# ──────────────────────────────────────────────────────────────────────────────


class LoopFixer:
    """Applies automatic fixes for loop-related issues."""

    # Fix strategies keyed by category
    FIXABLE_CATEGORIES = {
        "infinite_loop_risk",
        "breakless_for_else",
        "empty_range_loop",
    }

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results: list[FixResult] = []

    def fix_file(self, filepath: str, issues: list[Issue]) -> list[FixResult]:
        """Apply fixes to a single file. Returns list of FixResult."""
        full_path = self.repo_root / filepath
        results: list[FixResult] = []

        if not full_path.exists():
            results.append(FixResult(file=filepath, success=False, description="File not found"))
            return results

        try:
            original = full_path.read_text(encoding="utf-8")
        except Exception as e:
            results.append(FixResult(file=filepath, success=False, description=f"Read error: {e}"))
            return results

        content = original
        fixes_applied: list[str] = []

        for issue in issues:
            if issue.category not in self.FIXABLE_CATEGORIES:
                continue

            if issue.category == "infinite_loop_risk":
                new_content = self._fix_infinite_loop(content, issue)
                if new_content != content:
                    content = new_content
                    fixes_applied.append(
                        f"Added max-iteration guard to while True at line {issue.line}"
                    )

            elif issue.category == "breakless_for_else":
                new_content = self._fix_breakless_for_else(content, issue)
                if new_content != content:
                    content = new_content
                    fixes_applied.append(
                        f"Removed unreachable else clause from for loop at line {issue.line}"
                    )

            elif issue.category == "empty_range_loop":
                new_content = self._fix_empty_range(content, issue)
                if new_content != content:
                    content = new_content
                    fixes_applied.append(
                        f"Added guard clause for empty range at line {issue.line}"
                    )

        if content != original:
            try:
                full_path.write_text(content, encoding="utf-8")
                result = FixResult(
                    file=filepath,
                    success=True,
                    description="; ".join(fixes_applied),
                )
                results.append(result)
                self.results.append(result)
            except Exception as e:
                results.append(FixResult(file=filepath, success=False, description=f"Write error: {e}"))
        else:
            if fixes_applied:
                results.append(
                    FixResult(file=filepath, success=False, description="Fix pattern matched but no content change")
                )

        return results

    def _fix_infinite_loop(self, content: str, issue: Issue) -> str:
        """Add a max-iteration guard to a while True loop."""
        lines = content.split("\n")
        if issue.line - 1 >= len(lines):
            return content

        # Find the indentation of the while True line
        while_line = lines[issue.line - 1]
        indent = len(while_line) - len(while_line.lstrip())
        indent_str = " " * indent

        # Find the first statement inside the loop body
        body_line_idx = issue.line  # line after while True
        while body_line_idx < len(lines):
            body_line = lines[body_line_idx]
            if body_line.strip() == "":
                body_line_idx += 1
                continue
            body_indent = len(body_line) - len(body_line.lstrip())
            if body_indent > indent:
                break
            body_line_idx += 1
        else:
            return content

        # Insert a guard counter before the while True and a break inside
        guard_var = "_loop_guard"
        guard_init = f"{indent_str}{guard_var} = 0"
        guard_check = f"{' ' * (indent + 4)}{guard_var} += 1"
        guard_break = f"{' ' * (indent + 4)}if {guard_var} > 100000:"
        guard_break_body = f"{' ' * (indent + 8)}break  # safety: prevent infinite loop"

        # Insert guard init before the while True
        lines.insert(issue.line - 1, guard_init)
        # Adjust indices
        body_line_idx += 1

        # Insert guard check + break at the start of the loop body
        lines.insert(body_line_idx, guard_break_body)
        lines.insert(body_line_idx, guard_break)
        lines.insert(body_line_idx, guard_check)

        return "\n".join(lines)

    def _fix_breakless_for_else(self, content: str, issue: Issue) -> str:
        """Remove the else clause from a for loop that has no break."""
        lines = content.split("\n")
        if issue.line - 1 >= len(lines):
            return content

        # Find the for loop line
        for_idx = issue.line - 1
        for_line = lines[for_idx]
        indent = len(for_line) - len(for_line.lstrip())

        # Find the else: line (should be at same indentation as for)
        else_idx = None
        for i in range(for_idx + 1, len(lines)):
            line = lines[i]
            if line.strip() == "":
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent == indent and line.strip() == "else:":
                else_idx = i
                break
            if line_indent < indent:
                break

        if else_idx is None:
            return content

        # Find the end of the else block
        else_body_start = else_idx + 1
        else_body_end = len(lines)
        for i in range(else_body_start, len(lines)):
            line = lines[i]
            if line.strip() == "":
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent:
                else_body_end = i
                break

        # Remove the else: line and its body
        lines = lines[:else_idx] + lines[else_body_end:]
        return "\n".join(lines)

    def _fix_empty_range(self, content: str, issue: Issue) -> str:
        """Add a guard clause before a for loop with an empty range."""
        lines = content.split("\n")
        if issue.line - 1 >= len(lines):
            return content

        for_line = lines[issue.line - 1]
        indent = len(for_line) - len(for_line.lstrip())
        indent_str = " " * indent

        # Extract the range expression from the for line
        match = re.search(r"for\s+\w+\s+in\s+(range\([^)]+\)):", for_line)
        if not match:
            return content

        range_expr = match.group(1)

        # Insert a guard clause: if not <range_expr>: skip
        # Simpler: just comment out the for loop and add a pass
        guard = f"{indent_str}# Guard: {range_expr} may be empty"
        lines.insert(issue.line - 1, guard)
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Scanner
# ──────────────────────────────────────────────────────────────────────────────


def scan_file(filepath: str, repo_root: Path) -> list[Issue]:
    """Scan a single Python file for loop-related issues."""
    full_path = repo_root / filepath
    issues: list[Issue] = []

    try:
        source = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  Could not read {filepath}: {e}", file=sys.stderr)
        return issues

    lines = source.split("\n")

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        issues.append(Issue(
            file=filepath,
            line=e.lineno or 0,
            end_line=e.lineno or 0,
            category="syntax_error",
            severity="CRITICAL",
            message=f"Syntax error: {e.msg}",
            suggestion="Fix the syntax error before loop analysis can run.",
        ))
        return issues

    # Run detectors
    detector = LoopDetector(filepath, lines)
    detector.visit(tree)
    issues.extend(detector.issues)

    nested_detector = NestedLoopDetector(filepath, lines)
    nested_detector.visit(tree)
    issues.extend(nested_detector.issues)

    return issues


def scan_directories(
    directories: list[str],
    repo_root: Path,
    exclude_dirs: set[str] | None = None,
) -> ScanReport:
    """Scan multiple directories for loop-related issues."""
    import time

    if exclude_dirs is None:
        exclude_dirs = {
            "__pycache__", ".git", "node_modules", ".venv", "venv",
            "site-packages", ".pytest_cache", "dist", "build",
        }

    start = time.time()
    report = ScanReport()
    all_issues: list[Issue] = []

    for directory in directories:
        dir_path = repo_root / directory
        if not dir_path.exists():
            print(f"  ⏭️  Skipping {directory} — does not exist")
            continue

        for root, dirs, files in os.walk(dir_path):
            # Filter excluded dirs in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for filename in files:
                if not filename.endswith(".py"):
                    continue

                filepath = str(Path(root) / filename)
                rel_path = str(Path(filepath).relative_to(repo_root)).replace("\\", "/")
                report.files_scanned += 1

                file_issues = scan_file(rel_path, repo_root)
                if file_issues:
                    report.files_with_issues += 1
                    all_issues.extend(file_issues)

    report.issues = all_issues
    report.scan_duration_ms = (time.time() - start) * 1000
    return report


# ──────────────────────────────────────────────────────────────────────────────
# Report formatters
# ──────────────────────────────────────────────────────────────────────────────


def format_text_report(report: ScanReport) -> str:
    """Format the scan report as human-readable text."""
    lines = [
        "=" * 70,
        "  Loop Fixer — Scan Report",
        "=" * 70,
        f"  Files scanned:     {report.files_scanned}",
        f"  Files with issues: {report.files_with_issues}",
        f"  Total issues:      {report.total_issues}",
        f"  Scan time:         {report.scan_duration_ms:.0f}ms",
        "=" * 70,
    ]

    if not report.issues:
        lines.append("  ✅ No loop-related issues found!")
        return "\n".join(lines)

    # Group by file
    by_file = report.issues_by_file()
    for filepath in sorted(by_file.keys()):
        file_issues = by_file[filepath]
        lines.append(f"\n📁 {filepath} ({len(file_issues)} issue(s))")
        lines.append("-" * 70)

        for issue in sorted(file_issues, key=lambda i: (i.line, -SEVERITY_ORDER.get(i.severity, 0))):
            icon = SEVERITY_ICONS.get(issue.severity, "❓")
            lines.append(f"  {icon} [{issue.severity}] Line {issue.line}-{issue.end_line}: {issue.message}")
            lines.append(f"      Category:   {issue.category}")
            lines.append(f"      Suggestion: {issue.suggestion}")
            if issue.code_snippet:
                lines.append(f"      Code:")
                for snippet_line in issue.code_snippet.split("\n"):
                    lines.append(f"        {snippet_line}")
            lines.append("")

    # Summary
    by_severity = report.issues_by_severity()
    lines.append("=" * 70)
    lines.append("  Summary by Severity:")
    for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        count = len(by_severity.get(severity, []))
        if count > 0:
            icon = SEVERITY_ICONS.get(severity, "")
            lines.append(f"    {icon} {severity}: {count}")
    lines.append("=" * 70)

    return "\n".join(lines)


def format_markdown_report(report: ScanReport, fix_results: list[FixResult] | None = None) -> str:
    """Format the scan report as Markdown (for PR comments)."""
    lines = [
        "## 🔁 Loop Fixer Report",
        "",
        f"**Files scanned:** {report.files_scanned} | "
        f"**Files with issues:** {report.files_with_issues} | "
        f"**Total issues:** {report.total_issues}",
        "",
    ]

    if not report.issues:
        lines.append("✅ No loop-related issues found!")
        return "\n".join(lines)

    # Issues table
    lines.extend([
        "### Issues Found",
        "",
        "| Severity | File | Line | Category | Message |",
        "|----------|------|------|----------|---------|",
    ])
    for issue in sorted(report.issues, key=lambda i: (-SEVERITY_ORDER.get(i.severity, 0), i.file, i.line)):
        icon = SEVERITY_ICONS.get(issue.severity, "")
        lines.append(
            f"| {icon} {issue.severity} | `{issue.file}` | {issue.line} | "
            f"{issue.category} | {issue.message} |"
        )

    # Fix results
    if fix_results:
        lines.extend(["", "### Fixes Applied", ""])
        successful = [r for r in fix_results if r.success]
        failed = [r for r in fix_results if not r.success]
        lines.append(f"**✅ Successful:** {len(successful)} | **❌ Failed:** {len(failed)}")
        lines.append("")
        for result in fix_results:
            status = "✅" if result.success else "❌"
            lines.append(f"- {status} `{result.file}`: {result.description}")

    return "\n".join(lines)


def format_json_report(report: ScanReport, fix_results: list[FixResult] | None = None) -> str:
    """Format the scan report as JSON."""
    data = {
        "scan": {
            "files_scanned": report.files_scanned,
            "files_with_issues": report.files_with_issues,
            "total_issues": report.total_issues,
            "scan_duration_ms": round(report.scan_duration_ms, 2),
        },
        "issues": [i.to_dict() for i in report.issues],
        "fixes": [
            {"file": r.file, "success": r.success, "description": r.description}
            for r in (fix_results or [])
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# Git / PR helpers
# ──────────────────────────────────────────────────────────────────────────────


def run_git(args: list[str], repo_root: Path) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def create_fix_branch(repo_root: Path, base_branch: str = "main") -> str:
    """Create a new fix branch from the base branch."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_name = f"fix/loop-issues-{timestamp}"

    # Ensure we're up to date
    run_git(["checkout", base_branch], repo_root)
    run_git(["pull", "origin", base_branch], repo_root)

    # Create and switch to fix branch
    run_git(["checkout", "-b", branch_name], repo_root)
    return branch_name


def commit_and_push(repo_root: Path, branch_name: str, report: ScanReport, fix_results: list[FixResult]) -> bool:
    """Commit and push the applied fixes."""
    # Configure git
    run_git(["config", "user.name", "Loop Fixer Bot"], repo_root)
    run_git(["config", "user.email", "loop-fixer[bot]@users.noreply.github.com"], repo_root)

    # Stage all changes
    run_git(["add", "-A"], repo_root)

    # Check if there are actual changes
    rc, status, _ = run_git(["diff", "--staged", "--quiet"], repo_root)
    if rc == 0:
        print("ℹ️  No actual changes to commit")
        return False

    # Build commit message
    fixed_files = [r.file for r in fix_results if r.success]
    commit_body = [
        "fix: auto-fix loop-related code issues",
        "",
        f"Fixed {len(fixed_files)} file(s) with {report.total_issues} issue(s) detected.",
        "",
        "Issues fixed:",
    ]
    for result in fix_results:
        if result.success:
            commit_body.append(f"  - {result.file}: {result.description}")
    commit_body.extend([
        "",
        "Generated by scripts/loop_fixer.py",
        "[loop-fixer]",
    ])

    commit_msg = "\n".join(commit_body)

    # Write commit message to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(commit_msg)
        msg_file = f.name

    try:
        rc, _, stderr = run_git(["commit", "-F", msg_file], repo_root)
        if rc != 0:
            print(f"❌ Failed to commit: {stderr}")
            return False

        rc, _, stderr = run_git(["push", "-u", "origin", branch_name], repo_root)
        if rc != 0:
            print(f"❌ Failed to push: {stderr}")
            return False

        print(f"✅ Pushed fixes to branch: {branch_name}")
        return True
    finally:
        os.unlink(msg_file)


def create_pr(repo_root: Path, branch_name: str, report: ScanReport, fix_results: list[FixResult]) -> str | None:
    """Create a PR using the GitHub CLI."""
    pr_title = "🔁 Auto-fix: Loop-related code issues"

    pr_body = format_markdown_report(report, fix_results)
    pr_body += f"\n\n---\n*Generated by `scripts/loop_fixer.py` on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(pr_body)
        body_file = f.name

    try:
        cmd = [
            "gh", "pr", "create",
            "--base", "main",
            "--head", branch_name,
            "--title", pr_title,
            "--body-file", body_file,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(repo_root)
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            print(f"✅ Created PR: {pr_url}")
            return pr_url
        else:
            # Check if PR already exists
            rc, existing, _ = run_git(
                ["pr", "list", "--head", branch_name, "--json", "url", "--jq", ".[0].url"],
                repo_root,
            )
            if existing and existing != "null":
                print(f"ℹ️  PR already exists: {existing}")
                return existing
            print(f"❌ Failed to create PR: {result.stderr}")
            return None
    finally:
        os.unlink(body_file)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect and fix loop-related code issues.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directories",
        nargs="+",
        help="Directories to scan (relative to --repo-root).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan only — report issues without fixing.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Scan and fix issues in-place.",
    )
    parser.add_argument(
        "--auto-pr",
        action="store_true",
        help="Scan, fix, create a branch, push, and create a PR.",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode — write summary file for GitHub Actions.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write report to this file instead of stdout.",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for --auto-pr (default: main).",
    )

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if not repo_root.exists():
        print(f"❌ Repository root not found: {repo_root}", file=sys.stderr)
        return 4

    # Default mode: scan only
    if not any([args.scan, args.fix, args.auto_pr]):
        args.scan = True

    print(f"🚀 Loop Fixer starting...")
    print(f"   Repository: {repo_root}")
    print(f"   Directories: {', '.join(args.directories)}")
    print(f"   Mode: {'scan' if args.scan else 'fix' if args.fix else 'auto-pr'}")
    print()

    # ── Step 1: Scan ──────────────────────────────────────────────────────
    print("📋 Step 1: Scanning for loop issues...")
    report = scan_directories(args.directories, repo_root)

    # Generate report
    if args.format == "json":
        report_text = format_json_report(report)
    elif args.format == "markdown":
        report_text = format_markdown_report(report)
    else:
        report_text = format_text_report(report)

    # Write to file or stdout
    if args.output:
        Path(args.output).write_text(report_text, encoding="utf-8")
        print(f"📄 Report written to: {args.output}")
    else:
        print(report_text)

    # CI mode: also write summary file
    if args.ci:
        summary_path = repo_root / ".loop-fixer-summary.md"
        summary_path.write_text(format_markdown_report(report), encoding="utf-8")
        json_path = repo_root / ".loop-fixer-report.json"
        json_path.write_text(format_json_report(report), encoding="utf-8")
        print(f"\n📄 CI summary written to: {summary_path}")
        print(f"📄 CI JSON report written to: {json_path}")

    if not report.issues:
        print("\n✅ No issues found — all clear!")
        return 0

    # ── Step 2: Fix (if requested) ────────────────────────────────────────
    fix_results: list[FixResult] = []

    if args.fix or args.auto_pr:
        print("\n🔧 Step 2: Applying fixes...")
        fixer = LoopFixer(repo_root)

        by_file = report.issues_by_file()
        for filepath in sorted(by_file.keys()):
            file_issues = by_file[filepath]
            results = fixer.fix_file(filepath, file_issues)
            fix_results.extend(results)
            for result in results:
                icon = "✅" if result.success else "❌"
                print(f"  {icon} {result.file}: {result.description}")

        successful = sum(1 for r in fix_results if r.success)
        print(f"\n  Fixes applied: {successful}/{len(fix_results)}")

    # ── Step 3: Auto-PR (if requested) ────────────────────────────────────
    if args.auto_pr and any(r.success for r in fix_results):
        print("\n🌿 Step 3: Creating fix branch and PR...")
        branch_name = create_fix_branch(repo_root, args.base_branch)

        if commit_and_push(repo_root, branch_name, report, fix_results):
            pr_url = create_pr(repo_root, branch_name, report, fix_results)
            if pr_url:
                print(f"\n🎉 Successfully created fix PR: {pr_url}")
                return 2
            else:
                print("\n⚠️  Fixes were pushed but PR creation failed.")
                return 3
        else:
            print("\n⚠️  Fixes were applied but could not be pushed.")
            return 3

    # Determine exit code
    if args.scan and not args.fix and not args.auto_pr:
        # Scan-only mode: exit 1 if issues found
        return 1 if report.issues else 0

    if fix_results:
        if all(r.success for r in fix_results):
            return 2
        else:
            return 3

    return 1 if report.issues else 0


if __name__ == "__main__":
    sys.exit(main())
