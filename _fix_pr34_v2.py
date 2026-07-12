"""Complete PR #34 fix: merge master, resolve conflicts, apply AI review fixes, lint, push."""
import subprocess, sys, os

def run(cmd, check=True, cwd=None):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    print(f"$ {cmd}")
    if result.stdout: print(result.stdout[:2000])
    if result.stderr: print(result.stderr[:2000], file=sys.stderr)
    if check and result.returncode != 0:
        print(f"FAILED exit {result.returncode}", file=sys.stderr)
        sys.exit(1)
    return result

CWD = r"D:\EWM Robot\Robotic Platform Codes"
BRANCH = "feat/auto-impl-sap-zewm-20260711-234536"

# 1. Reset to clean origin
run(f"git checkout -f {BRANCH}", cwd=CWD)
run(f"git reset --hard origin/{BRANCH}", cwd=CWD)
print("=== Reset done ===")

# 2. Merge master
mr = run("git merge origin/master --no-edit", check=False, cwd=CWD)
if mr.returncode != 0:
    cr = run("git diff --name-only --diff-filter=U", cwd=CWD)
    conflicts = [f.strip() for f in cr.stdout.splitlines() if f.strip()]
    print(f"Conflicts: {conflicts}")
    for f in conflicts:
        run(f'git checkout --ours "{f}"', cwd=CWD)
        run(f'git add "{f}"', cwd=CWD)
    run('git commit --no-edit -m "merge: resolve conflicts with master"', cwd=CWD)
    print("=== Merge resolved ===")
else:
    print("=== Merge clean ===")

# 3. Fix cli.py - add import random at module level
cli = os.path.join(CWD, "traffic_coordinator_v5", "simulator", "cli.py")
with open(cli, 'r', encoding='utf-8') as f:
    content = f.read()
# Check if import random already exists at module level (first 30 lines)
first_lines = '\n'.join(content.split('\n')[:30])
if 'import random' not in first_lines:
    content = content.replace('import logging\n', 'import logging\nimport random\n', 1)
    with open(cli, 'w', encoding='utf-8') as f:
        f.write(content)
    print("=== Fixed cli.py: added import random ===")
else:
    print("=== cli.py already has import random ===")

# 4. Fix fleet.py - logger.exception for MQTT failure
fleet = os.path.join(CWD, "traffic_coordinator_v5", "simulator", "fleet.py")
with open(fleet, 'r', encoding='utf-8') as f:
    content = f.read()
if 'logger.error("Failed to connect MQTT: %s", exc)' in content:
    content = content.replace(
        'logger.error("Failed to connect MQTT: %s", exc)',
        'logger.exception("Failed to connect MQTT")'
    )
    with open(fleet, 'w', encoding='utf-8') as f:
        f.write(content)
    print("=== Fixed fleet.py: logger.exception ===")
else:
    print("=== fleet.py already fixed or pattern not found ===")

# 5. Fix test_zewm_robco_client.py - add OAuth2 token to mock_redis
test = os.path.join(CWD, "sap-bridge", "tests", "test_zewm_robco_client.py")
with open(test, 'r', encoding='utf-8') as f:
    content = f.read()
if 'sap:oauth2:token' not in content:
    old = '''instance.get.side_effect = lambda key: {
            "sap:zewm_robco:csrf_token": "mock-csrf-token",
            "sap:zewm_robco:csrf_cookies": "sap-usercontext=mock",
        }.get(key)'''
    new = '''instance.get.side_effect = lambda key: {
            "sap:zewm_robco:csrf_token": "mock-csrf-token",
            "sap:zewm_robco:csrf_cookies": "sap-usercontext=mock",
            "sap:oauth2:token:https://sap-s4hana:44300/sap/bc/sec/oauth2/token": "mock-oauth2-token",
        }.get(key)'''
    if old in content:
        content = content.replace(old, new)
        with open(test, 'w', encoding='utf-8') as f:
            f.write(content)
        print("=== Fixed test: added OAuth2 token to mock_redis ===")
    else:
        print("=== test mock_redis pattern not found, skipping ===")
else:
    print("=== test already has OAuth2 token key ===")

# 6. Run ruff check --fix
run("python -m ruff check --fix sap-bridge/auth.py sap-bridge/clients/ sap-bridge/tests/test_zewm_robco_client.py traffic_coordinator_v5/simulator/cli.py traffic_coordinator_v5/simulator/fleet.py", check=False, cwd=CWD)
print("=== Ruff check done ===")

# 7. Commit all changes
run("git add -A", cwd=CWD)
run('git commit -m "fix: resolve merge conflicts + AI review fixes (cli.py import, fleet.py exception, test mock_redis)"', check=False, cwd=CWD)
print("=== Committed ===")

# 8. Push
run(f"git push origin {BRANCH}", cwd=CWD)
print("=== Pushed ===")

# 9. Verify
run("git log --oneline -3", cwd=CWD)
run("git status", cwd=CWD)
print("=== ALL DONE ===")
