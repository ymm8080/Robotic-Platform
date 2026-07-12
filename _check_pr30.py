"""Check PR #30 branch lint and CI status."""
import subprocess
import time

# Checkout the PR branch
subprocess.run(["git", "checkout", "feat/p1-8-scenario-cli"], capture_output=True)

# Run ruff on the changed files
files = [
    "traffic_coordinator_v5/traffic_coordinator_main.py",
    "traffic_coordinator_v5/simulator/cli.py",
    "traffic_coordinator_v5/simulator/fleet.py",
    "traffic_coordinator_v5/simulator/map.py",
]
result = subprocess.run(
    ["python", "-m", "ruff", "check"] + files,
    capture_output=True, text=True
)
print("=== RUFF CHECK ===")
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print(f"Exit code: {result.returncode}")
