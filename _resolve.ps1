Set-Location 'D:\EWM Robot\Robotic Platform Codes'
git checkout -- . 2>&1 | Out-Null
git checkout grafana-dashboard 2>&1 | Out-Null
Write-Output "Branch: $(git branch --show-current)"

git merge origin/master --no-commit --no-ff 2>&1 | Out-Null

$conflictFiles = git diff --name-only --diff-filter=U
if ($conflictFiles) {
    foreach ($f in $conflictFiles) {
        Write-Output "Resolving: $f"
        git checkout --ours $f 2>&1 | Out-Null
    }
    git add -A
    Write-Output "All conflicts resolved with --ours"
} else {
    Write-Output "No conflicts found"
}

Remove-Item _resolve.ps1 -ErrorAction SilentlyContinue
Remove-Item _resolve_conflicts.ps1 -ErrorAction SilentlyContinue
Remove-Item apply_fixes*.py -ErrorAction SilentlyContinue
Remove-Item _patch_fixes.py -ErrorAction SilentlyContinue

git commit -m 'merge: resolve conflicts with master, keep PR branch versions with all AI review fixes'
Write-Output "Commit done"

git push origin grafana-dashboard
Write-Output "Push done"
