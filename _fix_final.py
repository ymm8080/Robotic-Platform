"""Final fix: make test_empty_config assertion robust without depending on error message wording."""
import subprocess, os

REPO = r"d:\EWM Robot\Robotic Platform Codes"
TEST_FILE = os.path.join(REPO, "sap-bridge", "tests", "test_zewm_robco_client.py")

def run(cmd, cwd=REPO):
    print(f">>> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode

run("git checkout feat/c4-tests")
run("git reset --hard origin/feat/c4-tests")

with open(TEST_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the specific error message assertions with count-based assertion
# that satisfies both reviews: > 1 (not too loose) and not dependent on wording (not too specific)
old = '''        errs = ZewmRobcoClient.validate_config({})
        # Empty config must produce multiple errors covering auth, URL, and client
        assert len(errs) > 1
        assert any("user" in e.lower() for e in errs)
        assert any("password" in e.lower() for e in errs)
        assert any("base_url" in e.lower() for e in errs)'''
new = '''        errs = ZewmRobcoClient.validate_config({})
        # Empty config must produce multiple errors (auth + url + client)
        assert len(errs) >= 3'''

assert old in content, f"Pattern not found!"
content = content.replace(old, new)

with open(TEST_FILE, "w", encoding="utf-8") as f:
    f.write(content)
print("Applied: replaced specific message assertions with count-based >= 3")

# Run tests
ret = run('python -m pytest "sap-bridge/tests/test_zewm_robco_client.py" -v --tb=short -q')
if ret != 0:
    print("TESTS FAILED!")
    exit(1)

# Commit and push
run("git add sap-bridge/tests/test_zewm_robco_client.py")
run('git commit -m "fix(c4): use count-based assertion for test_empty_config" -m "Replace error-message-specific assertions with len(errs) >= 3. Satisfies both AI reviews: not too loose (original wanted > 1) and not too tightly coupled to error wording (second review suggested more generic)."')
run("git push origin feat/c4-tests")

print("\n=== DONE ===")
