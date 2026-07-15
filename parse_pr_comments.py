import json

with open("pr24_comments_raw.json", encoding="utf-8-sig") as f:
    comments = json.load(f)

# Get last comment only
last = comments[-1]
with open("pr24_last_comment.txt", "w", encoding="utf-8") as out:
    out.write(f"=== LAST COMMENT (#{len(comments)}) ===\n")
    out.write(f"ID: {last['id']}\n")
    out.write(f"Author: {last['user']['login']}\n")
    out.write(f"Created: {last['created_at']}\n")
    out.write(f"Body:\n{last['body']}\n")
