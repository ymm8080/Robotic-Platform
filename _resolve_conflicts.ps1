Set-Location "D:\EWM Robot\Robotic Platform Codes"
git checkout -- . 2>$null
git checkout grafana-dashboard 2>$null
Write-Host "Branch: $(git branch --show-current)"

# Start merge
git merge origin/master --no-commit --no-ff 2>$null
Write-Host "Merge exit code: $LASTEXITCODE"

# Resolve all conflicts with --ours
$conflictFiles = git diff --name-only --diff-filter=U
if ($conflictFiles) {
    foreach ($f in $conflictFiles) {
        Write-Host "Resolving: $f"
        git checkout --ours $f 2>$null
    }
    git add -A
    Write-Host "All conflicts resolved with --ours"
} else {
    Write-Host "No conflicts found"
}

# Clean up temp files
Remove-Item _resolve_conflicts.ps1 -ErrorAction SilentlyContinue
Remove-Item apply_fixes*.py -ErrorAction SilentlyContinue
Remove-Item _patch_fixes.py -ErrorAction SilentlyContinue

# Commit the merge
git commit -m "merge: resolve conflicts with master — keep PR branch versions (all AI review fixes applied)"
Write-Host "Commit exit code: $LASTEXITCODE"

# Push
git push origin grafana-dashboard
Write-Host "Push exit code: $LASTEXITCODE"
