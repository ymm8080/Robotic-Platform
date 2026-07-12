"""Fix PR #46 AI review round 5: address remaining minor suggestions."""
import subprocess
import sys
import os

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

BRANCH = "fix/pr28-ai-review-final"


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(f"$ {cmd}")
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(f"  STDERR: {r.stderr.strip()}", file=sys.stderr)
    if check and r.returncode != 0:
        print(f"  EXIT CODE: {r.returncode}", file=sys.stderr)
        sys.exit(1)
    return r


run("git stash", check=False)
run(f"git checkout {BRANCH}")

r = run("git branch --show-current")
if BRANCH not in r.stdout:
    print(f"FATAL: Could not switch to {BRANCH}")
    sys.exit(1)

# Fix 1: Add timezone to log format (suggestion from r5)
fpath = "traffic_coordinator_v5/traffic_coordinator_main.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

old = """logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)"""

new = """logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)"""

if old in content:
    content = content.replace(old, new)
    print(f"[OK] Added datefmt with timezone to logging.basicConfig")
else:
    print(f"[WARN] Could not find logging.basicConfig pattern")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Fix 2: O(1) -> O(1) average-case (suggestion from r5)
fpath = "core/coordinator.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

old = "        # checks the keys (robot IDs) — O(1) lookup."
new = "        # checks the keys (robot IDs) — O(1) average-case lookup."

if old in content:
    content = content.replace(old, new)
    print(f"[OK] Updated O(1) -> O(1) average-case in coordinator.py")
else:
    print(f"[WARN] Could not find O(1) lookup comment")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Show diff
print("\n--- GIT DIFF ---")
run("git diff --stat")
run("git diff")

# Commit and push
run("git add traffic_coordinator_v5/traffic_coordinator_main.py core/coordinator.py")
run('git commit -m "style: add timezone to log datefmt, clarify O(1) average-case per AI review r5"')
run(f"git push origin {BRANCH}")

print("\n[DONE] Round 5 fixes committed and pushed.")
