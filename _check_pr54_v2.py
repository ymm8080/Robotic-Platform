"""Check PR #54 for all comments and their timestamps."""
import subprocess, json, sys

result = subprocess.run(
    ["gh", "pr", "view", "54", "--json", "comments,commits,state", "--repo", "ymm8080/Robotic-Platform"],
    capture_output=True, cwd=r"d:\EWM Robot\Robotic Platform Codes"
)
data = json.loads(result.stdout.decode("utf-8"))
print(f"PR state: {data['state']}")
print(f"Commits: {len(data['commits'])}")
for c in data['commits']:
    print(f"  {c['oid'][:8]} - {c['messageHeadline']}")
print(f"\nComments: {len(data['comments'])}")
for i, c in enumerate(data['comments']):
    print(f"\n=== Comment {i+1} by {c['author']['login']} at {c['createdAt']} ===")
    # Just print first 500 chars to see if there are new reviews
    body = c["body"][:500]
    sys.stdout.buffer.write(body.encode("utf-8"))
    sys.stdout.buffer.write(b"\n...\n")
