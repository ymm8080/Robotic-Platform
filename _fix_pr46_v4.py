"""Fix PR #46 AI review round 4: simplify logging config, fix docstring."""
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

# Fix 1: Simplify logging config — remove guard, basicConfig is idempotent by design
fpath = "traffic_coordinator_v5/traffic_coordinator_main.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

old = """# Configure root logger so _logger.info() calls produce output.
# Guard ensures idempotency: basicConfig is a no-op if handlers already exist,
# but we check explicitly to avoid overriding level set by another module.
_LOG_LEVEL = os.environ.get("TC_LOG_LEVEL", "WARNING" if MODE == "PRODUCTION" else "INFO")
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )"""

new = """# Configure root logger so _logger.info() calls produce output.
# logging.basicConfig() is idempotent by design: it only takes effect on the
# first call (when no handlers exist on the root logger). Subsequent calls are
# silent no-ops, so no guard is needed.
_LOG_LEVEL = os.environ.get("TC_LOG_LEVEL", "WARNING" if MODE == "PRODUCTION" else "INFO")
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)"""

if old in content:
    content = content.replace(old, new)
    print(f"[OK] Simplified logging config (removed guard, added idempotency comment)")
else:
    print(f"[WARN] Could not find logging config pattern")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Fix 2: Update robot.py docstring to say "3-digit milliseconds"
fpath = "traffic_coordinator_v5/simulator/robot.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

old = '"""Return an ISO-8601 UTC timestamp with millisecond precision (VDA5050 format)."""'
new = '"""Return an ISO-8601 UTC timestamp with 3-digit milliseconds (VDA5050 format)."""'

if old in content:
    content = content.replace(old, new)
    print(f"[OK] Updated _iso_now docstring")
else:
    print(f"[WARN] Could not find _iso_now docstring")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Fix 3: Add TC_LOG_LEVEL=DEBUG hint in coordinator.py debug comment
fpath = "core/coordinator.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

old = """                # Debug level: waypoint advancement is high-frequency (every
                # uplink); info/warning would flood production logs."""
new = """                # Debug level: waypoint advancement is high-frequency (every
                # uplink); info/warning would flood production logs.
                # Enable with TC_LOG_LEVEL=DEBUG."""

if old in content:
    content = content.replace(old, new)
    print(f"[OK] Added TC_LOG_LEVEL=DEBUG hint in coordinator.py")
else:
    print(f"[WARN] Could not find coordinator debug comment")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Show diff
print("\n--- GIT DIFF ---")
run("git diff --stat")
run("git diff")

# Commit and push
run("git add traffic_coordinator_v5/traffic_coordinator_main.py traffic_coordinator_v5/simulator/robot.py core/coordinator.py")
run('git commit -m "fix: simplify logging config (basicConfig is idempotent), clarify docstrings per AI review r4"')
run(f"git push origin {BRANCH}")

print("\n[DONE] Round 4 fixes committed and pushed.")
