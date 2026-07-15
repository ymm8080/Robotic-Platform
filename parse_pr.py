import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

with open("pr25_comments.json", "rb") as f:
    raw = f.read()

for enc in ["utf-16", "utf-16-le", "utf-16-be", "latin-1", "cp1252"]:
    try:
        text = raw.decode(enc)
        data = json.loads(text)
        break
    except (UnicodeDecodeError, json.JSONDecodeError):
        continue
else:
    print("Could not decode file")
    exit(1)

comments = data.get("comments", [])
print(f"Total comments: {len(comments)}")
for i, c in enumerate(comments):
    author = c.get("author", {}).get("login", "unknown")
    body = c.get("body", "")
    print(f"=== Comment {i + 1} | Author: {author} ===")
    print(body[:5000])
    print()
