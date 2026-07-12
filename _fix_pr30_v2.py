"""Fix PR #30: remove unused concurrent.futures import."""
import subprocess

subprocess.run(["git", "checkout", "feat/p1-8-scenario-cli"], capture_output=True)

filepath = "traffic_coordinator_v5/traffic_coordinator_main.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove unused import concurrent.futures
old_import = "import concurrent.futures\n"
if old_import in content:
    content = content.replace(old_import, "")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Removed unused 'import concurrent.futures'")
    subprocess.run(["git", "add", filepath], check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: remove unused concurrent.futures import (PR #30)"],
        check=True,
    )
    result = subprocess.run(
        ["git", "push", "origin", "feat/p1-8-scenario-cli"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    print("Done - pushed")
else:
    print("No change needed - import already removed")
