"""DeepSeek AI Review for GitHub Actions.

Reads diff from pr_diff.txt, calls DeepSeek API, writes review_output.md.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

# Read diff from file (avoids env var size limits)
try:
    with open("pr_diff.txt", encoding="utf-8") as f:
        diff = f.read()
except FileNotFoundError:
    print("No pr_diff.txt found, skipping review")
    sys.exit(0)

if not diff.strip():
    print("Empty diff, skipping review")
    sys.exit(0)

api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not set")
    sys.exit(1)

payload = json.dumps(
    {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert code reviewer. Analyze the PR diff and provide "
                    "a concise, actionable review in Chinese.\n\n"
                    "CRITICAL RULES:\n"
                    "1. Read EVERY line of the diff carefully before commenting. "
                    "Only report issues that ACTUALLY exist in the code shown in the diff.\n"
                    "2. Do NOT hallucinate code that is not present. If you claim a line "
                    "has a certain pattern, verify it exists in the diff first.\n"
                    "3. If the code already contains comments explaining a design decision, "
                    "do NOT suggest changing that decision. Respect documented intent.\n"
                    "4. If a suggested fix is ALREADY implemented in the code (e.g., "
                    "try/except, input validation, timing fixes), do NOT report it as an issue.\n"
                    "5. Focus on: 1) actual bugs and logic errors 2) security issues "
                    "3) performance concerns 4) code style. Be specific - reference "
                    "actual line content. If the code looks good, say so briefly.\n"
                    "6. Distinguish between 'must fix' (bugs, security) and 'suggestion' "
                    "(style, minor perf). Only report 'must fix' issues as bugs.\n"
                    "7. If there are NO must-fix bugs, do NOT include a '必须修复' section. "
                    "Only include '必须修复的问题' section when there are REAL bugs that "
                    "would cause runtime errors, security vulnerabilities, or data loss. "
                    "Style improvements and design suggestions should go in '建议改进' only.\n"
                    "8. If the code has no must-fix issues, start the review with "
                    "'<!--AUTOFIX:CLEAN-->' marker on the first line."
                ),
            },
            {
                "role": "user",
                "content": f"Review this diff carefully. Only report issues that actually exist in the code:\n\n{diff}",
            },
        ],
        "max_tokens": 8192,
        "temperature": 0.1,
    }
).encode("utf-8")

req = urllib.request.Request(
    "https://api.deepseek.com/chat/completions",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    },
)

try:
    resp = urllib.request.urlopen(req, timeout=180)
    result = json.loads(resp.read().decode("utf-8"))

    # Guard against unexpected API response structure (KeyError protection)
    choices = result.get("choices", [])
    if not choices:
        error_msg = result.get("error", {}).get("message", "Unknown error")
        print(f"ERROR: API returned no choices. Message: {error_msg}")
        sys.exit(1)

    review = choices[0].get("message", {}).get("content", "")
    if not review:
        print("ERROR: API returned empty review content")
        sys.exit(1)

    # Append structured marker for auto-fix.sh to parse.
    # Check if the "必须修复" section has actual numbered items (e.g., "1. **...**").
    # The section header alone is not enough — the AI always includes it.
    # We look for numbered list items under a "必须修复" heading.
    # Match "必须修复" section with at least one numbered item after it
    must_fix_pattern = r"必须修复[^#]*?\d+\.\s+\*\*"
    has_issues = bool(re.search(must_fix_pattern, review, re.DOTALL))
    marker = "<!--AUTOFIX:HAS_ISSUES-->" if has_issues else "<!--AUTOFIX:CLEAN-->"

    with open("review_output.md", "w", encoding="utf-8") as f:
        f.write(review)
        f.write(f"\n\n{marker}\n")
    print(f"Review generated successfully (marker: {marker})")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    # Read body but do NOT print full response — DeepSeek error responses
    # may echo back parts of the request headers in some edge cases,
    # which would leak the API key into CI logs.
    body = e.read().decode("utf-8", errors="replace")
    safe_preview = body[:200].replace("\n", " ")
    print(f"Response (sanitized, first 200 chars): {safe_preview}")
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Network Error: {e.reason}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    sys.exit(1)
