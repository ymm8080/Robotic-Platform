"""DeepSeek AI Review for GitHub Actions.

Reads diff from pr_diff.txt, calls DeepSeek API, writes review_output.md.
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Read diff from file (avoids env var size limits)
try:
    with open("pr_diff.txt") as f:
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

payload = json.dumps({
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
                "(style, minor perf). Only report 'must fix' issues as bugs."
            ),
        },
        {
            "role": "user",
            "content": f"Review this diff carefully. Only report issues that actually exist in the code:\n\n{diff}",
        },
    ],
    "max_tokens": 4096,
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
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read().decode("utf-8"))
    review = result["choices"][0]["message"]["content"]

    # Append structured marker for auto-fix.sh to parse
    issue_keywords = [
        "must fix", "必须修复", "bug", "安全问题",
        "逻辑错误", "性能问题", "critical", "严重",
        "错误", "缺陷", "漏洞", "risk", "danger",
    ]
    has_issues = any(kw in review.lower() for kw in issue_keywords)
    marker = "<!--AUTOFIX:HAS_ISSUES-->" if has_issues else "<!--AUTOFIX:CLEAN-->"

    with open("review_output.md", "w", encoding="utf-8") as f:
        f.write(review)
        f.write(f"\n\n{marker}\n")
    print(f"Review generated successfully (marker: {marker})")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    body = e.read().decode("utf-8")
    print(f"Response: {body[:500]}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
