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
                "a concise, actionable review in Chinese. Focus on: 1) bugs and "
                "logic errors 2) security issues 3) performance concerns 4) code "
                "style best practices. Be specific - reference line numbers and "
                "suggest fixes. If the code looks good, say so briefly."
            ),
        },
        {
            "role": "user",
            "content": f"Review this diff:\n\n{diff}",
        },
    ],
    "max_tokens": 4096,
    "temperature": 0.3,
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
    with open("review_output.md", "w", encoding="utf-8") as f:
        f.write(review)
    print("Review generated successfully")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    body = e.read().decode("utf-8")
    print(f"Response: {body[:500]}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
