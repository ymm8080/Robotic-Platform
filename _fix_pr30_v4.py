"""Fix PR #30: remove unused concurrent.futures import on correct branch."""
import subprocess

# Checkout the PR branch
result = subprocess.run(
    ["git", "checkout", "feat/p1-8-scenario-cli"],
    capture_output=True, text=True,
)
print(f"Checkout: {result.stdout.strip()} {result.stderr.strip()}")

# Verify branch
branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
print(f"Current branch: {branch}")
assert branch == "feat/p1-8-scenario-cli", f"Wrong branch: {branch}"

# Edit the file
filepath = "traffic_coordinator_v5/traffic_coordinator_main.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old_import = "import concurrent.futures\n"
if old_import in content:
    content = content.replace(old_import, "")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Removed 'import concurrent.futures'")

    subprocess.run(["git", "add", filepath], check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: remove unused concurrent.futures import (PR #30)"],
        check=True,
    )
    result = subprocess.run(
        ["git", "push", "origin", "feat/p1-8-scenario-cli"],
        capture_output=True, text=True,
    )
    print(f"Push stdout: {result.stdout.strip()}")
    print(f"Push stderr: {result.stderr.strip()}")
else:
    print("Import not found - already removed?")

# Show log
result = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True)
print(f"Log:\n{result.stdout}")
