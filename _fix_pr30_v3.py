"""Cherry-pick the concurrent.futures fix onto feat/p1-8-scenario-cli and push."""
import subprocess

# Save the commit hash
commit_hash = "428dc70"

# Checkout the PR branch
result = subprocess.run(
    ["git", "checkout", "feat/p1-8-scenario-cli"],
    capture_output=True, text=True,
)
print(f"Checkout: {result.stdout} {result.stderr}")

# Verify we're on the right branch
branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
print(f"Current branch: {branch}")

if branch != "feat/p1-8-scenario-cli":
    print(f"ERROR: Expected feat/p1-8-scenario-cli but on {branch}")
    exit(1)

# Cherry-pick the commit
result = subprocess.run(
    ["git", "cherry-pick", commit_hash],
    capture_output=True, text=True,
)
print(f"Cherry-pick: {result.stdout} {result.stderr}")

# Push
result = subprocess.run(
    ["git", "push", "origin", "feat/p1-8-scenario-cli"],
    capture_output=True, text=True,
)
print(f"Push: {result.stdout} {result.stderr}")

# Verify
result = subprocess.run(
    ["git", "log", "--oneline", "-3"],
    capture_output=True, text=True,
)
print(f"Log:\n{result.stdout}")
