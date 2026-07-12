"""Fix PR #46: fix remaining UP031 + commit all sap-bridge lint fixes."""
import subprocess
import sys
import os

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

BRANCH = "fix/pr28-ai-review-final"


def run(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.buffer.write(f"$ {cmd}\n".encode("utf-8"))
    if r.stdout.strip():
        sys.stdout.buffer.write((r.stdout.strip() + "\n").encode("utf-8"))
    if r.stderr.strip():
        sys.stdout.buffer.write(("  STDERR: " + r.stderr.strip() + "\n").encode("utf-8"))
    sys.stdout.flush()
    return r


run("git stash", check=False)
run(f"git checkout {BRANCH}")

r = run("git branch --show-current")
if BRANCH not in r.stdout:
    print("FATAL: Could not switch to branch")
    sys.exit(1)

# Run ruff --fix with --unsafe-fixes to fix UP031
print("=== RUFF FIX (sap-bridge, with unsafe-fixes) ===")
run("python -m ruff check --fix --unsafe-fixes --config sap-bridge/ruff.toml sap-bridge/")

# Verify ruff passes
print("\n=== RUFF CHECK (sap-bridge) ===")
result = run("python -m ruff check --config sap-bridge/ruff.toml sap-bridge/")
if "All checks passed" in result.stdout:
    print("RUFF: All checks passed!")
else:
    print("RUFF: Still has errors!")
    sys.exit(1)

# Show diff
print("\n=== GIT DIFF STAT ===")
run("git diff --stat")
print("\n=== GIT DIFF ===")
run("git diff")

# Commit and push
run("git add -A sap-bridge/")
run('git commit -m "fix(lint): resolve all ruff errors in sap-bridge (I001, F401, UP031)"')
run(f"git push origin {BRANCH}")

print("\n[DONE] sap-bridge lint fixes committed and pushed.")
