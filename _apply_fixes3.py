"""Fix AI review issues in deepseek-review.py, auto-fix.sh, and pr-gate.yml."""
import pathlib

# 1. Fix deepseek-review.py - remove redundant .lower() list comprehension
p1 = pathlib.Path(".github/scripts/deepseek-review.py")
c1 = p1.read_text(encoding="utf-8")
old1 = 'has_issues = any(kw in review.lower() for kw in [k.lower() for k in issue_keywords])'
new1 = 'has_issues = any(kw in review.lower() for kw in issue_keywords)'
if old1 in c1:
    c1 = c1.replace(old1, new1)
    p1.write_text(c1, encoding="utf-8")
    print("deepseek-review.py: fixed redundant .lower()")
else:
    print("deepseek-review.py: pattern not found, may already be fixed")

# 2. Fix auto-fix.sh - fix gh pr checks command
p2 = pathlib.Path("auto-fix.sh")
c2 = p2.read_text(encoding="utf-8")
old2 = 'gh pr checks ${PR_NUMBER}'
new2 = 'gh pr view ${PR_NUMBER} --json statusCheckRollup'
if old2 in c2:
    c2 = c2.replace(old2, new2)
    p2.write_text(c2, encoding="utf-8")
    print("auto-fix.sh: fixed gh pr checks -> gh pr view --json statusCheckRollup")
else:
    print("auto-fix.sh: pattern not found")

# 3. Fix pr-gate.yml - remove invalid #issuecomment-new anchor
p3 = pathlib.Path(".github/workflows/pr-gate.yml")
c3 = p3.read_text(encoding="utf-8")
old3 = '#issuecomment-new'
new3 = ''
if old3 in c3:
    c3 = c3.replace(old3, new3)
    p3.write_text(c3, encoding="utf-8")
    print("pr-gate.yml: removed invalid #issuecomment-new anchor")
else:
    print("pr-gate.yml: pattern not found")

print("All fixes applied!")
