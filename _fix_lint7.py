"""Fix PR #46: fix all sap-bridge lint errors."""
import subprocess
import sys
import os

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

BRANCH = "fix/pr28-ai-review-final"


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.buffer.write(f"$ {cmd}\n".encode("utf-8"))
    if r.stdout.strip():
        sys.stdout.buffer.write((r.stdout.strip() + "\n").encode("utf-8"))
    if r.stderr.strip():
        sys.stdout.buffer.write(("  STDERR: " + r.stderr.strip() + "\n").encode("utf-8"))
    sys.stdout.flush()
    if check and r.returncode != 0:
        sys.exit(1)
    return r


run("git stash", check=False)
run(f"git checkout {BRANCH}")

r = run("git branch --show-current")
if BRANCH not in r.stdout:
    print("FATAL: Could not switch to branch")
    sys.exit(1)

# Run ruff --fix on sap-bridge directory using its own ruff.toml
print("=== RUFF FIX (sap-bridge) ===")
run("python -m ruff check --fix --config sap-bridge/ruff.toml sap-bridge/")

# Verify ruff passes
print("\n=== RUFF CHECK (sap-bridge) ===")
run("python -m ruff check --config sap-bridge/ruff.toml sap-bridge/")

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
