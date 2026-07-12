"""Fix PR #46: fix sap-bridge lint using exact CI command."""
import subprocess
import sys
import os

os.chdir(r"d:\EWM Robot\Robotic Platform Codes")

BRANCH = "fix/pr28-ai-review-final"


def run(cmd, check=False, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
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

# Run exact CI command: cd sap-bridge && ruff check . --config ruff.toml
print("=== CI EXACT: ruff check . --config ruff.toml (from sap-bridge/) ===")
result = run("ruff check . --config ruff.toml", cwd="sap-bridge")

if result.returncode != 0:
    print("\n=== FIXING: ruff check --fix . --config ruff.toml ===")
    run("ruff check --fix --unsafe-fixes . --config ruff.toml", cwd="sap-bridge")
    
    # Verify
    print("\n=== VERIFY: ruff check . --config ruff.toml ===")
    result2 = run("ruff check . --config ruff.toml", cwd="sap-bridge")
    if result2.returncode != 0:
        print("STILL FAILING! Manual fix needed.")
        sys.exit(1)

print("\n=== ALL RUFF CHECKS PASSED ===")

# Show diff
print("\n=== GIT DIFF STAT ===")
run("git diff --stat")
print("\n=== GIT DIFF ===")
run("git diff")

# Commit and push
run("git add -A sap-bridge/")
run('git commit -m "fix(lint): resolve all ruff errors using exact CI command (cd sap-bridge)"')
run(f"git push origin {BRANCH}")

print("\n[DONE] Lint fixes committed and pushed.")
