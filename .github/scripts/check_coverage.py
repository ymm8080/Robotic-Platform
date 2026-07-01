#!/usr/bin/env python3
"""Check code coverage against a threshold.

Reads a coverage.py XML report (default: coverage.xml in the current directory),
prints the total coverage and a per-file breakdown, then exits non-zero if the
total line coverage is below the threshold.

Lives in a separate file so the workflow step does not rely on a multi-line
``python -c`` string (whose YAML indentation leaks into the Python source and
triggers ``IndentationError: unexpected indent``).

Usage:
    python .github/scripts/check_coverage.py [coverage.xml] [threshold]
"""
import sys
import xml.etree.ElementTree as ET

# Force UTF-8 output so emoji/unicode markers don't crash on non-UTF-8 consoles
# (harmless on Ubuntu CI, which is already UTF-8).
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

DEFAULT_THRESHOLD = 0.80


def main(argv: list[str]) -> int:
    coverage_file = argv[1] if len(argv) > 1 else "coverage.xml"
    threshold = float(argv[2]) if len(argv) > 2 else DEFAULT_THRESHOLD

    try:
        tree = ET.parse(coverage_file)
    except FileNotFoundError:
        print(f"ERROR: coverage report not found: {coverage_file}", file=sys.stderr)
        return 1
    except ET.ParseError as exc:
        print(f"ERROR: could not parse {coverage_file}: {exc}", file=sys.stderr)
        return 1

    root = tree.getroot()
    line_rate = float(root.attrib.get("line-rate", 0))
    pct = line_rate * 100

    print(f"Total coverage: {pct:.1f}%")

    # Per-file breakdown
    classes = sorted(
        root.findall(".//class"),
        key=lambda c: c.attrib.get("filename", ""),
    )
    for cls in classes:
        filename = cls.attrib.get("filename", "?")
        file_rate = float(cls.attrib.get("line-rate", 1))
        print(f"  {filename:45} {file_rate * 100:5.1f}%")

    if line_rate < threshold:
        print(
            f"❌ Coverage {pct:.1f}% below threshold {threshold * 100:.0f}%",
            file=sys.stderr,
        )
        return 1

    print(f"✅ Coverage above {threshold * 100:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
