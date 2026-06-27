"""DeepSeek AI Review for GitHub Actions."""
import json
import os
import sys
import urllib.request

DIFF = os.environ.get("DIFF", "")
if not DIFF:
    print("No diff found, skipping review")
    sys.exit(0)

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
            "content": f"Review this diff:\n\n{json.dumps(DIFF)}",
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
        "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
    },
)
resp = json.loads(
    urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
)
review = resp["choices"][0]["message"]["content"]
with open("review_output.md", "w", encoding="utf-8") as f:
    f.write(review)
print("Review generated")
