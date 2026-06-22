param()

$StatusFile = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\SESSION_STATUS.md"
$BriefFile = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\docs\claude-code-today-brief.md"

Write-Output ""
Write-Output "=============================================="
Write-Output "  LAST SESSION SUMMARY"
Write-Output "=============================================="

if (Test-Path $StatusFile) {
    $Content = Get-Content $StatusFile -Encoding UTF8 -Raw

    $UpdateTime = ""
    $Phase = ""
    $CompletedItems = @()
    $Decisions = @()
    $NextItems = @()
    $Topics = @()

    if ($Content -match "Last updated:\s*(.+)") {
        $UpdateTime = $Matches[1].Trim()
    }
    if ($Content -match "(?ms)## Current Phase\s*\n(.+?)(?=\n## )") {
        $Phase = $Matches[1].Trim()
    }

    if ($Content -match "(?ms)Completed This Session(.+?)(?=\n###|\n##)") {
        $Section = $Matches[1].Trim()
        $Section -split "`n" | ForEach-Object {
            $Line = $_.Trim()
            if ($Line -match "^-\s+(.+)" -or $Line -match "^\d+\.\s+(.+)") {
                $CompletedItems += $Matches[1].Trim()
            } elseif ($Line -ne "" -and $Line -notmatch "^[-\d\.]+\s*$") {
                $CompletedItems += $Line
            }
        }
    }

    if ($Content -match "(?ms)Topics Covered(.+?)(?=\n###|\n##)") {
        $Section = $Matches[1].Trim()
        $Section -split "`n" | ForEach-Object {
            if ($_.Trim() -match "^-\s+(.+)") {
                $Topics += $Matches[1].Trim()
            }
        }
    }

    if ($Content -match "(?ms)Key Decisions(.+?)(?=\n###|\n##)") {
        $Section = $Matches[1].Trim()
        $Section -split "`n" | ForEach-Object {
            if ($_.Trim() -match "^-\s+(.+)" -or $_.Trim() -match "^\d+\.\s+(.+)") {
                $Decisions += $Matches[1].Trim()
            }
        }
    }

    if ($Content -match "(?ms)Next Steps(.+?)(?=\n##)") {
        $Section = $Matches[1].Trim()
        $Section -split "`n" | ForEach-Object {
            if ($_.Trim() -match "^\d+\.\s+(.+)" -or $_.Trim() -match "^-\s+(.+)") {
                $NextItems += $Matches[1].Trim()
            }
        }
    }

    Write-Output ""
    if ($UpdateTime) { Write-Output "  Session Date: $UpdateTime" }
    if ($Phase) { Write-Output "  Phase: $Phase" }

    if ($CompletedItems.Count -gt 0) {
        Write-Output ""
        Write-Output "  COMPLETED:"
        $CompletedItems | ForEach-Object { Write-Output "    - $_" }
    }

    if ($Topics.Count -gt 0) {
        Write-Output ""
        Write-Output "  TOPICS:"
        $Topics | ForEach-Object { Write-Output "    - $_" }
    }

    if ($NextItems.Count -gt 0) {
        Write-Output ""
        Write-Output "  NEXT:"
        $NextItems | ForEach-Object { Write-Output "    - $_" }
    }
}
elseif (Test-Path $BriefFile) {
    $Content = Get-Content $BriefFile -Encoding UTF8 -Raw

    $Content -split "`n" | Select-Object -First 20 | ForEach-Object {
        Write-Output "  $_"
    }
}
else {
    Write-Output ""
    Write-Output "  No previous session found. Starting fresh!"
}

Write-Output ""
Write-Output "=============================================="
Write-Output ""
